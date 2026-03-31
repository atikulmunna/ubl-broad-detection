# UBL AI Backend - Database Migration Guide

**Audience**: Database Developer
**Purpose**: Understanding the data flow, metadata structure, and config-to-database migration requirements
**Date**: 2025-12-19

---

## Table of Contents
1. [System Architecture Overview](#system-architecture-overview)
2. [Data Flow](#data-flow)
3. [Image Metadata Structure](#image-metadata-structure)
4. [Queue System Details](#queue-system-details)
5. [Configuration Files to Database](#configuration-files-to-database)
6. [Database Schema Recommendations](#database-schema-recommendations)
7. [API Integration Points](#api-integration-points)

---

## 1. System Architecture Overview

The UBL AI Backend is a distributed system with three main components:

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Client    │─────▶│  AI Server  │─────▶│   Backend   │
│             │      │             │      │             │
└─────────────┘      └─────────────┘      └─────────────┘
       │                    │                    │
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────────────────────────────────────────────┐
│                    AWS Services                       │
│  - S3 (Image Storage)                                │
│  - SQS (Queue: image-processing, ai-results)         │
└──────────────────────────────────────────────────────┘
```

### Component Responsibilities:

**Client** (`simulation/client/main.py`):
- Uploads images to S3 with metadata
- Triggers AI processing via S3 events

**AI Server** (`simulation/ai-server/main.py`):
- Listens to SQS image-processing queue
- Downloads images from S3
- Runs AI models (YOLO-based detection)
- Sends results to SQS ai-results queue

**Backend** (`simulation/backend/main.py`):
- Listens to SQS ai-results queue
- Stores results in S3 as JSON files

---

## 2. Data Flow

### Step-by-Step Flow:

```
1. CLIENT UPLOAD
   ├── User uploads image via presigned URL
   ├── Image stored in S3: s3://ubl-shop-audits/raw/{visit_id}/{image_type}/{upload_id}.jpg
   └── S3 metadata attached:
       ├── upload-id: unique identifier for this upload
       ├── image-type: share_of_shelf | fixed_shelf | sachet | posm
       ├── visit-id: audit/visit identifier
       ├── shop-id: shop identifier
       └── shelf-type: (optional) for fixed_shelf images only

2. S3 EVENT NOTIFICATION
   └── S3 triggers event to SQS queue: image-processing

3. AI SERVER PROCESSING
   ├── Polls SQS image-processing queue
   ├── Receives message with S3 event details
   ├── Extracts metadata from S3 object
   ├── Downloads image from S3
   ├── Routes to appropriate AI model based on image_type
   ├── Runs inference:
   │   ├── share_of_shelf → DA_YOLO11X model
   │   ├── fixed_shelf → QPDS + Shelftalker + Exclusivity models
   │   ├── sachet → SACHET_YOLO11X model
   │   └── posm → POSM_YOLO11X model
   ├── Calculates compliance scores using config files
   └── Sends results to SQS ai-results queue

4. BACKEND PROCESSING
   ├── Polls SQS ai-results queue
   ├── Receives AI processing results
   ├── Stores results in S3:
   │   └── s3://ubl-shop-audits/results/{visit_id}/{image_type}/{upload_id}.json
   └── Deletes message from queue

5. RESULT RETRIEVAL
   └── Other services read results directly from S3
```

---

## 3. Image Metadata Structure

### 3.1 S3 Object Metadata (HTTP Headers)

When images are uploaded to S3, the following metadata is attached as HTTP headers:

```python
{
    "upload-id": "uuid-v4-string",           # Unique ID for this upload
    "image-type": "share_of_shelf",          # Type of analysis required
    "visit-id": "aud_123456",                # Audit/visit identifier
    "shop-id": "shop_789",                   # Shop identifier
    "shelf-type": "Hair Care Premium QPDS"   # Optional: only for fixed_shelf
}
```

### 3.2 S3 Key Structure

```
S3 Bucket: ubl-shop-audits

Raw Images:
  raw/{visit_id}/{image_type}/{upload_id}.jpg

  Example:
  raw/aud_123456/share_of_shelf/550e8400-e29b-41d4-a716-446655440000.jpg

Results:
  results/{visit_id}/{image_type}/{upload_id}.json

  Example:
  results/aud_123456/share_of_shelf/550e8400-e29b-41d4-a716-446655440000.json
```

### 3.3 Supported Image Types

| image_type      | Description                          | Models Used                           |
|----------------|--------------------------------------|---------------------------------------|
| share_of_shelf | General shelf product distribution   | DA_YOLO11X                           |
| fixed_shelf    | Fixed planogram compliance           | QPDS, Shelftalker, Exclusivity       |
| sachet         | Sachet display compliance            | SACHET_YOLO11X                       |
| posm           | Point of Sale Materials              | POSM_YOLO11X                         |

### 3.4 Additional Metadata for Fixed Shelf

For `image_type = "fixed_shelf"`, an additional metadata field is required:

```python
{
    "shelf-type": "Hair Care Premium QPDS"  # Must match a shelf type in qpds_standards.yaml
}
```

Valid shelf types:
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

---

## 4. Queue System Details

### 4.1 SQS Queues

**Queue 1: image-processing**
- **Purpose**: Trigger AI processing for uploaded images
- **Producer**: S3 (via event notifications)
- **Consumer**: AI Server
- **Message Format**:
```json
{
  "Records": [
    {
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
```

**Queue 2: ai-results**
- **Purpose**: Deliver AI processing results to backend
- **Producer**: AI Server
- **Consumer**: Backend
- **Message Format**:
```json
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440000",
  "visit_id": "aud_123456",
  "shop_id": "shop_789",
  "image_type": "share_of_shelf",
  "s3_key": "raw/aud_123456/share_of_shelf/550e8400-e29b-41d4-a716-446655440000.jpg",
  "result_s3_key": "processed/aud_123456/share_of_shelf/550e8400-e29b-41d4-a716-446655440000_result.json",
  "processing_status": "completed",
  "processed_at": "2025-12-19T10:30:45.123456",
  "ai_results": {
    "model_version": "DA_YOLO11X",
    "confidence": 0.20,
    "total_products": 45,
    "unique_products": 12,
    "product_breakdown": {
      "sunsilk_black_small": 8,
      "dove_hfr_large": 6,
      "horlicks_std": 12
    },
    "compliance_score": 87.5,
    "product_accuracy": [
      {
        "product": "Sunsilk Black Shine Small",
        "detected": 8,
        "expected": 10,
        "accuracy": 80.0
      }
    ],
    "summary": "Detected 45 products with 87.5% compliance"
  }
}
```

### 4.2 Queue Configuration

```python
# Environment Variables
AWS_ENDPOINT_URL = "http://localhost:4566"  # LocalStack for dev
AWS_DEFAULT_REGION = "ap-southeast-1"
S3_BUCKET = "ubl-shop-audits"
SQS_IMAGE_QUEUE_URL = "http://localhost:4566/000000000000/image-processing"
SQS_RESULTS_QUEUE_URL = "http://localhost:4566/000000000000/ai-results"
```

### 4.3 Queue Processing Parameters

- **MaxNumberOfMessages**: 10 (batch processing)
- **WaitTimeSeconds**: 10 (long polling)
- **MessageAttributeNames**: ['All']

---

## 5. Configuration Files to Database

Currently, compliance calculations rely on YAML config files in `config/` directory. These need to be migrated to database tables.

### 5.1 Config File Overview

| Config File | Purpose | Size | Priority |
|------------|---------|------|----------|
| `config.yaml` | Model paths, thresholds | Small | High |
| `qpds_standards.yaml` | Fixed shelf standards | Large | High |
| `sos_shelving_norm.yaml` | Share of shelf standards | Large | High |
| `sachet_standards.yaml` | Sachet display standards | Medium | High |
| `posm_standards.yaml` | POSM standards | Large | Medium |

### 5.2 Configuration Data Structure

#### 5.2.1 Main Config (`config.yaml`)

**Model Paths**:
```yaml
models:
  exclusivity: "models/EXCLUSIVITY.pt"
  ubl: "models/DA_YOLO11X.pt"
  qpds: "models/QPDS.pt"
  shelftalker: "models/Shelftalker.pt"
  sachet: "models/SACHET_YOLO11X.pt"
  posm: "models/POSM_YOLO11X.pt"
```

**Analysis Thresholds**:
```yaml
share_of_shelf:
  confidence: 0.20

fixed_shelf:
  shelftalker_conf: 0.30
  ubl_conf: 0.10
  exclusivity_conf: 0.60
  expand_margin: 0.05
  min_roi_area_ratio: 0.15
  min_shelftalker_completeness: 0.75

sachet:
  confidence: 0.30

posm:
  confidence: 0.30
```

#### 5.2.2 QPDS Standards (`qpds_standards.yaml`)

**Shelf Type Configuration**:
```yaml
shelf_types:
  "Hair Care Premium QPDS":
    min_shelftalkers: 4
    products:
      - product: "Dove Deep Repair Treatment Hair Mask 300ml"
        quantity: 2
        order: 1
      - product: "Tresemme Keratin Smooth Hair Mask 300ml"
        quantity: 2
        order: 2
```

**Total Shelf Types**: 13
**Total Products across all shelves**: 100+
**Product Mappings**: 80+ (AI class name → Standard product name)

**Shelftalker Mappings**:
```yaml
shelftalker_to_shelf_mapping:
  "Hair Care Premium QPDS": "da_hair_care_st_"
  "Winter Lotion QPDS": "da_lotion_st_"
```

**Expected Shelftalker Counts**:
```yaml
expected_shelftalkers:
  "Hair Care Premium QPDS": 4
  "Nutrition Store QPDS Double Shelf (2:1)": 5
```

#### 5.2.3 SOS Standards (`sos_shelving_norm.yaml`)

**Products with Planned Quantities**:
```yaml
products:
  - product: "Glow & Lovely Multivitamin Cream"
    quantity: 8
  - product: "Pond's Bright Beauty Cream"
    quantity: 8
```

**Total Products**: 92
**Product Mappings**: 100+ (AI class name → Standard product name)

#### 5.2.4 Sachet Standards (`sachet_standards.yaml`)

**Products**:
```yaml
products:
  - product: "Clear Anti Dandruff Sachet"
    quantity: 5
```

**Sachet Hangers**:
```yaml
sachet_hangers:
  - hanger: "Clear Sachet Hanger"
    quantity: 2
```

**Sachet to Hanger Mappings**:
```yaml
sachet_to_hanger:
  "clear_cac": "clear_sachet_hanger"
  "dove_cond_int_rpr": "dove_sachet_hanger"
```

**Total Products**: 51
**Total Hangers**: 10
**Mappings**: 40+

#### 5.2.5 POSM Standards (`posm_standards.yaml`)

**Items**:
```yaml
items:
  - item: "Clear Men Hamza Bunting"
    quantity: 1
  - item: "Lux Shop Banner"
    quantity: 1
```

**Total Items**: 116
**Item Mappings**: 150+ (AI class name → Standard item name)

---

## 6. Database Schema Recommendations

### 6.1 Core Tables

#### Table: `visits` (Audit Sessions)
```sql
CREATE TABLE visits (
    visit_id VARCHAR(50) PRIMARY KEY,
    shop_id VARCHAR(50) NOT NULL,
    merchandiser_id VARCHAR(50),
    visit_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'in_progress',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INDEX idx_visits_shop (shop_id);
INDEX idx_visits_date (visit_date);
```

#### Table: `image_uploads`
```sql
CREATE TABLE image_uploads (
    upload_id UUID PRIMARY KEY,
    visit_id VARCHAR(50) NOT NULL,
    shop_id VARCHAR(50) NOT NULL,
    image_type VARCHAR(20) NOT NULL,
    shelf_type VARCHAR(100),  -- NULL for non-fixed_shelf
    s3_key VARCHAR(500) NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_status VARCHAR(20) DEFAULT 'pending',
    processed_at TIMESTAMP,

    FOREIGN KEY (visit_id) REFERENCES visits(visit_id)
);

INDEX idx_uploads_visit (visit_id);
INDEX idx_uploads_status (processing_status);
INDEX idx_uploads_type (image_type);
```

#### Table: `ai_results`
```sql
CREATE TABLE ai_results (
    result_id SERIAL PRIMARY KEY,
    upload_id UUID NOT NULL,
    visit_id VARCHAR(50) NOT NULL,
    image_type VARCHAR(20) NOT NULL,
    model_version VARCHAR(50),
    confidence_threshold DECIMAL(4,2),
    total_detections INT,
    unique_detections INT,
    compliance_score DECIMAL(5,2),
    result_json JSONB,  -- Full AI result
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (upload_id) REFERENCES image_uploads(upload_id),
    FOREIGN KEY (visit_id) REFERENCES visits(visit_id)
);

INDEX idx_results_upload (upload_id);
INDEX idx_results_visit (visit_id);
INDEX idx_results_compliance (compliance_score);
```

#### Table: `detected_products`
```sql
CREATE TABLE detected_products (
    detection_id SERIAL PRIMARY KEY,
    result_id INT NOT NULL,
    upload_id UUID NOT NULL,
    product_class VARCHAR(100),  -- AI detection class
    product_name VARCHAR(200),   -- Mapped standard name
    quantity INT,
    confidence DECIMAL(4,2),

    FOREIGN KEY (result_id) REFERENCES ai_results(result_id),
    FOREIGN KEY (upload_id) REFERENCES image_uploads(upload_id)
);

INDEX idx_detections_result (result_id);
INDEX idx_detections_product (product_name);
```

### 6.2 Configuration Tables

#### Table: `model_configs`
```sql
CREATE TABLE model_configs (
    config_id SERIAL PRIMARY KEY,
    model_type VARCHAR(50) NOT NULL,  -- 'share_of_shelf', 'fixed_shelf', etc.
    model_name VARCHAR(100),
    model_path VARCHAR(500),
    confidence_threshold DECIMAL(4,2),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INDEX idx_model_type (model_type);
```

#### Table: `shelf_types`
```sql
CREATE TABLE shelf_types (
    shelf_type_id SERIAL PRIMARY KEY,
    shelf_type_name VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(50),
    min_shelftalkers INT DEFAULT 4,
    shelftalker_prefix VARCHAR(50),  -- e.g., "da_hair_care_st_"
    expected_shelftalkers INT DEFAULT 4,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Table: `shelf_products`
```sql
CREATE TABLE shelf_products (
    shelf_product_id SERIAL PRIMARY KEY,
    shelf_type_id INT NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    expected_quantity INT NOT NULL,
    display_order INT,

    FOREIGN KEY (shelf_type_id) REFERENCES shelf_types(shelf_type_id)
);

INDEX idx_shelf_products_type (shelf_type_id);
```

#### Table: `product_mappings`
```sql
CREATE TABLE product_mappings (
    mapping_id SERIAL PRIMARY KEY,
    analysis_type VARCHAR(20) NOT NULL,  -- 'qpds', 'sos', 'sachet', 'posm'
    ai_class_name VARCHAR(100) NOT NULL,
    standard_product_name VARCHAR(200) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,

    UNIQUE(analysis_type, ai_class_name)
);

INDEX idx_mappings_analysis (analysis_type);
INDEX idx_mappings_class (ai_class_name);
```

#### Table: `sos_standards`
```sql
CREATE TABLE sos_standards (
    standard_id SERIAL PRIMARY KEY,
    product_name VARCHAR(200) UNIQUE NOT NULL,
    expected_quantity INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);
```

#### Table: `sachet_standards`
```sql
CREATE TABLE sachet_standards (
    standard_id SERIAL PRIMARY KEY,
    product_name VARCHAR(200) UNIQUE NOT NULL,
    expected_quantity INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);
```

#### Table: `sachet_hangers`
```sql
CREATE TABLE sachet_hangers (
    hanger_id SERIAL PRIMARY KEY,
    hanger_name VARCHAR(100) UNIQUE NOT NULL,
    expected_quantity INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);
```

#### Table: `sachet_to_hanger_mappings`
```sql
CREATE TABLE sachet_to_hanger_mappings (
    mapping_id SERIAL PRIMARY KEY,
    sachet_class VARCHAR(100) NOT NULL,
    hanger_class VARCHAR(100) NOT NULL,

    UNIQUE(sachet_class)
);
```

#### Table: `posm_standards`
```sql
CREATE TABLE posm_standards (
    standard_id SERIAL PRIMARY KEY,
    item_name VARCHAR(200) UNIQUE NOT NULL,
    expected_quantity INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);
```

### 6.3 Additional Tables

#### Table: `shops`
```sql
CREATE TABLE shops (
    shop_id VARCHAR(50) PRIMARY KEY,
    shop_name VARCHAR(200),
    address TEXT,
    region VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Table: `merchandisers`
```sql
CREATE TABLE merchandisers (
    merchandiser_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200),
    email VARCHAR(200),
    phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. API Integration Points

### 7.1 Required Database APIs

The AI Server and Backend will need to call database APIs instead of reading YAML files. Here are the required endpoints:

#### 7.1.1 Model Configuration APIs

**GET** `/api/config/models/{model_type}`
- Returns: Model path, confidence thresholds
- Used by: AI Server (on startup and before processing)

Example Response:
```json
{
  "model_type": "share_of_shelf",
  "model_path": "models/DA_YOLO11X.pt",
  "confidence": 0.20
}
```

#### 7.1.2 Shelf Type APIs

**GET** `/api/config/shelf-types/{shelf_type_name}`
- Returns: Shelf configuration, expected products, quantities
- Used by: AI Server (during fixed_shelf processing)

Example Response:
```json
{
  "shelf_type_name": "Hair Care Premium QPDS",
  "category": "Hair Care",
  "min_shelftalkers": 4,
  "shelftalker_prefix": "da_hair_care_st_",
  "expected_shelftalkers": 4,
  "products": [
    {
      "product_name": "Dove Deep Repair Treatment Hair Mask 300ml",
      "expected_quantity": 2,
      "display_order": 1
    }
  ]
}
```

**GET** `/api/config/shelf-types`
- Returns: List of all shelf types
- Used by: Frontend, Validation

#### 7.1.3 Product Mapping APIs

**GET** `/api/config/product-mappings/{analysis_type}`
- Returns: All mappings for the analysis type
- Used by: AI Server (during result processing)

Example Request: `/api/config/product-mappings/qpds`

Example Response:
```json
{
  "analysis_type": "qpds",
  "mappings": {
    "horlicks_std": "Standard Horlicks 500G Jar",
    "dove_cond": "Dove Conditioner Intense Repair 170ml"
  }
}
```

**POST** `/api/config/product-mappings/lookup`
- Body: `{"analysis_type": "sos", "ai_class_name": "sunsilk_black_small"}`
- Returns: Mapped product name
- Used by: AI Server (for individual lookups)

#### 7.1.4 Standards APIs

**GET** `/api/config/standards/sos`
- Returns: All SOS standards
- Used by: AI Server (compliance calculation)

**GET** `/api/config/standards/sachet`
- Returns: All sachet standards including hangers
- Used by: AI Server (sachet compliance)

**GET** `/api/config/standards/posm`
- Returns: All POSM standards
- Used by: AI Server (POSM compliance)

#### 7.1.5 Result Storage APIs

**POST** `/api/results`
- Body: AI result JSON
- Stores: Result in database (replacing S3 JSON storage)
- Used by: Backend (when consuming ai-results queue)

Example Body:
```json
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440000",
  "visit_id": "aud_123456",
  "shop_id": "shop_789",
  "image_type": "share_of_shelf",
  "ai_results": { ... }
}
```

**GET** `/api/visits/{visit_id}/results`
- Returns: All AI results for a visit
- Used by: Frontend, Reporting

**GET** `/api/uploads/{upload_id}/result`
- Returns: Specific result for an upload
- Used by: Frontend, Detail views

---

## 8. Migration Strategy

### Phase 1: Database Setup (Week 1-2)
1. Create database schema
2. Migrate all YAML configs to database tables
3. Verify data integrity
4. Create database APIs

### Phase 2: Dual Mode Operation (Week 3-4)
1. Update AI Server to check both YAML and Database
2. Log discrepancies
3. Fix any data issues
4. Performance testing

### Phase 3: Database-Only Mode (Week 5)
1. Switch AI Server to database-only
2. Remove YAML file reads
3. Monitor performance
4. Backup and archive YAML files

### Phase 4: Optimization (Week 6+)
1. Add caching layer for frequently accessed configs
2. Optimize database queries
3. Add database replication if needed

---

## 9. Key Considerations

### 9.1 Performance
- **Cache**: Implement Redis/Memcached for config data
- **Connection Pool**: Use connection pooling for database
- **Batch Reads**: Load all standards on AI Server startup

### 9.2 Data Consistency
- **Versioning**: Track config changes with version numbers
- **Audit Log**: Log all config modifications
- **Rollback**: Ability to revert to previous configs

### 9.3 Configuration Updates
- **Hot Reload**: Allow config updates without restarting AI Server
- **Validation**: Validate all config changes before applying
- **Testing**: Test new configs in staging before production

### 9.4 Backward Compatibility
- **API Versioning**: Version all database APIs
- **Migration Scripts**: Provide scripts to migrate existing S3 results to database

---

## 10. Contact & Support

For questions about:
- **Data Flow**: Review sections 1-2
- **Metadata**: Review section 3
- **Queue System**: Review section 4
- **Database Schema**: Review section 6
- **APIs**: Review section 7

---

## Appendix A: Example Data Flow with Database

```
1. CLIENT uploads image
   └── S3: raw/aud_123/share_of_shelf/uuid.jpg
       Metadata: {visit_id, shop_id, image_type}

2. S3 Event → SQS image-processing

3. AI SERVER polls queue
   ├── Read message from SQS
   ├── Extract: visit_id, shop_id, image_type, s3_key
   ├── DATABASE API CALL: GET /api/config/models/share_of_shelf
   │   └── Returns: confidence threshold
   ├── Download image from S3
   ├── Run YOLO inference
   ├── DATABASE API CALL: GET /api/config/product-mappings/sos
   │   └── Returns: AI class → Product name mappings
   ├── DATABASE API CALL: GET /api/config/standards/sos
   │   └── Returns: Expected quantities
   ├── Calculate compliance score
   └── Send result to SQS ai-results

4. BACKEND polls ai-results queue
   ├── Read message
   ├── DATABASE API CALL: POST /api/results
   │   └── Stores full result in ai_results table
   │   └── Stores detected products in detected_products table
   └── Delete message from queue

5. FRONTEND/REPORTING
   └── DATABASE API CALL: GET /api/visits/{visit_id}/results
       └── Returns: All results for the visit
```

---

## Appendix B: Config File Sizes

| File | Lines | Products/Items | Mappings |
|------|-------|---------------|----------|
| config.yaml | 47 | N/A | N/A |
| qpds_standards.yaml | 375 | 100+ | 80+ |
| sos_shelving_norm.yaml | 335 | 92 | 100+ |
| sachet_standards.yaml | 226 | 51 | 40+ |
| posm_standards.yaml | 426 | 116 | 150+ |

**Total**: ~1,400 lines of YAML configuration to migrate

---

## Appendix C: Queue Message Examples

### Image Processing Queue Message
```json
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
          "key": "raw/aud_123456/fixed_shelf/550e8400.jpg"
        }
      }
    }
  ]
}
```

### AI Results Queue Message (Share of Shelf)
```json
{
  "upload_id": "550e8400-e29b-41d4-a716-446655440000",
  "visit_id": "aud_123456",
  "shop_id": "shop_789",
  "image_type": "share_of_shelf",
  "s3_key": "raw/aud_123456/share_of_shelf/550e8400.jpg",
  "result_s3_key": "processed/aud_123456/share_of_shelf/550e8400_result.json",
  "processing_status": "completed",
  "processed_at": "2025-12-19T10:30:45.123456",
  "ai_results": {
    "model_version": "DA_YOLO11X",
    "confidence": 0.20,
    "total_products": 45,
    "unique_products": 12,
    "product_breakdown": {
      "sunsilk_black_small": 8,
      "dove_hfr_large": 6,
      "clear_csm_small": 5,
      "horlicks_std": 12,
      "pepsodent_germicheck": 6,
      "lux_bar_flawless": 8
    },
    "compliance_score": 87.5,
    "product_accuracy": [
      {
        "product": "Sunsilk Black Shine Small",
        "detected": 8,
        "expected": 10,
        "accuracy": 80.0
      },
      {
        "product": "Dove Hair Fall Rescue Large",
        "detected": 6,
        "expected": 5,
        "accuracy": 120.0
      },
      {
        "product": "Horlicks Standard 500g",
        "detected": 12,
        "expected": 12,
        "accuracy": 100.0
      }
    ],
    "summary": "Detected 45 products with 87.5% compliance"
  }
}
```

### AI Results Queue Message (Fixed Shelf)
```json
{
  "upload_id": "660e8400-e29b-41d4-a716-446655440001",
  "visit_id": "aud_123456",
  "shop_id": "shop_789",
  "image_type": "fixed_shelf",
  "s3_key": "raw/aud_123456/fixed_shelf/660e8400.jpg",
  "processing_status": "completed",
  "processed_at": "2025-12-19T10:32:15.789012",
  "ai_results": {
    "model_version": "QPDS + Shelftalker + Exclusivity",
    "shelf_type": "Hair Care Premium QPDS",
    "no_of_shelftalker": 4,
    "shelftalkers_detected": [
      {
        "position": "shelftalker_0",
        "class_name": "da_hair_care_st_top",
        "confidence": 0.95
      },
      {
        "position": "shelftalker_1",
        "class_name": "da_hair_care_st_bottom",
        "confidence": 0.92
      },
      {
        "position": "shelftalker_2",
        "class_name": "da_hair_care_st_left",
        "confidence": 0.88
      },
      {
        "position": "shelftalker_3",
        "class_name": "da_hair_care_st_right",
        "confidence": 0.91
      }
    ],
    "total_products": 8,
    "product_breakdown": {
      "dove_mask_25": 2,
      "tresemme_mask_25": 2,
      "tresemme_serum_25": 2,
      "sunsilk_serum_25": 2
    },
    "selected_category": "all",
    "size_summary": {},
    "method": "roi (High quality: 4/4 shelftalkers detected)",
    "exclusivity_status": "yes",
    "non_ubl_count": 0,
    "non_ubl_products": {},
    "variant_compliance": 100.0,
    "product_accuracy": [
      {
        "product": "Dove Deep Repair Treatment Hair Mask 300ml",
        "detected": 2,
        "expected": 2,
        "accuracy": 100.0
      },
      {
        "product": "Tresemme Keratin Smooth Hair Mask 300ml",
        "detected": 2,
        "expected": 2,
        "accuracy": 100.0
      },
      {
        "product": "Tresemme Keratin Smooth Anti-Frizz Hair Serum 100ml",
        "detected": 2,
        "expected": 2,
        "accuracy": 100.0
      },
      {
        "product": "Sunsilk Super Shine Hair Serum 100ml",
        "detected": 2,
        "expected": 2,
        "accuracy": 100.0
      }
    ],
    "planogram_adherence": true,
    "shelftalker_adherence": true,
    "summary": "Fixed Shelf: 8 products, 100.0% compliance, Planogram: Pass, Shelftalker: Pass, Exclusivity: yes"
  }
}
```

---

**End of Document**
