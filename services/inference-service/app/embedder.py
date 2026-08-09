"""
inference_service.app.embedder
================================

BGE embedding model loaded once to us everywhere
lru cache added so that python calls it once and returns
the already loaded model instantly
"""

from __future__ import annotations
import time
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from aletheia_core.config import get_settings
from aletheia_core.logging import get_logger

log = get_logger(__name__)

@lru_cache(maxsize=1)
def _load_model(model_name: str) -> SentenceTransformer:
    """
    Load and cache the embedding model
    maxsize = 1: cache exactly one model if somehow called with two
    different model names
    """
    log.info("embedder loading", model=model_name)
    start = time.perf_counter()
    model = SentenceTransformer(model_name)
    elapsed = time.perf_counter() - start
    log.info("embedder loaded", model = model_name, seconds = round(elapsed, 2))
    return model

class Embedder:
    """
    Thin wrapper around the Sentence Transformer that enforces batch 
    embedding and normalizes output to plain Python for serialization
    """

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = _load_model(model_name)


    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        """Embedding dimensionality: read from the loading model"""
        return self._model.get_sentence_embedding_dimension()


    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        EMbed a batch of texts, always called with a list so that
        CPU/GPU is utilized well. EX: sending 50 texts in one call is
        faster than sendign 1 per 1
        
        normalise = True because unit vectors are required for cosine
        similarity
        """

        vectors = self._model.encode(
            texts,
            normalize_embeddings = True,
            show_progress_bar = False,
        )

        return vectors.tolist()



@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    
    settings = get_settings()
    return Embedder(model_name=settings.embedding_model_name)