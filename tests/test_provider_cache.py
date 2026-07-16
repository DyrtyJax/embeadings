import json
import os
import stat

import pytest

from embead.cache import VectorCache
from embead.provider import HashingProvider


class CountingProvider(HashingProvider):
    def __init__(self) -> None:
        super().__init__(dimension=16)
        self.encoded: list[list[str]] = []

    def encode(self, texts):
        self.encoded.append(list(texts))
        return super().encode(texts)


def test_hashing_provider_is_deterministic_and_normalized() -> None:
    provider = HashingProvider(dimension=16)
    first, second = provider.encode(["alpha beta", "alpha beta"])

    assert first == second
    assert sum(value * value for value in first) == pytest.approx(1)


def test_cache_reuses_vectors_and_only_computes_misses(tmp_path) -> None:
    cache = VectorCache(tmp_path)
    provider = CountingProvider()

    first = cache.encode(["alpha", "beta"], provider)
    second = cache.encode(["alpha", "beta", "gamma"], provider)

    assert second[:2] == first
    assert provider.encoded == [["alpha", "beta"], ["gamma"]]


def test_cache_computes_duplicate_content_once(tmp_path) -> None:
    cache = VectorCache(tmp_path)
    provider = CountingProvider()

    vectors = cache.encode(["same", "same"], provider)

    assert vectors[0] == vectors[1]
    assert provider.encoded == [["same"]]


def test_cache_key_changes_with_content_contract(tmp_path) -> None:
    cache = VectorCache(tmp_path)
    base = dict(model_id="model", model_revision="rev")

    assert cache.key_for("one", **base) != cache.key_for("two", **base)
    assert cache.key_for("one", **base) != cache.key_for(
        "one", **base, canonicalization_version="2"
    )


def test_corrupt_and_non_finite_entries_are_misses(tmp_path) -> None:
    cache = VectorCache(tmp_path)
    key = cache.key_for("one", model_id="model", model_revision="rev")
    path = tmp_path / key[:2] / f"{key}.json"
    path.parent.mkdir()
    path.write_text("not json")
    assert cache.get(key) is None

    payload = {
        "cache_version": 1,
        "key": key,
        "model_id": "model",
        "model_revision": "rev",
        "dimension": 2,
        "vector": [float("nan"), 0],
    }
    path.write_text(json.dumps(payload))
    assert cache.get(key) is None


def test_put_is_atomic_and_normalizes(tmp_path) -> None:
    cache = VectorCache(tmp_path)
    key = cache.key_for("one", model_id="model", model_revision="rev")
    cache.put(key, [3, 4], model_id="model", model_revision="rev")

    assert cache.get(key, dimension=2) == pytest.approx([0.6, 0.8])
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits are not portable")
def test_cache_restricts_directories_entries_and_lock_on_posix(tmp_path) -> None:
    root = tmp_path / "cache"
    root.mkdir(mode=0o755)
    cache = VectorCache(root)
    key = cache.key_for("one", model_id="model", model_revision="rev")

    cache.put(key, [3, 4], model_id="model", model_revision="rev")
    cache.get(key)

    entry = root / key[:2] / f"{key}.json"

    def mode(path):
        return stat.S_IMODE(path.stat().st_mode)

    assert mode(root) == 0o700
    assert mode(entry.parent) == 0o700
    assert mode(entry) == 0o600
    assert mode(root / ".cache.lock") == 0o600
