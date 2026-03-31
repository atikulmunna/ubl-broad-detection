"""
Product-based shelf detection using YOLO detections and clustering.
This approach detects products first, then groups them into shelf rows.
"""

import numpy as np
from typing import List, Tuple
from PIL import Image
from sklearn.cluster import DBSCAN


def calculate_iou_boxes(box1: List[float], box2: List[float]) -> float:
    """Calculate Intersection over Union of two bounding boxes."""
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2

    # Calculate intersection
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)

    if x2_i < x1_i or y2_i < y1_i:
        return 0.0

    intersection = (x2_i - x1_i) * (y2_i - y1_i)

    # Calculate union
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def remove_overlapping_shelves(
    shelf_crops: List[Tuple[Image.Image, dict]],
    iou_threshold: float = 0.3
) -> List[Tuple[Image.Image, dict]]:
    """
    Remove overlapping shelf regions, keeping the ones with more products.

    Args:
        shelf_crops: List of (image, metadata) tuples
        iou_threshold: IoU threshold for considering shelves as overlapping

    Returns:
        Filtered list of shelf crops
    """
    if len(shelf_crops) <= 1:
        return shelf_crops

    # Sort by product count (descending)
    sorted_shelves = sorted(
        shelf_crops,
        key=lambda x: x[1].get('product_count', 0),
        reverse=True
    )

    kept_shelves = []
    for shelf_img, shelf_meta in sorted_shelves:
        box = shelf_meta['box']

        # Check if this shelf overlaps significantly with any kept shelf
        overlaps = False
        for _, kept_meta in kept_shelves:
            kept_box = kept_meta['box']
            iou = calculate_iou_boxes(box, kept_box)

            if iou > iou_threshold:
                overlaps = True
                break

        if not overlaps:
            kept_shelves.append((shelf_img, shelf_meta))

    # Re-sort by vertical position (top to bottom)
    kept_shelves.sort(key=lambda x: x[1]['box'][1])

    # Re-index
    for idx, (img, meta) in enumerate(kept_shelves):
        meta['index'] = idx

    return kept_shelves


def cluster_products_into_rows(
    boxes: np.ndarray,
    eps: float = 50,  # Maximum vertical distance between products in same row
    min_samples: int = 2
) -> List[List[int]]:
    """
    Cluster product bounding boxes into horizontal rows using DBSCAN.

    This uses an adaptive approach:
    1. First clusters products by Y-coordinate to form initial rows
    2. Then merges nearby rows that are likely part of the same visual shelf

    Args:
        boxes: Array of shape (N, 4) with [x1, y1, x2, y2] coordinates
        eps: Maximum vertical distance between products in the same row
        min_samples: Minimum products per row

    Returns:
        List of lists, where each inner list contains indices of boxes in that row
    """
    if len(boxes) == 0:
        return []

    # Use the vertical center (y-coordinate) for clustering
    y_centers = ((boxes[:, 1] + boxes[:, 3]) / 2).reshape(-1, 1)

    # Cluster by y-coordinate
    clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(y_centers)

    # Group boxes by cluster
    clusters = {}
    for idx, label in enumerate(clustering.labels_):
        if label == -1:  # Noise point
            continue
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(idx)

    # Sort clusters by average y-position (top to bottom)
    sorted_clusters = sorted(
        clusters.values(),
        key=lambda indices: np.mean([boxes[i, 1] for i in indices])
    )

    # Merge nearby rows that are likely part of the same visual shelf
    # Calculate average product height to determine merge threshold
    avg_product_height = np.median(boxes[:, 3] - boxes[:, 1])
    # Use a very small threshold - only merge if products overlap or have tiny gaps
    # This prevents distinct shelves from being merged together
    merge_threshold = avg_product_height * 0.15  # Only merge if gap is < 15% of product height

    merged_clusters = []
    i = 0
    while i < len(sorted_clusters):
        current_cluster = sorted_clusters[i].copy()

        # Try to merge with next clusters only if they're extremely close
        j = i + 1
        while j < len(sorted_clusters):
            current_max_y = np.max([boxes[idx, 3] for idx in current_cluster])
            next_min_y = np.min([boxes[idx, 1] for idx in sorted_clusters[j]])

            gap = next_min_y - current_max_y

            # Only merge if gap is very small (overlapping or nearly touching products)
            if gap < merge_threshold:
                current_cluster.extend(sorted_clusters[j])
                j += 1
            else:
                break

        merged_clusters.append(current_cluster)
        i = j if j > i + 1 else i + 1

    return merged_clusters


