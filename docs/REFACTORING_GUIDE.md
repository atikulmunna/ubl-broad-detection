# Share of Shelf Category Aggregation - Implementation & Migration Guide

## What Was Changed (Current Implementation)

### Summary
Added category-wise splitting to Share of Shelf results. SOS images now return separate results per product category (hair_care, skin_care, oral_care, etc.) instead of single combined result.

### Files Modified
1. **`main.py:673-692`** - `analyze_share_of_shelf()` - Groups products by category
2. **`main.py:1142-1171`** - `_transform_result()` - Transforms each category separately
3. **`main.py:1223-1259`** - `_build_aggregated_result()` - Aggregates categories across images
4. **`utils/sos_category_mapping.py`** - NEW - Maps 92 products → 8 categories

### Categories Supported
- `hair_care` - Sunsilk, Dove, Clear, Tresemme
- `skin_care` - Glow & Lovely, Pond's, Vaseline, Dove lotion
- `oral_care` - Pepsodent, Closeup
- `nutrition` - Horlicks, Boost, Maltova
- `fabric` - Surf Excel, Wheel, Rin
- `skin_cleansing` - Lux, Lifebuoy, Dove bar
- `home_and_hygiene` - Vim, Domex
- `mini_meals` - (reserved)

---

## Current AI Server Flow

### Input (S3 Metadata)
```json
{
  "upload-id": "img_123",
  "image-type": "share_of_shelf",
  "visit-id": "visit_789",
  "expected-images-count": "2"
}
```

### Processing Steps

#### Step 1: Image Download & AI Detection
```python
# main.py:640 - analyze_share_of_shelf()
pil_image = Image.open(BytesIO(image_data))
results = model_manager.predict('ubl', source=pil_image, conf=0.20)

# Detects: sunsilk_black_small, dove_hfr_small, gl_mltvit_crm, ponds_white_beauty_fw
```

#### Step 2: Category Grouping (NEW)
```python
# main.py:673-680
from utils.sos_category_mapping import get_sos_category

category_breakdown = {
    "hair_care": {
        "sunsilk_black_small": 4,
        "dove_hfr_small": 2
    },
    "skin_care": {
        "gl_mltvit_crm": 12,
        "ponds_white_beauty_fw": 7
    }
}
```

#### Step 3: Per-Image Transform
```python
# main.py:1142-1171 - _transform_result()
# Returns dict of categories (NOT single object)
{
    "hair_care": {
        "upload_id": "img_123",
        "category_name": "Hair Care",
        "total_visible": 6,
        "results": {
            "brands": [
                {"brand": "sunsilk_black_small", "visible_qty": 4},
                {"brand": "dove_hfr_small", "visible_qty": 2}
            ]
        }
    },
    "skin_care": {
        "upload_id": "img_123",
        "category_name": "Skin Care",
        "total_visible": 19,
        "results": {"brands": [...]}
    }
}
```

#### Step 4: Visit Aggregation (When All Images Complete)
```python
# main.py:1223-1259 - _build_aggregated_result()
# Combines img_123 + img_456 by category

final_output = {
    "visit_id": "visit_789",
    "AI_Result": {
        "share_of_shelf": {
            "hair_care": {
                "overall": {
                    "category_name": "Hair Care",
                    "total_visible": 15,  # Sum across images
                    "image_count": 2
                },
                "brand_details": {
                    "img_123": {...},  # From image 1
                    "img_456": {...}   # From image 2
                }
            },
            "skin_care": {
                "overall": {...},
                "brand_details": {...}
            }
        }
    }
}
```

### Output (SQS Results Queue)
**Full example:**
```json
{
  "visit_id": "visit_789",
  "outlet_id": "shop_001",
  "AI_Result": {
    "share_of_shelf": {
      "hair_care": {
        "overall": {
          "category_name": "Hair Care",
          "total_visible": 15,
          "image_count": 2
        },
        "brand_details": {
          "img_123": {
            "upload_id": "img_123",
            "s3_key": "uploads/123.jpg",
            "category_name": "Hair Care",
            "total_visible": 6,
            "results": {
              "brands": [
                {"company_name": "Unilever", "brand": "sunsilk_black_small", "visible_qty": 4},
                {"company_name": "Unilever", "brand": "dove_hfr_small", "visible_qty": 2}
              ]
            }
          },
          "img_456": {
            "upload_id": "img_456",
            "total_visible": 9,
            "results": {"brands": [...]}
          }
        }
      },
      "skin_care": {
        "overall": {
          "category_name": "Skin Care",
          "total_visible": 38,
          "image_count": 2
        },
        "brand_details": {
          "img_123": {...},
          "img_456": {...}
        }
      }
    }
  }
}
```

