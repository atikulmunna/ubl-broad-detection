import json
import os
import sys
from pathlib import Path
from argparse import Namespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_proposer_sweep import build_sweep_configs, evaluate_proposer_sweep, save_best_run_config
from scripts.sweep_retail_proposer import _build_base_config, _build_sweep_options


def test_build_sweep_configs_expands_cartesian_product():
    configs = build_sweep_configs(
        base_config={"proposer_type": "mock_ground_truth"},
        sweep_options={
            "box_threshold": [0.1, 0.2],
            "captions": [["product"], ["product", "bottle"]],
        },
    )

    assert len(configs) == 4
    assert configs[0]["proposer_type"] == "mock_ground_truth"


def test_evaluate_proposer_sweep_ranks_best_run_first():
    cases = [
        {
            "case_id": "case_1",
            "image_path": "demo.jpg",
            "ground_truth_instances": [{"bbox_xyxy": [0, 0, 10, 10]}],
        }
    ]

    report = evaluate_proposer_sweep(
        cases=cases,
        base_config={
            "proposer_type": "mock_ground_truth",
            "mock_detections": [{"bbox_xyxy": [0, 0, 10, 10]}],
        },
        sweep_options={
            "mock_detections": [
                [],
                [{"bbox_xyxy": [0, 0, 10, 10]}],
            ],
        },
        top_k=1,
    )

    assert report["run_count"] == 2
    assert report["best_run"]["summary"]["proposal_recall"] == 1.0
    assert len(report["top_runs"]) == 1


def test_save_best_run_config_writes_best_config(tmp_path: Path):
    report = {
        "best_run": {
            "config": {"device": "cuda"},
            "summary": {"proposal_recall": 0.2},
        }
    }

    output_path = tmp_path / "best_config.json"
    save_best_run_config(report, str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["config"]["device"] == "cuda"
    assert payload["summary"]["proposal_recall"] == 0.2


def test_build_base_config_supports_yolo_local():
    args = Namespace(
        proposer_type="yolo_local",
        device="cuda",
        weights_path=["runs/detect/best.pt"],
        confidence_threshold=[0.15],
        image_size=[960],
        max_det=[300],
        model_id=[],
        caption_set=[],
        box_threshold=[],
        text_threshold=[],
        nms_iou_threshold=[],
        min_box_area_ratio=[],
        max_box_area_ratio=[],
        slice_size=640,
        slice_overlap_ratio=0.2,
    )

    config = _build_base_config(args)

    assert config["proposer_type"] == "yolo_local"
    assert config["weights_path"] == "runs/detect/best.pt"
    assert config["confidence_threshold"] == 0.15


def test_build_sweep_options_supports_yolo_local():
    args = Namespace(
        proposer_type="yolo_local",
        weights_path=["a.pt", "b.pt"],
        confidence_threshold=[0.05, 0.1],
        image_size=[960],
        max_det=[300, 500],
        model_id=[],
        caption_set=[],
        box_threshold=[],
        text_threshold=[],
        nms_iou_threshold=[],
        min_box_area_ratio=[],
        max_box_area_ratio=[],
        device="cuda",
        slice_size=640,
        slice_overlap_ratio=0.2,
    )

    sweep = _build_sweep_options(args)

    assert sweep["weights_path"] == ["a.pt", "b.pt"]
    assert sweep["confidence_threshold"] == [0.05, 0.1]
    assert sweep["max_det"] == [300, 500]
