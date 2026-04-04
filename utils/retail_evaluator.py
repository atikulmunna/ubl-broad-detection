"""
Small benchmark helpers for the retail experiment.

This module lets us score the current retail pipeline against a handful of
known examples before we invest in larger evaluation infrastructure.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from utils.retail_pipeline import process_retail_detections


def load_benchmark_cases(benchmark_path: str) -> List[Dict]:
    benchmark_file = Path(benchmark_path)
    with open(benchmark_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, dict):
        cases = payload.get("cases", [])
    elif isinstance(payload, list):
        cases = payload
    else:
        raise ValueError("Benchmark file must contain a list or an object with a 'cases' list")

    if not isinstance(cases, list):
        raise ValueError("Benchmark cases must be a list")

    normalized = []
    for case in cases:
        normalized_case = dict(case)
        image_path = normalized_case.get("image_path")
        if image_path:
            normalized_case["image_path"] = str(_resolve_case_path(image_path, benchmark_file.parent))
        normalized.append(normalized_case)

    return normalized


def validate_benchmark_cases(cases: List[Dict]) -> List[str]:
    issues = []

    for index, case in enumerate(cases):
        case_id = case.get("case_id") or f"case_{index + 1}"
        image_path = case.get("image_path")

        if not image_path:
            issues.append(f"{case_id}: missing image_path")
        elif not Path(image_path).exists():
            issues.append(f"{case_id}: image_path does not exist: {image_path}")

        detections = case.get("detections")
        if not isinstance(detections, list):
            issues.append(f"{case_id}: detections must be a list")

        expected_instances = case.get("expected_instances")
        if not isinstance(expected_instances, list):
            issues.append(f"{case_id}: expected_instances must be a list")
        elif detections is not None and isinstance(detections, list) and len(expected_instances) != len(detections):
            issues.append(f"{case_id}: expected_instances count must match detections count when provided")

        expected_summary = case.get("expected_summary")
        if expected_summary is not None and not isinstance(expected_summary, dict):
            issues.append(f"{case_id}: expected_summary must be an object when provided")

        ground_truth_instances = case.get("ground_truth_instances")
        if ground_truth_instances is not None and not isinstance(ground_truth_instances, list):
            issues.append(f"{case_id}: ground_truth_instances must be a list when provided")

    return issues


def evaluate_benchmark_cases(cases: List[Dict], runtime_config: Dict, top_k_skus: int,
                             catalog: Dict) -> Dict:
    case_results = []
    correct_brand = 0
    correct_sku = 0
    correct_recognition = 0
    correct_ubl = 0
    passed_cases = 0
    passed_summaries = 0
    total_detection_tp = 0
    total_detection_fp = 0
    total_detection_fn = 0
    total_detection_iou = 0.0
    total_detection_matches = 0

    for case in cases:
        case_name = case.get("case_id") or case.get("name") or f"case_{len(case_results) + 1}"
        expected_instances = case.get("expected_instances", [])
        expected_summary = case.get("expected_summary", {})
        ground_truth_instances = case.get("ground_truth_instances", [])

        pipeline_result = process_retail_detections(
            image_path=case["image_path"],
            detections=case.get("detections", []),
            sub_category=case.get("sub_category", "unknown"),
            runtime_config=runtime_config,
            top_k_skus=top_k_skus,
            catalog=catalog,
        )

        actual_instances = pipeline_result["instances"]
        instance_checks = []

        for index, expected in enumerate(expected_instances):
            actual = actual_instances[index] if index < len(actual_instances) else None
            checks = _evaluate_instance_expectation(expected, actual)
            instance_checks.append({
                "index": index,
                "expected": expected,
                "actual": actual,
                "checks": checks,
                "passed": all(checks.values()),
            })

            if actual is not None:
                if checks.get("brand_key", True):
                    correct_brand += 1
                if "matched_product_id" in expected and checks.get("matched_product_id", False):
                    correct_sku += 1
                if "recognition_level" in expected and checks.get("recognition_level", False):
                    correct_recognition += 1
                if "is_ubl" in expected and checks.get("is_ubl", False):
                    correct_ubl += 1

        count_match = len(actual_instances) == len(expected_instances)
        summary_checks = _evaluate_summary_expectation(expected_summary, pipeline_result["summary_counts"])
        summary_passed = all(summary_checks.values()) if summary_checks else True
        proposal_metrics = evaluate_detection_proposals(
            predictions=case.get("detections", []),
            ground_truth=ground_truth_instances,
        )
        if proposal_metrics["available"]:
            total_detection_tp += proposal_metrics["true_positives"]
            total_detection_fp += proposal_metrics["false_positives"]
            total_detection_fn += proposal_metrics["false_negatives"]
            total_detection_iou += proposal_metrics["matched_iou_sum"]
            total_detection_matches += proposal_metrics["matched_count"]
        case_passed = count_match and all(item["passed"] for item in instance_checks) and summary_passed
        if case_passed:
            passed_cases += 1
        if summary_passed:
            passed_summaries += 1

        case_results.append({
            "case_id": case_name,
            "passed": case_passed,
            "expected_instance_count": len(expected_instances),
            "actual_instance_count": len(actual_instances),
            "count_match": count_match,
            "instance_checks": instance_checks,
            "summary_checks": summary_checks,
            "summary_passed": summary_passed,
            "proposal_metrics": _serialize_proposal_metrics(proposal_metrics),
            "summary_counts": pipeline_result["summary_counts"],
            "index_runtime": pipeline_result["index_runtime"],
            "query_preparation": pipeline_result["query_preparation"],
        })

    sku_expectations = sum(1 for case in cases for expected in case.get("expected_instances", [])
                           if "matched_product_id" in expected)
    recognition_expectations = sum(1 for case in cases for expected in case.get("expected_instances", [])
                                   if "recognition_level" in expected)
    brand_expectations = sum(len(case.get("expected_instances", [])) for case in cases)
    ubl_expectations = sum(1 for case in cases for expected in case.get("expected_instances", [])
                           if "is_ubl" in expected)
    summary_expectations = sum(1 for case in cases if case.get("expected_summary"))
    detection_cases = sum(1 for case in cases if case.get("ground_truth_instances"))

    return {
        "summary": {
            "total_cases": len(cases),
            "passed_cases": passed_cases,
            "failed_cases": len(cases) - passed_cases,
            "passed_summaries": passed_summaries,
            "total_expected_instances": brand_expectations,
            "brand_accuracy": _safe_ratio(correct_brand, brand_expectations),
            "sku_accuracy": _safe_ratio(correct_sku, sku_expectations),
            "recognition_accuracy": _safe_ratio(correct_recognition, recognition_expectations),
            "ubl_accuracy": _safe_ratio(correct_ubl, ubl_expectations),
            "summary_accuracy": _safe_ratio(passed_summaries, summary_expectations),
            "detection_case_count": detection_cases,
            "proposal_precision": _safe_ratio(total_detection_tp, total_detection_tp + total_detection_fp),
            "proposal_recall": _safe_ratio(total_detection_tp, total_detection_tp + total_detection_fn),
            "proposal_mean_iou": _safe_ratio(total_detection_iou, total_detection_matches),
        },
        "cases": case_results,
    }


def save_evaluation_report(report: Dict, output_path: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)


def append_benchmark_case(benchmark_path: str, case: Dict) -> None:
    benchmark_file = Path(benchmark_path)
    benchmark_file.parent.mkdir(parents=True, exist_ok=True)

    if benchmark_file.exists():
        with open(benchmark_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = {"cases": []}

    if isinstance(payload, list):
        payload = {"cases": payload}
    if "cases" not in payload or not isinstance(payload["cases"], list):
        raise ValueError("Benchmark file must contain a list or an object with a 'cases' list")

    payload["cases"].append(case)

    with open(benchmark_file, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def evaluate_detection_proposals(predictions: List[Dict], ground_truth: List[Dict],
                                 iou_threshold: float = 0.5) -> Dict:
    if not ground_truth:
        return {
            "available": False,
            "true_positives": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "precision": None,
            "recall": None,
            "mean_iou": None,
            "matched_count": 0,
            "matched_iou_sum": 0.0,
        }

    prediction_boxes = [item.get("bbox_xyxy", []) for item in predictions if len(item.get("bbox_xyxy", [])) == 4]
    ground_truth_boxes = [item.get("bbox_xyxy", []) for item in ground_truth if len(item.get("bbox_xyxy", [])) == 4]

    matches = _match_boxes(prediction_boxes, ground_truth_boxes, iou_threshold=iou_threshold)
    matched_count = len(matches)
    matched_iou_sum = sum(match["iou"] for match in matches)
    true_positives = matched_count
    false_positives = max(0, len(prediction_boxes) - matched_count)
    false_negatives = max(0, len(ground_truth_boxes) - matched_count)

    return {
        "available": True,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": _safe_ratio(true_positives, true_positives + false_positives),
        "recall": _safe_ratio(true_positives, true_positives + false_negatives),
        "mean_iou": _safe_ratio(matched_iou_sum, matched_count),
        "matched_count": matched_count,
        "matched_iou_sum": matched_iou_sum,
    }


def _evaluate_instance_expectation(expected: Dict, actual: Optional[Dict]) -> Dict[str, bool]:
    checks = {}

    for field in ("brand_key", "matched_product_id", "recognition_level", "match_source", "is_ubl"):
        if field in expected:
            checks[field] = actual is not None and actual.get(field) == expected[field]

    return checks


def _evaluate_summary_expectation(expected: Dict, actual: Dict) -> Dict[str, bool]:
    checks = {}
    for field in ("total_products", "ubl_count", "competitor_count", "unknown_count"):
        if field in expected:
            checks[field] = actual.get(field) == expected[field]
    return checks


def _match_boxes(prediction_boxes: List[List[float]], ground_truth_boxes: List[List[float]],
                 iou_threshold: float) -> List[Dict]:
    candidate_pairs = []
    for pred_index, pred_box in enumerate(prediction_boxes):
        for gt_index, gt_box in enumerate(ground_truth_boxes):
            iou = _calculate_iou(pred_box, gt_box)
            if iou >= iou_threshold:
                candidate_pairs.append({
                    "pred_index": pred_index,
                    "gt_index": gt_index,
                    "iou": iou,
                })

    candidate_pairs.sort(key=lambda item: item["iou"], reverse=True)
    used_predictions = set()
    used_ground_truth = set()
    matches = []

    for pair in candidate_pairs:
        if pair["pred_index"] in used_predictions or pair["gt_index"] in used_ground_truth:
            continue
        used_predictions.add(pair["pred_index"])
        used_ground_truth.add(pair["gt_index"])
        matches.append(pair)

    return matches


def _calculate_iou(box_a: List[float], box_b: List[float]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_width = max(0.0, inter_x2 - inter_x1)
    inter_height = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_width * inter_height

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def _serialize_proposal_metrics(metrics: Dict) -> Dict:
    result = dict(metrics)
    result.pop("matched_iou_sum", None)
    return result


def _safe_ratio(numerator: int, denominator: int) -> Optional[float]:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _resolve_case_path(path_str: str, base_dir: Path) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()
