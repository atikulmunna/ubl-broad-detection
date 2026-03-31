# Vertical Adjacency Detection — Design

## Problem

Adjacency rules currently only handle horizontal layout (categories side by side).
A new rule applies when categories are stacked vertically (one above the other):
- HAIRCARE above/below SKINCARE → HAIRCARE gets 4 legs, SKINCARE gets 3
- Horizontal layout unchanged: PONDS > GAL > HAIRCARE priority

## Approach: Orientation-aware detection + config-driven rules

### 1. Orientation detection (`core/adjacency_detector.py`)

For each adjacent pair, compare x-overlap vs y-overlap of their bounding box bounds:
- y-overlap larger → categories are side by side → `horizontal`
- x-overlap larger → one is above/below the other → `vertical`

`detect_category_adjacency` returns `orientation` per pair:
```python
'HAIRCARE': {adjacent_to: ['PONDS'], orientation: {'PONDS': 'vertical'}}
```

### 2. New config (`config/standards/qpds_standards.yaml`)

Add `vertical_adjacency_adjustments` block alongside existing `adjacency_adjustments`:
```yaml
vertical_adjacency_adjustments:
  HAIRCARE_vertical_to_PONDS:
    HAIRCARE: 4
    PONDS: 3
  HAIRCARE_vertical_to_GAL:
    HAIRCARE: 4
    GAL: 3
  HAIRCARE_vertical_to_PONDS_and_GAL:
    HAIRCARE: 4
    PONDS: 3
    GAL: 3
```

### 3. Rule lookup (`get_required_legs`, `should_waive_shelftalker`)

Both functions receive orientation context and select the correct adjustment table:
- `horizontal` adjacency → existing `adjacency_adjustments`
- `vertical` adjacency → `vertical_adjacency_adjustments`

Shelftalker waiver mirrors the leg rule: in vertical case, skincare gets waived (not haircare).

## What doesn't change
- Existing horizontal rules and YAML structure
- Leg counting (`count_category_facings`)
- Compliance evaluation flow in `analyzers.py`
