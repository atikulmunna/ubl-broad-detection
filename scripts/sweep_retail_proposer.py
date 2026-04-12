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
    parser.add_argument("--weights-path", action="append", default=[])
    parser.add_argument("--caption-set", action="append", default=[],
                        help="Pipe-delimited prompt set, e.g. 'product|products|bottle|package'")
    parser.add_argument("--confidence-threshold", action="append", type=float, default=[])
    parser.add_argument("--box-threshold", action="append", type=float, default=[])
    parser.add_argument("--text-threshold", action="append", type=float, default=[])
    parser.add_argument("--nms-iou-threshold", action="append", type=float, default=[])
    parser.add_argument("--min-box-area-ratio", action="append", type=float, default=[])
    parser.add_argument("--max-box-area-ratio", action="append", type=float, default=[])
    parser.add_argument("--image-size", action="append", type=int, default=[])
    parser.add_argument("--max-det", action="append", type=int, default=[])
    args = parser.parse_args()

    cases = load_benchmark_cases(args.benchmark_file)
    issues = validate_benchmark_cases(cases)
    if issues:
        raise ValueError("Invalid benchmark manifest:\n- " + "\n- ".join(issues))

    base_config = _build_base_config(args)
    sweep_options = _build_sweep_options(args)

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


def _build_base_config(args):
    if args.proposer_type == "yolo_local":
        return {
            "proposer_type": args.proposer_type,
            "device": args.device,
            "weights_path": args.weights_path[0] if args.weights_path else "",
            "confidence_threshold": args.confidence_threshold[0] if args.confidence_threshold else 0.25,
            "iou_threshold": 0.45,
            "image_size": args.image_size[0] if args.image_size else 960,
            "max_det": args.max_det[0] if args.max_det else 300,
        }

    return {
        "proposer_type": args.proposer_type,
        "device": args.device,
        "slice_size": args.slice_size,
        "slice_overlap_ratio": args.slice_overlap_ratio,
        "model_id": args.model_id[0] if args.model_id else "IDEA-Research/grounding-dino-tiny",
        "captions": _parse_caption_set(args.caption_set[0]) if args.caption_set else ["product", "products", "bottle", "package"],
        "box_threshold": args.box_threshold[0] if args.box_threshold else 0.25,
        "text_threshold": args.text_threshold[0] if args.text_threshold else 0.25,
        "nms_iou_threshold": args.nms_iou_threshold[0] if args.nms_iou_threshold else 0.5,
        "min_box_area_ratio": args.min_box_area_ratio[0] if args.min_box_area_ratio else 0.0,
        "max_box_area_ratio": args.max_box_area_ratio[0] if args.max_box_area_ratio else 1.0,
    }


def _build_sweep_options(args):
    if args.proposer_type == "yolo_local":
        return {
            "weights_path": args.weights_path,
            "confidence_threshold": args.confidence_threshold,
            "image_size": args.image_size,
            "max_det": args.max_det,
        }

    return {
        "model_id": args.model_id,
        "captions": [_parse_caption_set(value) for value in args.caption_set],
        "box_threshold": args.box_threshold,
        "text_threshold": args.text_threshold,
        "nms_iou_threshold": args.nms_iou_threshold,
        "min_box_area_ratio": args.min_box_area_ratio,
        "max_box_area_ratio": args.max_box_area_ratio,
    }


if __name__ == "__main__":
    main()
