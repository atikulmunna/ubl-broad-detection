# Vertical Adjacency Detection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect whether adjacent shelf categories are horizontally or vertically arranged and apply different leg requirements accordingly (vertical: HAIRCARE=4/SKINCARE=3; horizontal: existing PONDS>GAL>HAIRCARE priority).

**Architecture:** Extend `detect_category_adjacency` to classify each adjacency pair as `horizontal` or `vertical` using bounding box overlap analysis. Add `vertical_adjacency_adjustments` to YAML config. Update `get_required_legs` and `should_waive_shelftalker` to select the correct rule table based on orientation.

**Tech Stack:** Python, PyYAML, existing QPDS standards config pipeline.

---

### Task 1: Add vertical_adjacency_adjustments to qpds_standards.yaml

**Files:**
- Modify: `config/standards/qpds_standards.yaml:550-580`

**Step 1: Add the new config block**

In `config/standards/qpds_standards.yaml`, append inside `adjacency_rules:` after line 577 (`HAIRCARE: 3`):

```yaml
  # Vertical adjacency: HAIRCARE stacked above/below SKINCARE
  # In this layout HAIRCARE takes priority (4 legs), SKINCARE gets 3
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

**Step 2: Verify YAML parses cleanly**

```bash
python3 -c "import yaml; d=yaml.safe_load(open('config/standards/qpds_standards.yaml')); print(list(d['adjacency_rules']['vertical_adjacency_adjustments'].keys()))"
```
Expected: `['HAIRCARE_vertical_to_PONDS', 'HAIRCARE_vertical_to_GAL', 'HAIRCARE_vertical_to_PONDS_and_GAL']`

**Step 3: Commit**

```bash
git add config/standards/qpds_standards.yaml
git commit -m "config: add vertical_adjacency_adjustments to adjacency_rules"
```

---

### Task 2: Extend detect_category_adjacency to return orientation

**Files:**
- Modify: `core/adjacency_detector.py:140-237`
- Test: `tests/test_adjacency_detector.py` (create)

**Background:**
`detect_category_adjacency` currently sorts categories by x-center and checks horizontal gaps. We add orientation detection per adjacent pair. Two categories are:
- **horizontal** (side by side): their y-ranges significantly overlap
- **vertical** (stacked): their x-ranges significantly overlap but y-ranges don't

Overlap for a dimension = `max(0, min(a_max, b_max) - max(a_min, b_min))`.
Compare x-overlap vs y-overlap — whichever is larger determines the axis of overlap, which indicates the OTHER axis is the separation axis.
- x-overlap > y-overlap → separated along y-axis → **vertical** layout
- y-overlap > x-overlap → separated along x-axis → **horizontal** layout

The result structure gains an `orientation` dict per category:
```python
'HAIRCARE': {
    'adjacent_to': ['PONDS'],
    'orientation': {'PONDS': 'vertical'}  # NEW
}
```

**Step 1: Write failing tests**

Create `tests/test_adjacency_detector.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.adjacency_detector import detect_category_adjacency


def _make_det(product_name, x1, y1, x2, y2):
    return {'product_name': product_name, 'bbox_xyxy': [x1, y1, x2, y2]}


# --- Horizontal layout (side by side) ---
# PONDS left [0,0,100,200], HAIRCARE right [110,0,210,200]
# y-overlap=200, x-overlap=0 → horizontal
HORIZONTAL_DETS = [
    _make_det("Pond's Face Wash", 0, 0, 100, 200),
    _make_det("Pond's Face Wash", 10, 20, 90, 180),
    _make_det("Dove Shampoo", 110, 0, 210, 200),
    _make_det("Dove Shampoo", 120, 20, 200, 180),
]

# --- Vertical layout (stacked) ---
# PONDS top [0,0,200,100], HAIRCARE below [0,110,200,210]
# x-overlap=200, y-overlap=0 → vertical
VERTICAL_DETS = [
    _make_det("Pond's Face Wash", 0, 0, 200, 100),
    _make_det("Pond's Face Wash", 10, 10, 190, 90),
    _make_det("Dove Shampoo", 0, 110, 200, 210),
    _make_det("Dove Shampoo", 10, 120, 190, 200),
]


def test_horizontal_adjacency_orientation():
    result = detect_category_adjacency(HORIZONTAL_DETS)
    assert result['adjacency_detected'] is True
    ponds_info = result['categories']['PONDS']
    assert 'HAIRCARE' in ponds_info['adjacent_to']
    assert ponds_info['orientation']['HAIRCARE'] == 'horizontal'
    hair_info = result['categories']['HAIRCARE']
    assert hair_info['orientation']['PONDS'] == 'horizontal'


