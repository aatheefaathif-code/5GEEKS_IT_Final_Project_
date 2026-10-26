import pytest
from app.api import learning
from app.core.config import settings
from app.main import app
from app.rag import answering
from fastapi.testclient import TestClient

client = TestClient(app)


def test_learning_question_rejects_invalid_grade_and_blank_question():
    payload = {
        "question": " ",
        "grade": 6,
        "subject": "Mathematics",
        "medium": "Tamil",
        "answer_language": "Tamil",
    }

    response = client.post("/api/v1/learning/ask", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)
def test_learning_preflight_allows_local_frontend_origins(origin):
    response = client.options(
        "/api/v1/learning/ask",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_learning_answer_returns_grounded_answer_with_source(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_model", "test/model")
    retrieval_queries = []
    answer_calls = []

    def retrieve(query, *args):
        retrieval_queries.append(query)
        return [{"chunk_id": "tb-1:7:1"}]

    def generate(*args):
        answer_calls.append(args)
        return {
            "answer": "Seven is the answer.",
            "status": "grounded",
            "sources": [
                {
                    "textbook_id": "tb-1",
                    "textbook_title": None,
                    "source_file": "Grade 01/English/book.pdf",
                    "pdf_page_number": 7,
                    "chapter": None,
                    "lesson": "2",
                    "source_official_status": "user_attested_official",
                    "chunk_id": "tb-1:7:1",
                }
            ],
        }

    monkeypatch.setattr(
        learning,
        "retrieve_evidence",
        retrieve,
    )
    monkeypatch.setattr(learning, "generate_grounded_answer", generate)

    response = client.post(
        "/api/v1/learning/ask",
        json={
            "question": "What is seven?",
            "grade": 1,
            "subject": "Mathematics",
            "medium": "English",
            "answer_language": "English",
            "conversation_history": [
                {"role": "student", "text": "What is seven?"},
                {"role": "tutor", "text": "Can you count seven objects?"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "grounded"
    assert response.json()["sources"][0]["pdf_page_number"] == 7
    assert retrieval_queries == ["What is seven?"]
    assert answer_calls[0][-1] == [
        {"role": "student", "text": "What is seven?"},
        {"role": "tutor", "text": "Can you count seven objects?"},
    ]


def test_learning_endpoint_reports_missing_nvidia_configuration(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_api_key", None)
    monkeypatch.setattr(settings, "nvidia_model", "")
    monkeypatch.setattr(
        learning,
        "retrieve_evidence",
        lambda *args: [{"chunk_id": "tb-1:1:1"}],
    )

    response = client.post(
        "/api/v1/learning/ask",
        json={
            "question": "Question",
            "grade": 1,
            "subject": "Mathematics",
            "medium": "English",
            "answer_language": "English",
        },
    )

    assert response.status_code == 503
    assert "NVIDIA_API_KEY" in response.json()["detail"]
    assert "NVIDIA_MODEL" in response.json()["detail"]


def test_learning_endpoint_translates_index_failure(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_model", "test/model")

    def unavailable(*args):
        raise learning.IndexUnavailableError("Vector index unavailable.")

    monkeypatch.setattr(learning, "retrieve_evidence", unavailable)

    response = client.post(
        "/api/v1/learning/ask",
        json={
            "question": "Question",
            "grade": 1,
            "subject": "Mathematics",
            "medium": "English",
            "answer_language": "English",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Vector index unavailable."


def test_learning_endpoint_reports_temporary_gemini_overload(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_model", "test/model")
    monkeypatch.setattr(
        learning,
        "retrieve_evidence",
        lambda *args: [{"chunk_id": "tb-1:1:1"}],
    )

    def overloaded(*args):
        raise learning.AnswerGenerationError(
            "NVIDIA answer generation failed.",
            upstream_status_code=503,
        )

    monkeypatch.setattr(learning, "generate_grounded_answer", overloaded)

    response = client.post(
        "/api/v1/learning/ask",
        json={
            "question": "Question",
            "grade": 1,
            "subject": "Mathematics",
            "medium": "English",
            "answer_language": "English",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {"code": "tutor_temporarily_busy"}


def test_learning_endpoint_shows_upstream_status_for_provider_errors(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_model", "test/model")
    monkeypatch.setattr(
        learning,
        "retrieve_evidence",
        lambda *args: [{"chunk_id": "tb-1:1:1"}],
    )

    def provider_error(*args):
        raise learning.AnswerGenerationError(
            "NVIDIA answer generation failed (upstream HTTP 404).",
            upstream_status_code=404,
        )

    monkeypatch.setattr(learning, "generate_grounded_answer", provider_error)

    response = client.post(
        "/api/v1/learning/ask",
        json={
            "question": "Question",
            "grade": 1,
            "subject": "Mathematics",
            "medium": "English",
            "answer_language": "English",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "NVIDIA answer generation failed (upstream HTTP 404)."
    )


def test_general_answer_without_textbook_evidence_is_labeled_and_has_no_sources(
    monkeypatch,
):
    monkeypatch.setattr(settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_model", "test/model")
    monkeypatch.setattr(
        answering,
        "_call_nvidia",
        lambda prompt, system: (
            '{"answer":"சூரியன் ஒரு நட்சத்திரம்.","cited_chunk_ids":[],"abstained":false}'
        ),
    )
    result = learning.generate_grounded_answer(
        question="What is the Sun?",
        grade=1,
        answer_language="Tamil",
        evidence=[],
    )

    assert result["status"] == "general"
    assert result["sources"] == []
    assert "பாடநூலில் கிடைக்கவில்லை" in result["answer"]


def test_learning_endpoint_returns_general_answers_without_sources(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_model", "test/model")
    monkeypatch.setattr(learning, "retrieve_evidence", lambda *args: [])
    generated = []

    def generate(*args):
        generated.append(args)
        return {
            "answer": "General answer — not found in the selected textbook.\n\nThe Sun is a star.",
            "status": "general",
            "sources": [],
        }

    monkeypatch.setattr(learning, "generate_grounded_answer", generate)
    response = client.post(
        "/api/v1/learning/ask",
        json={
            "question": "What is the Sun?",
            "grade": 1,
            "subject": "Science",
            "medium": "English",
            "answer_language": "English",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "general"
    assert response.json()["sources"] == []
    assert "not found in the selected textbook" in response.json()["answer"]
    assert len(generated) == 1


def test_transform_endpoint_translates_answer_to_a_different_language(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_model", "test/model")
    evidence_calls = []
    transform_calls = []

    def retrieve(*args):
        evidence_calls.append(args)
        return [{"chunk_id": "tb-1:7:1"}]

    def transform(*args):
        transform_calls.append(args)
        return "ஏழு என்பது ஒரு எண்."

    monkeypatch.setattr(learning, "retrieve_evidence", retrieve)
    monkeypatch.setattr(learning, "transform_grounded_answer", transform)
    response = client.post(
        "/api/v1/learning/transform-answer",
        json={
            "answer": "Seven is a number.",
            "question": "What is seven?",
            "grade": 1,
            "subject": "Mathematics",
            "medium": "English",
            "answer_language": "English",
            "action": "translate",
            "target_language": "Tamil",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"answer": "ஏழு என்பது ஒரு எண்."}
    assert evidence_calls == []
    assert transform_calls[0][3:] == (
        "translate",
        "English",
        [],
        "Tamil",
    )


def test_transform_endpoint_rejects_translation_to_current_language():
    response = client.post(
        "/api/v1/learning/transform-answer",
        json={
            "answer": "Seven is a number.",
            "question": "What is seven?",
            "grade": 1,
            "subject": "Mathematics",
            "medium": "English",
            "answer_language": "English",
            "action": "translate",
            "target_language": "English",
        },
    )

    assert response.status_code == 422


def test_transform_endpoint_requires_textbook_evidence_for_more_explanation(monkeypatch):
    monkeypatch.setattr(settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_model", "test/model")
    monkeypatch.setattr(learning, "retrieve_evidence", lambda *args: [])
    response = client.post(
        "/api/v1/learning/transform-answer",
        json={
            "answer": "Seven is a number.",
            "question": "What is seven?",
            "grade": 1,
            "subject": "Mathematics",
            "medium": "English",
            "answer_language": "English",
            "action": "explain",
        },
    )

    assert response.status_code == 503
    assert "verified textbook content" in response.json()["detail"]
