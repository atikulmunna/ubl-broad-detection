"""
Pipeline Module

Contains image processing pipeline: routing and processing functions.
"""

import asyncio
import json
import logging
import os
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote_plus

# Import analyzers
from core.analyzers import (
    analyze_share_of_shelf, analyze_fixed_shelf,
    analyze_sachet, analyze_posm, analyze_sovm
)
from core.retail_experiment import analyze_retail_experiment
from config.loader import CONFIG, NUM_WORKERS

logger = logging.getLogger(__name__)

# Thread pool for true parallel image processing
NUM_INFERENCE_WORKERS = int(os.getenv('NUM_INFERENCE_WORKERS', str(NUM_WORKERS)))
_inference_pool = ThreadPoolExecutor(max_workers=NUM_INFERENCE_WORKERS,
                                     thread_name_prefix="inference")

class _ThroughputTracker:
    """Rolling window + lifetime throughput stats with pass/fail tracking"""
    def __init__(self, window_sec=60):
        self._window = window_sec
        self._lock = threading.Lock()
        self._start = None
        self._image_ts = deque()
        self._visit_ts = deque()
        self._total_images = 0
        self._total_visits = 0
        self._passed = 0
        self._failed = 0

    def _prune(self, now):
        cutoff = now - self._window
        while self._image_ts and self._image_ts[0] < cutoff:
            self._image_ts.popleft()
        while self._visit_ts and self._visit_ts[0] < cutoff:
            self._visit_ts.popleft()

    def record_image(self):
        now = time.time()
        with self._lock:
            if self._start is None:
                self._start = now
            self._total_images += 1
            self._image_ts.append(now)
            self._prune(now)

    def record_visit(self, status: str = None):
        now = time.time()
        with self._lock:
            self._total_visits += 1
            if status == "Success":
                self._passed += 1
            elif status == "Failed":
                self._failed += 1
            self._visit_ts.append(now)
            self._prune(now)
            elapsed = now - self._start
            win = min(elapsed, self._window)
            wi = len(self._image_ts)
            wv = len(self._visit_ts)
            ti = self._total_images
            tv = self._total_visits
            p = self._passed
            f = self._failed
        # Log outside lock
        logger.info(
            f"[THROUGHPUT] total: {tv} visits ({p} passed, {f} failed), {ti} images in {elapsed:.1f}s "
            f"| last {self._window}s: {wv/win:.2f} visits/sec, {wi/win:.2f} images/sec"
        )

_throughput = _ThroughputTracker(window_sec=60)


def route_to_ai_model(image_type: str, image_path: str, worker_id: int = 0, metadata: dict = None, visit_id: str = "") -> dict:
    """Route to appropriate AI model based on image type"""
    logger.info(f"[Worker {worker_id}] [ROUTER] Routing to AI model for image_type='{image_type}'")
    model_mapping = {
        "share_of_shelf": analyze_share_of_shelf,
        "fixed_shelf": analyze_fixed_shelf,
        "sachet": analyze_sachet,
        "posm": analyze_posm,
        "sovm": analyze_sovm,
        "retail_experiment": analyze_retail_experiment,
    }

    analyzer = model_mapping.get(image_type)
    if not analyzer:
        logger.error(f"[Worker {worker_id}] [ROUTER] ❌ Unknown image type: {image_type}")
        raise ValueError(f"Unknown image type: {image_type}")

    # Pass additional metadata if needed
    kwargs = {"worker_id": worker_id, "visit_id": visit_id}
    if image_type == "fixed_shelf" and metadata:
        kwargs["shelf_type"] = metadata.get("shelf_type")
        kwargs["selected_category"] = metadata.get("selected_category", "all")
    elif image_type == "share_of_shelf" and metadata:
        kwargs["sub_category"] = metadata.get("sub_category") or metadata.get("sub-category", "unknown")
    elif image_type == "retail_experiment" and metadata:
        kwargs["sub_category"] = metadata.get("sub_category") or metadata.get("sub-category", "unknown")
    elif image_type == "posm" and metadata:
        kwargs["posm_items"] = metadata.get("posm_items", [])

    return analyzer(image_path, **kwargs)


