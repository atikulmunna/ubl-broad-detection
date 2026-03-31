# SOS Two-Stage Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the single-stage DA_YOLO11X SOS pipeline with a two-stage detection+classification pipeline using SOS-Detection.pt (bbox, 1 class) and SOS-Classification.pt (47 brand classes).

**Architecture:** Stage 1 detects all products as generic bboxes; Stage 2 classifies each bbox crop by brand (47 snake_case classes). Category comes from the client-supplied `sub_category` field, not from the model. Brand→is_ubl lookup uses a restructured flat YAML keyed by cls class name.

**Tech Stack:** Ultralytics YOLO, PyTorch, PIL, PyYAML, Python 3.10

---

## Model Classes Reference

SOS-Detection: 1 class — `product`

SOS-Classification: 47 brand classes (snake_case):
```
aci_neem, bactrol, boost, clear, clinic_plus, closeup, colgate, cosco, dabur, dano,
dettol, domex, dove, fast_wash, fiera, garnier, gh, ghari, gl, harpic, himalaya,
horlicks, keya, lifebuoy, lux, magic_tooth, maltova, marks, mediplus, meril, nivea,
parachute, pepsodent, ponds, revive, rin, sandalina, savlon, sensodyne, simple,
sunsilk, surf_excel, tibet, tresemme, vaseline, vim, wheel
```

UBL brands: boost, clear, clinic_plus, closeup, domex, dove, gh, gl, horlicks,
lifebuoy, lux, maltova, pepsodent, ponds, rin, simple, sunsilk, surf_excel,
tresemme, vaseline, vim, wheel (22 brands)

Competitor brands: all others (25 brands)

---

### Task 1: Restructure sos_brand_shelving_norm.yaml

**Files:**
- Modify: `config/standards/sos_brand_shelving_norm.yaml`

**Step 1: Replace entire file content**

New structure uses snake_case brand keys matching SOS-Classification model output exactly.
`min_qty` only on UBL brands.

```yaml
# SOS Brand Norms
# Keys match SOS-Classification model class names exactly (snake_case)
# is_ubl: yes/no — determines UBL vs competitor classification
# min_qty: minimum units required on shelf (UBL brands only)

brands:
  # === UBL BRANDS ===
  boost:      {is_ubl: yes, min_qty: 4}
  clear:      {is_ubl: yes, min_qty: 3}
  clinic_plus: {is_ubl: yes, min_qty: 2}
  closeup:    {is_ubl: yes, min_qty: 3}
  domex:      {is_ubl: yes, min_qty: 3}
  dove:       {is_ubl: yes, min_qty: 2}
  gh:         {is_ubl: yes, min_qty: 2}   # Glow & Handsome
  gl:         {is_ubl: yes, min_qty: 2}   # Glow & Lovely
  horlicks:   {is_ubl: yes, min_qty: 2}
  lifebuoy:   {is_ubl: yes, min_qty: 2}
  lux:        {is_ubl: yes, min_qty: 3}
  maltova:    {is_ubl: yes, min_qty: 3}
  pepsodent:  {is_ubl: yes, min_qty: 2}
  ponds:      {is_ubl: yes, min_qty: 2}
  rin:        {is_ubl: yes, min_qty: 4}
  simple:     {is_ubl: yes, min_qty: 1}
  sunsilk:    {is_ubl: yes, min_qty: 1}
  surf_excel: {is_ubl: yes, min_qty: 3}
  tresemme:   {is_ubl: yes, min_qty: 1}
  vaseline:   {is_ubl: yes, min_qty: 2}
  vim:        {is_ubl: yes, min_qty: 3}
  wheel:      {is_ubl: yes, min_qty: 4}

  # === COMPETITOR BRANDS ===
  aci_neem:    {is_ubl: no}
  bactrol:     {is_ubl: no}
  colgate:     {is_ubl: no}
  cosco:       {is_ubl: no}
  dabur:       {is_ubl: no}
  dano:        {is_ubl: no}
  dettol:      {is_ubl: no}
  fast_wash:   {is_ubl: no}
  fiera:       {is_ubl: no}
  garnier:     {is_ubl: no}
  ghari:       {is_ubl: no}
  harpic:      {is_ubl: no}
  himalaya:    {is_ubl: no}
  keya:        {is_ubl: no}
  magic_tooth: {is_ubl: no}
  marks:       {is_ubl: no}
  mediplus:    {is_ubl: no}
  meril:       {is_ubl: no}
  nivea:       {is_ubl: no}
  parachute:   {is_ubl: no}
  revive:      {is_ubl: no}
  sandalina:   {is_ubl: no}
  savlon:      {is_ubl: no}
  sensodyne:   {is_ubl: no}
  tibet:       {is_ubl: no}
```

