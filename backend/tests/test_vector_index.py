import csv
import hashlib
import json

import pytest
import torch
from app.ingestion.vector_index import (
    COLLECTION_NAME,
    MODEL_NAME,
    _chromadb_metadata,
    _embedding_text,
    _mean_pool,
    _read_chunks,
)


def _write_inputs(tmp_path, page_status="verified"):
    inventory_path = tmp_path / "inventory.csv"
    row = {
        "textbook_id": "tb-test",
        "relative_file_path": "Grade 01/Tamil/book.pdf",
        "grade": "1",
        "subject": "Mathematics",
        "medium": "Tamil",
        "textbook_title": "unknown",
        "edition_or_year": "unknown",
        "page_count": "2",
    }
    with inventory_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    inventory_hash = hashlib.sha256(inventory_path.read_bytes()).hexdigest()

    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    chunk = {
        "textbook_id": "tb-test",
        "grade": "1",
        "subject": "Mathematics",
        "medium": "Tamil",
        "textbook_title": "unknown",
        "edition_or_year": "unknown",
        "chapter": "unknown",
        "lesson": "2",
        "topic": "unknown",
        "page_verification_status": page_status,
        "subject_verification_status": "filename_evidence_assigned",
        "source_official_status": "user_attested_official",
        "source_file": row["relative_file_path"],
        "pdf_page_number": 1,
        "chunk_id": "tb-test:1:1",
        "text": "\u0b95\u0ba3\u0b95\u0bcd\u0b95\u0bc1 \u0baa\u0bc6\u0baf\u0bb0\u0bcd",
    }
    (chunks_dir / "tb-test.chunks.jsonl").write_text(
        json.dumps(chunk, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report = {
        "pipeline": "verified_ocr_to_cleaned_lesson_aware_chunks",
        "verification_method": "user_confirmed_source_pdf_comparison",
        "inventory_sha256": inventory_hash,
        "total_chunks": 1,
        "books_selected": 1,
    }
    (chunks_dir / "chunking_report.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )
    return inventory_path, chunks_dir, chunk


def test_reads_only_verified_chunks_with_current_inventory_provenance(tmp_path):
    inventory_path, chunks_dir, chunk = _write_inputs(tmp_path)

    chunks, report, inventory = _read_chunks(chunks_dir, inventory_path)

    assert chunks == [chunk]
    assert report["total_chunks"] == 1
    assert inventory["tb-test"]["subject"] == "Mathematics"


def test_refuses_unverified_chunk(tmp_path):
    inventory_path, chunks_dir, _ = _write_inputs(
        tmp_path,
        page_status="unverified",
    )

    with pytest.raises(ValueError, match="Unverified page"):
        _read_chunks(chunks_dir, inventory_path)


def test_refuses_chunks_from_stale_inventory(tmp_path):
    inventory_path, chunks_dir, _ = _write_inputs(tmp_path)
    inventory_path.write_text(
        inventory_path.read_text(encoding="utf-8-sig") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Inventory differs"):
        _read_chunks(chunks_dir, inventory_path)


def test_e5_input_uses_passage_prefix_and_available_context():
    chunk = {
        "grade": "5",
        "subject": "English Language",
        "medium": "English",
        "chapter": "unknown",
        "lesson": "3",
        "topic": "unknown",
        "text": "  A pupil reads a short story.  ",
    }

    assert _embedding_text(chunk) == (
        "passage: Grade 5 | English Language | English | Lesson 3\n"
        "A pupil reads a short story."
    )


def test_chroma_metadata_preserves_filters_and_page_reference():
    chunk = {
        "textbook_id": "tb-test",
        "grade": "1",
        "subject": "Mathematics",
        "medium": "Tamil",
        "textbook_title": "unknown",
        "edition_or_year": "unknown",
        "chapter": "unknown",
        "lesson": "unknown",
        "topic": "unknown",
        "page_verification_status": "verified",
        "subject_verification_status": "filename_evidence_assigned",
        "source_official_status": "user_attested_official",
        "source_file": "Grade 01/Tamil/book.pdf",
        "pdf_page_number": 7,
        "chunk_id": "tb-test:7:1",
    }

    metadata = _chromadb_metadata(chunk)

    assert metadata["grade"] == "1"
    assert metadata["subject"] == "Mathematics"
    assert metadata["medium"] == "Tamil"
    assert metadata["pdf_page_number"] == 7
    assert metadata["chunk_id"] == "tb-test:7:1"
    assert MODEL_NAME == "intfloat/multilingual-e5-large"
    assert COLLECTION_NAME == "textbook_chunks"


def test_mean_pool_ignores_padding_and_normalizes_embeddings():
    hidden = torch.tensor([[[3.0, 0.0], [0.0, 4.0], [100.0, 100.0]]])
    mask = torch.tensor([[1, 1, 0]])

    embedding = _mean_pool(hidden, mask)

    assert embedding.shape == (1, 2)
    assert torch.allclose(
        embedding,
        torch.tensor([[0.6, 0.8]]),
    )
