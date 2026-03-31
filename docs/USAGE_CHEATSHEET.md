# UBL AI System Usage Cheatsheet

## Quick Start

### 1. Start the System
```bash
cd simulation
sudo docker-compose up -d
```

### 2. Upload Images with Metadata
```bash
cd simulation/client
python upload_with_metadata.py
```

### 3. View Results
```bash
cd simulation/client
python view_results.py
```

---

## Upload Images

### Interactive Upload (Recommended)
```bash
cd simulation/client
python upload_with_metadata.py
```

**Available Image Types:**
1. `share_of_shelf` - Share of Shelf analysis
2. `fixed_shelf` - QPDS/Fixed Shelf (requires shelf_type)
3. `sachet` - Sachet compliance
4. `posm` - POSM compliance

**Available Shelf Types (for fixed_shelf):**
1. Hair Care Premium QPDS
2. Winter Lotion QPDS
3. Perfect Store - Hair (requires channel: PBS or GBS)
4. Perfect Store - Glow & Lovely (requires channel: PBS or GBS)
5. Perfect Store - Ponds (requires channel: PBS or GBS)
6. Lux Bodywash QPDS
7. Vim Liquid QPDS
8. Oral Care QPDS
9. Junior Clean Corner QPDS
10. Nutrition Store QPDS Single Shelf (1:1)
11. Nutrition Store QPDS Single Shelf (1:2)
12. Nutrition Store QPDS Double Shelf (2:1)
13. Nutrition Store QPDS Double Shelf (2:2)

**Channel Types (for Perfect Store shelves only):**
- PBS - Premium Beauty Store
- GBS - General Beauty Store

### Simple Upload (3 default images)
```bash
cd simulation/client
python upload_direct.py
```

---

## View Results

### Using Python Script (Recommended)
```bash
cd simulation/client
python view_results.py

# View specific audit
# Enter Visit ID when prompted: 345435

# View all results
# Press Enter when asked for Visit ID
```

### Using AWS CLI
```bash
# List all results
aws --endpoint-url=http://localhost:4566 s3 ls s3://ubl-shop-audits/results/ --recursive

# Download and view specific result
aws --endpoint-url=http://localhost:4566 s3 cp \
  s3://ubl-shop-audits/results/345435/fixed_shelf/upload_20251217_002407.json - \
  | python -m json.tool

# List raw images
aws --endpoint-url=http://localhost:4566 s3 ls s3://ubl-shop-audits/raw/ --recursive
```

---

## Monitor Processing

### Watch AI Server Logs
```bash
cd simulation
sudo docker-compose logs -f ai-server
```

**Expected Log Output:**
```
2025-12-23 18:30:15,456 - __main__ - INFO - ============================================================
2025-12-23 18:30:15,457 - __main__ - INFO - UBL AI SERVER - FULL FEATURE PARITY
2025-12-23 18:30:15,458 - __main__ - INFO - ============================================================
2025-12-23 18:30:15,459 - __main__ - INFO - Device: cuda:0
2025-12-23 18:30:15,460 - __main__ - INFO - Workers: 4
2025-12-23 18:30:15,461 - __main__ - INFO - Waiting for images to process...
2025-12-23 18:30:20,123 - __main__ - INFO - [Worker 1] Processing: raw/audit_123/fixed_shelf/upload_20251223.jpg
2025-12-23 18:30:20,456 - __main__ - INFO - [Worker 1] Upload: upload_20251223, Type: fixed_shelf, Audit: audit_123
2025-12-23 18:30:20,789 - __main__ - INFO - [Worker 1] Downloaded 2456789 bytes
2025-12-23 18:30:22,123 - __main__ - INFO - [Worker 1] Complete
```

### Watch Backend Logs
```bash
cd simulation
sudo docker-compose logs -f backend
```

### View Recent Logs
```bash
cd simulation

# Last 50 lines from AI server
sudo docker-compose logs ai-server | tail -50

# Last 20 lines from backend
sudo docker-compose logs backend | tail -20
```

---

## Understanding Results

### Fixed Shelf (QPDS) Result Structure
```json
{
  "model_version": "QPDS + Shelftalker + Exclusivity",
  "shelf_type": "Nutrition Store QPDS Single Shelf (1:2)",
  "no_of_shelftalker": 4,
  "shelftalkers_detected": [...],
  "total_products": 20,
  "product_breakdown": {
    "horlicks_std": 12,
    "horlicks_junior": 8
  },
  "size_summary": {...},
  "method": "roi (High quality: 4/4 shelftalkers detected)",
  "exclusivity_status": "yes",
  "variant_compliance": 100.0,
  "product_accuracy": [...],
  "planogram_adherence": true,
  "shelftalker_adherence": true,
  "summary": "Fixed Shelf: 20 products, 100.0% compliance..."
}
```

