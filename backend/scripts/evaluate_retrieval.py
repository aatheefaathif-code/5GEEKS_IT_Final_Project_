import argparse
import json
from pathlib import Path
from typing import Any

from app.rag.answering import retrieve_evidence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = PROJECT_ROOT / "data" / "evaluation" / "rag_retrieval_cases.jsonl"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open(encoding="utf-8") as case_file:
        for line_number, line in enumerate(case_file, start=1):
            if not line.strip():
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON in {path} at line {line_number}."
                ) from error
            required = {
                "case_id",
                "question",
                "grade",
                "subject",
                "medium",
                "expected_chunk_id",
            }
            if not required.issubset(case):
                missing = ", ".join(sorted(required - case.keys()))
                raise ValueError(
                    f"Missing required fields in {path} at line {line_number}: "
                    f"{missing}"
                )
            cases.append(case)
    if not cases:
        raise ValueError(f"No evaluation cases found in {path}.")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure retrieval of expected textbook passages."
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be at least 1.")

    cases = load_cases(args.cases)
    hits = 0
    for case in cases:
        evidence = retrieve_evidence(
            question=case["question"],
            grade=case["grade"],
            subject=case["subject"],
            medium=case["medium"],
            top_k=args.top_k,
        )
        ranked_ids = [item["chunk_id"] for item in evidence]
        expected_id = case["expected_chunk_id"]
        rank = ranked_ids.index(expected_id) + 1 if expected_id in ranked_ids else None
        hits += rank is not None
        print(
            json.dumps(
                {
                    "case_id": case["case_id"],
                    "medium": case["medium"],
                    "expected_chunk_rank": rank,
                    "top_k": args.top_k,
                    "hit": rank is not None,
                },
                ensure_ascii=False,
            )
        )

    hit_rate = hits / len(cases)
    print(
        json.dumps(
            {
                "cases": len(cases),
                "hits": hits,
                "recall_at_k": hit_rate,
                "top_k": args.top_k,
            }
        )
    )
    return 0 if hits == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
