import json

import pymupdf
import pytest
from app.ingestion.chunking import chunk_pages
from app.ingestion.cleaning import clean_repeated_headers_footers
from app.ingestion.export import export_chunks_jsonl
from app.ingestion.extraction import extract_pdf_pages
from app.ingestion.metadata import validate_chunk_metadata
from app.ingestion.pilot import _unicode_summary


def _create_text_pdf(path) -> None:
    document = pymupdf.open()
    for text in (
        "Syllabus Assistant\nLesson 1\nTamil: தமிழ்.",
        "Syllabus Assistant\nLesson 1\nSinhala: සිංහල.",
    ):
        page = document.new_page()
        page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_extraction_preserves_one_based_pdf_page_numbers_and_unicode(tmp_path) -> None:
    pdf = tmp_path / "pilot.pdf"
    _create_text_pdf(pdf)

    pages = extract_pdf_pages(pdf, "Grade 01/Tamil/pilot.pdf", "tb-test", "Tamil")

    assert [page["pdf_page_number"] for page in pages] == [1, 2]
    assert pages[0]["extraction_status"] == "success"
    assert "Lesson 1" in pages[0]["text"]
    assert "Lesson 1" in pages[1]["text"]


def test_force_ocr_flags_missing_engine_without_discarding_text_layer(
    tmp_path, monkeypatch
) -> None:
    pdf = tmp_path / "pilot.pdf"
    _create_text_pdf(pdf)
    monkeypatch.setattr("app.ingestion.extraction.shutil.which", lambda _: None)

    pages = extract_pdf_pages(
        pdf,
        "Grade 01/Tamil/pilot.pdf",
        "tb-test",
        "Tamil",
        use_ocr=True,
        ocr_all_pages=True,
    )

    assert pages[0]["text"]
    assert pages[0]["extraction_method"] == "text_layer"
    assert pages[0]["extraction_status"] == "unicode_mapping_review_ocr_unavailable"


def test_ocr_text_replaces_existing_text_layer_without_duplicate_text(
    tmp_path, monkeypatch
) -> None:
    pdf = tmp_path / "pilot.pdf"
    _create_text_pdf(pdf)
    monkeypatch.setattr("app.ingestion.extraction.shutil.which", lambda _: "tesseract")
    monkeypatch.setattr(
        "pytesseract.image_to_data",
        lambda *_args, **_kwargs: {
            "text": ["OCR", "recovered", "සිංහල"],
            "conf": ["90", "80", "70"],
            "block_num": ["1", "1", "1"],
            "par_num": ["1", "1", "1"],
            "line_num": ["1", "1", "1"],
        },
    )

    [page, _] = extract_pdf_pages(
        pdf,
        "Grade 01/Sinhala/pilot.pdf",
        "tb-test",
        "Sinhala",
        use_ocr=True,
        ocr_all_pages=True,
    )

    assert page["text"] == "OCR recovered සිංහල"
    assert page["extraction_method"] == "tesseract_ocr"
    assert page["text"].count("Lesson 1") == 0
    assert page["ocr_mean_confidence"] == 80
    assert page["embedded_text"]
    assert page["ocr_attempted"]
    assert page["ocr_trigger"] == "all_pages"


