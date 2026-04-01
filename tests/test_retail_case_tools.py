import json
import os
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_case_tools import create_case_template_from_image, render_case_preview, save_case_json


def test_create_case_template_from_image_records_size_and_relative_path(tmp_path: Path):
    eval_dir = tmp_path / "evaluation"
    image_dir = eval_dir / "images"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "shelf.jpg"
    Image.new("RGB", (120, 80), (10, 10, 10)).save(image_path)

    case = create_case_template_from_image(
        image_path=str(image_path),
        case_id="shelf_001",
        sub_category="hair_care",
        image_base_dir=str(eval_dir),
    )

    assert case["case_id"] == "shelf_001"
    assert case["image_path"] == str(Path("images") / "shelf.jpg")
    assert case["image_size"] == {"width": 120, "height": 80}
    assert case["expected_summary"]["total_products"] == 0


def test_save_case_json_writes_payload(tmp_path: Path):
    output_path = tmp_path / "cases" / "one.json"
    save_case_json({"case_id": "one"}, str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["case_id"] == "one"


def test_render_case_preview_draws_boxes(tmp_path: Path):
    eval_dir = tmp_path / "evaluation"
    image_dir = eval_dir / "images"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "shelf.jpg"
    Image.new("RGB", (100, 60), (0, 0, 0)).save(image_path)

    case = {
        "case_id": "preview_case",
        "image_path": str(Path("images") / "shelf.jpg"),
        "detections": [
            {"bbox_xyxy": [10, 10, 40, 40]},
        ],
        "expected_instances": [
            {"brand_key": "dove", "recognition_level": "brand_known", "is_ubl": True},
        ],
    }
    output_path = tmp_path / "preview.png"

    render_case_preview(case, str(output_path), image_base_dir=str(eval_dir))

    assert output_path.exists()
    with Image.open(output_path) as preview:
        assert preview.size == (100, 60)