def test_vertical_adjacency_orientation():
    result = detect_category_adjacency(VERTICAL_DETS)
    assert result['adjacency_detected'] is True
    ponds_info = result['categories']['PONDS']
    assert 'HAIRCARE' in ponds_info['adjacent_to']
    assert ponds_info['orientation']['HAIRCARE'] == 'vertical'
    hair_info = result['categories']['HAIRCARE']
    assert hair_info['orientation']['PONDS'] == 'vertical'


def test_no_adjacency_returns_empty_orientation():
    # Far apart horizontally — beyond threshold
    dets = [
        _make_det("Pond's Face Wash", 0, 0, 100, 200),
        _make_det("Dove Shampoo", 300, 0, 400, 200),
    ]
    result = detect_category_adjacency(dets, horizontal_threshold=50.0)
    assert result['adjacency_detected'] is False
    assert result['categories']['PONDS']['orientation'] == {}
```

**Step 2: Run to verify they fail**

```bash
cd /home/mkultra/Documents/UBL-AIBackend/dev/UBL-standalone
python3 -m pytest tests/test_adjacency_detector.py -v 2>&1 | tail -20
```
Expected: 3 FAILED (KeyError or AttributeError on `orientation`)

**Step 3: Implement orientation detection in detect_category_adjacency**

In `core/adjacency_detector.py`, update the `category_info` initialization (line ~181) to include `orientation`:

```python
category_info[category] = {
    'bounds': bounds,
    'position': None,
    'adjacent_to': [],
    'orientation': {}   # NEW: {other_category: 'horizontal'|'vertical'}
}
```

Replace the adjacency check block (lines ~204-215) with:

```python
        if i < len(sorted_categories) - 1:
            next_category = sorted_categories[i + 1]

            current_bounds = category_info[category]['bounds']
            next_bounds = category_info[next_category]['bounds']

            horizontal_gap = next_bounds['min_x'] - current_bounds['max_x']

            if horizontal_gap <= horizontal_threshold:
                # Determine orientation via overlap analysis
                x_overlap = max(0, min(current_bounds['max_x'], next_bounds['max_x'])
                                   - max(current_bounds['min_x'], next_bounds['min_x']))
                y_overlap = max(0, min(current_bounds['max_y'], next_bounds['max_y'])
                                   - max(current_bounds['min_y'], next_bounds['min_y']))
                orientation = 'vertical' if x_overlap > y_overlap else 'horizontal'

                category_info[category]['adjacent_to'].append(next_category)
                category_info[next_category]['adjacent_to'].append(category)
                category_info[category]['orientation'][next_category] = orientation
                category_info[next_category]['orientation'][category] = orientation

                logger.debug(
                    f"Adjacency detected: {category} <-> {next_category} "
                    f"(gap: {horizontal_gap:.1f}px, orientation: {orientation})"
                )
```

Also update the vertical adjacency check: the current sort is by `center_x`, which won't catch vertical stacking. Add a second pass that sorts by `center_y` to detect vertically adjacent pairs:

After the horizontal pass, add:

```python
    # Second pass: detect vertical adjacency (stacked categories)
    sorted_by_y = sorted(
        category_info.keys(),
        key=lambda cat: category_info[cat]['bounds']['center_y']
    )

    vertical_threshold = horizontal_threshold  # reuse same pixel gap

    for i in range(len(sorted_by_y) - 1):
        category = sorted_by_y[i]
        next_category = sorted_by_y[i + 1]

        # Skip if already found as adjacent in horizontal pass
        if next_category in category_info[category]['adjacent_to']:
            continue

        current_bounds = category_info[category]['bounds']
        next_bounds = category_info[next_category]['bounds']

        vertical_gap = next_bounds['min_y'] - current_bounds['max_y']

        if vertical_gap <= vertical_threshold:
            x_overlap = max(0, min(current_bounds['max_x'], next_bounds['max_x'])
                               - max(current_bounds['min_x'], next_bounds['min_x']))
            y_overlap = max(0, min(current_bounds['max_y'], next_bounds['max_y'])
                               - max(current_bounds['min_y'], next_bounds['min_y']))
            orientation = 'vertical' if x_overlap > y_overlap else 'horizontal'

            category_info[category]['adjacent_to'].append(next_category)
            category_info[next_category]['adjacent_to'].append(category)
            category_info[category]['orientation'][next_category] = orientation
            category_info[next_category]['orientation'][category] = orientation

            logger.debug(
                f"Vertical adjacency detected: {category} <-> {next_category} "
                f"(gap: {vertical_gap:.1f}px, orientation: {orientation})"
            )
