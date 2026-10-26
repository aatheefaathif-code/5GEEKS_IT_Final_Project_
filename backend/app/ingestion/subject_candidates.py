import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

SCHOLARSHIP_EXAM_PATTERN = re.compile(
    r"\b(?:scholarship.{0,30}(?:exam|paper)|(?:exam|paper).{0,30}scholarship)\b",
    re.IGNORECASE,
)
SUBJECT_PATTERNS = (
    (
        "Mathematics",
        re.compile(
            r"\b(?:mathematics|maths?)\b|\u0b95\u0ba3\u0bbf\u0ba4\u0bae|"
            r"\u0d9c\u0dab\u0dd2\u0dad\u0dba",
            re.IGNORECASE,
        ),
    ),
    ("Science", re.compile(r"\bscience\b", re.IGNORECASE)),
    (
        "Environmental Studies",
        re.compile(r"\b(?:environmental studies|our environment)\b", re.IGNORECASE),
    ),
    (
        "Buddhism",
        re.compile(
            r"\b(?:buddhism|buddhist|dhamma)\b|"
            r"\u0db6\u0dd4\u0daf\u0dca\u0db0 \u0db0\u0dbb\u0dca\u0db8\u0dba",
            re.IGNORECASE,
        ),
    ),
    (
        "Catholicism",
        re.compile(
            r"\bcatholic\b|\u0b95\u0ba4\u0bcd\u0ba4\u0bcb\u0bb2\u0bbf\u0b95|"
            r"\u0d9a\u0dad\u0ddd\u0dbd\u0dd2\u0d9a",
            re.IGNORECASE,
        ),
    ),
    (
        "Christianity",
        re.compile(
            r"\bchristian(?:ity)?\b|\u0b95\u0bbf\u0bb1\u0bbf\u0bb8\u0bcd\u0ba4\u0bb5|"
            r"\u0d9a\u0dca\u0dbb\u0dd2\u0dc3\u0dca\u0dad\u0dd2\u0dba\u0dcf\u0db1\u0dd2|"
            r"\u0d9a\u0dca\u0dbb\u0dd2\u0dc3\u0dca\u0dad\u0dd4",
            re.IGNORECASE,
        ),
    ),
    (
        "Islam",
        re.compile(
            r"\b(?:islam|islamic|muslim)\b|"
            r"\u0b87\u0bb8\u0bcd\u0bb2\u0bbe\u0bae|"
            r"\u0d89\u0dc3\u0dca\u0dbd\u0dcf\u0db8",
            re.IGNORECASE,
        ),
    ),
    (
        "Hinduism",
        re.compile(
            r"\b(?:hinduism|hindu)\b|\u0b9a\u0bc8\u0bb5 \u0ba8\u0bc6\u0bb1\u0bbf",
            re.IGNORECASE,
        ),
    ),
    (
        "English Language",
        re.compile(
            r"\b(?:english language|oral english|english|aboe)\b", re.IGNORECASE
        ),
    ),
    (
        "Sinhala Language",
        re.compile(
            r"\b(?:sinhala language|sinhala)\b|"
            r"\u0dc3\u0dd2\u0d82\u0dc4\u0dbd \u0d9a\u0dd2\u0dba\u0dc0\u0dd3\u0db8|"
            r"\u0dc3\u0dd2\u0d82\u0dc4\u0dbd \u0dc0\u0dd0\u0da9",
            re.IGNORECASE,
        ),
    ),
    (
        "Tamil Language",
        re.compile(
            r"\b(?:tamil language|tamil)\b|"
            r"\u0ba4\u0bae\u0bbf\u0bb4\u0bcd"
            r"(?:\s+(?:\u0b9a\u0bc6\u0baf\u0bb2|\u0bb5\u0bbe\u0b9a\u0bbf))?",
            re.IGNORECASE,
        ),
    ),
    (
        "Health and Physical Education",
        re.compile(r"\b(?:health|physical education)\b", re.IGNORECASE),
    ),
    (
        "Aesthetic Studies",
        re.compile(r"\b(?:aesthetic studies|art|music|dance|drama)\b", re.IGNORECASE),
    ),
    ("History", re.compile(r"\bhistory\b", re.IGNORECASE)),
    ("Geography", re.compile(r"\bgeography\b", re.IGNORECASE)),
    (
        "Information and Communication Technology",
        re.compile(r"\b(?:ict|computer studies)\b", re.IGNORECASE),
    ),
)


