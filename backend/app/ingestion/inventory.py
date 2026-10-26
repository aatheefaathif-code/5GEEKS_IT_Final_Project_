import argparse
import csv
import hashlib
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pymupdf

GRADE_FOLDER = re.compile(r"^Grade\s+(0?[1-5])$", re.IGNORECASE)
MEDIA = {"english": "English", "sinhala": "Sinhala", "tamil": "Tamil"}
SCRIPT_RANGES = {
    "English": ((0x0041, 0x024F),),
    "Sinhala": ((0x0D80, 0x0DFF),),
    "Tamil": ((0x0B80, 0x0BFF),),
}
FIELDS = (
    "textbook_id",
    "relative_file_path",
    "grade",
    "subject",
    "medium",
    "textbook_title",
    "edition_or_year",
    "page_count",
    "pdf_type",
    "extraction_status",
    "verification_status",
)
LOGGER = logging.getLogger(__name__)


def _folder_metadata(relative_path: Path) -> tuple[str, str]:
    grade = "unknown"
    medium = "unknown"
    for part in relative_path.parts[:-1]:
        grade_match = GRADE_FOLDER.fullmatch(part)
        if grade_match:
            grade = str(int(grade_match.group(1)))
        normalized = part.casefold()
        for key, label in MEDIA.items():
            if re.match(rf"^{re.escape(key)}(?:$|[-_\s])", normalized):
                medium = label
                break
    return grade, medium


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inspect_pdf(path: Path, medium: str) -> dict[str, Any]:
    with pymupdf.open(path) as document:
        page_count = len(document)
        if page_count == 0:
            raise ValueError("PDF contains no pages")

        text_page_count = 0
        image_only_page_count = 0
        expected_script_characters = 0
        pages_with_text_missing_expected_script = 0
        script_ranges = SCRIPT_RANGES.get(medium, ())
        for page in document:
            text = page.get_text("text")
            has_text = bool(re.sub(r"\s+", "", text))
            if has_text:
                text_page_count += 1
            script_count = sum(
                any(start <= ord(character) <= end for start, end in script_ranges)
                for character in text
            )
            expected_script_characters += script_count
            if has_text and script_ranges and script_count == 0:
                pages_with_text_missing_expected_script += 1
            if page.get_images(full=True) and not has_text:
                image_only_page_count += 1

        if text_page_count > 0 and image_only_page_count == 0:
            pdf_type = "text-based"
            extraction_status = "success"
        elif text_page_count == 0 and image_only_page_count > 0:
            pdf_type = "scanned"
            extraction_status = "requires_ocr"
        elif text_page_count > 0 and image_only_page_count > 0:
            pdf_type = "mixed"
            extraction_status = "partial_requires_ocr"
        else:
            pdf_type = "unknown"
            extraction_status = "no_extractable_text"

        metadata = document.metadata or {}
        metadata_title = (metadata.get("title") or "").strip()
        title = metadata_title if metadata_title else "unknown"
        suspected_text_encoding = (
            medium in SCRIPT_RANGES
            and text_page_count > 0
            and expected_script_characters == 0
        )
        if suspected_text_encoding and pdf_type == "text-based":
            extraction_status = "unicode_mapping_review"

        return {
            "page_count": page_count,
            "pdf_type": pdf_type,
            "extraction_status": extraction_status,
            "text_page_count": text_page_count,
            "pages_requiring_ocr": image_only_page_count,
            "expected_script_characters": expected_script_characters,
            "pages_with_text_missing_expected_script": (
                pages_with_text_missing_expected_script
            ),
            "suspected_text_encoding": suspected_text_encoding,
            "textbook_title": title,
        }


