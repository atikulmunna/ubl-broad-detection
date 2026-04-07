import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_inference_preview import render_inference_preview, save_inference_result
from utils.retail_proposer import run_product_proposer


def main():
    parser = argparse.ArgumentParser(description="Run proposer inference on shelf images and save visual previews")
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--image-dir", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--config-file", required=True)
    parser.add_argument("--output-dir", default="outputs/inference")
    args = parser.parse_args()

    proposer_config = _load_config(args.config_file)
    image_paths = _resolve_image_paths(args.image, args.image_dir, args.limit)
    if not image_paths:
        raise ValueError("No input images were found for inference")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"images": []}
    for image_path in image_paths:
        result = run_product_proposer(str(image_path), proposer_config)
        stem = image_path.stem
        json_path = output_dir / f"{stem}.json"
        preview_path = output_dir / f"{stem}_preview.png"

        payload = {
            "image_path": str(image_path),
            "proposer_config": proposer_config,
            "runtime": result.get("runtime", {}),
            "detections": result.get("detections", []),
        }
        save_inference_result(payload, str(json_path))
        render_inference_preview(str(image_path), payload["detections"], str(preview_path))

        manifest["images"].append({
            "image_path": str(image_path),
            "json_path": str(json_path),
            "preview_path": str(preview_path),
            "detection_count": len(payload["detections"]),
            "runtime": payload["runtime"],
        })

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "image_count": len(manifest["images"]),
        "manifest_path": str(manifest_path),
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
        if str(path) in seen:
            continue
        deduped.append(path)
        seen.add(str(path))

    if limit > 0:
        return deduped[:limit]
    return deduped


if __name__ == "__main__":
    main()
