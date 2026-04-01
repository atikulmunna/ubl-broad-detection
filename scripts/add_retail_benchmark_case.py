import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_evaluator import append_benchmark_case


def _parse_bbox(value: str):
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must have exactly 4 comma-separated integers")
    return parts


def main():
    parser = argparse.ArgumentParser(description="Append a benchmark case to the retail evaluation manifest")
    parser.add_argument("--benchmark-file", default="catalog/evaluation/sample_benchmark.json")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--sub-category", default="unknown")
    parser.add_argument("--bbox", required=True, help="x1,y1,x2,y2")
    parser.add_argument("--expected-brand", required=True)
    parser.add_argument("--expected-recognition", required=True)
    parser.add_argument("--expected-product-id", default="")
    parser.add_argument("--detected-brand", default="unknown")
    parser.add_argument("--det-confidence", type=float, default=0.2)
    args = parser.parse_args()

    expected = {
        "brand_key": args.expected_brand,
        "recognition_level": args.expected_recognition,
    }
    if args.expected_product_id:
        expected["matched_product_id"] = args.expected_product_id

    case = {
        "case_id": args.case_id,
        "image_path": args.image_path,
        "sub_category": args.sub_category,
        "detections": [
            {
                "brand": args.detected_brand,
                "confidence": args.det_confidence,
                "bbox_xyxy": _parse_bbox(args.bbox),
            }
        ],
        "expected_instances": [expected],
    }

    append_benchmark_case(args.benchmark_file, case)
    print(json.dumps({"appended_case_id": args.case_id, "benchmark_file": args.benchmark_file}, indent=2))


if __name__ == "__main__":
    main()
