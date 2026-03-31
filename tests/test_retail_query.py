import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.retail_query import build_query_asset, build_query_asset_from_detection


def test_build_query_asset_preserves_image_path_and_token():
    asset = build_query_asset(
        image_path="crops/item-1.png",
        fallback_token="dove",
        source="crop",
    )

    assert asset["image_path"] == "crops/item-1.png"
    assert asset["fallback_token"] == "dove"
    assert asset["source"] == "crop"


def test_build_query_asset_from_detection_prefers_real_image_path():
    asset = build_query_asset_from_detection({
        "query_image_path": "crops/item-1.png",
        "catalog_query": "legacy-token",
        "brand": "dove",
        "query_source": "crop",
    })

    assert asset["image_path"] == "crops/item-1.png"
    assert asset["fallback_token"] == "dove"
    assert asset["source"] == "crop"


def test_build_query_asset_from_detection_falls_back_to_brand_token():
    asset = build_query_asset_from_detection({
        "brand": "nivea",
    })

    assert asset["image_path"] == ""
    assert asset["fallback_token"] == "nivea"
    assert asset["source"] == "detection"
