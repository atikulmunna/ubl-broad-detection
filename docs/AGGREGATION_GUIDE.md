# Visit-Level AI Result Aggregation

## Overview

The AI server now aggregates all image results for a visit and sends **one combined message** per visit to the backend, instead of individual messages per image.

## How It Works

### 1. Image Upload with Metadata

When uploading images to S3, the backend **must include** this metadata:

```python
s3_client.put_object(
    Bucket='u-lens-production-audit-images',
    Key='raw/visit_123/fixed_shelf/image1.jpg',
    Body=image_data,
    Metadata={
        'upload-id': 'upl_abc123',
        'visit-id': 'visit_123',
        'shop-id': 'shop_456',
        'image-type': 'fixed_shelf',  # fixed_shelf, share_of_shelf, sachet, posm
        'shelf-type': 'WINTER_LOTION_QPDS_OPTION_2',  # For fixed_shelf only
        'channel': 'PBS',  # For fixed_shelf only
        'slab': 'Slab_A',  # Optional
        'expected-images-count': '5'  # ⭐ REQUIRED - Total images for this visit
    }
)
```

**Critical:** `expected-images-count` tells the AI server when the visit is complete.

### 2. AI Server Processing

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Server Flow                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Image 1 arrives → Process → Store in aggregator            │
│  Image 2 arrives → Process → Store in aggregator            │
│  Image 3 arrives → Process → Store in aggregator            │
│  Image 4 arrives → Process → Store in aggregator            │
│  Image 5 arrives → Process → Store in aggregator            │
│                                                              │
│  ✓ All 5 images processed!                                  │
│  → Build aggregated result                                  │
│  → Send ONE message to SQS                                  │
│  → Clean up memory                                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3. Aggregated SQS Message Format

The backend receives **one message** per visit:

```json
{
  "visit_id": "visit_123",
  "outlet_id": "shop_456",
  "shop_id": "shop_456",

  "pjp_mapping_id": null,
  "visitor_id": null,
  "execution_date": null,
  "execution_start_time": null,
  "execution_end_time": null,
  "is_executed": true,
  "is_execution_completed": true,
  "reason_for_no_execution": null,

  "is_visitor_challenged": false,
  "is_supervisor_challenged": false,
  "visitor_challenge_remarks": "",
  "supervisor_challenge_remarks": "",
  "is_location_error": false,

  "AI_Result": {
    "category_shelf_display": [
      {
        "upload_id": "upl_001",
        "s3_key": "raw/visit_123/fixed_shelf/img1.jpg",
        "processing_status": "completed",
        "processed_at": "2025-12-24T10:00:00.123456+00:00",
        "display_name": "WINTER LOTION QPDS",
        "outlet_type": "PBS",
        "slab": "Slab_A",
        "overall_compliance": "85.5%",
        "variant_compliance": "90.0%",
        "is_planogram_adherence": "Yes",
        "is_exclusivity": "Yes",
        "status": "passed",
        "challenge_remarks": "",
        "results": {
          "products": [
            {
              "sku_name": "LUX SHW BW BLK ORCHD 245ML",
              "planned_qty": 6,
              "visible_qty": 6,
              "accuracy": "100.0%"
            }
          ],
          "shelf_talker": "Yes",
          "shelf_talker_orientation": "Yes",
          "total_planned": 12,
          "total_visible": 12
        }
      },
      {
        "upload_id": "upl_002",
        "s3_key": "raw/visit_123/fixed_shelf/img2.jpg",
        "processing_status": "completed",
        "processed_at": "2025-12-24T10:01:00.123456+00:00",
        "display_name": "PREMIUM PORTFOLIO QPDS",
        "outlet_type": "PBS",
        "slab": "Slab_A",
        "overall_compliance": "75.0%",
        "variant_compliance": "80.0%",
        "is_planogram_adherence": "No",
        "is_exclusivity": "Yes",
        "status": "failed",
        "challenge_remarks": "",
        "results": {
          "products": [...],
          "shelf_talker": "No",
          "shelf_talker_orientation": "No",
          "total_planned": 10,
          "total_visible": 9
        }
      }
    ],

    "share_of_shelf": [
      {
        "upload_id": "upl_003",
        "s3_key": "raw/visit_123/share_of_shelf/img3.jpg",
        "processing_status": "completed",
        "processed_at": "2025-12-24T10:02:00.123456+00:00",
        "category_name": "Skin Care",
        "ubl_percentage": "100%",
        "competitor_percentage": "0%",
        "results": {
          "brands": [
            {
              "company_name": "Unilever Bangladesh Limited",
              "brand": "VASELINE",
              "min_qty": "N/A",
              "visible_qty": 4,
              "shelving_norm": "N/A"
            }
          ]
        }
      }
    ],

    "share_of_sachet": [
      {
        "upload_id": "upl_004",
        "s3_key": "raw/visit_123/sachet/img4.jpg",
        "processing_status": "completed",
        "processed_at": "2025-12-24T10:03:00.123456+00:00",
        "combined_sachet_hanger": "Yes",
        "brand_exclusive_hanger": "No",
        "results": {
          "sachets": [
            {
              "company_name": "Unilever Bangladesh Limited",
              "sachet_name": "DOVE SHAMPOO IRP 6ML",
              "visible_qty": 10,
              "orientation_adherence": "Yes",
              "slot_adherence": "N/A"
            }
          ]
        }
      }
    ],

    "share_of_posm": [
      {
        "upload_id": "upl_005",
        "s3_key": "raw/visit_123/posm/img5.jpg",
        "processing_status": "completed",
        "processed_at": "2025-12-24T10:04:00.123456+00:00",
        "ubl_posm_accuracy": "100%",
        "results": {
          "posm_items": [
            {
              "company": "Unilever Bangladesh Limited",
              "material_name": "DOVE CONDITIONER SACHET HANGER DEC'25",
              "input_qty": 1,
              "visible_qty": 1,
              "accuracy": "100%"
            }
          ]
        }
      }
    ]
  },

  "outlet_status_for_display": "Failed",
  "request_for_challenge": true,
  "challenged_by_supervisor": false,
  "changed_after_audit": false,
  "execution_done": true,
  "reason_for_error": null,

  "aggregated_at": "2025-12-24T10:05:00.123456+00:00",
  "total_images_processed": 5
}
```

