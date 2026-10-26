import json

import pytest
from app.ingestion.manual_verification import record_manual_verification


def _write_batch(tmp_path, pages):
    batch_dir = tmp_path / "full_ocr"
    queue_dir = tmp_path / "review_queue"
    batch_dir.mkdir()
    queue_dir.mkdir()
    (batch_dir / "tb-test.pages.jsonl").write_text(
        "".join(json.dumps(page) + "\n" for page in pages),
        encoding="utf-8",
    )
    report = {
        "progress": {"completed_books": 1, "failed_books": 0, "total_books": 1},
        "processed_books": [
            {
                "textbook_id": "tb-test",
                "page_output": "tb-test.pages.jsonl",
                "status": "processed",
                "verification_status": "unverified",
                "extraction_summary": {"page_count": len(pages)},
            }
        ],
    }
    (batch_dir / "batch_ocr_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    queue = [
        {
            "textbook_id": "tb-test",
            "pdf_page_number": 1,
            "verification_status": "unverified",
            "review_status": "unreviewed_triage",
        }
    ]
    (queue_dir / "page_review_queue.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in queue),
        encoding="utf-8",
    )
    (queue_dir / "page_review_queue_report.json").write_text(
        json.dumps({"unverified_or_not_verified_pages": len(pages)}),
        encoding="utf-8",
    )
    return batch_dir


def test_records_confirmed_manual_verification_for_each_page(tmp_path):
    batch_dir = _write_batch(
        tmp_path,
        [
            {
                "textbook_id": "tb-test",
                "pdf_page_number": page_number,
                "text": "OCR text",
                "verification_status": "unverified",
            }
            for page_number in (1, 2)
        ],
    )

    result = record_manual_verification(batch_dir, confirmed_page_count=2)

    pages = [
        json.loads(line)
        for line in (batch_dir / "tb-test.pages.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert result["verified_pages"] == 2
    assert all(page["verification_status"] == "verified" for page in pages)
    assert all(page["human_verified"] is True for page in pages)
    assert all(
        page["human_verification"]["verified_by"] == "user (identity not recorded)"
        for page in pages
    )

    queue_dir = batch_dir.parent / "review_queue"
    queued_page = json.loads(
        (queue_dir / "page_review_queue.jsonl").read_text(encoding="utf-8").strip()
    )
    queue_report = json.loads(
        (queue_dir / "page_review_queue_report.json").read_text(encoding="utf-8")
    )
    assert queued_page["verification_status"] == "verified"
    assert queued_page["review_status"] == "human_verified"
    assert queue_report["unverified_or_not_verified_pages"] == 0
    assert queue_report["human_verified_pages"] == 2


def test_refuses_confirmation_count_that_does_not_match_batch(tmp_path):
    batch_dir = _write_batch(
        tmp_path,
        [
            {
                "textbook_id": "tb-test",
                "pdf_page_number": 1,
                "text": "OCR text",
                "verification_status": "unverified",
            }
        ],
    )

    with pytest.raises(ValueError, match="does not match"):
        record_manual_verification(batch_dir, confirmed_page_count=2)

    page = json.loads(
        (batch_dir / "tb-test.pages.jsonl").read_text(encoding="utf-8").strip()
    )
    assert page["verification_status"] == "unverified"
