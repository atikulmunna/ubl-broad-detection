"""
Helpers for saving product proposer outputs as JSON and annotated images.
"""

import json
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw


def save_inference_result(result: Dict, output_path: str) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, indent=2), encoding="utf-8")


def render_inference_preview(image_path: str, detections: List[Dict], output_path: str) -> None:
    with Image.open(image_path).convert("RGB") as image:
        draw = ImageDraw.Draw(image)

        for index, detection in enumerate(detections, start=1):
            bbox = detection.get("bbox_xyxy", [])
            if len(bbox) != 4:
                continue

            confidence = detection.get("confidence")
            label = detection.get("label", detection.get("source", "proposal"))
            caption = detection.get("caption", "")
            text_bits = [f"{index}", str(label)]
            if confidence is not None:
                text_bits.append(f"{float(confidence):.2f}")
            if caption:
                text_bits.append(f"({caption})")

            draw.rectangle(bbox, outline="cyan", width=3)
            draw.text((bbox[0], max(0, bbox[1] - 16)), " ".join(text_bits), fill="cyan")

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_file)
