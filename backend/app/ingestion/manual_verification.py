import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VERIFICATION_METHOD = "user_confirmed_source_pdf_comparison"
VERIFIER = "user (identity not recorded)"


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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as input_file:
        return [json.loads(line) for line in input_file if line.strip()]


def _verification_record(
    record: dict[str, Any], verification: dict[str, str]
) -> dict[str, Any]:
    return {
        **record,
        "verification_status": "verified",
        "human_verified": True,
        "human_verification": verification,
    }


def record_manual_verification(
    batch_dir: Path,
    confirmed_page_count: int,
) -> dict[str, Any]:
    report_path = batch_dir / "batch_ocr_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    books = report.get("processed_books", [])
    if not books or report.get("progress", {}).get("failed_books", 0):
        raise ValueError("Manual verification requires a complete OCR batch.")
    if any(book.get("status") != "processed" for book in books):
        raise ValueError("Manual verification requires every book to be processed.")

    existing_verification = report.get("manual_verification")
    if existing_verification:
        if (
            existing_verification.get("verification_status") != "verified"
            or existing_verification.get("verification_method") != VERIFICATION_METHOD
        ):
            raise ValueError("Existing manual verification metadata is incompatible.")
        verification = existing_verification
    else:
        verification = {
            "verification_status": "verified",
            "verification_method": VERIFICATION_METHOD,
            "verified_by": VERIFIER,
            "verified_at": datetime.now(UTC).isoformat(),
            "scope": "all_textbook_pages",
            "page_count": 0,
            "basis": (
                "User confirmed all pages were compared with the source PDFs and "
                "found correct; no page-specific notes were provided."
            ),
        }

    page_updates: dict[tuple[str, int], dict[str, Any]] = {}
    updated_book_pages: dict[str, list[dict[str, Any]]] = {}
    for book in books:
        textbook_id = book["textbook_id"]
        page_path = batch_dir / book["page_output"]
        page_records = _read_jsonl(page_path)
        expected_pages = book.get("extraction_summary", {}).get("page_count")
        page_numbers = [record.get("pdf_page_number") for record in page_records]
        if (
            not page_records
            or len(page_records) != expected_pages
            or page_numbers != list(range(1, len(page_records) + 1))
        ):
            raise ValueError(f"Invalid or incomplete page records in {page_path}.")

        verified_records: list[dict[str, Any]] = []
        for record in page_records:
            key = (textbook_id, record["pdf_page_number"])
            if record.get("textbook_id") != textbook_id or key in page_updates:
                raise ValueError(f"Unexpected or duplicate page record in {page_path}.")
            if record.get("verification_status") not in ("unverified", "verified"):
                raise ValueError(f"Unsupported verification state in {page_path}.")
            if (
                record.get("verification_status") == "verified"
                and record.get("human_verification", {}).get("verification_method")
                != VERIFICATION_METHOD
            ):
                raise ValueError(
                    f"Page has incompatible existing verification in {page_path}."
                )
            verified_record = _verification_record(record, verification)
            page_updates[key] = verified_record
            verified_records.append(verified_record)
        updated_book_pages[book["page_output"]] = verified_records

    page_count = len(page_updates)
    if confirmed_page_count != page_count:
        raise ValueError(
            f"Confirmed page count {confirmed_page_count} does not match "
            f"the OCR batch count {page_count}."
        )

    verification["page_count"] = page_count
    queue_path = batch_dir.parent / "review_queue" / "page_review_queue.jsonl"
    queue_report_path = (
        batch_dir.parent / "review_queue" / "page_review_queue_report.json"
    )
    updated_queue: list[dict[str, Any]] | None = None
    queue_report: dict[str, Any] | None = None
    if queue_path.exists():
        updated_queue = []
        for record in _read_jsonl(queue_path):
            key = (record.get("textbook_id"), record.get("pdf_page_number"))
            if key not in page_updates:
                raise ValueError(f"Review queue contains an unknown page: {key}.")
            verified_queue_record = _verification_record(record, verification)
            verified_queue_record["review_status"] = "human_verified"
            updated_queue.append(verified_queue_record)
        if queue_report_path.exists():
            queue_report = json.loads(queue_report_path.read_text(encoding="utf-8"))
            queue_report.update(
                {
                    "verification_status": (
                        "all textbook pages are user-confirmed as manually "
                        "compared with source PDFs"
                    ),
                    "human_verified_pages": page_count,
                    "unverified_or_not_verified_pages": 0,
                    "manual_verification": verification,
                }
            )
            if "triage_rules" in queue_report:
                queue_report["triage_rules"]["P3"] = (
                    "no configured deterministic risk signal found; current "
                    "verification status comes from manual-verification metadata"
                )

    for book in books:
        book["verification_status"] = "verified"
    report["manual_verification"] = verification
    for page_output, records in updated_book_pages.items():
        _atomic_jsonl(batch_dir / page_output, records)
    if updated_queue is not None:
        _atomic_jsonl(queue_path, updated_queue)
    if queue_report is not None:
        _atomic_json(queue_report_path, queue_report)
    _atomic_json(report_path, report)
    return {
        "verification_status": verification["verification_status"],
        "verification_method": verification["verification_method"],
        "verified_pages": page_count,
        "books": len(books),
        "verification_metadata": verification,
    }


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Record a user-confirmed manual page verification."
    )
    parser.add_argument(
        "--batch-dir",
        type=Path,
        default=project_root / "data" / "extracted" / "full_ocr",
    )
    parser.add_argument(
        "--confirmed-page-count",
        type=int,
        required=True,
        help="Exact number of source-PDF pages the user confirms were reviewed.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            record_manual_verification(args.batch_dir, args.confirmed_page_count),
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
