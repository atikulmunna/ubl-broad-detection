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
