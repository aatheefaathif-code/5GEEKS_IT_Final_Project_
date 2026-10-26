import json
import re
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.api.auth import AuthUser, admin_client, get_current_user
from app.core.config import settings
from app.rag.answering import (
    AnswerGenerationError,
    IndexUnavailableError,
    QuizInsufficientEvidenceError,
    generate_grounded_quiz,
    retrieve_evidence,
)
from app.rag.constants import COLLECTION_NAME

router = APIRouter()
Medium = Literal["English", "Sinhala", "Tamil"]


class StudentCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    grade: int = Field(ge=1, le=5)

    @field_validator("display_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Student name cannot be blank.")
        return value


class QuizRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    topic: str = Field(min_length=1, max_length=240)
    medium: Medium
    question_count: int = Field(default=5, ge=3, le=5)

    @field_validator("subject", "topic")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value


class QuizSubmission(BaseModel):
    answers: list[int] = Field(min_length=3, max_length=5)


def _document_topic_titles(document: str) -> list[str]:
    lines = [
        re.sub(r"\s+", " ", line).strip(" \t•")
        for line in document.splitlines()[:80]
    ]
    titles: list[str] = []
    for index, line in enumerate(lines):
        title: str | None = None
        page_and_heading = re.match(r"^\d{1,3}\s+\d{1,3}\.\s+(.+)$", line)
        numbered_heading = re.match(r"^\d{1,3}\.\s+(.+)$", line)
        if page_and_heading:
            title = page_and_heading.group(1)
        elif numbered_heading:
            title = numbered_heading.group(1)
        elif re.fullmatch(r"\d{1,3}\.", line):
            next_line = next(
                (candidate for candidate in lines[index + 1 :] if candidate),
                "",
            )
            if (
                next_line
                and not re.fullmatch(r"\d{1,3}\.?", next_line)
                and not re.match(r"^\d{1,3}\.\s+", next_line)
            ):
                title = next_line
        if title:
            title = re.sub(r"[/.…]+$", "", title).strip(" \t.-•")
            if (
                2 <= len(title) <= 100
                and "\ufffd" not in title
                and any(character.isalpha() for character in title)
            ):
                titles.append(title)
    return titles


def _verified_quiz_options(grade: int, medium: str, subject: str | None) -> dict[str, list[str]]:
    import chromadb

    index_dir = Path(settings.chroma_persist_dir).resolve()
    manifest_path = index_dir / "index_manifest.json"
    if not manifest_path.is_file():
        raise IndexUnavailableError(f"Vector index manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("embedding_model") != settings.embedding_model
        or manifest.get("collection_name") != COLLECTION_NAME
    ):
        raise IndexUnavailableError("Textbook vector index metadata is invalid.")

    client = chromadb.PersistentClient(path=str(index_dir))
    try:
        collection = client.get_collection(COLLECTION_NAME)
        count = collection.count()
        if count != manifest.get("indexed_chunks"):
            raise IndexUnavailableError(
                "Vector collection count does not match its index manifest."
            )
        where = {
            "$and": [
                {"grade": str(grade)},
                {"medium": medium},
                {"page_verification_status": "verified"},
            ]
        }
        page_size = 1000
        offset = 0
        subjects: set[str] = set()
        topic_titles: dict[str, str] = {}
        best_document_topics: list[str] = []
        while offset < count:
            result = collection.get(
                where=where,
                include=["documents", "metadatas"],
                limit=page_size,
                offset=offset,
            )
            metadata_rows = result.get("metadatas") or []
            documents = result.get("documents") or []
            if not metadata_rows:
                break
            for metadata, document in zip(metadata_rows, documents, strict=True):
                indexed_subject = metadata.get("subject")
                if not isinstance(indexed_subject, str) or not indexed_subject.strip():
                    continue
                subjects.add(indexed_subject.strip())
                if subject and indexed_subject.strip().casefold() != subject.casefold():
                    continue
                for field in ("topic", "lesson", "chapter"):
                    value = metadata.get(field)
                    if (
                        isinstance(value, str)
                        and value.strip().casefold() != "unknown"
                        and "\ufffd" not in value
                    ):
                        title = value.strip()
                        key = re.sub(r"[^\w]+", "", title.casefold())
                        topic_titles.setdefault(key, title)
                if isinstance(document, str):
                    document_topics = _document_topic_titles(document)
                    if len(document_topics) > len(best_document_topics):
                        best_document_topics = document_topics
            offset += len(metadata_rows)
        for title in best_document_topics:
            key = re.sub(r"[^\w]+", "", title.casefold())
            topic_titles.setdefault(key, title)
        return {
            "subjects": sorted(subjects, key=str.casefold),
            "topics": sorted(topic_titles.values(), key=str.casefold),
        }
    except chromadb.errors.NotFoundError as error:
        raise IndexUnavailableError("The textbook vector collection is missing.") from error
    finally:
        client.close()


