import json
import os
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_inference_preview import render_inference_preview, save_inference_result


def test_save_inference_result_writes_json(tmp_path: Path):
    output_path = tmp_path / "prediction.json"
    save_inference_result({"detections": [1, 2]}, str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["detections"] == [1, 2]


def test_render_inference_preview_saves_annotated_image(tmp_path: Path):
    image_path = tmp_path / "shelf.jpg"
    Image.new("RGB", (100, 80), (0, 0, 0)).save(image_path)
    output_path = tmp_path / "preview.png"

    render_inference_preview(
        image_path=str(image_path),
        detections=[{"bbox_xyxy": [10, 10, 40, 40], "confidence": 0.9, "label": "product"}],
        output_path=str(output_path),
    )

    assert output_path.exists()
    with Image.open(output_path) as preview:
        assert preview.size == (100, 80)
