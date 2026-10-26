import csv
import json

import pytest
from app.ingestion.subject_candidates import (
    apply_evidence_backed_candidates,
    apply_user_confirmed_candidates,
    build_subject_candidate_report,
    write_subject_candidate_report,
)


def _write_inventory(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_candidates_use_explicit_filename_clue_not_folder_medium(tmp_path):
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-math",
                "relative_file_path": "Grade 01/English/Grade 1 Mathematics.pdf",
                "grade": "1",
                "medium": "English",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-unclear",
                "relative_file_path": "Grade 01/English/Activity Book.pdf",
                "grade": "1",
                "medium": "English",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-medium-only",
                "relative_file_path": (
                    "Grade 01/Sinhala/Language Sinhala Grade 1 Book.pdf"
                ),
                "grade": "1",
                "medium": "Sinhala",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-scholarship",
                "relative_file_path": (
                    "Grade 05/Tamil-medium/2025-Scholarship-Exam-Paper-Tamil-Medium.pdf"
                ),
                "grade": "5",
                "medium": "Tamil",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
        ],
    )
    original_bytes = manifest.read_bytes()

    report = build_subject_candidate_report(manifest)

    assert report["textbooks"][0]["subject_candidate"] == "Mathematics"
    assert report["textbooks"][0]["candidate_status"] == (
        "candidate_requires_human_confirmation"
    )
    assert report["textbooks"][1]["subject_candidate"] == "unknown"
    assert report["textbooks"][1]["candidate_status"] == "no_explicit_subject_clue"
    assert report["textbooks"][2]["subject_candidate"] == "unknown"
    assert (
        report["textbooks"][3]["subject_candidate"]
        == "Scholarship Examination (multi-subject)"
    )
    assert report["textbooks"][3]["candidate_status"] == (
        "candidate_requires_human_confirmation"
    )
    assert report["inventory_modified"] is False
    assert report["candidates_are_confirmed"] is False
    assert manifest.read_bytes() == original_bytes


def test_multiple_subject_clues_are_reported_as_ambiguous(tmp_path):
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-mixed",
                "relative_file_path": "Grade 02/Tamil/Science and Mathematics.pdf",
                "grade": "2",
                "medium": "Tamil",
                "subject": "unknown",
                "textbook_title": "unknown",
            }
        ],
    )

    report = build_subject_candidate_report(manifest)

    assert report["textbooks"][0]["subject_candidate"] == "ambiguous"
    assert {
        item["candidate"] for item in report["textbooks"][0]["candidate_evidence"]
    } == {
        "Mathematics",
        "Science",
    }


def test_candidates_recognize_explicit_sinhala_and_tamil_titles(tmp_path):
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-islam",
                "relative_file_path": (
                    "Grade 01/Sinhala/Language Sinhala Grade 1 Book "
                    "\u0d89\u0dc3\u0dca\u0dbd\u0dcf\u0db8\u0dca.pdf"
                ),
                "grade": "1",
                "medium": "Sinhala",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-math",
                "relative_file_path": (
                    "Grade 02/Tamil/Language Tamil Grade 2 Book "
                    "\u0b95\u0ba3\u0bbf\u0ba4\u0bae\u0bcd.pdf"
                ),
                "grade": "2",
                "medium": "Tamil",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-catholic",
                "relative_file_path": (
                    "Grade 03/Sinhala/Language Sinhala Grade 3 Book "
                    "\u0d9a\u0dad\u0ddd\u0dbd\u0dd2\u0d9a \u0db0\u0dbb\u0dca\u0db8\u0dba.pdf"
                ),
                "grade": "3",
                "medium": "Sinhala",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-buddhism",
                "relative_file_path": (
                    "Grade 03/Sinhala/Language Sinhala Grade 3 Book "
                    "\u0db6\u0dd4\u0daf\u0dca\u0db0 \u0db0\u0dbb\u0dca\u0db8\u0dba.pdf"
                ),
                "grade": "3",
                "medium": "Sinhala",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-hinduism",
                "relative_file_path": (
                    "Grade 03/Tamil/Language Tamil Grade 3 Book "
                    "\u0b9a\u0bc8\u0bb5 \u0ba8\u0bc6\u0bb1\u0bbf.pdf"
                ),
                "grade": "3",
                "medium": "Tamil",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-sinhala-language",
                "relative_file_path": (
                    "Grade 03/Sinhala/Language Sinhala Grade 3 Book "
                    "\u0dc3\u0dd2\u0d82\u0dc4\u0dbd "
                    "\u0d9a\u0dd2\u0dba\u0dc0\u0dd3\u0db8\u0dca "
                    "\u0db4\u0ddc\u0dad.pdf"
                ),
                "grade": "3",
                "medium": "Sinhala",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-christianity",
                "relative_file_path": (
                    "Grade 03/Tamil/Language Tamil Grade 3 Book "
                    "\u0b95\u0bbf\u0bb1\u0bbf\u0bb8\u0bcd\u0ba4\u0bb5\u0bae\u0bcd.pdf"
                ),
                "grade": "3",
                "medium": "Tamil",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-christianity-sinhala",
                "relative_file_path": (
                    "Grade 04/Sinhala/Language Sinhala Grade 4 Book "
                    "\u0d9a\u0dca\u200d\u0dbb\u0dd2\u0dc3\u0dca\u0dad\u0dd4.pdf"
                ),
                "grade": "4",
                "medium": "Sinhala",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-tamil-language",
                "relative_file_path": (
                    "Grade 04/Tamil/Language Tamil Grade 4 Book "
                    "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd.pdf"
                ),
                "grade": "4",
                "medium": "Tamil",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-scholarship",
                "relative_file_path": (
                    "Grade 05/tamil-medium-grade-5-scholarship-exam-past-paper/"
                    "2022-Marking-scheme-Past-Paper.pdf"
                ),
                "grade": "5",
                "medium": "Tamil",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
        ],
    )

    report = build_subject_candidate_report(manifest)
    candidates = {
        item["textbook_id"]: item["subject_candidate"]
        for item in report["textbooks"]
    }

    assert candidates == {
        "tb-islam": "Islam",
        "tb-math": "Mathematics",
        "tb-catholic": "Catholicism",
        "tb-buddhism": "Buddhism",
        "tb-hinduism": "Hinduism",
        "tb-sinhala-language": "Sinhala Language",
        "tb-christianity": "Christianity",
        "tb-christianity-sinhala": "Christianity",
        "tb-tamil-language": "Tamil Language",
        "tb-scholarship": "Scholarship Examination (multi-subject)",
    }