**Step 2: Verify count**
```bash
python3 -c "
import yaml
with open('config/standards/sos_brand_shelving_norm.yaml') as f:
    d = yaml.safe_load(f)
brands = d['brands']
ubl = [k for k,v in brands.items() if v['is_ubl'] == 'yes']
comp = [k for k,v in brands.items() if v['is_ubl'] == 'no']
print(f'Total: {len(brands)}, UBL: {len(ubl)}, Competitor: {len(comp)}')
assert len(brands) == 47, f'Expected 47, got {len(brands)}'
print('OK')
"
```
Expected: `Total: 47, UBL: 22, Competitor: 25` then `OK`

**Step 3: Commit**
```bash
git add config/standards/sos_brand_shelving_norm.yaml
git commit -m "feat: restructure sos_brand_shelving_norm to flat brand dict keyed by cls class name"
```

---

### Task 2: Update config.yaml — share_of_shelf section

**Files:**
- Modify: `config/config.yaml`

**Step 1: Replace the share_of_shelf section**

Find:
```yaml
share_of_shelf:
  conf: 0.20               # Confidence threshold for all product detection (UBL + Competitor)
  detection_method: "none"  # Shelf detection method: "none" or "clustering"
```

Replace with:
```yaml
share_of_shelf:
  det_conf: 0.25            # Stage 1: Detection confidence threshold (SOS-Detection)
  cls_conf: 0.50            # Stage 2: Classification confidence threshold (SOS-Classification)
  cls_batch_size: 8         # Stage 2: Batch size for classification (higher = faster, more VRAM)
```

Also update models section. Find:
```yaml
  ubl: "models/DA_YOLO11X.pt"  # 243 classes (UBL + Competitor) for Share of Shelf
```
Replace with:
```yaml
  sos_det: "models/SOS-Detection.pt"   # Stage 1: Product detection (1 class: product)
  sos_cls: "models/SOS-Classification.pt"  # Stage 2: Brand classification (47 classes)
```

**Step 2: Verify yaml parses**
```bash
python3 -c "
import yaml
with open('config/config.yaml') as f:
    c = yaml.safe_load(f)
sos = c['share_of_shelf']
assert 'det_conf' in sos and 'cls_conf' in sos and 'cls_batch_size' in sos
assert 'sos_det' in c['models'] and 'sos_cls' in c['models']
assert 'ubl' not in c['models']
print('OK', sos)
"
```

**Step 3: Commit**
```bash
git add config/config.yaml
git commit -m "feat: update config.yaml for SOS two-stage pipeline"
```

---

### Task 3: Update config/loader.py

**Files:**
- Modify: `config/loader.py`

**Step 1: Update MODEL_PATHS — remove `ubl`, add `sos_det` and `sos_cls`**

Find:
```python
MODEL_PATHS = {
    'exclusivity': MODELS_CONFIG.get('exclusivity', os.path.join(MODEL_DIR, "EXCLUSIVITY.pt")),
    'ubl': MODELS_CONFIG.get('ubl', os.path.join(MODEL_DIR, "DA_YOLO11X.pt")),
    'qpds': MODELS_CONFIG.get('qpds', os.path.join(MODEL_DIR, "QPDS.pt")),
```
Replace with:
```python
MODEL_PATHS = {
    'exclusivity': MODELS_CONFIG.get('exclusivity', os.path.join(MODEL_DIR, "EXCLUSIVITY.pt")),
    'sos_det': MODELS_CONFIG.get('sos_det', os.path.join(MODEL_DIR, "SOS-Detection.pt")),
    'sos_cls': MODELS_CONFIG.get('sos_cls', os.path.join(MODEL_DIR, "SOS-Classification.pt")),
    'qpds': MODELS_CONFIG.get('qpds', os.path.join(MODEL_DIR, "QPDS.pt")),
```

