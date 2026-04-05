import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_proposer import run_product_proposer
from utils.retail_proposer import generate_image_slices, non_max_suppression
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
    assert result["runtime"]["mode"] == "missing_dependencies"
    assert result["runtime"]["caption"] == "product"
    assert result["runtime"]["reason"]


def test_generate_image_slices_covers_image_with_overlap():
    slices = generate_image_slices((1000, 800), slice_size=400, overlap_ratio=0.25)

    assert slices[0] == {"x1": 0, "y1": 0, "x2": 400, "y2": 400}
    assert slices[-1]["x2"] == 1000
    assert slices[-1]["y2"] == 800
    assert len(slices) > 1


def test_non_max_suppression_keeps_best_box():
    detections = [
        {"bbox_xyxy": [0, 0, 10, 10], "confidence": 0.9},
        {"bbox_xyxy": [1, 1, 11, 11], "confidence": 0.8},
        {"bbox_xyxy": [30, 30, 40, 40], "confidence": 0.7},
    ]

    kept = non_max_suppression(detections, iou_threshold=0.5)

    assert len(kept) == 2
    assert kept[0]["confidence"] == 0.9
    assert kept[1]["confidence"] == 0.7


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
