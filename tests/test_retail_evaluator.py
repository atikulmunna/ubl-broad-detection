import json
import os
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_embedding import create_embedder
from utils.retail_evaluator import evaluate_benchmark_cases, load_benchmark_cases, save_evaluation_report
from utils.retail_index import build_catalog_index
from utils.retail_runtime import reset_runtime_index_cache


def _catalog():
    return {
        "brands": {
            "dove": {
                "display_name": "Dove",
                "is_ubl": True,
                "categories": ["hair_care"],
                "skus": [
                    {
                        "product_id": "dove-hfr-small",
                        "display_name": "Dove Hair Fall Rescue Small",
                        "categories": ["hair_care"],
                        "pack_type": "bottle",
                        "reference_images": ["dove-hfr-small/front.png"],
                    }
                ],
            },
            "unknown": {
                "display_name": "Unknown",
                "is_ubl": False,
                "categories": [],
                "skus": [],
            },
        }
    }


def test_load_benchmark_cases_supports_object_payload(tmp_path: Path):
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(json.dumps({"cases": [{"case_id": "one"}]}), encoding="utf-8")

    cases = load_benchmark_cases(str(benchmark_path))

    assert len(cases) == 1
    assert cases[0]["case_id"] == "one"


def test_evaluate_benchmark_cases_scores_brand_and_sku_matches(tmp_path: Path):
    reset_runtime_index_cache()

    ref_dir = tmp_path / "refs" / "dove-hfr-small"
    ref_dir.mkdir(parents=True)
    ref_path = ref_dir / "front.png"
    Image.new("RGB", (20, 20), (30, 220, 30)).save(ref_path)

    image_path = tmp_path / "scene.png"
    Image.new("RGB", (20, 20), (30, 220, 30)).save(image_path)

    embedder = create_embedder("file_content_hash", dimension=8)
    index = build_catalog_index(
        embedder=embedder,
        catalog=_catalog(),
        reference_root=tmp_path / "refs",
        embedder_type="file_content_hash",
    )
    index_dir = tmp_path / "index"
    index.save(index_dir)

    cases = [
        {
            "case_id": "known_dove",
            "image_path": str(image_path),
            "sub_category": "hair_care",
            "detections": [
                {
                    "brand": "unknown",
                    "confidence": 0.2,
                    "bbox_xyxy": [0, 0, 20, 20],
                }
            ],
            "expected_instances": [
                {
                    "brand_key": "dove",
                    "matched_product_id": "dove-hfr-small",
                    "recognition_level": "sku_known",
                }
            ],
        }
    ]
    runtime_config = {
        "use_saved_index": True,
        "index_dir": str(index_dir),
        "embedder_type": "file_content_hash",
        "crop_expand_ratio": 0.0,
    }

    report = evaluate_benchmark_cases(
        cases=cases,
        runtime_config=runtime_config,
        top_k_skus=5,
        catalog=_catalog(),
    )

    assert report["summary"]["total_cases"] == 1
    assert report["summary"]["passed_cases"] == 1
    assert report["summary"]["brand_accuracy"] == 1.0
    assert report["summary"]["sku_accuracy"] == 1.0
    assert report["summary"]["recognition_accuracy"] == 1.0
    assert report["cases"][0]["passed"] is True


def test_save_evaluation_report_writes_json(tmp_path: Path):
    report = {"summary": {"total_cases": 1}, "cases": []}
    output_path = tmp_path / "reports" / "latest.json"

    save_evaluation_report(report, str(output_path))

    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["summary"]["total_cases"] == 1
