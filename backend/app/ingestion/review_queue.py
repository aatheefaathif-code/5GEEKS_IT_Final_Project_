import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

EXPECTED_SCRIPT_RANGES = {
    "Sinhala": ((0x0D80, 0x0DFF),),
    "Tamil": ((0x0B80, 0x0BFF),),
}
LOW_CONFIDENCE_THRESHOLD = 70.0


def _contains_expected_script(text: str, medium: str) -> bool:
    ranges = EXPECTED_SCRIPT_RANGES.get(medium)
    return bool(
        ranges
        and any(
            start <= ord(character) <= end
            for character in text
            for start, end in ranges
        )
    )


def _page_risk(page: dict[str, Any], medium: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    status = str(page.get("extraction_status", "unknown"))
    text = str(page.get("text") or "")

    if not text.strip():
        reasons.append("empty_extracted_text")
    if "failed" in status or "unavailable" in status:
        reasons.append("extraction_or_ocr_failure")
    if status == "ocr_no_text_text_layer_retained":
        reasons.append("ocr_empty_original_text_retained")
    if (
        medium in EXPECTED_SCRIPT_RANGES
        and text.strip()
        and not _contains_expected_script(text, medium)
    ):
        reasons.append("expected_language_script_absent")
    confidence = page.get("ocr_mean_confidence")
    if (
        page.get("ocr_attempted")
        and isinstance(confidence, (int, float))
        and confidence < LOW_CONFIDENCE_THRESHOLD
    ):
        reasons.append("low_ocr_confidence_heuristic")

    if "empty_extracted_text" in reasons or "extraction_or_ocr_failure" in reasons:
        priority = "P0"
    elif any(
        reason in reasons
        for reason in (
            "ocr_empty_original_text_retained",
            "expected_language_script_absent",
        )
    ):
        priority = "P1"
    elif "low_ocr_confidence_heuristic" in reasons:
        priority = "P2"
    else:
        priority = "P3"
    return priority, reasons


def build_review_queue(batch_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report_path = batch_dir / "batch_ocr_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("progress", {}).get("failed_books", 0):
        raise ValueError("Cannot build a complete review queue while books failed.")

    queue: list[dict[str, Any]] = []
    priority_counts: Counter[str] = Counter()
    medium_counts: dict[str, Counter[str]] = defaultdict(Counter)
    reason_counts: Counter[str] = Counter()
    total_pages = 0
    unverified_pages = 0

    for book in report.get("processed_books", []):
        if book.get("status") != "processed":
            raise ValueError(
                f"Book is not fully processed: {book.get('textbook_id', 'unknown')}"
            )
        page_path = batch_dir / book["page_output"]
        with page_path.open(encoding="utf-8") as pages_file:
            for line_number, line in enumerate(pages_file, start=1):
                page = json.loads(line)
                total_pages += 1
                verification_status = page.get("verification_status", "unknown")
                unverified_pages += verification_status != "verified"
                priority, reasons = _page_risk(page, book.get("medium", "unknown"))
                priority_counts[priority] += 1
                medium_counts[book.get("medium", "unknown")][priority] += 1
                reason_counts.update(reasons)
                if priority == "P3":
                    continue
                queue.append(
                    {
                        "textbook_id": book["textbook_id"],
                        "source_file": book["relative_file_path"],
                        "grade": book.get("grade", "unknown"),
                        "medium": book.get("medium", "unknown"),
                        "pdf_page_number": page["pdf_page_number"],
                        "extraction_method": page.get("extraction_method"),
                        "extraction_status": page.get("extraction_status"),
                        "ocr_attempted": bool(page.get("ocr_attempted")),
                        "ocr_trigger": page.get("ocr_trigger"),
                        "ocr_mean_confidence": page.get("ocr_mean_confidence"),
                        "priority": priority,
                        "risk_reasons": reasons,
                        "verification_status": verification_status,
                        "human_verified": page.get("human_verified", False),
                        "human_verification": page.get("human_verification"),
                        "review_status": (
                            "human_verified"
                            if verification_status == "verified"
                            else "unreviewed_triage"
                        ),
                        "queue_source_line": line_number,
                    }
                )

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    queue.sort(
        key=lambda record: (
            priority_order[record["priority"]],
            record["grade"],
            record["medium"],
            record["textbook_id"],
            record["pdf_page_number"],
        )
    )
    verification_summary = (
        "all pages are marked verified from recorded human verification metadata"
        if unverified_pages == 0 and total_pages
        else "page verification status is preserved; triage does not verify content"
    )
    summary = {
        "batch_report": report_path.name,
        "model_used": False,
        "original_pages_modified": False,
        "verification_status": verification_summary,
        "total_pages_scanned": total_pages,
        "unverified_or_not_verified_pages": unverified_pages,
        "priority_counts": {
            priority: priority_counts[priority] for priority in ("P0", "P1", "P2", "P3")
        },
        "queued_page_count": len(queue),
        "risk_reason_counts": dict(reason_counts),
        "by_medium": {
            medium: {
                priority: counts[priority] for priority in ("P0", "P1", "P2", "P3")
            }
            for medium, counts in sorted(medium_counts.items())
        },
        "triage_rules": {
            "P0": "empty extracted text or extraction/OCR failure",
            "P1": "OCR returned no text while original layer was retained, or expected Sinhala/Tamil script is absent",
            "P2": f"OCR confidence below {LOW_CONFIDENCE_THRESHOLD:g}; heuristic only, not calibrated",
            "P3": (
                "no configured deterministic risk signal found; verification "
                "status is tracked separately"
            ),
        },
    }
    return queue, summary


def write_review_queue(batch_dir: Path, output_dir: Path) -> dict[str, Any]:
    queue_path = output_dir / "page_review_queue.jsonl"
    report_path = output_dir / "page_review_queue_report.json"
    existing_outputs = [path for path in (queue_path, report_path) if path.exists()]
    if existing_outputs:
        raise FileExistsError(
            "Refusing to overwrite review-queue output: "
            + ", ".join(str(path) for path in existing_outputs)
        )
    queue, summary = build_review_queue(batch_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    queue_temp = queue_path.with_suffix(queue_path.suffix + ".tmp")
    with queue_temp.open("w", encoding="utf-8", newline="\n") as queue_file:
        for record in queue:
            queue_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    queue_temp.replace(queue_path)
    summary["queue_file"] = queue_path.name
    report_temp = report_path.with_suffix(report_path.suffix + ".tmp")
    report_temp.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_temp.replace(report_path)
    return summary


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Prioritize OCR pages for review without changing OCR text."
    )
    parser.add_argument(
        "--batch-dir",
        type=Path,
        default=project_root / "data" / "extracted" / "full_ocr",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "data" / "extracted" / "review_queue",
    )
    args = parser.parse_args()
    summary = write_review_queue(args.batch_dir, args.output_dir)
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
