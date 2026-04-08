import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_yolo_training import prepare_yolo_training_workspace


def build_parser():
    parser = argparse.ArgumentParser(description="Prepare a COCO retail dataset for one-class YOLO training.")
    parser.add_argument("--dataset-root", required=True, help="Dataset root with train/valid/test split folders.")
    parser.add_argument(
        "--output-yaml",
        default="",
        help="Optional path for the generated YOLO dataset yaml. Defaults to dataset_root\\retail_one_class_dataset.yaml.",
    )
    parser.add_argument(
        "--class-name",
        action="append",
        dest="class_names",
        help="Class name to include in the YOLO dataset yaml. Repeat for multiple classes.",
    )
    parser.add_argument(
        "--clean-existing",
        action="store_true",
        help="Delete existing .txt labels in each split before regenerating them.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    summary = prepare_yolo_training_workspace(
        dataset_root=args.dataset_root,
        output_yaml_path=args.output_yaml or None,
        class_names=args.class_names or ("product",),
        clean_existing=args.clean_existing,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