def get_row_bounding_box(boxes: np.ndarray, indices: List[int], expand_margin: float = 0.1) -> List[float]:
    """
    Get the bounding box that encompasses all products in a row with smart padding.

    Args:
        boxes: Array of shape (N, 4) with [x1, y1, x2, y2] coordinates
        indices: Indices of boxes to include
        expand_margin: Vertical expansion margin (fraction of row height)

    Returns:
        [x1, y1, x2, y2] bounding box coordinates
    """
    row_boxes = boxes[indices]

    # Get exact bounds of products
    x1 = np.min(row_boxes[:, 0])
    y1 = np.min(row_boxes[:, 1])
    x2 = np.max(row_boxes[:, 2])
    y2 = np.max(row_boxes[:, 3])

    # Only expand vertically (give some padding above/below)
    height = y2 - y1
    vertical_padding = height * expand_margin

    y1 = max(0, y1 - vertical_padding)
    y2 = y2 + vertical_padding

    # Don't expand horizontally - keep tight to products
    # Add just a tiny bit of horizontal padding (5% of average product width)
    avg_product_width = np.mean(row_boxes[:, 2] - row_boxes[:, 0])
    horizontal_padding = avg_product_width * 0.05

    x1 = max(0, x1 - horizontal_padding)
    x2 = x2 + horizontal_padding

    return [float(x1), float(y1), float(x2), float(y2)]


def detect_shelves_from_products(
    image: Image.Image,
    product_boxes: np.ndarray,
    clustering_eps: float = 50,
    min_products_per_row: int = 2,
    expand_margin: float = 0.1
) -> List[Tuple[Image.Image, dict]]:
    """
    Detect shelf rows by clustering product detections.

    Args:
        image: PIL Image
        product_boxes: Array of product bounding boxes (N, 4)
        clustering_eps: Maximum vertical distance for same-row clustering
        min_products_per_row: Minimum products to form a row
        expand_margin: Expand row bounding box by this fraction (for padding)

    Returns:
        List of (cropped_image, metadata) tuples
    """
    if len(product_boxes) == 0:
        return [(image, {
            'box': [0, 0, image.width, image.height],
            'score': 1.0,
            'label': 'full_image',
            'index': 0,
            'product_count': 0
        })]

    # Cluster products into rows
    row_clusters = cluster_products_into_rows(
        product_boxes,
        eps=clustering_eps,
        min_samples=min_products_per_row
    )

    if not row_clusters:
        return [(image, {
            'box': [0, 0, image.width, image.height],
            'score': 1.0,
            'label': 'full_image',
            'index': 0,
            'product_count': len(product_boxes)
        })]

    # Create shelf crops for each row
    shelf_crops = []
    for idx, row_indices in enumerate(row_clusters):
        # Get bounding box for this row (already includes smart padding)
        bbox = get_row_bounding_box(product_boxes, row_indices, expand_margin)
        x1, y1, x2, y2 = bbox

        # Ensure within image bounds
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(image.width, x2)
        y2 = min(image.height, y2)

        # Crop the shelf region
        cropped = image.crop((x1, y1, x2, y2))

        metadata = {
            'box': [x1, y1, x2, y2],
            'score': 1.0,
            'label': f'product_row_{idx}',
            'index': idx,
            'product_count': len(row_indices),
            'product_indices': row_indices
        }

        shelf_crops.append((cropped, metadata))

    # Remove overlapping shelves
    shelf_crops = remove_overlapping_shelves(shelf_crops, iou_threshold=0.3)

    return shelf_crops


if __name__ == "__main__":
    # Example usage
    print("Product clustering module for shelf detection")
    print("This detects shelves by clustering product detections instead of using llmdet")