---

## Current Architecture Issues (Why This Needs Refactoring)

### Problem 1: AI-Side Visit Aggregation
```python
# main.py:1032 - VisitResultAggregator
self.visits = {
    "visit_789": {
        "results": {...},
        "processed_count": 1,
        "expected_count": 2  # WAITING for 2nd image
    }
}
```

**Issues:**
- ❌ State held in-memory on AI server
- ❌ Lost if server restarts
- ❌ Can't scale to multiple AI servers (each has separate state)
- ❌ No partial results until ALL images complete
- ❌ Memory grows with long visits

### Problem 2: No Database Persistence
- AI server has no DB
- Can't query "how many images processed for visit X?"
- Can't retrieve partial results

### Problem 3: Multi-Server Coordination
```
AI Server 1: Processes img_123 → waits for img_456
AI Server 2: Processes img_456 → waits for img_123
Result: Visit never completes (each server waiting for the other)
```

---

## Future Migration Plan (Backend Aggregation)

### Architecture Change

#### Current (AI-Side Aggregation)
```
S3 → SQS Image Queue → AI Server (VisitResultAggregator)
                           ├─ Holds state in-memory
                           ├─ Waits for all images
                           └─ Sends 1 message when complete
                                ↓
                           SQS Results Queue → Backend
```

#### Future (Backend Aggregation)
```
S3 → SQS Image Queue → AI Server (Stateless)
                           ├─ Process 1 image
                           ├─ No state, no waiting
                           └─ Send result immediately
                                ↓
                           SQS Results Queue → Backend
                                                  ├─ Store in DB (per-image)
                                                  ├─ Check if visit complete
                                                  └─ Aggregate from DB when done
```

---

## Backend Developer Tasks

### Task 1: Create Database Schema

**Table: `ai_image_results`**
```sql
CREATE TABLE ai_image_results (
    id SERIAL PRIMARY KEY,
    visit_id VARCHAR NOT NULL,
    upload_id VARCHAR UNIQUE NOT NULL,
    image_type VARCHAR NOT NULL,  -- 'share_of_shelf', 'fixed_shelf', etc.
    s3_key VARCHAR,

    -- Category-wise SOS results (JSONB)
    category_breakdown JSONB,  -- {"hair_care": {...}, "skin_care": {...}}

    -- Raw AI result
    ai_result JSONB,

    processed_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_visit (visit_id),
    INDEX idx_upload (upload_id)
);

CREATE TABLE visit_tracking (
    visit_id VARCHAR PRIMARY KEY,
    expected_image_count INT,
    processed_image_count INT DEFAULT 0,
    is_complete BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);
```

### Task 2: Modify SQS Consumer

**Current Backend Code (Change This):**
```python
# OLD - Expects aggregated result
def process_sqs_result(message):
    data = json.loads(message['Body'])
    visit_id = data['visit_id']
    ai_result = data['AI_Result']  # Already aggregated

    # Store to DB
    store_visit_result(visit_id, ai_result)
```

**New Backend Code:**
```python
# NEW - Receives per-image results
def process_sqs_result(message):
    data = json.loads(message['Body'])
    visit_id = data['visit_id']
    upload_id = data['upload_id']
    image_type = data['image_type']

    # 1. Store per-image result
    db.execute("""
        INSERT INTO ai_image_results (visit_id, upload_id, image_type, category_breakdown, ai_result)
        VALUES (%s, %s, %s, %s, %s)
    """, (visit_id, upload_id, image_type, data['category_breakdown'], data))

    # 2. Update visit tracking
    db.execute("""
        UPDATE visit_tracking
        SET processed_image_count = processed_image_count + 1
        WHERE visit_id = %s
    """, (visit_id,))

    # 3. Check if visit complete
    visit = db.query("""
        SELECT processed_image_count, expected_image_count
        FROM visit_tracking
        WHERE visit_id = %s
    """, (visit_id,))

    if visit['processed_image_count'] >= visit['expected_image_count']:
        # 4. Aggregate from DB
        aggregate_visit_results(visit_id)
```

### Task 3: Implement Aggregation Function

