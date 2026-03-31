# Knowlege Base

This file is the living project record for `ubl-broad-detection`.

It answers three questions continuously:

1. What are we doing?
2. Why are we doing it?
3. How are we doing it?

From this point onward, this file should be updated at the end of every completed module.

## Project Intent

### What

We are building a broad retail detection system that can work across UBL and non-UBL products.

### Why

The main business goal is to avoid repeated annotation work every time new products are introduced into the catalog.

Instead of training a closed detector for every SKU and re-annotating constantly, we want a system that can:

- localize products broadly
- match them against a catalog
- classify them at SKU level when confident
- fall back safely to brand-level or unknown when not confident

### How

We are building the system in layers:

1. catalog foundation
2. index and matching foundation
3. runtime integration
4. query and crop generation
5. later: stronger image feature extraction and broader proposal engines

## Guiding Principles

- Keep experimentation isolated in this repo, away from the production repo.
- Build module by module.
- After each module:
  - verify with focused tests
  - commit
  - push
- Prefer safe fallback behavior over forced wrong predictions.
- Treat unknown products as a first-class outcome.

## Current Architecture Direction

### Detection side

Right now, the experimental analyzer reuses the existing SOS two-stage detection path as a temporary proposal engine.

Later, this can be replaced or augmented with stronger broad-product proposal methods such as:

- open-vocabulary detection
- SAM-assisted proposals
- other generic retail localization methods

### Recognition side

Recognition is moving toward a catalog-first system:

- reference images live under `catalog/references/<product_id>/`
- a local index is built from catalog references
- detections are converted into structured query assets
- crop-based query images are generated for matching
- results are resolved into:
  - `sku_known`
  - `brand_known`
  - `unknown`

## Module History

### Initial import

Commit: `376b64a`

What:
- Created this standalone repo from the `labs` branch snapshot of the original project.

Why:
- We wanted to experiment in a separate repo without risking the production codebase.

How:
- Fresh repo initialization
- new README
- pushed to GitHub as `ubl-broad-detection`

### Module 1: Retail catalog validation layer

Commit: `87fcb56`

What:
- Added normalized retail catalog handling and validation.

Why:
- The catalog is the foundation of the new architecture.
- If the catalog is inconsistent, everything above it becomes unreliable.

How:
- Added validation for:
  - brand structure
  - SKU structure
  - duplicate `product_id`
  - required `unknown` brand
- Added unit tests for normalization and validation behavior.

### Module 2: Retail catalog index primitives

Commit: `2f385ae`

What:
- Added the first in-memory catalog index and nearest-neighbor search primitives.

Why:
- We needed a searchable catalog layer before introducing more advanced recognition.

How:
- Added:
  - reference discovery
  - deterministic embeddings
  - in-memory cosine search
  - save/load-ready structure
- Added unit tests for discovery, search, and summary behavior.

### Module 3: Matching and index builder integration

Commit: `4cef88c`

What:
- Connected catalog matching decisions to the experimental analyzer path.

Why:
- The analyzer needed a real decision layer instead of only simple brand enrichment.

How:
- Added matching orchestration between:
  - detector outputs
  - catalog enrichment
  - optional index search
- Added a builder CLI for the retail index.

### Module 4: Catalog reference audit workflow

Commit: `7c9cb6c`

What:
- Added catalog reference readiness auditing.

Why:
- We needed visibility into which SKUs were index-ready and which still had no references.

How:
- Added:
  - reference audit reporting
  - `--audit-only` CLI mode
  - tests for ready/missing SKU reporting

### Module 5: Catalog onboarding report tooling

Commit: `0af661e`

What:
- Added machine-readable onboarding reports and documentation for catalog asset layout.

Why:
- The project needed a practical workflow for adding new reference assets.

How:
- Added:
  - `catalog/README.md`
  - onboarding JSON report generation
  - README usage updates
  - tests for missing-by-brand reporting

### Module 6: Runtime saved-index loading

Commit: `ef3a43d`

What:
- Added runtime loading of a saved catalog index.

Why:
- The analyzer needed to use a prepared index when available, while still falling back safely when unavailable.

How:
- Added runtime helper logic for:
  - loading saved index files
  - caching runtime index state
  - reporting `loaded`, `empty`, `unavailable`, or `disabled`
- Added tests for runtime behavior.

### Module 7: Seed initial retail reference assets

Commit: `7696fe1`

What:
- Seeded the first small set of reference assets.

Why:
- Up to this point the index path existed structurally, but the repo had no real references.
- We needed a non-empty audit and non-empty index path.

How:
- Added seed reference images for a few SKUs.
- Tightened discovery so only image files count as references.
- Rebuilt the local index successfully.

### Module 8: Match source telemetry

Commit: `b45324f`

What:
- Added observability for how each match decision was made.

Why:
- We need to know whether results come from index matching or detector fallback to debug quality and trust outputs.

How:
- Added per-instance `match_source`:
  - `index_sku`
  - `index_brand`
  - `detector_brand_fallback`
- Added analyzer-level match-source breakdowns.
- Added tests for the new telemetry behavior.

### Module 9: Pluggable retail embedder layer

Commit: `1236627`

What:
- Extracted embedding logic into a dedicated module and made it pluggable.

Why:
- We want to replace the placeholder embedding logic later without rewriting the rest of the system.

How:
- Added:
  - `DeterministicPathEmbedder`
  - `FileContentHashEmbedder`
  - `create_embedder(...)`
- Updated runtime and index code to use the abstraction.
- Added tests for both embedder paths.

### Module 10: Structured retail query assets

Commit: `3017766`

What:
- Replaced raw query strings with a structured query-asset contract.

Why:
- Matching inputs needed to support real image-path queries and token fallbacks cleanly.

How:
- Added structured query assets with:
  - `image_path`
  - `fallback_token`
  - `source`
- Updated matcher and embedder logic to use them.
- Added dedicated query-asset tests.

### Module 11: Crop-based retail query inputs

Commit: `2683c05`

What:
- Added temporary crop generation from detections and fed those crops into the query pipeline.

Why:
- This is the first step toward real crop-based matching instead of token-only matching.

How:
- Added crop extraction utilities.
- Analyzer now writes temporary detection crops and passes `query_image_path` into matching.
- Added tests for valid and invalid crop extraction behavior.

## Current Status

As of now, the repo has:

- a validated retail catalog
- catalog reference auditing
- onboarding reporting
- saved index build/load support
- runtime index integration
- pluggable embedders
- structured query assets
- crop-based query generation
- match-source telemetry

## What Is Still Placeholder

- The proposal engine still reuses the current SOS detection path.
- The current embedders are lightweight stand-ins, not final ML feature extractors.
- Crop matching is structurally in place, but not yet powered by a strong learned image embedder.

## Most Likely Next Steps

1. Switch the experiment to prefer content-based matching more aggressively where safe.
2. Add stronger image-feature extraction behind the embedder abstraction.
3. Improve crop quality and query generation.
4. Eventually replace the temporary proposal stage with a broader retail proposal engine.
