"""
UBL Backend API with Presigned URLs and SQS Results Consumer

Features:
- FastAPI endpoints for generating presigned URLs
- Full metadata support (shelf_type, channel, category)
- Background SQS consumer for AI results
- S3 storage for results
- REST API for querying results

Architecture:
- Client requests presigned URLs from API
- Client uploads images to S3 using presigned URLs
- S3 triggers event notification to image-processing queue
- AI server processes images and sends results to ai-results queue
- Backend consumes results and stores them in S3 as JSON files
- API endpoints provide access to results
"""

import os
import json
import uuid
import asyncio
import traceback
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
from botocore.client import Config

# ============================================================================
# Configuration
# ============================================================================

AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-southeast-1")
S3_BUCKET = os.getenv("S3_BUCKET", "ubl-shop-audits")
SQS_AI_RESULTS_QUEUE_URL = os.getenv("SQS_AI_RESULTS_QUEUE_URL")
RESULTS_PREFIX = "results/"

# In-memory storage (for tracking uploads)
image_uploads = {}
audit_results = {}

# AWS Clients
s3_client = boto3.client(
    's3',
    endpoint_url=AWS_ENDPOINT_URL,
    region_name=AWS_REGION,
    aws_access_key_id='test',
    aws_secret_access_key='test',
    config=Config(signature_version='s3v4')
)

sqs_client = boto3.client(
    'sqs',
    endpoint_url=AWS_ENDPOINT_URL,
    region_name=AWS_REGION,
    aws_access_key_id='test',
    aws_secret_access_key='test'
)


# ============================================================================
# Background SQS Consumer
# ============================================================================

async def consume_ai_results():
    """Background task to consume AI processing results from SQS"""
    print("="*60)
    print("Starting AI Results Consumer")
    print("="*60)
    print(f"Queue: {SQS_AI_RESULTS_QUEUE_URL}")
    print("="*60)

    processed_count = 0

    while True:
        try:
            response = sqs_client.receive_message(
                QueueUrl=SQS_AI_RESULTS_QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=10,
                MessageAttributeNames=['All']
            )

            messages = response.get('Messages', [])

            if messages:
                print(f"\n📥 Received {len(messages)} result(s)")

            for message in messages:
                try:
                    result = json.loads(message['Body'])

                    # Handle aggregated visit-level results from AI server
                    if 'ai_summary' in result:
                        # This is an aggregated result for entire visit
                        ai_summary = result['ai_summary']
                        visit_id = ai_summary['header']['visit_id']
                        tasks = ai_summary['header'].get('task', 'UNKNOWN')

                        print(f"   Processing visit: {visit_id} (tasks: {tasks})")

                        # Store aggregated result to S3
                        s3_key = f"{RESULTS_PREFIX}{visit_id}/ai_summary.json"
                        result['stored_at'] = datetime.utcnow().isoformat()

                        s3_client.put_object(
                            Bucket=S3_BUCKET,
                            Key=s3_key,
                            Body=json.dumps(result, indent=2),
                            ContentType='application/json',
                            Metadata={
                                'visit-id': visit_id,
                                'tasks': tasks
                            }
                        )

                        print(f"   ✓ Stored: {s3_key}")

                        # Update in-memory tracking
                        audit_results[visit_id] = ai_summary['results']

                        processed_count += 1
                        print(f"   ✓ Total processed: {processed_count} visits")

                    else:
                        # Legacy per-image format (not used with current AI server)
                        upload_id = result.get('upload_id', 'unknown')
                        visit_id = result.get('visit_id', 'unknown')
                        image_type = result.get('image_type', 'unknown')

                        print(f"   Processing: {image_type} (visit: {visit_id})")

                        # Store result to S3
                        s3_key = f"{RESULTS_PREFIX}{visit_id}/{image_type}/{upload_id}.json"
                        result['stored_at'] = datetime.utcnow().isoformat()

                        s3_client.put_object(
                            Bucket=S3_BUCKET,
                            Key=s3_key,
                            Body=json.dumps(result, indent=2),
                            ContentType='application/json',
                            Metadata={
                                'visit-id': visit_id,
                                'image-type': image_type,
                                'upload-id': upload_id
                            }
                        )

                        print(f"   ✓ Stored: {s3_key}")
                        processed_count += 1

                    # Delete message from queue
                    sqs_client.delete_message(
                        QueueUrl=SQS_AI_RESULTS_QUEUE_URL,
                        ReceiptHandle=message['ReceiptHandle']
                    )

                except Exception as e:
                    print(f"   Error processing message: {e}")
                    traceback.print_exc()

            await asyncio.sleep(2)

        except Exception as e:
            print(f"Error in consumer loop: {e}")
            traceback.print_exc()
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("\n🚀 Starting Backend API...")
    task = asyncio.create_task(consume_ai_results())
    yield
    print("\n⚠ Shutting down...")
    task.cancel()


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="UBL Backend API",
    description="Shop Audit Backend with Presigned URLs",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================

class ImageMetadata(BaseModel):
    """Metadata for a specific image type"""
    slab: Optional[str] = None  # For fixed_shelf - QPDS shelf name
    channel: Optional[str] = None  # For fixed_shelf - PBS, GBS, NPS
    sub_category: Optional[str] = None  # For share_of_shelf - hair_care, skin_care, etc.


