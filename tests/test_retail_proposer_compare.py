import json
import os
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_proposer_compare import compare_manifests, load_manifest, render_side_by_side_previews, save_comparison_report


def test_load_manifest_reads_json(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"images": []}), encoding="utf-8")

    payload = load_manifest(str(manifest_path))

    assert payload["images"] == []


def test_compare_manifests_aligns_common_images():
    left_manifest = {
        "images": [
            {"image_path": "a.jpg", "detection_count": 2, "preview_path": "left_a.png", "json_path": "left_a.json"},
            {"image_path": "b.jpg", "detection_count": 1, "preview_path": "left_b.png", "json_path": "left_b.json"},
        ]
    }
    right_manifest = {
        "images": [
            {"image_path": "a.jpg", "detection_count": 5, "preview_path": "right_a.png", "json_path": "right_a.json"},
            {"image_path": "c.jpg", "detection_count": 9, "preview_path": "right_c.png", "json_path": "right_c.json"},
        ]
    }

    report = compare_manifests(left_manifest, right_manifest, "left", "right")

    assert report["summary"]["common_image_count"] == 1
    assert report["summary"]["delta_total_detections"] == 3
    assert report["images"][0]["image_path"] == "a.jpg"


def test_save_comparison_report_writes_json(tmp_path: Path):
    output_path = tmp_path / "comparison.json"
    save_comparison_report({"summary": {"common_image_count": 1}}, str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["common_image_count"] == 1


def test_render_side_by_side_previews_saves_image(tmp_path: Path):
    left_preview = tmp_path / "left.png"
    right_preview = tmp_path / "right.png"
    Image.new("RGB", (40, 20), "red").save(left_preview)
    Image.new("RGB", (50, 20), "blue").save(right_preview)

    report = {
        "images": [
            {
                "image_path": "sample.jpg",
                "left_name": "left",
                "right_name": "right",
                "left_detection_count": 2,
                "right_detection_count": 3,
                "left_preview_path": str(left_preview),
                "right_preview_path": str(right_preview),
            }
        ]
    }

    saved_paths = render_side_by_side_previews(report, str(tmp_path / "out"))

    assert len(saved_paths) == 1
    assert Path(saved_paths[0]).exists()