def inventory_rows(root: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rows: list[dict[str, str]] = []
    hashes: dict[str, list[str]] = defaultdict(list)
    unreadable: list[dict[str, str]] = []
    pages_requiring_ocr = 0
    text_encoding_review: list[dict[str, str]] = []
    root = root.resolve()

    grade_folders = sorted(
        (
            path
            for path in root.iterdir()
            if path.is_dir() and GRADE_FOLDER.fullmatch(path.name)
        ),
        key=lambda path: path.name.casefold(),
    )
    for grade_folder in grade_folders:
        for pdf_path in sorted(
            grade_folder.rglob("*"),
            key=lambda path: path.as_posix().casefold(),
        ):
            if not pdf_path.is_file() or pdf_path.suffix.casefold() != ".pdf":
                continue

            relative_path = pdf_path.relative_to(root)
            relative_path_text = relative_path.as_posix()
            grade, medium = _folder_metadata(relative_path)
            textbook_id = (
                "tb-"
                + hashlib.sha256(relative_path_text.encode("utf-8")).hexdigest()[:16]
            )
            row = {
                "textbook_id": textbook_id,
                "relative_file_path": relative_path_text,
                "grade": grade,
                "subject": "unknown",
                "medium": medium,
                "textbook_title": "unknown",
                "edition_or_year": "unknown",
                "page_count": "unknown",
                "pdf_type": "unknown",
                "extraction_status": "unreadable",
                "verification_status": "unverified",
            }

            try:
                hashes[_file_sha256(pdf_path)].append(relative_path_text)
            except OSError as error:
                LOGGER.exception("Cannot hash PDF %s", ascii(relative_path_text))
                unreadable.append(
                    {
                        "relative_file_path": relative_path_text,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
            try:
                inspected = _inspect_pdf(pdf_path, medium)
                row.update(
                    {
                        "textbook_title": inspected["textbook_title"],
                        "page_count": str(inspected["page_count"]),
                        "pdf_type": inspected["pdf_type"],
                        "extraction_status": inspected["extraction_status"],
                    }
                )
                pages_requiring_ocr += inspected["pages_requiring_ocr"]
                if inspected["suspected_text_encoding"]:
                    text_encoding_review.append(
                        {
                            "relative_file_path": relative_path_text,
                            "medium": medium,
                            "pages_with_text_missing_expected_script": str(
                                inspected["pages_with_text_missing_expected_script"]
                            ),
                        }
                    )
            except Exception as error:
                LOGGER.exception("Cannot inspect PDF %s", ascii(relative_path_text))
                if not any(
                    item["relative_file_path"] == relative_path_text
                    for item in unreadable
                ):
                    unreadable.append(
                        {
                            "relative_file_path": relative_path_text,
                            "error": f"{type(error).__name__}: {error}",
                        }
                    )
            rows.append(row)

    duplicates = [paths for paths in hashes.values() if len(paths) > 1]
    counts: Counter[tuple[str, str]] = Counter(
        (row["grade"], row["medium"]) for row in rows
    )
    metadata_fields = (
        "grade",
        "subject",
        "medium",
        "textbook_title",
        "edition_or_year",
        "page_count",
        "pdf_type",
    )
    metadata_issues = [
        {
            "relative_file_path": row["relative_file_path"],
            "unknown_fields": [
                field for field in metadata_fields if row[field] == "unknown"
            ],
        }
        for row in rows
        if any(row[field] == "unknown" for field in metadata_fields)
    ]
    summary: dict[str, Any] = {
        "pdf_count": len(rows),
        "counts_by_grade_and_medium": {
            f"grade_{grade}|{medium}": count
            for (grade, medium), count in sorted(counts.items())
        },
        "unreadable_pdfs": unreadable,
        "duplicate_files": duplicates,
        "scanned_pdfs": [
            row["relative_file_path"] for row in rows if row["pdf_type"] == "scanned"
        ],
        "mixed_pdfs": [
            row["relative_file_path"] for row in rows if row["pdf_type"] == "mixed"
        ],
        "pages_requiring_ocr": pages_requiring_ocr,
        "suspected_text_encoding": text_encoding_review,
        "unknown_grade_or_medium": [
            row["relative_file_path"]
            for row in rows
            if row["grade"] == "unknown" or row["medium"] == "unknown"
        ],
        "unknown_subject": sum(row["subject"] == "unknown" for row in rows),
        "unknown_title": sum(row["textbook_title"] == "unknown" for row in rows),
        "unknown_edition": sum(row["edition_or_year"] == "unknown" for row in rows),
        "unverified_count": sum(
            row["verification_status"] == "unverified" for row in rows
        ),
        "metadata_issues": metadata_issues,
    }
    return rows, summary


def write_inventory(root: Path, output: Path) -> dict[str, Any]:
    rows, summary = inventory_rows(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as inventory_file:
        writer = csv.DictWriter(inventory_file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Inspect local grade 1–5 PDFs and create a verified-field inventory."
    )
    parser.add_argument("--root", type=Path, default=project_root)
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "data" / "manifests" / "textbook_inventory.csv",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = write_inventory(args.root, args.output)
    if args.report:
        import json

        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"PDF count: {summary['pdf_count']}")
    for key, count in summary["counts_by_grade_and_medium"].items():
        print(f"{key}: {count}")
    print(f"Unreadable: {len(summary['unreadable_pdfs'])}")
    print(f"Duplicate groups: {len(summary['duplicate_files'])}")
    print(f"Scanned (OCR needed): {len(summary['scanned_pdfs'])}")
    print(f"Mixed (some OCR needed): {len(summary['mixed_pdfs'])}")
    print(f"Unknown grade/medium: {len(summary['unknown_grade_or_medium'])}")
    print(
        "Unknown subject/title/edition: "
        f"{summary['unknown_subject']}/{summary['unknown_title']}/"
        f"{summary['unknown_edition']}"
    )
    print(f"Inventory: {args.output}")
    if args.report:
        print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
