"""
Embedding abstractions for the retail experiment.

This module separates embedding generation from index and runtime logic so
we can upgrade the feature extractor later without rewriting the catalog,
index, or matching layers.
"""

import hashlib
import io
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image


class RetailEmbedder(Protocol):
    dimension: int

    def embed_reference(self, reference) -> np.ndarray:
        ...

    def embed_query(self, query: str) -> np.ndarray:
        ...

    def embed_query_asset(self, query_asset: dict) -> np.ndarray:
        ...


class _BaseHashEmbedder:
    def __init__(self, dimension: int = 16):
        if dimension <= 0:
            raise ValueError("Embedder dimension must be positive")
        self.dimension = dimension

    def _vector_from_bytes(self, payload: bytes) -> np.ndarray:
        values = np.zeros(self.dimension, dtype=np.float32)
        if not payload:
            payload = b"\0"
        for index, byte in enumerate(payload):
            values[index % self.dimension] += (byte - 127.5) / 127.5
        norm = np.linalg.norm(values)
        if norm == 0:
            return values
        return values / norm


class DeterministicPathEmbedder(_BaseHashEmbedder):
    """
    Cheap deterministic embedder for testing.

    It hashes the provided path/key into a fixed-size normalized vector so
    index behavior can be exercised without any ML dependency.
    """

    def embed_key(self, key: str) -> np.ndarray:
        return self._vector_from_bytes(key.encode("utf-8"))

    def embed_reference(self, reference) -> np.ndarray:
        return self.embed_key(reference.image_path)

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed_key(query)

    def embed_query_asset(self, query_asset: dict) -> np.ndarray:
        query_value = query_asset.get("image_path") or query_asset.get("fallback_token") or ""
        return self.embed_query(query_value)


class FileContentHashEmbedder(_BaseHashEmbedder):
    """
    Content-based embedder using image bytes.

    This is still lightweight and non-ML, but it behaves more like a real
    image feature extractor because it depends on file contents rather than
    only the file path.
    """

    def _read_file_bytes(self, path_value: str) -> bytes:
        path = Path(path_value)
        return path.read_bytes()

    def _read_normalized_image_bytes(self, path_value: str) -> bytes:
        with Image.open(path_value) as image:
            normalized = image.convert("RGB")
            size_payload = f"{normalized.width}x{normalized.height}".encode("utf-8")
            return size_payload + b"|" + normalized.tobytes()

    def _digest_bytes(self, payload: bytes) -> bytes:
        return hashlib.sha256(payload).digest()

    def embed_reference(self, reference) -> np.ndarray:
        try:
            payload = self._read_normalized_image_bytes(reference.image_path)
        except Exception:
            payload = self._read_file_bytes(reference.image_path)
        return self._vector_from_bytes(self._digest_bytes(payload))

    def embed_query(self, query: str) -> np.ndarray:
        path = Path(query)
        if path.exists():
            try:
                payload = self._read_normalized_image_bytes(query)
            except Exception:
                payload = self._read_file_bytes(query)
        else:
            payload = query.encode("utf-8")
        return self._vector_from_bytes(self._digest_bytes(payload))

    def embed_query_asset(self, query_asset: dict) -> np.ndarray:
        image_path = query_asset.get("image_path", "")
        fallback_token = query_asset.get("fallback_token", "")
        if image_path:
            return self.embed_query(image_path)
        return self.embed_query(fallback_token)


def create_embedder(embedder_type: str = "deterministic_path", dimension: int = 16):
    if embedder_type == "deterministic_path":
        return DeterministicPathEmbedder(dimension=dimension)
    if embedder_type == "file_content_hash":
        return FileContentHashEmbedder(dimension=dimension)
    raise ValueError(f"Unknown embedder_type: {embedder_type}")
