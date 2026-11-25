"""Embedding service wrapping sentence-transformers (BGE-small-en-v1.5 default)."""

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings


class EmbeddingService:
    def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
        self.model_name = model_name
        self._model = SentenceTransformer(
            model_name,
            cache_folder=cache_dir,
        )

    def embed_passages(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vec.tolist() for vec in vectors]

    def embed_query(self, query: str) -> list[float]:
        # BGE models perform best with the retrieval query instruction prefix
        if "bge" in self.model_name.lower():
            formatted = f"Represent this sentence for searching relevant passages: {query}"
        else:
            formatted = query
        vec = self._model.encode(
            [formatted],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        return vec.tolist()


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    settings = get_settings()
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
    return EmbeddingService(
        model_name=settings.embedding_model,
        cache_dir=str(settings.model_cache_dir),
    )
