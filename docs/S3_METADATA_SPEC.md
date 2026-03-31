# S3 Metadata Specification for Backend

## Required S3 Metadata Fields

When uploading images to S3, set these metadata fields so AI server can process them:

### Common Fields (All Image Types)
```json
{
  "upload-id": "<uuid>",
  "image-type": "<task_type>",
  "visit-id": "<visit_id>",
  "shop-id": "<outlet_id>",
  "expected-images-count": "<total_images_for_visit>"
}
```

### Task-Specific Fields

#### 1. Fixed Shelf (`category_shelf_display`)
```json
{
  "slab": "<qpds_shelf_name>",
  "channel": "<PBS|GBS|NPS>"
}
```

**Valid slab examples (QPDS shelf names):**
- `RURAL_GBS_POND'S_NATIONAL`
- `METRO_PBS_HC`
- `PREMIUM_PORTFOLIO_QPDS`
- `ORAL_QPDS`
- `LUX_BODYWASH_QPDS`
- `METRO_GBS_GAL_NATIONAL`
- `URBAN_PBS_HC`

#### 2. Share of Shelf (`share_of_shelf`)
```json
{
  "sub-category": "<category>"
}
```

**Valid sub-category values:**
- `hair_care`
- `skin_care`
- `oral_care`
- `nutrition`
- `fabric`
- `skin_cleansing`
- `home_and_hygiene`
- `mini_meals`

#### 3. POSM (`share_of_posm`)
No additional fields required.

#### 4. Sachet (`share_of_sachet`)
No additional fields required.

---

## Complete Example: 4 Images (1 per task)

**Visit ID:** `VISIT_12345`
**Total Images:** 4
**Shop ID:** `OUT_PJP_001`

### Image 1: Fixed Shelf
```json
{
  "upload-id": "uuid_001",
  "image-type": "category_shelf_display",
  "visit-id": "VISIT_12345",
  "shop-id": "OUT_PJP_001",
  "slab": "RURAL_GBS_POND'S_NATIONAL",
  "channel": "GBS",
  "expected-images-count": "4"
}
```

### Image 2: Share of Shelf
```json
{
  "upload-id": "uuid_002",
  "image-type": "share_of_shelf",
  "visit-id": "VISIT_12345",
  "shop-id": "OUT_PJP_001",
  "sub-category": "hair_care",
  "expected-images-count": "4"
}
```

### Image 3: POSM
```json
{
  "upload-id": "uuid_003",
  "image-type": "share_of_posm",
  "visit-id": "VISIT_12345",
  "shop-id": "OUT_PJP_001",
  "expected-images-count": "4"
}
```

### Image 4: Sachet
```json
{
  "upload-id": "uuid_004",
  "image-type": "share_of_sachet",
  "visit-id": "VISIT_12345",
  "shop-id": "OUT_PJP_001",
  "expected-images-count": "4"
}
```

---

## Multi-Image Example: 11 SOS Images

**Scenario:** Home Care parent has 2 sub-categories (fabric: 2 images, home_and_hygiene: 1 image)

```json
// Image 1: fabric
{
  "upload-id": "uuid_009",
  "image-type": "share_of_shelf",
  "visit-id": "VISIT_12345",
  "shop-id": "OUT_PJP_001",
  "sub-category": "fabric",
  "expected-images-count": "22"
}

// Image 2: fabric
{
  "upload-id": "uuid_010",
  "image-type": "share_of_shelf",
  "visit-id": "VISIT_12345",
  "shop-id": "OUT_PJP_001",
  "sub-category": "fabric",
  "expected-images-count": "22"
}

// Image 3: home_and_hygiene
{
  "upload-id": "uuid_011",
  "image-type": "share_of_shelf",
  "visit-id": "VISIT_12345",
  "shop-id": "OUT_PJP_001",
  "sub-category": "home_and_hygiene",
  "expected-images-count": "22"
}
```

---

## Important Notes

1. **`expected-images-count` must be SAME for all images in a visit**
   - AI aggregator waits until this count is reached
   - Count ALL images across all task types

2. **Hyphenated keys in S3 metadata**
   - Use `upload-id` not `upload_id`
   - Use `image-type` not `image_type`
   - Use `visit-id` not `visit_id`
   - Use `shop-id` not `shop_id`
   - Use `sub-category` not `sub_category`
   - Use `expected-images-count` not `expected_images_count`
   - `slab` and `channel` have no hyphens

3. **Case sensitive**
   - `share_of_shelf` not `Share_Of_Shelf`
   - `category_shelf_display` not `Category_Shelf_Display`

4. **AI detects all products regardless of sub-category**
   - If `hair_care` image contains fabric products, AI still detects them
   - `sub-category` is for organization, not filtering

---

## Mapping Backend Categories to AI Sub-Categories

From `payload.json` structure:

| Backend Parent | Backend Sub | AI sub-category |
|---|---|---|
| Home Care | fabsol | `fabric` |
| Home Care | hygin | `home_and_hygiene` |
| Personal Care | Skin Cleansing | `skin_cleansing` |
| Personal Care | Oral Care | `oral_care` |
| Personal Care | Hair Care | `hair_care` |
| Personal Care | Skin Care | `skin_care` |
| Personal Care | Mini Snacks | `mini_meals` |
| Nutrition | food | `nutrition` |

**Use AI sub-category names in S3 metadata, not backend names.**
