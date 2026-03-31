# UBL AI Backend - Metadata Flow Guide

**Audience**: Backend Developers, Database Team
**Purpose**: Understanding how metadata flows from client upload to AI processing
**Date**: 2025-12-19

---

## Table of Contents
1. [Overview](#overview)
2. [Important Clarification](#important-clarification)
3. [Complete Metadata Flow](#complete-metadata-flow)
4. [Metadata Structure](#metadata-structure)
5. [Code Examples](#code-examples)
6. [Database Migration Options](#database-migration-options)

---

## 1. Overview

Metadata (visit_id, shop_id, image_type, etc.) flows through the system attached to S3 objects, NOT through direct service-to-service communication.

### Key Points:
- ✅ Metadata is stored WITH the S3 object as HTTP headers
- ✅ SQS messages contain ONLY the S3 location (bucket + key)
- ✅ AI Server retrieves metadata by calling S3 API (`head_object`)
- ❌ Backend does NOT send metadata directly to AI Server
- ❌ Metadata is NOT embedded in SQS messages (currently)

---

## 2. Important Clarification

### Common Misconception:
"The backend sends metadata along with the image to the AI server"

### Actual Architecture:
The backend does NOT send anything to the AI server. The flow is:

```
Client → S3 (image + metadata) → Event Notification → SQS → AI Server polls SQS
                                                                    ↓
                                                          AI Server ← S3 (retrieves metadata + image)
```

This is a **pull-based architecture** where:
- S3 is the single source of truth
- AI Server pulls both image data and metadata from S3
- Services communicate asynchronously via SQS queues

---

## 3. Complete Metadata Flow

### Step-by-Step Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ STEP 1: Client Uploads Image to S3 with Metadata                    │
└─────────────────────────────────────────────────────────────────────┘

Client Application
  │
  │ POST (multipart/form-data)
  │ To: Presigned URL or Direct S3 Upload
  │
  ├── File: image.jpg (binary data)
  │
  └── HTTP Headers (S3 Object Metadata):
      ├── x-amz-meta-upload-id: "550e8400-e29b-41d4-a716-446655440000"
      ├── x-amz-meta-image-type: "share_of_shelf"
      ├── x-amz-meta-visit-id: "aud_123456"
      ├── x-amz-meta-shop-id: "shop_789"
      ├── x-amz-meta-shelf-type: "Hair Care Premium QPDS" (optional)
      └── x-amz-meta-channel: "PBS" (optional, for Perfect Store shelves)

  ↓

S3 Object Created
  ├── Bucket: ubl-shop-audits
  ├── Key: raw/aud_123456/share_of_shelf/550e8400-e29b-41d4-a716-446655440000.jpg
  ├── Binary Content: <JPEG image bytes>
  └── Object Metadata (stored by S3):
      {
        "upload-id": "550e8400-e29b-41d4-a716-446655440000",
        "image-type": "share_of_shelf",
        "visit-id": "aud_123456",
        "shop-id": "shop_789"
      }

┌─────────────────────────────────────────────────────────────────────┐
│ STEP 2: S3 Triggers Event Notification to SQS                       │
└─────────────────────────────────────────────────────────────────────┘

S3 Event (ObjectCreated:Put)
  │
  │ Automatic event notification configured on bucket
  │
  ↓

SQS Queue: image-processing

Message Body:
{
  "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "eventName": "ObjectCreated:Put",
      "s3": {
        "bucket": {
          "name": "ubl-shop-audits"
        },
        "object": {
          "key": "raw/aud_123456/share_of_shelf/550e8400-e29b-41d4-a716-446655440000.jpg"
        }
      }
    }
  ]
}

⚠️ CRITICAL NOTE: Metadata is NOT included in this message!
                  Only the S3 location (bucket name + object key) is sent.

┌─────────────────────────────────────────────────────────────────────┐
│ STEP 3: AI Server Polls SQS Queue                                   │
└─────────────────────────────────────────────────────────────────────┘

AI Server (Continuous Loop)
  │
  │ receive_message(QueueUrl=image_queue, WaitTimeSeconds=10)
  │
  ↓

Receives message with S3 location:
  {
    "bucket": "ubl-shop-audits",
    "key": "raw/aud_123456/share_of_shelf/550e8400.jpg"
  }

┌─────────────────────────────────────────────────────────────────────┐
│ STEP 4: AI Server Retrieves Metadata from S3                        │
└─────────────────────────────────────────────────────────────────────┘

AI Server makes TWO separate S3 API calls:

╔═══════════════════════════════════════════════════════════════════╗
║ API Call #1: HEAD_OBJECT (Retrieve Object Metadata Only)         ║
╚═══════════════════════════════════════════════════════════════════╝

Request:
  s3_client.head_object(
    Bucket='ubl-shop-audits',
    Key='raw/aud_123456/share_of_shelf/550e8400.jpg'
  )

Response:
  {
    'ContentLength': 2458392,
    'ContentType': 'image/jpeg',
    'Metadata': {                          ← METADATA RETRIEVED HERE
      'upload-id': '550e8400-e29b-41d4-a716-446655440000',
      'image-type': 'share_of_shelf',
      'visit-id': 'aud_123456',
      'shop-id': 'shop_789',
      'shelf-type': None
    },
    'LastModified': datetime(2025, 12, 19, 10, 30, 45)
  }

AI Server extracts:
  ✓ upload_id = "550e8400-e29b-41d4-a716-446655440000"
  ✓ image_type = "share_of_shelf"
  ✓ visit_id = "aud_123456"
  ✓ shop_id = "shop_789"
  ✓ shelf_type = None (not applicable for share_of_shelf)


╔═══════════════════════════════════════════════════════════════════╗
║ API Call #2: GET_OBJECT (Download Image Binary Data)             ║
╚═══════════════════════════════════════════════════════════════════╝

Request:
  s3_client.get_object(
    Bucket='ubl-shop-audits',
    Key='raw/aud_123456/share_of_shelf/550e8400.jpg'
  )

Response:
  {
    'Body': <StreamingBody>,  ← Binary image data
    'ContentLength': 2458392,
    'ContentType': 'image/jpeg'
  }

AI Server reads:
  image_data = image_obj['Body'].read()  # ~2.4 MB JPEG bytes

┌─────────────────────────────────────────────────────────────────────┐
│ STEP 5: AI Server Processes Image                                   │
└─────────────────────────────────────────────────────────────────────┘

AI Server now has:
  ✓ Metadata (from head_object)
  ✓ Image binary data (from get_object)

Processing:
  1. Validate image_type
  2. Load image with PIL
  3. Route to appropriate model based on image_type
  4. Run AI inference
  5. Calculate compliance using config files
  6. Send results to SQS ai-results queue

┌─────────────────────────────────────────────────────────────────────┐
│ STEP 6: AI Server Sends Results to Backend                          │
└─────────────────────────────────────────────────────────────────────┘

SQS Queue: ai-results

Message includes metadata from Step 4:
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440000",
  "visit_id": "aud_123456",
  "shop_id": "shop_789",
  "image_type": "share_of_shelf",
  "s3_key": "raw/aud_123456/share_of_shelf/550e8400.jpg",
  "processing_status": "completed",
  "processed_at": "2025-12-19T10:31:15.123456",
  "ai_results": { ... }
}
```

---

## 4. Metadata Structure

### 4.1 Required Metadata Fields

All image uploads MUST include these metadata fields:

| Field Name | S3 Header | Example Value | Required | Description |
|-----------|-----------|---------------|----------|-------------|
| upload_id | x-amz-meta-upload-id | "550e8400-e29b-..." | ✅ Yes | Unique identifier (UUID v4) |
| image_type | x-amz-meta-image-type | "share_of_shelf" | ✅ Yes | Type of analysis |
| visit_id | x-amz-meta-visit-id | "aud_123456" | ✅ Yes | Audit/visit identifier |
| shop_id | x-amz-meta-shop-id | "shop_789" | ✅ Yes | Shop identifier |
| shelf_type | x-amz-meta-shelf-type | "Hair Care Premium QPDS" | ⚠️ Conditional | Required only for fixed_shelf |
| channel | x-amz-meta-channel | "PBS" or "GBS" | ⚠️ Conditional | Required for Perfect Store shelves |

### 4.2 Valid Values

**image_type** (exactly one of):
- `"share_of_shelf"` - General product distribution analysis
- `"fixed_shelf"` - Fixed planogram compliance (requires shelf_type)
- `"sachet"` - Sachet display compliance
- `"posm"` - Point of Sale Materials

**shelf_type** (required when image_type = "fixed_shelf"):
- "Hair Care Premium QPDS"
- "Winter Lotion QPDS"
- "Perfect Store - Hair"
- "Perfect Store - Glow & Lovely"
- "Perfect Store - Ponds"
- "Lux Bodywash QPDS"
- "Vim Liquid QPDS"
- "Oral Care QPDS"
- "Junior Clean Corner QPDS"
- "Nutrition Store QPDS Single Shelf (1:1)"
- "Nutrition Store QPDS Single Shelf (1:2)"
- "Nutrition Store QPDS Double Shelf (2:1)"
- "Nutrition Store QPDS Double Shelf (2:2)"

### 4.3 S3 Key Naming Convention

```
Pattern:
  raw/{visit_id}/{image_type}/{upload_id}.jpg

Examples:
  raw/aud_123456/share_of_shelf/550e8400-e29b-41d4-a716-446655440000.jpg
  raw/aud_789012/fixed_shelf/660e8400-e29b-41d4-a716-446655440001.jpg
  raw/aud_345678/sachet/770e8400-e29b-41d4-a716-446655440002.jpg
  raw/aud_901234/posm/880e8400-e29b-41d4-a716-446655440003.jpg
```

This naming convention serves as a **fallback** if S3 metadata retrieval fails:
```python
# Fallback parsing from S3 key
parts = s3_key.split('/')
# parts = ['raw', 'aud_123456', 'share_of_shelf', '550e8400-...jpg']
visit_id = parts[1]      # aud_123456
image_type = parts[2]    # share_of_shelf
```

---

## 5. Code Examples

### 5.1 AI Server: Metadata Retrieval

**File**: `simulation/ai-server/main.py` (lines 938-970)

```python
async def process_image(sqs_message, worker_id: int = 0):
    """Process a single image from S3"""

    # Parse SQS message to get S3 location
    body = sqs_message['Body']
    event = json.loads(body)

    # Extract bucket and key from S3 event
    s3_record = event['Records'][0]['s3']
    bucket = s3_record['bucket']['name']
    s3_key = s3_record['object']['key']

    logger.info(f"[Worker {worker_id}] Processing: {s3_key}")

    # ═══════════════════════════════════════════════════════════
    # STEP 1: Fetch metadata from S3 (head_object)
    # ═══════════════════════════════════════════════════════════
    upload_id = 'unknown'
    image_type = 'unknown'
    visit_id = 'unknown'
    shop_id = 'unknown'
    shelf_type = None
    channel = None

    try:
        # HEAD request - gets metadata without downloading image
        metadata_response = s3_client.head_object(
            Bucket=bucket,
            Key=s3_key
        )

        # Extract metadata dictionary
        metadata = metadata_response.get('Metadata', {})

        # Parse individual fields
        upload_id = metadata.get('upload-id', 'unknown')
        image_type = metadata.get('image-type', 'unknown')
        visit_id = metadata.get('visit-id', 'unknown')
        shop_id = metadata.get('shop-id', 'unknown')
        shelf_type = metadata.get('shelf-type')  # May be None
        channel = metadata.get('channel')  # PBS or GBS for Perfect Store

    except Exception as e:
        logger.warning(f"Could not fetch metadata: {e}")

    # ═══════════════════════════════════════════════════════════
    # FALLBACK: Parse from S3 key structure
    # ═══════════════════════════════════════════════════════════
    if image_type == 'unknown' or visit_id == 'unknown':
        parts = s3_key.split('/')
        # Expected: ['raw', visit_id, image_type, 'filename.jpg']
        if len(parts) >= 4 and parts[0] == 'raw':
            visit_id = parts[1]
            image_type = parts[2]

    logger.info(f"[Worker {worker_id}] Upload: {upload_id}, Type: {image_type}, Audit: {visit_id}")

    # Validate image type
    supported_types = ['share_of_shelf', 'fixed_shelf', 'sachet', 'posm']
    if image_type not in supported_types:
        logger.warning(f"[Worker {worker_id}] Unsupported image type '{image_type}', skipping")
        return

    # ═══════════════════════════════════════════════════════════
    # STEP 2: Download image from S3 (get_object)
    # ═══════════════════════════════════════════════════════════
    image_obj = s3_client.get_object(Bucket=bucket, Key=s3_key)
    image_data = image_obj['Body'].read()

    logger.info(f"[Worker {worker_id}] Downloaded {len(image_data)} bytes")

    # ═══════════════════════════════════════════════════════════
    # STEP 3: Process with AI model
    # ═══════════════════════════════════════════════════════════
    ai_result = await route_to_ai_model(
        image_type,
        image_data,
        worker_id=worker_id,
        metadata={"shelf_type": shelf_type, "channel": channel} if shelf_type or channel else None
    )

    # ═══════════════════════════════════════════════════════════
    # STEP 4: Send result to backend via SQS
    # ═══════════════════════════════════════════════════════════
    result_message = {
        "upload_id": upload_id,
        "visit_id": visit_id,
        "shop_id": shop_id,
        "image_type": image_type,
        "s3_key": s3_key,
        "processing_status": "completed",
        "ai_results": ai_result,
        "processed_at": datetime.utcnow().isoformat()
    }

    sqs_client.send_message(
        QueueUrl=SQS_RESULTS_QUEUE_URL,
        MessageBody=json.dumps(result_message)
    )
```

### 5.2 Client: Uploading with Metadata (Presigned URL Pattern)

**File**: `simulation/client/main.py` (conceptual)

```python
import requests
import boto3

# ═══════════════════════════════════════════════════════════
# Step 1: Request presigned URL from backend
# ═══════════════════════════════════════════════════════════
response = requests.post(
    'http://backend/api/audits/aud_123456/upload-urls',
    json={
        'visit_id': 'aud_123456',
        'shop_id': 'shop_789',
        'merchandiser_id': 'user_456'
    }
)

presigned_data = response.json()['share_of_shelf']

# presigned_data contains:
# {
#   'upload_id': '550e8400-e29b-41d4-a716-446655440000',
#   'presigned_url': {
#     'url': 'http://s3.amazonaws.com/ubl-shop-audits/...',
#     'fields': {
#       'key': 'raw/aud_123456/share_of_shelf/550e8400.jpg',
#       'x-amz-meta-upload-id': '550e8400-...',
#       'x-amz-meta-image-type': 'share_of_shelf',
#       'x-amz-meta-visit-id': 'aud_123456',
#       'x-amz-meta-shop-id': 'shop_789'
#     }
#   }
# }

# ═══════════════════════════════════════════════════════════
# Step 2: Upload image using presigned URL
# ═══════════════════════════════════════════════════════════
with open('image.jpg', 'rb') as f:
    files = {'file': f}

    # POST to presigned URL with metadata fields
    response = requests.post(
        presigned_data['presigned_url']['url'],
        data=presigned_data['presigned_url']['fields'],  # Includes metadata
        files=files
    )

# Metadata is now attached to S3 object automatically!
```

### 5.3 Backend: Generating Presigned URLs with Metadata

```python
import boto3
import uuid
from datetime import datetime, timedelta

s3_client = boto3.client('s3')

def generate_upload_urls(visit_id, shop_id, image_types):
    """Generate presigned URLs with metadata for image uploads"""

    presigned_urls = {}

    for image_type in image_types:
        upload_id = str(uuid.uuid4())
        s3_key = f'raw/{visit_id}/{image_type}/{upload_id}.jpg'

        # Generate presigned POST with metadata
        presigned_post = s3_client.generate_presigned_post(
            Bucket='ubl-shop-audits',
            Key=s3_key,
            Fields={
                # Metadata fields - will be attached to S3 object
                'x-amz-meta-upload-id': upload_id,
                'x-amz-meta-image-type': image_type,
                'x-amz-meta-visit-id': visit_id,
                'x-amz-meta-shop-id': shop_id,
                'Content-Type': 'image/jpeg'
            },
            Conditions=[
                {'x-amz-meta-upload-id': upload_id},
                {'x-amz-meta-image-type': image_type},
                {'x-amz-meta-visit-id': visit_id},
                {'x-amz-meta-shop-id': shop_id},
                {'Content-Type': 'image/jpeg'},
                ['content-length-range', 1024, 10485760]  # 1KB - 10MB
            ],
            ExpiresIn=3600  # 1 hour
        )

        presigned_urls[image_type] = {
            'upload_id': upload_id,
            'presigned_url': presigned_post
        }

    return presigned_urls
```

### 5.4 Direct S3 Upload with Metadata (Alternative)

```python
import boto3

s3_client = boto3.client('s3')

def upload_image_direct(image_path, visit_id, shop_id, image_type, upload_id):
    """Upload image directly to S3 with metadata"""

    s3_key = f'raw/{visit_id}/{image_type}/{upload_id}.jpg'

    with open(image_path, 'rb') as f:
        s3_client.put_object(
            Bucket='ubl-shop-audits',
            Key=s3_key,
            Body=f,
            ContentType='image/jpeg',
            Metadata={                          # ← Metadata attached here
                'upload-id': upload_id,
                'image-type': image_type,
                'visit-id': visit_id,
                'shop-id': shop_id
            }
        )

    print(f"✓ Uploaded to: {s3_key}")
    print(f"  Metadata: visit={visit_id}, shop={shop_id}, type={image_type}")
```

---

## 6. Database Migration Options

When migrating from S3-stored metadata to database-stored metadata, you have two main options:

### Option A: Database Lookup (Pull Model)

AI Server queries database to get metadata instead of calling S3.

**Flow**:
```
SQS Message → AI Server → Database API (GET /api/uploads/{s3_key})
                            ↓
                        Returns metadata
```

**Pros**:
- Single source of truth (database)
- No duplicate data in SQS messages
- Easy to update metadata after upload

**Cons**:
- Additional database query per image
- Requires database to be available before processing

**Implementation**:

```python
# AI Server modification
async def process_image(sqs_message, worker_id: int = 0):
    body = sqs_message['Body']
    event = json.loads(body)

    s3_key = event['Records'][0]['s3']['object']['key']

    # NEW: Query database instead of S3 head_object
    response = requests.get(f'http://backend-api/api/uploads/metadata?s3_key={s3_key}')
    metadata = response.json()

    upload_id = metadata['upload_id']
    image_type = metadata['image_type']
    visit_id = metadata['visit_id']
    shop_id = metadata['shop_id']
    shelf_type = metadata.get('shelf_type')

    # Continue processing...
```

**Required Database API**:
```python
@app.get("/api/uploads/metadata")
def get_upload_metadata(s3_key: str):
    """Get metadata for an S3 object from database"""
    upload = db.query(ImageUpload).filter_by(s3_key=s3_key).first()

    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    return {
        "upload_id": upload.upload_id,
        "visit_id": upload.visit_id,
        "shop_id": upload.shop_id,
        "image_type": upload.image_type,
        "shelf_type": upload.shelf_type
    }
```

### Option B: Embed Metadata in SQS Message (Push Model)

Include metadata directly in SQS message body.

**Flow**:
```
Backend → SQS (with metadata embedded) → AI Server
```

**Pros**:
- No additional API calls
- Faster processing (no database lookup)
- Self-contained messages

**Cons**:
- Metadata duplicated in database and SQS
- Messages become larger
- Can't update metadata after message is sent

**Implementation**:

```python
# Backend: Send custom message to SQS (instead of S3 event)
def trigger_ai_processing(upload_id, visit_id, shop_id, image_type, s3_key, shelf_type=None):
    """Send processing request to AI Server with metadata"""

    message = {
        'upload_id': upload_id,
        'visit_id': visit_id,
        'shop_id': shop_id,
        'image_type': image_type,
        'shelf_type': shelf_type,
        's3': {
            'bucket': {'name': 'ubl-shop-audits'},
            'object': {'key': s3_key}
        }
    }

    sqs_client.send_message(
        QueueUrl=SQS_IMAGE_QUEUE_URL,
        MessageBody=json.dumps(message)
    )
```

```python
# AI Server: Read metadata directly from message
async def process_image(sqs_message, worker_id: int = 0):
    body = sqs_message['Body']
    message = json.loads(body)

    # Extract metadata directly from message (no API call needed)
    upload_id = message['upload_id']
    visit_id = message['visit_id']
    shop_id = message['shop_id']
    image_type = message['image_type']
    shelf_type = message.get('shelf_type')

    # Extract S3 location
    bucket = message['s3']['bucket']['name']
    s3_key = message['s3']['object']['key']

    # Download image from S3
    image_obj = s3_client.get_object(Bucket=bucket, Key=s3_key)
    image_data = image_obj['Body'].read()

    # Continue processing...
```

### Recommendation: Option B (Embed in SQS)

**Recommended approach**: Embed metadata in SQS messages

**Reasoning**:
1. **Performance**: No additional database query per image (important for high throughput)
2. **Simplicity**: Self-contained messages are easier to debug and monitor
3. **Decoupling**: AI Server doesn't need database access
4. **Scalability**: Reduces database load during peak processing

**Migration Steps**:
1. Backend creates database record when image is uploaded
2. Backend sends SQS message with metadata embedded
3. AI Server processes message (no database call needed)
4. AI Server sends results back to Backend via SQS
5. Backend stores results in database

---

## 7. Troubleshooting

### Issue: Metadata not found

**Symptom**: AI Server logs show "Could not fetch metadata"

**Possible Causes**:
1. S3 object uploaded without metadata headers
2. Metadata headers not prefixed with `x-amz-meta-`
3. S3 permissions issue

**Solution**:
```python
# Verify metadata exists
response = s3_client.head_object(Bucket='ubl-shop-audits', Key=s3_key)
print(response.get('Metadata', {}))
```

### Issue: Incorrect image routing

**Symptom**: Share of shelf images processed as fixed shelf

**Possible Causes**:
1. Wrong `image_type` in metadata
2. S3 key structure doesn't match pattern

**Solution**:
```python
# Validate before upload
valid_types = ['share_of_shelf', 'fixed_shelf', 'sachet', 'posm']
assert image_type in valid_types, f"Invalid image_type: {image_type}"
```

### Issue: Missing shelf_type for fixed_shelf

**Symptom**: Fixed shelf processing fails or uses wrong standards

**Possible Causes**:
1. `shelf_type` metadata not provided
2. Invalid shelf_type value

**Solution**:
```python
# Validate shelf_type for fixed_shelf
if image_type == 'fixed_shelf':
    assert shelf_type is not None, "shelf_type required for fixed_shelf"
    assert shelf_type in VALID_SHELF_TYPES, f"Invalid shelf_type: {shelf_type}"
```

---

## 8. Summary

### Current Architecture (S3 Metadata):
1. ✅ Metadata stored in S3 object headers
2. ✅ SQS contains only S3 location
3. ✅ AI Server calls `head_object()` to get metadata
4. ✅ AI Server calls `get_object()` to download image

### Recommended Future Architecture (Database + SQS):
1. ✅ Metadata stored in database when image uploaded
2. ✅ SQS message includes metadata (no S3 head_object needed)
3. ✅ AI Server reads metadata from SQS message
4. ✅ AI Server calls `get_object()` to download image
5. ✅ AI Server queries database for compliance standards

### Key Takeaway:
**Backend does NOT send data to AI Server.** The system uses asynchronous, queue-based communication where S3 serves as the data source and SQS coordinates processing.

---

**End of Document**
