import re
from typing import Any

HEADING_PATTERNS = (
    (
        "chapter",
        re.compile(
            r"^\s*chapter\s+(\d{1,2})(?:\s*[:.-]\s*.*?)?\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "lesson",
        re.compile(
            r"^\s*lesson\s+(\d{1,2})(?:\s*[:.-]\s*.*?)?\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "chapter",
        re.compile(r"^\s*(?:அத்தியாயம்|පරිච්ඡේදය)\s+(\d{1,2})\s*$"),
    ),
    (
        "lesson",
        re.compile(r"^\s*(?:பாடம்|පාඩම)\s+(\d{1,2})\s*$"),
    ),
)


def _heading_update(line: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    for field, pattern in HEADING_PATTERNS:
        match = pattern.match(line)
        if match:
            return {**metadata, field: match.group(1).strip()}
    return None


def chunk_pages(
    pages: list[dict[str, Any]],
    document_metadata: dict[str, Any],
    max_characters: int = 1400,
) -> list[dict[str, Any]]:
    if max_characters < 1:
        raise ValueError("max_characters must be positive")

    chunks: list[dict[str, Any]] = []
    active_metadata = {
        **document_metadata,
        "chapter": document_metadata.get("chapter", "unknown"),
        "lesson": document_metadata.get("lesson", "unknown"),
        "topic": document_metadata.get("topic", "unknown"),
    }

    def add_chunk(text: str, metadata: dict[str, Any], page: dict[str, Any]) -> None:
        chunks.append(
            {
                **metadata,
                "source_file": page["source_file"],
                "pdf_page_number": page["pdf_page_number"],
                "chunk_id": (
                    f"{metadata['textbook_id']}:"
                    f"{page['pdf_page_number']}:{len(chunks) + 1}"
                ),
                "text": text,
            }
        )

    for page in pages:
        text = page["text"].strip()
        if not text:
            continue
        current_metadata = dict(active_metadata)
        current_text = ""

        def flush(
            chunk_metadata: dict[str, Any],
            source_page: dict[str, Any] = page,
        ) -> None:
            nonlocal current_text
            if current_text:
                add_chunk(current_text, chunk_metadata, source_page)
                current_text = ""

        def append_paragraph(
            paragraph: str,
            paragraph_metadata: dict[str, Any],
            source_page: dict[str, Any] = page,
        ) -> None:
            nonlocal current_text
            while len(paragraph) > max_characters:
                if current_text:
                    flush(paragraph_metadata, source_page)
                add_chunk(paragraph[:max_characters], paragraph_metadata, source_page)
                paragraph = paragraph[max_characters:]
            if not paragraph:
                return
            if current_text and len(current_text) + len(paragraph) + 2 > max_characters:
                flush(paragraph_metadata, source_page)
            current_text = f"{current_text}\n\n{paragraph}".strip()

        paragraph_lines: list[str] = []
        for line in text.splitlines():
            updated_metadata = _heading_update(line, active_metadata)
            if updated_metadata is not None:
                if paragraph_lines:
                    append_paragraph(
                        "\n".join(paragraph_lines).strip(), current_metadata
                    )
                    paragraph_lines = []
                flush(current_metadata)
                active_metadata = updated_metadata
                current_metadata = dict(active_metadata)
                paragraph_lines.append(line.strip())
            elif line.strip():
                paragraph_lines.append(line.strip())
            elif paragraph_lines:
                append_paragraph("\n".join(paragraph_lines).strip(), current_metadata)
                paragraph_lines = []
        if paragraph_lines:
            append_paragraph("\n".join(paragraph_lines).strip(), current_metadata)
        flush(current_metadata)
    return chunks