```

**Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_adjacency_detector.py -v 2>&1 | tail -20
```
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add core/adjacency_detector.py tests/test_adjacency_detector.py
git commit -m "feat: add orientation detection to detect_category_adjacency"
```

---

### Task 3: Update get_required_legs to use orientation

**Files:**
- Modify: `core/adjacency_detector.py:285-334`
- Test: `tests/test_adjacency_detector.py` (extend)

**Background:**
`get_required_legs` currently only uses horizontal priority rules. It needs to:
1. Check the orientation between the current category and each adjacent category
2. If any adjacency is `vertical` → look up `vertical_adjacency_adjustments`
3. If all adjacencies are `horizontal` → use existing `adjacency_adjustments`

For vertical lookup, build a key like `HAIRCARE_vertical_to_PONDS` and check the adjustment table. The leg value for the current category is read directly from the matched adjustment entry.

**Step 1: Add tests**

Append to `tests/test_adjacency_detector.py`:

```python
from core.adjacency_detector import get_required_legs


def test_horizontal_haircare_gets_3_legs():
    result = detect_category_adjacency(HORIZONTAL_DETS)
    # HAIRCARE adjacent to PONDS horizontally → priority rules → HAIRCARE gets 3
    legs = get_required_legs('HAIRCARE', result)
    assert legs == 3


def test_horizontal_ponds_gets_4_legs():
    result = detect_category_adjacency(HORIZONTAL_DETS)
    legs = get_required_legs('PONDS', result)
    assert legs == 4


def test_vertical_haircare_gets_4_legs():
    result = detect_category_adjacency(VERTICAL_DETS)
    # HAIRCARE stacked above/below PONDS → vertical rules → HAIRCARE gets 4
    legs = get_required_legs('HAIRCARE', result)
    assert legs == 4


def test_vertical_ponds_gets_3_legs():
    result = detect_category_adjacency(VERTICAL_DETS)
    legs = get_required_legs('PONDS', result)
    assert legs == 3
```

**Step 2: Run to verify they fail**

```bash
python3 -m pytest tests/test_adjacency_detector.py::test_vertical_haircare_gets_4_legs tests/test_adjacency_detector.py::test_vertical_ponds_gets_3_legs -v 2>&1 | tail -10
```
Expected: FAILED (returns wrong leg counts)

**Step 3: Implement orientation-aware get_required_legs**

Replace `get_required_legs` in `core/adjacency_detector.py` (lines ~285-334):

```python
def get_required_legs(category: str, adjacency_info: Dict) -> int:
    rules = _load_adjacency_rules()

    if not rules or not adjacency_info.get('adjacency_detected'):
        return rules.get('default_legs', {}).get(category, 4)

    categories = adjacency_info.get('categories', {})
    cat_info = categories.get(category, {})
    adjacent_to = cat_info.get('adjacent_to', [])
    orientation_map = cat_info.get('orientation', {})

    if not adjacent_to:
        return rules.get('default_legs', {}).get(category, 4)

    # Check for any vertical adjacency first
    vertical_neighbors = [c for c in adjacent_to if orientation_map.get(c) == 'vertical']

    if vertical_neighbors:
        vert_adjustments = rules.get('vertical_adjacency_adjustments', {})

        # Build lookup key: sorted neighbor brands joined with _and_
        # e.g. HAIRCARE vertical to PONDS → "HAIRCARE_vertical_to_PONDS"
        # Try multi-neighbor key first, then single
        neighbor_str = '_and_'.join(sorted(vertical_neighbors))
        key = f"{category}_vertical_to_{neighbor_str}"

        if key not in vert_adjustments:
            # Try individual neighbors
            for neighbor in vertical_neighbors:
                key = f"{category}_vertical_to_{neighbor}"
                if key in vert_adjustments:
                    break

        adjustment = vert_adjustments.get(key, {})
        if category in adjustment:
            return adjustment[category]

        # Also check from the other side (e.g. PONDS_vertical_to_HAIRCARE doesn't exist,
        # but HAIRCARE_vertical_to_PONDS does — look up category's value there)
        for adj_key, adj_val in vert_adjustments.items():
            if category in adj_val and all(n in adj_key for n in vertical_neighbors):
                return adj_val[category]

        return rules.get('default_legs', {}).get(category, 4)

    # All adjacencies are horizontal — use existing priority rules
    priority_order = rules.get('priority_order', ['PONDS', 'GAL', 'HAIRCARE'])

    try:
        my_priority = priority_order.index(category)
    except ValueError:
        return 4

    for adj_cat in adjacent_to:
        try:
            adj_priority = priority_order.index(adj_cat)
            if adj_priority < my_priority:
                return 3
        except ValueError:
            continue

    return 4
