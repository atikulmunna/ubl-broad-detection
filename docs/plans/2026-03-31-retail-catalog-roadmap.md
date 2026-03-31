# Retail Catalog Roadmap

## Goal

Build a new retail detection system on the `labs` branch that reduces or avoids repeated box annotation when new products enter the catalog.

The system should prefer:

1. generic product localization
2. catalog-aware recognition
3. confidence-based fallback to brand-only or unknown
4. reuse of existing UBL/non-UBL aggregation logic

## Why This Direction

The current repository is strong at:

- retail task routing
- UBL vs competitor logic
- share-of-shelf aggregation
- compliance-oriented post-processing

The current repository is weak at:

- handling unseen products without retraining
- onboarding new catalog items without detector annotation
- open-set recognition

The new system should move the main maintenance burden from annotation to catalog curation.

## Target Contract

Each detected instance should resolve to one of:

- `sku_known`
- `brand_known`
- `unknown`

This is safer than forcing every instance into a closed SKU list.

## Proposed Architecture

### Stage 1: Product Proposal

Use a broad instance proposal model to find product-like objects on shelf.

Candidate implementations:

- open-vocabulary detector
- detector + SAM refinement
- SAM prompted from broad proposals

The key requirement is high recall for shelf items.

### Stage 2: Catalog Recognition

For each proposed instance:

- crop the item
- compute visual features
- compare against a catalog index
- return top-k candidates with confidence

Catalog assets may include:

- packshots
- multiple views
- brand metadata
- category metadata
- size / pack-form metadata

### Stage 3: Unknown Handling

If confidence is low:

- keep brand if it is reliable
- otherwise mark unknown
- cluster repeated unknowns for review

### Stage 4: Business Logic

Reuse the current repo for:

- UBL vs competitor classification
- SOS-style aggregation
- shelf-level metrics
- compliance rules where SKU certainty is sufficient

## Delivery Phases

### Phase 0: Baseline

- keep all experimentation on `labs`
- preserve current production analyzers
- create experimental analyzer route

### Phase 1: Catalog Foundation

- add retail catalog schema
- load catalog from config
- support brand metadata and SKU metadata

### Phase 2: Baseline Experiment

- reuse existing SOS detector/classifier as a temporary proposal engine
- enrich detections with catalog metadata
- emit `sku_known` / `brand_known` / `unknown`

This phase is intentionally imperfect, but it gives us a measurable starting point.

### Phase 3: Embedding Index

- add feature extraction for crops
- add nearest-neighbor search over catalog references
- use confidence thresholds for recognition level

### Phase 4: Generic Proposal Engine

- replace or augment the temporary proposal stage with broad retail localization
- evaluate SAM-assisted proposal quality

### Phase 5: Review Loop

- surface persistent unknown clusters
- review only uncertain or novel items
- update catalog without retraining when possible

## Success Criteria

- adding a new product usually requires catalog updates only
- new product launches do not require detector annotation in the common case
- unknowns are surfaced cleanly instead of being misclassified
- existing UBL/non-UBL metrics remain usable during transition

## Near-Term Repo Changes

The first implementation on `labs` should add:

- `config/standards/retail_catalog.yaml`
- a `retail_experiment` config section
- `core/retail_experiment.py`
- router support for a new `retail_experiment` image type
- tests for catalog enrichment and confidence fallback behavior
