import argparse
import csv
import hashlib
import json
import logging
import os
import shutil
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ingestion.extraction import OCR_LANGUAGES, extract_pdf_pages

LOGGER = logging.getLogger(__name__)
REPORT_NAME = "batch_ocr_report.json"


def _read_inventory(inventory_path: Path) -> list[dict[str, str]]:
    with inventory_path.open(encoding="utf-8-sig", newline="") as inventory_file:
        rows = list(csv.DictReader(inventory_file))
    if not rows:
        raise ValueError(f"Inventory is empty: {inventory_path}")

    textbook_ids = [row.get("textbook_id", "") for row in rows]
    relative_paths = [row.get("relative_file_path", "") for row in rows]
    if any(not value for value in textbook_ids + relative_paths):
        raise ValueError("Inventory rows must include textbook IDs and source paths.")
    if len(set(textbook_ids)) != len(textbook_ids):
        raise ValueError("Inventory contains duplicate textbook IDs.")
    if len(set(relative_paths)) != len(relative_paths):
        raise ValueError("Inventory contains duplicate source paths.")
    return rows


def _resolve_sources(
    rows: list[dict[str, str]], source_root: Path
) -> list[tuple[dict[str, str], Path]]:
    resolved_root = source_root.resolve()
    resolved: list[tuple[dict[str, str], Path]] = []
    missing: list[str] = []
    for row in rows:
        relative_path = Path(row["relative_file_path"])
        if relative_path.is_absolute():
            raise ValueError(
                f"Inventory source path must be relative: {row['relative_file_path']}"
            )
        source = (resolved_root / relative_path).resolve()
        if not source.is_relative_to(resolved_root):
            raise ValueError(
                f"Inventory source escapes source root: {row['relative_file_path']}"
            )
        if not source.is_file():
            missing.append(row["relative_file_path"])
        else:
            resolved.append((row, source))
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} inventory PDFs are missing under {resolved_root}: "
            + ", ".join(missing[:5])
        )
    return resolved


