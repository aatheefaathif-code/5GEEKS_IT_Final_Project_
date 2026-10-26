from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.coloring import router as coloring_router
from app.api.family import router as family_router
from app.api.health import router as health_router
from app.api.learning import router as learning_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(learning_router, prefix=settings.api_prefix)
app.include_router(family_router, prefix=settings.api_prefix)
app.include_router(coloring_router, prefix=settings.api_prefix)
