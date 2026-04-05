import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_coco import save_benchmark_manifest
from utils.retail_evaluator import load_benchmark_cases, validate_benchmark_cases
from utils.retail_proposer_benchmark import evaluate_proposer_on_cases


def main():
    parser = argparse.ArgumentParser(description="Evaluate a shelf product proposer against benchmark cases")
    parser.add_argument("--benchmark-file", required=True)
    parser.add_argument("--output-file", default="catalog/evaluation/proposer_report.json")
    parser.add_argument("--proposer-type", default="grounding_dino_sahi")
    parser.add_argument("--caption", default="product")
    parser.add_argument("--slice-size", type=int, default=640)
    parser.add_argument("--slice-overlap-ratio", type=float, default=0.2)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    args = parser.parse_args()

    cases = load_benchmark_cases(args.benchmark_file)
    issues = validate_benchmark_cases(cases)
    if issues:
        raise ValueError("Invalid benchmark manifest:\n- " + "\n- ".join(issues))

    report = evaluate_proposer_on_cases(
        cases=cases,
        proposer_config={
            "proposer_type": args.proposer_type,
            "caption": args.caption,
            "slice_size": args.slice_size,
            "slice_overlap_ratio": args.slice_overlap_ratio,
        },
        iou_threshold=args.iou_threshold,
    )

    with open(args.output_file, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