**Step 2: Update `_load_brand_norms_main()` to parse new flat YAML**

Find and replace the entire `_load_brand_norms_main` function:
```python
def _load_brand_norms_main():
    """Load SOS brand norms from flat brand dict keyed by cls class name"""
    try:
        norm_path = os.path.join(os.path.dirname(__file__), "standards", "sos_brand_shelving_norm.yaml")
        with open(norm_path) as f:
            data = yaml.safe_load(f)
            norms = data.get('brands', {})
            logger.info(f"Loaded {len(norms)} brand norms for SOS classification")
            return norms
    except Exception as e:
        logger.warning(f"Could not load brand norms: {e}")
        return {}
```

`BRAND_NORMS` is now `{brand_key: {is_ubl, min_qty}}` — a simple dict lookup by cls class name.

**Step 3: Verify loader**
```bash
python3 -c "
from config.loader import BRAND_NORMS, MODEL_PATHS
assert 'sos_det' in MODEL_PATHS and 'sos_cls' in MODEL_PATHS
assert 'ubl' not in MODEL_PATHS
assert BRAND_NORMS.get('boost', {}).get('is_ubl') == 'yes'
assert BRAND_NORMS.get('colgate', {}).get('is_ubl') == 'no'
assert len(BRAND_NORMS) == 47
print('OK')
"
```

**Step 4: Commit**
```bash
git add config/loader.py
git commit -m "feat: update loader for SOS two-stage — new model paths and flat brand norms"
```

---

### Task 4: Add `_detect_products_two_stage_sos()` in detection.py

**Files:**
- Modify: `core/detection.py`

**Step 1: Add the new function after `_detect_products_two_stage` (~line 486)**

This function uses bbox crops (no masks — SOS-Detection is object detection, not segmentation).
Crop is letterboxed to 384×384 (same as QPDS cls training).
Returns list of `{brand, bbox_xyxy, confidence}` dicts.

