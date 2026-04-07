import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_proposer import run_product_proposer
from utils.retail_proposer import _box_area_ratio, _resolve_captions, generate_image_slices, non_max_suppression
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
            "device": "cpu",
            "slice_size": 512,
            "slice_overlap_ratio": 0.25,
        },
    )

    assert result["runtime"]["available"] is False
    assert result["runtime"]["mode"] == "missing_dependencies"
    assert result["runtime"]["caption"] == "product."
    assert result["runtime"]["captions"] == ["product."]
    assert result["runtime"]["requested_device"] == "cpu"
    assert result["runtime"]["reason"]


def test_run_product_proposer_returns_stub_for_grounding_dino_sam3():
    result = run_product_proposer(
        image_path="demo.jpg",
        proposer_config={
            "proposer_type": "grounding_dino_sam3",
            "device": "cpu",
            "sam3_model_id": "facebook/sam3",
        },
    )

    assert result["runtime"]["mode"] == "missing_dependencies"
    assert result["runtime"]["sam3_model_id"] == "facebook/sam3"
    assert result["runtime"]["backend"] == "grounding dino + sam3 refinement"


def test_run_product_proposer_falls_back_when_sam3_refinement_fails():
    coarse_result = {
        "detections": [{"bbox_xyxy": [0, 0, 10, 10], "confidence": 0.8}],
        "runtime": {"available": True},
    }
    with patch("utils.retail_proposer._sam3_dependency_status", return_value={"available": True}), \
         patch("utils.retail_proposer._run_grounding_dino_sahi", return_value=coarse_result), \
         patch("utils.retail_proposer._refine_with_sam3", side_effect=RuntimeError("gated repo")):
        result = run_product_proposer(
            image_path="demo.jpg",
            proposer_config={"proposer_type": "grounding_dino_sam3"},
        )

    assert result["runtime"]["mode"] == "sam3_unavailable_fallback"
    assert result["runtime"]["sam3_fallback_to_coarse"] is True
    assert result["detections"] == coarse_result["detections"]


def test_resolve_captions_normalizes_and_deduplicates():
    captions = _resolve_captions({
        "caption": "ignored",
        "captions": ["product", " products. ", "", "product"],
    })

    assert captions == ["product.", "products."]


def test_box_area_ratio_uses_full_image_area():
    ratio = _box_area_ratio([0, 0, 10, 20], image_area=1000)

    assert ratio == 0.2


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


def test_run_product_proposer_reports_area_filters_in_stub_runtime():
    result = run_product_proposer(
        image_path="demo.jpg",
        proposer_config={
            "proposer_type": "grounding_dino_sahi",
            "device": "cpu",
            "min_box_area_ratio": 0.001,
            "max_box_area_ratio": 0.2,
        },
    )

    assert result["runtime"]["min_box_area_ratio"] == 0.001
    assert result["runtime"]["max_box_area_ratio"] == 0.2


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
