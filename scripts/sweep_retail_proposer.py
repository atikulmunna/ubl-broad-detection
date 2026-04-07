import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_evaluator import load_benchmark_cases, validate_benchmark_cases
from utils.retail_proposer_sweep import evaluate_proposer_sweep, save_best_run_config


def main():
    parser = argparse.ArgumentParser(description="Run a small config sweep for the shelf product proposer")
    parser.add_argument("--benchmark-file", required=True)
    parser.add_argument("--output-file", default="catalog/evaluation/proposer_sweep_report.json")
    parser.add_argument("--best-config-file", default="")
    parser.add_argument("--proposer-type", default="grounding_dino_sahi")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--slice-size", type=int, default=640)
    parser.add_argument("--slice-overlap-ratio", type=float, default=0.2)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--top-k", type=int, default=5)

    parser.add_argument("--model-id", action="append", default=[])
    parser.add_argument("--caption-set", action="append", default=[],
                        help="Pipe-delimited prompt set, e.g. 'product|products|bottle|package'")
    parser.add_argument("--box-threshold", action="append", type=float, default=[])
    parser.add_argument("--text-threshold", action="append", type=float, default=[])
    parser.add_argument("--nms-iou-threshold", action="append", type=float, default=[])
    parser.add_argument("--min-box-area-ratio", action="append", type=float, default=[])
    parser.add_argument("--max-box-area-ratio", action="append", type=float, default=[])
    args = parser.parse_args()

    cases = load_benchmark_cases(args.benchmark_file)
    issues = validate_benchmark_cases(cases)
    if issues:
        raise ValueError("Invalid benchmark manifest:\n- " + "\n- ".join(issues))

    base_config = {
        "proposer_type": args.proposer_type,
        "device": args.device,
        "slice_size": args.slice_size,
        "slice_overlap_ratio": args.slice_overlap_ratio,
        "model_id": "IDEA-Research/grounding-dino-tiny",
        "captions": ["product.", "products.", "bottle.", "package."],
        "box_threshold": 0.25,
        "text_threshold": 0.25,
        "nms_iou_threshold": 0.5,
        "min_box_area_ratio": 0.0,
        "max_box_area_ratio": 1.0,
    }
    sweep_options = {
        "model_id": args.model_id,
        "captions": [_parse_caption_set(value) for value in args.caption_set],
        "box_threshold": args.box_threshold,
        "text_threshold": args.text_threshold,
        "nms_iou_threshold": args.nms_iou_threshold,
        "min_box_area_ratio": args.min_box_area_ratio,
        "max_box_area_ratio": args.max_box_area_ratio,
    }

    report = evaluate_proposer_sweep(
        cases=cases,
        base_config=base_config,
        sweep_options=sweep_options,
        iou_threshold=args.iou_threshold,
        top_k=args.top_k,
    )

    with open(args.output_file, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    if args.best_config_file:
        save_best_run_config(report, args.best_config_file)

    print(json.dumps({
        "run_count": report["run_count"],
        "best_run": report["best_run"],
    }, indent=2))


def _parse_caption_set(raw_value: str):
    parts = [part.strip() for part in str(raw_value).split("|")]
    return [part for part in parts if part]


if __name__ == "__main__":
    main()
