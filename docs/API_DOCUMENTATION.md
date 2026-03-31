# UBL Backend API Documentation

## Base URL
```
http://localhost:8000
```

---

## 1. Generate Presigned Upload URLs

**Endpoint:** `POST /api/audits/{visit_id}/upload-urls`

### Request Body

```json
{
  "visit_id": "1234",
  "shop_id": "shop_001",
  "merchandiser_id": "user_001",
  "image_types": ["fixed_shelf"],
  "metadata": {
    "fixed_shelf": {
      "shelf_type": "Perfect Store - Ponds",
      "channel": "PBS",
      "category": "skincare"
    }
  }
}
```

### Request Body Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `visit_id` | string | Yes | Unique visit/audit identifier |
| `shop_id` | string | Yes | Shop identifier |
| `merchandiser_id` | string | Yes | User/merchandiser identifier |
| `image_types` | array | No | List of image types to upload. Defaults to all types if not provided |
| `metadata` | object | No | Per-image-type metadata (see below) |

### Image Types

Available image types:
- `share_of_shelf` - Share of Shelf analysis
- `fixed_shelf` - QPDS/Fixed Shelf analysis (supports metadata)
- `sachet` - Sachet compliance
- `posm` - POSM compliance

### Metadata Structure (for fixed_shelf)

```json
{
  "fixed_shelf": {
    "shelf_type": "Hair Care Premium QPDS",
    "channel": "PBS",
    "category": "haircare"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `shelf_type` | string | No | Type of shelf being audited |
| `channel` | string | No | Channel type: "PBS" or "GBS" |
| `category` | string | No | Product category filter |

### Available Shelf Types

- `Hair Care Premium QPDS`
- `Winter Lotion QPDS`
- `Perfect Store - Hair`
- `Perfect Store - Glow & Lovely`
- `Perfect Store - Ponds`
- `Lux Bodywash QPDS`
- `Vim Liquid QPDS`
- `Oral Care QPDS`
- `Junior Clean Corner QPDS`
- `Nutrition Store QPDS Single Shelf (1:1)`
- `Nutrition Store QPDS Single Shelf (1:2)`
- `Nutrition Store QPDS Double Shelf (2:1)`
- `Nutrition Store QPDS Double Shelf (2:2)`

### Response

```json
{
  "fixed_shelf": {
    "upload_id": "upl_a1b2c3d4",
    "s3_key": "raw/1234/fixed_shelf/20241224_120000_abcd1234.jpg",
    "presigned_url": {
      "url": "http://localhost:4566/ubl-shop-audits",
      "fields": {
        "key": "raw/1234/fixed_shelf/20241224_120000_abcd1234.jpg",
        "x-amz-meta-upload-id": "upl_a1b2c3d4",
        "x-amz-meta-visit-id": "1234",
        "x-amz-meta-shop-id": "shop_001",
        "x-amz-meta-merchandiser-id": "user_001",
        "x-amz-meta-image-type": "fixed_shelf",
        "x-amz-meta-shelf-type": "Perfect Store - Ponds",
        "x-amz-meta-channel": "PBS",
        "policy": "...",
        "x-amz-algorithm": "AWS4-HMAC-SHA256",
        "x-amz-credential": "...",
        "x-amz-date": "...",
        "x-amz-signature": "..."
      }
    }
  }
}
```

---

## 2. Upload Image Using Presigned URL

**Method:** `POST` to the presigned URL

### How to Upload

Use the presigned URL response from step 1:

```javascript
// JavaScript/Frontend Example
const formData = new FormData();

// Add all fields from presigned_url.fields
Object.keys(presignedUrl.fields).forEach(key => {
  formData.append(key, presignedUrl.fields[key]);
});

// Add the file LAST
formData.append('file', imageFile);

// Upload
const response = await fetch(presignedUrl.url, {
  method: 'POST',
  body: formData
});
```

```python
# Python Example
import requests

presigned_data = response.json()['fixed_shelf']
presigned_url = presigned_data['presigned_url']

with open('image.jpg', 'rb') as f:
    files = {'file': f}
    response = requests.post(
        presigned_url['url'],
        data=presigned_url['fields'],
        files=files
    )
