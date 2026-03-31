# Slot Adherence Logic - Percentage-Based Threshold

## Overview
The slot adherence check determines whether sachets are positioned correctly below their designated brand hangers. As of this update, the logic uses a **percentage-based threshold** instead of requiring all sachets to be perfectly placed.

## Configuration
Located in `config/config.yaml`:
```yaml
sachet:
  slot_adherence_threshold: 80  # Percentage (0-100)
```

## Logic
For each product (e.g., "Clear Men Cool Sport Menthol Shampoo"):

1. **Count total visible sachets** (including rotated variants)
   - Example: `clear_men_shamp_csm` (12) + `clear_men_shamp_csm_rotate` (3) = **15 total**

2. **Count misplaced sachets** from `slot_adherence_details.misplaced_sachets[]`
   - Example: 1 misplaced → **1 misplaced**

3. **Calculate correctly placed**
   - Correctly placed = Total visible - Misplaced
   - Example: 15 - 1 = **14 correctly placed**

4. **Calculate placement percentage**
   - Percentage = (Correctly placed / Total visible) × 100
   - Example: (14 / 15) × 100 = **93.3%**

5. **Apply threshold**
   - If percentage >= `slot_adherence_threshold` → **"Yes"**
   - If percentage < `slot_adherence_threshold` → **"No"**
   - If no hanger mapping exists (e.g., Clinic Plus) → **"N/A"**

## Examples

| Product | Total | Misplaced | Correct | % | Threshold | Result |
|---------|-------|-----------|---------|---|-----------|--------|
| Clear Anti Dandruff | 11 | 11 | 0 | 0% | 80% | **No** |
| Clear Men Cool Sport | 15 | 1 | 14 | 93.3% | 80% | **Yes** ✓ |
| Sunsilk Black Shine | 6 | 2 | 4 | 66.7% | 80% | **No** |

## Rationale

### Previous Behavior (strict "any" check):
- Used `any(base_cls in misplaced_classes for base_cls in base_classes)`
- If **ANY** sachet was misplaced → entire product marked "No"
- Problem: 1 misplaced out of 15 sachets (93.3% correct) still failed

### New Behavior (percentage threshold):
- Allows minor misplacements while still catching major violations
- Default 80% threshold balances strictness and real-world practicality
- Example: 14/15 correctly placed (93.3%) passes as "Yes"
- Example: 4/6 correctly placed (66.7%) fails as "No"

## Threshold Tuning Guide

| Threshold | Behavior | Use Case |
|-----------|----------|----------|
| 100% | Strictest - all must be perfect | Quality control, audits |
| 90% | Very strict - allows 1-2 errors | High compliance standards |
| **80%** | **Balanced - current default** | **Real-world displays** |
| 70% | Lenient - allows ~30% errors | Lenient compliance |
| 50% | Very lenient - majority rule | Initial rollout phase |

## Code Location

**File:** `utils/aggregator.py`  
**Lines:** ~240-265

```python
# Calculate placement percentage
total_misplaced = sum(misplaced_counts.get(base_cls, 0) for base_cls in base_classes)
total_visible = group_data["total_qty"]
correctly_placed = total_visible - total_misplaced
placement_percentage = (correctly_placed / total_visible * 100) if total_visible > 0 else 0

# Load threshold from config (default 80%)
config = _load_config()
threshold = config.get('sachet', {}).get('slot_adherence_threshold', 80)

# Apply threshold
slot_adh = "Yes" if placement_percentage >= threshold else "No"
```

## Testing

Run the test script to verify:
```bash
conda run -n taco python3 tests/test_slot_adherence_aggregation.py
```

Expected output:
- Clear Anti Dandruff: 0% → "No" ✓
- Clear Men: 93.3% → "Yes" ✓
- Sunsilk: 66.7% → "No" ✓
