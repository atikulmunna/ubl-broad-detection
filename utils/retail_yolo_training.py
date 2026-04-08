"""Helpers for preparing and training a one-class YOLO retail detector."""

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml


SUPPORTED_SPLITS = ("train", "valid", "test")
DEFAULT_CLASS_NAMES = ("product",)


def prepare_yolo_labels_from_coco(dataset_root: str, class_id: int = 0, clean_existing: bool = False) -> Dict:
    root = Path(dataset_root)
    summary = {"dataset_root": str(root.resolve()), "splits": {}}

    for split in SUPPORTED_SPLITS:
        split_dir = root / split
        annotation_path = split_dir / "_annotations.coco.json"
        if not annotation_path.exists():
            continue

        if clean_existing:
            for label_path in split_dir.glob("*.txt"):
                label_path.unlink()

        payload = json.loads(annotation_path.read_text(encoding="utf-8"))
        images_by_id = {item["id"]: item for item in payload.get("images", [])}
        annotations_by_image = {}
        for annotation in payload.get("annotations", []):
            annotations_by_image.setdefault(annotation.get("image_id"), []).append(annotation)

        image_count = 0
        label_count = 0
        empty_label_count = 0
        for image_id, image_record in images_by_id.items():
            image_path = split_dir / image_record["file_name"]
            if not image_path.exists():
                continue

            yolo_lines = []
            for annotation in annotations_by_image.get(image_id, []):
                bbox = annotation.get("bbox", [])
                converted = coco_bbox_to_yolo_line(
                    bbox=bbox,
                    image_width=image_record.get("width"),
                    image_height=image_record.get("height"),
                    class_id=class_id,
                )
                if converted is not None:
                    yolo_lines.append(converted)

            label_path = image_path.with_suffix(".txt")
            label_path.write_text("\n".join(yolo_lines), encoding="utf-8")
            image_count += 1
            label_count += len(yolo_lines)
            if not yolo_lines:
                empty_label_count += 1

        summary["splits"][split] = {
            "image_count": image_count,
            "label_count": label_count,
            "empty_label_count": empty_label_count,
            "annotation_path": str(annotation_path.resolve()),
        }

    return summary


def write_yolo_dataset_yaml(dataset_root: str, output_path: str, class_names: Iterable[str]) -> Dict:
    root = Path(dataset_root).resolve()
    names = list(class_names)
    payload = {
        "path": str(root),
        "train": "train",
        "val": "valid",
        "test": "test",
        "nc": len(names),
        "names": names,
    }
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return payload


def prepare_yolo_training_workspace(
    dataset_root: str,
    output_yaml_path: Optional[str] = None,
    class_names: Iterable[str] = DEFAULT_CLASS_NAMES,
    class_id: int = 0,
    clean_existing: bool = False,
) -> Dict:
    root = Path(dataset_root).resolve()
    yaml_path = Path(output_yaml_path).resolve() if output_yaml_path else root / "retail_one_class_dataset.yaml"
    label_summary = prepare_yolo_labels_from_coco(
        dataset_root=str(root),
        class_id=class_id,
        clean_existing=clean_existing,
    )
    dataset_yaml = write_yolo_dataset_yaml(
        dataset_root=str(root),
        output_path=str(yaml_path),
        class_names=class_names,
    )
    return {
        "dataset_root": str(root),
        "dataset_yaml_path": str(yaml_path),
        "class_names": list(class_names),
        "label_summary": label_summary,
        "dataset_yaml": dataset_yaml,
    }


def build_yolo_train_args(
    dataset_yaml_path: str,
    model: str = "yolo11n.pt",
    project: str = "outputs/yolo_train",
    name: str = "retail_one_class",
    epochs: int = 50,
    imgsz: int = 1280,
    batch: int = 8,
    device: str = "",
    workers: int = 4,
    patience: int = 20,
    cache: bool = False,
) -> Dict:
    return {
        "data": str(Path(dataset_yaml_path).resolve()),
        "model": model,
        "project": project,
        "name": name,
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
        "device": device,
        "workers": workers,
        "patience": patience,
        "cache": cache,
    }


def summarize_yolo_training_result(result, train_args: Dict) -> Dict:
    save_dir = getattr(result, "save_dir", None)
    return {
        "model": train_args.get("model"),
        "data": train_args.get("data"),
        "epochs": train_args.get("epochs"),
        "imgsz": train_args.get("imgsz"),
        "batch": train_args.get("batch"),
        "device": train_args.get("device"),
        "project": train_args.get("project"),
        "name": train_args.get("name"),
        "save_dir": str(save_dir) if save_dir is not None else None,
    }


def coco_bbox_to_yolo_line(bbox: List[float], image_width: int, image_height: int, class_id: int = 0):
    if len(bbox) != 4 or not image_width or not image_height:
        return None

    x, y, width, height = bbox
    if width <= 0 or height <= 0:
        return None

    x_center = (x + width / 2.0) / image_width
    y_center = (y + height / 2.0) / image_height
    norm_width = width / image_width
    norm_height = height / image_height

    values = [class_id, x_center, y_center, norm_width, norm_height]
    return " ".join(_format_float(value) for value in values)


def _format_float(value):
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.6f}".rstrip("0").rstrip(".")
