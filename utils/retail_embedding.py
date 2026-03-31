"""
Embedding abstractions for the retail experiment.

This module separates embedding generation from index and runtime logic so
we can upgrade the feature extractor later without rewriting the catalog,
index, or matching layers.
"""

import hashlib
from pathlib import Path
from typing import Protocol

import numpy as np


class RetailEmbedder(Protocol):
    dimension: int

    def embed_reference(self, reference) -> np.ndarray:
        ...

    def embed_query(self, query: str) -> np.ndarray:
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
            values[index % self.dimension] += (byte + 1) / 255.0
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

    def _digest_bytes(self, payload: bytes) -> bytes:
        return hashlib.sha256(payload).digest()

    def embed_reference(self, reference) -> np.ndarray:
        payload = self._read_file_bytes(reference.image_path)
        return self._vector_from_bytes(self._digest_bytes(payload))

    def embed_query(self, query: str) -> np.ndarray:
        path = Path(query)
        if path.exists():
            payload = self._read_file_bytes(query)
        else:
            payload = query.encode("utf-8")
        return self._vector_from_bytes(self._digest_bytes(payload))


def create_embedder(embedder_type: str = "deterministic_path", dimension: int = 16):
    if embedder_type == "deterministic_path":
        return DeterministicPathEmbedder(dimension=dimension)
    if embedder_type == "file_content_hash":
        return FileContentHashEmbedder(dimension=dimension)
    raise ValueError(f"Unknown embedder_type: {embedder_type}")