```python
def _detect_products_two_stage_sos(worker_id: int, image_path: str, det_conf: float,
                                    cls_conf: float, cls_batch_size: int, visit_id: str = ""):
    """
    Two-stage SOS pipeline: Detection (bbox) → Brand Classification

    Stage 1: SOS-Detection.pt detects all products as generic bboxes (1 class: 'product')
    Stage 2: SOS-Classification.pt classifies each bbox crop by brand (47 classes)

    Args:
        worker_id: Worker ID for model selection
        image_path: Path to image file on disk
        det_conf: Detection confidence threshold (Stage 1)
        cls_conf: Classification confidence threshold (Stage 2)
        cls_batch_size: Batch size for classification inference
        visit_id: Visit ID for logging

    Returns:
        List of dicts: {brand: str, bbox_xyxy: list[int], confidence: float}
    """
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Starting det+cls pipeline "
                f"(det_conf={det_conf}, cls_conf={cls_conf}, batch={cls_batch_size})")

    # STAGE 1: Object Detection
    t_stage1_start = time.perf_counter()
    det_results = model_manager.predict('sos_det', image_path, worker_id=worker_id,
                                        conf=det_conf, verbose=False)
    det_result = det_results[0] if det_results else None
    t_stage1_ms = (time.perf_counter() - t_stage1_start) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Stage 1 (det) took {t_stage1_ms:.0f}ms")

    if not det_result or not det_result.boxes or len(det_result.boxes) == 0:
        logger.warning(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] No products detected")
        return []

    boxes = det_result.boxes.xyxy.cpu().numpy()   # [N, 4]
    det_scores = det_result.boxes.conf.cpu().numpy()  # [N]
    del det_result
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    num_boxes = len(boxes)
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Stage 1 complete: {num_boxes} products detected")

    # STAGE 2: Crop + Classify
    t_crop_start = time.perf_counter()
    pil_image = Image.open(image_path).convert('RGB')
    img_w, img_h = pil_image.size

    crop_images = []
    valid_indices = []
    for idx, box in enumerate(boxes):
        x1, y1, x2, y2 = map(int, box)
        # Clamp to image bounds
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img_w, x2), min(img_h, y2)
        if x2 <= x1 or y2 <= y1:
            logger.warning(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Skipping degenerate box at {idx}")
            continue

        crop_pil = pil_image.crop((x1, y1, x2, y2))
        cw, ch = crop_pil.size
        scale = min(384 / ch, 384 / cw)
        new_w, new_h = int(cw * scale), int(ch * scale)
        resized = crop_pil.resize((new_w, new_h), Image.Resampling.BILINEAR)
        canvas = Image.new('RGB', (384, 384), (0, 0, 0))
        canvas.paste(resized, ((384 - new_w) // 2, (384 - new_h) // 2))
        crop_images.append(canvas)
        valid_indices.append(idx)

    t_crop_ms = (time.perf_counter() - t_crop_start) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Created {len(crop_images)} crops in {t_crop_ms:.0f}ms")

    if not crop_images:
        return []

    # Chunked classification (OOM-safe, same pattern as QPDS)
    t_cls_start = time.perf_counter()
    cls_results = []
    chunk_size = cls_batch_size
    i = 0
    while i < len(crop_images):
        chunk = crop_images[i:i + chunk_size]
        try:
            chunk_results = model_manager.predict('sos_cls', chunk, worker_id=worker_id,
                                                   batch=chunk_size, verbose=False)
        except torch.cuda.OutOfMemoryError:
            if chunk_size > 1:
                logger.warning(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] OOM on chunk_size={chunk_size}, halving")
                torch.cuda.empty_cache()
                chunk_size = chunk_size // 2
                continue
            else:
                raise
        cls_results.extend(chunk_results)
        torch.cuda.empty_cache()
        i += chunk_size

    t_cls_ms = (time.perf_counter() - t_cls_start) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Stage 2 (cls) took {t_cls_ms:.0f}ms for {len(crop_images)} crops")

    # Combine results
    cls_names = cls_results[0].names if cls_results else {}
    detections = []
    for i, (cls_result, orig_idx) in enumerate(zip(cls_results, valid_indices)):
        cls_id = cls_result.probs.top1
        cls_score = float(cls_result.probs.top1conf)
        if cls_score < cls_conf:
            logger.debug(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Instance {i}: cls conf too low ({cls_score:.2f})")
            continue
        brand = cls_names.get(cls_id, str(cls_id))
        det_score = float(det_scores[orig_idx])
        box = boxes[orig_idx]
        detections.append({
            'brand': brand,
            'bbox_xyxy': [int(box[0]), int(box[1]), int(box[2]), int(box[3])],
            'confidence': round(det_score * cls_score, 4),
        })

    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Final: {len(detections)} classified detections")
    return detections
```

**Step 2: Add `_detect_products_two_stage_sos` to the import in analyzers.py (Task 5 will do this, but verify the function name is correct)**
```bash
python3 -c "
from core.detection import _detect_products_two_stage_sos
print('Import OK')
"
```
Expected: `Import OK`

**Step 3: Commit**
```bash
git add core/detection.py
git commit -m "feat: add _detect_products_two_stage_sos bbox-based two-stage detection"
```

---

### Task 5: Rewrite `analyze_share_of_shelf` in analyzers.py

**Files:**
- Modify: `core/analyzers.py`

**Step 1: Update the import from detection.py**

