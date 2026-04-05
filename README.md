# UBL Broad Detection

Lean experiment repo for shelf-level product detection and benchmarking.

The current goal is simple:
- detect product instances on dense retail shelves
- benchmark proposal quality on real shelf images
- keep later UBL/non-UBL classification as a separate stage

## Scope

- shelf-image benchmark tooling
- crop/query preparation
- catalog and reference helpers for later matching experiments
- a lightweight retail experiment path kept separate from production code

## Evaluation Workflow

- Put shelf images under `catalog/evaluation/images/`
- COCO one-class shelf datasets can be imported into benchmark cases
- Create a case JSON from a shelf image:
  `python scripts/create_retail_case_template.py --image-path catalog\\evaluation\\images\\shelf_001.jpg --case-id shelf_001 --output-file catalog\\evaluation\\case_shelf_001.json --sub-category hair_care`
- Import a COCO split into a benchmark manifest:
  `python scripts/import_retail_coco.py --annotation-file "dataset\\...\\test\\_annotations.coco.json" --images-dir "dataset\\...\\test" --output-file catalog\\evaluation\\imported_test.json --sub-category hair_care`
- Add `detections`, `expected_instances`, and `expected_summary`
- Add `ground_truth_instances` if you want proposal recall/precision and mean IoU metrics
- Render a preview while labeling:
  `python scripts/render_retail_case_preview.py --case-file catalog\\evaluation\\case_shelf_001.json --output-file catalog\\evaluation\\previews\\shelf_001.png`
- Evaluate all cases listed in `catalog/evaluation/sample_benchmark.json`:
  `python scripts/evaluate_retail_benchmark.py`
- Evaluate a proposer against imported benchmark cases:
  `python scripts/evaluate_retail_proposer.py --benchmark-file catalog\\evaluation\\imported_test.json --proposer-type grounding_dino_sahi`

## Notes

- `catalog/evaluation/images/` is for multi-product shelf photos
- `catalog/references/` is only for optional single-product reference images
- `catalog/evaluation/case_template.json` shows the expected shape of a shelf case
- proposal metrics use IoU matching between `detections` and `ground_truth_instances`
- `grounding_dino_sahi` now has an optional real inference path through Hugging Face `transformers`
- sliced inference is built in so the benchmark path can use SAHI-style windowing even before adding the external SAHI package
- to activate real Grounding DINO inference, install the optional proposer dependencies first
