"""
Product proposer abstractions for shelf detection experiments.
"""

from pathlib import Path
from typing import Dict, List


def run_product_proposer(image_path: str, proposer_config: Dict) -> Dict:
    proposer_type = proposer_config.get("proposer_type", "mock_ground_truth")

    if proposer_type == "mock_ground_truth":
        detections = proposer_config.get("mock_detections", [])
        return {
            "proposer_type": proposer_type,
            "detections": [dict(item) for item in detections],
            "runtime": {
                "available": True,
                "mode": "mock",
            },
        }

    if proposer_type == "grounding_dino_sahi":
        return {
            "proposer_type": proposer_type,
            "detections": [],
            "runtime": {
                "available": False,
                "mode": "stub",
                "reason": "Grounding DINO + SAHI integration scaffold not wired to inference yet",
                "image_path": str(Path(image_path)),
                "caption": proposer_config.get("caption", "product"),
                "slice_size": proposer_config.get("slice_size", 640),
                "slice_overlap_ratio": proposer_config.get("slice_overlap_ratio", 0.2),
            },
        }

    raise ValueError(f"Unknown proposer_type: {proposer_type}")
