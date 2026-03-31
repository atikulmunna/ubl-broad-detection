"""
Experimental retail analyzer for the labs branch.

This module provides a catalog-first retail path that can evolve toward
generic proposal + catalog matching without disturbing the current
production analyzers.
"""

import logging
import time
from collections import defaultdict
from typing import Dict

from config.loader import RETAIL_EXPERIMENT_CONFIG
from core.detection import _detect_products_two_stage_sos
from utils.retail_catalog import enrich_brand_detection

logger = logging.getLogger(__name__)


def analyze_retail_experiment(image_path: str, worker_id: int = 0, visit_id: str = "",
                              sub_category: str = "unknown") -> Dict:
    """
    Experimental broad retail analyzer.

    Current baseline:
    - uses the existing SOS two-stage detector/classifier as a proposal engine
    - enriches each instance with catalog metadata
    - emits recognition confidence levels designed for future open-set expansion
    """
    logger.info(f"[Worker {worker_id}] [{visit_id}] [RETAIL-EXP] Starting retail experiment (sub_category={sub_category})")
    try:
        t_start = time.perf_counter()
        det_conf = RETAIL_EXPERIMENT_CONFIG.get("det_conf", 0.25)
        cls_conf = RETAIL_EXPERIMENT_CONFIG.get("cls_conf", 0.50)
        cls_batch_size = RETAIL_EXPERIMENT_CONFIG.get("cls_batch_size", 8)

        t_detect = time.perf_counter()
        detections = _detect_products_two_stage_sos(
            worker_id, image_path, det_conf, cls_conf, cls_batch_size, visit_id=visit_id
        )
        detection_ms = (time.perf_counter() - t_detect) * 1000

        enriched_instances = []
        brand_breakdown = defaultdict(int)
        ubl_count = 0
        competitor_count = 0
        unknown_count = 0

        for det in detections:
            brand_key = det.get("brand", "unknown")
            enriched = enrich_brand_detection(
                brand_key=brand_key,
                confidence=det.get("confidence", 0.0),
                sub_category=sub_category,
            )
            enriched["bbox_xyxy"] = det.get("bbox_xyxy", [])
            enriched_instances.append(enriched)

            brand_breakdown[enriched["brand_display_name"]] += 1
            if enriched["recognition_level"] == "unknown":
                unknown_count += 1
            elif enriched["is_ubl"]:
                ubl_count += 1
            else:
                competitor_count += 1

        total_ms = (time.perf_counter() - t_start) * 1000

        return {
            "model_version": "retail_experiment_v0",
            "confidence": {"det": det_conf, "cls": cls_conf},
            "sub_category": sub_category,
            "total_products": len(enriched_instances),
            "ubl_count": ubl_count,
            "competitor_count": competitor_count,
            "unknown_count": unknown_count,
            "brand_breakdown": dict(brand_breakdown),
            "instances": enriched_instances,
            "timing": {
                "total_ms": round(total_ms, 1),
                "detection_ms": round(detection_ms, 1),
            },
            "summary": (
                f"Retail experiment detected {len(enriched_instances)} products: "
                f"{ubl_count} UBL, {competitor_count} competitor, {unknown_count} unknown"
            ),
        }
    except Exception as e:
        logger.error(f"[{visit_id}] [RETAIL-EXP] Error in analyze_retail_experiment: {e}", exc_info=True)
        return {
            "error": str(e),
            "summary": "Error processing retail experiment",
        }
