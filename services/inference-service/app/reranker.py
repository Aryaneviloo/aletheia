"""
inference_service.app.reranker
================================

Standard pipeline: bi-encoder retrieves top-50 fast → cross-encoder
reranks to find the genuinely best 10. 
"""

from __future__ import annotations

import time
from functools import lru_cache

from sentence_transformers import CrossEncoder

from aletheia_core.config import get_settings
from aletheia_core.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _load_reranker(model_name: str) -> CrossEncoder:
    log.info("reranker_loading", model=model_name)
    start = time.perf_counter()
    model = CrossEncoder(model_name)
    elapsed = time.perf_counter() - start
    log.info("reranker_loaded", model=model_name, seconds=round(elapsed, 2))
    return model

class Reranker:
    """
    wraps crossencoder to score(query, candidate) pairs and return 
    plain python floats suitable for JSON serialization
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = _load_reranker(model_name)

    @property
    def model_name(self) -> str:
        return self._model_name

    def score(self, query: str, candidates: list[str]) -> list[float]:
        """
        Score each candidate against the query
        """
        pairs = [(query, candidate) for candidate in candidates]
        scores = self._model.predict(pairs)
        return scores.tolist()

@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    settings = get_settings()
    return Reranker(model_name=settings.reranker_model_name)

