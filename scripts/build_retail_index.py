"""
Build and persist the experimental retail catalog index.

Usage:
    python scripts/build_retail_index.py
    python scripts/build_retail_index.py --reference-root catalog/references --output-dir catalog/index
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.retail_index import INDEX_ROOT, REFERENCE_ROOT, build_catalog_index


def parse_args():
    parser = argparse.ArgumentParser(description="Build the experimental retail catalog index.")
    parser.add_argument(
        "--reference-root",
        default=str(REFERENCE_ROOT),
        help="Directory containing catalog reference images.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(INDEX_ROOT),
        help="Directory where the built index files will be written.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    reference_root = Path(args.reference_root)
    output_dir = Path(args.output_dir)

    index = build_catalog_index(reference_root=reference_root)
    saved = index.save(output_dir)

    print(f"Built retail index with {index.size} references and dimension {index.dimension}")
    print(f"Manifest: {saved['manifest_path']}")
    print(f"Embeddings: {saved['embeddings_path']}")


if __name__ == "__main__":
    main()