def _read_inventory(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as inventory_file:
        reader = csv.DictReader(inventory_file)
        if reader.fieldnames is None:
            raise ValueError(f"Inventory has no header row: {path}")
        rows = [
            {key: value or "" for key, value in row.items() if key is not None}
            for row in reader
        ]
        return rows, list(reader.fieldnames)


def _subject_candidates(row: dict[str, str]) -> dict[str, Any]:
    filename = Path(row.get("relative_file_path", "")).stem
    filename_evidence = re.sub(
        r"\bLanguage\s+(?:English|Sinhala|Tamil)\s+Grade\s+0?[1-5]\s+Book\b",
        " ",
        filename,
        flags=re.IGNORECASE,
    )
    filename_evidence = re.sub(
        r"\b(?:English|Sinhala|Tamil)[\s_-]+medium\b",
        " ",
        filename_evidence,
        flags=re.IGNORECASE,
    )
    filename_evidence = _normalize_subject_evidence(filename_evidence)
    title = row.get("textbook_title", "").strip()
    evidence_sources = [("filename", filename_evidence)]
    if title and title.casefold() != "unknown":
        evidence_sources.append(
            ("pdf_metadata_title", _normalize_subject_evidence(title))
        )

    matches: dict[str, list[dict[str, str]]] = defaultdict(list)
    for source_name, value in evidence_sources:
        for candidate, pattern in SUBJECT_PATTERNS:
            for match in pattern.finditer(value):
                matches[candidate].append(
                    {"source": source_name, "matched_text": match.group(0)}
                )

    relative_path = _normalize_subject_evidence(
        row.get("relative_file_path", "")
    )
    for match in SCHOLARSHIP_EXAM_PATTERN.finditer(relative_path):
        matches["Scholarship Examination (multi-subject)"].append(
            {"source": "relative_file_path", "matched_text": match.group(0)}
        )

    candidates = sorted(matches)
    if len(candidates) == 1:
        subject_candidate = candidates[0]
        status = "candidate_requires_human_confirmation"
    elif candidates:
        subject_candidate = "ambiguous"
        status = "multiple_candidates_require_human_confirmation"
    else:
        subject_candidate = "unknown"
        status = "no_explicit_subject_clue"

    return {
        "subject_candidate": subject_candidate,
        "candidate_status": status,
        "candidate_evidence": [
            {"candidate": candidate, **evidence}
            for candidate, evidence_items in sorted(matches.items())
            for evidence in evidence_items
        ],
        "subject": row.get("subject", "unknown") or "unknown",
    }


def _normalize_subject_evidence(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\u200c", "").replace(
        "\u200d", ""
    )


def build_subject_candidate_report(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Inventory manifest not found: {manifest_path}")
    rows, columns = _read_inventory(manifest_path)
    if "relative_file_path" not in columns:
        raise ValueError("Inventory is missing the relative_file_path column.")

    textbooks: list[dict[str, Any]] = []
    subject_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    by_grade: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        result = _subject_candidates(row)
        candidate = result["subject_candidate"]
        status = result["candidate_status"]
        subject_counts[candidate] += 1
        status_counts[status] += 1
        by_grade[row.get("grade", "unknown") or "unknown"][candidate] += 1
        textbooks.append(
            {
                "textbook_id": row.get("textbook_id", "unknown"),
                "relative_file_path": row["relative_file_path"],
                "grade": row.get("grade", "unknown") or "unknown",
                "medium": row.get("medium", "unknown") or "unknown",
                "textbook_title": row.get("textbook_title", "unknown") or "unknown",
                "current_subject": row.get("subject", "unknown") or "unknown",
                **result,
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "report_type": "filename_and_pdf_metadata_subject_candidates",
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "inventory_records": len(rows),
        "inventory_modified": False,
        "candidate_method": (
            "Conservative English, Sinhala, and Tamil subject-term matching against "
            "the PDF filename and non-unknown PDF metadata title. The relative path "
            "is additionally checked only for explicit scholarship-exam wording. "
            "Grade and medium alone are not subject evidence. Matches are suggestions."
        ),
        "candidates_are_confirmed": False,
        "subject_candidate_counts": dict(sorted(subject_counts.items())),
        "candidate_status_counts": dict(sorted(status_counts.items())),
        "by_grade": {
            grade: dict(sorted(counts.items()))
            for grade, counts in sorted(by_grade.items())
        },
        "textbooks": textbooks,
    }


def write_subject_candidate_report(
    manifest_path: Path, output_path: Path, overwrite: bool = False
) -> dict[str, Any]:
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing subject candidate report: {output_path}"
        )
    report = build_subject_candidate_report(manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(output_path, report)
    return report


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def apply_user_confirmed_candidates(
    manifest_path: Path,
    candidate_report: dict[str, Any],
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    rows, columns = _read_inventory(manifest_path)
    current_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if candidate_report.get("manifest_sha256") != current_hash:
        raise ValueError(
            "Subject candidate report is stale; regenerate it from the current "
            "inventory before applying confirmations."
        )

    rows_by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        textbook_id = row.get("textbook_id", "").strip()
        if not textbook_id or textbook_id in rows_by_id:
            raise ValueError("Inventory has a missing or duplicate textbook ID.")
        rows_by_id[textbook_id] = row

    approved: list[dict[str, Any]] = []
    for item in candidate_report.get("textbooks", []):
        if item.get("candidate_status") == "no_explicit_subject_clue":
            continue
        if item.get("candidate_status") != "candidate_requires_human_confirmation":
            raise ValueError(
                f"Cannot apply ambiguous candidate for {item.get('textbook_id')}."
            )
        candidate = item.get("subject_candidate", "").strip()
        if not candidate or candidate in {"unknown", "ambiguous"}:
            raise ValueError(
                f"Invalid subject candidate for {item.get('textbook_id')}."
            )
        row = rows_by_id.get(item.get("textbook_id", ""))
        if row is None:
            raise ValueError(
                f"Candidate references unknown textbook ID: {item.get('textbook_id')}."
            )
        if row.get("relative_file_path") != item.get("relative_file_path"):
            raise ValueError(
                f"Candidate source path changed for {item.get('textbook_id')}."
            )
        current_subject = row.get("subject", "").strip()
        if current_subject.casefold() not in {"", "unknown", candidate.casefold()}:
            raise ValueError(
                f"Refusing to replace existing subject for {item.get('textbook_id')}."
            )
        if item.get("candidate_evidence") is None:
            raise ValueError(
                f"Candidate has no evidence for {item.get('textbook_id')}."
            )
        approved.append(item)

    if not approved:
        raise ValueError("No unambiguous subject candidates were approved.")

    verified_at = datetime.now(UTC).isoformat()
    provenance_fields = (
        "subject_verification_status",
        "subject_verified_by",
        "subject_verified_at",
        "subject_verification_basis",
    )
    for field in provenance_fields:
        if field not in columns:
            columns.append(field)

    confirmation_rows: list[dict[str, Any]] = []
    for item in approved:
        row = rows_by_id[item["textbook_id"]]
        subject = item["subject_candidate"]
        row["subject"] = subject
        row["subject_verification_status"] = "user_confirmed"
        row["subject_verified_by"] = "user (identity not recorded)"
        row["subject_verified_at"] = verified_at
        row["subject_verification_basis"] = (
            "User reviewed and accepted the subject candidate and its recorded "
            "filename/PDF-title evidence."
        )
        confirmation_rows.append(
            {
                "textbook_id": item["textbook_id"],
                "relative_file_path": item["relative_file_path"],
                "grade": item.get("grade", "unknown"),
                "medium": item.get("medium", "unknown"),
                "subject": subject,
                "evidence": item["candidate_evidence"],
                "confirmation_status": "user_confirmed",
                "verified_by": "user (identity not recorded)",
                "verified_at": verified_at,
            }
        )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=manifest_path.parent,
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            writer = csv.DictWriter(temporary_file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        temporary_path.replace(manifest_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    manifest_after_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return {
        "confirmed_at": verified_at,
        "confirmed_by": "user (identity not recorded)",
        "confirmation_method": "user_reviewed_subject_candidates",
        "candidate_report_manifest_sha256": current_hash,
        "manifest_sha256_after_confirmation": manifest_after_hash,
        "confirmation_count": len(confirmation_rows),
        "subjects": dict(
            sorted(Counter(row["subject"] for row in confirmation_rows).items())
        ),
        "confirmations": confirmation_rows,
    }


def apply_evidence_backed_candidates(
    manifest_path: Path,
    candidate_report: dict[str, Any],
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    rows, columns = _read_inventory(manifest_path)
    current_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if candidate_report.get("manifest_sha256") != current_hash:
        raise ValueError(
            "Subject candidate report is stale; regenerate it from the current "
            "inventory before applying evidence-backed assignments."
        )

    rows_by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        textbook_id = row.get("textbook_id", "").strip()
        if not textbook_id or textbook_id in rows_by_id:
            raise ValueError("Inventory has a missing or duplicate textbook ID.")
        rows_by_id[textbook_id] = row

    assignments: list[dict[str, Any]] = []
    for item in candidate_report.get("textbooks", []):
        row = rows_by_id.get(item.get("textbook_id", ""))
        if row is None:
            raise ValueError(
                f"Candidate references unknown textbook ID: {item.get('textbook_id')}."
            )
        if row.get("relative_file_path") != item.get("relative_file_path"):
            raise ValueError(
                f"Candidate source path changed for {item.get('textbook_id')}."
            )
        current_subject = row.get("subject", "").strip()
        if current_subject.casefold() not in {"", "unknown"}:
            continue
        if item.get("candidate_status") == "no_explicit_subject_clue":
            continue
        if item.get("candidate_status") != "candidate_requires_human_confirmation":
            raise ValueError(
                f"Cannot apply ambiguous candidate for {item.get('textbook_id')}."
            )
        candidate = item.get("subject_candidate", "").strip()
        evidence = item.get("candidate_evidence")
        if not candidate or candidate in {"unknown", "ambiguous"} or not evidence:
            raise ValueError(
                f"Invalid or unsupported subject candidate for "
                f"{item.get('textbook_id')}."
            )
        if any(
            item_evidence.get("source")
            not in {"filename", "pdf_metadata_title", "relative_file_path"}
            for item_evidence in evidence
        ):
            raise ValueError(
                f"Unsupported evidence source for {item.get('textbook_id')}."
            )
        assignments.append(item)

    if not assignments:
        raise ValueError("No evidence-backed subject assignments are available.")

    assigned_at = datetime.now(UTC).isoformat()
    provenance_fields = (
        "subject_verification_status",
        "subject_verified_by",
        "subject_verified_at",
        "subject_verification_basis",
    )
    for field in provenance_fields:
        if field not in columns:
            columns.append(field)

    assignment_records: list[dict[str, Any]] = []
    for item in assignments:
        row = rows_by_id[item["textbook_id"]]
        subject = item["subject_candidate"]
        row["subject"] = subject
        row["subject_verification_status"] = "filename_evidence_assigned"
        row["subject_verified_by"] = "automated explicit-title classifier"
        row["subject_verified_at"] = assigned_at
        row["subject_verification_basis"] = (
            "Assigned from a unique explicit subject term in the PDF filename, "
            "PDF metadata title, or scholarship-exam relative path. This is not "
            "independent publisher verification or individual human confirmation."
        )
        assignment_records.append(
            {
                "textbook_id": item["textbook_id"],
                "relative_file_path": item["relative_file_path"],
                "grade": item.get("grade", "unknown"),
                "medium": item.get("medium", "unknown"),
                "subject": subject,
                "evidence": item["candidate_evidence"],
                "assignment_status": "filename_evidence_assigned",
                "assigned_at": assigned_at,
            }
        )

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=manifest_path.parent,
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            writer = csv.DictWriter(temporary_file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        temporary_path.replace(manifest_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return {
        "assigned_at": assigned_at,
        "assignment_method": "unique_explicit_subject_title_evidence",
        "candidate_report_manifest_sha256": current_hash,
        "manifest_sha256_after_assignment": hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest(),
        "assignment_count": len(assignment_records),
        "subjects": dict(
            sorted(Counter(item["subject"] for item in assignment_records).items())
        ),
        "assignments": assignment_records,
    }


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description=(
            "Suggest textbook subjects from explicit filename/PDF-title clues "
            "without modifying the inventory."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=project_root / "data" / "manifests" / "textbook_inventory.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root
        / "data"
        / "manifests"
        / "textbook_subject_candidates.json",
    )
    parser.add_argument(
        "--replace-report",
        action="store_true",
        help="Replace the existing subject candidate report.",
    )
    parser.add_argument(
        "--apply-user-confirmed-candidates",
        action="store_true",
        help=(
            "Apply every single, unambiguous candidate from the current manifest "
            "after the user has confirmed them."
        ),
    )
    parser.add_argument(
        "--apply-evidence-backed-candidates",
        action="store_true",
        help=(
            "Apply unique explicit-title candidates without marking them "
            "user-confirmed."
        ),
    )
    parser.add_argument(
        "--confirmation-report",
        type=Path,
        default=project_root
        / "data"
        / "manifests"
        / "textbook_subject_confirmation.json",
    )
    parser.add_argument(
        "--evidence-assignment-report",
        type=Path,
        default=project_root
        / "data"
        / "manifests"
        / "textbook_subject_evidence_assignment.json",
    )
    args = parser.parse_args()
    if args.apply_user_confirmed_candidates and args.apply_evidence_backed_candidates:
        parser.error("Choose only one subject assignment mode.")
    if args.apply_user_confirmed_candidates:
        if args.confirmation_report.exists():
            raise FileExistsError(
                "Refusing to overwrite subject confirmation report: "
                f"{args.confirmation_report}"
            )
        candidate_report = build_subject_candidate_report(args.manifest)
        if args.output.exists() and not args.replace_report:
            raise FileExistsError(
                f"Refusing to overwrite existing subject candidate report: {args.output}. "
                "Pass --replace-report after reviewing the refreshed candidates."
            )
        report = apply_user_confirmed_candidates(args.manifest, candidate_report)
        _atomic_json(args.confirmation_report, report)
        candidate_report["candidates_are_confirmed"] = True
        candidate_report["candidate_generation_modified_inventory"] = False
        candidate_report["inventory_modified"] = True
        candidate_report["manifest_sha256_after_confirmation"] = report[
            "manifest_sha256_after_confirmation"
        ]
        candidate_report["confirmation_status"] = (
            "unambiguous candidates accepted by the user and applied to the inventory"
        )
        candidate_report["confirmation_report"] = str(
            args.confirmation_report.resolve()
        )
        _atomic_json(args.output, candidate_report)
    elif args.apply_evidence_backed_candidates:
        if args.evidence_assignment_report.exists():
            raise FileExistsError(
                "Refusing to overwrite subject evidence assignment report: "
                f"{args.evidence_assignment_report}"
            )
        candidate_report = build_subject_candidate_report(args.manifest)
        if args.output.exists() and not args.replace_report:
            raise FileExistsError(
                f"Refusing to overwrite existing subject candidate report: {args.output}. "
                "Pass --replace-report after reviewing the refreshed candidates."
            )
        report = apply_evidence_backed_candidates(args.manifest, candidate_report)
        _atomic_json(args.evidence_assignment_report, report)
        candidate_report["inventory_modified"] = True
        candidate_report["manifest_sha256_after_assignment"] = report[
            "manifest_sha256_after_assignment"
        ]
        candidate_report["assignment_status"] = (
            "unique candidates assigned from explicit title evidence; not "
            "individually human-confirmed"
        )
        candidate_report["evidence_assignment_report"] = str(
            args.evidence_assignment_report.resolve()
        )
        _atomic_json(args.output, candidate_report)
    else:
        report = write_subject_candidate_report(
            args.manifest, args.output, overwrite=args.replace_report
        )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "inventory_records": (
                    len(report["confirmations"])
                    if args.apply_user_confirmed_candidates
                    else report.get("assignment_count", report.get("inventory_records"))
                ),
                "confirmation_report": (
                    str(args.confirmation_report.resolve())
                    if args.apply_user_confirmed_candidates
                    else None
                ),
                "evidence_assignment_report": (
                    str(args.evidence_assignment_report.resolve())
                    if args.apply_evidence_backed_candidates
                    else None
                ),
                "confirmed_count": (
                    report["confirmation_count"]
                    if args.apply_user_confirmed_candidates
                    else 0
                ),
                "confirmed_subjects": (
                    report["subjects"]
                    if args.apply_user_confirmed_candidates
                    else report.get("subjects", report.get("subject_candidate_counts"))
                ),
                "candidate_status_counts": (
                    report.get("candidate_status_counts", {})
                    if not args.apply_user_confirmed_candidates
                    and not args.apply_evidence_backed_candidates
                    else {}
                ),
                "inventory_modified": (
                    args.apply_user_confirmed_candidates
                    or args.apply_evidence_backed_candidates
                ),
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
