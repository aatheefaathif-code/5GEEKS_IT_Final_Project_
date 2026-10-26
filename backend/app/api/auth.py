from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from supabase import Client, create_client

router = APIRouter()


class AccountRequest(BaseModel):
    email: str = Field(
        min_length=5,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=8, max_length=128)


class AuthUser(BaseModel):
    id: str
    email: str
    role: Literal["parent", "teacher"]
    full_name: str | None = None


def require_supabase_configuration() -> None:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY.",
        )


def admin_client() -> Client:
    require_supabase_configuration()
    if not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Secure family data is unavailable until "
                "SUPABASE_SERVICE_ROLE_KEY is configured on the backend."
            ),
        )
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )


def _auth_request(path: str, payload: dict[str, str]) -> dict:
    require_supabase_configuration()
    try:
        response = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/{path}",
            headers={"apikey": settings.supabase_anon_key},
            json=payload,
            timeout=15.0,
        )
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=503,
            detail="Could not connect to Supabase Auth.",
        ) from error
    if response.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Supabase Auth is rate-limiting requests. Please wait and try again.",
        )
    if response.status_code >= 500:
        raise HTTPException(
            status_code=503,
            detail="Supabase Auth is temporarily unavailable.",
        )
    if response.status_code >= 400:
        if path.startswith("token"):
            raise HTTPException(status_code=401, detail="Email or password is incorrect.")
        try:
            error_body = response.json()
        except ValueError:
            error_body = None
        detail = (
            error_body.get("msg") or error_body.get("message")
            if isinstance(error_body, dict)
            else None
        )
        raise HTTPException(
            status_code=400,
            detail=detail if isinstance(detail, str) else "Could not create the account.",
        )
    try:
        body = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="Supabase Auth returned an invalid response.",
        ) from error
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=502,
            detail="Supabase Auth returned an invalid response.",
        )
    return body


def _profile_for_user(user_id: str, email: str | None) -> AuthUser:
    rows = (
        admin_client()
        .table("profiles")
        .select("user_id, role, full_name")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(
            status_code=403,
            detail="This account has no approved parent or teacher profile.",
        )
    profile = rows[0]
    if profile["role"] not in ("parent", "teacher"):
        raise HTTPException(
            status_code=403,
            detail="This account is not authorized to access family records.",
        )
    return AuthUser(
        id=user_id,
        email=email or "",
        role=profile["role"],
        full_name=profile["full_name"],
    )


@router.post("/auth/signup", status_code=201, tags=["auth"])
def sign_up(request: AccountRequest) -> dict[str, str | bool]:
    _auth_request(
        "signup",
        {"email": request.email, "password": request.password},
    )
    return {
        "created": True,
        "message": "Account created. Verify your email if Supabase requires confirmation, then sign in.",
    }


@router.post("/auth/login", tags=["auth"])
def sign_in(request: AccountRequest) -> dict:
    body = _auth_request(
        "token?grant_type=password",
        {"email": request.email, "password": request.password},
    )
    access_token = body.get("access_token")
    user = body.get("user")
    if not isinstance(access_token, str) or not isinstance(user, dict):
        raise HTTPException(
            status_code=502,
            detail="Supabase Auth returned an incomplete sign-in response.",
        )
    user_id = user.get("id")
    email = user.get("email")
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=502,
            detail="Supabase Auth returned an invalid user record.",
        )
    profile = _profile_for_user(user_id, email if isinstance(email, str) else None)
    return {"access_token": access_token, "user": profile.model_dump()}


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    require_supabase_configuration()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "apikey": settings.supabase_anon_key,
                "Authorization": f"Bearer {token}",
            },
            timeout=15.0,
        )
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=503,
            detail="Could not verify your Supabase session.",
        ) from error
    if response.status_code in (401, 403):
        raise HTTPException(status_code=401, detail="Your sign-in has expired.")
    if response.status_code >= 400:
        raise HTTPException(
            status_code=503,
            detail="Supabase could not verify your session.",
        )
    try:
        user = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail="Supabase Auth returned an invalid user response.",
        ) from error
    user_id = user.get("id") if isinstance(user, dict) else None
    email = user.get("email") if isinstance(user, dict) else None
    if not isinstance(user_id, str):
        raise HTTPException(status_code=401, detail="Your sign-in has expired.")
    return _profile_for_user(user_id, email if isinstance(email, str) else None)


@router.get("/auth/me", response_model=AuthUser, tags=["auth"])
def current_user(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> AuthUser:
    return user