```python
def aggregate_visit_results(visit_id):
    """Aggregate all images for a visit from DB"""

    # 1. Fetch all SOS results for this visit
    sos_results = db.query("""
        SELECT upload_id, category_breakdown
        FROM ai_image_results
        WHERE visit_id = %s AND image_type = 'share_of_shelf'
    """, (visit_id,))

    # 2. Aggregate by category (SAME LOGIC as AI server lines 1223-1259)
    aggregated_by_category = {}

    for result in sos_results:
        category_breakdown = result['category_breakdown']

        for category, cat_data in category_breakdown.items():
            if category not in aggregated_by_category:
                aggregated_by_category[category] = {
                    "brand_details": {},
                    "total_visible": 0,
                    "image_count": 0
                }

            agg = aggregated_by_category[category]
            agg["image_count"] += 1
            agg["total_visible"] += cat_data.get("total_visible", 0)
            agg["brand_details"][result['upload_id']] = cat_data

    # 3. Build final structure
    final_result = {
        "visit_id": visit_id,
        "AI_Result": {
            "share_of_shelf": {
                category: {
                    "overall": {
                        "category_name": category.replace('_', ' ').title(),
                        "total_visible": agg["total_visible"],
                        "image_count": agg["image_count"]
                    },
                    "brand_details": agg["brand_details"]
                }
                for category, agg in aggregated_by_category.items()
            }
        }
    }

    # 4. Store aggregated result
    db.execute("""
        UPDATE visit_tracking
        SET is_complete = TRUE, completed_at = NOW()
        WHERE visit_id = %s
    """, (visit_id,))

    # 5. Trigger downstream workflows (notifications, reports, etc.)
    publish_visit_complete_event(visit_id, final_result)
```

### Task 4: Remove AI Server Aggregation

**Delete from `main.py`:**
```python
# DELETE this entire class
class VisitResultAggregator:  # Lines 1032-1300
    # ... all of this goes away
```

**Simplify AI result sending:**
```python
# main.py - After processing single image
async def process_image(...):
    ai_result = await route_to_ai_model(image_type, image_data, ...)

    # Send immediately (don't wait for other images)
    result_message = {
        "visit_id": visit_id,
        "upload_id": upload_id,
        "image_type": image_type,
        "category_breakdown": ai_result.get("category_breakdown"),  # For SOS
        "ai_result": ai_result,  # Full result
        "processed_at": datetime.now().isoformat()
    }

    # Send to SQS Results Queue immediately
    sqs_client.send_message(
        QueueUrl=SQS_RESULTS_QUEUE_URL,
        MessageBody=json.dumps(result_message)
    )
```

---

## Migration Checklist

### Backend Team
- [ ] Create `ai_image_results` table
- [ ] Create `visit_tracking` table
- [ ] Update SQS consumer to store per-image results
- [ ] Implement `aggregate_visit_results()` function
- [ ] Add visit completion check logic
- [ ] Test with sample data

### AI Team (After Backend Ready)
- [ ] Remove `VisitResultAggregator` class
- [ ] Remove visit state management
- [ ] Change to immediate SQS sending
- [ ] Update message format (per-image instead of aggregated)
- [ ] Test with LocalStack

### Testing
- [ ] Single image visit → completes immediately
- [ ] Multi-image visit → aggregates when all done
- [ ] Partial results queryable from DB
- [ ] AI server restart → no state lost
- [ ] Multiple AI servers → results properly aggregated

---

## Code Markers for Refactoring

All temporary aggregation code marked with:
```python
# TODO-REFACTOR: Remove this aggregation when moving to backend (Option B)
# In Option B, backend will receive per-image results and aggregate in DB
```

**Search for:** `TODO-REFACTOR` in `main.py`

**Lines to delete during migration:**
- `main.py:1032-1300` - Entire `VisitResultAggregator` class
- `main.py:1223-1259` - Category aggregation logic (moves to backend)

**Lines to keep:**
- `main.py:673-680` - Category grouping in `analyze_share_of_shelf()`
- `main.py:1142-1171` - Category transform in `_transform_result()`
- `utils/sos_category_mapping.py` - All category mapping logic

---

## Benefits After Migration

### AI Server
- ✅ Stateless → easy horizontal scaling
- ✅ No memory accumulation
- ✅ Restart-safe (no state loss)
- ✅ No multi-server coordination needed

### Backend
- ✅ Database-backed state → queryable, persistent
- ✅ Partial results visible → show progress to users
- ✅ Flexible aggregation → can re-aggregate anytime
- ✅ Better error handling → retry individual images

### Overall
- ✅ Production-ready scalability
- ✅ Cleaner separation of concerns (AI vs aggregation)
- ✅ Easier monitoring and debugging
- ✅ Better fault tolerance

---

## Questions?

Contact AI team or refer to:
- `/home/mkultra/.claude/plans/sos-aggregation-architecture.md` - Full architectural analysis
- `/home/mkultra/.claude/plans/wondrous-coalescing-kite.md` - Implementation plan
- `main.py` - Search for `TODO-REFACTOR` comments
