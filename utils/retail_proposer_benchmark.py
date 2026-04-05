"""
Benchmark helpers for proposal-stage shelf detection.
"""

from typing import Dict, List

from utils.retail_evaluator import evaluate_detection_proposals
from utils.retail_proposer import run_product_proposer


def evaluate_proposer_on_cases(cases: List[Dict], proposer_config: Dict,
                               iou_threshold: float = 0.5) -> Dict:
    case_results = []
    total_tp = 0
    total_fp = 0
    total_fn = 0
    total_iou = 0.0
    total_matches = 0

    for case in cases:
        proposer_result = run_product_proposer(case["image_path"], proposer_config)
        detections = proposer_result.get("detections", [])
        metrics = evaluate_detection_proposals(
            predictions=detections,
            ground_truth=case.get("ground_truth_instances", []),
            iou_threshold=iou_threshold,
        )

        if metrics["available"]:
            total_tp += metrics["true_positives"]
            total_fp += metrics["false_positives"]
            total_fn += metrics["false_negatives"]
            total_iou += metrics["matched_iou_sum"]
            total_matches += metrics["matched_count"]

        case_results.append({
            "case_id": case.get("case_id"),
            "proposal_metrics": {
                "available": metrics["available"],
                "true_positives": metrics["true_positives"],
                "false_positives": metrics["false_positives"],
                "false_negatives": metrics["false_negatives"],
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "mean_iou": metrics["mean_iou"],
                "matched_count": metrics["matched_count"],
            },
            "proposer_runtime": proposer_result.get("runtime", {}),
            "prediction_count": len(detections),
            "ground_truth_count": len(case.get("ground_truth_instances", [])),
        })

    case_count = len(cases)
    evaluated_case_count = sum(1 for case in cases if case.get("ground_truth_instances"))

    return {
        "summary": {
            "total_cases": case_count,
            "evaluated_cases": evaluated_case_count,
            "proposal_precision": _safe_ratio(total_tp, total_tp + total_fp),
            "proposal_recall": _safe_ratio(total_tp, total_tp + total_fn),
            "proposal_mean_iou": _safe_ratio(total_iou, total_matches),
        },
        "cases": case_results,
    }


def _safe_ratio(numerator: float, denominator: float):
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)
