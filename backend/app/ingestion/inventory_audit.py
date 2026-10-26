import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

UNKNOWN_VALUES = {"", "unknown", "n/a", "na", "none", "null", "tbd"}
FIELD_ALIASES = {
    "grade": ("grade",),
    "subject": ("subject",),
    "medium": ("medium",),
    "textbook_title": ("textbook_title",),
    "edition_or_year": ("edition_or_year", "edition", "year"),
    "page_count": ("page_count",),
    "local_file_path": ("relative_file_path", "local_file_path", "file_path"),
    "download_status": ("download_status",),
    "source_url_or_origin": ("source_url", "source_origin"),
    "official_source_verification_status": ("official_source_status",),
    "verification_status": ("verification_status",),
}
ATTESTATION_VALUES = {
    "download_status": "user_downloaded",
    "source_origin": (
        "User states they personally downloaded and checked the official source; "
        "exact URL not recorded."
    ),
    "official_source_status": "user_attested_official",
    "official_source_verified_by": "user (identity not recorded)",
    "official_source_verification_basis": (
        "User confirms all inventoried textbooks were personally downloaded and "
        "verified as official; independent verification not performed."
    ),
}
ATTESTATION_FIELDS = (
    "download_status",
    "source_origin",
    "official_source_status",
    "official_source_verified_by",
    "official_source_verified_at",
    "official_source_verification_basis",
)


def _is_unknown(value: str | None) -> bool:
    return value is None or value.strip().casefold() in UNKNOWN_VALUES