class UploadURLRequest(BaseModel):
    """Request for presigned upload URLs"""
    visit_id: str
    shop_id: str
    merchandiser_id: str
    expected_images_count: int  # Total images for this visit (required for AI aggregation)
    image_types: Optional[List[str]] = None
    metadata: Optional[Dict[str, ImageMetadata]] = None


class PresignedURLResponse(BaseModel):
    """Response with presigned URL details"""
    upload_id: str
    presigned_url: Dict
    s3_key: str


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "service": "UBL Backend API",
        "status": "running",
        "endpoints": {
            "generate_urls": "POST /api/audits/{visit_id}/upload-urls",
            "get_images": "GET /api/audits/{visit_id}/images",
            "get_results": "GET /api/audits/{visit_id}/results",
            "health": "GET /health"
        }
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.post("/api/audits/{visit_id}/upload-urls")
def generate_upload_urls(visit_id: str, request: UploadURLRequest) -> Dict[str, PresignedURLResponse]:
    """
    Generate presigned URLs for image uploads with full metadata support
    """
    # Default image types if not specified
    image_types = request.image_types or [
        "share_of_shelf",
        "fixed_shelf",
        "sachet",
        "posm"
    ]

    urls = {}

    print(f"\n{'='*60}")
    print(f"📤 GENERATING PRESIGNED URLS")
    print(f"{'='*60}")
    print(f"Visit ID: {visit_id}")
    print(f"Shop ID: {request.shop_id}")
    print(f"Merchandiser ID: {request.merchandiser_id}")
    print(f"Expected Images Count: {request.expected_images_count}")
    print(f"Image Types: {', '.join(image_types)}")
    print(f"{'='*60}\n")

    for image_type in image_types:
        # Generate unique identifiers
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_uuid = str(uuid.uuid4())[:8]
        upload_id = f"upl_{uuid.uuid4().hex[:8]}"
        s3_key = f"raw/{visit_id}/{image_type}/{timestamp}_{file_uuid}.jpg"

        # Build metadata fields for S3
        metadata_fields = {
            "x-amz-meta-upload-id": upload_id,
            "x-amz-meta-visit-id": visit_id,
            "x-amz-meta-shop-id": request.shop_id,
            "x-amz-meta-merchandiser-id": request.merchandiser_id,
            "x-amz-meta-image-type": image_type,
            "x-amz-meta-expected-images-count": str(request.expected_images_count)
        }

        # Add image-specific metadata if provided
        if request.metadata and image_type in request.metadata:
            img_metadata = request.metadata[image_type]
            if img_metadata.slab:
                metadata_fields["x-amz-meta-slab"] = img_metadata.slab
            if img_metadata.channel:
                metadata_fields["x-amz-meta-channel"] = img_metadata.channel
            if img_metadata.sub_category:
                metadata_fields["x-amz-meta-sub-category"] = img_metadata.sub_category

        # Track upload
        image_uploads[upload_id] = {
            "id": upload_id,
            "visit_id": visit_id,
            "shop_id": request.shop_id,
            "merchandiser_id": request.merchandiser_id,
            "image_type": image_type,
            "s3_key": s3_key,
            "status": "pending_upload",
            "metadata": dict(request.metadata.get(image_type)) if request.metadata and image_type in request.metadata else None,
            "created_at": datetime.utcnow().isoformat()
        }

        # Generate presigned POST URL
        presigned_post = s3_client.generate_presigned_post(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Fields=metadata_fields,
            Conditions=[
                {"x-amz-meta-upload-id": upload_id},
                ["content-length-range", 100, 15728640]  # 100 bytes to 15MB
            ],
            ExpiresIn=3600  # 1 hour
        )

        # Fix LocalStack URL for external access
        if 'localstack' in presigned_post['url']:
            presigned_post['url'] = presigned_post['url'].replace(
                'http://localstack:4566',
                'http://localhost:4566'
            )

        urls[image_type] = {
            "upload_id": upload_id,
            "presigned_url": presigned_post,
            "s3_key": s3_key
        }

        print(f"✓ {image_type}: {upload_id}")
        if request.metadata and image_type in request.metadata:
            img_meta = request.metadata[image_type]
            if img_meta.slab:
                print(f"  └─ Slab: {img_meta.slab}")
            if img_meta.channel:
                print(f"  └─ Channel: {img_meta.channel}")
            if img_meta.sub_category:
                print(f"  └─ Sub-Category: {img_meta.sub_category}")

    print()
    return urls


@app.get("/api/audits/{visit_id}/images")
def get_audit_images(visit_id: str):
    """Get all uploaded images for a visit/audit"""
    audit_uploads = {
        uid: data for uid, data in image_uploads.items()
        if data['visit_id'] == visit_id
    }

    if not audit_uploads:
        raise HTTPException(status_code=404, detail="No images found for this visit")

    return {
        "visit_id": visit_id,
        "total_images": len(audit_uploads),
        "images": audit_uploads
    }


@app.get("/api/audits/{visit_id}/results")
def get_audit_results(visit_id: str):
    """Get AI processing results for a visit/audit"""
    if visit_id not in audit_results:
        raise HTTPException(status_code=404, detail="No results found for this visit")

    return {
        "visit_id": visit_id,
        "results": audit_results[visit_id]
    }


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    print("\n" + "="*60)
    print("UBL BACKEND API")
    print("="*60)
    print(f"Bucket: {S3_BUCKET}")
    print(f"Results Queue: {SQS_AI_RESULTS_QUEUE_URL}")
    print("="*60 + "\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )


