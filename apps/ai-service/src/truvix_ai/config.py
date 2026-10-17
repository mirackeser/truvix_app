"""Configuration management for Truvix AI Service."""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Execution environment."""
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PROD = "prod"


class AIProviderSettings(BaseSettings):
    """Settings for the AI LLM provider."""
    model_config = SettingsConfigDict(env_prefix="TRUVIX_AI_PROVIDER_")

    api_key: SecretStr | None = None
    base_url: HttpUrl = Field(default=HttpUrl("https://api.openai.com/v1"))
    model: str = "gpt-4o-mini"
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.3
    max_output_tokens: int = 1024
    request_timeout_seconds: float = 30.0
    embeddings_model: str = "text-embedding-3-small"

    @property
    def enabled(self) -> bool:
        """Check if provider is configured and enabled."""
        return self.api_key is not None


class VectorStoreSettings(BaseSettings):
    """Settings for the Chroma vector database."""
    model_config = SettingsConfigDict(env_prefix="TRUVIX_AI_VECTOR_STORE_")

    chroma_host: str = "localhost"
    chroma_port: int = 8000
    collection_name: str = "truvix_vehicles"


class GuardrailSettings(BaseSettings):
    """Safety and limits settings."""
    model_config = SettingsConfigDict(env_prefix="TRUVIX_AI_GUARDRAILS_")

    max_input_chars: int = 4000
    max_photos: int = 12


class ServiceSettings(BaseSettings):
    """Root configuration for the service."""
    model_config = SettingsConfigDict(
        env_prefix="TRUVIX_AI_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    environment: Environment = Environment.DEV
    log_level: str = "INFO"
    log_format: str = "console"
    sentry_dsn: str | None = None

    provider: AIProviderSettings = Field(default_factory=AIProviderSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    guardrails: GuardrailSettings = Field(default_factory=GuardrailSettings)


@lru_cache
def get_settings() -> ServiceSettings:
    """Get cached service settings."""
    return ServiceSettings()