async def process_image(sqs_message, worker_id: int = 0):
    """Async wrapper — dispatches to thread pool for true parallel processing"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _inference_pool,
        _process_image_sync,
        sqs_message, worker_id
    )


def _process_image_sync(sqs_message, worker_id: int = 0):
    """Process a single image from S3 (runs in thread pool)"""
    # Import main to access globals (s3_client, sqs_client, visit_aggregator)
    import main

    try:
        body = sqs_message['Body']
        logger.debug(f"[Worker {worker_id}] SQS message received")
        event = json.loads(body)

        # Skip S3 test events
        if event.get('Event') == 's3:TestEvent':
            logger.debug(f"[Worker {worker_id}] Skipping S3 test event")
            return

        # Parse S3 event
        s3_record = None
        bucket = None
        s3_key = None

        # Recheck: metadata embedded in message, skip head_object later
        recheck_metadata = None
        if event.get('recheck'):
            bucket = event['bucket']
            s3_key = event['key']
            recheck_metadata = event.get('metadata', {})
            logger.info(f"[Worker {worker_id}] Recheck message: {s3_key}")
        elif 'Records' in event:
            s3_record = event['Records'][0]['s3']
            bucket = s3_record['bucket']['name']
            s3_key = s3_record['object']['key']
        elif 's3' in event:
            s3_record = event['s3']
            bucket = s3_record['bucket']['name']
            s3_key = s3_record['object']['key']
        elif 'bucket' in event and 'key' in event:
            bucket = event['bucket']
            s3_key = event['key']
        else:
            logger.warning(f"[Worker {worker_id}] Unknown event structure: {json.dumps(event, indent=2)}")
            return

        # URL-decode the S3 key (S3 event notifications URL-encode special characters like & -> %26)
        if s3_key:
            s3_key = unquote_plus(s3_key)

        # Skip folder paths (keys ending with /)
        if s3_key.endswith('/'):
            logger.debug(f"[Worker {worker_id}] Skipping folder path: {s3_key}")
            return

        # Skip non-image files
        valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')
        if not s3_key.lower().endswith(valid_extensions):
            logger.debug(f"[Worker {worker_id}] Skipping non-image file: {s3_key}")
            return

        logger.info(f"[Worker {worker_id}] Processing: {s3_key}")

        # Fetch metadata
        upload_id = 'unknown'
        image_type = 'unknown'
        visit_id = 'unknown'
        shop_id = 'unknown'
        shelf_type = None
        channel = None
        expected_images_count = 1
        slab = None
        sub_category = None
        retake = False
        retake_count = 0

        try:
            if recheck_metadata:
                metadata = recheck_metadata
                logger.debug(f"[Worker {worker_id}] Recheck metadata: {metadata}")
            else:
                metadata_response = main.s3_client.head_object(Bucket=bucket, Key=s3_key)
                metadata = metadata_response.get('Metadata', {})
                logger.debug(f"[Worker {worker_id}] S3 Metadata: {metadata}")

            upload_id = metadata.get('upload-id', 'unknown')
            image_type = metadata.get('image-type', 'unknown')
            visit_id = metadata.get('visit-id', metadata.get('visitid', 'unknown'))
            
            logger.info(f"[Worker {worker_id}] Metadata: visit_id={visit_id}, image_type={image_type}, upload_id={upload_id}")
            shop_id = metadata.get('shop-id', 'unknown')
            shelf_type = slab = metadata.get('slab')
            channel = metadata.get('channel')
            sub_category = metadata.get('sub-category')

            # Get retake count first (how many times this has been retaken: 1, 2, 3...)
            retake_count_str = metadata.get('retake-count', '0')
            try:
                retake_count = int(retake_count_str)
            except (ValueError, TypeError):
                retake_count = 0
                logger.warning(f"Invalid retake-count: {retake_count_str}, defaulting to 0")

            # Detect retake: either 'retake' flag is true OR retake_count > 0
            retake_flag = metadata.get('retake', 'false').lower() == 'true'
            retake = retake_flag or retake_count > 0
            
            # DEBUG: Log retake detection
            if retake:
                logger.info(f"🔄 RETAKE DETECTED for upload_id={upload_id}, visit_id={visit_id}")
                logger.info(f"   Metadata: retake={metadata.get('retake')}, retake-count={metadata.get('retake-count')}")
                logger.info(f"   Detected: retake_flag={retake_flag}, retake_count={retake_count}, retake={retake}")

            # Extract POSM items
            posm_items = []
            posm_items_json = metadata.get('posm-items')
            if posm_items_json:
                try:
                    posm_items = json.loads(posm_items_json)
                except:
                    logger.warning(f"Failed to parse posm-items: {posm_items_json}")
                    posm_items = []

            # Get expected images count for visit aggregation
            # For retakes: ALWAYS default to 1 (no aggregation, immediate processing)
            # Ignore any expected-images-count from presigned URL metadata
            if retake:
                expected_images_count = 1
                logger.info(f"Retake detected (flag={retake_flag}, count={retake_count}): forcing expected_images_count=1")
            else:
                expected_images_str = metadata.get('expected-images-count', '1')
                try:
                    expected_images_count = int(expected_images_str)
                except (ValueError, TypeError):
                    expected_images_count = 1
                    logger.warning(f"Invalid expected-images-count: {expected_images_str}, defaulting to 1")

        except Exception as e:
            logger.warning(f"Could not fetch metadata: {e}")

        # Fallback: parse from S3 key
        if image_type == 'unknown' or visit_id == 'unknown':
            parts = s3_key.split('/')
            if len(parts) >= 4 and parts[0] == 'raw':
                visit_id = parts[1]
                image_type = parts[2]

        if retake:
            logger.info(f"[Worker {worker_id}] Upload: {upload_id}, Type: {image_type}, Visit: {visit_id}, Retake: {retake}, Retake Count: {retake_count}")
        else:
            logger.info(f"[Worker {worker_id}] Upload: {upload_id}, Type: {image_type}, Visit: {visit_id}")

        # Validate image type is supported
        supported_types = ['share_of_shelf', 'fixed_shelf', 'sachet', 'posm', 'sovm', 'retail_experiment']
        if image_type not in supported_types:
            logger.warning(f"[Worker {worker_id}] Unsupported image type '{image_type}', skipping. Supported: {supported_types}")
            return

        # Download image to temp file (bit-for-bit, no decoding/re-encoding)
        s3_dl_start = time.perf_counter()
        image_obj = main.s3_client.get_object(Bucket=bucket, Key=s3_key)
        image_bytes = image_obj['Body'].read()
        s3_download_ms = (time.perf_counter() - s3_dl_start) * 1000

        if len(image_bytes) == 0:
            logger.warning(f"[Worker {worker_id}] Empty file, skipping")
            return

        # Write raw bytes to temp file — preserves original encoding
        ext = os.path.splitext(s3_key)[1] or '.jpg'
        temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        temp_path = temp_file.name
        temp_file.write(image_bytes)
        temp_file.close()

        logger.info(f"[Worker {worker_id}] Downloaded {len(image_bytes)} bytes in {s3_download_ms:.0f}ms")

        # Process with AI
        try:
            logger.info(f"[Worker {worker_id}] Running AI model: {image_type} for visit {visit_id}")

            # Build metadata for AI model
            ai_metadata = {}
            if shelf_type or channel:
                ai_metadata["shelf_type"] = shelf_type
                ai_metadata["channel"] = channel
            if image_type == "share_of_shelf" and sub_category:
                ai_metadata["sub_category"] = sub_category
            if image_type == "posm" and posm_items:
                ai_metadata["posm_items"] = posm_items

            ai_start = time.perf_counter()
            ai_result = route_to_ai_model(
                image_type,
                temp_path,
                worker_id=worker_id,
                metadata=ai_metadata if ai_metadata else None,
                visit_id=visit_id
            )
            ai_processing_ms = (time.perf_counter() - ai_start) * 1000
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        _throughput.record_image()
        logger.info(f"[Worker {worker_id}] ✓ AI processing complete in {ai_processing_ms:.0f}ms")
        logger.info(f"[Worker {worker_id}] {image_type}: {ai_result.get('summary', 'Complete')}")
        
        # Check if AI result is empty or contains errors
        if 'error' in ai_result:
            logger.error(f"[Worker {worker_id}] ❌ AI ERROR for visit {visit_id}: {ai_result.get('error')}")
        elif not ai_result or len(ai_result) <= 2:
            logger.warning(f"[Worker {worker_id}] ⚠ EMPTY RESULT for visit {visit_id}, {image_type}")

        # Debug logging for sachet processing
        if image_type == "sachet":
            logger.info(f"[SACHET DEBUG] Worker {worker_id}:")
            logger.info(f"  upload_id: {upload_id}")
            logger.info(f"  visit_id: {visit_id}")
            logger.info(f"  s3_key: {s3_key}")
            logger.info(f"  Detected products: {list(ai_result.get('product_breakdown', {}).keys())}")
            logger.info(f"  Product counts: {ai_result.get('product_breakdown', {})}")
            logger.info(f"  Expected images count: {expected_images_count}")

        # Map internal image types to API field names
        image_type_mapping = {
            "fixed_shelf": "category_shelf_display",
            "share_of_shelf": "share_of_shelf",
            "sachet": "share_of_sachet",
            "posm": "share_of_posm",
            "sovm": "sovm",
            "retail_experiment": "retail_experiment",
        }
        api_image_type = image_type_mapping.get(image_type, image_type)

        # Prepare metadata for aggregator
        result_metadata = {
            "upload_id": upload_id,
            "s3_key": s3_key,
            "shop_id": shop_id,
            "slab": slab,
            "sub_category": sub_category,
            "retake_count": retake_count,
            "s3_download_ms": round(s3_download_ms, 1),
            "processing_time_ms": round(ai_processing_ms, 1)
        }

        # TODO-REFACTOR: Replace this block when backend ready
        # Future: Send per-image result immediately to SQS (no aggregation)
        # Replace lines 1640-1659 with: main.sqs_client.send_message(QueueUrl=main.SQS_RESULTS_QUEUE_URL, MessageBody=json.dumps(per_image_result))

        # Add result to visit aggregator
        logger.info(f"[Worker {worker_id}] Adding result to aggregator for visit {visit_id}")
        aggregated_result = main.visit_aggregator.add_result(
            visit_id=visit_id,
            image_type=api_image_type,
            result=ai_result,
            metadata=result_metadata,
            expected_count=expected_images_count,
            is_retake=retake
        )

        # If visit is complete, send aggregated result to SQS
        if aggregated_result:
            logger.info(f"[Worker {worker_id}] ===== VISIT COMPLETE =====")
            logger.info(f"[Worker {worker_id}] Visit {visit_id} complete! Sending aggregated result to backend...")
            
            # Log aggregated result summary
            image_types = list(aggregated_result.get('results', {}).keys())
            logger.info(f"[Worker {worker_id}] Aggregated Report Summary for {visit_id}:")
            logger.info(f"[Worker {worker_id}]   - Image types: {', '.join(image_types)}")
            
            # Show summary for each image type
            for img_type, results_list in aggregated_result.get('results', {}).items():
                if results_list and len(results_list) > 0:
                    result = results_list[0]  # Get first result (or latest for retakes)
                    summary = result.get('ai_result', {}).get('summary', 'N/A')
                    logger.info(f"[Worker {worker_id}]   - {img_type}: {summary}")
            
            # Log full aggregated JSON at INFO level
            logger.info(f"[Worker {worker_id}] Full Aggregated Result JSON:")
            logger.info(json.dumps(aggregated_result))

            try:
                response = main.sqs_client.send_message(
                    QueueUrl=main.SQS_RESULTS_QUEUE_URL,
                    MessageBody=json.dumps(aggregated_result)
                )
                message_id = response.get('MessageId', 'unknown')
                logger.info(f"[Worker {worker_id}] ✓ Aggregated result sent to SQS successfully (MessageId: {message_id})")
                logger.info(f"[Worker {worker_id}] Visit {visit_id} processing complete")
                visit_status = aggregated_result.get('ai_summary', {}).get('results', {}).get('store_compliance', {}).get('Status')
                _throughput.record_visit(status=visit_status)
            except Exception as e:
                logger.error(f"[Worker {worker_id}] ❌ FAILED to send aggregated result to SQS for visit {visit_id}: {e}", exc_info=True)
                logger.error(f"[Worker {worker_id}] Visit {visit_id} will be LOST - result not delivered to backend!")
        else:
            logger.info(f"[Worker {worker_id}] Result stored, waiting for more images for visit {visit_id}")

    except Exception as e:
        logger.error(f"[Worker {worker_id}] Error: {e}", exc_info=True)


# ============================================================================
# Main Loop with Worker Pool
# ============================================================================