def _student_for_user(user: AuthUser, student_id: str) -> dict:
    db = admin_client()
    student_rows = (
        db.table("students")
        .select("id, display_name, grade, parent_user_id")
        .eq("id", student_id)
        .limit(1)
        .execute()
        .data
    )
    if not student_rows:
        raise HTTPException(status_code=404, detail="Student record not found.")
    student = student_rows[0]
    if user.role == "parent" and student["parent_user_id"] == user.id:
        return student
    if user.role == "teacher":
        access = (
            db.table("teacher_student_access")
            .select("student_id")
            .eq("teacher_user_id", user.id)
            .eq("student_id", student_id)
            .limit(1)
            .execute()
            .data
        )
        if access:
            return student
    raise HTTPException(status_code=404, detail="Student record not found.")


def _public_quiz(row: dict) -> dict:
    questions = row["questions"]
    if isinstance(questions, str):
        questions = json.loads(questions)
    return {
        "id": row["id"],
        "grade": row["grade"],
        "subject": row["subject"],
        "medium": row["medium"],
        "questions": [
            {
                "question": question["question"],
                "options": question["options"],
                "sources": question["sources"],
            }
            for question in questions
        ],
    }


@router.get("/family/students", tags=["family"])
def list_students(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> list[dict]:
    db = admin_client()
    if user.role == "parent":
        return (
            db.table("students")
            .select("id, display_name, grade")
            .eq("parent_user_id", user.id)
            .order("created_at")
            .execute()
            .data
        )
    links = (
        db.table("teacher_student_access")
        .select("student_id")
        .eq("teacher_user_id", user.id)
        .execute()
        .data
    )
    student_ids = [row["student_id"] for row in links]
    if not student_ids:
        return []
    return (
        db.table("students")
        .select("id, display_name, grade")
        .in_("id", student_ids)
        .order("created_at")
        .execute()
        .data
    )


@router.post("/family/students", status_code=201, tags=["family"])
def create_student(
    request: StudentCreate,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    if user.role != "parent":
        raise HTTPException(
            status_code=403,
            detail="Only a parent can create a child profile.",
        )
    result = (
        admin_client()
        .table("students")
        .insert(
            {
                "display_name": request.display_name,
                "grade": request.grade,
                "parent_user_id": user.id,
            }
        )
        .execute()
        .data
    )
    if not result:
        raise HTTPException(status_code=502, detail="Could not save the student profile.")
    return {key: result[0][key] for key in ("id", "display_name", "grade")}


@router.get("/family/students/{student_id}/progress", tags=["family"])
def student_progress(
    student_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    _student_for_user(user, student_id)
    db = admin_client()
    attempts = (
        db.table("quiz_attempts")
        .select("id, quiz_id, score, total, created_at")
        .eq("student_id", student_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data
    )
    badges = (
        db.table("badge_awards")
        .select("badge_code, awarded_at")
        .eq("student_id", student_id)
        .order("awarded_at")
        .execute()
        .data
    )
    summaries = (
        db.table("student_progress_summary")
        .select("completed_quizzes, correct_answers, answered_questions")
        .eq("student_id", student_id)
        .limit(1)
        .execute()
        .data
    )
    summary = (
        summaries[0]
        if summaries
        else {
            "completed_quizzes": 0,
            "correct_answers": 0,
            "answered_questions": 0,
        }
    )
    return {
        "student_id": student_id,
        "attempts": attempts,
        **summary,
        "badges": badges,
    }


@router.get(
    "/family/students/{student_id}/quiz-options",
    tags=["learning"],
)
def quiz_options(
    student_id: str,
    medium: Annotated[Medium, Query()],
    user: Annotated[AuthUser, Depends(get_current_user)],
    subject: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
) -> dict[str, list[str]]:
    student = _student_for_user(user, student_id)
    try:
        return _verified_quiz_options(student["grade"], medium, subject)
    except IndexUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/family/students/{student_id}/quizzes", status_code=201, tags=["learning"])
def create_textbook_quiz(
    student_id: str,
    request: QuizRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    student = _student_for_user(user, student_id)
    if not settings.nvidia_api_key or not settings.nvidia_model.strip():
        raise HTTPException(
            status_code=503,
            detail="Textbook quizzes are unavailable until NVIDIA is configured.",
        )
    try:
        evidence = retrieve_evidence(
            request.topic,
            student["grade"],
            request.subject,
            request.medium,
            top_k=8,
        )
        if not evidence:
            raise HTTPException(
                status_code=422,
                detail="There is not enough verified textbook content to make this quiz.",
            )
        quiz = generate_grounded_quiz(
            request.subject,
            student["grade"],
            request.medium,
            evidence,
            request.question_count,
            request.topic,
        )
    except IndexUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except QuizInsufficientEvidenceError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AnswerGenerationError as error:
        status = (
            503
            if error.upstream_status_code == 429
            or (
                error.upstream_status_code is not None
                and error.upstream_status_code >= 500
            )
            else 502
        )
        raise HTTPException(status_code=status, detail=str(error)) from error

    quiz_id = str(uuid.uuid4())
    stored = {
        **quiz,
        "questions": quiz["questions"],
    }
    result = (
        admin_client()
        .table("textbook_quizzes")
        .insert(
            {
                "id": quiz_id,
                "student_id": student_id,
                "grade": student["grade"],
                "subject": request.subject,
                "topic": request.topic,
                "medium": request.medium,
                "questions": stored["questions"],
                "source_chunk_ids": quiz["source_chunk_ids"],
            }
        )
        .execute()
        .data
    )
    if not result:
        raise HTTPException(status_code=502, detail="Could not save the quiz.")
    return _public_quiz({**result[0], "questions": stored["questions"]})


@router.post(
    "/family/students/{student_id}/quizzes/{quiz_id}/submit",
    tags=["learning"],
)
def submit_textbook_quiz(
    student_id: str,
    quiz_id: str,
    request: QuizSubmission,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> dict:
    _student_for_user(user, student_id)
    db = admin_client()
    quiz_rows = (
        db.table("textbook_quizzes")
        .select("id, student_id, questions")
        .eq("id", quiz_id)
        .eq("student_id", student_id)
        .limit(1)
        .execute()
        .data
    )
    if not quiz_rows:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    if (
        db.table("quiz_attempts")
        .select("id")
        .eq("quiz_id", quiz_id)
        .limit(1)
        .execute()
        .data
    ):
        raise HTTPException(status_code=409, detail="This quiz has already been submitted.")
    questions = quiz_rows[0]["questions"]
    if isinstance(questions, str):
        questions = json.loads(questions)
    if len(request.answers) != len(questions):
        raise HTTPException(
            status_code=422,
            detail="Submit one selected answer for every quiz question.",
        )
    for index, (answer, question) in enumerate(
        zip(request.answers, questions, strict=True)
    ):
        if answer < 0 or answer >= len(question["options"]):
            raise HTTPException(
                status_code=422,
                detail=f"Answer {index + 1} is not a valid option.",
            )
    score = sum(
        answer == question["correct_index"]
        for answer, question in zip(request.answers, questions, strict=True)
    )
    previous_awards = (
        db.table("badge_awards")
        .select("badge_code")
        .eq("student_id", student_id)
        .execute()
        .data
    )
    result = (
        db.table("quiz_attempts")
        .insert(
            {
                "quiz_id": quiz_id,
                "student_id": student_id,
                "score": score,
                "total": len(questions),
                "answers": request.answers,
            }
        )
        .execute()
        .data
    )
    if not result:
        raise HTTPException(status_code=502, detail="Could not save quiz progress.")

    awards = (
        db.table("badge_awards")
        .select("badge_code")
        .eq("student_id", student_id)
        .execute()
        .data
    )
    previous_codes = {award["badge_code"] for award in previous_awards}
    new_badges = [
        award["badge_code"]
        for award in awards
        if award["badge_code"] not in previous_codes
    ]
    return {
        "score": score,
        "total": len(questions),
        "answers": [
            {
                "correct": answer == question["correct_index"],
                "correct_index": question["correct_index"],
                "explanation": question["explanation"],
                "sources": question["sources"],
            }
            for answer, question in zip(request.answers, questions, strict=True)
        ],
        "new_badges": new_badges,
    }
