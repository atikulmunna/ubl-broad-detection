import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from utils.retail_catalog import (
    CatalogValidationError,
    candidate_skus_for_brand,
    enrich_brand_detection,
    validate_catalog,
)


def test_enrich_brand_detection_returns_brand_known_for_multi_sku_brand():
    result = enrich_brand_detection("dove", confidence=0.88, sub_category="hair_care")

    assert result["brand_key"] == "dove"
    assert result["brand_display_name"] == "Dove"
    assert result["is_ubl"] is True
    assert result["recognition_level"] == "brand_known"
    assert len(result["candidate_skus"]) >= 2


def test_enrich_brand_detection_returns_sku_known_for_single_candidate_brand():
    result = enrich_brand_detection("colgate", confidence=0.77, sub_category="oral_care")

    assert result["brand_key"] == "colgate"
    assert result["is_ubl"] is False
    assert result["recognition_level"] == "sku_known"
    assert len(result["candidate_skus"]) == 1


def test_enrich_brand_detection_flags_unknown_brand():
    result = enrich_brand_detection("brand_not_in_catalog", confidence=0.42, sub_category="unknown")

    assert result["brand_key"] == "brand_not_in_catalog"
    assert result["recognition_level"] == "unknown"
    assert result["candidate_skus"] == []


def test_candidate_skus_respects_category_filter():
    skus = candidate_skus_for_brand("dove", sub_category="skin_care", limit=10)

    assert len(skus) == 1
    assert skus[0]["product_id"] == "dove-natural-radiance-lotion"


def test_validate_catalog_normalizes_optional_fields():
    catalog = {
        "brands": {
            "demo": {
                "display_name": "Demo",
                "is_ubl": True,
                "categories": ["hair_care"],
                "skus": [
                    {
                        "product_id": "demo-1",
                        "display_name": "Demo 1",
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

    normalized = validate_catalog(catalog)

    assert normalized["brands"]["demo"]["skus"][0]["categories"] == ["hair_care"]
    assert normalized["brands"]["demo"]["skus"][0]["aliases"] == []
    assert normalized["brands"]["demo"]["skus"][0]["reference_images"] == []
    assert normalized["brands"]["demo"]["skus"][0]["active"] is True


def test_validate_catalog_rejects_duplicate_product_ids():
    catalog = {
        "brands": {
            "brand_a": {
                "display_name": "Brand A",
                "is_ubl": True,
                "categories": [],
                "skus": [{"product_id": "dup-1"}],
            },
            "brand_b": {
                "display_name": "Brand B",
                "is_ubl": False,
                "categories": [],
                "skus": [{"product_id": "dup-1"}],
            },
            "unknown": {
                "display_name": "Unknown",
                "is_ubl": False,
                "categories": [],
                "skus": [],
            },
        }
    }

    with pytest.raises(CatalogValidationError, match="Duplicate product_id"):
        validate_catalog(catalog)


def test_validate_catalog_requires_unknown_brand():
    catalog = {
        "brands": {
            "demo": {
                "display_name": "Demo",
                "is_ubl": True,
                "categories": [],
                "skus": [{"product_id": "demo-1"}],
            }
        }
    }

    with pytest.raises(CatalogValidationError, match="must include an 'unknown'"):
        validate_catalog(catalog)
