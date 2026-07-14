"""Embedding providers used by the semantic analysis core."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

Vector = list[float]


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Minimal provider contract required by the rest of emBEADings."""

    @property
    def model_id(self) -> str: ...

    @property
    def model_revision(self) -> str: ...

    def encode(self, texts: Sequence[str]) -> list[Vector]:
        """Return one fixed-dimension, normalized vector per input string."""


def _normalize(values: Sequence[float]) -> Vector:
    vector = [float(value) for value in values]
    if not vector or any(not math.isfinite(value) for value in vector):
        raise ValueError("embedding vectors must be non-empty and finite")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ValueError("embedding vectors must have a non-zero norm")
    return [value / norm for value in vector]


class Model2VecProvider:
    """Lazy local Model2Vec provider.

    Importing this module does not import or initialize Model2Vec. The model is
    loaded only on the first call to :meth:`encode`, which keeps lightweight CLI
    operations and tests fast.
    """

    DEFAULT_MODEL_ID = "minishlab/potion-base-8M"
    DEFAULT_MODEL_REVISION = "bf8b056651a2c21b8d2565580b8569da283cab23"

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        *,
        model_revision: str = DEFAULT_MODEL_REVISION,
    ) -> None:
        self._model_id = model_id
        self._model_revision = model_revision
        self._model: object | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def model_revision(self) -> str:
        return self._model_revision

    def _load_model(self) -> object:
        if self._model is None:
            try:
                from huggingface_hub import snapshot_download
                from model2vec import StaticModel
            except ImportError as exc:  # pragma: no cover - packaging failure
                raise RuntimeError(
                    "Model2Vec is not installed; install the emBEADings runtime dependencies"
                ) from exc
            model_path = snapshot_download(
                repo_id=self.model_id,
                revision=self.model_revision,
            )
            self._model = StaticModel.from_pretrained(model_path)
        return self._model

    def encode(self, texts: Sequence[str]) -> list[Vector]:
        inputs = list(texts)
        if not inputs:
            return []
        model = self._load_model()
        raw_vectors = model.encode(inputs)  # type: ignore[attr-defined]
        vectors = [_normalize(vector) for vector in raw_vectors]
        if len(vectors) != len(inputs):
            raise ValueError("embedding provider returned the wrong number of vectors")
        _require_fixed_dimension(vectors)
        return vectors


class HashingProvider:
    """Small deterministic provider for tests and synthetic examples.

    It hashes lowercase word tokens into a signed feature vector. It is not a
    semantic model, but shared vocabulary produces predictable cosine similarity.
    """

    def __init__(self, dimension: int = 64) -> None:
        if dimension < 2:
            raise ValueError("dimension must be at least 2")
        self.dimension = dimension

    @property
    def model_id(self) -> str:
        return f"hashing/{self.dimension}"

    @property
    def model_revision(self) -> str:
        return "1"

    def encode(self, texts: Sequence[str]) -> list[Vector]:
        return [self._encode_one(text) for text in texts]

    def _encode_one(self, text: str) -> Vector:
        values = [0.0] * self.dimension
        tokens = re.findall(r"[\w'-]+", text.casefold()) or [""]
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            values[index] += sign
        # Empty strings and rare exact token cancellation still need a valid vector.
        if not any(values):
            values[0] = 1.0
        return _normalize(values)


def _require_fixed_dimension(vectors: Sequence[Sequence[float]]) -> None:
    if vectors and any(len(vector) != len(vectors[0]) for vector in vectors):
        raise ValueError("embedding provider returned vectors with inconsistent dimensions")
