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
    gemini_model: str = "gemini-3.5-flash"
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
    open_query_retrieval: bool = True
    doc_upload_enabled: bool = True

    # STAIR Section Selection & Evaluation
    section_selector_mode: str = "auto"  # auto | l1_passthrough | bm25_toc | stair_l2 | stair_l3
    stair_top_k_sections: int = 6
    stair_lora_adapter_path: str = ""
    stair_base_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    eval_results_path: Path = Path("../data/evaluation/retrieval_results.json")

    # Voice (Sarvam AI primary STT/TTS + faster-whisper / Piper fallback)
    sarvam_api_key: str = ""
    sarvam_stt_model: str = "saarika:v1"
    sarvam_tts_model: str = "bulbul:v1"
    sarvam_language_code: str = "en-IN"
    sarvam_speaker: str = "meera"
    sarvam_pace: float = 1.05
    sarvam_loudness: float = 1.5
    sarvam_sample_rate: int = 16000
    prefer_sarvam_voice: bool = True
    whisper_model_size: str = "base.en"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    enable_server_stt: bool = True
    piper_binary_path: str = "piper"
    piper_voice_path: str = ""

    # Security, Auth, Rate Limiting & CORS
    jwt_secret_key: str = "change-me-in-production-32-chars-min"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    auth_required: bool = False
    seed_demo_users: bool = True
    demo_admin_password: str = "Admin!Mission2026"
    demo_engineer_password: str = "Engineer!Mission2026"
    rate_limit_per_minute: int = 120
    chat_rate_limit_per_minute: int = 40
    max_upload_pages: int = 800
    prewarm_models: bool = True
    demo_cache_path: Path = Path("../data/demo/demo_cache.json")
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
