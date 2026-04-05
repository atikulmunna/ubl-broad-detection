"""
Product proposer abstractions for shelf detection experiments.
"""

import importlib.util
from pathlib import Path
from typing import Dict, List

from PIL import Image

_GROUNDING_DINO_BACKEND = None


def run_product_proposer(image_path: str, proposer_config: Dict) -> Dict:
    proposer_type = proposer_config.get("proposer_type", "mock_ground_truth")

    if proposer_type == "mock_ground_truth":
        detections = proposer_config.get("mock_detections", [])
        return {
            "proposer_type": proposer_type,
            "detections": [dict(item) for item in detections],
            "runtime": {
                "available": True,
                "mode": "mock",
            },
        }

    if proposer_type == "grounding_dino_sahi":
        return _run_grounding_dino_sahi(image_path, proposer_config)

    raise ValueError(f"Unknown proposer_type: {proposer_type}")


def _run_grounding_dino_sahi(image_path: str, proposer_config: Dict) -> Dict:
    dependency_status = _grounding_dino_dependency_status()
    runtime = {
        "available": dependency_status["available"],
        "mode": "real" if dependency_status["available"] else "missing_dependencies",
        "reason": dependency_status.get("reason", ""),
        "image_path": str(Path(image_path)),
        "caption": proposer_config.get("caption", "product"),
        "slice_size": proposer_config.get("slice_size", 640),
        "slice_overlap_ratio": proposer_config.get("slice_overlap_ratio", 0.2),
        "model_id": proposer_config.get("model_id", "IDEA-Research/grounding-dino-tiny"),
        "backend": "transformers + sliced inference",
    }

    if not dependency_status["available"]:
        return {
            "proposer_type": "grounding_dino_sahi",
            "detections": [],
            "runtime": runtime,
        }

    detections, extra_runtime = _infer_grounding_dino_slices(image_path, proposer_config)
    runtime.update(extra_runtime)
    return {
        "proposer_type": "grounding_dino_sahi",
        "detections": detections,
        "runtime": runtime,
    }


def _grounding_dino_dependency_status() -> Dict:
    torch_available, torch_reason = _torch_import_status()
    if not torch_available:
        return {
            "available": False,
            "reason": torch_reason,
        }

    transformers_available = bool(importlib.util.find_spec("transformers"))
    if not transformers_available:
        return {
            "available": False,
            "reason": "Missing optional dependency: transformers",
        }
    return {"available": True}


def _infer_grounding_dino_slices(image_path: str, proposer_config: Dict):
    torch = _import_torch()
    processor, model, device = _get_grounding_dino_backend(
        proposer_config.get("model_id", "IDEA-Research/grounding-dino-tiny")
    )
    caption = proposer_config.get("caption", "product")
    slice_size = int(proposer_config.get("slice_size", 640))
    slice_overlap_ratio = float(proposer_config.get("slice_overlap_ratio", 0.2))
    box_threshold = float(proposer_config.get("box_threshold", 0.25))
    text_threshold = float(proposer_config.get("text_threshold", 0.25))
    nms_iou_threshold = float(proposer_config.get("nms_iou_threshold", 0.5))

    with Image.open(image_path).convert("RGB") as image:
        slices = generate_image_slices(image.size, slice_size=slice_size, overlap_ratio=slice_overlap_ratio)
        detections = []

        for slice_region in slices:
            crop = image.crop((slice_region["x1"], slice_region["y1"], slice_region["x2"], slice_region["y2"]))
            inputs = processor(images=crop, text=caption, return_tensors="pt")
            inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}

            with torch.no_grad():
                outputs = model(**inputs)

            results = processor.post_process_grounded_object_detection(
                outputs,
                inputs["input_ids"],
                threshold=box_threshold,
                text_threshold=text_threshold,
                target_sizes=[(crop.height, crop.width)],
            )[0]

            for box, score, label in zip(results["boxes"], results["scores"], results["labels"]):
                x1, y1, x2, y2 = [float(value) for value in box.tolist()]
                detections.append({
                    "bbox_xyxy": [
                        int(round(x1 + slice_region["x1"])),
                        int(round(y1 + slice_region["y1"])),
                        int(round(x2 + slice_region["x1"])),
                        int(round(y2 + slice_region["y1"])),
                    ],
                    "confidence": round(float(score), 4),
                    "label": str(label),
                    "source": "grounding_dino_sahi",
                })

    merged = non_max_suppression(detections, iou_threshold=nms_iou_threshold)
    runtime = {
        "device": device,
        "slice_count": len(slices),
        "raw_detection_count": len(detections),
        "merged_detection_count": len(merged),
        "box_threshold": box_threshold,
        "text_threshold": text_threshold,
        "nms_iou_threshold": nms_iou_threshold,
    }
    return merged, runtime


def generate_image_slices(image_size, slice_size: int, overlap_ratio: float) -> List[Dict]:
    width, height = image_size
    if slice_size <= 0:
        raise ValueError("slice_size must be positive")
    if overlap_ratio < 0 or overlap_ratio >= 1:
        raise ValueError("overlap_ratio must be in [0, 1)")

    step = max(1, int(round(slice_size * (1 - overlap_ratio))))
    x_positions = _sliding_positions(width, slice_size, step)
    y_positions = _sliding_positions(height, slice_size, step)

    slices = []
    for y1 in y_positions:
        for x1 in x_positions:
            x2 = min(width, x1 + slice_size)
            y2 = min(height, y1 + slice_size)
            slices.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return slices


def non_max_suppression(detections: List[Dict], iou_threshold: float = 0.5) -> List[Dict]:
    ordered = sorted(detections, key=lambda item: item.get("confidence", 0.0), reverse=True)
    kept = []

    for detection in ordered:
        bbox = detection.get("bbox_xyxy", [])
        if len(bbox) != 4:
            continue
        if all(_calculate_iou(bbox, existing["bbox_xyxy"]) < iou_threshold for existing in kept):
            kept.append(detection)

    return kept


def _sliding_positions(length: int, window: int, step: int) -> List[int]:
    if length <= window:
        return [0]

    positions = list(range(0, max(1, length - window + 1), step))
    last_position = length - window
    if positions[-1] != last_position:
        positions.append(last_position)
    return positions


def _calculate_iou(box_a: List[float], box_b: List[float]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def _get_grounding_dino_backend(model_id: str):
    global _GROUNDING_DINO_BACKEND
    if _GROUNDING_DINO_BACKEND and _GROUNDING_DINO_BACKEND["model_id"] == model_id:
        return (
            _GROUNDING_DINO_BACKEND["processor"],
            _GROUNDING_DINO_BACKEND["model"],
            _GROUNDING_DINO_BACKEND["device"],
        )

    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    torch = _import_torch()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id)
    model.to(device)
    model.eval()

    _GROUNDING_DINO_BACKEND = {
        "model_id": model_id,
        "processor": processor,
        "model": model,
        "device": device,
    }
    return processor, model, device


def _torch_import_status():
    if not importlib.util.find_spec("torch"):
        return False, "Missing optional dependency: torch"

    try:
        import torch  # noqa: F401
    except Exception as exc:
        return False, f"torch import failed: {exc}"

    return True, ""


def _import_torch():
    import torch
    return torch
