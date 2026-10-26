import re
from collections import Counter
from typing import Any


def clean_repeated_headers_footers(
    pages: list[dict[str, Any]], minimum_ratio: float = 0.6
) -> list[dict[str, Any]]:
    if not pages:
        return []
    if not 0 < minimum_ratio <= 1:
        raise ValueError("minimum_ratio must be in the interval (0, 1]")

    normalized_pages = []
    line_counts: Counter[str] = Counter()
    for page in pages:
        lines = page["text"].splitlines()
        normalized_pages.append(lines)
        candidates = {
            re.sub(r"\s+", " ", line).strip().casefold() for line in lines[:2]
        }
        candidates.update(
            re.sub(r"\s+", " ", line).strip().casefold() for line in lines[-2:]
        )
        line_counts.update(candidate for candidate in candidates if candidate)

    threshold = max(2, int(len(pages) * minimum_ratio + 0.999))
    repeated = {line for line, count in line_counts.items() if count >= threshold}
    cleaned_pages = []
    for page, lines in zip(pages, normalized_pages, strict=True):
        cleaned = [
            line
            for line in lines
            if re.sub(r"\s+", " ", line).strip().casefold() not in repeated
        ]
        cleaned_pages.append({**page, "text": "\n".join(cleaned).strip()})
    return cleaned_pages
