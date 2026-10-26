import argparse
import base64
import hashlib
import json
import logging
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf

LOGGER = logging.getLogger(__name__)
RESULTS_NAME = "ollama_page_reviews.jsonl"
REPORT_NAME = "ollama_page_reviews_report.json"
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _atomic_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for record in records:
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary_path.replace(path)


def _ollama_json(
    endpoint: str, path: str, payload: dict[str, Any], timeout: int = 60
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise TypeError(f"Ollama returned a non-object response for {path}.")
    return result


def _check_vision_model(endpoint: str, model: str) -> None:
    result = _ollama_json(endpoint, "/api/show", {"name": model})
    capabilities = result.get("capabilities")
    if not isinstance(capabilities, list) or "vision" not in capabilities:
        raise RuntimeError(f"Ollama model {model!r} does not report vision support.")


def _read_page_record(
    batch_dir: Path, textbook_id: str, page_number: int
) -> dict[str, Any]:
    path = batch_dir / f"{textbook_id}.pages.jsonl"
    with path.open(encoding="utf-8") as page_file:
        for line_number, line in enumerate(page_file, start=1):
            record = json.loads(line)
            if record.get("pdf_page_number") == page_number:
                return record
    raise ValueError(f"Page {page_number} was not found in {path}.")


def _render_page(source_root: Path, source_file: str, page_number: int) -> bytes:
    root = source_root.resolve()
    source_path = (root / source_file).resolve()
    if not source_path.is_relative_to(root):
        raise ValueError(f"Source path escapes source root: {source_file}")
    if not source_path.is_file():
        raise FileNotFoundError(f"Source textbook is missing: {source_path}")
    with pymupdf.open(source_path) as document:
        if page_number < 1 or page_number > len(document):
            raise ValueError(
                f"PDF page {page_number} is outside 1..{len(document)}: {source_file}"
            )
        pixmap = document[page_number - 1].get_pixmap(dpi=145, alpha=False)
        return pixmap.tobytes("png")


def _make_prompt(record: dict[str, Any], page: dict[str, Any]) -> str:
    ocr_text = (page.get("text") or "").strip()
    if len(ocr_text) > 4000:
        ocr_text = ocr_text[:4000] + "\n[OCR TEXT TRUNCATED FOR REVIEW]"
    if not ocr_text:
        ocr_text = "[EMPTY OCR TEXT]"
    return (
        "Compare the textbook image with the OCR text. Return at most two concrete "
        "OCR concerns, only when supported by the image. Do not transcribe the page, "
        "solve exercises, infer illegible text, or call any page verified. If you "
        "cannot identify a clear discrepancy, return an empty concerns array. "
        "For each concern give a short issue and an exact short substring from the "
        "OCR text as ocr_quote; use [EMPTY OCR TEXT] only if OCR is empty. "
        "JSON only with this shape: "
        '{"concerns":[{"issue":"short factual concern","ocr_quote":"exact OCR substring",'
        '"confidence":"low|medium|high"}],"human_review_needed":true}. '
        "This is fallible AI triage; human comparison is still required.\n"
        f"Language: {record.get('medium')}; grade: {record.get('grade')}; "
        f"PDF page: {record.get('pdf_page_number')}; "
        f"OCR status: {page.get('extraction_status')}.\n"
        f"OCR text:\n{ocr_text}"
    )


def _review_one(
    record: dict[str, Any],
    page: dict[str, Any],
    image_bytes: bytes,
    endpoint: str,
    model: str,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": _make_prompt(record, page),
                "images": [base64.b64encode(image_bytes).decode("ascii")],
            }
        ],
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 300},
    }
    response = _ollama_json(endpoint, "/api/chat", payload, timeout=300)
    message = response.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise TypeError("Ollama chat response is missing message content.")
    raw_assessment = message["content"]
    assessment = json.loads(raw_assessment)
    concerns = assessment.get("concerns")
    if not isinstance(concerns, list):
        raise TypeError("Ollama assessment must contain a concerns array.")
    model_human_review_recommended = assessment.get("human_review_needed")
    assessment["model_human_review_recommended"] = model_human_review_recommended
    assessment["human_review_needed"] = True
    ocr_text = page.get("text") or ""
    for concern in concerns:
        if not isinstance(concern, dict):
            raise TypeError("Each Ollama concern must be a JSON object.")
        quote = concern.get("ocr_quote")
        if not isinstance(quote, str):
            concern["quote_matches_ocr"] = False
            concern["quote_validation_issue"] = "missing_or_non_string_quote"
            continue
        concern["quote_matches_ocr"] = (
            quote == "[EMPTY OCR TEXT]" if not ocr_text else quote in ocr_text
        )
        if not concern["quote_matches_ocr"]:
            concern["quote_validation_issue"] = "quote_not_found_in_saved_ocr"

    return {
        "review_status": "ai_review_only",
        "human_verified": False,
        "assessment": assessment,
        "raw_assessment": raw_assessment,
        "done_reason": response.get("done_reason"),
        "output_tokens": response.get("eval_count"),
    }


