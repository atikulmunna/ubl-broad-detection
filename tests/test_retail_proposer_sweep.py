import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_proposer_sweep import build_sweep_configs, evaluate_proposer_sweep, save_best_run_config


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
