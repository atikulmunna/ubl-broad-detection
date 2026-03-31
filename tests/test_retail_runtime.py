import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.retail_embedding import create_embedder
from utils.retail_index import build_catalog_index
from utils.retail_runtime import get_runtime_index_components, reset_runtime_index_cache


class _FakeIndex:
    def __init__(self, size=2, dimension=8):
        self.size = size
        self.dimension = dimension


class _FakeEmbedder:
    def __init__(self, embedder_type="deterministic_path", dimension=16):
        self.embedder_type = embedder_type
        self.dimension = dimension


def test_runtime_index_components_can_load_saved_index():
    reset_runtime_index_cache()

    def fake_loader(path):
        assert path.as_posix().endswith("catalog/index")
        return _FakeIndex(size=3, dimension=12)

    index, embedder, status = get_runtime_index_components(
        {"use_saved_index": True, "index_dir": "catalog/index", "embedder_type": "deterministic_path"},
        index_loader=fake_loader,
        embedder_factory=_FakeEmbedder,
    )

    assert index.size == 3
    assert embedder.dimension == 12
    assert embedder.embedder_type == "deterministic_path"
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
        {"use_saved_index": True, "index_dir": "catalog/missing", "embedder_type": "deterministic_path"},
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

    config = {"use_saved_index": True, "index_dir": "catalog/index", "embedder_type": "deterministic_path"}
    first = get_runtime_index_components(config, index_loader=fake_loader, embedder_factory=_FakeEmbedder)
    second = get_runtime_index_components(config, index_loader=fake_loader, embedder_factory=_FakeEmbedder)

    assert calls["count"] == 1
    assert first[2]["index_status"] == "loaded"
    assert second[2]["index_status"] == "loaded"


def test_runtime_index_components_can_load_real_saved_index(tmp_path: Path):
    reset_runtime_index_cache()
    catalog = {
        "brands": {
            "dove": {
                "display_name": "Dove",
                "is_ubl": True,
                "categories": ["hair_care"],
                "skus": [
                    {
                        "product_id": "dove-hfr-small",
                        "display_name": "Dove Hair Fall Rescue Small",
                        "reference_images": ["dove-hfr-small/front.png"],
                    }
                ],
            },
            "unknown": {
                "display_name": "Unknown",
                "is_ubl": False,
                "categories": [],
                "skus": [],
            },
        }
    }

    embedder = create_embedder("deterministic_path", dimension=8)
    index = build_catalog_index(embedder=embedder, catalog=catalog, reference_root=tmp_path)
    output_dir = tmp_path / "index"
    index.save(output_dir)

    index_obj, embedder_obj, status = get_runtime_index_components(
        {"use_saved_index": True, "index_dir": str(output_dir), "embedder_type": "deterministic_path"},
    )

    assert index_obj.size == 1
    assert embedder_obj.dimension == index_obj.dimension
    assert status["index_used"] is True
    assert status["index_status"] == "loaded"
