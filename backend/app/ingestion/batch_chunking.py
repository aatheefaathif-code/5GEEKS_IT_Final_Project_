import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ingestion.chunking import chunk_pages
from app.ingestion.cleaning import clean_repeated_headers_footers
from app.ingestion.export import export_chunks_jsonl


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_inventory(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as inventory_file:
        rows = list(csv.DictReader(inventory_file))
    seen_ids: set[str] = set()
    for row in rows:
        textbook_id = row.get("textbook_id", "").strip()
        if not textbook_id or textbook_id in seen_ids:
            raise ValueError("Inventory contains missing or duplicate textbook IDs.")
        seen_ids.add(textbook_id)
    return rows


def _select_books(
    rows: list[dict[str, str]],
    textbook_ids: set[str] | None,
    limit_per_medium: int | None,
) -> list[dict[str, str]]:
    if textbook_ids is not None:
        row_by_id = {row["textbook_id"]: row for row in rows}
        unknown_ids = textbook_ids - row_by_id.keys()
        if unknown_ids:
            raise ValueError("Unknown textbook IDs: " + ", ".join(sorted(unknown_ids)))
        return [row for row in rows if row["textbook_id"] in textbook_ids]
    if limit_per_medium is None:
        return rows

    selected: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for row in rows:
        medium = row.get("medium", "unknown") or "unknown"
        if counts[medium] < limit_per_medium:
            selected.append(row)
            counts[medium] += 1
    return selected


def _read_verified_pages(
    page_path: Path,
    textbook: dict[str, str],
    expected_page_count: int,
    verification: dict[str, Any],
) -> list[dict[str, Any]]:
    with page_path.open(encoding="utf-8") as pages_file:
        pages = [json.loads(line) for line in pages_file if line.strip()]
    if len(pages) != expected_page_count:
        raise ValueError(
            f"Expected {expected_page_count} pages in {page_path}, got {len(pages)}."
        )
    expected_numbers = list(range(1, expected_page_count + 1))
    if [page.get("pdf_page_number") for page in pages] != expected_numbers:
        raise ValueError(f"Non-sequential PDF page numbers in {page_path}.")
    for page in pages:
        if page.get("textbook_id") != textbook["textbook_id"]:
            raise ValueError(f"Unexpected textbook ID in {page_path}.")
        if page.get("source_file") != textbook["relative_file_path"]:
            raise ValueError(f"Source path mismatch in {page_path}.")
        if (
            page.get("verification_status") != "verified"
            or page.get("human_verified") is not True
        ):
            raise ValueError(f"Refusing to chunk unverified page in {page_path}.")
        page_verification = page.get("human_verification", {})
        if page_verification.get("verification_method") != verification.get(
            "verification_method"
        ) or page_verification.get("verified_at") != verification.get("verified_at"):
            raise ValueError(f"Verification provenance mismatch in {page_path}.")
    return pages


def prepare_chunks(
    inventory_path: Path,
    batch_dir: Path,
    output_dir: Path,
    textbook_ids: set[str] | None = None,
    limit_per_medium: int | None = None,
    max_characters: int = 1400,
) -> dict[str, Any]:
    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    if limit_per_medium is not None and limit_per_medium < 1:
        raise ValueError("limit_per_medium must be positive")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise NotADirectoryError(f"Output path is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            raise FileExistsError(
                f"Output directory is not empty: {output_dir}. Choose a new path."
            )

    batch_report_path = batch_dir / "batch_ocr_report.json"
    batch_report = json.loads(batch_report_path.read_text(encoding="utf-8"))
    verification = batch_report.get("manual_verification", {})
    if (
        verification.get("verification_status") != "verified"
        or verification.get("verification_method")
        != "user_confirmed_source_pdf_comparison"
    ):
        raise ValueError("Batch does not contain a complete manual page verification.")

    books_in_report = {
        item["textbook_id"]: item
        for item in batch_report.get("processed_books", [])
        if item.get("status") == "processed"
    }
    inventory_rows = _read_inventory(inventory_path)
    selected = _select_books(inventory_rows, textbook_ids, limit_per_medium)
    if not selected:
        raise ValueError("No textbook records selected for chunking.")

    prepared: list[tuple[dict[str, str], list[dict[str, Any]]]] = []
    for textbook in selected:
        textbook_id = textbook["textbook_id"]
        book_report = books_in_report.get(textbook_id)
        if book_report is None:
            raise ValueError(
                f"Textbook is missing from OCR batch report: {textbook_id}."
            )
        if book_report.get("verification_status") != "verified":
            raise ValueError(f"Textbook pages are not marked verified: {textbook_id}.")
        if book_report.get("relative_file_path") != textbook["relative_file_path"]:
            raise ValueError(f"Inventory source path changed for {textbook_id}.")
        page_path = batch_dir / book_report["page_output"]
        page_count = int(textbook["page_count"])
        pages = _read_verified_pages(page_path, textbook, page_count, verification)
        prepared.append((textbook, pages))

    output_dir.mkdir(parents=True, exist_ok=True)
    book_summaries: list[dict[str, Any]] = []
    total_chunks = 0
    total_pages = 0
    for textbook, pages in prepared:
        cleaned_pages = clean_repeated_headers_footers(pages)
        metadata = {
            "textbook_id": textbook["textbook_id"],
            "grade": textbook.get("grade", "unknown") or "unknown",
            "subject": textbook.get("subject", "unknown") or "unknown",
            "medium": textbook.get("medium", "unknown") or "unknown",
            "textbook_title": textbook.get("textbook_title", "unknown") or "unknown",
            "edition_or_year": textbook.get("edition_or_year", "unknown") or "unknown",
            "chapter": "unknown",
            "lesson": "unknown",
            "topic": "unknown",
            "page_verification_status": "verified",
            "subject_verification_status": textbook.get(
                "subject_verification_status", "unknown"
            )
            or "unknown",
            "source_official_status": textbook.get("official_source_status", "unknown")
            or "unknown",
        }
        chunks = chunk_pages(cleaned_pages, metadata, max_characters)
        chunk_path = output_dir / f"{textbook['textbook_id']}.chunks.jsonl"
        count = export_chunks_jsonl(chunks, chunk_path)
        total_pages += len(pages)
        total_chunks += count
        book_summaries.append(
            {
                "textbook_id": textbook["textbook_id"],
                "source_file": textbook["relative_file_path"],
                "grade": metadata["grade"],
                "subject": metadata["subject"],
                "medium": metadata["medium"],
                "input_pages": len(pages),
                "pages_with_text": sum(bool(page["text"].strip()) for page in pages),
                "chunks": count,
                "chunk_file": chunk_path.name,
                "lesson_values": sorted(
                    {
                        str(chunk["lesson"])
                        for chunk in chunks
                        if chunk["lesson"] != "unknown"
                    }
                ),
            }
        )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "pipeline": "verified_ocr_to_cleaned_lesson_aware_chunks",
        "inventory_path": str(inventory_path.resolve()),
        "inventory_sha256": _sha256(inventory_path),
        "ocr_batch_report": str(batch_report_path.resolve()),
        "ocr_batch_report_sha256": _sha256(batch_report_path),
        "verification_method": verification["verification_method"],
        "verified_input_pages": total_pages,
        "books_selected": len(selected),
        "total_chunks": total_chunks,
        "max_characters": max_characters,
        "cleaning": "repeated page-edge headers and footers removed heuristically",
        "lesson_heading_detection": [
            "English: Chapter/Lesson",
            "Tamil: அத்தியாயம்/பாடம்",
            "Sinhala: පරිච්ඡේදය/පාඩම",
        ],
        "unknown_metadata_policy": (
            "Unsupported subject/title/edition/chapter/lesson/topic fields remain "
            "unknown; PDF page numbers are 1-based and are not printed-page claims."
        ),
        "embeddings_created": False,
        "vector_database_created": False,
        "books": book_summaries,
    }
    report_path = output_dir / "chunking_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description=(
            "Clean and lesson-chunk manually verified OCR page records without "
            "re-running OCR or creating embeddings."
        )
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=project_root / "data" / "manifests" / "textbook_inventory.csv",
    )
    parser.add_argument(
        "--batch-dir",
        type=Path,
        default=project_root / "data" / "extracted" / "full_ocr",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "data" / "extracted" / "chunk_pilot",
    )
    parser.add_argument(
        "--textbook-id",
        action="append",
        dest="textbook_ids",
        help="Select a textbook ID; may be repeated.",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--all",
        action="store_true",
        help="Chunk every manually verified textbook in the inventory.",
    )
    selection.add_argument(
        "--limit-per-medium",
        type=int,
        default=1,
        help="Pilot with the first N books per medium (default: 1).",
    )
    parser.add_argument("--max-characters", type=int, default=1400)
    args = parser.parse_args()
    if args.all and args.textbook_ids:
        parser.error("--all cannot be combined with --textbook-id.")
    limit = None if args.all or args.textbook_ids else args.limit_per_medium
    report = prepare_chunks(
        args.inventory,
        args.batch_dir,
        args.output_dir,
        textbook_ids=set(args.textbook_ids) if args.textbook_ids else None,
        limit_per_medium=limit,
        max_characters=args.max_characters,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "report": str((args.output_dir / "chunking_report.json").resolve()),
                "books_selected": report["books_selected"],
                "verified_input_pages": report["verified_input_pages"],
                "total_chunks": report["total_chunks"],
                "embeddings_created": report["embeddings_created"],
                "vector_database_created": report["vector_database_created"],
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
