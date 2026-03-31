import sys
import os
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.retail_index import (
    CatalogIndexError,
    DeterministicPathEmbedder,
    audit_catalog_references,
    build_onboarding_report,
    build_catalog_index,
    discover_reference_images,
    load_catalog_index,
    summarize_matches,
)


def _catalog_with_explicit_refs():
    return {
        "brands": {
            "dove": {
                "display_name": "Dove",
                "is_ubl": True,
                "categories": ["hair_care"],
                "skus": [
                    {
                        "product_id": "dove-hfr-small",
                        "display_name": "Dove Hair Fall Rescue Small",
                        "categories": ["hair_care"],
                        "pack_type": "bottle",
                        "reference_images": [
                            "dove-hfr-small/front.jpg",
                            "dove-hfr-small/angle.jpg",
                        ],
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


def test_discover_reference_images_uses_explicit_catalog_paths(tmp_path: Path):
    refs = discover_reference_images(
        catalog=_catalog_with_explicit_refs(),
        reference_root=tmp_path,
    )

    assert len(refs) == 2
    assert refs[0].product_id == "dove-hfr-small"
    assert refs[0].brand_key == "dove"
    assert refs[0].source == "catalog"
    assert refs[0].image_path.endswith(str(Path("dove-hfr-small") / "front.jpg"))


def test_discover_reference_images_can_scan_filesystem(tmp_path: Path):
    product_dir = tmp_path / "dove-hfr-small"
    product_dir.mkdir()
    (product_dir / "front.jpg").write_text("front")
    (product_dir / "side.png").write_text("side")

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
                        "categories": ["hair_care"],
                        "pack_type": "bottle",
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

    refs = discover_reference_images(catalog=catalog, reference_root=tmp_path)

    assert len(refs) == 2
    assert all(ref.source == "filesystem" for ref in refs)


def test_build_catalog_index_and_search_returns_best_match(tmp_path: Path):
    embedder = DeterministicPathEmbedder(dimension=8)
    catalog = _catalog_with_explicit_refs()
    index = build_catalog_index(embedder=embedder, catalog=catalog, reference_root=tmp_path)

    query = embedder.embed_query(str((tmp_path / "dove-hfr-small" / "front.jpg").resolve()))
    matches = index.search(query, top_k=1)

    assert index.size == 2
    assert matches[0].product_id == "dove-hfr-small"
    assert matches[0].brand_key == "dove"


def test_search_rejects_dimension_mismatch(tmp_path: Path):
    embedder = DeterministicPathEmbedder(dimension=8)
    index = build_catalog_index(embedder=embedder, catalog=_catalog_with_explicit_refs(), reference_root=tmp_path)

    bad_query = np.zeros(3, dtype=np.float32)
    try:
        index.search(bad_query, top_k=1)
    except CatalogIndexError as exc:
        assert "dimension mismatch" in str(exc)
    else:
        raise AssertionError("Expected CatalogIndexError for bad query dimension")


def test_summarize_matches_returns_expected_recognition_levels(tmp_path: Path):
    embedder = DeterministicPathEmbedder(dimension=8)
    index = build_catalog_index(embedder=embedder, catalog=_catalog_with_explicit_refs(), reference_root=tmp_path)

    strong_query = embedder.embed_query(str((tmp_path / "dove-hfr-small" / "front.jpg").resolve()))
    strong_match = index.search(strong_query, top_k=1)
    strong_summary = summarize_matches(strong_match, sku_score_threshold=0.95, brand_score_threshold=0.70)

    weak_query = embedder.embed_query("completely-different-product")
    weak_match = index.search(weak_query, top_k=1)
    weak_summary = summarize_matches(weak_match, sku_score_threshold=0.999, brand_score_threshold=0.999)

    assert strong_summary["recognition_level"] == "sku_known"
    assert strong_summary["product_id"] == "dove-hfr-small"
    assert weak_summary["recognition_level"] == "unknown"


def test_catalog_index_can_be_saved_and_loaded(tmp_path: Path):
    embedder = DeterministicPathEmbedder(dimension=8)
    index = build_catalog_index(embedder=embedder, catalog=_catalog_with_explicit_refs(), reference_root=tmp_path)

    output_dir = tmp_path / "index"
    saved = index.save(output_dir)
    loaded = load_catalog_index(output_dir)

    assert Path(saved["manifest_path"]).exists()
    assert Path(saved["embeddings_path"]).exists()
    assert loaded.size == index.size
    assert loaded.dimension == index.dimension

    query = embedder.embed_query(str((tmp_path / "dove-hfr-small" / "front.jpg").resolve()))
    matches = loaded.search(query, top_k=1)
    assert matches[0].product_id == "dove-hfr-small"


def test_audit_catalog_references_reports_ready_and_missing(tmp_path: Path):
    (tmp_path / "dove-hfr-small").mkdir()
    (tmp_path / "dove-hfr-small" / "front.jpg").write_text("front")

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
                        "categories": ["hair_care"],
                        "pack_type": "bottle",
                    },
                    {
                        "product_id": "dove-missing",
                        "display_name": "Dove Missing",
                        "categories": ["hair_care"],
                        "pack_type": "bottle",
                    },
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

    audit = audit_catalog_references(catalog=catalog, reference_root=tmp_path)

    assert audit["summary"]["ready_count"] == 1
    assert audit["summary"]["missing_count"] == 1
    assert audit["ready"][0]["product_id"] == "dove-hfr-small"
    assert audit["missing"][0]["product_id"] == "dove-missing"


def test_build_onboarding_report_groups_missing_skus_by_brand(tmp_path: Path):
    catalog = {
        "brands": {
            "dove": {
                "display_name": "Dove",
                "is_ubl": True,
                "categories": ["hair_care"],
                "skus": [
                    {"product_id": "dove-ready", "display_name": "Dove Ready", "reference_images": ["dove-ready/front.jpg"]},
                    {"product_id": "dove-missing", "display_name": "Dove Missing"},
                ],
            },
            "nivea": {
                "display_name": "Nivea",
                "is_ubl": False,
                "categories": ["skin_care"],
                "skus": [
                    {"product_id": "nivea-missing", "display_name": "Nivea Missing"},
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

    report = build_onboarding_report(catalog=catalog, reference_root=tmp_path)

    assert report["summary"]["total_skus"] == 3
    assert report["summary"]["missing_count"] == 2
    assert "dove" in report["missing_by_brand"]
    assert "nivea" in report["missing_by_brand"]
    assert report["missing_by_brand"]["dove"]["skus"][0]["product_id"] == "dove-missing"
