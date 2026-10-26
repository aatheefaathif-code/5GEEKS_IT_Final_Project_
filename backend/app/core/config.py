from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Syllabus-Aligned AI Learning Assistant API"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_api_key: str | None = None
    nvidia_model: str = ""
    chroma_persist_dir: str = "data/index/chroma_multilingual_e5_large"
    embedding_model: str = "intfloat/multilingual-e5-large"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
