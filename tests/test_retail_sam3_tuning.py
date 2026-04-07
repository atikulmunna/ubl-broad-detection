import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.retail_sam3_tuning import (
    build_sam3_tuning_configs,
    save_sam3_tuning_summary,
    summarize_sam3_tuning_runs,
)


def test_build_sam3_tuning_configs_expands_cartesian_product():
    configs = build_sam3_tuning_configs(
        base_config={"proposer_type": "grounding_dino_sam3"},
        tuning_options={
            "sam3_score_threshold": [0.2, 0.35],
            "sam3_box_iou_threshold": [0.0, 0.05],
        },
    )

    assert len(configs) == 4
    assert configs[0]["proposer_type"] == "grounding_dino_sam3"


def test_summarize_sam3_tuning_runs_ranks_higher_detection_count_first():
    summary = summarize_sam3_tuning_runs([
        {"run_id": 1, "average_detection_count": 2, "average_retention_ratio": 0.1},
        {"run_id": 2, "average_detection_count": 5, "average_retention_ratio": 0.05},
    ])

    assert summary["run_count"] == 2
    assert summary["best_run"]["run_id"] == 2


def test_save_sam3_tuning_summary_writes_json(tmp_path: Path):
    output_path = tmp_path / "summary.json"
    save_sam3_tuning_summary({"run_count": 1}, str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["run_count"] == 1
