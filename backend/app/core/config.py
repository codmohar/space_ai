"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

ABSTENTION_MESSAGE = (
    "Not found in the available mission reports. More supporting documentation is required."
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MISSIONWISE AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+psycopg://missionwise:missionwise_dev_password@localhost:5432/missionwise"
    )

    # Storage & paths
    storage_dir: Path = Path("./storage")
    data_dir: Path = Path("../data")
    model_cache_dir: Path = Path("./model_cache")
    max_upload_mb: int = 100

    # LLM
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    llm_max_retries: int = 2
    llm_timeout_seconds: int = 45

    # Embeddings & Reranker
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384
    reranker_model: str = "BAAI/bge-reranker-base"

    # Retrieval & Sufficiency
    retrieval_top_k_dense: int = 25
    retrieval_top_k_bm25: int = 25
    retrieval_top_k_rerank: int = 6
    min_rerank_score_threshold: float = 0.18
    min_rrf_score_threshold: float = 0.012
    prompt_version: str = "rag-v1.0"

    # STAIR Section Selection & Evaluation
    section_selector_mode: str = "auto"  # auto | l1_passthrough | bm25_toc | stair_l2 | stair_l3
    stair_top_k_sections: int = 6
    stair_lora_adapter_path: str = ""
    stair_base_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    eval_results_path: Path = Path("../data/evaluation/retrieval_results.json")

    # Voice (faster-whisper STT + optional Piper TTS)
    whisper_model_size: str = "base.en"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    enable_server_stt: bool = True
    piper_binary_path: str = "piper"
    piper_voice_path: str = ""

    # Security & CORS
    jwt_secret_key: str = "change-me-in-production-32-chars-min"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
