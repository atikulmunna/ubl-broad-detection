"""
Catalog indexing primitives for the retail experiment.

This module defines a lightweight, testable interface for:
- discovering catalog reference assets
- generating deterministic embeddings
- building a searchable in-memory index
- returning nearest-neighbor matches with confidence heuristics

The first version uses a simple pluggable embedder interface and a small
NumPy-based index so we can test the contract before introducing a heavier
vision model.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

from utils.retail_catalog import VALIDATED_RETAIL_CATALOG


REFERENCE_ROOT = Path("catalog") / "references"
INDEX_ROOT = Path("catalog") / "index"


@dataclass(frozen=True)
class CatalogReference:
    product_id: str
    brand_key: str
    brand_display_name: str
    is_ubl: bool
    category: str
    pack_type: str
    image_path: str
    source: str


@dataclass(frozen=True)
class CatalogMatch:
    product_id: str
    brand_key: str
    brand_display_name: str
    is_ubl: bool
    category: str
    pack_type: str
    image_path: str
    source: str
    score: float


class CatalogIndexError(ValueError):
    """Raised when catalog indexing inputs are invalid."""


class DeterministicPathEmbedder:
    """
    Cheap deterministic embedder for testing.

    It hashes the provided key into a fixed-size normalized vector so index
    behavior can be exercised without any ML dependency.
    """

    def __init__(self, dimension: int = 16):
        if dimension <= 0:
            raise CatalogIndexError("Embedder dimension must be positive")
        self.dimension = dimension

    def embed_key(self, key: str) -> np.ndarray:
        values = np.zeros(self.dimension, dtype=np.float32)
        encoded = key.encode("utf-8")
        if not encoded:
            encoded = b"\0"
        for index, byte in enumerate(encoded):
            values[index % self.dimension] += (byte + 1) / 255.0

        norm = np.linalg.norm(values)
        if norm == 0:
            return values
        return values / norm

    def embed_reference(self, reference: CatalogReference) -> np.ndarray:
        return self.embed_key(reference.image_path)

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed_key(query)


def discover_reference_images(catalog: Dict = None, reference_root: Path = None) -> List[CatalogReference]:
    catalog_data = catalog or VALIDATED_RETAIL_CATALOG
    root = Path(reference_root) if reference_root else REFERENCE_ROOT
    references: List[CatalogReference] = []

    for brand_key, brand_entry in catalog_data.get("brands", {}).items():
        for sku in brand_entry.get("skus", []):
            category = sku.get("categories", [None])[0]
            explicit_images = sku.get("reference_images", [])

            if explicit_images:
                relative_paths = explicit_images
                source = "catalog"
            else:
                relative_paths = sorted(
                    str(path.relative_to(root))
                    for path in (root / sku["product_id"]).glob("*")
                    if path.is_file()
                )
                source = "filesystem"

            for relative_path in relative_paths:
                full_path = str((root / relative_path).resolve()) if not Path(relative_path).is_absolute() else relative_path
                references.append(CatalogReference(
                    product_id=sku["product_id"],
                    brand_key=brand_key,
                    brand_display_name=brand_entry.get("display_name", brand_key),
                    is_ubl=bool(brand_entry.get("is_ubl", False)),
                    category=category or "unknown",
                    pack_type=sku.get("pack_type", "unknown"),
                    image_path=full_path,
                    source=source,
                ))

    return references


def audit_catalog_references(catalog: Dict = None, reference_root: Path = None) -> Dict:
    """
    Report which SKUs are ready for indexing and which still lack references.

    A SKU is considered ready if either:
    - it declares one or more `reference_images`, or
    - files exist under `catalog/references/<product_id>/`
    """
    catalog_data = catalog or VALIDATED_RETAIL_CATALOG
    root = Path(reference_root) if reference_root else REFERENCE_ROOT

    ready = []
    missing = []

    for brand_key, brand_entry in catalog_data.get("brands", {}).items():
        for sku in brand_entry.get("skus", []):
            explicit_images = sku.get("reference_images", [])
            filesystem_images = sorted(
                str(path.relative_to(root))
                for path in (root / sku["product_id"]).glob("*")
                if path.is_file()
            )

            record = {
                "brand_key": brand_key,
                "brand_display_name": brand_entry.get("display_name", brand_key),
                "product_id": sku["product_id"],
                "display_name": sku.get("display_name", sku["product_id"]),
                "explicit_reference_count": len(explicit_images),
                "filesystem_reference_count": len(filesystem_images),
                "reference_count": len(explicit_images) or len(filesystem_images),
            }

            if explicit_images or filesystem_images:
                ready.append(record)
            else:
                missing.append(record)

    return {
        "ready": ready,
        "missing": missing,
        "summary": {
            "ready_count": len(ready),
            "missing_count": len(missing),
            "total_skus": len(ready) + len(missing),
        },
    }


def build_onboarding_report(catalog: Dict = None, reference_root: Path = None) -> Dict:
    """
    Build a machine-readable onboarding report for catalog reference assets.
    """
    audit = audit_catalog_references(catalog=catalog, reference_root=reference_root)
    missing_by_brand = {}

    for item in audit["missing"]:
        brand_key = item["brand_key"]
        missing_by_brand.setdefault(brand_key, {
            "brand_display_name": item["brand_display_name"],
            "skus": [],
        })
        missing_by_brand[brand_key]["skus"].append({
            "product_id": item["product_id"],
            "display_name": item["display_name"],
            "expected_reference_dir": str((Path(reference_root) if reference_root else REFERENCE_ROOT) / item["product_id"]),
        })

    return {
        "summary": audit["summary"],
        "missing_by_brand": missing_by_brand,
        "ready": audit["ready"],
    }


class InMemoryCatalogIndex:
    """Tiny cosine-similarity index for catalog references."""

    def __init__(self, references: Sequence[CatalogReference], embeddings: np.ndarray):
        self.references = list(references)
        self.embeddings = np.asarray(embeddings, dtype=np.float32)

        if len(self.references) != len(self.embeddings):
            raise CatalogIndexError("Reference count must match embedding count")

        if self.embeddings.ndim != 2:
            raise CatalogIndexError("Embeddings must be a 2D array")

    @property
    def size(self) -> int:
        return len(self.references)

    @property
    def dimension(self) -> int:
        return int(self.embeddings.shape[1]) if self.embeddings.size else 0

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[CatalogMatch]:
        if self.size == 0:
            return []
        if top_k <= 0:
            raise CatalogIndexError("top_k must be positive")

        query = np.asarray(query_embedding, dtype=np.float32)
        if query.ndim != 1 or query.shape[0] != self.dimension:
            raise CatalogIndexError("Query embedding dimension mismatch")

        scores = self.embeddings @ query
        top_indices = np.argsort(scores)[::-1][:top_k]

        matches = []
        for index in top_indices:
            reference = self.references[int(index)]
            matches.append(CatalogMatch(
                product_id=reference.product_id,
                brand_key=reference.brand_key,
                brand_display_name=reference.brand_display_name,
                is_ubl=reference.is_ubl,
                category=reference.category,
                pack_type=reference.pack_type,
                image_path=reference.image_path,
                source=reference.source,
                score=float(scores[int(index)]),
            ))
        return matches

    def save(self, output_dir: Path) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        embeddings_path = output_path / "embeddings.npy"
        manifest_path = output_path / "manifest.json"

        np.save(embeddings_path, self.embeddings)
        manifest = {
            "size": self.size,
            "dimension": self.dimension,
            "references": [asdict(reference) for reference in self.references],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return {
            "embeddings_path": str(embeddings_path),
            "manifest_path": str(manifest_path),
        }

    @classmethod
    def load(cls, input_dir: Path) -> "InMemoryCatalogIndex":
        input_path = Path(input_dir)
        embeddings_path = input_path / "embeddings.npy"
        manifest_path = input_path / "manifest.json"

        if not embeddings_path.exists() or not manifest_path.exists():
            raise CatalogIndexError(f"Index files not found in {input_path}")

        embeddings = np.load(embeddings_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        references = [CatalogReference(**item) for item in manifest.get("references", [])]
        return cls(references, embeddings)


def build_catalog_index(embedder: DeterministicPathEmbedder = None, catalog: Dict = None,
                        reference_root: Path = None) -> InMemoryCatalogIndex:
    embedder = embedder or DeterministicPathEmbedder()
    references = discover_reference_images(catalog=catalog, reference_root=reference_root)
    if not references:
        return InMemoryCatalogIndex([], np.zeros((0, embedder.dimension), dtype=np.float32))

    embeddings = np.vstack([embedder.embed_reference(reference) for reference in references])
    return InMemoryCatalogIndex(references, embeddings)


def load_catalog_index(index_root: Path = None) -> InMemoryCatalogIndex:
    root = Path(index_root) if index_root else INDEX_ROOT
    return InMemoryCatalogIndex.load(root)


def summarize_matches(matches: Sequence[CatalogMatch], sku_score_threshold: float = 0.92,
                      brand_score_threshold: float = 0.80) -> Dict:
    if not matches:
        return {
            "recognition_level": "unknown",
            "brand_key": "unknown",
            "product_id": None,
            "score": 0.0,
        }

    best = matches[0]
    if best.score >= sku_score_threshold:
        level = "sku_known"
    elif best.score >= brand_score_threshold:
        level = "brand_known"
    else:
        level = "unknown"

    return {
        "recognition_level": level,
        "brand_key": best.brand_key if level != "unknown" else "unknown",
        "product_id": best.product_id if level == "sku_known" else None,
        "score": round(float(best.score), 4),
    }