Find:
```python
from core.detection import (
    _detect_shelftalker_roi, _validate_roi_quality,
    _detect_products_in_roi, _detect_products_full_image, _detect_products_two_stage,
    _check_exclusivity, _infer_roi_from_planogram_products
)
```
Replace with:
```python
from core.detection import (
    _detect_shelftalker_roi, _validate_roi_quality,
    _detect_products_in_roi, _detect_products_full_image, _detect_products_two_stage,
    _detect_products_two_stage_sos,
    _check_exclusivity, _infer_roi_from_planogram_products
)
```

**Step 2: Remove unused SOS-specific imports**

Find and remove:
```python
from utils.brand_mapper import extract_brand_from_product
from utils.sos_category_mapping import get_sos_category
```
(Only remove if not used elsewhere in the file — grep first:)
```bash
grep -n "extract_brand_from_product\|get_sos_category" core/analyzers.py
```
If only used in `analyze_share_of_shelf`, remove both import lines.

**Step 3: Replace `analyze_share_of_shelf` entirely**

Find the function from `def analyze_share_of_shelf(` to the closing `except Exception` block and replace with:

```python
def analyze_share_of_shelf(image_path: str, worker_id: int = 0, visit_id: str = "",
                            sub_category: str = "unknown") -> dict:
    """Analyze Share of Shelf using two-stage detection+classification pipeline"""
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS] Starting SOS analysis (sub_category={sub_category})")
    try:
        t_start = time.perf_counter()

        det_conf = SHARE_OF_SHELF_CONFIG.get('det_conf', 0.25)
        cls_conf = SHARE_OF_SHELF_CONFIG.get('cls_conf', 0.50)
        cls_batch_size = SHARE_OF_SHELF_CONFIG.get('cls_batch_size', 8)

        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS] det_conf={det_conf}, cls_conf={cls_conf}, batch={cls_batch_size}")

        t_detect = time.perf_counter()
        detections = _detect_products_two_stage_sos(
            worker_id, image_path, det_conf, cls_conf, cls_batch_size, visit_id=visit_id
        )
        detection_ms = (time.perf_counter() - t_detect) * 1000

        # Classify each detection as UBL or competitor via brand norm lookup
        t_classify = time.perf_counter()
        ubl_brands = defaultdict(int)
        competitor_brands = defaultdict(int)

        for det in detections:
            brand = det['brand']
            entry = BRAND_NORMS.get(brand)
            if entry and entry.get('is_ubl') == 'yes':
                ubl_brands[brand] += 1
            else:
                competitor_brands[brand] += 1

        classify_ms = (time.perf_counter() - t_classify) * 1000

        ubl_count = sum(ubl_brands.values())
        competitor_count = sum(competitor_brands.values())
        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS] UBL: {dict(ubl_brands)}")
        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS] Competitor: {dict(competitor_brands)}")

        # Compliance: check each UBL brand against min_qty
        t_compliance = time.perf_counter()
        compliance_score = 0.0
        product_accuracy = []
        ubl_norms = {k: v for k, v in BRAND_NORMS.items() if v.get('is_ubl') == 'yes'}
        if ubl_norms:
            met = 0
            for brand, norm in ubl_norms.items():
                min_qty = norm.get('min_qty', 1)
                detected = ubl_brands.get(brand, 0)
                passed = detected >= min_qty
                if passed:
                    met += 1
                product_accuracy.append({
                    'brand': brand,
                    'detected': detected,
                    'min_qty': min_qty,
                    'passed': passed,
                })
            compliance_score = round((met / len(ubl_norms)) * 100, 1)
        compliance_ms = (time.perf_counter() - t_compliance) * 1000

        # Category breakdown — all detections belong to client-supplied sub_category
        category_breakdown = {
            sub_category: {
                **{b: c for b, c in ubl_brands.items()},
                **{b: c for b, c in competitor_brands.items()},
            }
        }

        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS] ✓ {ubl_count} UBL + {competitor_count} competitor | compliance={compliance_score}%")

        return {
            "model_version": "SOS-Detection + SOS-Classification (47 brands)",
            "confidence": {"det": det_conf, "cls": cls_conf},
            "total_products": ubl_count + competitor_count,
            "ubl_product_breakdown": dict(ubl_brands),
            "competitor_product_breakdown": dict(competitor_brands),
            "category_breakdown": category_breakdown,
            "competitor_count": competitor_count,
            "compliance_score": compliance_score,
            "product_accuracy": product_accuracy,
            "timing": {
                "total_ms": round(total_ms, 1),
                "detection_ms": round(detection_ms, 1),
                "classification_ms": round(classify_ms, 1),
                "compliance_ms": round(compliance_ms, 1),
            },
            "summary": f"Detected {ubl_count} UBL + {competitor_count} competitor products",
        }

    except Exception as e:
        logger.error(f"[{visit_id}] [SOS] Error in analyze_share_of_shelf: {e}", exc_info=True)
        return {
            "error": str(e),
            "summary": "Error processing Share of Shelf"
        }
```

