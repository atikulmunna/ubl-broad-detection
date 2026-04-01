# UBL Broad Detection

Experimental retail detection workspace for broad product discovery across UBL and non-UBL items.

This repository was split from the `labs` branch of the original `UBL-standalone` project so we can explore catalog-first retail detection, open-set recognition, and future SAM-assisted product proposal work without touching the production repo.

## Focus

- broad retail product detection
- catalog-aware brand and SKU recognition
- reduced dependence on repeated annotation for new product launches
- safe experimentation outside the production codebase

## Origin

Original repository:

- https://github.com/Yok4ai/UBL-standalone

This repo starts from the `labs` branch snapshot plus the early `retail_experiment` scaffolding.

## Current State

- existing UBL retail pipeline copied from the source repo
- experimental catalog metadata in `config/standards/retail_catalog.yaml`
- experimental analyzer path for `retail_experiment`
- roadmap in `docs/plans/2026-03-31-retail-catalog-roadmap.md`

## Catalog Workflow

- Put product reference images under `catalog/references/<product_id>/`
- Or declare `reference_images` directly in `config/standards/retail_catalog.yaml`
- Audit readiness with:
  `python scripts/build_retail_index.py --audit-only`
- Write an onboarding JSON report with:
  `python scripts/build_retail_index.py --audit-only --report-file catalog/index/onboarding-report.json`
- Build the local index with:
  `python scripts/build_retail_index.py`

## Small-Batch Evaluation

- Put a few benchmark cases in `catalog/evaluation/sample_benchmark.json`
- Put full shelf images under `catalog/evaluation/images/`
- Each case should point to a real shelf image, the detections you want to test, and expected outputs
- Relative image paths in the manifest are resolved from the manifest folder
- Run:
  `python scripts/evaluate_retail_benchmark.py`
- The latest report is written to:
  `catalog/evaluation/latest_report.json`
- A case can contain many detections from one shelf image
- `expected_summary` can be used to check shelf-level counts such as `ubl_count`, `competitor_count`, and `unknown_count`
- `catalog/references/` is for single-product reference images only
- To append one quick single-detection case from the command line:
  `python scripts/add_retail_benchmark_case.py --case-id demo --image-path images\\shelf_01.jpg --sub-category hair_care --bbox 0,0,64,64 --expected-brand dove --expected-recognition brand_known`
- To append a full multi-product shelf case from JSON:
  `python scripts/add_retail_benchmark_case.py --case-json catalog\\evaluation\\case_mixed_shelf.json`