## Image Type Mapping

The AI server automatically maps internal types to API names:

| Internal Type    | API Name (in AI_Result)     |
|------------------|-----------------------------|
| `fixed_shelf`    | `category_shelf_display`    |
| `share_of_shelf` | `share_of_shelf`            |
| `sachet`         | `share_of_sachet`           |
| `posm`           | `share_of_posm`             |

## Status Calculation

### Overall Status (`outlet_status_for_display`)

- **Passed**: All `category_shelf_display` results have `status: "passed"` (compliance >= 80%)
- **Failed**: At least one `category_shelf_display` result has `status: "failed"` (compliance < 80%)

### Request for Challenge (`request_for_challenge`)

- `true`: If overall status is "Failed"
- `false`: If overall status is "Passed"

## Backend Integration

### When Upload Starts

1. Count total images for the visit
2. Set `expected-images-count` metadata on **every** image upload
3. Upload images to S3 (triggers SQS notification to AI server)

### When Result Arrives

1. Receive **one** SQS message per visit (not per image!)
2. Parse the `AI_Result` object
3. Save to database
4. Update visit status

### Example Backend Code

```python
# Upload images for a visit
visit_id = "visit_123"
images = [
    {"type": "fixed_shelf", "shelf_type": "WINTER_LOTION_QPDS", "file": img1},
    {"type": "fixed_shelf", "shelf_type": "PREMIUM_PORTFOLIO_QPDS", "file": img2},
    {"type": "share_of_shelf", "file": img3},
    {"type": "sachet", "file": img4},
    {"type": "posm", "file": img5}
]

total_images = len(images)

for idx, img in enumerate(images):
    s3_client.put_object(
        Bucket='u-lens-production-audit-images',
        Key=f'raw/{visit_id}/{img["type"]}/image_{idx}.jpg',
        Body=img["file"],
        Metadata={
            'upload-id': f'upl_{uuid.uuid4().hex[:8]}',
            'visit-id': visit_id,
            'shop-id': 'shop_456',
            'image-type': img["type"],
            'expected-images-count': str(total_images),  # ⭐ Same for all images
            # ... other metadata
        }
    )

# Later, receive aggregated result
def process_sqs_message(message):
    result = json.loads(message['Body'])
    visit_id = result['visit_id']
    ai_result = result['AI_Result']

    # Process category_shelf_display results
    for shelf_result in ai_result.get('category_shelf_display', []):
        save_shelf_result(visit_id, shelf_result)

    # Process share_of_shelf results
    for sos_result in ai_result.get('share_of_shelf', []):
        save_sos_result(visit_id, sos_result)

    # ... and so on

    # Update overall visit status
    update_visit_status(
        visit_id=visit_id,
        status=result['outlet_status_for_display'],
        needs_challenge=result['request_for_challenge']
    )
```

## Important Notes

1. **All images must include `expected-images-count`** - Without this, the AI server won't know when to send the aggregated result

2. **Memory Safety** - The AI server cleans up memory after sending the aggregated result. No persistent storage is used.

3. **Restart Tolerance** - If the AI server restarts while processing a visit, those images will need to be re-uploaded. This is acceptable for your setup.

4. **Thread Safety** - The aggregator uses locks to handle concurrent image processing safely.

5. **Partial Results** - If some images fail to process, the AI server will still wait for `expected-images-count` to be reached. Make sure error handling is in place.

## Troubleshooting

### Visit never completes
- Check that all images have the same `visit-id`
- Verify `expected-images-count` matches actual uploaded images
- Check AI server logs for processing errors

### Wrong expected count
- Make sure you count all images before uploading
- Set the same `expected-images-count` on every image

### Missing image types in result
- Verify S3 metadata has correct `image-type`
- Check that image files are valid (not corrupted)
- Review AI server logs for processing errors
