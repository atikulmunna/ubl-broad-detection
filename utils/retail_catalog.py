"""
Utilities for the catalog-first retail experiment.

This module is intentionally lightweight so catalog logic can be tested
without importing the full model stack.
"""

from typing import Dict, List

from config.loader import BRAND_NORMS, RETAIL_CATALOG, RETAIL_EXPERIMENT_CONFIG


class CatalogValidationError(ValueError):
    """Raised when the retail catalog is structurally invalid."""


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    raise CatalogValidationError(f"Expected list value, received {type(value).__name__}")


def _normalize_brand_entry(brand_key: str, brand_entry: Dict) -> Dict:
    if not isinstance(brand_entry, dict):
        raise CatalogValidationError(f"Brand '{brand_key}' must map to an object")

    display_name = brand_entry.get("display_name") or brand_key
    categories = _as_list(brand_entry.get("categories", []))
    skus = brand_entry.get("skus", [])
    if not isinstance(skus, list):
        raise CatalogValidationError(f"Brand '{brand_key}' skus must be a list")

    normalized_skus = []
    for index, sku in enumerate(skus):
        if not isinstance(sku, dict):
            raise CatalogValidationError(f"Brand '{brand_key}' sku at index {index} must be an object")

        product_id = sku.get("product_id")
        if not product_id:
            raise CatalogValidationError(f"Brand '{brand_key}' sku at index {index} is missing product_id")

        normalized_skus.append({
            "product_id": str(product_id),
            "display_name": sku.get("display_name") or str(product_id),
            "categories": _as_list(sku.get("categories", categories)),
            "pack_type": sku.get("pack_type", "unknown"),
            "active": bool(sku.get("active", True)),
            "aliases": _as_list(sku.get("aliases", [])),
            "reference_images": _as_list(sku.get("reference_images", [])),
        })

    return {
        "display_name": display_name,
        "is_ubl": bool(brand_entry.get("is_ubl", False)),
        "categories": categories,
        "skus": normalized_skus,
    }


def normalize_catalog(catalog: Dict) -> Dict:
    """Normalize catalog structure into a predictable shape."""
    if not isinstance(catalog, dict):
        raise CatalogValidationError("Retail catalog must be a dictionary")

    brands = catalog.get("brands", {})
    if not isinstance(brands, dict):
        raise CatalogValidationError("Retail catalog 'brands' must be a dictionary")

    normalized_brands = {}
    seen_product_ids = set()
    for brand_key, brand_entry in brands.items():
        normalized_brand = _normalize_brand_entry(brand_key, brand_entry)
        for sku in normalized_brand["skus"]:
            product_id = sku["product_id"]
            if product_id in seen_product_ids:
                raise CatalogValidationError(f"Duplicate product_id found: {product_id}")
            seen_product_ids.add(product_id)
        normalized_brands[str(brand_key)] = normalized_brand

    return {"brands": normalized_brands}


def validate_catalog(catalog: Dict) -> Dict:
    """Validate and return normalized catalog data."""
    normalized = normalize_catalog(catalog)

    if "unknown" not in normalized["brands"]:
        raise CatalogValidationError("Retail catalog must include an 'unknown' brand entry")

    return normalized


VALIDATED_RETAIL_CATALOG = validate_catalog(RETAIL_CATALOG)


def get_catalog_brand_entry(brand_key: str, catalog: Dict = None) -> Dict:
    catalog_data = catalog or VALIDATED_RETAIL_CATALOG
    brands = catalog_data.get("brands", {})
    return brands.get(brand_key, {})


def get_catalog_sku_entry(product_id: str, catalog: Dict = None) -> Dict:
    catalog_data = catalog or VALIDATED_RETAIL_CATALOG
    for brand_key, brand_entry in catalog_data.get("brands", {}).items():
        for sku in brand_entry.get("skus", []):
            if sku.get("product_id") == product_id:
                result = dict(sku)
                result["brand_key"] = brand_key
                result["brand_display_name"] = brand_entry.get("display_name", brand_key)
                result["is_ubl"] = bool(brand_entry.get("is_ubl", False))
                return result
    return {}


def is_ubl_brand(brand_key: str, catalog_entry: Dict) -> bool:
    if "is_ubl" in catalog_entry:
        return bool(catalog_entry.get("is_ubl"))

    brand_norm = BRAND_NORMS.get(brand_key, {})
    return brand_norm.get("is_ubl") == "yes"


def candidate_skus_for_brand(brand_key: str, sub_category: str, limit: int, catalog: Dict = None) -> List[Dict]:
    catalog_entry = get_catalog_brand_entry(brand_key, catalog=catalog)
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


def recognition_level(brand_key: str, candidate_skus: List[Dict], unique_sku_match_limit: int, catalog: Dict = None) -> str:
    if not get_catalog_brand_entry(brand_key, catalog=catalog):
        return "unknown"
    if len(candidate_skus) <= unique_sku_match_limit:
        return "sku_known"
    return "brand_known"


def enrich_brand_detection(brand_key: str, confidence: float, sub_category: str = "unknown", catalog: Dict = None) -> Dict:
    """Map a brand detection to catalog-aware output."""
    top_k = RETAIL_EXPERIMENT_CONFIG.get("top_k_skus", 5)
    unique_limit = RETAIL_EXPERIMENT_CONFIG.get("unique_sku_match_limit", 1)

    catalog_entry = get_catalog_brand_entry(brand_key, catalog=catalog)
    brand_norm = BRAND_NORMS.get(brand_key, {})
    candidate_skus = candidate_skus_for_brand(brand_key, sub_category, top_k, catalog=catalog)
    level = recognition_level(brand_key, candidate_skus, unique_limit, catalog=catalog)

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
                "aliases": sku.get("aliases", []),
                "reference_images": sku.get("reference_images", []),
            }
            for sku in candidate_skus
        ],
        "confidence": round(float(confidence), 4),
        "category_hint": sub_category,
    }


def enrich_sku_match(product_id: str, confidence: float, sub_category: str = "unknown", catalog: Dict = None) -> Dict:
    sku_entry = get_catalog_sku_entry(product_id, catalog=catalog)
    if not sku_entry:
        return enrich_brand_detection("unknown", confidence=confidence, sub_category=sub_category, catalog=catalog)

    return {
        "brand_key": sku_entry["brand_key"],
        "brand_display_name": sku_entry["brand_display_name"],
        "is_ubl": sku_entry["is_ubl"],
        "recognition_level": "sku_known",
        "matched_product_id": sku_entry["product_id"],
        "matched_product_display_name": sku_entry["display_name"],
        "candidate_skus": [
            {
                "product_id": sku_entry["product_id"],
                "display_name": sku_entry["display_name"],
                "pack_type": sku_entry.get("pack_type", "unknown"),
                "aliases": sku_entry.get("aliases", []),
                "reference_images": sku_entry.get("reference_images", []),
            }
        ],
        "confidence": round(float(confidence), 4),
        "category_hint": sub_category,
    }
