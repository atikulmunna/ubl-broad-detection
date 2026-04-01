import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.loader import RETAIL_CATALOG, RETAIL_EXPERIMENT_CONFIG
from utils.retail_evaluator import (
    evaluate_benchmark_cases,
    load_benchmark_cases,
    save_evaluation_report,
    validate_benchmark_cases,
)


def main():
    parser = argparse.ArgumentParser(description="Evaluate the retail experiment against a small benchmark set")
    parser.add_argument(
        "--benchmark-file",
        default="catalog/evaluation/sample_benchmark.json",
        help="Path to the benchmark case JSON file",
    )
    parser.add_argument(
        "--output-file",
        default="catalog/evaluation/latest_report.json",
        help="Where to write the evaluation report JSON",
    )
    args = parser.parse_args()

    cases = load_benchmark_cases(args.benchmark_file)
    issues = validate_benchmark_cases(cases)
    if issues:
        raise ValueError("Invalid benchmark manifest:\n- " + "\n- ".join(issues))

    report = evaluate_benchmark_cases(
        cases=cases,
        runtime_config=RETAIL_EXPERIMENT_CONFIG,
        top_k_skus=RETAIL_EXPERIMENT_CONFIG.get("top_k_skus", 5),
        catalog=RETAIL_CATALOG,
    )
    save_evaluation_report(report, args.output_file)

    summary = report["summary"]
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
