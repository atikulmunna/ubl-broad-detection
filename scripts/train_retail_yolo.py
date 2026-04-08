import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_yolo_training import (
    build_yolo_train_args,
    prepare_yolo_training_workspace,
    summarize_yolo_training_result,
)


def build_parser():
    parser = argparse.ArgumentParser(description="Train a one-class YOLO retail detector from a COCO shelf dataset.")
    parser.add_argument("--dataset-root", required=True, help="Dataset root with train/valid/test split folders.")
    parser.add_argument("--dataset-yaml", default="", help="Optional YOLO dataset yaml path.")
    parser.add_argument("--model", default="yolo11n.pt", help="Ultralytics model checkpoint to fine-tune.")
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs.")
    parser.add_argument("--imgsz", type=int, default=1280, help="Training image size.")
    parser.add_argument("--batch", type=int, default=8, help="Training batch size.")
    parser.add_argument("--device", default="", help="Training device, for example cuda or 0.")
    parser.add_argument("--workers", type=int, default=4, help="Dataloader workers.")
    parser.add_argument("--patience", type=int, default=20, help="Early stopping patience.")
    parser.add_argument("--project", default="outputs/yolo_train", help="Ultralytics project directory.")
    parser.add_argument("--name", default="retail_one_class", help="Ultralytics run name.")
    parser.add_argument("--cache", action="store_true", help="Enable Ultralytics image caching.")
    parser.add_argument(
        "--clean-existing-labels",
        action="store_true",
        help="Delete existing split label txt files before regeneration.",
    )
    parser.add_argument(
        "--summary-file",
        default="",
        help="Optional JSON file to save the preparation and training summary.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    workspace = prepare_yolo_training_workspace(
        dataset_root=args.dataset_root,
        output_yaml_path=args.dataset_yaml or None,
        clean_existing=args.clean_existing_labels,
    )

    from ultralytics import YOLO

    train_args = build_yolo_train_args(
        dataset_yaml_path=workspace["dataset_yaml_path"],
        model=args.model,
        project=args.project,
        name=args.name,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        cache=args.cache,
    )
    model = YOLO(train_args.pop("model"))
    result = model.train(**train_args)

    summary = {
        "workspace": workspace,
        "training": summarize_yolo_training_result(
            result=result,
            train_args={"model": args.model, **train_args},
        ),
    }

    if args.summary_file:
        summary_path = Path(args.summary_file)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
