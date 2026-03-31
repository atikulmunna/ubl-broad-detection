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

from utils.retail_index import (
    INDEX_ROOT,
    REFERENCE_ROOT,
    audit_catalog_references,
    build_catalog_index,
    build_onboarding_report,
)


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
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Only report catalog reference readiness without writing an index.",
    )
    parser.add_argument(
        "--report-file",
        default="",
        help="Optional JSON file path for writing the onboarding report.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    reference_root = Path(args.reference_root)
    output_dir = Path(args.output_dir)

    audit = audit_catalog_references(reference_root=reference_root)
    report = build_onboarding_report(reference_root=reference_root)
    print(
        "Catalog reference audit: "
        f"{audit['summary']['ready_count']} ready, "
        f"{audit['summary']['missing_count']} missing, "
        f"{audit['summary']['total_skus']} total"
    )

    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(__import__("json").dumps(report, indent=2), encoding="utf-8")
        print(f"Report: {report_path}")

    if args.audit_only:
        return

    index = build_catalog_index(reference_root=reference_root)
    saved = index.save(output_dir)

    print(f"Built retail index with {index.size} references and dimension {index.dimension}")
    print(f"Manifest: {saved['manifest_path']}")
    print(f"Embeddings: {saved['embeddings_path']}")


if __name__ == "__main__":
    main()
