"""Módulo de configuración del proyecto basado en Pydantic Settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración global de la aplicación."""

    llm_provider: str = "mock"  # "mock", "gemini", "openai"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = "gemini-3.1-flash-lite"
    database_path: str = "data/orders.db"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Instancia singleton de configuración
settings = Settings()
