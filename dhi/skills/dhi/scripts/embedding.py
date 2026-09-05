"""Single place that loads the local embedding model, used by both indexing
and search so both sides always agree on model + preprocessing."""

import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"

_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


def embed_documents(texts: list[str]) -> list[np.ndarray]:
    if not texts:
        return []
    model = _get_model()
    return [np.asarray(v, dtype=np.float32) for v in model.embed(texts)]


def embed_query(text: str) -> np.ndarray:
    model = _get_model()
    return np.asarray(next(iter(model.query_embed([text]))), dtype=np.float32)
