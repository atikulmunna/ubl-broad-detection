import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.retail_catalog import enrich_brand_detection


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
