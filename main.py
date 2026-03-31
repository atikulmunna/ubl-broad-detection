"""
UBL AI Server with SQS Integration

Integrated multi-stream YOLO inference engine with AWS SQS architecture.
Processes images from S3, runs AI models, and sends results back via SQS.

Features:
- Multiple concurrent CUDA streams for high GPU utilization
- YOLO model inference (DA, QPDS, Shelftalker, Sachet, POSM, Exclusivity)
- Compliance calculations (Fixed Shelf, Share of Shelf, Sachet, POSM)
- S3 image processing with metadata
- SQS message handling
"""

import os
import asyncio
import logging

import boto3
from dotenv import load_dotenv

from utils.logger import setup_cloudwatch_logging

# Configure CloudWatch-compatible JSON logging
setup_cloudwatch_logging()
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Import core modules
from core.model_manager import model_manager
from core.analyzers import (
    # Import feature flags for startup logging
    SIZE_VARIANT_AVAILABLE, QPDS_AVAILABLE, SOS_AVAILABLE,
    SACHET_AVAILABLE, POSM_AVAILABLE
)
from core.pipeline import process_image

# ============================================================================
# Configuration
# ============================================================================

# S3 Bucket Configuration
S3_BUCKET_PREFIX = "u-lens-production"

# AWS Configuration
USE_LOCALSTACK = os.getenv("USE_LOCALSTACK", "false").lower() == "true"
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-southeast-1")

# S3 Buckets (only those needed for AI service)
S3_BUCKET = os.getenv("S3_BUCKET", f"{S3_BUCKET_PREFIX}-audit-images")
S3_MODELS_BUCKET = os.getenv("S3_MODELS_BUCKET", f"{S3_BUCKET_PREFIX}-ai-models")
S3_RESULTS_BUCKET = os.getenv("S3_RESULTS_BUCKET", f"{S3_BUCKET_PREFIX}-ai-results")

# SQS Queues
SQS_IMAGE_QUEUE_URL = os.getenv("SQS_IMAGE_QUEUE_URL")
SQS_RESULTS_QUEUE_URL = os.getenv("SQS_RESULTS_QUEUE_URL")

# Load worker configuration from config.yaml (with environment variable override)
from config.loader import NUM_WORKERS
NUM_INFERENCE_WORKERS = int(os.getenv('NUM_INFERENCE_WORKERS', str(NUM_WORKERS)))
SQS_POLL_INTERVAL = float(os.getenv('SQS_POLL_INTERVAL', '0.1'))
SQS_EMPTY_WAIT = float(os.getenv('SQS_EMPTY_WAIT', '1.0'))


# AWS Clients - Production uses IAM Role, LocalStack uses test credentials
if USE_LOCALSTACK:
    logger.info("Running in LocalStack mode")
    s3_client = boto3.client(
        's3',
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION,
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )
    sqs_client = boto3.client(
        'sqs',
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION,
        aws_access_key_id='test',
        aws_secret_access_key='test'
    )
else:
    logger.info("Running in Production mode (using IAM Role)")
    s3_client = boto3.client('s3', region_name=AWS_REGION)
    sqs_client = boto3.client('sqs', region_name=AWS_REGION)


# ============================================================================
# Shared Model Manager (Memory Efficient)
# ============================================================================
# Model manager moved to core/model_manager.py
# Imported above: from core.model_manager import model_manager


# ============================================================================
# Detection Functions
# ============================================================================
# Detection utilities moved to core/detection.py
# Functions: calculate_iou, _get_expected_shelftalker_prefix, _detect_shelftalker_roi,
#            _detect_products_in_roi, _detect_products_full_image, _validate_roi_quality,
#            _check_exclusivity


# ============================================================================
# Analysis Functions
# ============================================================================
# Analyzers moved to core/analyzers.py
# Imported above: from core.analyzers import analyze_share_of_shelf, etc.


# ============================================================================
# Visit Result Aggregation
# ============================================================================
# TODO-REFACTOR: Remove import when backend ready
from utils.aggregator import VisitResultAggregator


# TODO-REFACTOR: Remove when backend ready
# Global visit aggregator
visit_aggregator = VisitResultAggregator()


# ============================================================================
# Image Processing Pipeline
# ============================================================================
# Pipeline moved to core/pipeline.py
# Imported above: from core.pipeline import process_image


# ============================================================================
# Main Event Loop
# ============================================================================

async def _process_and_delete(message, worker_id, worker_id_pool):
    """Process one image and delete SQS message on success. Fire-and-forget task."""
    try:
        await process_image(message, worker_id)
        # Delete on success (runs in default executor to avoid blocking)
        loop = asyncio.get_event_loop()
        receipt = message['ReceiptHandle']
        await loop.run_in_executor(None, lambda: sqs_client.delete_message(
            QueueUrl=SQS_IMAGE_QUEUE_URL,
            ReceiptHandle=receipt
        ))
    except Exception as e:
        logger.error(f"[Worker {worker_id}] Error processing message: {e}", exc_info=True)
    finally:
        worker_id_pool.put_nowait(worker_id)


async def main():
    """Main loop — continuous polling with fire-and-forget worker tasks"""
    logger.info("="*60)
    logger.info("UBL AI SERVER - THREADED PARALLEL PROCESSING")
    logger.info("="*60)
    logger.info(f"Device: {model_manager.device}")
    logger.info(f"Workers: {NUM_INFERENCE_WORKERS}")
    logger.info(f"Queue: {SQS_IMAGE_QUEUE_URL}")
    logger.info(f"Results: {SQS_RESULTS_QUEUE_URL}")
    logger.info(f"Bucket: {S3_BUCKET}")
    logger.info(f"Size Variant Detection: {'Enabled' if SIZE_VARIANT_AVAILABLE else 'Disabled'}")
    logger.info(f"QPDS Compliance: {'Enabled' if QPDS_AVAILABLE else 'Disabled'}")
    logger.info(f"SOS Compliance: {'Enabled' if SOS_AVAILABLE else 'Disabled'}")
    logger.info(f"Sachet Compliance: {'Enabled' if SACHET_AVAILABLE else 'Disabled'}")
    logger.info(f"POSM Compliance: {'Enabled' if POSM_AVAILABLE else 'Disabled'}")
    logger.info("="*60)
    logger.info("Waiting for images to process...")

    # Worker ID pool — acts as both semaphore and ID assigner
    worker_id_pool = asyncio.Queue()
    for i in range(NUM_INFERENCE_WORKERS):
        worker_id_pool.put_nowait(i)

    loop = asyncio.get_event_loop()

    while True:
        try:
            # Poll SQS in default executor (non-blocking long poll)
            response = await loop.run_in_executor(None, lambda: sqs_client.receive_message(
                QueueUrl=SQS_IMAGE_QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
                MessageAttributeNames=['All']
            ))

            messages = response.get('Messages', [])

            if messages:
                logger.info(f"Received {len(messages)} message(s)")

                for message in messages:
                    # Wait for available worker (natural backpressure)
                    worker_id = await worker_id_pool.get()
                    active = NUM_INFERENCE_WORKERS - worker_id_pool.qsize()
                    logger.info(f"Dispatching to Worker {worker_id} ({active}/{NUM_INFERENCE_WORKERS} active)")
                    asyncio.create_task(
                        _process_and_delete(message, worker_id, worker_id_pool)
                    )

                await asyncio.sleep(SQS_POLL_INTERVAL)
            else:
                await asyncio.sleep(SQS_EMPTY_WAIT)

        except KeyboardInterrupt:
            logger.info("Shutting down AI server...")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
