from types import SimpleNamespace

import pytest
from app.api import auth, family
from app.core.config import settings
from fastapi import HTTPException


class Query:
    def __init__(self, data):
        self.data = data

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class Database:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return Query(self.tables.get(name, []))


class StatefulQuery:
    def __init__(self, database, name):
        self.database = database
        self.name = name
        self.filters = {}
        self.insert_value = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, key, values):
        self.filters[key] = values
        return self

    def limit(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def insert(self, value):
        self.insert_value = value
        return self

    def execute(self):
        records = self.database.tables.setdefault(self.name, [])
        if self.insert_value is not None:
            saved = {"id": f"{self.name}-{len(records) + 1}", **self.insert_value}
            records.append(saved)
            if self.name == "quiz_attempts":
                badges = self.database.tables.setdefault("badge_awards", [])
                for code in ["first_quiz"]:
                    if not any(
                        row["student_id"] == saved["student_id"]
                        and row["badge_code"] == code
                        for row in badges
                    ):
                        badges.append(
                            {"student_id": saved["student_id"], "badge_code": code}
                        )
            return SimpleNamespace(data=[saved])
        matches = [
            row
            for row in records
            if all(
                row.get(key) in value if isinstance(value, list) else row.get(key) == value
                for key, value in self.filters.items()
            )
        ]
        return SimpleNamespace(data=matches)


class StatefulDatabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return StatefulQuery(self, name)


def test_protected_endpoint_requires_bearer_token():
    with pytest.raises(HTTPException) as error:
        auth.get_current_user()

    assert error.value.status_code == 401


def test_quiz_topic_suggestions_extract_numbered_textbook_headings():
    document = "1.\nGood Morning to You\n2.\nWhat is Your Name?\n3. Bits of Paper\n"

    assert family._document_topic_titles(document) == [
        "Good Morning to You",
        "What is Your Name?",
        "Bits of Paper",
    ]


def test_quiz_options_use_authorized_student_grade_and_selected_subject(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        family,
        "_student_for_user",
        lambda user, student_id: {"grade": 1},
    )

    def fake_options(grade, medium, subject):
        captured.update(grade=grade, medium=medium, subject=subject)
        return {"subjects": ["English Language"], "topics": ["Good Morning to You"]}

    monkeypatch.setattr(family, "_verified_quiz_options", fake_options)
    user = auth.AuthUser(
        id="parent-1",
        email="parent@example.com",
        role="parent",
    )

    result = family.quiz_options(
        "student-1",
        "English",
        user,
        "English Language",
    )

    assert captured == {
        "grade": 1,
        "medium": "English",
        "subject": "English Language",
    }
    assert result["subjects"] == ["English Language"]
    assert result["topics"] == ["Good Morning to You"]


def test_protected_endpoint_requires_supabase_configuration(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_anon_key", "")

    with pytest.raises(HTTPException) as error:
        auth.get_current_user("Bearer token")

    assert error.value.status_code == 503


def test_bearer_token_is_verified_by_supabase_and_role_is_loaded(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "public-test-key")
    sent_headers = {}

    def fake_get(_url, headers, timeout):
        sent_headers.update(headers)
        assert timeout == 15.0
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "id": "parent-1",
                "email": "parent@example.com",
            },
        )

    monkeypatch.setattr(auth.httpx, "get", fake_get)
    monkeypatch.setattr(
        auth,
        "_profile_for_user",
        lambda user_id, email: auth.AuthUser(
            id=user_id,
            email=email or "",
            role="parent",
        ),
    )

    user = auth.get_current_user("Bearer verified-test-token")

    assert sent_headers["Authorization"] == "Bearer verified-test-token"
    assert user.id == "parent-1"
    assert user.role == "parent"


def test_parent_can_access_only_owned_student(monkeypatch):
    monkeypatch.setattr(
        family,
        "admin_client",
        lambda: Database(
            {
                "students": [
                    {
                        "id": "student-1",
                        "display_name": "Child",
                        "grade": 3,
                        "parent_user_id": "parent-1",
                    }
                ]
            }
        ),
    )
    parent = auth.AuthUser(
        id="parent-1",
        email="parent@example.com",
        role="parent",
    )
    stranger = auth.AuthUser(
        id="parent-2",
        email="other@example.com",
        role="parent",
    )

    assert family._student_for_user(parent, "student-1")["grade"] == 3
    with pytest.raises(HTTPException) as error:
        family._student_for_user(stranger, "student-1")
    assert error.value.status_code == 404


