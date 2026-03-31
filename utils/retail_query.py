"""
Query asset helpers for retail matching.

These helpers define the structured input we send into the embedder for
matching. A detection may provide:
- a real crop/image path
- a fallback text token
- both
"""

from typing import Dict


def build_query_asset(image_path: str = "", fallback_token: str = "", source: str = "unknown") -> Dict:
    return {
        "image_path": image_path or "",
        "fallback_token": fallback_token or "",
        "source": source,
    }


def build_query_asset_from_detection(detection: Dict) -> Dict:
    return build_query_asset(
        image_path=detection.get("query_image_path", "") or detection.get("catalog_query", ""),
        fallback_token=detection.get("query_token", "") or detection.get("brand", "") or "unknown",
        source=detection.get("query_source", "detection"),
    )