```

**Step 4: Run all adjacency tests**

```bash
python3 -m pytest tests/test_adjacency_detector.py -v 2>&1 | tail -20
```
Expected: all PASSED

**Step 5: Commit**

```bash
git add core/adjacency_detector.py tests/test_adjacency_detector.py
git commit -m "feat: orientation-aware leg requirements in get_required_legs"
```

---

### Task 4: Update should_waive_shelftalker to use orientation

**Files:**
- Modify: `core/adjacency_detector.py:370-432`
- Test: `tests/test_adjacency_detector.py` (extend)

**Background:**
In horizontal layout: lower-priority category (HAIRCARE) gets the waiver.
In vertical layout: SKINCARE (PONDS/GAL) now has fewer required legs, so SKINCARE gets the waiver.
Rule: waive if the category's required legs < default (i.e. `get_required_legs < 4`).

**Step 1: Add tests**

```python
from core.adjacency_detector import should_waive_shelftalker


def test_horizontal_haircare_gets_waiver():
    result = detect_category_adjacency(HORIZONTAL_DETS)
    assert should_waive_shelftalker('HAIRCARE', result) is True


def test_horizontal_ponds_no_waiver():
    result = detect_category_adjacency(HORIZONTAL_DETS)
    assert should_waive_shelftalker('PONDS', result) is False


def test_vertical_ponds_gets_waiver():
    result = detect_category_adjacency(VERTICAL_DETS)
    assert should_waive_shelftalker('PONDS', result) is True


def test_vertical_haircare_no_waiver():
    result = detect_category_adjacency(VERTICAL_DETS)
    assert should_waive_shelftalker('HAIRCARE', result) is False
```

**Step 2: Run to verify vertical tests fail**

```bash
python3 -m pytest tests/test_adjacency_detector.py::test_vertical_ponds_gets_waiver tests/test_adjacency_detector.py::test_vertical_haircare_no_waiver -v 2>&1 | tail -10
```
Expected: FAILED

**Step 3: Simplify should_waive_shelftalker to use get_required_legs**

Replace `should_waive_shelftalker` in `core/adjacency_detector.py` (lines ~370-432):

```python
def should_waive_shelftalker(category: str, adjacency_info: Dict) -> bool:
    rules = _load_adjacency_rules()

    if not rules.get('common_leg_shelftalker_waiver', False):
        return False

    if not adjacency_info.get('adjacency_detected'):
        return False

    cat_info = adjacency_info.get('categories', {}).get(category, {})
    if not cat_info.get('adjacent_to'):
        return False

    # Waive if required legs are less than default (category shares a leg)
    default = rules.get('default_legs', {}).get(category, 4)
    required = get_required_legs(category, adjacency_info)
    waived = required < default

    if waived:
        logger.info(f"Shelftalker waived for {category}: required {required} < default {default}")
    else:
        logger.debug(f"Shelftalker NOT waived for {category}: required {required} == default {default}")

    return waived
```

**Step 4: Run all tests**

```bash
python3 -m pytest tests/test_adjacency_detector.py -v 2>&1 | tail -20
```
Expected: all PASSED

**Step 5: Commit**

```bash
git add core/adjacency_detector.py tests/test_adjacency_detector.py
git commit -m "feat: orientation-aware shelftalker waiver in should_waive_shelftalker"
```

---

### Task 5: Smoke test with real visit logs

**Files:**
- Read: pipeline logs

**Step 1: Run a quick import check**

```bash
python3 -c "
from core.adjacency_detector import detect_category_adjacency, get_required_legs, should_waive_shelftalker
print('imports OK')
"
```
Expected: `imports OK`

**Step 2: Verify no regressions on existing horizontal logic**

```bash
python3 -m pytest tests/test_adjacency_detector.py -v 2>&1 | tail -20
```
Expected: all PASSED

**Step 3: Commit (if any fixups)**

```bash
git add -p
git commit -m "fix: adjacency detector smoke test fixups"
```
(skip if nothing to commit)
