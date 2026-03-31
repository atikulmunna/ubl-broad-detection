"""
Utilities for the catalog-first retail experiment.

This module is intentionally lightweight so catalog logic can be tested
without importing the full model stack.
"""

from typing import Dict, List

from config.loader import BRAND_NORMS, RETAIL_CATALOG, RETAIL_EXPERIMENT_CONFIG


def get_catalog_brand_entry(brand_key: str) -> Dict:
    brands = RETAIL_CATALOG.get("brands", {})
    return brands.get(brand_key, {})


def is_ubl_brand(brand_key: str, catalog_entry: Dict) -> bool:
    if "is_ubl" in catalog_entry:
        return bool(catalog_entry.get("is_ubl"))

    brand_norm = BRAND_NORMS.get(brand_key, {})
    return brand_norm.get("is_ubl") == "yes"


def candidate_skus_for_brand(brand_key: str, sub_category: str, limit: int) -> List[Dict]:
    catalog_entry = get_catalog_brand_entry(brand_key)
    skus = catalog_entry.get("skus", [])
    active_skus = [sku for sku in skus if sku.get("active", True)]

    if sub_category and sub_category != "unknown":
        filtered = [
            sku for sku in active_skus
            if not sku.get("categories") or sub_category in sku.get("categories", [])
        ]
        if filtered:
            active_skus = filtered

    return active_skus[:limit]


def recognition_level(brand_key: str, candidate_skus: List[Dict], unique_sku_match_limit: int) -> str:
    if not get_catalog_brand_entry(brand_key):
        return "unknown"
    if len(candidate_skus) <= unique_sku_match_limit:
        return "sku_known"
    return "brand_known"


def enrich_brand_detection(brand_key: str, confidence: float, sub_category: str = "unknown") -> Dict:
    """Map a brand detection to catalog-aware output."""
    top_k = RETAIL_EXPERIMENT_CONFIG.get("top_k_skus", 5)
    unique_limit = RETAIL_EXPERIMENT_CONFIG.get("unique_sku_match_limit", 1)

    catalog_entry = get_catalog_brand_entry(brand_key)
    brand_norm = BRAND_NORMS.get(brand_key, {})
    candidate_skus = candidate_skus_for_brand(brand_key, sub_category, top_k)
    level = recognition_level(brand_key, candidate_skus, unique_limit)

    display_name = (
        catalog_entry.get("display_name")
        or brand_norm.get("display_name")
        or brand_key
    )

    return {
        "brand_key": brand_key,
        "brand_display_name": display_name,
        "is_ubl": is_ubl_brand(brand_key, catalog_entry),
        "recognition_level": level,
        "candidate_skus": [
            {
                "product_id": sku.get("product_id"),
                "display_name": sku.get("display_name"),
                "pack_type": sku.get("pack_type", "unknown"),
            }
            for sku in candidate_skus
        ],
        "confidence": round(float(confidence), 4),
        "category_hint": sub_category,
    }
