import sys
import os
from pathlib import Path

import numpy as np

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
    image_path.write_bytes(b"image-bytes")

    embedder = FileContentHashEmbedder(dimension=8)
    ref = _Ref(str(image_path))

    vec1 = embedder.embed_reference(ref)
    vec2 = embedder.embed_query(str(image_path))

    assert np.allclose(vec1, vec2)


def test_file_content_hash_embedder_falls_back_to_string_query_when_file_missing():
    embedder = FileContentHashEmbedder(dimension=8)

    vec = embedder.embed_query("nonexistent-query-token")

    assert vec.shape == (8,)
