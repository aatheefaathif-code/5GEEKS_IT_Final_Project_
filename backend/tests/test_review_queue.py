import json

import pytest
from app.ingestion.review_queue import build_review_queue, write_review_queue


def _write_batch(tmp_path, pages):
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    (batch_dir / "tb-test.pages.jsonl").write_text(
        "".join(json.dumps(page, ensure_ascii=False) + "\n" for page in pages),
        encoding="utf-8",
    )
    report = {
        "progress": {"failed_books": 0},
        "processed_books": [
            {
                "textbook_id": "tb-test",
                "relative_file_path": "Grade 01/Tamil/book.pdf",
                "grade": "1",
                "medium": "Tamil",
                "status": "processed",
                "page_output": "tb-test.pages.jsonl",
            }
        ],
    }
    (batch_dir / "batch_ocr_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    return batch_dir


def test_review_queue_prioritizes_missing_script_and_preserves_unverified_status(
    tmp_path,
) -> None:
    pages = [
        {
            "pdf_page_number": 1,
            "text": "",
            "extraction_status": "ocr_no_text",
            "extraction_method": "none",
            "verification_status": "unverified",
        },
        {
            "pdf_page_number": 2,
            "text": "English text only",
            "extraction_status": "success",
            "extraction_method": "text_layer",
            "verification_status": "unverified",
        },
        {
            "pdf_page_number": 3,
            "text": "தமிழ் உள்ளடக்கம்",
            "extraction_status": "success",
            "extraction_method": "tesseract_ocr",
            "ocr_attempted": True,
            "ocr_mean_confidence": 65,
            "verification_status": "unverified",
        },
    ]
    batch_dir = _write_batch(tmp_path, pages)

    queue, summary = build_review_queue(batch_dir)

    assert [item["pdf_page_number"] for item in queue] == [1, 2, 3]
    assert [item["priority"] for item in queue] == ["P0", "P1", "P2"]
    assert summary["total_pages_scanned"] == 3
    assert summary["queued_page_count"] == 3
    assert summary["unverified_or_not_verified_pages"] == 3
    assert all(item["verification_status"] == "unverified" for item in queue)
    assert all(item["review_status"] == "unreviewed_triage" for item in queue)


def test_review_queue_marks_pages_without_signals_as_unverified_not_verified(
    tmp_path,
) -> None:
    batch_dir = _write_batch(
        tmp_path,
        [
            {
                "pdf_page_number": 1,
                "text": "தமிழ் பாடம்",
                "extraction_status": "success",
                "extraction_method": "text_layer",
                "verification_status": "unverified",
            }
        ],
    )

    queue, summary = build_review_queue(batch_dir)

    assert queue == []
    assert summary["priority_counts"]["P3"] == 1
    assert summary["unverified_or_not_verified_pages"] == 1


def test_review_queue_preserves_manual_verification_status(tmp_path):
    batch_dir = _write_batch(
        tmp_path,
        [
            {
                "pdf_page_number": 1,
                "text": "தமிழ் பாடம்",
                "extraction_status": "success",
                "extraction_method": "text_layer",
                "ocr_attempted": True,
                "ocr_mean_confidence": 65,
                "verification_status": "verified",
                "human_verified": True,
                "human_verification": {
                    "verification_method": "user_confirmed_source_pdf_comparison"
                },
            }
        ],
    )

    queue, summary = build_review_queue(batch_dir)

    assert queue[0]["verification_status"] == "verified"
    assert queue[0]["human_verified"] is True
    assert queue[0]["review_status"] == "human_verified"
    assert summary["unverified_or_not_verified_pages"] == 0


def test_review_queue_refuses_failed_batch_and_does_not_overwrite(tmp_path) -> None:
    batch_dir = _write_batch(tmp_path, [])
    report_path = batch_dir / "batch_ocr_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["progress"]["failed_books"] = 1
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="while books failed"):
        build_review_queue(batch_dir)

    output_dir = tmp_path / "queue"
    output_dir.mkdir()
    (output_dir / "page_review_queue_report.json").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_review_queue(batch_dir, output_dir)
