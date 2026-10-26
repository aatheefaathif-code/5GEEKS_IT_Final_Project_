import csv
import json

import pytest
from app.ingestion.batch_chunking import prepare_chunks

VERIFICATION = {
    "verification_status": "verified",
    "verification_method": "user_confirmed_source_pdf_comparison",
    "verified_at": "2026-10-19T00:00:00+00:00",
}


def _write_inputs(tmp_path, pages, subject="unknown"):
    manifest = tmp_path / "inventory.csv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "textbook_id": "tb-test",
        "relative_file_path": "Grade 01/English/book.pdf",
        "grade": "1",
        "subject": subject,
        "medium": "English",
        "textbook_title": "unknown",
        "edition_or_year": "unknown",
        "page_count": str(len(pages)),
        "official_source_status": "user_attested_official",
        "subject_verification_status": "user_confirmed",
    }
    with manifest.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    batch_dir = tmp_path / "full_ocr"
    batch_dir.mkdir()
    page_path = batch_dir / "tb-test.pages.jsonl"
    page_path.write_text(
        "".join(json.dumps(page) + "\n" for page in pages),
        encoding="utf-8",
    )
    batch_report = {
        "manual_verification": {
            **VERIFICATION,
            "page_count": len(pages),
        },
        "processed_books": [
            {
                "textbook_id": "tb-test",
                "relative_file_path": row["relative_file_path"],
                "page_output": page_path.name,
                "status": "processed",
                "verification_status": "verified",
            }
        ],
    }
    (batch_dir / "batch_ocr_report.json").write_text(
        json.dumps(batch_report), encoding="utf-8"
    )
    return manifest, batch_dir


def _page(number, text, verification_status="verified"):
    return {
        "textbook_id": "tb-test",
        "source_file": "Grade 01/English/book.pdf",
        "pdf_page_number": number,
        "text": text,
        "verification_status": verification_status,
        "human_verified": verification_status == "verified",
        "human_verification": VERIFICATION,
    }


def test_batch_chunking_preserves_lessons_pages_and_unknown_metadata(tmp_path):
    manifest, batch_dir = _write_inputs(
        tmp_path,
        [
            _page(
                1,
                "Lesson 1\nFirst lesson content.\n\nLesson 2\nSecond lesson content.",
            ),
            _page(2, "More content for lesson two."),
        ],
    )
    output_dir = tmp_path / "chunks"

    report = prepare_chunks(manifest, batch_dir, output_dir, max_characters=100)

    chunks = [
        json.loads(line)
        for line in (output_dir / "tb-test.chunks.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert report["verified_input_pages"] == 2
    assert report["total_chunks"] == 3
    assert [(chunk["lesson"], chunk["pdf_page_number"]) for chunk in chunks] == [
        ("1", 1),
        ("2", 1),
        ("2", 2),
    ]
    assert all(chunk["subject"] == "unknown" for chunk in chunks)
    assert all(chunk["page_verification_status"] == "verified" for chunk in chunks)
    assert all(
        chunk["source_official_status"] == "user_attested_official" for chunk in chunks
    )


def test_batch_chunking_rejects_any_unverified_page_without_output(tmp_path):
    manifest, batch_dir = _write_inputs(
        tmp_path,
        [_page(1, "Lesson 1\nSome text.", verification_status="unverified")],
    )
    output_dir = tmp_path / "chunks"

    with pytest.raises(ValueError, match="unverified page"):
        prepare_chunks(manifest, batch_dir, output_dir)

    assert not output_dir.exists()


def test_batch_chunking_refuses_to_overwrite_existing_output(tmp_path):
    manifest, batch_dir = _write_inputs(tmp_path, [_page(1, "Some text.")])
    output_dir = tmp_path / "chunks"
    output_dir.mkdir()
    (output_dir / "keep.txt").write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="not empty"):
        prepare_chunks(manifest, batch_dir, output_dir)

    assert (output_dir / "keep.txt").read_text(encoding="utf-8") == "preserve"


def test_batch_chunking_rejects_verification_provenance_mismatch(tmp_path):
    page = _page(1, "Lesson 1\nSome text.")
    page["human_verification"] = {
        **VERIFICATION,
        "verified_at": "different timestamp",
    }
    manifest, batch_dir = _write_inputs(tmp_path, [page])

    with pytest.raises(ValueError, match="provenance mismatch"):
        prepare_chunks(manifest, batch_dir, tmp_path / "chunks")
