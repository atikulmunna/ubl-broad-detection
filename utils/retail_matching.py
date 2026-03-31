"""
Catalog matching orchestration for the retail experiment.

This module bridges:
- detector outputs
- catalog enrichment
- optional catalog index search

It is kept free of model imports so the decision logic can be tested in
isolation before connecting real crop embeddings.
"""

from collections import defaultdict
from typing import Dict, List

from utils.retail_catalog import enrich_brand_detection, enrich_sku_match
from utils.retail_index import summarize_matches
from utils.retail_query import build_query_asset_from_detection


def resolve_detection_with_catalog(detection: Dict, sub_category: str, index=None, embedder=None,
                                   top_k: int = 5, catalog: Dict = None) -> Dict:
    """
    Resolve one detector output against the catalog.

    Current behavior:
    - if a catalog query plus index/embedder are available, try index search
    - if index yields a confident SKU, return SKU-level recognition
    - if index yields only brand confidence, return brand-level recognition
    - otherwise fall back to detector brand -> catalog enrichment
    """
    brand_key = detection.get("brand", "unknown")
    query_asset = build_query_asset_from_detection(detection)
    has_query = bool(query_asset.get("image_path") or query_asset.get("fallback_token"))

    if index is not None and embedder is not None and has_query:
        query_embedding = embedder.embed_query_asset(query_asset)
        matches = index.search(query_embedding, top_k=top_k)
        summary = summarize_matches(matches)
        detector_brand_known = brand_key not in ("", "unknown", None)
        brand_agrees = summary.get("brand_key") == brand_key

        if summary["recognition_level"] == "sku_known" and summary.get("product_id") and (brand_agrees or not detector_brand_known):
            resolved = enrich_sku_match(
                summary["product_id"],
                confidence=summary["score"],
                sub_category=sub_category,
                catalog=catalog,
            )
            resolved["match_source"] = "index_sku"
        elif summary["recognition_level"] == "brand_known" and (brand_agrees or not detector_brand_known):
            resolved = enrich_brand_detection(
                summary["brand_key"],
                confidence=summary["score"],
                sub_category=sub_category,
                catalog=catalog,
            )
            resolved["match_source"] = "index_brand"
        else:
            resolved = enrich_brand_detection(
                brand_key,
                confidence=detection.get("confidence", 0.0),
                sub_category=sub_category,
                catalog=catalog,
            )
            resolved["match_source"] = "detector_brand_fallback"
    else:
        resolved = enrich_brand_detection(
            brand_key,
            confidence=detection.get("confidence", 0.0),
            sub_category=sub_category,
            catalog=catalog,
        )
        resolved["match_source"] = "detector_brand_fallback"

    resolved["bbox_xyxy"] = detection.get("bbox_xyxy", [])
    resolved["detected_brand"] = brand_key
    resolved["query_source"] = query_asset.get("source", "unknown")
    return resolved


def summarize_resolved_instances(instances: List[Dict]) -> Dict:
    brand_breakdown = defaultdict(int)
    match_source_breakdown = defaultdict(int)
    ubl_count = 0
    competitor_count = 0
    unknown_count = 0

    for instance in instances:
        brand_breakdown[instance.get("brand_display_name", instance.get("brand_key", "unknown"))] += 1
        match_source_breakdown[instance.get("match_source", "unknown")] += 1
        if instance.get("recognition_level") == "unknown":
            unknown_count += 1
        elif instance.get("is_ubl"):
            ubl_count += 1
        else:
            competitor_count += 1

    return {
        "ubl_count": ubl_count,
        "competitor_count": competitor_count,
        "unknown_count": unknown_count,
        "brand_breakdown": dict(brand_breakdown),
        "match_source_breakdown": dict(match_source_breakdown),
        "total_products": len(instances),
    }
