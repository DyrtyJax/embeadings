#!/usr/bin/env python3
"""Compare optional embedding and vector-cache alternatives on public synthetic data."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import sqlite3
import statistics
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from embead.cache import VectorCache
from embead.provider import HashingProvider, Model2VecProvider, _normalize

SEMANTIC_PAIRS = (
    (
        "Keep users signed in after a browser restart",
        "Persist authentication sessions across relaunches",
    ),
    ("Recover an account with a reset email", "Restore access through the password recovery link"),
    (
        "Delay image loading until the gallery is visible",
        "Lazy load thumbnails when they enter the viewport",
    ),
    ("Reject an expired API credential", "Deny requests made with stale access tokens"),
    ("Export invoices as accessible PDF documents", "Generate screen-reader friendly billing PDFs"),
    ("Retry a failed background delivery", "Reschedule unsuccessful asynchronous message sends"),
    ("Prevent duplicate checkout submissions", "Make purchase creation idempotent"),
    ("Record an audit event for permission changes", "Log role updates in the security history"),
    (
        "Rotate encryption keys without downtime",
        "Replace active cryptographic keys during live traffic",
    ),
    ("Paginate a large activity timeline", "Load history entries in bounded pages"),
    ("Validate uploaded spreadsheet columns", "Check tabular import headers before ingestion"),
    (
        "Restore a deleted project from retention storage",
        "Recover removed workspaces during the grace period",
    ),
)


def _milliseconds(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _quality(vectors: Sequence[Sequence[float]]) -> dict[str, float]:
    expected = {index: index + 1 if index % 2 == 0 else index - 1 for index in range(len(vectors))}
    hits = 0
    margins: list[float] = []
    for index, vector in enumerate(vectors):
        scores = [
            -math.inf if index == other else float(np.dot(vector, candidate))
            for other, candidate in enumerate(vectors)
        ]
        ranked = sorted(range(len(scores)), key=lambda other: (-scores[other], other))
        hits += ranked[0] == expected[index]
        best_wrong = max(score for other, score in enumerate(scores) if other != expected[index])
        margins.append(scores[expected[index]] - best_wrong)
    return {
        "pair_recall_at_1": round(hits / len(vectors), 4),
        "median_pair_margin": round(statistics.median(margins), 6),
    }


def _provider_result(
    name: str,
    factory: Callable[[], Any],
    encode: Callable[[Any, Sequence[str]], list[list[float]]],
) -> dict[str, Any]:
    texts = [text for pair in SEMANTIC_PAIRS for text in pair]
    started = time.perf_counter()
    provider = factory()
    initialization_ms = _milliseconds(started)
    started = time.perf_counter()
    vectors = encode(provider, texts)
    cold_encode_ms = _milliseconds(started)
    started = time.perf_counter()
    repeat = encode(provider, texts)
    warm_encode_ms = _milliseconds(started)
    if len(vectors) != len(texts) or any(len(vector) != len(vectors[0]) for vector in vectors):
        raise ValueError(f"{name} returned an invalid vector batch")
    deterministic = all(
        np.allclose(left, right, rtol=1e-6, atol=1e-6)
        for left, right in zip(vectors, repeat, strict=True)
    )
    return {
        "provider": name,
        "records": len(texts),
        "dimension": len(vectors[0]),
        "initialization_ms": round(initialization_ms, 3),
        "cold_encode_ms": round(cold_encode_ms, 3),
        "warm_encode_ms": round(warm_encode_ms, 3),
        "deterministic": deterministic,
        "quality": _quality(vectors),
    }


def _model2vec(cache_dir: Path) -> dict[str, Any]:
    os.environ.setdefault("HF_HOME", str(cache_dir))
    return _provider_result(
        "model2vec/potion-base-8M",
        Model2VecProvider,
        lambda provider, texts: provider.encode(texts),
    )


def _fastembed(cache_dir: Path) -> dict[str, Any]:
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise RuntimeError("install the optional fastembed package") from exc

    return _provider_result(
        "fastembed/BAAI-bge-small-en-v1.5",
        lambda: TextEmbedding(model_name="BAAI/bge-small-en-v1.5", cache_dir=str(cache_dir)),
        lambda provider, texts: [
            _normalize(vector) for vector in provider.embed(list(texts), batch_size=64)
        ],
    )


def _storage_vectors(count: int, dimension: int) -> list[list[float]]:
    provider = HashingProvider(dimension)
    texts = [f"synthetic vector record {index} group {index % 97}" for index in range(count)]
    return provider.encode(texts)


def _file_cache(root: Path, vectors: Sequence[Sequence[float]]) -> dict[str, Any]:
    cache = VectorCache(root)
    keys = [f"{index:064x}" for index in range(len(vectors))]
    started = time.perf_counter()
    for key, vector in zip(keys, vectors, strict=True):
        cache.put(key, vector, model_id="synthetic", model_revision="1")
    write_ms = _milliseconds(started)
    started = time.perf_counter()
    loaded = [
        cache.get(key, model_id="synthetic", model_revision="1")
        for key in keys
    ]
    read_ms = _milliseconds(started)
    return {
        "backend": "json-files",
        "write_ms": round(write_ms, 3),
        "full_read_ms": round(read_ms, 3),
        "knn_25_ms": None,
        "disk_bytes": _directory_bytes(root),
        "records_recovered": sum(item is not None for item in loaded),
    }


def _sqlite_vec(root: Path, vectors: Sequence[Sequence[float]]) -> dict[str, Any]:
    try:
        import sqlite_vec
    except ImportError as exc:
        raise RuntimeError("install the optional sqlite-vec package") from exc

    root.mkdir(parents=True, exist_ok=True)
    path = root / "vectors.sqlite3"
    connection = sqlite3.connect(path)
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    dimension = len(vectors[0])
    connection.execute(f"create virtual table vectors using vec0(embedding float[{dimension}])")
    started = time.perf_counter()
    connection.executemany(
        "insert into vectors(rowid, embedding) values (?, ?)",
        (
            (index, sqlite_vec.serialize_float32(np.asarray(vector, dtype=np.float32)))
            for index, vector in enumerate(vectors, start=1)
        ),
    )
    connection.commit()
    write_ms = _milliseconds(started)
    started = time.perf_counter()
    recovered = connection.execute("select count(*) from vectors").fetchone()[0]
    connection.execute("select embedding from vectors").fetchall()
    read_ms = _milliseconds(started)
    started = time.perf_counter()
    for vector in vectors[:25]:
        connection.execute(
            "select rowid from vectors where embedding match ? and k = 10 order by distance",
            (sqlite_vec.serialize_float32(np.asarray(vector, dtype=np.float32)),),
        ).fetchall()
    knn_ms = _milliseconds(started)
    version = connection.execute("select vec_version()").fetchone()[0]
    connection.close()
    return {
        "backend": "sqlite-vec",
        "version": version,
        "write_ms": round(write_ms, 3),
        "full_read_ms": round(read_ms, 3),
        "knn_25_ms": round(knn_ms, 3),
        "disk_bytes": path.stat().st_size,
        "records_recovered": recovered,
    }


def run(cache_root: Path, storage_counts: Sequence[int], dimension: int) -> dict[str, Any]:
    cache_root.mkdir(parents=True, exist_ok=True)
    providers = [
        _model2vec(cache_root / "model2vec-model"),
        _fastembed(cache_root / "fastembed-model"),
    ]
    storage: dict[str, list[dict[str, Any]]] = {"json-files": [], "sqlite-vec": []}
    for count in storage_counts:
        vectors = _storage_vectors(count, dimension)
        json_result = _file_cache(cache_root / f"files-{count}", vectors)
        sqlite_result = _sqlite_vec(cache_root / f"sqlite-{count}", vectors)
        for result in (json_result, sqlite_result):
            result["records"] = count
            result["dimension"] = dimension
            storage[result["backend"]].append(result)
    return {
        "benchmark": "embeadings-embedding-storage-alternatives-v1",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "numpy": np.__version__,
            "fastembed": importlib.metadata.version("fastembed"),
            "sqlite_vec": importlib.metadata.version("sqlite-vec"),
        },
        "provider_results": providers,
        "provider_cache_bytes": {
            "model2vec": _directory_bytes(cache_root / "model2vec-model"),
            "fastembed": _directory_bytes(cache_root / "fastembed-model"),
        },
        "storage_results": storage,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--storage-count", type=int, action="append", dest="storage_counts")
    parser.add_argument("--dimension", type=int, default=256)
    args = parser.parse_args()
    counts = args.storage_counts or [1000, 5000]
    if any(count < 2 for count in counts) or args.dimension < 2:
        parser.error("storage counts and dimension must be at least 2")
    if args.cache_root:
        payload = run(args.cache_root, counts, args.dimension)
    else:
        with tempfile.TemporaryDirectory(prefix="embead-alternatives-") as directory:
            payload = run(Path(directory), counts, args.dimension)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
