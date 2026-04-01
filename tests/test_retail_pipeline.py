import sys
import os
from pathlib import Path

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.retail_index import build_catalog_index
from utils.retail_embedding import create_embedder
from utils.retail_pipeline import process_retail_detections
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


def test_process_retail_detections_uses_saved_index_with_query_inputs(tmp_path: Path, monkeypatch):
    reset_runtime_index_cache()

    ref_dir = tmp_path / "refs" / "dove-hfr-small"
    ref_dir.mkdir(parents=True)
    ref_path = ref_dir / "front.png"
    Image.new("RGB", (20, 20), (20, 200, 20)).save(ref_path)

    embedder = create_embedder("file_content_hash", dimension=8)
    index = build_catalog_index(
        embedder=embedder,
        catalog=_catalog(),
        reference_root=tmp_path / "refs",
        embedder_type="file_content_hash",
    )
    index_dir = tmp_path / "index"
    index.save(index_dir)

    image_path = tmp_path / "scene.png"
    Image.new("RGB", (100, 100), (0, 0, 0)).save(image_path)
    with Image.open(image_path).convert("RGB") as image:
        for x in range(10, 30):
            for y in range(10, 30):
                image.putpixel((x, y), (20, 200, 20))
        image.save(image_path)

    detections = [
        {"brand": "unknown", "confidence": 0.25, "bbox_xyxy": [10, 10, 30, 30]},
    ]
    runtime_config = {
        "use_saved_index": True,
        "index_dir": str(index_dir),
        "embedder_type": "file_content_hash",
    }

    def fake_attach_query_crops(image_path, detections, output_dir):
        updated = []
        for detection in detections:
            item = dict(detection)
            item["query_image_path"] = str(ref_path)
            item["query_source"] = "crop"
            updated.append(item)
        return updated

    monkeypatch.setattr("utils.retail_pipeline.attach_query_crops", fake_attach_query_crops)

    result = process_retail_detections(
        image_path=str(image_path),
        detections=detections,
        sub_category="hair_care",
        runtime_config=runtime_config,
        top_k_skus=5,
        catalog=_catalog(),
    )

    assert result["index_runtime"]["index_status"] == "loaded"
    assert result["index_runtime"]["index_embedder_type"] == "file_content_hash"
    assert result["query_preparation"]["crop_ready"] == 1
    assert result["summary_counts"]["total_products"] == 1
    assert result["instances"][0]["match_source"] == "index_sku"
    assert result["instances"][0]["brand_key"] == "dove"