def test_teacher_requires_explicit_student_access(monkeypatch):
    monkeypatch.setattr(
        family,
        "admin_client",
        lambda: Database(
            {
                "students": [
                    {
                        "id": "student-1",
                        "display_name": "Child",
                        "grade": 3,
                        "parent_user_id": "parent-1",
                    }
                ],
                "teacher_student_access": [],
            }
        ),
    )
    teacher = auth.AuthUser(
        id="teacher-1",
        email="teacher@example.com",
        role="teacher",
    )

    with pytest.raises(HTTPException) as error:
        family._student_for_user(teacher, "student-1")

    assert error.value.status_code == 404


def test_public_quiz_never_returns_answer_key():
    public = family._public_quiz(
        {
            "id": "quiz-1",
            "grade": 2,
            "subject": "Science",
            "medium": "English",
            "questions": [
                {
                    "question": "Which part grows?",
                    "options": ["Root", "Stone", "Cup"],
                    "correct_index": 0,
                    "explanation": "The textbook explains the root.",
                    "sources": [{"chunk_id": "book:3:1", "pdf_page_number": 3}],
                }
            ],
        }
    )

    assert "correct_index" not in public["questions"][0]
    assert "explanation" not in public["questions"][0]
    assert public["questions"][0]["sources"][0]["pdf_page_number"] == 3


def test_quiz_generation_saves_grounded_questions_without_answer_key(
    monkeypatch,
):
    database = StatefulDatabase(
        {
            "students": [
                {
                    "id": "student-1",
                    "display_name": "Child",
                    "grade": 2,
                    "parent_user_id": "parent-1",
                }
            ]
        }
    )
    monkeypatch.setattr(family, "admin_client", lambda: database)
    monkeypatch.setattr(settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(settings, "nvidia_model", "test/model")
    evidence = [{"chunk_id": "book:3:1"}]
    generated = {
        "questions": [
            {
                "question": f"Question {number}",
                "options": ["A", "B", "C"],
                "correct_index": 1,
                "explanation": "The page supports this answer.",
                "sources": [{"chunk_id": "book:3:1", "pdf_page_number": 3}],
            }
            for number in range(3)
        ],
        "source_chunk_ids": ["book:3:1"],
    }
    monkeypatch.setattr(family, "retrieve_evidence", lambda *_args, **_kwargs: evidence)
    monkeypatch.setattr(family, "generate_grounded_quiz", lambda *_args: generated)
    parent = auth.AuthUser(
        id="parent-1",
        email="parent@example.com",
        role="parent",
    )

    response = family.create_textbook_quiz(
        "student-1",
        family.QuizRequest(
            subject="Science",
            topic="Plants",
            medium="English",
            question_count=3,
        ),
        parent,
    )

    assert len(database.tables["textbook_quizzes"]) == 1
    assert isinstance(database.tables["textbook_quizzes"][0]["questions"], list)
    assert "correct_index" not in response["questions"][0]
    assert "explanation" not in response["questions"][0]
    assert response["questions"][0]["sources"][0]["pdf_page_number"] == 3


def test_quiz_score_is_calculated_on_server_and_saved(monkeypatch):
    database = StatefulDatabase(
        {
            "students": [
                {
                    "id": "student-1",
                    "display_name": "Child",
                    "grade": 2,
                    "parent_user_id": "parent-1",
                }
            ],
            "textbook_quizzes": [
                {
                    "id": "quiz-1",
                    "student_id": "student-1",
                    "questions": [
                        {
                            "question": "One",
                            "options": ["A", "B", "C"],
                            "correct_index": 0,
                            "explanation": "Evidence one.",
                            "sources": [],
                        },
                        {
                            "question": "Two",
                            "options": ["A", "B", "C"],
                            "correct_index": 1,
                            "explanation": "Evidence two.",
                            "sources": [],
                        },
                        {
                            "question": "Three",
                            "options": ["A", "B", "C"],
                            "correct_index": 2,
                            "explanation": "Evidence three.",
                            "sources": [],
                        },
                    ],
                }
            ],
            "quiz_attempts": [],
            "badge_awards": [],
        }
    )
    monkeypatch.setattr(family, "admin_client", lambda: database)
    parent = auth.AuthUser(
        id="parent-1",
        email="parent@example.com",
        role="parent",
    )

    response = family.submit_textbook_quiz(
        "student-1",
        "quiz-1",
        family.QuizSubmission(answers=[0, 0, 2]),
        parent,
    )

    assert response["score"] == 2
    assert response["total"] == 3
    assert database.tables["quiz_attempts"][0]["score"] == 2
    assert response["new_badges"] == ["first_quiz"]
