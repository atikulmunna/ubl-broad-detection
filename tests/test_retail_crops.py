import sys
import os
from pathlib import Path

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.retail_crops import attach_query_crops
from utils.retail_crops import summarize_query_crops


def test_attach_query_crops_writes_crop_images(tmp_path: Path):
    image_path = tmp_path / "source.png"
    Image.new("RGB", (100, 80), (255, 0, 0)).save(image_path)

    detections = [
        {"brand": "dove", "bbox_xyxy": [10, 10, 60, 50]},
    ]

    updated = attach_query_crops(str(image_path), detections, str(tmp_path / "crops"))

    crop_path = Path(updated[0]["query_image_path"])
    assert crop_path.exists()
    assert updated[0]["query_source"] == "crop"


def test_attach_query_crops_falls_back_for_invalid_bbox(tmp_path: Path):
    image_path = tmp_path / "source.png"
    Image.new("RGB", (100, 80), (255, 0, 0)).save(image_path)

    detections = [
        {"brand": "dove", "bbox_xyxy": [20, 20, 20, 50]},
    ]

    updated = attach_query_crops(str(image_path), detections, str(tmp_path / "crops"))

    assert updated[0]["query_image_path"] == ""
    assert updated[0]["query_source"] == "detection"


def test_summarize_query_crops_counts_crop_and_fallback_paths():
    summary = summarize_query_crops([
        {"query_image_path": "crops/one.png"},
        {"query_image_path": ""},
        {"query_image_path": "crops/two.png"},
    ])

    assert summary["total_detections"] == 3
    assert summary["crop_ready"] == 2
    assert summary["fallback_only"] == 1
