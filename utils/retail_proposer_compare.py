"""Helpers for comparing proposer inference manifests and previews."""

import json
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw


def load_manifest(manifest_path: str) -> Dict:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def compare_manifests(left_manifest: Dict, right_manifest: Dict, left_name: str, right_name: str) -> Dict:
    left_images = {item["image_path"]: item for item in left_manifest.get("images", [])}
    right_images = {item["image_path"]: item for item in right_manifest.get("images", [])}
    common_paths = sorted(set(left_images) & set(right_images))

    image_comparisons = []
    left_total = 0
    right_total = 0
    for image_path in common_paths:
        left_item = left_images[image_path]
        right_item = right_images[image_path]
        left_count = int(left_item.get("detection_count", 0))
        right_count = int(right_item.get("detection_count", 0))
        left_total += left_count
        right_total += right_count
        image_comparisons.append({
            "image_path": image_path,
            "left_name": left_name,
            "right_name": right_name,
            "left_detection_count": left_count,
            "right_detection_count": right_count,
            "delta_detection_count": right_count - left_count,
            "left_preview_path": left_item.get("preview_path"),
            "right_preview_path": right_item.get("preview_path"),
            "left_json_path": left_item.get("json_path"),
            "right_json_path": right_item.get("json_path"),
        })

    return {
        "summary": {
            "common_image_count": len(common_paths),
            "left_name": left_name,
            "right_name": right_name,
            "left_total_detections": left_total,
            "right_total_detections": right_total,
            "delta_total_detections": right_total - left_total,
        },
        "images": image_comparisons,
    }


def save_comparison_report(report: Dict, output_path: str) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report, indent=2), encoding="utf-8")


def render_side_by_side_previews(report: Dict, output_dir: str) -> List[str]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    saved_paths = []

    for item in report.get("images", []):
        left_preview_path = item.get("left_preview_path")
        right_preview_path = item.get("right_preview_path")
        if not left_preview_path or not right_preview_path:
            continue

        output_path = output_root / f"{Path(item['image_path']).stem}_compare.png"
        _render_side_by_side_preview(
            left_preview_path=left_preview_path,
            right_preview_path=right_preview_path,
            left_title=f"{item['left_name']} ({item['left_detection_count']})",
            right_title=f"{item['right_name']} ({item['right_detection_count']})",
            output_path=str(output_path),
        )
        saved_paths.append(str(output_path))

    return saved_paths


def _render_side_by_side_preview(left_preview_path: str, right_preview_path: str,
                                 left_title: str, right_title: str, output_path: str) -> None:
    with Image.open(left_preview_path).convert("RGB") as left_image, Image.open(right_preview_path).convert("RGB") as right_image:
        width = left_image.width + right_image.width
        height = max(left_image.height, right_image.height) + 28
        canvas = Image.new("RGB", (width, height), color="black")
        canvas.paste(left_image, (0, 28))
        canvas.paste(right_image, (left_image.width, 28))

        draw = ImageDraw.Draw(canvas)
        draw.text((8, 6), left_title, fill="cyan")
        draw.text((left_image.width + 8, 6), right_title, fill="yellow")

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_file)
