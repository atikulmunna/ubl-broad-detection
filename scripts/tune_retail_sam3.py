import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_inference_preview import render_inference_preview, save_inference_result
from utils.retail_proposer import run_product_proposer
from utils.retail_sam3_tuning import (
    build_sam3_tuning_configs,
    save_sam3_tuning_summary,
    summarize_sam3_tuning_runs,
)


def main():
    parser = argparse.ArgumentParser(description="Run a small SAM3 refinement tuning sweep on shelf images")
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--image-dir", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--config-file", required=True)
    parser.add_argument("--output-dir", default="outputs/sam3_tuning")

    parser.add_argument("--sam3-score-threshold", action="append", type=float, default=[])
    parser.add_argument("--sam3-box-iou-threshold", action="append", type=float, default=[])
    parser.add_argument("--sam3-mask-threshold", action="append", type=float, default=[])
    parser.add_argument("--sam3-max-refine-boxes", action="append", type=int, default=[])
    args = parser.parse_args()

    base_config = _load_config(args.config_file)
    image_paths = _resolve_image_paths(args.image, args.image_dir, args.limit)
    if not image_paths:
        raise ValueError("No input images were found for SAM3 tuning")

    tuning_options = {
        "sam3_score_threshold": args.sam3_score_threshold or [0.2, 0.35],
        "sam3_box_iou_threshold": args.sam3_box_iou_threshold or [0.0, 0.05],
        "sam3_mask_threshold": args.sam3_mask_threshold or [0.0],
        "sam3_max_refine_boxes": args.sam3_max_refine_boxes or [48],
    }
    configs = build_sam3_tuning_configs(base_config, tuning_options)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_summaries = []
    for run_index, proposer_config in enumerate(configs, start=1):
        run_dir = output_dir / f"run_{run_index:02d}"
        run_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "run_id": run_index,
            "config": proposer_config,
            "images": [],
        }
        for image_path in image_paths:
            result = run_product_proposer(str(image_path), proposer_config)
            stem = image_path.stem
            json_path = run_dir / f"{stem}.json"
            preview_path = run_dir / f"{stem}_preview.png"
            payload = {
                "image_path": str(image_path),
                "proposer_config": proposer_config,
                "runtime": result.get("runtime", {}),
                "detections": result.get("detections", []),
            }
            save_inference_result(payload, str(json_path))
            render_inference_preview(str(image_path), payload["detections"], str(preview_path))

            coarse_count = int(payload["runtime"].get("coarse_detection_count", 0) or 0)
            refined_count = len(payload["detections"])
            retention_ratio = (refined_count / coarse_count) if coarse_count > 0 else None
            manifest["images"].append({
                "image_path": str(image_path),
                "json_path": str(json_path),
                "preview_path": str(preview_path),
                "detection_count": refined_count,
                "coarse_detection_count": coarse_count,
                "retention_ratio": retention_ratio,
                "runtime": payload["runtime"],
            })

        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        run_summaries.append(_summarize_run(manifest))

    summary = summarize_sam3_tuning_runs(run_summaries)
    summary_path = output_dir / "summary.json"
    save_sam3_tuning_summary(summary, str(summary_path))
    print(json.dumps({
        "run_count": summary["run_count"],
        "best_run": summary["best_run"],
        "summary_path": str(summary_path),
    }, indent=2))


def _load_config(config_file: str):
    payload = json.loads(Path(config_file).read_text(encoding="utf-8"))
    return payload.get("config", payload)


def _resolve_image_paths(explicit_images, image_dir: str, limit: int):
    image_paths = [Path(path).resolve() for path in explicit_images]
    if image_dir:
        image_paths.extend(
            sorted(
                path.resolve()
                for path in Path(image_dir).iterdir()
                if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
            )
        )

    deduped = []
    seen = set()
    for path in image_paths:
        key = str(path)
        if key in seen:
            continue
        deduped.append(path)
        seen.add(key)

    if limit > 0:
        return deduped[:limit]
    return deduped


def _summarize_run(manifest: Dict) -> Dict:
    images = manifest.get("images", [])
    detection_counts = [item.get("detection_count", 0) for item in images]
    retention_values = [item.get("retention_ratio") for item in images if item.get("retention_ratio") is not None]
    return {
        "run_id": manifest["run_id"],
        "config": manifest["config"],
        "manifest_path": str(Path(f"run_{manifest['run_id']:02d}") / "manifest.json"),
        "image_count": len(images),
        "average_detection_count": _average(detection_counts),
        "average_retention_ratio": _average(retention_values),
        "modes": sorted({str(item.get("runtime", {}).get("mode", "unknown")) for item in images}),
    }


def _average(values):
    if not values:
        return 0.0
    return round(sum(float(value) for value in values) / len(values), 4)


if __name__ == "__main__":
    main()
