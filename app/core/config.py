from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"  # MVP/BACKEND/.env


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    DATABASE_URL: str
    APP_DATABASE_URL: str = ""
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    GROQ_API_KEY: str = ""
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "hr_policy_eka"
    EMBED_MODEL: str="sentence-transformers/all-MiniLM-L6-v2"
    RETRIEVAL_MIN_SCORE: float = 0.25   # calibrate in step 5, don't guess
    GROQ_ROUTER_MODEL:str="openai/gpt-oss-20b"
    GROQ_ANSWER_MODEL:str="openai/gpt-oss-120b"
    CHAT_DAILY_LIMIT: int = 300    # chat messages per company per UTC day

    @field_validator("JWT_SECRET")
    @classmethod
    def secret_long_enough(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @property
    def runtime_db_url(self) -> str:
        return self.APP_DATABASE_URL or self.DATABASE_URL


settings = Settings()