def test_applies_evidence_candidates_without_claiming_user_confirmation(tmp_path):
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-english",
                "relative_file_path": "Grade 01/English/ABOE Activity Book.pdf",
                "grade": "1",
                "medium": "English",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-unknown",
                "relative_file_path": "Grade 01/English/Activity Book.pdf",
                "grade": "1",
                "medium": "English",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
        ],
    )
    report = build_subject_candidate_report(manifest)

    result = apply_evidence_backed_candidates(manifest, report)

    with manifest.open(encoding="utf-8-sig", newline="") as input_file:
        rows = {row["textbook_id"]: row for row in csv.DictReader(input_file)}
    assert rows["tb-english"]["subject"] == "English Language"
    assert (
        rows["tb-english"]["subject_verification_status"]
        == "filename_evidence_assigned"
    )
    assert (
        rows["tb-english"]["subject_verified_by"]
        == "automated explicit-title classifier"
    )
    assert rows["tb-unknown"]["subject"] == "unknown"
    assert result["assignment_count"] == 1
    assert result["subjects"] == {"English Language": 1}


def test_write_subject_candidate_report_refuses_to_overwrite(tmp_path):
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-one",
                "relative_file_path": "Grade 01/English/Mathematics.pdf",
                "grade": "1",
                "medium": "English",
                "subject": "unknown",
                "textbook_title": "unknown",
            }
        ],
    )
    output = tmp_path / "subjects.json"
    output.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_subject_candidate_report(manifest, output)
    assert output.read_text(encoding="utf-8") == "preserve"


def test_write_subject_candidate_report_creates_json(tmp_path):
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-one",
                "relative_file_path": "Grade 01/English/Science.pdf",
                "grade": "1",
                "medium": "English",
                "subject": "unknown",
                "textbook_title": "unknown",
            }
        ],
    )
    output = tmp_path / "subjects.json"

    report = write_subject_candidate_report(manifest, output)

    assert json.loads(output.read_text(encoding="utf-8"))["inventory_records"] == 1
    assert report["textbooks"][0]["subject_candidate"] == "Science"


def test_applies_only_user_confirmed_single_candidates_with_provenance(tmp_path):
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-english",
                "relative_file_path": "Grade 03/English/English Pupils Book.pdf",
                "grade": "3",
                "medium": "English",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
            {
                "textbook_id": "tb-unknown",
                "relative_file_path": "Grade 01/English/Activity Book.pdf",
                "grade": "1",
                "medium": "English",
                "subject": "unknown",
                "textbook_title": "unknown",
            },
        ],
    )
    report = build_subject_candidate_report(manifest)

    result = apply_user_confirmed_candidates(manifest, report)

    with manifest.open(encoding="utf-8-sig", newline="") as input_file:
        rows = {row["textbook_id"]: row for row in csv.DictReader(input_file)}
    assert rows["tb-english"]["subject"] == "English Language"
    assert rows["tb-english"]["subject_verification_status"] == "user_confirmed"
    assert rows["tb-english"]["subject_verified_by"] == "user (identity not recorded)"
    assert rows["tb-unknown"]["subject"] == "unknown"
    assert result["confirmation_count"] == 1
    assert result["subjects"] == {"English Language": 1}


def test_rejects_stale_subject_candidate_report(tmp_path):
    manifest = tmp_path / "inventory.csv"
    _write_inventory(
        manifest,
        [
            {
                "textbook_id": "tb-english",
                "relative_file_path": "Grade 03/English/English Pupils Book.pdf",
                "grade": "3",
                "medium": "English",
                "subject": "unknown",
                "textbook_title": "unknown",
            }
        ],
    )
    report = build_subject_candidate_report(manifest)
    manifest.write_text(
        manifest.read_text(encoding="utf-8-sig") + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="stale"):
        apply_user_confirmed_candidates(manifest, report)
