import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_case_tools import create_case_template_from_image, save_case_json


def main():
    parser = argparse.ArgumentParser(description="Create a shelf benchmark case template from an image")
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--sub-category", default="unknown")
    parser.add_argument("--image-base-dir", default="catalog/evaluation")
    args = parser.parse_args()

    case = create_case_template_from_image(
        image_path=args.image_path,
        case_id=args.case_id,
        sub_category=args.sub_category,
        image_base_dir=args.image_base_dir,
    )
    save_case_json(case, args.output_file)
    print(f"Wrote case template: {args.output_file}")


if __name__ == "__main__":
    main()
