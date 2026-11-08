"""Loads the embedding model once; embed(texts) -> L2-normalised vectors.

EMBEDDING_MODEL=hash selects a tiny hashing embedder with no download. It is only good
enough for UI development and tests; use bge-m3 for anything you want to measure.
"""
import hashlib
import os
import re
import threading

import numpy as np

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)
_TOKEN = re.compile(r"\w+", re.UNICODE)


class HashEmbedder:
    name = "hash"

    def __init__(self, dim: int):
        self.dim = dim

    def _bucket(self, tok: str) -> tuple[int, float]:
        h = hashlib.md5(tok.encode()).digest()
        return int.from_bytes(h[:4], "little") % self.dim, 1.0 if h[4] & 1 else -1.0

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, t in enumerate(texts):
            toks = [w.lower() for w in _TOKEN.findall(t)]
            feats = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
            for f in feats:
                i, sign = self._bucket(f)
                out[row, i] += sign
            n = np.linalg.norm(out[row])
            if n:
                out[row] /= n
        return out


class STEmbedder:
    def __init__(self, model_name: str, device: str, batch_size: int):
        if settings.hf_token:
            os.environ.setdefault("HF_TOKEN", settings.hf_token)
        from sentence_transformers import SentenceTransformer

        log.info("loading embedding model", extra={"kv": {"model": model_name, "device": device}})
        self.name = model_name
        self.model = SentenceTransformer(model_name, device=device)
        self.batch_size = batch_size
        dim = self.model.get_sentence_embedding_dimension()
        if dim != settings.embedding_dim:
            raise ValueError(f"{model_name} outputs {dim} dims but EMBEDDING_DIM={settings.embedding_dim}. "
                             "Change EMBEDDING_DIM and vector(N) in db/init.sql, then re-ingest.")

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, settings.embedding_dim), dtype=np.float32)
        return np.asarray(self.model.encode(texts, batch_size=self.batch_size,
                                            normalize_embeddings=True, show_progress_bar=False),
                          dtype=np.float32)


_lock = threading.Lock()
_instance = None


def get_embedder():
    global _instance
    with _lock:
        if _instance is None:
            if settings.embedding_model.lower() == "hash":
                _instance = HashEmbedder(settings.embedding_dim)
            else:
                _instance = STEmbedder(settings.embedding_model, settings.embedding_device,
                                       settings.embedding_batch_size)
        return _instance


def is_loaded() -> bool:
    return _instance is not None
