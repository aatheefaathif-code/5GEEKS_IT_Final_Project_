import argparse
import csv
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
from collections import Counter
from datetime import datetime
from importlib import metadata, util
from pathlib import Path
from typing import Any

import pymupdf

from app.ingestion.extraction import extract_pdf_pages, write_jsonl
from app.ingestion.pilot import EXPECTED_SCRIPT_RANGES, _unicode_summary

LOGGER = logging.getLogger(__name__)
PILOT_TEXTBOOK_IDS = {
    "tb-c09bceea56f29c48": "English Grade 5",
    "tb-54a6625068631b2b": "Sinhala Grade 5 mathematics PDF",
    "tb-5d0eaaf98277f744": "Tamil Grade 5 mathematics PDF",
    "tb-9bd554bea9127760": "scanned Sinhala Grade 2 mathematics PDF",
}
IMAGE_MANIFEST_FIELDS = (
    "textbook_id",
    "source_file",
    "pdf_page_number",
    "image_index_on_page",
    "image_xref",
    "width_pixels",
    "height_pixels",
    "format",
    "image_path",
    "page_render_path",
    "page_text_context",
    "visual_interpretation",
    "validation_status",
)


def _script_character_count(text: str, medium: str) -> int:
    ranges = EXPECTED_SCRIPT_RANGES[medium]
    return sum(
        any(start <= ord(character) <= end for start, end in ranges)
        for character in text
    )


def _text_is_usable(text: str, medium: str) -> bool:
    if len(re.sub(r"\s+", "", text)) < 20:
        return False
    if medium in ("Tamil", "Sinhala"):
        return _script_character_count(text, medium) > 0
    return True


def _render_page(page: pymupdf.Page, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=130, alpha=False).save(destination)


def _page_table_records(page: pymupdf.Page) -> list[dict[str, Any]]:
    try:
        tables = page.find_tables().tables
    except Exception:
        LOGGER.exception(
            "Table detection failed on PDF page %d",
            page.number + 1,
        )
        return [
            {
                "pdf_page_number": page.number + 1,
                "detection_status": "failed",
                "human_review_required": True,
            }
        ]

    records = []
    for index, table in enumerate(tables, start=1):
        try:
            rows = table.extract()
            records.append(
                {
                    "pdf_page_number": page.number + 1,
                    "table_index_on_page": index,
                    "rows": rows,
                    "row_count": len(rows),
                    "detection_status": "heuristic_requires_visual_review",
                    "human_review_required": True,
                }
            )
        except Exception:
            LOGGER.exception("Table extraction failed on PDF page %d", page.number + 1)
            records.append(
                {
                    "pdf_page_number": page.number + 1,
                    "table_index_on_page": index,
                    "detection_status": "extraction_failed",
                    "human_review_required": True,
                }
            )
    return records


