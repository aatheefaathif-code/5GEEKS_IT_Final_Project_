import json
import logging
from pathlib import Path
from typing import Any

from app.ingestion.metadata import validate_chunk_metadata

LOGGER = logging.getLogger(__name__)


def export_chunks_jsonl(chunks: list[dict[str, Any]], output_path: Path) -> int:
    invalid_chunks = []
    for index, chunk in enumerate(chunks, start=1):
        errors = validate_chunk_metadata(chunk)
        if errors:
            LOGGER.error("Invalid chunk %d: %s", index, "; ".join(errors))
            invalid_chunks.append(index)
    if invalid_chunks:
        raise ValueError(
            f"Refusing to export invalid chunks at indexes {invalid_chunks}."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for chunk in chunks:
            output_file.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return len(chunks)
