import sys
import os
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.retail_embedding import (
    DeterministicPathEmbedder,
    FileContentHashEmbedder,
    create_embedder,
)


class _Ref:
    def __init__(self, image_path: str):
        self.image_path = image_path


def test_create_embedder_supports_both_known_types():
    det = create_embedder("deterministic_path", dimension=8)
    content = create_embedder("file_content_hash", dimension=8)

    assert isinstance(det, DeterministicPathEmbedder)
    assert isinstance(content, FileContentHashEmbedder)


def test_deterministic_path_embedder_is_stable():
    embedder = DeterministicPathEmbedder(dimension=8)

    vec1 = embedder.embed_query("catalog/references/demo/front.png")
    vec2 = embedder.embed_query("catalog/references/demo/front.png")

    assert np.allclose(vec1, vec2)


def test_file_content_hash_embedder_uses_file_contents(tmp_path: Path):
    image_path = tmp_path / "front.png"
    Image.new("RGB", (16, 16), (10, 200, 10)).save(image_path)

    embedder = FileContentHashEmbedder(dimension=8)
    ref = _Ref(str(image_path))

    vec1 = embedder.embed_reference(ref)
    vec2 = embedder.embed_query(str(image_path))

    assert np.allclose(vec1, vec2)


def test_file_content_hash_embedder_matches_reencoded_same_pixels(tmp_path: Path):
    ref_path = tmp_path / "reference.png"
    query_path = tmp_path / "query.png"

    Image.new("RGB", (16, 16), (20, 120, 220)).save(ref_path)
    with Image.open(ref_path) as image:
        image.convert("RGB").save(query_path)

    embedder = FileContentHashEmbedder(dimension=8)
    ref_vec = embedder.embed_reference(_Ref(str(ref_path)))
    query_vec = embedder.embed_query(str(query_path))

    assert np.allclose(ref_vec, query_vec)


def test_file_content_hash_embedder_falls_back_to_string_query_when_file_missing():
    embedder = FileContentHashEmbedder(dimension=8)

    vec = embedder.embed_query("nonexistent-query-token")

    assert vec.shape == (8,)


def test_embedder_can_embed_query_asset():
    embedder = DeterministicPathEmbedder(dimension=8)

    vec = embedder.embed_query_asset({
        "image_path": "catalog/references/demo/front.png",
        "fallback_token": "dove",
    })

    assert vec.shape == (8,)
