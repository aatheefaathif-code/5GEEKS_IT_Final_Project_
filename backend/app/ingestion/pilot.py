import argparse
import csv
import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from app.ingestion.extraction import extract_pdf_pages, write_jsonl

EXPECTED_SCRIPT_RANGES = {
    "English": ((0x0041, 0x024F),),
    "Sinhala": ((0x0D80, 0x0DFF),),
    "Tamil": ((0x0B80, 0x0BFF),),
}


def select_pilot_textbooks(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    usable = [
        row
        for row in rows
        if row["medium"] in EXPECTED_SCRIPT_RANGES
        and row["page_count"].isdigit()
        and row["pdf_type"] != "unknown"
    ]
    selected = []
    for medium in EXPECTED_SCRIPT_RANGES:
        candidates = [row for row in usable if row["medium"] == medium]
        if not candidates:
            continue
        text_candidates = [row for row in candidates if row["pdf_type"] == "text-based"]
        pool = text_candidates or candidates
        selected.append(
            max(
                pool,
                key=lambda row: (int(row["page_count"]), row["relative_file_path"]),
            )
        )

    scanned = [row for row in usable if row["pdf_type"] == "scanned"]
    if scanned and not any(row["pdf_type"] == "scanned" for row in selected):
        selected.append(
            max(
                scanned,
                key=lambda row: (int(row["page_count"]), row["relative_file_path"]),
            )
        )
    return selected


def _unicode_summary(text: str, medium: str) -> dict[str, Any]:
    ranges = EXPECTED_SCRIPT_RANGES[medium]
    expected_script_characters = sum(
        any(start <= ord(character) <= end for start, end in ranges)
        for character in text
    )
    replacement_characters = text.count("\ufffd")
    null_characters = text.count("\x00")
    other_control_characters = sum(
        unicodedata.category(character) == "Cc" and character not in "\n\r\t\x00"
        for character in text
    )
    if not text:
        unicode_check = "no extracted text; Unicode could not be assessed"
    elif expected_script_characters == 0:
        unicode_check = "expected script absent; manual extraction review needed"
    elif replacement_characters == 0 and null_characters == 0:
        unicode_check = "no obvious corruption markers detected"
    else:
        unicode_check = "possible Unicode corruption; review extracted text"
    return {
        "expected_script_characters": expected_script_characters,
        "replacement_characters": replacement_characters,
        "null_characters": null_characters,
        "other_control_characters": other_control_characters,
        "unicode_check": unicode_check,
    }


def run_pilot(
    project_root: Path,
    inventory_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    with inventory_path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))

    selected = select_pilot_textbooks(rows)
    documents = []
    for textbook in selected:
        pages = extract_pdf_pages(
            project_root / Path(textbook["relative_file_path"]),
            textbook["relative_file_path"],
            textbook["textbook_id"],
            textbook["medium"],
            use_ocr=True,
        )
        slug = re.sub(r"[^a-z0-9]+", "-", textbook["medium"].casefold()).strip("-")
        output_path = output_dir / (
            f"{slug}-grade-{textbook['grade']}-{textbook['textbook_id']}.pages.jsonl"
        )
        write_jsonl(pages, output_path)
        text = "\n".join(page["text"] for page in pages if page["text"])
        documents.append(
            {
                "textbook_id": textbook["textbook_id"],
                "relative_file_path": textbook["relative_file_path"],
                "grade": textbook["grade"],
                "medium": textbook["medium"],
                "pdf_type": textbook["pdf_type"],
                "inventory_extraction_status": textbook["extraction_status"],
                "textbook_title": textbook["textbook_title"],
                "page_count": len(pages),
                "pages_with_text": sum(bool(page["text"]) for page in pages),
                "pages_requiring_ocr": sum(
                    page["extraction_status"] != "success" for page in pages
                ),
                "ocr_unavailable_pages": sum(
                    page["extraction_status"] == "ocr_unavailable" for page in pages
                ),
                "extracted_characters": len(text),
                **_unicode_summary(text, textbook["medium"]),
                "output_file": output_path.as_posix(),
            }
        )

    report = {
        "scope": "small pilot only; no other PDFs were extracted",
        "selected_document_count": len(documents),
        "ocr_executable_available": shutil.which("tesseract") is not None,
        "documents": documents,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "pilot_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Extract a small multilingual PDF pilot."
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=project_root / "data" / "manifests" / "textbook_inventory.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "data" / "extracted" / "pilot",
    )
    args = parser.parse_args()
    report = run_pilot(project_root, args.inventory, args.output_dir)
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
