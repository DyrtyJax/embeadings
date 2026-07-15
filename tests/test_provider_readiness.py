import pytest

from embead.provider import provider_readiness


class ListProvider:
    model_id = "public/test"
    model_revision = "revision"

    def encode(self, texts):
        assert texts == ["safe probe"]
        return [[1.0, 0.0, 0.0]]


def test_provider_readiness_accepts_list_vectors() -> None:
    assert provider_readiness(ListProvider(), probe_text="safe probe") == {
        "status": "ready",
        "model_id": "public/test",
        "model_revision": "revision",
        "vector_dimension": 3,
    }


class BrokenProvider(ListProvider):
    def encode(self, texts):
        return []


def test_provider_readiness_rejects_missing_vector() -> None:
    with pytest.raises(ValueError, match="wrong number"):
        provider_readiness(BrokenProvider())
