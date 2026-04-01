"""
Experimental retail analyzer for the labs branch.

This module provides a catalog-first retail path that can evolve toward
generic proposal + catalog matching without disturbing the current
production analyzers.
"""

import logging
import tempfile
import time
from typing import Dict

from config.loader import RETAIL_EXPERIMENT_CONFIG
from core.detection import _detect_products_two_stage_sos
from utils.retail_crops import attach_query_crops, summarize_query_crops
from utils.retail_matching import resolve_detection_with_catalog, summarize_resolved_instances
from utils.retail_runtime import get_runtime_index_components

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
        top_k_skus = RETAIL_EXPERIMENT_CONFIG.get("top_k_skus", 5)

        index, embedder, index_status = get_runtime_index_components(RETAIL_EXPERIMENT_CONFIG)

        t_detect = time.perf_counter()
        detections = _detect_products_two_stage_sos(
            worker_id, image_path, det_conf, cls_conf, cls_batch_size, visit_id=visit_id
        )
        detection_ms = (time.perf_counter() - t_detect) * 1000

        with tempfile.TemporaryDirectory(prefix="retail_query_crops_") as crop_dir:
            detections = attach_query_crops(image_path, detections, crop_dir)
            query_preparation = summarize_query_crops(detections)

            enriched_instances = [
                resolve_detection_with_catalog(
                    det,
                    sub_category=sub_category,
                    index=index,
                    embedder=embedder,
                    top_k=top_k_skus,
                )
                for det in detections
            ]
        summary_counts = summarize_resolved_instances(enriched_instances)

        total_ms = (time.perf_counter() - t_start) * 1000

        return {
            "model_version": "retail_experiment_v0",
            "confidence": {"det": det_conf, "cls": cls_conf},
            "sub_category": sub_category,
            "total_products": summary_counts["total_products"],
            "ubl_count": summary_counts["ubl_count"],
            "competitor_count": summary_counts["competitor_count"],
            "unknown_count": summary_counts["unknown_count"],
            "brand_breakdown": summary_counts["brand_breakdown"],
            "match_source_breakdown": summary_counts["match_source_breakdown"],
            "instances": enriched_instances,
            "index_runtime": index_status,
            "query_preparation": query_preparation,
            "timing": {
                "total_ms": round(total_ms, 1),
                "detection_ms": round(detection_ms, 1),
            },
            "summary": (
                f"Retail experiment detected {len(enriched_instances)} products: "
                f"{summary_counts['ubl_count']} UBL, {summary_counts['competitor_count']} competitor, "
                f"{summary_counts['unknown_count']} unknown"
            ),
        }
    except Exception as e:
        logger.error(f"[{visit_id}] [RETAIL-EXP] Error in analyze_retail_experiment: {e}", exc_info=True)
        return {
            "error": str(e),
            "summary": "Error processing retail experiment",
        }