def _load_existing_results(path: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return results
    with path.open(encoding="utf-8") as results_file:
        for line_number, line in enumerate(results_file, start=1):
            result = json.loads(line)
            key = f"{result['textbook_id']}:{result['pdf_page_number']}"
            results[key] = result
    return results


def run_reviews(
    queue_path: Path,
    batch_dir: Path,
    source_root: Path,
    output_dir: Path,
    endpoint: str,
    model: str,
    priorities: set[str],
    resume: bool = False,
) -> dict[str, Any]:
    if not priorities or not priorities <= ALLOWED_PRIORITIES:
        raise ValueError(
            f"Priorities must be selected from {sorted(ALLOWED_PRIORITIES)}."
        )
    queue_bytes = queue_path.read_bytes()
    queue_hash = _sha256(queue_bytes)
    queue_rows = [
        json.loads(line)
        for line in queue_bytes.decode("utf-8").splitlines()
        if line.strip()
    ]
    selected = [row for row in queue_rows if row.get("priority") in priorities]
    settings = {
        "queue_sha256": queue_hash,
        "priorities": sorted(priorities),
        "selected_pages": len(selected),
        "endpoint": endpoint,
        "model": model,
        "render_dpi": 145,
        "ocr_text_max_characters": 4000,
        "review_status": "ai_review_only; human verification required",
    }
    results_path = output_dir / RESULTS_NAME
    report_path = output_dir / REPORT_NAME

    if report_path.exists() and not resume:
        raise FileExistsError(
            f"Review report already exists: {report_path}. Use --resume or a new directory."
        )
    if results_path.exists() and not resume:
        raise FileExistsError(
            f"Review results already exist: {results_path}. Use --resume or a new directory."
        )
    if resume:
        if not report_path.exists() or not results_path.exists():
            raise FileNotFoundError(
                "Cannot resume without both the existing review report and results file."
            )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("settings") != settings:
            raise ValueError(
                "Cannot resume: queue, priorities, or model settings changed."
            )
        existing = _load_existing_results(results_path)
    else:
        if output_dir.exists() and any(output_dir.iterdir()):
            raise FileExistsError(
                f"Output directory is not empty: {output_dir}. Use another directory."
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "created_at": datetime.now(UTC).isoformat(),
            "settings": settings,
            "completed_pages": 0,
            "failed_pages": 0,
        }
        existing = {}

    _check_vision_model(endpoint, model)
    finished = {
        key
        for key, value in existing.items()
        if value.get("request_status") == "completed"
    }
    for index, record in enumerate(selected, start=1):
        result_key = f"{record['textbook_id']}:{record['pdf_page_number']}"
        if result_key in finished:
            continue
        started = time.monotonic()
        result: dict[str, Any] = {
            "textbook_id": record["textbook_id"],
            "source_file": record["source_file"],
            "grade": record.get("grade", "unknown"),
            "medium": record.get("medium", "unknown"),
            "pdf_page_number": record["pdf_page_number"],
            "priority": record["priority"],
            "risk_reasons": record.get("risk_reasons", []),
            "model": model,
            "review_status": "ai_review_only",
            "human_verified": False,
            "verification_status": record.get("verification_status", "unverified"),
            "generated_at": datetime.now(UTC).isoformat(),
        }
        try:
            page = _read_page_record(
                batch_dir,
                record["textbook_id"],
                record["pdf_page_number"],
            )
            image_bytes = _render_page(
                source_root,
                record["source_file"],
                record["pdf_page_number"],
            )
            assessment = _review_one(
                record,
                page,
                image_bytes,
                endpoint,
                model,
            )
            result.update(
                {
                    **assessment,
                    "ocr_status": page.get("extraction_status"),
                    "ocr_method": page.get("extraction_method"),
                    "ocr_text_sha256": _sha256(
                        (page.get("text") or "").encode("utf-8")
                    ),
                    "image_sha256": _sha256(image_bytes),
                    "render_dpi": 145,
                    "request_status": "completed",
                }
            )
        except Exception as error:
            LOGGER.exception(
                "Ollama triage failed for %s page %s",
                record["textbook_id"],
                record["pdf_page_number"],
            )
            result.update(
                {
                    "review_status": "request_failed",
                    "request_status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
        result["duration_seconds"] = round(time.monotonic() - started, 1)
        existing[result_key] = result
        _atomic_jsonl(results_path, list(existing.values()))
        report["completed_pages"] = sum(
            item.get("request_status") == "completed" for item in existing.values()
        )
        report["failed_pages"] = sum(
            item.get("request_status") == "failed" for item in existing.values()
        )
        report["updated_at"] = datetime.now(UTC).isoformat()
        report["progress"] = {
            "current_page_index": index,
            "selected_pages": len(selected),
            "completed_pages": report["completed_pages"],
            "failed_pages": report["failed_pages"],
        }
        _atomic_json(report_path, report)
        LOGGER.info(
            "Ollama triage %d/%d: %s p.%d (%s)",
            index,
            len(selected),
            record["textbook_id"],
            record["pdf_page_number"],
            result["request_status"],
        )

    report["finished_at"] = datetime.now(UTC).isoformat()
    report["completed_pages"] = sum(
        item.get("request_status") == "completed" for item in existing.values()
    )
    report["failed_pages"] = sum(
        item.get("request_status") == "failed" for item in existing.values()
    )
    report["human_verified_pages"] = 0
    report["results_file"] = RESULTS_NAME
    _atomic_json(report_path, report)
    return report


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Run local Ollama vision triage on pages from a review queue."
    )
    parser.add_argument(
        "--queue",
        type=Path,
        default=project_root
        / "data"
        / "extracted"
        / "review_queue"
        / "page_review_queue.jsonl",
    )
    parser.add_argument(
        "--batch-dir",
        type=Path,
        default=project_root / "data" / "extracted" / "full_ocr",
    )
    parser.add_argument("--source-root", type=Path, default=project_root / "data")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root
        / "data"
        / "extracted"
        / "reviews"
        / "ollama_high_risk_round1_20261019",
    )
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument(
        "--priority",
        action="append",
        choices=sorted(ALLOWED_PRIORITIES),
        dest="priorities",
    )
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    priorities = set(args.priorities or ["P0", "P1"])
    report = run_reviews(
        queue_path=args.queue,
        batch_dir=args.batch_dir,
        source_root=args.source_root,
        output_dir=args.output_dir,
        endpoint=args.endpoint,
        model=args.model,
        priorities=priorities,
        resume=args.resume,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir.resolve()),
                "progress": report.get("progress"),
                "completed_pages": report["completed_pages"],
                "failed_pages": report["failed_pages"],
                "human_verified_pages": 0,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    if report["failed_pages"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
