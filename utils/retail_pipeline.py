"""
Lightweight retail matching pipeline helpers.

This module holds the analyzer's catalog-matching flow in a testable place
without depending on the heavy core package import path.
"""

import tempfile
from typing import Dict, List

from utils.retail_crops import attach_query_crops, summarize_query_crops
from utils.retail_matching import resolve_detection_with_catalog, summarize_resolved_instances
from utils.retail_runtime import get_runtime_index_components


def process_retail_detections(image_path: str, detections: List[Dict], sub_category: str,
                              runtime_config: Dict, top_k_skus: int, catalog: Dict = None) -> Dict:
    """
    Run the catalog-matching portion of the retail experiment on detections.
    """
    index, embedder, index_status = get_runtime_index_components(runtime_config)

    with tempfile.TemporaryDirectory(prefix="retail_query_crops_") as crop_dir:
        detections_with_queries = attach_query_crops(image_path, detections, crop_dir)
        query_preparation = summarize_query_crops(detections_with_queries)

        enriched_instances = [
            resolve_detection_with_catalog(
                det,
                sub_category=sub_category,
                index=index,
                embedder=embedder,
                top_k=top_k_skus,
                catalog=catalog,
            )
            for det in detections_with_queries
        ]

    summary_counts = summarize_resolved_instances(enriched_instances)

    return {
        "instances": enriched_instances,
        "index_runtime": index_status,
        "query_preparation": query_preparation,
        "summary_counts": summary_counts,
    }
