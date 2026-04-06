"""
COCO import helpers for retail shelf benchmarks.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional


def load_coco_annotations(annotation_path: str) -> Dict:
    with open(annotation_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("COCO annotation file must contain a JSON object")

    if "images" not in payload or "annotations" not in payload:
        raise ValueError("COCO annotation file must contain 'images' and 'annotations'")

    return payload


def build_cases_from_coco(annotation_path: str, images_dir: str, sub_category: str = "unknown",
                          limit: Optional[int] = None, include_segmentation: bool = True,
                          min_ground_truth: int = 0, sort_by_density: bool = False) -> List[Dict]:
    payload = load_coco_annotations(annotation_path)
    images_root = Path(images_dir).resolve()

    images = payload.get("images", [])
    annotations = payload.get("annotations", [])
    annotations_by_image = defaultdict(list)
    for annotation in annotations:
        annotations_by_image[annotation.get("image_id")].append(annotation)

    image_records = list(images)
    if sort_by_density:
        image_records.sort(
            key=lambda item: len(annotations_by_image.get(item.get("id"), [])),
            reverse=True,
        )

    cases = []
    for image_record in image_records:
        image_id = image_record.get("id")
        image_path = images_root / image_record["file_name"]
        ground_truth_instances = []

        for annotation in annotations_by_image.get(image_id, []):
            bbox = _coco_bbox_to_xyxy(annotation.get("bbox", []))
            if bbox is None:
                continue

            ground_truth = {
                "bbox_xyxy": bbox,
            }
            if include_segmentation and annotation.get("segmentation"):
                ground_truth["segmentation"] = annotation["segmentation"]
            ground_truth_instances.append(ground_truth)

        annotation_count = len(ground_truth_instances)
        if annotation_count < min_ground_truth:
            continue

        case = {
            "case_id": _case_id_from_image(image_record),
            "image_path": str(image_path),
            "sub_category": sub_category,
            "image_size": {
                "width": image_record.get("width"),
                "height": image_record.get("height"),
            },
            "detections": [],
            "ground_truth_instances": ground_truth_instances,
            "expected_instances": [],
            "ground_truth_count": annotation_count,
        }
        cases.append(case)

        if limit is not None and len(cases) >= limit:
            break

    return cases


def save_benchmark_manifest(cases: List[Dict], output_path: str) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump({"cases": cases}, handle, indent=2)


def _coco_bbox_to_xyxy(bbox: List[float]) -> Optional[List[int]]:
    if len(bbox) != 4:
        return None

    x, y, width, height = bbox
    x1 = int(round(x))
    y1 = int(round(y))
    x2 = int(round(x + width))
    y2 = int(round(y + height))

    if x2 <= x1 or y2 <= y1:
        return None

    return [x1, y1, x2, y2]


def _case_id_from_image(image_record: Dict) -> str:
    file_name = image_record.get("file_name", "")
    stem = Path(file_name).stem
    return stem or f"image_{image_record.get('id', 'unknown')}"