def _configure_tesseract(
    executable: Path | None, tessdata_dir: Path | None
) -> tuple[str, list[str]]:
    if executable is not None:
        resolved_executable = executable.resolve()
        if not resolved_executable.is_file():
            raise FileNotFoundError(
                f"Tesseract executable does not exist: {resolved_executable}"
            )
        os.environ["PATH"] = (
            str(resolved_executable.parent) + os.pathsep + os.environ.get("PATH", "")
        )

    if tessdata_dir is not None:
        resolved_tessdata = tessdata_dir.resolve()
        if not resolved_tessdata.is_dir():
            raise FileNotFoundError(
                f"Tesseract data directory does not exist: {resolved_tessdata}"
            )
        os.environ["TESSDATA_PREFIX"] = str(resolved_tessdata)

    tesseract = shutil.which("tesseract")
    if tesseract is None:
        raise RuntimeError(
            "Tesseract was not found on PATH. Pass --tesseract-executable."
        )
    completed = subprocess.run(
        [tesseract, "--list-langs"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    installed_languages = {
        line.strip() for line in completed.stdout.splitlines() if line.strip()
    }
    required_languages = set(OCR_LANGUAGES.values())
    missing_languages = required_languages - installed_languages
    if missing_languages:
        raise RuntimeError(
            "Tesseract language models are missing: "
            + ", ".join(sorted(missing_languages))
        )
    return tesseract, sorted(required_languages)


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _atomic_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for record in records:
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary_path.replace(path)


def _validate_existing_output(path: Path, textbook: dict[str, str]) -> dict[str, Any]:
    page_numbers: list[int] = []
    extraction_statuses: Counter[str] = Counter()
    ocr_attempted_pages = 0
    with path.open(encoding="utf-8") as output_file:
        for line_number, line in enumerate(output_file, start=1):
            record = json.loads(line)
            if record.get("textbook_id") != textbook["textbook_id"]:
                raise ValueError(f"Unexpected textbook ID in {path}:{line_number}")
            verification_status = record.get("verification_status")
            if verification_status not in ("unverified", "verified"):
                raise ValueError(
                    f"Missing supported verification marker in {path}:{line_number}"
                )
            if verification_status == "verified" and (
                record.get("human_verified") is not True
                or not record.get("human_verification", {}).get("verification_method")
            ):
                raise ValueError(
                    f"Missing human verification metadata in {path}:{line_number}"
                )
            page_numbers.append(record.get("pdf_page_number"))
            extraction_statuses[record.get("extraction_status", "unknown")] += 1
            ocr_attempted_pages += bool(record.get("ocr_attempted"))

    expected_page_count = int(textbook["page_count"])
    if page_numbers != list(range(1, expected_page_count + 1)):
        raise ValueError(
            f"Page sequence/count in {path} does not match inventory "
            f"({expected_page_count} expected)."
        )
    return {
        "page_count": len(page_numbers),
        "extraction_statuses": dict(extraction_statuses),
        "ocr_attempted_pages": ocr_attempted_pages,
    }


def _run_batch(
    rows: list[dict[str, str]],
    source_root: Path,
    output_dir: Path,
    inventory_path: Path,
    tesseract_path: str,
    languages: list[str],
    resume: bool,
) -> dict[str, Any]:
    selected_rows = rows
    resolved_sources = _resolve_sources(selected_rows, source_root)
    report_path = output_dir / REPORT_NAME
    inventory_hash = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    settings = {
        "source_root": str(source_root.resolve()),
        "inventory_sha256": inventory_hash,
        "books_selected": len(selected_rows),
        "tesseract_executable": tesseract_path,
        "tesseract_languages": languages,
        "render_dpi": 220,
        "ocr_policy": (
            "OCR pages without text for all media; additionally OCR Sinhala/Tamil "
            "pages whose text layer contains no expected-script characters."
        ),
        "verification_status": "unverified; manual page comparison required",
    }

    if report_path.exists():
        if not resume:
            raise FileExistsError(
                f"Batch report already exists: {report_path}. Use --resume or a new output directory."
            )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("settings") != settings:
            raise ValueError(
                "Cannot resume because the inventory or OCR settings differ from "
                "the existing batch report."
            )
    else:
        if resume and any(output_dir.iterdir()):
            raise ValueError(
                f"Cannot resume: output directory has files but no {REPORT_NAME}."
            )
        report = {
            "started_at": datetime.now(UTC).isoformat(),
            "settings": settings,
            "processed_books": [],
        }
        _atomic_json(report_path, report)

    completed = {
        item["textbook_id"]: item
        for item in report["processed_books"]
        if item.get("status") == "processed"
    }
    processed_ids = {item["textbook_id"] for item in report["processed_books"]}

    for index, (textbook, source_path) in enumerate(resolved_sources, start=1):
        textbook_id = textbook["textbook_id"]
        page_path = output_dir / f"{textbook_id}.pages.jsonl"
        if textbook_id in completed:
            existing_summary = _validate_existing_output(page_path, textbook)
            if existing_summary != completed[textbook_id].get("extraction_summary"):
                raise ValueError(f"Existing output summary does not match {page_path}.")
            LOGGER.info(
                "Skipping completed book %d/%d: %s",
                index,
                len(selected_rows),
                textbook_id,
            )
            continue
        if page_path.exists():
            raise FileExistsError(
                f"Output exists without a matching completed report: {page_path}"
            )
        if textbook_id in processed_ids:
            report["processed_books"] = [
                item
                for item in report["processed_books"]
                if item["textbook_id"] != textbook_id
            ]

        LOGGER.info(
            "Processing book %d/%d: %s (%s)",
            index,
            len(selected_rows),
            textbook_id,
            ascii(textbook["relative_file_path"]),
        )
        try:
            pages = extract_pdf_pages(
                source_path,
                textbook["relative_file_path"],
                textbook_id,
                textbook["medium"],
                use_ocr=True,
                ocr_on_missing_script=True,
            )
            for page in pages:
                page["verification_status"] = "unverified"
            if len(pages) != int(textbook["page_count"]):
                raise ValueError(
                    f"Inventory expects {textbook['page_count']} pages; "
                    f"PDF extraction returned {len(pages)}."
                )
            _atomic_jsonl(page_path, pages)
            extraction_summary = _validate_existing_output(page_path, textbook)
            record = {
                "textbook_id": textbook_id,
                "relative_file_path": textbook["relative_file_path"],
                "grade": textbook["grade"],
                "medium": textbook["medium"],
                "page_output": page_path.name,
                "status": "processed",
                "verification_status": "unverified",
                "extraction_summary": extraction_summary,
            }
        except Exception as error:
            LOGGER.exception(
                "Failed to process %s",
                ascii(textbook["relative_file_path"]),
            )
            record = {
                "textbook_id": textbook_id,
                "relative_file_path": textbook["relative_file_path"],
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }

        report["processed_books"] = [
            item
            for item in report["processed_books"]
            if item["textbook_id"] != textbook_id
        ]
        report["processed_books"].append(record)
        report["updated_at"] = datetime.now(UTC).isoformat()
        report["progress"] = {
            "completed_books": sum(
                item.get("status") == "processed" for item in report["processed_books"]
            ),
            "failed_books": sum(
                item.get("status") == "failed" for item in report["processed_books"]
            ),
            "total_books": len(selected_rows),
        }
        _atomic_json(report_path, report)

    report["finished_at"] = datetime.now(UTC).isoformat()
    report["progress"] = {
        "completed_books": sum(
            item.get("status") == "processed" for item in report["processed_books"]
        ),
        "failed_books": sum(
            item.get("status") == "failed" for item in report["processed_books"]
        ),
        "total_books": len(selected_rows),
    }
    _atomic_json(report_path, report)
    return report


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Extract page text and OCR missing-text/script pages for inventoried PDFs."
    )
    parser.add_argument(
        "--all", action="store_true", help="Process all inventory PDFs."
    )
    parser.add_argument(
        "--limit", type=int, help="Process only the first N inventory PDFs."
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=project_root / "data" / "manifests" / "textbook_inventory.csv",
    )
    parser.add_argument("--source-root", type=Path, default=project_root / "data")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tesseract-executable", type=Path)
    parser.add_argument("--tessdata-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.all and args.limit is None:
        parser.error(
            "Pass --all to process every inventory PDF or --limit for a smoke run."
        )
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer.")
    if args.all and args.limit is not None:
        parser.error("--all and --limit cannot be used together.")

    rows = _read_inventory(args.inventory)
    if args.limit is not None:
        rows = rows[: args.limit]
    if args.output_dir.exists() and not args.output_dir.is_dir():
        raise NotADirectoryError(f"Output path is not a directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if any(args.output_dir.iterdir()) and not args.resume:
        raise FileExistsError(
            f"Output directory is not empty: {args.output_dir}. "
            "Use --resume or choose a new directory."
        )

    tesseract_path, languages = _configure_tesseract(
        args.tesseract_executable,
        args.tessdata_dir,
    )
    report = _run_batch(
        rows,
        args.source_root,
        args.output_dir,
        args.inventory,
        tesseract_path,
        languages,
        args.resume,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "report": str((args.output_dir / REPORT_NAME).resolve()),
                "progress": report["progress"],
                "manual_verification_required": (
                    report.get("manual_verification", {}).get("verification_status")
                    != "verified"
                ),
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    if report["progress"]["failed_books"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
