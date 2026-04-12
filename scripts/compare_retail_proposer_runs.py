import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_proposer_compare import (
    compare_manifests,
    load_manifest,
    render_side_by_side_previews,
    save_comparison_report,
)


def main():
    parser = argparse.ArgumentParser(description="Compare two proposer inference manifests and render side-by-side previews.")
    parser.add_argument("--left-manifest", required=True)
    parser.add_argument("--right-manifest", required=True)
    parser.add_argument("--left-name", default="left")
    parser.add_argument("--right-name", default="right")
    parser.add_argument("--output-report", default="outputs/inference_compare/comparison.json")
    parser.add_argument("--output-preview-dir", default="outputs/inference_compare/previews")
    args = parser.parse_args()

    left_manifest = load_manifest(args.left_manifest)
    right_manifest = load_manifest(args.right_manifest)
    report = compare_manifests(
        left_manifest=left_manifest,
        right_manifest=right_manifest,
        left_name=args.left_name,
        right_name=args.right_name,
    )
    preview_paths = render_side_by_side_previews(report, args.output_preview_dir)
    report["summary"]["preview_count"] = len(preview_paths)
    save_comparison_report(report, args.output_report)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