def test_ocr_retries_text_layer_missing_expected_script(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "pilot.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "English-only text in Tamil book")
    document.save(pdf)
    document.close()
    monkeypatch.setattr("app.ingestion.extraction.shutil.which", lambda _: "tesseract")
    monkeypatch.setattr(
        "pytesseract.image_to_data",
        lambda *_args, **_kwargs: {
            "text": ["தமிழ்", "text"],
            "conf": ["90", "80"],
            "block_num": ["1", "1"],
            "par_num": ["1", "1"],
            "line_num": ["1", "1"],
        },
    )

    [page] = extract_pdf_pages(
        pdf,
        "Grade 01/Tamil/pilot.pdf",
        "tb-test",
        "Tamil",
        use_ocr=True,
        ocr_on_missing_script=True,
    )

    assert page["text"] == "தமிழ் text"
    assert page["extraction_method"] == "tesseract_ocr"
    assert page["ocr_trigger"] == "missing_expected_script"
    assert page["ocr_attempted"]
    assert "English-only text" in page["embedded_text"]


def test_extraction_does_not_set_ocr_trigger_when_ocr_is_disabled(tmp_path) -> None:
    pdf = tmp_path / "pilot.pdf"
    _create_text_pdf(pdf)

    [page, _] = extract_pdf_pages(
        pdf,
        "Grade 01/Tamil/pilot.pdf",
        "tb-test",
        "Tamil",
    )

    assert page["ocr_trigger"] is None
    assert not page["ocr_attempted"]


def test_ocr_failure_retains_embedded_text_and_reports_failure(
    tmp_path, monkeypatch
) -> None:
    pdf = tmp_path / "pilot.pdf"
    _create_text_pdf(pdf)
    monkeypatch.setattr("app.ingestion.extraction.shutil.which", lambda _: "tesseract")

    def fail_ocr(*_args, **_kwargs):
        raise RuntimeError("simulated OCR failure")

    monkeypatch.setattr("pytesseract.image_to_data", fail_ocr)
    pages = extract_pdf_pages(
        pdf,
        "Grade 01/Sinhala/pilot.pdf",
        "tb-test",
        "Sinhala",
        use_ocr=True,
        ocr_all_pages=True,
    )

    assert "Lesson 1" in pages[0]["text"]
    assert pages[0]["extraction_method"] == "text_layer"
    assert pages[0]["extraction_status"] == "ocr_failed_text_layer_retained"


def test_empty_and_unreadable_pdf_pages_are_reported(tmp_path) -> None:
    empty_pdf = tmp_path / "empty.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(empty_pdf)
    document.close()

    [page] = extract_pdf_pages(
        empty_pdf, "Grade 01/English/empty.pdf", "tb-empty", "English"
    )
    assert page["pdf_page_number"] == 1
    assert page["text"] == ""
    assert page["extraction_status"] == "requires_ocr"

    broken_pdf = tmp_path / "broken.pdf"
    broken_pdf.write_bytes(b"not a PDF")
    with pytest.raises(pymupdf.FileDataError):
        extract_pdf_pages(
            broken_pdf, "Grade 01/English/broken.pdf", "tb-broken", "English"
        )


def test_cleaning_removes_repeated_edge_headers_and_footers() -> None:
    pages = [
        {
            "pdf_page_number": number,
            "text": f"Repeated title\nLesson text {number}\nRepeated footer",
        }
        for number in (1, 2, 3)
    ]

    cleaned = clean_repeated_headers_footers(pages)

    assert [page["pdf_page_number"] for page in cleaned] == [1, 2, 3]
    assert all("Repeated title" not in page["text"] for page in cleaned)
    assert all("Repeated footer" not in page["text"] for page in cleaned)
    assert "Lesson text 2" in cleaned[1]["text"]


def test_chunking_tracks_detected_lesson_and_original_pdf_page() -> None:
    page = {
        "source_file": "Grade 01/English/book.pdf",
        "pdf_page_number": 14,
        "text": "Lesson 2\nA short lesson paragraph.",
    }
    metadata = {
        "textbook_id": "tb-123",
        "grade": "1",
        "subject": "unknown",
        "medium": "English",
    }

    [chunk] = chunk_pages([page], metadata)

    assert chunk["pdf_page_number"] == 14
    assert chunk["source_file"] == page["source_file"]
    assert chunk["lesson"] == "2"
    assert chunk["chapter"] == "unknown"
    assert validate_chunk_metadata(chunk) == []


def test_chunking_keeps_multiple_lesson_headings_on_their_own_chunks() -> None:
    page = {
        "source_file": "Grade 01/English/book.pdf",
        "pdf_page_number": 1,
        "text": ("Lesson 1\nFirst lesson content.\n\nLesson 2\nSecond lesson content."),
    }
    metadata = {
        "textbook_id": "tb-123",
        "grade": "1",
        "subject": "unknown",
        "medium": "English",
    }

    chunks = chunk_pages([page], metadata, max_characters=100)

    assert [chunk["lesson"] for chunk in chunks] == ["1", "2"]
    assert "First lesson content." in chunks[0]["text"]
    assert "Second lesson content." in chunks[1]["text"]


def test_chunking_does_not_treat_lesson_references_as_headings() -> None:
    page = {
        "source_file": "Grade 01/English/book.pdf",
        "pdf_page_number": 1,
        "text": "Lesson 4 in the textbook. Complete the activity.",
    }
    metadata = {
        "textbook_id": "tb-123",
        "grade": "1",
        "subject": "unknown",
        "medium": "English",
    }

    [chunk] = chunk_pages([page], metadata)

    assert chunk["lesson"] == "unknown"


@pytest.mark.parametrize(
    ("heading", "expected_field", "expected_value"),
    [
        ("පාඩම 2", "lesson", "2"),
        ("பாடம் 3", "lesson", "3"),
        ("පරිච්ඡේදය 1", "chapter", "1"),
        ("அத்தியாயம் 4", "chapter", "4"),
    ],
)
def test_chunking_detects_numbered_sinhala_and_tamil_headings(
    heading, expected_field, expected_value
) -> None:
    page = {
        "source_file": "Grade 01/Tamil/book.pdf",
        "pdf_page_number": 1,
        "text": f"{heading}\nLesson content.",
    }
    metadata = {
        "textbook_id": "tb-123",
        "grade": "1",
        "subject": "unknown",
        "medium": "Tamil",
    }

    [chunk] = chunk_pages([page], metadata)

    assert chunk[expected_field] == expected_value


@pytest.mark.parametrize(
    "line",
    [
        "පාඩම කියවන්න. සුදුසු වචන තෝරා හිස්තැන් පුරවන්න.",
        "பாடம் படித்து விடையளிக்கவும்.",
        "පරිච්ඡේදය තුළින් සාමුහිකත්වය වර්ධනය කිරීම.",
    ],
)
def test_chunking_ignores_unnumbered_sinhala_and_tamil_instruction_lines(
    line,
) -> None:
    page = {
        "source_file": "Grade 01/Sinhala/book.pdf",
        "pdf_page_number": 1,
        "text": f"{line}\nInstruction content.",
    }
    metadata = {
        "textbook_id": "tb-123",
        "grade": "1",
        "subject": "unknown",
        "medium": "Sinhala",
    }

    [chunk] = chunk_pages([page], metadata)

    assert chunk["lesson"] == "unknown"
    assert chunk["chapter"] == "unknown"


def test_jsonl_export_preserves_unicode_and_rejects_invalid_metadata(tmp_path) -> None:
    chunk = {
        "chunk_id": "tb-123:1:1",
        "textbook_id": "tb-123",
        "source_file": "Grade 01/Tamil/book.pdf",
        "pdf_page_number": 1,
        "grade": "1",
        "subject": "unknown",
        "medium": "Tamil",
        "chapter": "unknown",
        "lesson": "unknown",
        "text": "தமிழ் தமிழ்",
    }
    output = tmp_path / "chunks.jsonl"

    assert export_chunks_jsonl([chunk], output) == 1
    [record] = [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert record["text"] == "தமிழ் தமிழ்"

    invalid_output = tmp_path / "invalid" / "chunks.jsonl"
    with pytest.raises(ValueError, match="Refusing to export invalid chunks"):
        export_chunks_jsonl([{"text": "missing provenance"}], invalid_output)
    assert not invalid_output.exists()


def test_chunk_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_characters must be positive"):
        chunk_pages([], {}, max_characters=0)


def test_unicode_quality_check_flags_missing_script_and_counts_native_script() -> None:
    tamil = _unicode_summary("தமிழ்", "Tamil")
    sinhala = _unicode_summary("සිංහල", "Sinhala")
    corrupted = _unicode_summary("i.Ks;h", "Sinhala")
    scanned = _unicode_summary("", "Tamil")

    assert tamil["expected_script_characters"] > 0
    assert sinhala["expected_script_characters"] > 0
    assert corrupted["unicode_check"].startswith("expected script absent")
    assert scanned["unicode_check"].startswith("no extracted text")
