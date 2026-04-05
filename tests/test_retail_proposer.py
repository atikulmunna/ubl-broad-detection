import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_proposer import run_product_proposer
from utils.retail_proposer_benchmark import evaluate_proposer_on_cases


def test_run_product_proposer_supports_mock_mode():
    result = run_product_proposer(
        image_path="demo.jpg",
        proposer_config={
            "proposer_type": "mock_ground_truth",
            "mock_detections": [{"bbox_xyxy": [0, 0, 10, 10]}],
        },
    )

    assert result["runtime"]["available"] is True
    assert result["detections"][0]["bbox_xyxy"] == [0, 0, 10, 10]


def test_run_product_proposer_returns_stub_for_grounding_dino_sahi():
    result = run_product_proposer(
        image_path="demo.jpg",
        proposer_config={
            "proposer_type": "grounding_dino_sahi",
            "caption": "product",
            "slice_size": 512,
            "slice_overlap_ratio": 0.25,
        },
    )

    assert result["runtime"]["available"] is False
    assert result["runtime"]["mode"] == "stub"
    assert result["runtime"]["caption"] == "product"


def test_evaluate_proposer_on_cases_scores_mock_predictions():
    cases = [
        {
            "case_id": "one",
            "image_path": "demo.jpg",
            "ground_truth_instances": [{"bbox_xyxy": [0, 0, 10, 10]}],
        }
    ]

    report = evaluate_proposer_on_cases(
        cases=cases,
        proposer_config={
            "proposer_type": "mock_ground_truth",
            "mock_detections": [{"bbox_xyxy": [0, 0, 10, 10]}],
        },
    )

    assert report["summary"]["proposal_precision"] == 1.0
    assert report["summary"]["proposal_recall"] == 1.0
    assert report["summary"]["proposal_mean_iou"] == 1.0
    assert report["cases"][0]["proposal_metrics"]["true_positives"] == 1
