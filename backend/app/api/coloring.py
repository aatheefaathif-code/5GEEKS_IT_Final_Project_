import csv
import json
from pathlib import Path
from typing import Annotated, Literal

import pymupdf
from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParameter
from fastapi.responses import Response

router = APIRouter()
Medium = Literal["English", "Sinhala", "Tamil"]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = (PROJECT_ROOT / "data").resolve()
INVENTORY_PATH = DATA_ROOT / "manifests" / "textbook_inventory.csv"
OCR_ROOT = DATA_ROOT / "extracted" / "full_ocr"
VERIFICATION_METHOD = "user_confirmed_source_pdf_comparison"


def _inventory() -> list[dict[str, str]]:
    if not INVENTORY_PATH.is_file():
        raise HTTPException(
            status_code=503,
            detail="The textbook inventory is not available for coloring activities.",
        )
    with INVENTORY_PATH.open(encoding="utf-8-sig", newline="") as inventory_file:
        return list(csv.DictReader(inventory_file))


def _verified_pages(textbook_id: str) -> dict[int, dict]:
    pages_path = OCR_ROOT / f"{textbook_id}.pages.jsonl"
    if not pages_path.is_file():
        return {}
    verified: dict[int, dict] = {}
    with pages_path.open(encoding="utf-8") as pages_file:
        for line in pages_file:
            page = json.loads(line)
            verification = page.get("human_verification")
            if (
                page.get("verification_status") == "verified"
                and page.get("human_verified") is True
                and isinstance(verification, dict)
                and verification.get("verification_method") == VERIFICATION_METHOD
                and isinstance(page.get("pdf_page_number"), int)
            ):
                verified[page["pdf_page_number"]] = page
    return verified


def _pdf_path(relative_path: str) -> Path:
    source_path = (DATA_ROOT / relative_path).resolve()
    if not source_path.is_relative_to(DATA_ROOT) or not source_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="The selected textbook file is not available.",
        )
    return source_path


def _page_metadata(
    book: dict[str, str],
    page_number: int,
    verified_pages: dict[int, dict] | None = None,
) -> dict | None:
    textbook_id = book.get("textbook_id", "")
    relative_path = book.get("relative_file_path", "")
    if not textbook_id or not relative_path:
        return None
    verified = verified_pages if verified_pages is not None else _verified_pages(textbook_id)
    exercise = verified.get(page_number)
    reference = verified.get(page_number - 1)
    if not exercise or not reference:
        return None
    if "colour and say" not in str(exercise.get("text", "")).casefold():
        return None
    try:
        page_count = int(book.get("page_count", "0"))
    except ValueError:
        return None
    if page_number > page_count:
        return None
    return {
        "textbook_id": textbook_id,
        "textbook_title": book.get("textbook_title") or "unknown",
        "source_file": relative_path,
        "grade": int(book["grade"]),
        "subject": book.get("subject", "unknown"),
        "medium": book.get("medium", "unknown"),
        "reference_page": page_number - 1,
        "exercise_page": page_number,
    }


@router.get("/learning/coloring-pages", tags=["learning"])
def list_coloring_pages(
    grade: Annotated[int, Query(ge=1, le=5)],
    medium: Medium,
    subject: Annotated[str, Query(min_length=1, max_length=120)],
) -> list[dict]:
    results = []
    for book in _inventory():
        if (
            book.get("grade") != str(grade)
            or book.get("medium") != medium
            or book.get("subject", "").casefold() != subject.strip().casefold()
        ):
            continue
        textbook_id = book.get("textbook_id", "")
        if not textbook_id:
            continue
        verified_pages = _verified_pages(textbook_id)
        for page_number, page in verified_pages.items():
            if "colour and say" not in str(page.get("text", "")).casefold():
                continue
            pair = _page_metadata(book, page_number, verified_pages)
            if pair:
                results.append(pair)
    return results


@router.get(
    "/learning/coloring-pages/{textbook_id}/{page_number}.png",
    response_class=Response,
    tags=["learning"],
)
def render_coloring_page(
    textbook_id: str,
    page_number: Annotated[int, PathParameter(ge=1)],
    kind: Literal["reference", "exercise"],
) -> Response:
    book = next(
        (
            row
            for row in _inventory()
            if row.get("textbook_id") == textbook_id
        ),
        None,
    )
    if book is None:
        raise HTTPException(status_code=404, detail="The textbook page was not found.")
    pair = _page_metadata(book, page_number)
    if pair is None:
        raise HTTPException(
            status_code=404,
            detail="This page is not a verified coloring activity.",
        )
    selected_page = (
        pair["reference_page"] if kind == "reference" else pair["exercise_page"]
    )
    try:
        document = pymupdf.open(_pdf_path(pair["source_file"]))
        try:
            if selected_page < 1 or selected_page > len(document):
                raise HTTPException(
                    status_code=404,
                    detail="The selected page is outside this textbook.",
                )
            pixmap = document[selected_page - 1].get_pixmap(
                dpi=120,
                alpha=False,
                colorspace=pymupdf.csRGB,
            )
            image = pixmap.tobytes("png")
        finally:
            document.close()
    except HTTPException:
        raise
    except (OSError, pymupdf.FileDataError, pymupdf.EmptyFileError) as error:
        raise HTTPException(
            status_code=503,
            detail="Could not open the verified textbook page.",
        ) from error
    return Response(
        content=image,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