```

### Success Response

- Status Code: `204 No Content` or `200 OK`
- Empty body

---

## 3. Get Uploaded Images

**Endpoint:** `GET /api/audits/{visit_id}/images`

### Response

```json
{
  "visit_id": "1234",
  "total_images": 1,
  "images": {
    "upl_a1b2c3d4": {
      "id": "upl_a1b2c3d4",
      "visit_id": "1234",
      "shop_id": "shop_001",
      "merchandiser_id": "user_001",
      "image_type": "fixed_shelf",
      "s3_key": "raw/1234/fixed_shelf/20241224_120000_abcd1234.jpg",
      "status": "pending_upload",
      "metadata": {
        "shelf_type": "Perfect Store - Ponds",
        "channel": "PBS",
        "category": "skincare"
      },
      "created_at": "2024-12-24T12:00:00.000000"
    }
  }
}
```

---

## 4. Get AI Processing Results

**Endpoint:** `GET /api/audits/{visit_id}/results`

### Response

```json
{
  "visit_id": "1234",
  "results": {
    "fixed_shelf": {
      "model_version": "QPDS + Shelftalker + Exclusivity",
      "shelf_type": "Perfect Store - Ponds",
      "channel": "PBS",
      "status": "completed",
      "overall_compliance": 85.5,
      "planogram_adherence": "Yes",
      "exclusively": "Yes",
      "variant_compliance": 90.0,
      "shelf_talker_present": "Yes",
      "shelf_talker_orientation_correct": "Yes",
      "products": [
        {
          "sku_name": "da_ponds_age_miracle_50ml",
          "planned_qty": 4,
          "visible_qty": 4,
          "accuracy": 100.0
        }
      ],
      "totals": {
        "total_planned": 20,
        "total_visible": 18
      },
      "no_of_shelftalker": 4,
      "total_products": 18,
      "summary": "Fixed Shelf: 18 products, 85.5% compliance, Planogram: Pass, Shelftalker: Pass, Exclusivity: yes"
    }
  }
}
```

---

## 5. Health Check

**Endpoint:** `GET /health`

### Response

```json
{
  "status": "healthy"
}
```

---

## Complete Flow Example

### Step 1: Request Upload URLs

```bash
curl -X POST http://localhost:8000/api/audits/1234/upload-urls \
  -H "Content-Type: application/json" \
  -d '{
    "visit_id": "1234",
    "shop_id": "shop_001",
    "merchandiser_id": "user_001",
    "image_types": ["fixed_shelf"],
    "metadata": {
      "fixed_shelf": {
        "shelf_type": "Perfect Store - Ponds",
        "channel": "PBS"
      }
    }
  }'
```

### Step 2: Upload Image

```bash
# Extract presigned URL fields and upload
curl -X POST "http://localhost:4566/ubl-shop-audits" \
  -F "key=raw/1234/fixed_shelf/20241224_120000_abcd1234.jpg" \
  -F "x-amz-meta-upload-id=upl_a1b2c3d4" \
  -F "x-amz-meta-visit-id=1234" \
  -F "x-amz-meta-shop-id=shop_001" \
  -F "x-amz-meta-image-type=fixed_shelf" \
  -F "x-amz-meta-shelf-type=Perfect Store - Ponds" \
  -F "x-amz-meta-channel=PBS" \
  -F "policy=..." \
  -F "x-amz-algorithm=AWS4-HMAC-SHA256" \
  -F "x-amz-credential=..." \
  -F "x-amz-date=..." \
  -F "x-amz-signature=..." \
  -F "file=@image.jpg"
```

### Step 3: Check Results (after AI processing)

```bash
curl http://localhost:8000/api/audits/1234/results
```

---

## Error Responses

### 404 Not Found

```json
{
  "detail": "No results found for this visit"
}
```

### 500 Internal Server Error

```json
{
  "detail": "Internal server error message"
}
```

---

## Notes for Developers

### Frontend Developer
1. Call `/upload-urls` endpoint first to get presigned URLs
2. Use the presigned URL to upload images directly to S3 (bypasses backend)
3. Poll `/results` endpoint to check for AI processing completion
4. **Important:** Add ALL fields from `presigned_url.fields` to FormData before adding the file

### Backend Developer
1. The API generates presigned URLs that embed metadata directly
2. Images are uploaded to S3 with all metadata attached
3. S3 event notifications trigger AI processing automatically
4. Results are consumed from SQS and stored in S3
5. API endpoints provide query access to results

### Processing Flow
```
Client → POST /upload-urls → Get presigned URL
Client → POST to S3 (presigned) → Image uploaded with metadata
S3 → Event notification → SQS queue
AI Server → Process from SQS → Send results to results queue
Backend → Consume results → Store in S3
Client → GET /results → Retrieve AI analysis
```
