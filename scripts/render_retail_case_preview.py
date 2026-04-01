import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_case_tools import render_case_preview


def main():
    parser = argparse.ArgumentParser(description="Render a preview image for a shelf benchmark case")
    parser.add_argument("--case-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--image-base-dir", default="catalog/evaluation")
    args = parser.parse_args()

    with open(args.case_file, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    case = payload
    if isinstance(payload, dict) and "cases" in payload:
        raise ValueError("Preview renderer expects a single case JSON file, not a benchmark manifest")

    render_case_preview(case=case, output_path=args.output_file, image_base_dir=args.image_base_dir)
    print(f"Wrote preview: {args.output_file}")


if __name__ == "__main__":
    main()
