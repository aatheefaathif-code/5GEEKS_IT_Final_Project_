import json

from app.ingestion import ollama_review


def test_ollama_assessment_is_never_verified_and_checks_quotes(monkeypatch) -> None:
    monkeypatch.setattr(
        ollama_review,
        "_ollama_json",
        lambda *_args, **_kwargs: {
            "message": {
                "content": json.dumps(
                    {
                        "concerns": [
                            {
                                "issue": "Possible missing digit",
                                "ocr_quote": "invented quote",
                                "confidence": "low",
                            }
                        ],
                        "human_review_needed": True,
                    }
                )
            },
            "done_reason": "stop",
        },
    )

    result = ollama_review._review_one(
        {"medium": "Tamil", "grade": "1", "pdf_page_number": 1},
        {"text": "தமிழ் உரை", "extraction_status": "success"},
        b"test image",
        "http://127.0.0.1:11434",
        "qwen3.5:4b",
    )

    assert result["review_status"] == "ai_review_only"
    assert result["human_verified"] is False
    assert result["assessment"]["human_review_needed"] is True
    assert result["assessment"]["concerns"][0]["quote_matches_ocr"] is False


def test_ollama_assessment_cannot_clear_human_review(monkeypatch) -> None:
    monkeypatch.setattr(
        ollama_review,
        "_ollama_json",
        lambda *_args, **_kwargs: {
            "message": {
                "content": json.dumps({"concerns": [], "human_review_needed": False})
            }
        },
    )

    result = ollama_review._review_one(
        {"medium": "English", "grade": "1", "pdf_page_number": 1},
        {"text": "A page of text.", "extraction_status": "success"},
        b"test image",
        "http://127.0.0.1:11434",
        "qwen3.5:4b",
    )

    assert result["assessment"]["model_human_review_recommended"] is False
    assert result["assessment"]["human_review_needed"] is True


def test_ollama_assessment_records_missing_quote_as_unmatched(monkeypatch) -> None:
    monkeypatch.setattr(
        ollama_review,
        "_ollama_json",
        lambda *_args, **_kwargs: {
            "message": {
                "content": json.dumps(
                    {
                        "concerns": [{"issue": "Possible problem"}],
                        "human_review_needed": True,
                    }
                )
            }
        },
    )

    result = ollama_review._review_one(
        {"medium": "English", "grade": "1", "pdf_page_number": 1},
        {"text": "A page of text.", "extraction_status": "success"},
        b"test image",
        "http://127.0.0.1:11434",
        "qwen3.5:4b",
    )

    concern = result["assessment"]["concerns"][0]
    assert concern["quote_matches_ocr"] is False
    assert concern["quote_validation_issue"] == "missing_or_non_string_quote"


def test_review_runner_resumes_completed_page_without_duplicate_output(
    tmp_path, monkeypatch
) -> None:
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    (batch_dir / "tb-test.pages.jsonl").write_text(
        json.dumps(
            {
                "textbook_id": "tb-test",
                "pdf_page_number": 1,
                "text": "",
                "extraction_status": "ocr_no_text",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    queue_path = tmp_path / "queue.jsonl"
    queue_path.write_text(
        json.dumps(
            {
                "textbook_id": "tb-test",
                "source_file": "book.pdf",
                "grade": "1",
                "medium": "Sinhala",
                "pdf_page_number": 1,
                "priority": "P0",
                "risk_reasons": ["empty_extracted_text"],
                "verification_status": "unverified",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "reviews"
    monkeypatch.setattr(ollama_review, "_check_vision_model", lambda *_args: None)
    monkeypatch.setattr(ollama_review, "_render_page", lambda *_args: b"page image")
    monkeypatch.setattr(
        ollama_review,
        "_review_one",
        lambda *_args: {
            "review_status": "ai_review_only",
            "human_verified": False,
            "assessment": {"concerns": [], "human_review_needed": True},
        },
    )

    report = ollama_review.run_reviews(
        queue_path=queue_path,
        batch_dir=batch_dir,
        source_root=tmp_path,
        output_dir=output_dir,
        endpoint="http://127.0.0.1:11434",
        model="qwen3.5:4b",
        priorities={"P0"},
    )

    assert report["completed_pages"] == 1
    assert report["human_verified_pages"] == 0

    def unexpected_rerun(*_args, **_kwargs):
        raise AssertionError("completed page must not be rerun")

    monkeypatch.setattr(ollama_review, "_review_one", unexpected_rerun)
    resumed_report = ollama_review.run_reviews(
        queue_path=queue_path,
        batch_dir=batch_dir,
        source_root=tmp_path,
        output_dir=output_dir,
        endpoint="http://127.0.0.1:11434",
        model="qwen3.5:4b",
        priorities={"P0"},
        resume=True,
    )

    result_path = output_dir / ollama_review.RESULTS_NAME
    results = [
        json.loads(line)
        for line in result_path.read_text(encoding="utf-8").splitlines()
    ]
    assert resumed_report["completed_pages"] == 1
    assert len(results) == 1
    assert results[0]["verification_status"] == "unverified"


def test_review_runner_marks_failed_request_as_not_reviewed(
    tmp_path, monkeypatch
) -> None:
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    (batch_dir / "tb-test.pages.jsonl").write_text(
        json.dumps(
            {
                "textbook_id": "tb-test",
                "pdf_page_number": 1,
                "text": "",
                "extraction_status": "ocr_no_text",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    queue_path = tmp_path / "queue.jsonl"
    queue_path.write_text(
        json.dumps(
            {
                "textbook_id": "tb-test",
                "source_file": "book.pdf",
                "grade": "1",
                "medium": "Sinhala",
                "pdf_page_number": 1,
                "priority": "P0",
                "risk_reasons": ["empty_extracted_text"],
                "verification_status": "unverified",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "reviews"
    monkeypatch.setattr(ollama_review, "_check_vision_model", lambda *_args: None)
    monkeypatch.setattr(ollama_review, "_render_page", lambda *_args: b"page image")

    def fail_review(*_args, **_kwargs):
        raise ValueError("invalid model response")

    monkeypatch.setattr(ollama_review, "_review_one", fail_review)
    report = ollama_review.run_reviews(
        queue_path=queue_path,
        batch_dir=batch_dir,
        source_root=tmp_path,
        output_dir=output_dir,
        endpoint="http://127.0.0.1:11434",
        model="qwen3.5:4b",
        priorities={"P0"},
    )

    result_path = output_dir / ollama_review.RESULTS_NAME
    result = json.loads(result_path.read_text(encoding="utf-8").strip())
    assert report["failed_pages"] == 1
    assert result["review_status"] == "request_failed"
    assert result["request_status"] == "failed"
    assert result["human_verified"] is False
