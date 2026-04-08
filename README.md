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
- For dense-shelf evaluation, prefer importing the most heavily annotated cases first:
  `python scripts/import_retail_coco.py --annotation-file "dataset\\...\\test\\_annotations.coco.json" --images-dir "dataset\\...\\test" --output-file catalog\\evaluation\\imported_dense_test.json --sub-category hair_care --sort-by-density --min-ground-truth 10 --limit 10`
- Add `detections`, `expected_instances`, and `expected_summary`
- Add `ground_truth_instances` if you want proposal recall/precision and mean IoU metrics
- Render a preview while labeling:
  `python scripts/render_retail_case_preview.py --case-file catalog\\evaluation\\case_shelf_001.json --output-file catalog\\evaluation\\previews\\shelf_001.png`
- Evaluate all cases listed in `catalog/evaluation/sample_benchmark.json`:
  `python scripts/evaluate_retail_benchmark.py`
- Evaluate a proposer against imported benchmark cases:
  `python scripts/evaluate_retail_proposer.py --benchmark-file catalog\\evaluation\\imported_test.json --proposer-type grounding_dino_sahi`
- Sweep multiple product prompts in one run:
  `python scripts/evaluate_retail_proposer.py --benchmark-file catalog\\evaluation\\imported_dense_test.json --proposer-type grounding_dino_sahi --device cpu --caption-candidate "product" --caption-candidate "products" --caption-candidate "bottle" --caption-candidate "package"`
- Tune thresholds, model choice, and simple area filters from the CLI:
  `python scripts/evaluate_retail_proposer.py --benchmark-file catalog\\evaluation\\imported_dense_test.json --proposer-type grounding_dino_sahi --device cpu --model-id IDEA-Research/grounding-dino-tiny --box-threshold 0.2 --text-threshold 0.15 --nms-iou-threshold 0.4 --min-box-area-ratio 0.00005 --max-box-area-ratio 0.08`
- Run a ranked sweep across several configs:
  `python scripts/sweep_retail_proposer.py --benchmark-file catalog\\evaluation\\imported_dense_test.json --device cpu --model-id IDEA-Research/grounding-dino-tiny --caption-set "product|products|bottle|package" --caption-set "product|products|bottle|container" --box-threshold 0.15 --box-threshold 0.2 --text-threshold 0.1 --text-threshold 0.15 --nms-iou-threshold 0.4 --min-box-area-ratio 0.00005 --max-box-area-ratio 0.08`
- Save the winning sweep config as a reusable baseline:
  `python scripts/sweep_retail_proposer.py --benchmark-file catalog\\evaluation\\imported_dense_test.json --device cuda --model-id IDEA-Research/grounding-dino-tiny --caption-set "product|products|bottle|container" --box-threshold 0.15 --text-threshold 0.1 --nms-iou-threshold 0.4 --min-box-area-ratio 0.00005 --max-box-area-ratio 0.08 --best-config-file config\\proposer\\grounding_dino_sahi_baseline.json`
- Run inference on a few shelf images and save preview overlays:
  `python scripts/infer_retail_images.py --image-dir catalog\\evaluation\\images --limit 3 --config-file config\\proposer\\grounding_dino_sahi_baseline.json --output-dir outputs\\inference`
- Try a category-specific prompt set:
  `python scripts/infer_retail_images.py --image-dir catalog\\evaluation\\images --limit 3 --config-file config\\proposer\\grounding_dino_category_specific.json --output-dir outputs\\inference_category`
- Start a refinement experiment with Grounding DINO proposals and SAM 3 box prompts:
  `python scripts/infer_retail_images.py --image-dir catalog\\evaluation\\images --limit 3 --config-file config\\proposer\\grounding_dino_sam3_experiment.json --output-dir outputs\\inference_sam3`
- Tune SAM3 refinement settings on one or more images:
  `python scripts/tune_retail_sam3.py --image-dir catalog\\evaluation\\images --limit 1 --config-file config\\proposer\\grounding_dino_sam3_experiment.json --output-dir outputs\\sam3_tuning`
- Use the first tuned SAM3 config directly:
  `python scripts/infer_retail_images.py --image-dir catalog\\evaluation\\images --limit 1 --config-file config\\proposer\\grounding_dino_sam3_tuned.json --output-dir outputs\\inference_sam3_tuned`
- Try a whole-product retail prompt set with tuned SAM3:
  `python scripts/infer_retail_images.py --image-dir catalog\\evaluation\\images --limit 3 --config-file config\\proposer\\grounding_dino_sam3_whole_product.json --output-dir outputs\\inference_whole_product`
- Prepare a Roboflow-style COCO shelf dataset for one-class YOLO training:
  `python scripts/prepare_retail_yolo_dataset.py --dataset-root "dataset\\SOS Merged -OneClass-COCO Format"`
- Train a one-class retail detector baseline from the same dataset:
  `python scripts/train_retail_yolo.py --dataset-root "dataset\\SOS Merged -OneClass-COCO Format" --model yolo11n.pt --device cuda --epochs 50 --imgsz 1280 --batch 8 --summary-file outputs\\yolo_train\\summary.json`
- On RTX 50-series GPUs, use a CUDA-capable PyTorch env before running real proposer inference:
  `pip install --upgrade --index-url https://download.pytorch.org/whl/cu130 torch torchvision torchaudio`

## Notes

- `catalog/evaluation/images/` is for multi-product shelf photos
- `catalog/references/` is only for optional single-product reference images
- `catalog/evaluation/case_template.json` shows the expected shape of a shelf case
- proposal metrics use IoU matching between `detections` and `ground_truth_instances`
- `grounding_dino_sahi` now has an optional real inference path through Hugging Face `transformers`
- repeated `--caption-candidate` values are normalized and merged with NMS, which makes prompt tuning easier on dense shelves
- the proposer CLI now exposes model, threshold, NMS, and box-area knobs so dense-shelf tuning does not require code changes
- the sweep CLI ranks configs by recall first, then precision, then mean IoU so we can keep a current benchmark baseline
- sliced inference is built in so the benchmark path can use SAHI-style windowing even before adding the external SAHI package
- to activate real Grounding DINO inference, install the optional proposer dependencies first
- the current working GPU path in local testing uses `torch 2.11.0+cu130`, which works with the RTX 5060 Laptop GPU
- a `grounding_dino_sam3` proposer path now exists to refine coarse Grounding DINO boxes with SAM 3, but it may require Hugging Face access to `facebook/sam3`
- the tuned default prompt set is now intentionally narrow (`product`, `products`) to reduce duplicate whole-object vs label/sticker detections
- containment suppression is applied after NMS so low-confidence inner boxes inside larger product boxes are filtered more aggressively
- `prepare_retail_yolo_dataset.py` converts each split's COCO boxes into sidecar YOLO `.txt` labels and writes a dataset yaml without touching the source images
- `train_retail_yolo.py` is the new baseline path for learning "one physical product = one box" directly from your shelf dataset
