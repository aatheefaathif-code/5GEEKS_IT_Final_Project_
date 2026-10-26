import csv
import json

import pytest
from app.ingestion.inventory_audit import (
    audit_inventory,
    record_user_source_attestation,
    write_audit_report,
)


def _write_inventory(path, rows, fieldnames=None):
    fieldnames = fieldnames or list(rows[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_inventory_audit_reports_missing_metadata_and_existing_local_file(
    tmp_path,
):
    data_root = tmp_path / "data"
    source = data_root / "Grade 01" / "English" / "book.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source unchanged")
    manifest = data_root / "manifests" / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-one",
                "relative_file_path": "Grade 01/English/book.pdf",
                "grade": "1",
                "subject": "unknown",
                "medium": "English",
                "edition_or_year": "unknown",
                "page_count": "12",
                "verification_status": "unverified",
            }
        ],
    )
    original_bytes = manifest.read_bytes()

    report = audit_inventory(manifest, data_root)

    assert report["inventory_records"] == 1
    assert report["textbooks"][0]["local_file_exists"] is True
    assert "source_url_or_origin" in report["textbooks"][0]["missing_fields"]
    assert "subject" in report["textbooks"][0]["missing_fields"]
    assert report["field_coverage"]["download_status"]["missing_column"] is True
    assert report["field_coverage"]["edition_or_year"]["records_missing_value"] == 1
    assert manifest.read_bytes() == original_bytes
    assert source.read_bytes() == b"source unchanged"


def test_inventory_audit_marks_paths_outside_data_root(tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-outside",
                "relative_file_path": "..\\outside.pdf",
                "grade": "1",
                "subject": "Maths",
                "medium": "Tamil",
                "edition_or_year": "2025",
                "page_count": "10",
                "verification_status": "unverified",
            }
        ],
    )

    report = audit_inventory(manifest, data_root)

    assert report["textbooks"][0]["path_status"] == "outside_data_root"
    assert report["textbooks"][0]["local_file_exists"] is False


def test_write_audit_report_refuses_to_overwrite(tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-one",
                "relative_file_path": "missing.pdf",
                "grade": "1",
                "subject": "Maths",
                "medium": "Tamil",
                "edition_or_year": "2025",
                "page_count": "10",
                "verification_status": "unverified",
            }
        ],
    )
    output = tmp_path / "audit.json"
    output.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_audit_report(manifest, data_root, output)

    assert output.read_text(encoding="utf-8") == "preserve"


def test_write_audit_report_creates_json(tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-one",
                "relative_file_path": "missing.pdf",
                "grade": "1",
                "subject": "Maths",
                "medium": "Tamil",
                "edition_or_year": "2025",
                "page_count": "10",
                "verification_status": "unverified",
            }
        ],
    )
    output = tmp_path / "reports" / "audit.json"

    report = write_audit_report(manifest, data_root, output)

    assert json.loads(output.read_text(encoding="utf-8"))["inventory_records"] == 1
    assert report["inventory_records"] == 1


def test_records_user_attestation_without_inventing_url_or_edition(tmp_path):
    data_root = tmp_path / "data"
    source = data_root / "Grade 01" / "Tamil" / "book.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"unchanged")
    manifest = data_root / "manifests" / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-one",
                "relative_file_path": "Grade 01/Tamil/book.pdf",
                "grade": "1",
                "subject": "unknown",
                "medium": "Tamil",
                "textbook_title": "unknown",
                "edition_or_year": "unknown",
                "page_count": "10",
                "verification_status": "unverified",
            }
        ],
    )

    assert record_user_source_attestation(manifest, data_root) == 1
    with manifest.open(encoding="utf-8-sig", newline="") as input_file:
        row = next(csv.DictReader(input_file))
    report = audit_inventory(manifest, data_root)

    assert row["download_status"] == "user_downloaded"
    assert row["official_source_status"] == "user_attested_official"
    assert row["source_origin"].endswith("exact URL not recorded.")
    assert row["official_source_verified_by"] == "user (identity not recorded)"
    assert row["official_source_verified_at"]
    assert row["edition_or_year"] == "unknown"
    assert "source_url" not in row
    assert report["user_attested_official_books"] == 1
    assert (
        report["field_coverage"]["source_url_or_origin"]["records_missing_value"] == 0
    )
    assert source.read_bytes() == b"unchanged"

    attestation_time = row["official_source_verified_at"]
    assert record_user_source_attestation(manifest, data_root) == 1
    with manifest.open(encoding="utf-8-sig", newline="") as input_file:
        repeated_row = next(csv.DictReader(input_file))
    assert repeated_row["official_source_verified_at"] == attestation_time


def test_does_not_attest_inventory_when_local_source_is_missing(tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-missing",
                "relative_file_path": "missing.pdf",
                "grade": "1",
            }
        ],
    )
    original_bytes = manifest.read_bytes()

    with pytest.raises(ValueError, match="local source files are missing"):
        record_user_source_attestation(manifest, data_root)

    assert manifest.read_bytes() == original_bytes
