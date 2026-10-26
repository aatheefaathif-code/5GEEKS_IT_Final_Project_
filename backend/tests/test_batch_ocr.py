import csv

from app.ingestion import batch_ocr


def test_batch_ocr_writes_unverified_pages_and_resumes_completed_book(
    tmp_path, monkeypatch
) -> None:
    source_root = tmp_path / "data"
    source_root.mkdir()
    (source_root / "book.pdf").write_bytes(b"PDF placeholder")
    inventory_path = tmp_path / "inventory.csv"
    with inventory_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=(
                "textbook_id",
                "relative_file_path",
                "page_count",
                "grade",
                "medium",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "textbook_id": "tb-test",
                "relative_file_path": "book.pdf",
                "page_count": "2",
                "grade": "1",
                "medium": "Tamil",
            }
        )

    output_dir = tmp_path / "full_ocr"
    output_dir.mkdir()
    fake_pages = [
        {
            "textbook_id": "tb-test",
            "pdf_page_number": page_number,
            "text": "தமிழ்",
            "extraction_status": "success",
            "ocr_attempted": page_number == 1,
        }
        for page_number in (1, 2)
    ]
    monkeypatch.setattr(
        batch_ocr,
        "extract_pdf_pages",
        lambda *_args, **_kwargs: fake_pages,
    )

    report = batch_ocr._run_batch(
        rows=batch_ocr._read_inventory(inventory_path),
        source_root=source_root,
        output_dir=output_dir,
        inventory_path=inventory_path,
        tesseract_path="tesseract",
        languages=["eng", "sin", "tam"],
        resume=False,
    )

    assert report["progress"] == {
        "completed_books": 1,
        "failed_books": 0,
        "total_books": 1,
    }
    assert report["processed_books"][0]["verification_status"] == "unverified"
    assert (
        report.get("manual_verification", {}).get("verification_status") != "verified"
    )

    def unexpected_ocr(*_args, **_kwargs):
        raise AssertionError("completed output should be resumed without OCR")

    monkeypatch.setattr(batch_ocr, "extract_pdf_pages", unexpected_ocr)
    resumed_report = batch_ocr._run_batch(
        rows=batch_ocr._read_inventory(inventory_path),
        source_root=source_root,
        output_dir=output_dir,
        inventory_path=inventory_path,
        tesseract_path="tesseract",
        languages=["eng", "sin", "tam"],
        resume=True,
    )

    assert resumed_report["progress"] == report["progress"]
