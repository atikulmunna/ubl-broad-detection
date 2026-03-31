"""
Simple Size Variant Detection - Ratio-Based Approach

Uses relative width ratios within the same image to determine size variants.
Width is more robust than height since shelf occlusion is predominantly vertical.
Size variant config derived from composite keys in qpds_standards.yaml.
"""

import re
import numpy as np
import logging
from typing import List, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)


def _build_size_variants_from_yaml() -> Dict[str, List[str]]:
    """
    Derive PRODUCT_SIZE_VARIANTS from qpds_standards.yaml composite keys.

    Scans product_mappings for keys like "class_name:size" and groups sizes
    per class_name, sorted ascending by numeric value.
    """
    try:
        from config.loader import QPDS_STANDARDS
        mappings = QPDS_STANDARDS.get('product_mappings', {})
    except (ImportError, Exception) as e:
        logger.warning(f"Could not load QPDS standards for size variants: {e}")
        return {}

    # Parse composite keys: "class_name:size" pattern
    variants = defaultdict(set)
    for key in mappings:
        if ':' in str(key):
            parts = str(key).split(':', 1)
            class_name = parts[0]
            size = parts[1]
            variants[class_name].add(size)

    # Sort sizes ascending by numeric value
    def _size_sort_key(s: str) -> float:
        m = re.search(r'(\d+(?:\.\d+)?)', s)
        return float(m.group(1)) if m else 0.0

    return {cls: sorted(sizes, key=_size_sort_key) for cls, sizes in variants.items()}


# Build at module load
PRODUCT_SIZE_VARIANTS = _build_size_variants_from_yaml()

if PRODUCT_SIZE_VARIANTS:
    logger.info(f"Size variants loaded for {len(PRODUCT_SIZE_VARIANTS)} classes from YAML: "
                f"{list(PRODUCT_SIZE_VARIANTS.keys())}")


def calculate_bbox_width(bbox_xyxy: List[float]) -> float:
    """Calculate the width of a bounding box."""
    return bbox_xyxy[2] - bbox_xyxy[0]


def assign_size_variants_simple(detections: List[Dict]) -> List[Dict]:
    """
    Assign size variants using simple ratio-based clustering.

    Logic:
    1. Group detections by class
    2. Sort by width within each class (robust to vertical occlusion)
    3. If 2+ variants exist, split into groups (narrower = smaller size)
    4. If 1 variant exists, assign that variant to all

    Args:
        detections: List of detections with bbox_xyxy and class_name

    Returns:
        Enriched detections with "size_variant" field
    """
    by_class = defaultdict(list)
    for idx, det in enumerate(detections):
        by_class[det["class_name"]].append((idx, det))

    enriched = [det.copy() for det in detections]

    for class_name, items in by_class.items():
        variants = PRODUCT_SIZE_VARIANTS.get(class_name)

        if not variants:
            for idx, _ in items:
                enriched[idx]["size_variant"] = "N/A"
            continue

        if len(variants) == 1:
            for idx, _ in items:
                enriched[idx]["size_variant"] = variants[0]
            continue

        # Multiple variants - cluster by width (robust to vertical occlusion)
        widths = [(idx, calculate_bbox_width(det["bbox_xyxy"])) for idx, det in items]
        widths_sorted = sorted(widths, key=lambda x: x[1])

        if len(widths) == 1:
            # Single detection - default to first (smallest) variant
            enriched[widths[0][0]]["size_variant"] = variants[0]
            continue

        # 1D k-means: try every split point, pick the one that minimizes
        # total within-cluster variance. Robust to outliers within groups.
        width_values = np.array([w for _, w in widths_sorted])
        n_variants = len(variants)

        if n_variants == 2:
            # Optimal 1D split: find cut that minimizes combined variance
            best_cost = float('inf')
            best_split = 1
            for s in range(1, len(width_values)):
                left = width_values[:s]
                right = width_values[s:]
                cost = left.var() * len(left) + right.var() * len(right)
                if cost < best_cost:
                    best_cost = cost
                    best_split = s
            clusters = [widths_sorted[:best_split], widths_sorted[best_split:]]
        else:
            # Fallback for 3+ variants: iterative k-means
            # Init centroids evenly spaced
            centroids = np.linspace(width_values[0], width_values[-1], n_variants)
            for _ in range(20):
                labels = np.argmin(np.abs(width_values[:, None] - centroids[None, :]), axis=1)
                new_centroids = np.array([width_values[labels == k].mean() if (labels == k).any() else centroids[k]
                                          for k in range(n_variants)])
                if np.allclose(centroids, new_centroids):
                    break
                centroids = new_centroids
            clusters = [[] for _ in range(n_variants)]
            for i, label in enumerate(labels):
                clusters[label].append(widths_sorted[i])

        logger.info(f"[SizeVariant] {class_name}: {len(widths_sorted)} detections, "
                     f"split into {[len(c) for c in clusters]} clusters, "
                     f"widths={[round(w,1) for _,w in widths_sorted]}")

        for cluster_idx, cluster in enumerate(clusters):
            variant_idx = min(cluster_idx, len(variants) - 1)
            size = variants[variant_idx]
            for idx, _ in cluster:
                enriched[idx]["size_variant"] = size

    # Safety: ensure all detections have size_variant
    for idx, det in enumerate(enriched):
        if "size_variant" not in det:
            enriched[idx]["size_variant"] = "N/A"

    return enriched


def get_size_summary(detections: List[Dict]) -> Dict[str, Dict[str, int]]:
    """
    Create a summary of size variant counts keyed by class_name.

    Returns:
        Dict: {class_name: {size: count}}
    """
    summary = defaultdict(lambda: defaultdict(int))

    for det in detections:
        class_name = det.get("class_name", "unknown")
        size = det.get("size_variant", "N/A")

        if size == "N/A":
            continue

        summary[class_name][size] += 1

    return {k: dict(v) for k, v in summary.items()}
