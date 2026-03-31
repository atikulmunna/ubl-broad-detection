import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.retail_runtime import get_runtime_index_components, reset_runtime_index_cache


class _FakeIndex:
    def __init__(self, size=2, dimension=8):
        self.size = size
        self.dimension = dimension


class _FakeEmbedder:
    def __init__(self, dimension=16):
        self.dimension = dimension


def test_runtime_index_components_can_load_saved_index():
    reset_runtime_index_cache()

    def fake_loader(path):
        assert path.as_posix().endswith("catalog/index")
        return _FakeIndex(size=3, dimension=12)

    index, embedder, status = get_runtime_index_components(
        {"use_saved_index": True, "index_dir": "catalog/index"},
        index_loader=fake_loader,
        embedder_factory=_FakeEmbedder,
    )

    assert index.size == 3
    assert embedder.dimension == 12
    assert status["index_used"] is True
    assert status["index_status"] == "loaded"


def test_runtime_index_components_respect_disabled_setting():
    reset_runtime_index_cache()

    index, embedder, status = get_runtime_index_components(
        {"use_saved_index": False, "index_dir": "catalog/index"},
    )

    assert index is None
    assert embedder is None
    assert status["index_status"] == "disabled"


def test_runtime_index_components_fall_back_when_loader_fails():
    reset_runtime_index_cache()

    def failing_loader(path: Path):
        raise FileNotFoundError(str(path))

    index, embedder, status = get_runtime_index_components(
        {"use_saved_index": True, "index_dir": "catalog/missing"},
        index_loader=failing_loader,
        embedder_factory=_FakeEmbedder,
    )

    assert index is None
    assert embedder is None
    assert status["index_used"] is False
    assert status["index_status"] == "unavailable"


def test_runtime_index_components_cache_results():
    reset_runtime_index_cache()
    calls = {"count": 0}

    def fake_loader(path):
        calls["count"] += 1
        return _FakeIndex(size=1, dimension=4)

    config = {"use_saved_index": True, "index_dir": "catalog/index"}
    first = get_runtime_index_components(config, index_loader=fake_loader, embedder_factory=_FakeEmbedder)
    second = get_runtime_index_components(config, index_loader=fake_loader, embedder_factory=_FakeEmbedder)

    assert calls["count"] == 1
    assert first[2]["index_status"] == "loaded"
    assert second[2]["index_status"] == "loaded"
