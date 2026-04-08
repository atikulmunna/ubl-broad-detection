import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_yolo_training import (
    build_yolo_train_args,
    coco_bbox_to_yolo_line,
    prepare_yolo_labels_from_coco,
    prepare_yolo_training_workspace,
    summarize_yolo_training_result,
    write_yolo_dataset_yaml,
)


def _write_dataset_fixture(base_dir: Path):
    for split in ("train", "valid", "test"):
        split_dir = base_dir / split
        split_dir.mkdir(parents=True)
        image_name = f"{split}_sample.jpg"
        Image.new("RGB", (100, 80), (0, 0, 0)).save(split_dir / image_name)
        payload = {
            "images": [
                {"id": 1, "file_name": image_name, "width": 100, "height": 80},
            ],
            "annotations": [
                {"id": 1, "image_id": 1, "bbox": [10, 20, 30, 40]},
            ],
            "categories": [{"id": 1, "name": "product"}],
        }
        (split_dir / "_annotations.coco.json").write_text(json.dumps(payload), encoding="utf-8")


def test_coco_bbox_to_yolo_line_converts_values():
    line = coco_bbox_to_yolo_line([10, 20, 30, 40], image_width=100, image_height=80, class_id=0)

    assert line == "0 0.25 0.5 0.3 0.5"


def test_prepare_yolo_labels_from_coco_writes_split_labels(tmp_path: Path):
    _write_dataset_fixture(tmp_path)

    summary = prepare_yolo_labels_from_coco(str(tmp_path))

    train_label = (tmp_path / "train" / "train_sample.txt").read_text(encoding="utf-8")
    assert train_label == "0 0.25 0.5 0.3 0.5"
    assert summary["splits"]["train"]["label_count"] == 1
    assert summary["splits"]["train"]["empty_label_count"] == 0


def test_prepare_yolo_labels_from_coco_can_clean_existing_labels(tmp_path: Path):
    _write_dataset_fixture(tmp_path)
    stale_label = tmp_path / "train" / "stale.txt"
    stale_label.write_text("old", encoding="utf-8")

    prepare_yolo_labels_from_coco(str(tmp_path), clean_existing=True)

    assert not stale_label.exists()


def test_write_yolo_dataset_yaml_writes_expected_structure(tmp_path: Path):
    output_path = tmp_path / "retail.yaml"

    payload = write_yolo_dataset_yaml(
        dataset_root=str(tmp_path),
        output_path=str(output_path),
        class_names=("product",),
    )

    assert payload["nc"] == 1
    assert payload["names"] == ["product"]
    assert output_path.exists()


def test_prepare_yolo_training_workspace_builds_yaml_and_labels(tmp_path: Path):
    _write_dataset_fixture(tmp_path)

    workspace = prepare_yolo_training_workspace(str(tmp_path))

    assert Path(workspace["dataset_yaml_path"]).exists()
    assert workspace["label_summary"]["splits"]["valid"]["label_count"] == 1
    assert workspace["dataset_yaml"]["names"] == ["product"]


def test_build_yolo_train_args_returns_ultralytics_kwargs(tmp_path: Path):
    dataset_yaml = tmp_path / "retail.yaml"
    dataset_yaml.write_text("names: [product]", encoding="utf-8")

    args = build_yolo_train_args(
        dataset_yaml_path=str(dataset_yaml),
        model="yolo11s.pt",
        project="outputs/yolo_train",
        name="trial_a",
        epochs=10,
        imgsz=960,
        batch=4,
        device="cuda",
        workers=2,
        patience=7,
        cache=True,
    )

    assert args["model"] == "yolo11s.pt"
    assert args["epochs"] == 10
    assert args["device"] == "cuda"
    assert args["cache"] is True


def test_summarize_yolo_training_result_extracts_key_fields():
    result = SimpleNamespace(save_dir="outputs/yolo_train/trial_a")
    summary = summarize_yolo_training_result(
        result=result,
        train_args={
            "model": "yolo11n.pt",
            "data": "dataset.yaml",
            "epochs": 50,
            "imgsz": 1280,
            "batch": 8,
            "device": "cuda",
            "project": "outputs/yolo_train",
            "name": "retail_one_class",
        },
    )

    assert summary["model"] == "yolo11n.pt"
    assert summary["save_dir"] == "outputs/yolo_train/trial_a"
