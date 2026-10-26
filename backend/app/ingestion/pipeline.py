import argparse
import json
import logging
from pathlib import Path
from typing import Any

from app.ingestion.chunking import chunk_pages
from app.ingestion.cleaning import clean_repeated_headers_footers
from app.ingestion.export import export_chunks_jsonl
from app.ingestion.extraction import extract_pdf_pages, write_jsonl

LOGGER = logging.getLogger(__name__)


def prepare_document(
    project_root: Path,
    relative_file_path: str,
    textbook: dict[str, str],
    max_characters: int = 1400,
    use_ocr: bool = False,
    ocr_all_pages: bool = False,
    ocr_on_missing_script: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = project_root / "data" / Path(relative_file_path)
    pages = extract_pdf_pages(
        source,
        relative_file_path,
        textbook["textbook_id"],
        textbook["medium"],
        use_ocr=use_ocr,
        ocr_all_pages=ocr_all_pages,
        ocr_on_missing_script=ocr_on_missing_script,
    )
    cleaned_pages = clean_repeated_headers_footers(pages)
    document_metadata = {
        "textbook_id": textbook["textbook_id"],
        "grade": textbook["grade"],
        "subject": textbook["subject"],
        "medium": textbook["medium"],
        "chapter": "unknown",
        "lesson": "unknown",
        "topic": "unknown",
    }
    chunks = chunk_pages(cleaned_pages, document_metadata, max_characters)
    return pages, chunks


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Extract, clean, chunk, and export one selected PDF."
    )
    parser.add_argument("--relative-file-path", required=True)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=project_root / "data" / "manifests" / "textbook_inventory.csv",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-characters", type=int, default=1400)
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument(
        "--ocr-all-pages",
        action="store_true",
        help="OCR pages with selectable text to address suspected font encodings.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    relative_file_path = Path(args.relative_file_path).as_posix()

    import csv

    with args.inventory.open(encoding="utf-8-sig", newline="") as inventory_file:
        inventory = {
            row["relative_file_path"]: row for row in csv.DictReader(inventory_file)
        }
    textbook = inventory.get(relative_file_path)
    if textbook is None:
        raise SystemExit(f"PDF is not present in the inventory: {relative_file_path}")

    try:
        pages, chunks = prepare_document(
            project_root,
            relative_file_path,
            textbook,
            args.max_characters,
            args.ocr or args.ocr_all_pages,
            ocr_all_pages=args.ocr_all_pages,
            ocr_on_missing_script=args.ocr and not args.ocr_all_pages,
        )
    except Exception:
        LOGGER.exception("Dataset processing failed for %s", ascii(relative_file_path))
        raise
    output_dir = args.output.parent
    page_output = output_dir / f"{args.output.stem}.pages.jsonl"
    write_jsonl(pages, page_output)
    count = export_chunks_jsonl(chunks, args.output)
    report = {
        "relative_file_path": relative_file_path,
        "page_count": len(pages),
        "pages_with_text": sum(bool(page["text"]) for page in pages),
        "pages_requiring_ocr": sum(
            page["extraction_status"] != "success" for page in pages
        ),
        "chunk_count": count,
        "page_output": str(page_output),
        "chunk_output": str(args.output),
    }
    report_path = output_dir / f"{args.output.stem}.report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