def _manifest_rows(manifest_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with manifest_path.open(encoding="utf-8-sig", newline="") as manifest_file:
        reader = csv.DictReader(manifest_file)
        if reader.fieldnames is None:
            raise ValueError(f"Inventory has no header row: {manifest_path}")
        rows = [
            {key: value or "" for key, value in row.items() if key is not None}
            for row in reader
        ]
        return rows, list(reader.fieldnames)


def audit_inventory(manifest_path: Path, data_root: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    data_root = data_root.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Inventory manifest not found: {manifest_path}")
    if not data_root.is_dir():
        raise NotADirectoryError(f"Textbook data root not found: {data_root}")

    rows, columns = _manifest_rows(manifest_path)
    column_names = {column.casefold(): column for column in columns}
    field_coverage: dict[str, dict[str, Any]] = {}
    for field, aliases in FIELD_ALIASES.items():
        matching_columns = [
            column_names[alias.casefold()]
            for alias in aliases
            if alias.casefold() in column_names
        ]
        missing_rows = []
        for row in rows:
            value_present = any(
                not _is_unknown(row.get(column)) for column in matching_columns
            )
            if not value_present:
                missing_rows.append(
                    row.get("textbook_id") or row.get("relative_file_path") or "unknown"
                )
        field_coverage[field] = {
            "columns_found": matching_columns,
            "missing_column": not matching_columns,
            "records_missing_value": len(missing_rows),
            "missing_records": missing_rows,
        }

    audited_records: list[dict[str, Any]] = []
    missing_value_counts: Counter[str] = Counter()
    path_issues: list[dict[str, str]] = []
    textbooks_by_id: Counter[str] = Counter()
    textbook_paths: Counter[str] = Counter()
    for row_number, row in enumerate(rows, start=2):
        textbook_id = row.get("textbook_id", "").strip() or f"row-{row_number}"
        path_columns = [
            column
            for column in FIELD_ALIASES["local_file_path"]
            if column in row and not _is_unknown(row.get(column))
        ]
        relative_path = row.get(path_columns[0], "").strip() if path_columns else ""
        file_exists = False
        path_status = "missing"
        if relative_path:
            candidate = (data_root / relative_path).resolve()
            try:
                candidate.relative_to(data_root)
            except ValueError:
                path_status = "outside_data_root"
                path_issues.append(
                    {
                        "textbook_id": textbook_id,
                        "relative_file_path": relative_path,
                        "issue": path_status,
                    }
                )
            else:
                file_exists = candidate.is_file()
                path_status = "exists" if file_exists else "file_not_found"
                if not file_exists:
                    path_issues.append(
                        {
                            "textbook_id": textbook_id,
                            "relative_file_path": relative_path,
                            "issue": path_status,
                        }
                    )

        missing_fields = [
            field
            for field, aliases in FIELD_ALIASES.items()
            if not any(
                not _is_unknown(row.get(column)) for column in aliases if column in row
            )
        ]
        missing_value_counts.update(missing_fields)
        audited_records.append(
            {
                "row_number": row_number,
                "textbook_id": textbook_id,
                "relative_file_path": relative_path or "unknown",
                "local_file_exists": file_exists,
                "path_status": path_status,
                "missing_fields": missing_fields,
                "verification_status": row.get("verification_status", "unknown"),
            }
        )
        if row.get("textbook_id", "").strip():
            textbooks_by_id[row["textbook_id"].strip()] += 1
        if relative_path:
            textbook_paths[relative_path.casefold()] += 1

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "audit_type": "read_only_inventory_metadata_audit",
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "data_root": str(data_root),
        "inventory_records": len(rows),
        "columns": columns,
        "field_coverage": field_coverage,
        "missing_value_counts": dict(sorted(missing_value_counts.items())),
        "path_issues": path_issues,
        "duplicate_textbook_ids": [
            textbook_id for textbook_id, count in textbooks_by_id.items() if count > 1
        ],
        "duplicate_local_paths": [
            path for path, count in textbook_paths.items() if count > 1
        ],
        "page_count_scope": (
            "Page counts are read from the manifest only; PDFs were not opened or "
            "recounted."
        ),
        "verification_scope": (
            "The manifest verification_status is reported as recorded. OCR page "
            "verification is separate from official-source verification. Any "
            "official-source user attestation is not independently verified."
        ),
        "user_attested_official_books": sum(
            row.get("official_source_status") == "user_attested_official"
            for row in rows
        ),
        "textbooks": audited_records,
    }


def record_user_source_attestation(manifest_path: Path, data_root: Path) -> int:
    manifest_path = manifest_path.resolve()
    data_root = data_root.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Inventory manifest not found: {manifest_path}")
    if not data_root.is_dir():
        raise NotADirectoryError(f"Textbook data root not found: {data_root}")

    rows, columns = _manifest_rows(manifest_path)
    if not rows:
        raise ValueError("Cannot record a source attestation for an empty inventory.")
    if "relative_file_path" not in columns:
        raise ValueError("Inventory is missing the relative_file_path column.")

    missing_files: list[str] = []
    for row in rows:
        relative_path = row.get("relative_file_path", "").strip()
        if _is_unknown(relative_path):
            missing_files.append(relative_path or "unknown")
            continue
        source_path = (data_root / relative_path).resolve()
        try:
            source_path.relative_to(data_root)
        except ValueError:
            missing_files.append(relative_path)
            continue
        if not source_path.is_file():
            missing_files.append(relative_path)
    if missing_files:
        raise ValueError(
            "Cannot attest the complete inventory; local source files are missing "
            "or outside the data root: " + ", ".join(missing_files[:10])
        )

    existing_columns = set(columns)
    for field in ATTESTATION_FIELDS:
        if field not in existing_columns:
            columns.append(field)

    existing_attestation = all(
        row.get("official_source_status") == "user_attested_official"
        and row.get("official_source_verified_by")
        == ATTESTATION_VALUES["official_source_verified_by"]
        and row.get("official_source_verification_basis")
        == ATTESTATION_VALUES["official_source_verification_basis"]
        and row.get("official_source_verified_at")
        for row in rows
    )
    verified_at = (
        rows[0]["official_source_verified_at"]
        if existing_attestation
        else datetime.now(UTC).isoformat()
    )
    for row in rows:
        for field, value in ATTESTATION_VALUES.items():
            current = row.get(field, "").strip()
            if current and current.casefold() != value.casefold():
                raise ValueError(
                    f"Refusing to replace existing {field} value "
                    f"{current!r} for {row.get('textbook_id', 'unknown')}."
                )
            row[field] = value
        current_time = row.get("official_source_verified_at", "").strip()
        if current_time and current_time != verified_at:
            raise ValueError(
                "Refusing to replace existing official-source attestation time "
                f"for {row.get('textbook_id', 'unknown')}."
            )
        row["official_source_verified_at"] = verified_at

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
    return len(rows)


def write_audit_report(
    manifest_path: Path, data_root: Path, output_path: Path
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing audit report: {output_path}"
        )
    report = audit_inventory(manifest_path, data_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)
    return report


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Audit textbook inventory metadata without modifying source data."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=project_root / "data" / "manifests" / "textbook_inventory.csv",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=project_root / "data",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "data" / "manifests" / "textbook_inventory_audit.json",
    )
    parser.add_argument(
        "--record-user-attestation",
        action="store_true",
        help=(
            "Record the user's official-source confirmation after checking every "
            "local PDF path in the inventory."
        ),
    )
    args = parser.parse_args()
    attested_books = None
    if args.record_user_attestation:
        attested_books = record_user_source_attestation(args.manifest, args.data_root)
    report = write_audit_report(args.manifest, args.data_root, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "inventory_records": report["inventory_records"],
                "user_attested_books": attested_books,
                "official_source_user_attestations": report[
                    "user_attested_official_books"
                ],
                "field_coverage": {
                    field: {
                        "missing_column": coverage["missing_column"],
                        "records_missing_value": coverage["records_missing_value"],
                    }
                    for field, coverage in report["field_coverage"].items()
                },
                "path_issues": len(report["path_issues"]),
                "duplicate_textbook_ids": len(report["duplicate_textbook_ids"]),
                "duplicate_local_paths": len(report["duplicate_local_paths"]),
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
