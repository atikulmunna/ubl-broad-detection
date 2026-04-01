"""
Crop extraction helpers for retail query generation.

These utilities prepare real image-path queries from detector outputs so the
catalog matcher can operate on actual cropped product regions.
"""

from pathlib import Path
from typing import Dict, List

from PIL import Image


def _normalize_bbox(bbox: List[float], width: int, height: int):
    if len(bbox) != 4:
        return None

    x1, y1, x2, y2 = [int(round(value)) for value in bbox]
    x1 = max(0, min(x1, width))
    y1 = max(0, min(y1, height))
    x2 = max(0, min(x2, width))
    y2 = max(0, min(y2, height))

    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def attach_query_crops(image_path: str, detections: List[Dict], output_dir: str) -> List[Dict]:
    """
    Save per-detection crops and annotate detections with query image metadata.
    """
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path).convert("RGB") as image:
        width, height = image.size
        updated = []

        for index, detection in enumerate(detections):
            updated_detection = dict(detection)
            bbox = _normalize_bbox(updated_detection.get("bbox_xyxy", []), width, height)

            if bbox is None:
                updated_detection["query_image_path"] = ""
                updated_detection["query_source"] = "detection"
                updated.append(updated_detection)
                continue

            crop = image.crop(bbox)
            crop_path = output_root / f"detection_{index:03d}.png"
            crop.save(crop_path)

            updated_detection["query_image_path"] = str(crop_path)
            updated_detection["query_source"] = "crop"
            updated.append(updated_detection)

    return updated


def summarize_query_crops(detections: List[Dict]) -> Dict:
    total = len(detections)
    crop_ready = 0
    fallback_only = 0

    for detection in detections:
        if detection.get("query_image_path"):
            crop_ready += 1
        else:
            fallback_only += 1

    return {
        "total_detections": total,
        "crop_ready": crop_ready,
        "fallback_only": fallback_only,
    }
