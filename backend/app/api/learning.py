from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.rag.answering import (
    AnswerGenerationError,
    IndexUnavailableError,
    generate_grounded_answer,
    retrieve_evidence,
    transform_grounded_answer,
)

router = APIRouter()
Medium = Literal["English", "Sinhala", "Tamil"]


class ConversationTurn(BaseModel):
    role: Literal["student", "tutor"]
    text: str = Field(min_length=1, max_length=1200)

    @field_validator("text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Conversation text cannot be blank.")
        return value


class LearningQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    grade: int = Field(ge=1, le=5)
    subject: str = Field(min_length=1, max_length=120)
    medium: Medium
    answer_language: Medium
    conversation_history: list[ConversationTurn] = Field(
        default_factory=list,
        max_length=8,
    )

    @field_validator("question", "subject")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value


class AnswerTransformation(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    question: str = Field(min_length=1, max_length=1200)
    grade: int = Field(ge=1, le=5)
    subject: str = Field(min_length=1, max_length=120)
    medium: Medium
    answer_language: Medium
    action: Literal["translate", "explain", "short"]
    target_language: Medium | None = None

    @field_validator("answer", "question", "subject")
    @classmethod
    def strip_required_transformation_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value


class SourceReference(BaseModel):
    textbook_id: str
    textbook_title: str | None
    source_file: str
    pdf_page_number: int = Field(ge=1)
    chapter: str | None
    lesson: str | None
    source_official_status: str
    chunk_id: str


class LearningAnswer(BaseModel):
    answer: str
    status: Literal["grounded", "general", "abstained"]
    sources: list[SourceReference]


@router.post("/learning/ask", response_model=LearningAnswer, tags=["learning"])
def ask_learning_question(request: LearningQuestion) -> LearningAnswer:
    if not settings.nvidia_api_key or not settings.nvidia_model.strip():
        raise HTTPException(
            status_code=503,
            detail=(
                "Learning answers are unavailable until NVIDIA_API_KEY and "
                "NVIDIA_MODEL are configured."
            ),
        )
    try:
        prior_student_question = next(
            (
                turn.text
                for turn in reversed(request.conversation_history)
                if turn.role == "student"
            ),
            None,
        )
        retrieval_terms = (
            [prior_student_question]
            if prior_student_question
            and prior_student_question != request.question
            else []
        )
        retrieval_query = " ".join([*retrieval_terms, request.question])
        evidence = retrieve_evidence(
            retrieval_query,
            request.grade,
            request.subject.strip(),
            request.medium,
        )
        result = generate_grounded_answer(
            request.question,
            request.grade,
            request.answer_language,
            evidence,
            [turn.model_dump() for turn in request.conversation_history],
        )
    except IndexUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except AnswerGenerationError as error:
        if error.upstream_status_code == 429 or (
            error.upstream_status_code is not None
            and error.upstream_status_code >= 500
        ):
            raise HTTPException(
                status_code=503,
                detail={"code": "tutor_temporarily_busy"},
            ) from error
        raise HTTPException(status_code=502, detail=str(error)) from error
    return LearningAnswer.model_validate(result)


@router.post("/learning/transform-answer", tags=["learning"])
def transform_learning_answer(request: AnswerTransformation) -> dict[str, str]:
    if request.action == "translate" and (
        request.target_language is None
        or request.target_language == request.answer_language
    ):
        raise HTTPException(
            status_code=422,
            detail="Choose a translation language different from the current answer language.",
        )
    if not settings.nvidia_api_key or not settings.nvidia_model.strip():
        raise HTTPException(
            status_code=503,
            detail=(
                "Answer actions are unavailable until NVIDIA_API_KEY and "
                "NVIDIA_MODEL are configured."
            ),
        )
    try:
        evidence = (
            retrieve_evidence(
                request.question,
                request.grade,
                request.subject.strip(),
                request.medium,
            )
            if request.action == "explain"
            else []
        )
        answer = transform_grounded_answer(
            request.answer,
            request.question,
            request.grade,
            request.action,
            request.answer_language,
            evidence,
            request.target_language,
        )
    except IndexUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except AnswerGenerationError as error:
        if error.upstream_status_code == 429 or (
            error.upstream_status_code is not None
            and error.upstream_status_code >= 500
        ):
            raise HTTPException(
                status_code=503,
                detail={"code": "tutor_temporarily_busy"},
            ) from error
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"answer": answer}