def _ocr_capabilities() -> dict[str, Any]:
    try:
        easyocr_version = metadata.version("easyocr")
    except metadata.PackageNotFoundError:
        easyocr_version = None
    cache = Path.home() / ".EasyOCR" / "model"
    cached_model_files = sorted(path.name for path in cache.glob("*") if path.is_file())
    tesseract_executable = shutil.which("tesseract")
    tessdata_dir = Path(
        os.environ.get(
            "TESSDATA_PREFIX",
            str(Path(tesseract_executable).resolve().parent / "tessdata")
            if tesseract_executable
            else "",
        )
    )
    tesseract_languages: list[str] = []
    tesseract_version = None
    if tesseract_executable and tessdata_dir.is_dir():
        try:
            version_result = subprocess.run(
                [tesseract_executable, "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            tesseract_version = version_result.stdout.splitlines()[0].strip()
            result = subprocess.run(
                [
                    tesseract_executable,
                    "--list-langs",
                    "--tessdata-dir",
                    str(tessdata_dir),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            tesseract_languages = sorted(
                line.strip()
                for line in result.stdout.splitlines()
                if re.fullmatch(r"[a-zA-Z0-9_]+", line.strip())
            )
        except (OSError, subprocess.CalledProcessError):
            LOGGER.exception("Unable to list Tesseract language models")

    language_data = {}
    for language in ("eng", "sin", "tam"):
        model_path = tessdata_dir / f"{language}.traineddata"
        if model_path.is_file():
            model_hash = hashlib.sha256()
            with model_path.open("rb") as model_file:
                for block in iter(lambda: model_file.read(1024 * 1024), b""):
                    model_hash.update(block)
            language_data[language] = {
                "installed": True,
                "size_bytes": model_path.stat().st_size,
                "sha256": model_hash.hexdigest(),
            }
        else:
            language_data[language] = {"installed": False}
    language_available = {
        language: (
            language in tesseract_languages
            and language_data[language]["installed"]
        )
        for language in ("eng", "sin", "tam")
    }
    return {
        "tesseract_executable": tesseract_executable is not None,
        "tesseract_version": tesseract_version,
        "tesseract_languages": tesseract_languages,
        "tesseract_language_data": language_data,
        "ocrmypdf_executable": shutil.which("ocrmypdf") is not None,
        "pdftoppm_executable": shutil.which("pdftoppm") is not None,
        "pytesseract_wrapper_installed": util.find_spec("pytesseract") is not None,
        "easyocr_package_version": easyocr_version,
        "easyocr_torch_module_installed": util.find_spec("torch") is not None,
        "easyocr_local_model_files": cached_model_files,
        "easyocr_model_ready_without_download": bool(cached_model_files),
        "missing_for_tesseract_ocr": [
            item
            for item, available in (
                ("Tesseract executable", tesseract_executable is not None),
                *[
                    (
                        f"Tesseract {language} trained data",
                        language_available[language],
                    )
                    for language in ("eng", "sin", "tam")
                ],
            )
            if not available
        ],
        "note": (
            "Tesseract and required language-data availability were checked locally. "
            "No vision model was invoked."
        ),
    }


def _selected_textbooks(
    inventory_path: Path,
    selected_ids: set[str],
) -> list[dict[str, str]]:
    with inventory_path.open(encoding="utf-8-sig", newline="") as source:
        records = {row["textbook_id"]: row for row in csv.DictReader(source)}
    missing_ids = selected_ids - records.keys()
    if missing_ids:
        raise ValueError(
            f"Selected IDs are missing from inventory: {sorted(missing_ids)}"
        )
    selected = [records[textbook_id] for textbook_id in sorted(selected_ids)]
    for row in selected:
        if row["grade"] not in {"2", "5"}:
            raise ValueError(f"Unexpected pilot grade for {row['textbook_id']}")
        if row["medium"] not in EXPECTED_SCRIPT_RANGES:
            raise ValueError(f"Unexpected pilot medium for {row['textbook_id']}")
        if row["verification_status"] != "unverified":
            raise ValueError(
                "Do not infer verification state; review the inventory row for "
                f"{row['textbook_id']}."
            )
    return selected


def run_multimodal_pilot(
    project_root: Path,
    inventory_path: Path,
    output_dir: Path,
    selected_ids: set[str] | None = None,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing pilot output: {output_dir}"
        )
    selected_ids = selected_ids or set(PILOT_TEXTBOOK_IDS)
    textbooks = _selected_textbooks(inventory_path, selected_ids)
    output_dir.mkdir(parents=True)
    images_dir = output_dir / "images"
    renders_dir = output_dir / "rendered_pages"
    images_dir.mkdir()
    renders_dir.mkdir()

    image_manifest: list[dict[str, str]] = []
    all_tables: list[dict[str, Any]] = []
    tables_by_textbook: dict[str, dict[int, list[dict[str, Any]]]] = {}
    document_reports = []
    all_page_records = []

    for textbook in textbooks:
        source_path = project_root / Path(textbook["relative_file_path"])
        pages = extract_pdf_pages(
            source_path,
            textbook["relative_file_path"],
            textbook["textbook_id"],
            textbook["medium"],
            use_ocr=(
                textbook["pdf_type"] == "scanned"
                or textbook["extraction_status"] == "unicode_mapping_review"
                or textbook["medium"] == "English"
            ),
            ocr_all_pages=(
                textbook["extraction_status"] == "unicode_mapping_review"
            ),
        )
        per_page_tables: dict[int, list[dict[str, Any]]] = {}
        page_render_paths: dict[int, str] = {}
        image_pages = []
        table_pages = []
        unique_images: dict[int, dict[str, Any]] = {}
        image_count_by_page: Counter[int] = Counter()
        table_records_by_page: dict[int, list[dict[str, Any]]] = {}
        extraction_failures = []

        with pymupdf.open(source_path) as document:
            for page_index, page in enumerate(document):
                page_number = page_index + 1
                page_images = page.get_images(full=True)
                if page_images:
                    image_pages.append(page_number)
                    image_count_by_page[page_number] = len(page_images)
                tables = _page_table_records(page)
                if tables:
                    table_pages.append(page_number)
                    table_records_by_page[page_number] = tables

                for image_index, image_info in enumerate(page_images, start=1):
                    xref = image_info[0]
                    if xref <= 0:
                        extraction_failures.append(
                            {
                                "pdf_page_number": page_number,
                                "image_xref": xref,
                                "error": "invalid or self-masked image reference",
                            }
                        )
                        continue
                    image_info_record = unique_images.get(xref)
                    if image_info_record is None:
                        try:
                            image_data = document.extract_image(xref)
                            extension = re.sub(
                                r"[^a-zA-Z0-9]", "", image_data["ext"]
                            ).lower()
                            image_relative_path = (
                                Path("images")
                                / textbook["textbook_id"]
                                / f"xref_{xref}.{extension or 'bin'}"
                            )
                            image_output_path = output_dir / image_relative_path
                            image_output_path.parent.mkdir(parents=True, exist_ok=True)
                            image_output_path.write_bytes(image_data["image"])
                            image_info_record = {
                                "image_path": image_relative_path.as_posix(),
                                "width_pixels": str(image_data["width"]),
                                "height_pixels": str(image_data["height"]),
                                "format": extension or "unknown",
                                "page_text_context": pages[page_number - 1]["text"][
                                    :500
                                ],
                            }
                            unique_images[xref] = image_info_record
                        except Exception as error:
                            LOGGER.exception(
                                "Image extraction failed for %s page %d xref %d",
                                ascii(textbook["relative_file_path"]),
                                page_number,
                                xref,
                            )
                            extraction_failures.append(
                                {
                                    "pdf_page_number": page_number,
                                    "image_xref": xref,
                                    "error": f"{type(error).__name__}: {error}",
                                }
                            )
                            continue

                    image_manifest.append(
                        {
                            "textbook_id": textbook["textbook_id"],
                            "source_file": textbook["relative_file_path"],
                            "pdf_page_number": str(page_number),
                            "image_index_on_page": str(image_index),
                            "image_xref": str(xref),
                            **image_info_record,
                            "page_render_path": "",
                            "page_text_context": pages[page_number - 1]["text"][:500],
                            "visual_interpretation": "not_performed",
                            "validation_status": "extracted_requires_human_review",
                        }
                    )

                if tables:
                    all_tables.extend(
                        {
                            "textbook_id": textbook["textbook_id"],
                            "source_file": textbook["relative_file_path"],
                            **table,
                        }
                        for table in tables
                    )

            selected_render_pages = set()
            if image_pages:
                image_page = max(
                    image_pages,
                    key=lambda number: (
                        bool(pages[number - 1]["text"]),
                        image_count_by_page[number],
                    ),
                )
                selected_render_pages.add(image_page)
            if table_pages:
                selected_render_pages.add(table_pages[0])
            if textbook["pdf_type"] == "scanned":
                selected_render_pages.add(
                    next(
                        (
                            page["pdf_page_number"]
                            for page in pages
                            if not page["text"]
                            and page["pdf_page_number"] > 1
                            and image_count_by_page[page["pdf_page_number"]] <= 3
                        ),
                        next(
                            (
                                page["pdf_page_number"]
                                for page in pages
                                if not page["text"]
                            ),
                            1,
                        ),
                    )
                )

            for page_number in sorted(selected_render_pages):
                render_relative_path = (
                    Path("rendered_pages")
                    / textbook["textbook_id"]
                    / f"page_{page_number:04}.png"
                )
                render_path = output_dir / render_relative_path
                _render_page(document[page_number - 1], render_path)
                page_render_paths[page_number] = render_relative_path.as_posix()
                for image in image_manifest:
                    if (
                        image["textbook_id"] == textbook["textbook_id"]
                        and int(image["pdf_page_number"]) == page_number
                    ):
                        image["page_render_path"] = render_relative_path.as_posix()

        for page in pages:
            page_number = page["pdf_page_number"]
            text = page["text"]
            page.update(
                {
                    "medium": textbook["medium"],
                    "text_character_count": len(text),
                    "expected_script_character_count": _script_character_count(
                        text, textbook["medium"]
                    ),
                    "usable_text": _text_is_usable(text, textbook["medium"]),
                    "image_reference_count": image_count_by_page[page_number],
                    "table_candidates": len(table_records_by_page.get(page_number, [])),
                    "rendered_page_path": page_render_paths.get(page_number),
                    "human_review_required": (
                        page["extraction_method"] == "tesseract_ocr"
                        or not _text_is_usable(text, textbook["medium"])
                        or page["extraction_status"] != "success"
                    ),
                }
            )
            per_page_tables[page_number] = table_records_by_page.get(page_number, [])
            all_page_records.append(page)
        tables_by_textbook[textbook["textbook_id"]] = per_page_tables

        page_output = output_dir / f"{textbook['textbook_id']}.pages.jsonl"
        write_jsonl(pages, page_output)
        page_text = "\n".join(page["text"] for page in pages if page["text"])
        ocr_page_count = sum(
            page["extraction_method"] == "tesseract_ocr" for page in pages
        )
        document_reports.append(
            {
                "textbook_id": textbook["textbook_id"],
                "selection_label": PILOT_TEXTBOOK_IDS.get(
                    textbook["textbook_id"], "test selection"
                ),
                "relative_file_path": textbook["relative_file_path"],
                "grade": textbook["grade"],
                "medium": textbook["medium"],
                "pdf_type": textbook["pdf_type"],
                "verification_status": textbook["verification_status"],
                "page_count": len(pages),
                "pages_with_any_selectable_text": sum(
                    page["extraction_method"] == "text_layer"
                    or bool(page["embedded_text"])
                    for page in pages
                ),
                "pages_with_extracted_text": sum(
                    bool(page["text"]) for page in pages
                ),
                "pages_with_usable_expected_language_text": sum(
                    page["usable_text"] for page in pages
                ),
                "pages_with_ocr_output": ocr_page_count,
                "pages_ocr_unavailable": sum(
                    page["extraction_status"] == "ocr_unavailable" for page in pages
                ),
                "pages_ocr_no_text": sum(
                    page["extraction_status"]
                    in {"ocr_no_text", "ocr_no_text_text_layer_retained"}
                    for page in pages
                ),
                "pages_ocr_failed": sum(
                    page["extraction_status"]
                    in {"ocr_failed", "ocr_failed_text_layer_retained"}
                    for page in pages
                ),
                "pages_with_ocr_script_output": sum(
                    page["extraction_method"] == "tesseract_ocr"
                    and page["expected_script_character_count"] > 0
                    for page in pages
                ),
                "pages_with_ocr_confidence": sum(
                    page["ocr_mean_confidence"] is not None for page in pages
                ),
                "mean_ocr_confidence": (
                    round(
                        sum(
                            page["ocr_mean_confidence"]
                            for page in pages
                            if page["ocr_mean_confidence"] is not None
                        )
                        / sum(
                            page["ocr_mean_confidence"] is not None
                            for page in pages
                        ),
                        2,
                    )
                    if any(
                        page["ocr_mean_confidence"] is not None for page in pages
                    )
                    else None
                ),
                "pages_requiring_human_review": sum(
                    page["human_review_required"] for page in pages
                ),
                "extracted_text_characters": len(page_text),
                **_unicode_summary(page_text, textbook["medium"]),
                "pages_with_embedded_images": len(image_pages),
                "embedded_image_references": sum(image_count_by_page.values()),
                "unique_images_extracted": len(unique_images),
                "image_extraction_failures": len(extraction_failures),
                "image_extraction_errors": extraction_failures,
                "table_candidate_pages": len(table_pages),
                "table_candidate_count": sum(
                    len(records) for records in table_records_by_page.values()
                ),
                "rendered_sample_pages": [
                    {
                        "pdf_page_number": page_number,
                        "file": path,
                        "reasons": [
                            reason
                            for condition, reason in (
                                (
                                    page_number in image_pages,
                                    "image-rich page",
                                ),
                                (
                                    page_number in table_pages,
                                    "heuristic table candidate",
                                ),
                                (
                                    textbook["pdf_type"] == "scanned",
                                    "scanned PDF page",
                                ),
                            )
                            if condition
                        ],
                    }
                    for page_number, path in page_render_paths.items()
                ],
                "page_text_file": page_output.relative_to(output_dir).as_posix(),
            }
        )

    ocr_records = [
        {
            "textbook_id": page["textbook_id"],
            "source_file": page["source_file"],
            "pdf_page_number": page["pdf_page_number"],
            "extraction_method": page["extraction_method"],
            "extraction_status": page["extraction_status"],
            "ocr_mean_confidence": page["ocr_mean_confidence"],
            "text": (
                page["text"]
                if page["extraction_method"] == "tesseract_ocr"
                else ""
            ),
            "human_review_required": page["human_review_required"],
        }
        for page in all_page_records
        if page["extraction_method"] == "tesseract_ocr"
        or "ocr" in page["extraction_status"]
    ]
    ocr_output = output_dir / "ocr_results.jsonl"
    write_jsonl(ocr_records, ocr_output)

    image_manifest_path = output_dir / "image_manifest.csv"
    with image_manifest_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as manifest_file:
        writer = csv.DictWriter(manifest_file, fieldnames=IMAGE_MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(image_manifest)

    table_output = output_dir / "table_candidates.jsonl"
    write_jsonl(all_tables, table_output)
    sample_output = output_dir / "sample_content.json"
    sample_pages = []
    for textbook_id in sorted(selected_ids):
        textbook_pages = [
            page for page in all_page_records if page["textbook_id"] == textbook_id
        ]
        candidate_pages = [
            page
            for page in textbook_pages
            if page["rendered_page_path"]
        ]
        for page in candidate_pages:
            render_reasons = []
            if page["image_reference_count"]:
                render_reasons.append("image or illustration present")
            if page["table_candidates"]:
                render_reasons.append("heuristic table candidate")
            if not page["text"]:
                render_reasons.append("scanned/image-only page")
            sample_pages.append(
                {
                    "textbook_id": textbook_id,
                    "source_file": page["source_file"],
                    "pdf_page_number": page["pdf_page_number"],
                    "text_sample": page["text"][:700],
                    "image_references": [
                        image
                        for image in image_manifest
                        if image["textbook_id"] == textbook_id
                        and int(image["pdf_page_number"]) == page["pdf_page_number"]
                    ][:8],
                    "tables": tables_by_textbook.get(textbook_id, {}).get(
                        page["pdf_page_number"], []
                    ),
                    "caption_status": (
                        "No image caption automatically verified; page text is context only."
                        if page["image_reference_count"]
                        else "No embedded images on this page."
                    ),
                    "render_reasons": render_reasons,
                    "human_review_required": True,
                }
            )
    sample_output.write_text(
        json.dumps(sample_pages, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    image_pages_total = sum(
        report["pages_with_embedded_images"] for report in document_reports
    )
    report = {
        "scope": "four selected PDFs only; no full-corpus processing",
        "usable_text_rule": (
            "Heuristic: at least 20 non-whitespace characters and (for Sinhala/Tamil) "
            "at least one expected-script character. This is not a human accuracy review."
        ),
        "selected_pdf_count": len(document_reports),
        "selected_documents": document_reports,
        "totals": {
            "pages": sum(report["page_count"] for report in document_reports),
            "pages_with_any_selectable_text": sum(
                report["pages_with_any_selectable_text"] for report in document_reports
            ),
            "pages_with_usable_expected_language_text": sum(
                report["pages_with_usable_expected_language_text"]
                for report in document_reports
            ),
            "pages_with_ocr_output": sum(
                report["pages_with_ocr_output"] for report in document_reports
            ),
            "pages_ocr_unavailable": sum(
                report["pages_ocr_unavailable"] for report in document_reports
            ),
            "pages_ocr_no_text": sum(
                report["pages_ocr_no_text"] for report in document_reports
            ),
            "pages_ocr_failed": sum(
                report["pages_ocr_failed"] for report in document_reports
            ),
            "pages_with_ocr_script_output": sum(
                report["pages_with_ocr_script_output"]
                for report in document_reports
            ),
            "pages_with_embedded_images": image_pages_total,
            "embedded_image_references": len(image_manifest),
            "unique_image_files": len(
                {image["image_path"] for image in image_manifest if image["image_path"]}
            ),
            "image_extraction_failures": sum(
                report["image_extraction_failures"] for report in document_reports
            ),
            "table_candidate_pages": sum(
                report["table_candidate_pages"] for report in document_reports
            ),
            "table_candidates": sum(
                report["table_candidate_count"] for report in document_reports
            ),
        },
        "ocr_capabilities": _ocr_capabilities(),
        "vision_analysis": {
            "performed": False,
            "limitation": (
                "No vision model was invoked. Extracted images and rendered pages "
                "are references for human review only."
            ),
        },
        "outputs": {
            "image_manifest": image_manifest_path.relative_to(output_dir).as_posix(),
            "table_candidates": table_output.relative_to(output_dir).as_posix(),
            "sample_content": sample_output.relative_to(output_dir).as_posix(),
            "ocr_results": ocr_output.relative_to(output_dir).as_posix(),
        },
    }
    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Run a bounded text/image/OCR pilot on four selected PDFs."
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=project_root / "data" / "manifests" / "textbook_inventory.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root
        / "data"
        / "extracted"
        / f"pilot_multimodal_{datetime.now():%Y%m%d_%H%M%S}",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.ERROR,
        format="%(levelname)s %(message)s",
    )
    report = run_multimodal_pilot(project_root, args.inventory, args.output_dir)
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
