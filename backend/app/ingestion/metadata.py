from typing import Any

REQUIRED_FIELDS = (
    "textbook_id",
    "source_file",
    "pdf_page_number",
    "grade",
    "subject",
    "medium",
    "chapter",
    "lesson",
)
VALID_MEDIA = {"English", "Sinhala", "Tamil", "unknown"}


def validate_chunk_metadata(metadata: dict[str, Any]) -> list[str]:
    errors = [
        f"missing required field: {field}"
        for field in REQUIRED_FIELDS
        if field not in metadata or metadata[field] in (None, "")
    ]
    if "grade" in metadata and metadata["grade"] not in {
        "unknown",
        1,
        2,
        3,
        4,
        5,
        "1",
        "2",
        "3",
        "4",
        "5",
    }:
        errors.append("grade must be 1–5 or unknown")
    if "medium" in metadata and metadata["medium"] not in VALID_MEDIA:
        errors.append("medium must be English, Sinhala, Tamil, or unknown")
    page_number = metadata.get("pdf_page_number")
    if page_number is not None and (
        not isinstance(page_number, int)
        or isinstance(page_number, bool)
        or page_number < 1
    ):
        errors.append("pdf_page_number must be a positive integer")
    return errors
