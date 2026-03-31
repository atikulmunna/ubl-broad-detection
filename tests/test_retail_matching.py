import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.retail_index import DeterministicPathEmbedder, build_catalog_index
from utils.retail_matching import resolve_detection_with_catalog, summarize_resolved_instances


def _catalog():
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
                        "reference_images": ["dove-hfr-small/front.jpg"],
                    }
                ],
            },
            "nivea": {
                "display_name": "Nivea",
                "is_ubl": False,
                "categories": ["skin_care"],
                "skus": [
                    {
                        "product_id": "nivea-cream",
                        "display_name": "Nivea Cream",
                        "categories": ["skin_care"],
                        "pack_type": "jar",
                        "reference_images": ["nivea-cream/front.jpg"],
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


def test_resolve_detection_falls_back_to_brand_enrichment_without_index():
    resolved = resolve_detection_with_catalog(
        detection={"brand": "dove", "confidence": 0.84, "bbox_xyxy": [1, 2, 3, 4]},
        sub_category="hair_care",
        catalog=_catalog(),
    )

    assert resolved["brand_key"] == "dove"
    assert resolved["recognition_level"] == "sku_known"
    assert resolved["bbox_xyxy"] == [1, 2, 3, 4]
    assert resolved["detected_brand"] == "dove"


def test_resolve_detection_uses_catalog_index_when_query_is_available(tmp_path):
    embedder = DeterministicPathEmbedder(dimension=8)
    index = build_catalog_index(embedder=embedder, catalog=_catalog(), reference_root=tmp_path)

    resolved = resolve_detection_with_catalog(
        detection={
            "brand": "unknown",
            "confidence": 0.20,
            "catalog_query": str((tmp_path / "dove-hfr-small" / "front.jpg").resolve()),
        },
        sub_category="hair_care",
        index=index,
        embedder=embedder,
        catalog=_catalog(),
    )

    assert resolved["brand_key"] == "dove"
    assert resolved["recognition_level"] == "sku_known"
    assert resolved["matched_product_id"] == "dove-hfr-small"


def test_resolve_detection_falls_back_when_index_match_is_weak(tmp_path):
    embedder = DeterministicPathEmbedder(dimension=8)
    index = build_catalog_index(embedder=embedder, catalog=_catalog(), reference_root=tmp_path)

    resolved = resolve_detection_with_catalog(
        detection={
            "brand": "nivea",
            "confidence": 0.91,
            "catalog_query": "completely-different-product",
        },
        sub_category="skin_care",
        index=index,
        embedder=embedder,
        catalog=_catalog(),
    )

    assert resolved["brand_key"] == "nivea"
    assert resolved["detected_brand"] == "nivea"


def test_summarize_resolved_instances_counts_known_and_unknown():
    summary = summarize_resolved_instances([
        {"brand_display_name": "Dove", "is_ubl": True, "recognition_level": "sku_known"},
        {"brand_display_name": "Nivea", "is_ubl": False, "recognition_level": "brand_known"},
        {"brand_display_name": "Unknown", "is_ubl": False, "recognition_level": "unknown"},
    ])

    assert summary["ubl_count"] == 1
    assert summary["competitor_count"] == 1
    assert summary["unknown_count"] == 1
    assert summary["brand_breakdown"]["Dove"] == 1