### Share of Shelf Result Structure
```json
{
  "model_version": "UBL + Exclusivity",
  "total_products": 0,
  "ubl_products": 0,
  "competitor_products": 0,
  "ubl_share_percentage": 0.0,
  "exclusivity_status": "yes",
  "summary": "Detected 0 products with 0.0% compliance"
}
```

### Sachet Result Structure
```json
{
  "model_version": "Sachet Detection",
  "total_sachets": 1,
  "sachet_breakdown": {...},
  "compliance_percentage": 0.0,
  "summary": "Detected 1 sachets with 0.0% compliance"
}
```

### POSM Result Structure
```json
{
  "model_version": "POSM Detection",
  "total_posm": 1,
  "posm_breakdown": {...},
  "compliance_percentage": 50.0,
  "summary": "Detected 1 POSM items with 50.0% compliance"
}
```

---

## System Management

### Start/Stop
```bash
cd simulation

# Start all services
sudo docker-compose up -d

# Stop all services
sudo docker-compose down

# Restart specific service
sudo docker-compose restart ai-server
```

### Rebuild After Code Changes
```bash
cd simulation

# Rebuild AI server
sudo docker-compose build ai-server
sudo docker-compose up -d ai-server

# Rebuild backend
sudo docker-compose build backend
sudo docker-compose up -d backend
```

### Check Status
```bash
cd simulation
sudo docker-compose ps
```

---

## Example Workflow

### Complete Analysis Flow
```bash
# 1. Start the system
cd /home/mkultra/Documents/UBL-Infrastructure/simulation
sudo docker-compose up -d

# 2. Upload a Perfect Store - Hair image with channel
cd client
python upload_with_metadata.py
# Enter: Visit ID: 12345
#        Shop ID: 67890
#        Type: 2 (fixed_shelf)
#        Shelf: 3 (Perfect Store - Hair)
#        Channel: 1 (PBS)
#        Path: ../examples/DA/perfect-store-hair.jpg

# 3. Monitor processing
cd ..
sudo docker-compose logs -f ai-server
# Wait for: "INFO - [Worker 1] Complete"

# 4. View results
cd client
python view_results.py
# Enter Visit ID: 12345

# 5. Check result in S3
aws --endpoint-url=http://localhost:4566 s3 ls \
  s3://ubl-shop-audits/results/12345/ --recursive
```

---

## Common Issues & Solutions

### AI Server Not Processing
```bash
# Check if containers are running
cd simulation
sudo docker-compose ps

# Restart AI server
sudo docker-compose restart ai-server

# Check logs for errors
sudo docker-compose logs ai-server | tail -100
```

### No Results Appearing
```bash
# Check backend is running
sudo docker-compose logs backend | tail -20

# Verify queues exist (should see processing messages)
sudo docker-compose logs ai-server | grep "Sent result"
sudo docker-compose logs backend | grep "Processing"
```

### Upload Fails
```bash
# Verify image path is correct
ls -la <your-image-path>

# Check S3 is accessible
aws --endpoint-url=http://localhost:4566 s3 ls
```

---

## Configuration

### Model Confidence Thresholds
Edit `config/config.yaml`:
```yaml
fixed_shelf:
  shelftalker_conf: 0.30    # Shelftalker detection
  ubl_conf: 0.10            # Product detection
  exclusivity_conf: 0.60    # Non-UBL products

share_of_shelf:
  confidence: 0.20          # Product detection

sachet:
  confidence: 0.30          # Sachet detection

posm:
  confidence: 0.30          # POSM detection
```

### Number of Workers
```bash
# Set in docker-compose.yml or environment
export NUM_INFERENCE_WORKERS=4
cd simulation
sudo docker-compose up -d
```

---

## Quick Commands Reference

```bash
# Start system
cd simulation && sudo docker-compose up -d

# Upload image
cd simulation/client && python upload_with_metadata.py

# View results
cd simulation/client && python view_results.py

# Check AI logs
cd simulation && sudo docker-compose logs -f ai-server

# List all results
aws --endpoint-url=http://localhost:4566 s3 ls s3://ubl-shop-audits/results/ --recursive

# Stop system
cd simulation && sudo docker-compose down
```
