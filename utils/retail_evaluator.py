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

    return cases


def evaluate_benchmark_cases(cases: List[Dict], runtime_config: Dict, top_k_skus: int,
                             catalog: Dict) -> Dict:
    case_results = []
    total_instances = 0
    correct_brand = 0
    correct_sku = 0
    correct_recognition = 0
    passed_cases = 0

    for case in cases:
        case_name = case.get("case_id") or case.get("name") or f"case_{len(case_results) + 1}"
        expected_instances = case.get("expected_instances", [])

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
                total_instances += 1
                if checks.get("brand_key", True):
                    correct_brand += 1
                if "matched_product_id" in expected and checks.get("matched_product_id", False):
                    correct_sku += 1
                if "recognition_level" in expected and checks.get("recognition_level", False):
                    correct_recognition += 1

        count_match = len(actual_instances) == len(expected_instances)
        case_passed = count_match and all(item["passed"] for item in instance_checks)
        if case_passed:
            passed_cases += 1

        case_results.append({
            "case_id": case_name,
            "passed": case_passed,
            "expected_instance_count": len(expected_instances),
            "actual_instance_count": len(actual_instances),
            "count_match": count_match,
            "instance_checks": instance_checks,
            "summary_counts": pipeline_result["summary_counts"],
            "index_runtime": pipeline_result["index_runtime"],
            "query_preparation": pipeline_result["query_preparation"],
        })

    sku_expectations = sum(1 for case in cases for expected in case.get("expected_instances", [])
                           if "matched_product_id" in expected)
    recognition_expectations = sum(1 for case in cases for expected in case.get("expected_instances", [])
                                   if "recognition_level" in expected)
    brand_expectations = sum(len(case.get("expected_instances", [])) for case in cases)

    return {
        "summary": {
            "total_cases": len(cases),
            "passed_cases": passed_cases,
            "failed_cases": len(cases) - passed_cases,
            "total_expected_instances": brand_expectations,
            "brand_accuracy": _safe_ratio(correct_brand, brand_expectations),
            "sku_accuracy": _safe_ratio(correct_sku, sku_expectations),
            "recognition_accuracy": _safe_ratio(correct_recognition, recognition_expectations),
        },
        "cases": case_results,
    }


def save_evaluation_report(report: Dict, output_path: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)


def _evaluate_instance_expectation(expected: Dict, actual: Optional[Dict]) -> Dict[str, bool]:
    checks = {}

    for field in ("brand_key", "matched_product_id", "recognition_level", "match_source"):
        if field in expected:
            checks[field] = actual is not None and actual.get(field) == expected[field]

    return checks


def _safe_ratio(numerator: int, denominator: int) -> Optional[float]:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)
