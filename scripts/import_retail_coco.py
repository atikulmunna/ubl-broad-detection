import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_coco import build_cases_from_coco, save_benchmark_manifest


def main():
    parser = argparse.ArgumentParser(description="Import a COCO retail dataset into the shelf benchmark format")
    parser.add_argument("--annotation-file", required=True)
    parser.add_argument("--images-dir", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--sub-category", default="unknown")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    cases = build_cases_from_coco(
        annotation_path=args.annotation_file,
        images_dir=args.images_dir,
        sub_category=args.sub_category,
        limit=args.limit or None,
    )
    save_benchmark_manifest(cases, args.output_file)
    print(f"Wrote {len(cases)} cases to {args.output_file}")


if __name__ == "__main__":
    main()
