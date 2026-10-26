import json

import pytest
from app.rag import answering


def make_evidence(chunk_id="book:3:1"):
    return [
        {
            "chunk_id": chunk_id,
            "text": "The root holds the plant in the soil.",
            "metadata": {
                "textbook_id": "book",
                "textbook_title": "Grade 2 Science",
                "source_file": "Grade 02/English/science.pdf",
                "pdf_page_number": 3,
                "chapter": "Plants",
                "lesson": "Roots",
                "source_official_status": "user_attested_official",
            },
        }
    ]


def test_quiz_generation_validates_and_attaches_real_sources(monkeypatch):
    generated = {
        "questions": [
            {
                "question": "What does the root do?",
                "options": [
                    "It holds the plant in soil.",
                    "It makes a cup.",
                    "It paints the leaves.",
                ],
                "correct_index": 0,
                "explanation": "The textbook says the root holds the plant in soil.",
                "cited_chunk_ids": ["book:3:1"],
            }
        ]
    }
    monkeypatch.setattr(
        answering,
        "_call_nvidia",
        lambda *_args: json.dumps(generated),
    )

    result = answering.generate_grounded_quiz(
        "Science",
        2,
        "English",
        make_evidence(),
        question_count=1,
        topic="Plant roots",
    )

    assert result["source_chunk_ids"] == ["book:3:1"]
    assert result["questions"][0]["sources"][0]["pdf_page_number"] == 3


def test_quiz_generation_rejects_unknown_citation(monkeypatch):
    generated = {
        "questions": [
            {
                "question": "What does the root do?",
                "options": ["A", "B", "C"],
                "correct_index": 0,
                "explanation": "The textbook says so.",
                "cited_chunk_ids": ["made-up-page"],
            }
        ]
    }
    monkeypatch.setattr(
        answering,
        "_call_nvidia",
        lambda *_args: json.dumps(generated),
    )

    with pytest.raises(answering.AnswerGenerationError, match="evidence validation"):
        answering.generate_grounded_quiz(
            "Science",
            2,
            "English",
            make_evidence(),
            question_count=1,
        )


def test_quiz_generation_rejects_wrong_script(monkeypatch):
    generated = {
        "questions": [
            {
                "question": "What does the root do?",
                "options": ["A", "B", "C"],
                "correct_index": 0,
                "explanation": "The textbook says so.",
                "cited_chunk_ids": ["book:3:1"],
            }
        ]
    }
    monkeypatch.setattr(
        answering,
        "_call_nvidia",
        lambda *_args: json.dumps(generated),
    )

    with pytest.raises(answering.AnswerGenerationError, match="wrong language or script"):
        answering.generate_grounded_quiz(
            "Science",
            2,
            "Tamil",
            make_evidence(),
            question_count=1,
        )


def test_quiz_generation_abstains_when_model_cannot_support_question_count(
    monkeypatch,
):
    monkeypatch.setattr(
        answering,
        "_call_nvidia",
        lambda *_args: json.dumps({"questions": []}),
    )

    with pytest.raises(answering.QuizInsufficientEvidenceError):
        answering.generate_grounded_quiz(
            "Science",
            2,
            "English",
            make_evidence(),
            question_count=3,
        )
