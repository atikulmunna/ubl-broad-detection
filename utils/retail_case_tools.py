"""
Helpers for creating and previewing shelf benchmark cases.
"""

import json
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw


def create_case_template_from_image(image_path: str, case_id: str, sub_category: str = "unknown",
                                    image_base_dir: str = "") -> Dict:
    image_file = Path(image_path)
    with Image.open(image_file) as image:
        width, height = image.size

    if image_base_dir:
        try:
            resolved_image_path = str(image_file.resolve().relative_to(Path(image_base_dir).resolve()))
        except ValueError:
            resolved_image_path = str(image_file.resolve())
    else:
        resolved_image_path = str(image_file)

    return {
        "case_id": case_id,
        "image_path": resolved_image_path,
        "sub_category": sub_category,
        "image_size": {
            "width": width,
            "height": height,
        },
        "detections": [],
        "expected_instances": [],
        "expected_summary": {
            "total_products": 0,
            "ubl_count": 0,
            "competitor_count": 0,
            "unknown_count": 0,
        },
    }


def save_case_json(case: Dict, output_path: str) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as handle:
        json.dump(case, handle, indent=2)


def render_case_preview(case: Dict, output_path: str, image_base_dir: str = "") -> None:
    image_path = _resolve_case_image_path(case.get("image_path", ""), image_base_dir)
    with Image.open(image_path).convert("RGB") as image:
        draw = ImageDraw.Draw(image)

        detections: List[Dict] = case.get("detections", [])
        expected_instances: List[Dict] = case.get("expected_instances", [])

        for index, detection in enumerate(detections):
            bbox = detection.get("bbox_xyxy", [])
            if len(bbox) != 4:
                continue

            expected = expected_instances[index] if index < len(expected_instances) else {}
            brand_key = expected.get("brand_key", detection.get("brand", "unknown"))
            recognition = expected.get("recognition_level", "unknown")
            is_ubl = expected.get("is_ubl")

            color = _choose_color(is_ubl, brand_key)
            draw.rectangle(bbox, outline=color, width=3)
            label = f"{index + 1}: {brand_key} [{recognition}]"
            draw.text((bbox[0], max(0, bbox[1] - 16)), label, fill=color)

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_file)


def _resolve_case_image_path(image_path: str, image_base_dir: str) -> Path:
    image_file = Path(image_path)
    if image_file.is_absolute():
        return image_file
    if image_base_dir:
        return (Path(image_base_dir) / image_file).resolve()
    return image_file.resolve()


def _choose_color(is_ubl, brand_key: str) -> str:
    if is_ubl is True:
        return "lime"
    if is_ubl is False:
        return "red"
    if brand_key == "unknown":
        return "yellow"
    return "cyan"
