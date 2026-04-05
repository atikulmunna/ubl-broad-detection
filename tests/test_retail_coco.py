import json
import os
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_coco import build_cases_from_coco, load_coco_annotations, save_benchmark_manifest


def _write_coco_fixture(base_dir: Path):
    images_dir = base_dir / "images"
    images_dir.mkdir(parents=True)
    Image.new("RGB", (100, 80), (0, 0, 0)).save(images_dir / "shelf_a.jpg")
    Image.new("RGB", (90, 60), (0, 0, 0)).save(images_dir / "shelf_b.jpg")

    annotation_path = base_dir / "_annotations.coco.json"
    payload = {
        "images": [
            {"id": 1, "file_name": "shelf_a.jpg", "width": 100, "height": 80},
            {"id": 2, "file_name": "shelf_b.jpg", "width": 90, "height": 60},
        ],
        "annotations": [
            {"id": 11, "image_id": 1, "bbox": [10, 20, 30, 40], "segmentation": [[10, 20, 40, 20, 40, 60, 10, 60]]},
            {"id": 12, "image_id": 1, "bbox": [50, 10, 20, 20], "segmentation": [[50, 10, 70, 10, 70, 30, 50, 30]]},
            {"id": 13, "image_id": 2, "bbox": [5, 5, 10, 10], "segmentation": [[5, 5, 15, 5, 15, 15, 5, 15]]},
        ],
        "categories": [{"id": 1, "name": "product"}],
    }
    annotation_path.write_text(json.dumps(payload), encoding="utf-8")
    return annotation_path, images_dir


def test_load_coco_annotations_reads_payload(tmp_path: Path):
    annotation_path, _ = _write_coco_fixture(tmp_path)

    payload = load_coco_annotations(str(annotation_path))

    assert len(payload["images"]) == 2
    assert len(payload["annotations"]) == 3


def test_build_cases_from_coco_groups_annotations_per_image(tmp_path: Path):
    annotation_path, images_dir = _write_coco_fixture(tmp_path)

    cases = build_cases_from_coco(
        annotation_path=str(annotation_path),
        images_dir=str(images_dir),
        sub_category="hair_care",
    )

    assert len(cases) == 2
    assert cases[0]["case_id"] == "shelf_a"
    assert cases[0]["sub_category"] == "hair_care"
    assert len(cases[0]["ground_truth_instances"]) == 2
    assert cases[0]["ground_truth_instances"][0]["bbox_xyxy"] == [10, 20, 40, 60]
    assert cases[1]["ground_truth_instances"][0]["bbox_xyxy"] == [5, 5, 15, 15]


def test_build_cases_from_coco_honors_limit(tmp_path: Path):
    annotation_path, images_dir = _write_coco_fixture(tmp_path)

    cases = build_cases_from_coco(
        annotation_path=str(annotation_path),
        images_dir=str(images_dir),
        limit=1,
    )

    assert len(cases) == 1


def test_save_benchmark_manifest_writes_cases(tmp_path: Path):
    output_path = tmp_path / "benchmark.json"
    save_benchmark_manifest([{"case_id": "one"}], str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["cases"][0]["case_id"] == "one"
