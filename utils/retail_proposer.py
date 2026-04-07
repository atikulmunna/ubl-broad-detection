"""
Product proposer abstractions for shelf detection experiments.
"""

import importlib.util
from pathlib import Path
from typing import Dict, List

from PIL import Image

_GROUNDING_DINO_BACKEND = None
_SAM3_BACKEND = None


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

    if proposer_type == "grounding_dino_sam3":
        return _run_grounding_dino_sam3(image_path, proposer_config)

    raise ValueError(f"Unknown proposer_type: {proposer_type}")


def _run_grounding_dino_sahi(image_path: str, proposer_config: Dict) -> Dict:
    captions = _resolve_captions(proposer_config)
    min_box_area_ratio = float(proposer_config.get("min_box_area_ratio", 0.0))
    max_box_area_ratio = float(proposer_config.get("max_box_area_ratio", 1.0))
    dependency_status = _grounding_dino_dependency_status()
    runtime = {
        "available": dependency_status["available"],
        "mode": "real" if dependency_status["available"] else "missing_dependencies",
        "reason": dependency_status.get("reason", ""),
        "image_path": str(Path(image_path)),
        "caption": captions[0],
        "captions": captions,
        "slice_size": proposer_config.get("slice_size", 640),
        "slice_overlap_ratio": proposer_config.get("slice_overlap_ratio", 0.2),
        "model_id": proposer_config.get("model_id", "IDEA-Research/grounding-dino-tiny"),
        "requested_device": proposer_config.get("device", "auto"),
        "min_box_area_ratio": min_box_area_ratio,
        "max_box_area_ratio": max_box_area_ratio,
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


def _sam3_dependency_status() -> Dict:
    dependency_status = _grounding_dino_dependency_status()
    if not dependency_status["available"]:
        return dependency_status

    try:
        import transformers
    except Exception as exc:
        return {
            "available": False,
            "reason": f"transformers import failed: {exc}",
        }

    if not hasattr(transformers, "Sam3Model") or not hasattr(transformers, "Sam3Processor"):
        return {
            "available": False,
            "reason": "Installed transformers build does not expose Sam3Model/Sam3Processor",
        }
    return {"available": True}


def _run_grounding_dino_sam3(image_path: str, proposer_config: Dict) -> Dict:
    runtime = {
        "available": False,
        "mode": "missing_dependencies",
        "reason": "",
        "image_path": str(Path(image_path)),
        "backend": "grounding dino + sam3 refinement",
    }

    sam_status = _sam3_dependency_status()
    runtime["available"] = sam_status["available"]
    runtime["reason"] = sam_status.get("reason", "")
    runtime["sam3_model_id"] = proposer_config.get("sam3_model_id", "facebook/sam3")
    runtime["sam3_mask_threshold"] = float(proposer_config.get("sam3_mask_threshold", 0.5))
    runtime["sam3_score_threshold"] = float(proposer_config.get("sam3_score_threshold", 0.5))
    runtime["sam3_max_refine_boxes"] = int(proposer_config.get("sam3_max_refine_boxes", 48))
    runtime["sam3_box_iou_threshold"] = float(proposer_config.get("sam3_box_iou_threshold", 0.1))

    if not sam_status["available"]:
        return {
            "proposer_type": "grounding_dino_sam3",
            "detections": [],
            "runtime": runtime,
        }

    coarse_config = dict(proposer_config)
    coarse_config["proposer_type"] = "grounding_dino_sahi"
    coarse_result = _run_grounding_dino_sahi(image_path, coarse_config)
    coarse_detections = coarse_result.get("detections", [])
    runtime["coarse_runtime"] = coarse_result.get("runtime", {})
    runtime["coarse_detection_count"] = len(coarse_detections)

    if not coarse_result.get("runtime", {}).get("available"):
        runtime["available"] = False
        runtime["mode"] = "missing_dependencies"
        runtime["reason"] = coarse_result.get("runtime", {}).get("reason", runtime["reason"])
        return {
            "proposer_type": "grounding_dino_sam3",
            "detections": [],
            "runtime": runtime,
        }

    try:
        refined_detections, sam_runtime = _refine_with_sam3(image_path, coarse_detections, proposer_config)
        runtime.update(sam_runtime)
        runtime["mode"] = "real"
    except Exception as exc:
        runtime["mode"] = "sam3_unavailable_fallback"
        runtime["sam3_load_error"] = str(exc)
        runtime["sam3_fallback_to_coarse"] = True
        runtime["sam3_refine_input_count"] = 0
        runtime["sam3_refined_detection_count"] = len(coarse_detections)
        refined_detections = coarse_detections
    return {
        "proposer_type": "grounding_dino_sam3",
        "detections": refined_detections,
        "runtime": runtime,
    }


def _infer_grounding_dino_slices(image_path: str, proposer_config: Dict):
    torch = _import_torch()
    processor, model, device = _get_grounding_dino_backend(
        proposer_config.get("model_id", "IDEA-Research/grounding-dino-tiny"),
        proposer_config.get("device", "auto"),
    )
    captions = _resolve_captions(proposer_config)
    slice_size = int(proposer_config.get("slice_size", 640))
    slice_overlap_ratio = float(proposer_config.get("slice_overlap_ratio", 0.2))
    box_threshold = float(proposer_config.get("box_threshold", 0.25))
    text_threshold = float(proposer_config.get("text_threshold", 0.25))
    nms_iou_threshold = float(proposer_config.get("nms_iou_threshold", 0.5))
    min_box_area_ratio = float(proposer_config.get("min_box_area_ratio", 0.0))
    max_box_area_ratio = float(proposer_config.get("max_box_area_ratio", 1.0))

    with Image.open(image_path).convert("RGB") as image:
        image_area = float(image.width * image.height)
        slices = generate_image_slices(image.size, slice_size=slice_size, overlap_ratio=slice_overlap_ratio)
        detections = []
        per_caption_counts = {}
        filtered_small = 0
        filtered_large = 0

        for caption in captions:
            caption_count = 0
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
                    detection = {
                        "bbox_xyxy": [
                            int(round(x1 + slice_region["x1"])),
                            int(round(y1 + slice_region["y1"])),
                            int(round(x2 + slice_region["x1"])),
                            int(round(y2 + slice_region["y1"])),
                        ],
                        "confidence": round(float(score), 4),
                        "label": str(label),
                        "caption": caption,
                        "source": "grounding_dino_sahi",
                    }
                    area_ratio = _box_area_ratio(detection["bbox_xyxy"], image_area)
                    if area_ratio < min_box_area_ratio:
                        filtered_small += 1
                        continue
                    if area_ratio > max_box_area_ratio:
                        filtered_large += 1
                        continue

                    detections.append(detection)
                    caption_count += 1
            per_caption_counts[caption] = caption_count

    merged = non_max_suppression(detections, iou_threshold=nms_iou_threshold)
    runtime = {
        "device": device,
        "caption_count": len(captions),
        "per_caption_detection_count": per_caption_counts,
        "slice_count": len(slices),
        "raw_detection_count": len(detections),
        "merged_detection_count": len(merged),
        "filtered_small_count": filtered_small,
        "filtered_large_count": filtered_large,
        "box_threshold": box_threshold,
        "text_threshold": text_threshold,
        "nms_iou_threshold": nms_iou_threshold,
    }
    return merged, runtime


def _refine_with_sam3(image_path: str, coarse_detections: List[Dict], proposer_config: Dict):
    torch = _import_torch()
    processor, model, device = _get_sam3_backend(
        proposer_config.get("sam3_model_id", "facebook/sam3"),
        proposer_config.get("device", "auto"),
    )
    max_refine_boxes = int(proposer_config.get("sam3_max_refine_boxes", 48))
    mask_threshold = float(proposer_config.get("sam3_mask_threshold", 0.5))
    score_threshold = float(proposer_config.get("sam3_score_threshold", 0.5))
    box_iou_threshold = float(proposer_config.get("sam3_box_iou_threshold", 0.1))
    multimask_output = bool(proposer_config.get("sam3_multimask_output", False))

    selected = sorted(
        [item for item in coarse_detections if len(item.get("bbox_xyxy", [])) == 4],
        key=lambda item: item.get("confidence", 0.0),
        reverse=True,
    )[:max_refine_boxes]
    if not selected:
        return [], {
            "sam3_device": device,
            "sam3_refine_input_count": 0,
            "sam3_refined_detection_count": 0,
            "sam3_filtered_low_score_count": 0,
            "sam3_filtered_low_iou_count": 0,
        }

    with Image.open(image_path).convert("RGB") as image:
        input_boxes = [[detection["bbox_xyxy"] for detection in selected]]
        input_labels = [[1 for _ in selected]]
        inputs = processor(
            images=image,
            input_boxes=input_boxes,
            input_boxes_labels=input_labels,
            return_tensors="pt",
        )
        inputs = {key: value.to(device) if hasattr(value, "to") else value for key, value in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs, multimask_output=multimask_output)

        results = processor.post_process_instance_segmentation(
            outputs,
            threshold=score_threshold,
            mask_threshold=mask_threshold,
            target_sizes=inputs.get("original_sizes").tolist(),
        )[0]

    result_masks = results.get("masks", [])
    result_boxes = results.get("boxes", [])
    result_scores = results.get("scores", [])
    refined_detections = []
    filtered_low_score = 0
    filtered_low_iou = 0

    for coarse_detection, refined_box, refined_score, refined_mask in zip(selected, result_boxes, result_scores, result_masks):
        score = float(refined_score)
        if score < score_threshold:
            filtered_low_score += 1
            continue

        if hasattr(refined_box, "tolist"):
            refined_box = refined_box.tolist()
        bbox_xyxy = [int(round(value)) for value in refined_box]
        if _calculate_iou(coarse_detection["bbox_xyxy"], bbox_xyxy) < box_iou_threshold:
            filtered_low_iou += 1
            continue

        mask_area = _mask_area(refined_mask)
        refined_detections.append({
            "bbox_xyxy": bbox_xyxy,
            "confidence": round(score, 4),
            "label": coarse_detection.get("label", "product"),
            "caption": coarse_detection.get("caption", ""),
            "source": "grounding_dino_sam3",
            "coarse_bbox_xyxy": list(coarse_detection["bbox_xyxy"]),
            "coarse_confidence": coarse_detection.get("confidence"),
            "mask_area": mask_area,
        })

    merged = non_max_suppression(
        refined_detections,
        iou_threshold=float(proposer_config.get("nms_iou_threshold", 0.5)),
    )
    runtime = {
        "sam3_device": device,
        "sam3_refine_input_count": len(selected),
        "sam3_refined_detection_count": len(merged),
        "sam3_raw_refined_count": len(refined_detections),
        "sam3_filtered_low_score_count": filtered_low_score,
        "sam3_filtered_low_iou_count": filtered_low_iou,
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


def _box_area_ratio(bbox_xyxy: List[float], image_area: float) -> float:
    if image_area <= 0 or len(bbox_xyxy) != 4:
        return 0.0

    x1, y1, x2, y2 = bbox_xyxy
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    return (width * height) / image_area


def _mask_area(mask) -> int:
    if hasattr(mask, "sum"):
        value = mask.sum()
        if hasattr(value, "item"):
            return int(value.item())
        return int(value)
    return 0


def _resolve_captions(proposer_config: Dict) -> List[str]:
    captions = proposer_config.get("captions")
    if captions is None:
        captions = [proposer_config.get("caption", "product")]
    elif not isinstance(captions, list):
        captions = [captions]

    normalized = []
    seen = set()
    for caption in captions:
        if caption is None:
            continue
        text = str(caption).strip()
        if not text:
            continue
        if text[-1] not in ".!?":
            text = f"{text}."
        if text not in seen:
            normalized.append(text)
            seen.add(text)

    if not normalized:
        normalized.append("product.")
    return normalized


def _get_grounding_dino_backend(model_id: str, requested_device: str = "auto"):
    global _GROUNDING_DINO_BACKEND
    if (
        _GROUNDING_DINO_BACKEND
        and _GROUNDING_DINO_BACKEND["model_id"] == model_id
        and _GROUNDING_DINO_BACKEND["requested_device"] == requested_device
    ):
        return (
            _GROUNDING_DINO_BACKEND["processor"],
            _GROUNDING_DINO_BACKEND["model"],
            _GROUNDING_DINO_BACKEND["device"],
        )

    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    torch = _import_torch()

    if requested_device == "cpu":
        device = "cpu"
    elif requested_device == "cuda":
        device = "cuda"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id)
    model.to(device)
    model.eval()

    _GROUNDING_DINO_BACKEND = {
        "model_id": model_id,
        "requested_device": requested_device,
        "processor": processor,
        "model": model,
        "device": device,
    }
    return processor, model, device


def _get_sam3_backend(model_id: str, requested_device: str = "auto"):
    global _SAM3_BACKEND
    if (
        _SAM3_BACKEND
        and _SAM3_BACKEND["model_id"] == model_id
        and _SAM3_BACKEND["requested_device"] == requested_device
    ):
        return (
            _SAM3_BACKEND["processor"],
            _SAM3_BACKEND["model"],
            _SAM3_BACKEND["device"],
        )

    from transformers import Sam3Model, Sam3Processor
    torch = _import_torch()

    if requested_device == "cpu":
        device = "cpu"
    elif requested_device == "cuda":
        device = "cuda"
    else:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    processor = Sam3Processor.from_pretrained(model_id)
    model = Sam3Model.from_pretrained(model_id)
    model.to(device)
    model.eval()

    _SAM3_BACKEND = {
        "model_id": model_id,
        "requested_device": requested_device,
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