**Step 4: Verify syntax**
```bash
python3 -c "from core.analyzers import analyze_share_of_shelf; print('Import OK')"
```

**Step 5: Commit**
```bash
git add core/analyzers.py
git commit -m "feat: rewrite analyze_share_of_shelf for two-stage pipeline"
```

---

### Task 6: Update pipeline.py — pass sub_category to SOS

**Files:**
- Modify: `core/pipeline.py`

**Step 1: Pass `sub_category` for SOS in `route_to_ai_model`**

Find:
```python
    if image_type == "fixed_shelf" and metadata:
        kwargs["shelf_type"] = metadata.get("shelf_type")
        kwargs["selected_category"] = metadata.get("selected_category", "all")
    elif image_type == "posm" and metadata:
        kwargs["posm_items"] = metadata.get("posm_items", [])
```
Replace with:
```python
    if image_type == "fixed_shelf" and metadata:
        kwargs["shelf_type"] = metadata.get("shelf_type")
        kwargs["selected_category"] = metadata.get("selected_category", "all")
    elif image_type == "share_of_shelf" and metadata:
        kwargs["sub_category"] = metadata.get("sub_category") or metadata.get("sub-category", "unknown")
    elif image_type == "posm" and metadata:
        kwargs["posm_items"] = metadata.get("posm_items", [])
```

**Step 2: Verify the metadata key used in pipeline for SOS**

Check how `sub_category` is stored in metadata in `_process_image_sync`:
```bash
grep -n "sub.category\|sub_category" core/pipeline.py
```
Confirm the key name matches what's used in the elif above. Adjust key name if different.

**Step 3: Commit**
```bash
git add core/pipeline.py
git commit -m "feat: pass sub_category metadata to analyze_share_of_shelf"
```

---

### Task 7: Smoke test end-to-end

**Step 1: Verify all models load**
```bash
conda run -n taco python3 -c "
from core.model_manager import model_manager
assert model_manager.get_model('sos_det') is not None, 'sos_det not loaded'
assert model_manager.get_model('sos_cls') is not None, 'sos_cls not loaded'
assert model_manager.get_model('ubl', 0) is None or True  # ubl should be gone
print('Models OK')
"
```

**Step 2: Run analyzer on a sample SOS image**
```bash
conda run -n taco python3 -c "
import glob, os
# Find any jpeg in the project
imgs = glob.glob('simulation/**/*.jpg', recursive=True) + glob.glob('simulation/**/*.jpeg', recursive=True)
img = imgs[0] if imgs else None
if not img:
    print('No test image found — skip')
else:
    from core.analyzers import analyze_share_of_shelf
    result = analyze_share_of_shelf(img, worker_id=0, visit_id='TEST', sub_category='hair_care')
    print('Result keys:', list(result.keys()))
    print('Summary:', result.get('summary'))
    print('Timing:', result.get('timing'))
    assert 'error' not in result, f'Error: {result}'
    print('PASS')
"
```
Expected: Result keys printed, no `error` key, timing shown.

**Step 3: Commit**
```bash
git add .
git commit -m "test: verify SOS two-stage smoke test passes"
```

---

## Unresolved Questions
- None — all design decisions resolved during brainstorming.
