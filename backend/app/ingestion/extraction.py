import json
import logging
import shutil
from pathlib import Path
from typing import Any

import pymupdf

LOGGER = logging.getLogger(__name__)
OCR_LANGUAGES = {"English": "eng", "Sinhala": "sin", "Tamil": "tam"}
EXPECTED_SCRIPT_RANGES = {
    "Sinhala": ((0x0D80, 0x0DFF),),
    "Tamil": ((0x0B80, 0x0BFF),),
}


def _has_expected_script(text: str, medium: str) -> bool:
    ranges = EXPECTED_SCRIPT_RANGES.get(medium)
    return bool(
        ranges
        and any(
            start <= ord(character) <= end
            for character in text
            for start, end in ranges
        )
    )


def extract_pdf_pages(
    pdf_path: Path,
    relative_file_path: str,
    textbook_id: str,
    medium: str,
    use_ocr: bool = False,
    ocr_all_pages: bool = False,
    ocr_on_missing_script: bool = False,
) -> list[dict[str, Any]]:
    pages = []
    tesseract_available = shutil.which("tesseract") is not None
    logged_missing_tesseract = False
    logged_unknown_language = False

    with pymupdf.open(pdf_path) as document:
        for index, page in enumerate(document):
            embedded_text = page.get_text("text").strip()
            text = embedded_text
            extraction_method = "text_layer" if text else "none"
            extraction_status = "success" if text else "requires_ocr"
            ocr_mean_confidence = None
            ocr_attempted = False
            ocr_trigger = None
            if use_ocr:
                if not text:
                    ocr_trigger = "missing_text"
                elif ocr_all_pages:
                    ocr_trigger = "all_pages"
                elif (
                    ocr_on_missing_script
                    and medium in EXPECTED_SCRIPT_RANGES
                    and not _has_expected_script(text, medium)
                ):
                    ocr_trigger = "missing_expected_script"

            if use_ocr and ocr_trigger is not None:
                if not tesseract_available:
                    extraction_status = (
                        "unicode_mapping_review_ocr_unavailable"
                        if text
                        else "ocr_unavailable"
                    )
                    if not logged_missing_tesseract:
                        LOGGER.error(
                            "Tesseract executable is unavailable for %s",
                            ascii(relative_file_path),
                        )
                        logged_missing_tesseract = True
                elif medium not in OCR_LANGUAGES:
                    extraction_status = "ocr_language_unknown"
                    if not logged_unknown_language:
                        LOGGER.error(
                            "No OCR language configured for %s",
                            ascii(relative_file_path),
                        )
                        logged_unknown_language = True
                else:
                    try:
                        import pytesseract
                        from PIL import Image

                        ocr_attempted = True
                        pixmap = page.get_pixmap(dpi=220, alpha=False)
                        image = Image.frombytes(
                            "RGB",
                            (pixmap.width, pixmap.height),
                            pixmap.samples,
                        )
                        ocr_data = pytesseract.image_to_data(
                            image,
                            lang=OCR_LANGUAGES[medium],
                            output_type=pytesseract.Output.DICT,
                        )
                        line_tokens: dict[tuple[int, int, int, int], list[str]] = {}
                        confidences = []
                        for token_index, token in enumerate(ocr_data["text"]):
                            token = token.strip()
                            if not token:
                                continue
                            line_key = tuple(
                                int(ocr_data[key][token_index])
                                for key in (
                                    "block_num",
                                    "par_num",
                                    "line_num",
                                )
                            )
                            line_tokens.setdefault(line_key, []).append(token)
                            confidence = float(ocr_data["conf"][token_index])
                            if confidence >= 0:
                                confidences.append(confidence)
                        ocr_text = "\n".join(
                            " ".join(tokens) for tokens in line_tokens.values()
                        ).strip()
                        if confidences:
                            ocr_mean_confidence = round(
                                sum(confidences) / len(confidences), 2
                            )
                        if ocr_text:
                            text = ocr_text
                            extraction_method = "tesseract_ocr"
                            extraction_status = "success"
                        elif text:
                            extraction_status = "ocr_no_text_text_layer_retained"
                        else:
                            extraction_status = "ocr_no_text"
                    except Exception:
                        extraction_status = (
                            "ocr_failed_text_layer_retained" if text else "ocr_failed"
                        )
                        LOGGER.exception(
                            "OCR failed for %s page %d",
                            ascii(relative_file_path),
                            index + 1,
                        )

            pages.append(
                {
                    "textbook_id": textbook_id,
                    "source_file": relative_file_path,
                    "pdf_page_number": index + 1,
                    "text": text,
                    "embedded_text": (
                        embedded_text
                        if (
                            use_ocr
                            and (ocr_all_pages or ocr_on_missing_script)
                            and embedded_text
                            and ocr_trigger is not None
                        )
                        else None
                    ),
                    "extraction_method": extraction_method,
                    "extraction_status": extraction_status,
                    "ocr_mean_confidence": ocr_mean_confidence,
                    "ocr_attempted": ocr_attempted,
                    "ocr_trigger": ocr_trigger,
                }
            )
    return pages


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for record in records:
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
