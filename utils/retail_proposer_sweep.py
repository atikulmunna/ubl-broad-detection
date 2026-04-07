"""
Sweep helpers for shelf product proposer experiments.
"""

import itertools
import json
from pathlib import Path
from typing import Dict, List

from utils.retail_proposer_benchmark import evaluate_proposer_on_cases


def build_sweep_configs(base_config: Dict, sweep_options: Dict[str, List]) -> List[Dict]:
    keys = [key for key, values in sweep_options.items() if values]
    if not keys:
        return [dict(base_config)]

    configs = []
    value_lists = [sweep_options[key] for key in keys]
    for values in itertools.product(*value_lists):
        config = dict(base_config)
        for key, value in zip(keys, values):
            config[key] = value
        configs.append(config)
    return configs


def evaluate_proposer_sweep(cases: List[Dict], base_config: Dict, sweep_options: Dict[str, List],
                            iou_threshold: float = 0.5, top_k: int = 5) -> Dict:
    runs = []
    configs = build_sweep_configs(base_config, sweep_options)

    for index, config in enumerate(configs, start=1):
        report = evaluate_proposer_on_cases(cases=cases, proposer_config=config, iou_threshold=iou_threshold)
        runs.append({
            "run_id": index,
            "config": config,
            "summary": report["summary"],
            "report": report,
        })

    ranked_runs = sorted(
        runs,
        key=lambda item: (
            _metric_or_default(item["summary"].get("proposal_recall")),
            _metric_or_default(item["summary"].get("proposal_precision")),
            _metric_or_default(item["summary"].get("proposal_mean_iou")),
        ),
        reverse=True,
    )

    return {
        "run_count": len(ranked_runs),
        "top_k": top_k,
        "best_run": _strip_report(ranked_runs[0]) if ranked_runs else None,
        "top_runs": [_strip_report(run) for run in ranked_runs[:top_k]],
        "all_runs": [_strip_report(run) for run in ranked_runs],
    }


def save_best_run_config(sweep_report: Dict, output_path: str) -> None:
    best_run = sweep_report.get("best_run")
    if not best_run:
        raise ValueError("Sweep report does not contain a best_run")

    payload = {
        "config": best_run["config"],
        "summary": best_run["summary"],
    }
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _strip_report(run: Dict) -> Dict:
    return {
        "run_id": run["run_id"],
        "config": run["config"],
        "summary": run["summary"],
    }


def _metric_or_default(value):
    if value is None:
        return -1.0
    return float(value)
