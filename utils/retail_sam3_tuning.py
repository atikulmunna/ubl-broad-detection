"""
Helpers for running and summarizing SAM3 refinement tuning experiments.
"""

import itertools
import json
from pathlib import Path
from typing import Dict, List


def build_sam3_tuning_configs(base_config: Dict, tuning_options: Dict[str, List]) -> List[Dict]:
    keys = [key for key, values in tuning_options.items() if values]
    if not keys:
        return [dict(base_config)]

    configs = []
    value_lists = [tuning_options[key] for key in keys]
    for values in itertools.product(*value_lists):
        config = dict(base_config)
        for key, value in zip(keys, values):
            config[key] = value
        configs.append(config)
    return configs


def summarize_sam3_tuning_runs(run_summaries: List[Dict]) -> Dict:
    ranked = sorted(
        run_summaries,
        key=lambda item: (
            float(item.get("average_detection_count", 0.0)),
            float(item.get("average_retention_ratio", 0.0)),
        ),
        reverse=True,
    )
    return {
        "run_count": len(ranked),
        "best_run": ranked[0] if ranked else None,
        "runs": ranked,
    }


def save_sam3_tuning_summary(summary: Dict, output_path: str) -> None:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
