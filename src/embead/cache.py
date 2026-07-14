"""Content-addressed, cross-process-safe JSON vector cache."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from filelock import FileLock

from .provider import EmbeddingProvider, Vector


class VectorCache:
    """Store validated vectors beneath a caller-supplied cache directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(self.root / ".cache.lock"))

    @staticmethod
    def key_for(
        text: str,
        *,
        model_id: str,
        model_revision: str,
        schema_version: int = 1,
        canonicalization_version: str = "1",
    ) -> str:
        payload = {
            "canonical_text": text,
            "canonicalization_version": canonicalization_version,
            "model_id": model_id,
            "model_revision": model_revision,
            "schema_version": schema_version,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def get(
        self,
        key: str,
        *,
        model_id: str | None = None,
        model_revision: str | None = None,
        dimension: int | None = None,
    ) -> Vector | None:
        path = self._path(key)
        with self._lock:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
                return None
        if not self._valid_payload(
            payload,
            key=key,
            model_id=model_id,
            model_revision=model_revision,
            dimension=dimension,
        ):
            return None
        return [float(value) for value in payload["vector"]]

    def put(
        self,
        key: str,
        vector: Sequence[float],
        *,
        model_id: str,
        model_revision: str,
    ) -> None:
        values = _validate_vector(vector)
        payload = {
            "cache_version": 1,
            "key": key,
            "model_id": model_id,
            "model_revision": model_revision,
            "dimension": len(values),
            "vector": values,
        }
        path = self._path(key)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(prefix=f".{key}.", suffix=".tmp", dir=path.parent)
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(
                        payload,
                        handle,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, path)
            finally:
                temporary_path.unlink(missing_ok=True)

    def encode(
        self,
        texts: Sequence[str],
        provider: EmbeddingProvider,
        *,
        schema_version: int = 1,
        canonicalization_version: str = "1",
    ) -> list[Vector]:
        """Return vectors in input order, computing and caching only misses."""

        inputs = list(texts)
        keys = [
            self.key_for(
                text,
                model_id=provider.model_id,
                model_revision=provider.model_revision,
                schema_version=schema_version,
                canonicalization_version=canonicalization_version,
            )
            for text in inputs
        ]
        results: list[Vector | None] = [
            self.get(
                key,
                model_id=provider.model_id,
                model_revision=provider.model_revision,
            )
            for key in keys
        ]
        missing_by_key: dict[str, int] = {}
        for index, vector in enumerate(results):
            if vector is None:
                missing_by_key.setdefault(keys[index], index)
        if missing_by_key:
            missing_indexes = list(missing_by_key.values())
            computed = provider.encode([inputs[index] for index in missing_indexes])
            if len(computed) != len(missing_by_key):
                raise ValueError("embedding provider returned the wrong number of vectors")
            expected_dimension = len(computed[0]) if computed else None
            for index, vector in zip(missing_indexes, computed, strict=True):
                values = _validate_vector(vector, dimension=expected_dimension)
                self.put(
                    keys[index],
                    values,
                    model_id=provider.model_id,
                    model_revision=provider.model_revision,
                )
                for result_index, key in enumerate(keys):
                    if key == keys[index]:
                        results[result_index] = values

        vectors = [vector for vector in results if vector is not None]
        if vectors:
            expected_dimension = len(vectors[0])
            vectors = [_validate_vector(vector, dimension=expected_dimension) for vector in vectors]
        return vectors

    def _path(self, key: str) -> Path:
        if len(key) != 64 or any(character not in "0123456789abcdef" for character in key):
            raise ValueError("cache key must be a lowercase SHA-256 digest")
        return self.root / key[:2] / f"{key}.json"

    @staticmethod
    def _valid_payload(
        payload: Any,
        *,
        key: str,
        model_id: str | None,
        model_revision: str | None,
        dimension: int | None,
    ) -> bool:
        if not isinstance(payload, dict) or payload.get("cache_version") != 1:
            return False
        if payload.get("key") != key:
            return False
        if model_id is not None and payload.get("model_id") != model_id:
            return False
        if model_revision is not None and payload.get("model_revision") != model_revision:
            return False
        recorded_dimension = payload.get("dimension")
        if not isinstance(recorded_dimension, int) or recorded_dimension < 1:
            return False
        if dimension is not None and recorded_dimension != dimension:
            return False
        try:
            _validate_vector(payload.get("vector"), dimension=recorded_dimension)
        except (TypeError, ValueError):
            return False
        return True


def _validate_vector(vector: Sequence[float], *, dimension: int | None = None) -> Vector:
    if not isinstance(vector, Sequence) or isinstance(vector, (str, bytes)):
        raise TypeError("vector must be a sequence of numbers")
    values = [float(value) for value in vector]
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("vector must be non-empty and finite")
    if dimension is not None and len(values) != dimension:
        raise ValueError("vector has the wrong dimension")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise ValueError("vector must have a non-zero norm")
    if not math.isclose(norm, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        values = [value / norm for value in values]
    return values
