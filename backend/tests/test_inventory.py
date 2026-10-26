import csv
import io

import pymupdf
from app.ingestion.inventory import FIELDS, inventory_rows, write_inventory
from PIL import Image


def _create_pdf(path, page_texts: list[str], title: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        page.insert_text((72, 72), text)
    if title:
        document.set_metadata({"title": title})
    document.save(path)
    document.close()


def test_inventory_uses_metadata_and_marks_unconfirmed_fields_unknown(tmp_path) -> None:
    pdf = tmp_path / "Grade 02" / "Tamil" / "Textbook.pdf"
    _create_pdf(pdf, ["Tamil text content for a page"], "Metadata Title")

    [row], summary = inventory_rows(tmp_path)

    assert row["grade"] == "2"
    assert row["medium"] == "Tamil"
    assert row["textbook_title"] == "Metadata Title"
    assert row["verification_status"] == "unverified"
    assert row["edition_or_year"] == "unknown"
    assert row["subject"] == "unknown"
    assert row["page_count"] == "1"
    assert row["pdf_type"] == "text-based"
    assert summary["pdf_count"] == 1


def test_inventory_flags_non_unicode_text_layer_for_review(tmp_path) -> None:
    pdf = tmp_path / "Grade 03" / "Sinhala" / "legacy-font.pdf"
    _create_pdf(pdf, ["i.Ks;h - legacy font text"])

    [row], summary = inventory_rows(tmp_path)

    assert row["pdf_type"] == "text-based"
    assert row["extraction_status"] == "unicode_mapping_review"
    assert summary["suspected_text_encoding"][0]["medium"] == "Sinhala"


def test_inventory_csv_has_requested_columns_and_page_level_facts(tmp_path) -> None:
    pdf = tmp_path / "Grade 01" / "English" / "Book.pdf"
    _create_pdf(pdf, ["A readable page with enough text for testing."])
    output = tmp_path / "manifests" / "inventory.csv"

    summary = write_inventory(tmp_path, output)

    with output.open(encoding="utf-8-sig", newline="") as inventory_file:
        reader = csv.DictReader(inventory_file)
        rows = list(reader)

    assert reader.fieldnames == list(FIELDS)
    assert rows[0]["page_count"] == "1"
    assert rows[0]["textbook_id"].startswith("tb-")
    assert summary["pdf_count"] == 1


def test_inventory_identifies_scanned_mixed_unreadable_and_duplicates(tmp_path) -> None:
    text_pdf = tmp_path / "Grade 01" / "English" / "readable.pdf"
    _create_pdf(text_pdf, ["This page has more than twenty characters."])
    duplicate_pdf = tmp_path / "Grade 02" / "English" / "duplicate.pdf"
    duplicate_pdf.parent.mkdir(parents=True)
    duplicate_pdf.write_bytes(text_pdf.read_bytes())

    scanned_pdf = tmp_path / "Grade 03" / "Sinhala" / "scanned.pdf"
    scanned_pdf.parent.mkdir(parents=True)
    document = pymupdf.open()
    page = document.new_page()
    image_bytes = io.BytesIO()
    Image.new("RGB", (40, 40), color="white").save(image_bytes, format="PNG")
    page.insert_image(
        pymupdf.Rect(50, 50, 250, 250),
        stream=image_bytes.getvalue(),
    )
    document.save(scanned_pdf)
    document.close()

    mixed_pdf = tmp_path / "Grade 04" / "Tamil" / "mixed.pdf"
    mixed_pdf.parent.mkdir(parents=True)
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "This page has extractable text.")
    page = document.new_page()
    page.insert_image(
        pymupdf.Rect(50, 50, 250, 250),
        stream=image_bytes.getvalue(),
    )
    document.save(mixed_pdf)
    document.close()
    broken_pdf = tmp_path / "Grade 05" / "English" / "broken.pdf"
    broken_pdf.parent.mkdir(parents=True)
    broken_pdf.write_bytes(b"not a PDF")

    rows, summary = inventory_rows(tmp_path)
    by_name = {row["relative_file_path"].split("/")[-1]: row for row in rows}

    assert by_name["scanned.pdf"]["pdf_type"] == "scanned"
    assert by_name["scanned.pdf"]["extraction_status"] == "requires_ocr"
    assert by_name["mixed.pdf"]["pdf_type"] == "mixed"
    assert by_name["broken.pdf"]["extraction_status"] == "unreadable"
    assert len(summary["duplicate_files"]) == 1
    assert len(summary["unreadable_pdfs"]) == 1
    assert summary["pages_requiring_ocr"] == 2
