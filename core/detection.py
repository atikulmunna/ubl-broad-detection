"""
Detection Utilities Module

Contains all detection helper functions for ROI, products, and exclusivity checks.
"""

import os
import logging
import time
import tempfile
from typing import Optional, Dict
from collections import defaultdict

import torch
import yaml
import numpy as np
import cv2
from PIL import Image

from core.model_manager import model_manager
from config.loader import CONFIG, FIXED_SHELF_CONFIG

logger = logging.getLogger(__name__)

# Try importing CATEGORY_MAPPING (optional)
try:
    from utils.category_analysis import CATEGORY_MAPPING
except ImportError:
    logger.warning("Category mapping not available, using 'unknown' for all categories")
    CATEGORY_MAPPING = {}

# Try importing QPDS availability flag
try:
    from utils.qpds_compliance import calculate_compliance
    QPDS_AVAILABLE = True
except ImportError:
    QPDS_AVAILABLE = False

# Debug visualizer (only loads if DEBUG_MODE=true)
# To remove: delete this block and remove debug_* calls below
try:
    from utils.debug_visualizer import (
        DEBUG_MODE,
        save_roi_visualization,
        save_exclusivity_visualization,
        save_planogram_roi_visualization,
        save_products_visualization
    )
except ImportError:
    DEBUG_MODE = False


def calculate_iou(box1, box2) -> float:
    """Calculate Intersection over Union for two bounding boxes"""
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2

    inter_x_min = max(x1_min, x2_min)
    inter_y_min = max(y1_min, y2_min)
    inter_x_max = min(x1_max, x2_max)
    inter_y_max = min(y1_max, y2_max)

    inter_area = max(0, inter_x_max - inter_x_min) * max(0, inter_y_max - inter_y_min)
    box1_area = (x1_max - x1_min) * (y1_max - y1_min)
    box2_area = (x2_max - x2_min) * (y2_max - y2_min)
    union_area = box1_area + box2_area - inter_area

    return inter_area / union_area if union_area > 0 else 0


def _get_expected_shelftalker_prefix(shelf_type: str) -> Optional[str]:
    """Get the expected shelftalker class prefix for a given shelf type."""
    if not shelf_type:
        return None

    try:
        yaml_path = "config/standards/qpds_standards.yaml"
        if not os.path.exists(yaml_path):
            logger.warning(f"QPDS standards file not found: {yaml_path}")
            return None

        with open(yaml_path, 'r') as f:
            standards = yaml.safe_load(f)
            mapping = standards.get('shelftalker_to_shelf_mapping', {})

        return mapping.get(shelf_type)
    except Exception as e:
        logger.error(f"Error loading shelftalker prefix for '{shelf_type}': {e}")
        return None


def _detect_shelftalker_roi(worker_id: int, pil_image: Image.Image, image_path: str, st_conf: float, expand_margin: float,
                            shelf_type: str = None, visit_id: str = ""):
    """Detect shelftalkers and create combined ROI."""
    t1 = time.perf_counter()
    st_results = model_manager.predict('shelftalker', image_path, worker_id=worker_id, conf=st_conf, verbose=False)
    st_result = st_results[0] if st_results else None
    t_predict = (time.perf_counter() - t1) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [Shelftalker] Timing: predict={t_predict:.0f}ms")

    if not st_result or not st_result.boxes:
        return None, [], []

    st_boxes = st_result.boxes.xyxy.cpu().numpy()
    st_scores = st_result.boxes.conf.cpu().numpy()
    st_classes = st_result.boxes.cls.cpu().numpy().astype(int)

    if len(st_boxes) == 0:
        return None, [], []

    shelftalker_model = model_manager.get_model('shelftalker', worker_id=worker_id)
    expected_prefix = _get_expected_shelftalker_prefix(shelf_type) if shelf_type else None

    individual_shelftalkers = []
    filtered_boxes = []
    all_detected = []

    for idx, (box, score, cls_id) in enumerate(zip(st_boxes, st_scores, st_classes)):
        class_name = shelftalker_model.names.get(int(cls_id), str(cls_id)) if shelftalker_model else str(cls_id)

        shelftalker_info = {
            'position': f"shelftalker_{idx}",
            'class_name': class_name,
            'confidence': float(score),
            'bbox': list(box)  # Add bbox for visualization
        }
        all_detected.append(shelftalker_info)

        if expected_prefix:
            if class_name.startswith(expected_prefix):
                individual_shelftalkers.append(shelftalker_info)
                filtered_boxes.append(box)
        else:
            individual_shelftalkers.append(shelftalker_info)
            filtered_boxes.append(box)

    if expected_prefix and len(filtered_boxes) == 0:
        if len(all_detected) > 0:
            detected_types = set([st['class_name'].split('_st_')[0] for st in all_detected if '_st_' in st['class_name']])
            logger.warning(f"[{visit_id}] shelf_type='{shelf_type}' expects '{expected_prefix}' but detected: {detected_types}")
        return None, [], all_detected

    if len(filtered_boxes) == 0:
        return None, [], all_detected

    filtered_boxes = np.array(filtered_boxes)

    # ROI Strategy: Create polygon from inner corner points of all shelftalkers
    # For each shelftalker, use its inner corners based on position
    
    inner_points = []
    for box in filtered_boxes:
        x1, y1, x2, y2 = box
        # Add all 4 corners, we'll create convex hull from them
        inner_points.append([x1, y1])  # top-left
        inner_points.append([x2, y1])  # top-right
        inner_points.append([x1, y2])  # bottom-left
        inner_points.append([x2, y2])  # bottom-right
    
    # Convert to numpy array for convex hull
    inner_points = np.array(inner_points, dtype=np.float32)
    
    # Create convex hull polygon from inner corner points
    hull = cv2.convexHull(inner_points)
    hull_points = hull.squeeze().tolist()
    
    # Ensure we have a valid polygon (at least 3 points)
    if len(hull_points) < 3:
        logger.warning(f"[{visit_id}] Shelftalker ROI polygon has < 3 points: {len(hull_points)}")
        return None, individual_shelftalkers, all_detected
    
    # Apply inward tightening (move vertices toward centroid)
    if expand_margin > 0:
        # Calculate centroid of polygon
        centroid_x = np.mean([p[0] if isinstance(p, (list, np.ndarray)) else 0 for p in hull_points])
        centroid_y = np.mean([p[1] if isinstance(p, (list, np.ndarray)) else 0 for p in hull_points])
        
        # Move each vertex toward centroid by expand_margin ratio
        tightened_points = []
        for point in hull_points:
            if isinstance(point, (list, np.ndarray)):
                x, y = point[0] if len(point) > 0 else 0, point[1] if len(point) > 1 else 0
            else:
                x, y = 0, 0
            
            # Move toward centroid
            x = x + (centroid_x - x) * expand_margin
            y = y + (centroid_y - y) * expand_margin
            tightened_points.append([x, y])
        hull_points = tightened_points
    
    # Clamp polygon points to image bounds
    clamped_polygon = []
    for point in hull_points:
        if isinstance(point, (list, np.ndarray)):
            x, y = point[0] if len(point) > 0 else 0, point[1] if len(point) > 1 else 0
        else:
            x, y = 0, 0
        x = max(0, min(pil_image.width, float(x)))
        y = max(0, min(pil_image.height, float(y)))
        clamped_polygon.append([x, y])
    
    combined_roi = clamped_polygon  # Return polygon instead of bbox

    # Debug visualization (remove block to disable)
    if DEBUG_MODE:
        st_with_bbox = [{'class_name': st['class_name'], 'bbox': list(box)}
                        for st, box in zip(individual_shelftalkers, filtered_boxes)]
        save_roi_visualization(pil_image, st_with_bbox, combined_roi, prefix="shelftalker_roi")
    
    logger.info(f"[{visit_id}] [Shelftalker ROI] Created polygon with {len(clamped_polygon)} vertices from {len(filtered_boxes)} shelftalkers")

    return combined_roi, individual_shelftalkers, all_detected


def _detect_products_in_roi(worker_id: int, pil_image: Image.Image, roi_box: list,
                            ubl_conf: float, selected_category: str):
    """Detect products within ROI (crop then detect)."""
    x1, y1, x2, y2 = roi_box
    roi_image = pil_image.crop((x1, y1, x2, y2))

    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    temp_path = temp_file.name
    temp_file.close()
    roi_image.save(temp_path)

    try:
        qpds_results = model_manager.predict('qpds', temp_path, worker_id=worker_id, conf=ubl_conf, verbose=False)
        qpds_result = qpds_results[0] if qpds_results else None
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    if not qpds_result or not qpds_result.boxes:
        return []

    boxes = qpds_result.boxes.xyxy.cpu().numpy()
    scores = qpds_result.boxes.conf.cpu().numpy()
    class_ids = qpds_result.boxes.cls.cpu().numpy().astype(int)

    qpds_model = model_manager.get_model('qpds', worker_id=worker_id)

    detections = []
    for box, score, class_id in zip(boxes, scores, class_ids):
        class_name = qpds_model.names.get(int(class_id), str(class_id)) if qpds_model else str(class_id)
        category = CATEGORY_MAPPING.get(class_name, 'unknown')

        if class_name.startswith('da_') and '_st_' in class_name:
            continue

        if selected_category != "all" and category != selected_category:
            continue

        x1_global = float(box[0] + x1)
        y1_global = float(box[1] + y1)
        x2_global = float(box[2] + x1)
        y2_global = float(box[3] + y1)

        detections.append({
            'bbox_xyxy': [x1_global, y1_global, x2_global, y2_global],
            'class_name': class_name,
            'category': category,
            'confidence': float(score)
        })

    return detections


def _detect_products_full_image(worker_id: int, pil_image: Image.Image, image_path: str, ubl_conf: float,
                               selected_category: str, visit_id: str = ""):
    """Detect products on full image without ROI restriction (legacy single-stage)."""
    qpds_results = model_manager.predict('qpds', image_path, worker_id=worker_id, conf=ubl_conf, verbose=False)
    qpds_result = qpds_results[0] if qpds_results else None

    if not qpds_result or not qpds_result.boxes:
        return []

    boxes = qpds_result.boxes.xyxy.cpu().numpy()
    scores = qpds_result.boxes.conf.cpu().numpy()
    class_ids = qpds_result.boxes.cls.cpu().numpy().astype(int)

    qpds_model = model_manager.get_model('qpds', worker_id=worker_id)

    detections = []
    for box, score, class_id in zip(boxes, scores, class_ids):
        class_name = qpds_model.names.get(int(class_id), str(class_id)) if qpds_model else str(class_id)
        category = CATEGORY_MAPPING.get(class_name, 'unknown')

        if class_name.startswith('da_') and '_st_' in class_name:
            continue

        if selected_category != "all" and category != selected_category:
            continue

        detections.append({
            'bbox_xyxy': [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
            'class_name': class_name,
            'category': category,
            'confidence': float(score)
        })

    return detections


def _detect_products_two_stage(worker_id: int, pil_image: Image.Image, image_path: str, seg_conf: float,
                               cls_conf: float, cls_batch_size: int, selected_category: str, visit_id: str = ""):
    """
    Two-stage detection pipeline: Segmentation → Classification

    Stage 1: QPDS-seg.pt segments all UBL-like products (single class 'ubl')
    Stage 2: QPDS-cls.pt classifies each segmented instance via masked 384x384 crops

    Args:
        worker_id: Worker ID for CUDA stream selection
        pil_image: Input PIL image
        image_path: Path to image file on disk
        seg_conf: Segmentation confidence threshold (Stage 1)
        cls_conf: Classification confidence threshold (Stage 2)
        cls_batch_size: Batch size for classification inference
        selected_category: Category filter ("all" or specific category)

    Returns:
        List of detection dicts with bbox_xyxy, class_name, category, confidence
    """
    logger.info(f"[Worker {worker_id}] [{visit_id}] [2-Stage] Starting seg+cls pipeline (seg_conf={seg_conf}, cls_conf={cls_conf}, batch={cls_batch_size})")

    # STAGE 1: Instance Segmentation
    t_stage1_start = time.perf_counter()
    seg_results = model_manager.predict('qpds_seg', image_path, worker_id=worker_id, conf=seg_conf, verbose=False)
    seg_result = seg_results[0] if seg_results else None
    t_stage1_ms = (time.perf_counter() - t_stage1_start) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [2-Stage] Stage 1 (seg) took {t_stage1_ms:.0f}ms")
    
    if not seg_result or not seg_result.masks:
        logger.warning(f"[Worker {worker_id}] [{visit_id}] [2-Stage] No segmentation masks detected")
        return []
    
    # Extract segmentation data
    masks = seg_result.masks.data.cpu().numpy()  # [N, H, W] binary masks
    boxes = seg_result.boxes.xyxy.cpu().numpy()  # [N, 4] bounding boxes (from YOLO seg)
    seg_scores = seg_result.boxes.conf.cpu().numpy()  # [N] segmentation confidence
    del seg_result  # free GPU tensors before Stage 2 allocation
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    num_instances = len(masks)
    logger.info(f"[Worker {worker_id}] [{visit_id}] [2-Stage] Stage 1 complete: {num_instances} instances segmented")
    
    if num_instances == 0:
        return []
    
    # STAGE 2: Batch Classification
    # Create masked crops (384x384 with padding) - uses PIL for resizing to match training
    # Parallelize mask resizing (cv2 releases GIL), then sequential PIL operations
    t_crop_start = time.perf_counter()
    image_np = np.array(pil_image)  # RGB format
    img_h, img_w = image_np.shape[:2]
    
    def resize_mask_and_crop(mask, box):
        """Parallel: Resize mask and extract masked crop (GIL-releasing operations)"""
        # cv2.resize releases GIL - safe to parallelize
        mask_resized = cv2.resize(mask.astype(np.uint8), (img_w, img_h), interpolation=cv2.INTER_NEAREST)
        
        x1, y1, x2, y2 = map(int, box)
        
        # NumPy operations release GIL - safe to parallelize
        crop = image_np[y1:y2, x1:x2].copy()
        mask_crop = mask_resized[y1:y2, x1:x2]
        crop[mask_crop == 0] = 0
        
        return crop
    
    # Parallel mask processing (cv2 + NumPy release GIL)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as executor:
        masked_crops = list(executor.map(
            lambda args: resize_mask_and_crop(*args),
            zip(masks, boxes)
        ))
    
    # Sequential PIL resize (PIL might hold GIL, keep it safe)
    crop_images = []
    valid_indices = []
    for idx, crop in enumerate(masked_crops):
        # Skip zero-size crops (degenerate boxes after int truncation)
        if crop.shape[0] == 0 or crop.shape[1] == 0:
            logger.warning(f"[Worker {worker_id}] [{visit_id}] [2-Stage] Skipping zero-size crop at instance {idx}")
            continue

        # Convert to PIL and resize with PIL (matches training pipeline)
        crop_pil = Image.fromarray(crop)

        # Letterbox resize to 384x384 using PIL
        h, w = crop_pil.size[1], crop_pil.size[0]
        scale = min(384 / h, 384 / w)
        new_h, new_w = int(h * scale), int(w * scale)
        
        resized_pil = crop_pil.resize((new_w, new_h), Image.Resampling.BILINEAR)
        
        # Create 384x384 canvas with black padding
        canvas = Image.new('RGB', (384, 384), (0, 0, 0))
        y_offset = (384 - new_h) // 2
        x_offset = (384 - new_w) // 2
        canvas.paste(resized_pil, (x_offset, y_offset))
        
        crop_images.append(canvas)
        valid_indices.append(idx)

    if len(crop_images) == 0:
        logger.warning(f"[Worker {worker_id}] [{visit_id}] [2-Stage] All crops were zero-size, no classifications possible")
        return []

    t_crop_ms = (time.perf_counter() - t_crop_start) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [2-Stage] Created {len(crop_images)} masked crops (384x384) in {t_crop_ms:.0f}ms")

    # Run batch classification via ultralytics predict (thread-safe, uses per-model lock)
    # Process in chunks to avoid OOM when many crops are present; empty_cache between chunks
    # allows PyTorch to defragment reserved-but-unallocated memory.
    t_cls_start = time.perf_counter()
    cls_results = []
    chunk_size = cls_batch_size
    i = 0
    while i < len(crop_images):
        chunk = crop_images[i:i + chunk_size]
        try:
            chunk_results = model_manager.predict('qpds_cls', chunk, worker_id=worker_id,
                                                  batch=chunk_size, verbose=False)
        except torch.cuda.OutOfMemoryError:
            if chunk_size > 1:
                logger.warning(f"[Worker {worker_id}] [{visit_id}] [2-Stage] OOM on chunk_size={chunk_size}, halving to {chunk_size // 2}")
                torch.cuda.empty_cache()
                chunk_size = chunk_size // 2
                continue  # retry same chunk with smaller size
            else:
                raise
        cls_results.extend(chunk_results)
        torch.cuda.empty_cache()
        i += chunk_size

    t_cls_ms = (time.perf_counter() - t_cls_start) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [2-Stage] Stage 2 (cls) took {t_cls_ms:.0f}ms for {len(crop_images)} classifications")

    if not cls_results:
        logger.error(f"[Worker {worker_id}] [{visit_id}] [2-Stage] Classification returned no results")
        return []

    # COMBINE RESULTS (only valid indices that weren't skipped)
    cls_names = cls_results[0].names if cls_results else {}
    valid_boxes = boxes[valid_indices]
    valid_seg_scores = seg_scores[valid_indices]
    detections = []
    for i, (cls_result, box, seg_score) in enumerate(zip(cls_results, valid_boxes, valid_seg_scores)):
        cls_id = cls_result.probs.top1
        cls_score = float(cls_result.probs.top1conf)

        # Check if confidence meets threshold
        if cls_score < cls_conf:
            logger.debug(f"[Worker {worker_id}] [{visit_id}] [2-Stage] Instance {i}: Classification confidence too low ({cls_score:.2f} < {cls_conf})")
            continue

        class_name = cls_names.get(cls_id, str(cls_id))
        category = CATEGORY_MAPPING.get(class_name, 'unknown')

        # Filter shelftalkers
        if class_name.startswith('da_') and '_st_' in class_name:
            continue

        # Filter by selected category
        if selected_category != "all" and category != selected_category:
            continue

        # Combined confidence (seg * cls)
        combined_conf = float(seg_score) * cls_score

        detections.append({
            'bbox_xyxy': [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
            'class_name': class_name,
            'category': category,
            'confidence': combined_conf,  # Combined confidence
            'seg_confidence': float(seg_score),  # Debug: Stage 1 confidence
            'cls_confidence': cls_score  # Debug: Stage 2 confidence
        })
    
    logger.info(f"[Worker {worker_id}] [{visit_id}] [2-Stage] Pipeline complete: {len(detections)}/{num_instances} valid detections")
    return detections


def _detect_products_two_stage_sos(worker_id: int, image_path: str, det_conf: float,
                                    cls_conf: float, cls_batch_size: int, visit_id: str = ""):
    """
    Two-stage SOS pipeline: Detection (bbox) → Brand Classification

    Stage 1: SOS-Detection.pt detects all products as generic bboxes (1 class: 'product')
    Stage 2: SOS-Classification.pt classifies each bbox crop by brand (47 classes)

    Args:
        worker_id: Worker ID for model selection
        image_path: Path to image file on disk
        det_conf: Detection confidence threshold (Stage 1)
        cls_conf: Classification confidence threshold (Stage 2)
        cls_batch_size: Batch size for classification inference
        visit_id: Visit ID for logging

    Returns:
        List of dicts: {brand: str, bbox_xyxy: list[int], confidence: float}
    """
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Starting det+cls pipeline "
                f"(det_conf={det_conf}, cls_conf={cls_conf}, batch={cls_batch_size})")

    # STAGE 1: Object Detection
    t_stage1_start = time.perf_counter()
    det_results = model_manager.predict('sos_det', image_path, worker_id=worker_id,
                                        conf=det_conf, verbose=False)
    det_result = det_results[0] if det_results else None
    t_stage1_ms = (time.perf_counter() - t_stage1_start) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Stage 1 (det) took {t_stage1_ms:.0f}ms")

    if not det_result or not det_result.boxes or len(det_result.boxes) == 0:
        logger.warning(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] No products detected")
        return []

    boxes = det_result.boxes.xyxy.cpu().numpy()   # [N, 4]
    det_scores = det_result.boxes.conf.cpu().numpy()  # [N]
    del det_result
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    num_boxes = len(boxes)
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Stage 1 complete: {num_boxes} products detected")

    # STAGE 2: Crop + Classify
    t_crop_start = time.perf_counter()
    pil_image = Image.open(image_path).convert('RGB')
    img_w, img_h = pil_image.size

    crop_images = []
    valid_indices = []
    for idx, box in enumerate(boxes):
        x1, y1, x2, y2 = map(int, box)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img_w, x2), min(img_h, y2)
        if x2 <= x1 or y2 <= y1:
            logger.warning(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Skipping degenerate box at {idx}")
            continue

        crop_pil = pil_image.crop((x1, y1, x2, y2))
        cw, ch = crop_pil.size
        scale = min(384 / ch, 384 / cw)
        new_w, new_h = int(cw * scale), int(ch * scale)
        resized = crop_pil.resize((new_w, new_h), Image.Resampling.BILINEAR)
        canvas = Image.new('RGB', (384, 384), (0, 0, 0))
        canvas.paste(resized, ((384 - new_w) // 2, (384 - new_h) // 2))
        crop_images.append(canvas)
        valid_indices.append(idx)

    t_crop_ms = (time.perf_counter() - t_crop_start) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Created {len(crop_images)} crops in {t_crop_ms:.0f}ms")

    if not crop_images:
        return []

    # Chunked classification (OOM-safe, same pattern as QPDS)
    t_cls_start = time.perf_counter()
    cls_results = []
    chunk_size = cls_batch_size
    i = 0
    while i < len(crop_images):
        chunk = crop_images[i:i + chunk_size]
        try:
            chunk_results = model_manager.predict('sos_cls', chunk, worker_id=worker_id,
                                                   batch=chunk_size, verbose=False)
        except torch.cuda.OutOfMemoryError:
            if chunk_size > 1:
                logger.warning(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] OOM on chunk_size={chunk_size}, halving")
                torch.cuda.empty_cache()
                chunk_size = chunk_size // 2
                continue
            else:
                raise
        cls_results.extend(chunk_results)
        torch.cuda.empty_cache()
        i += chunk_size

    t_cls_ms = (time.perf_counter() - t_cls_start) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Stage 2 (cls) took {t_cls_ms:.0f}ms for {len(crop_images)} crops")

    # Combine results
    cls_names = cls_results[0].names if cls_results else {}
    detections = []
    for i, (cls_result, orig_idx) in enumerate(zip(cls_results, valid_indices)):
        cls_id = cls_result.probs.top1
        cls_score = float(cls_result.probs.top1conf)
        if cls_score < cls_conf:
            logger.debug(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Instance {i}: cls conf too low ({cls_score:.2f})")
            continue
        brand = cls_names.get(cls_id, str(cls_id))
        det_score = float(det_scores[orig_idx])
        box = boxes[orig_idx]
        detections.append({
            'brand': brand,
            'bbox_xyxy': [int(box[0]), int(box[1]), int(box[2]), int(box[3])],
            'confidence': round(det_score * cls_score, 4),
        })

    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS-2Stage] Final: {len(detections)} classified detections")
    return detections


def _validate_roi_quality(shelftalkers: list, roi_box: list, image_width: int, image_height: int,
                         shelf_type: str = None) -> Dict:
    """Validate ROI quality based on shelftalker detection."""
    quality_info = {
        'quality_score': 0.0,
        'detected_count': len(shelftalkers),
        'expected_count': 4,
        'completeness_ratio': 0.0,
        'roi_area_ratio': 0.0,
        'use_roi': False,
        'reason': ''
    }

    if not shelftalkers or roi_box is None:
        quality_info['reason'] = 'No shelftalkers detected'
        return quality_info

    roi_width = roi_box[2] - roi_box[0]
    roi_height = roi_box[3] - roi_box[1]
    roi_area = roi_width * roi_height
    image_area = image_width * image_height
    roi_area_ratio = roi_area / image_area if image_area > 0 else 0
    quality_info['roi_area_ratio'] = roi_area_ratio

    expected_count = 4
    if QPDS_AVAILABLE and shelf_type:
        try:
            yaml_path = "config/standards/qpds_standards.yaml"
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r') as f:
                    standards = yaml.safe_load(f)
                    expected_shelftalkers = standards.get('expected_shelftalkers', {})
                    expected_count = expected_shelftalkers.get(shelf_type, 4)
        except Exception as e:
            logger.warning(f"Could not load expected shelftalker count for '{shelf_type}': {e}, using default: 4")

    quality_info['expected_count'] = expected_count
    detected_count = len(shelftalkers)
    completeness_ratio = detected_count / expected_count if expected_count > 0 else 0
    quality_info['completeness_ratio'] = completeness_ratio

    min_roi_area_ratio = FIXED_SHELF_CONFIG.get('min_roi_area_ratio', 0.08)
    min_completeness = FIXED_SHELF_CONFIG.get('min_shelftalker_completeness', 0.75)

    if completeness_ratio >= min_completeness and roi_area_ratio >= min_roi_area_ratio:
        quality_info['use_roi'] = True
        quality_info['quality_score'] = completeness_ratio * roi_area_ratio
        quality_info['reason'] = f'High quality: {detected_count}/{expected_count} shelftalkers detected'
    elif detected_count >= 4 and roi_area_ratio >= min_roi_area_ratio:
        quality_info['use_roi'] = True
        quality_info['quality_score'] = 0.8
        quality_info['reason'] = f'Good quality: {detected_count} shelftalkers detected'
    else:
        quality_info['use_roi'] = False
        quality_info['quality_score'] = completeness_ratio * roi_area_ratio * 0.5
        if detected_count < expected_count:
            quality_info['reason'] = f'Incomplete: only {detected_count}/{expected_count} shelftalkers detected'
        elif roi_area_ratio < min_roi_area_ratio:
            quality_info['reason'] = f'ROI too small: {roi_area_ratio*100:.1f}% of image'
        else:
            quality_info['reason'] = 'Low confidence in ROI quality'

    return quality_info


def _infer_roi_from_planogram_products(detections: list, shelf_type: str, img_width: int, img_height: int,
                                        match_threshold: float = 0.70, margin: float = 0.10,
                                        pil_image: Optional[Image.Image] = None, visit_id: str = "") -> Optional[list]:
    """
    Infer ROI from detected products that match the planogram.

    Returns bounding box around planogram-matched products if ≥match_threshold
    of expected total instances are detected.
    """
    if not detections or not shelf_type:
        return None

    try:
        yaml_path = "config/standards/qpds_standards.yaml"
        if not os.path.exists(yaml_path):
            return None

        with open(yaml_path, 'r') as f:
            standards = yaml.safe_load(f)

        shelf_config = standards.get('shelf_types', {}).get(shelf_type)
        if not shelf_config:
            return None

        expected_products = shelf_config.get('products', [])
        product_mappings = standards.get('product_mappings', {})

        # Build reverse mapping: standard name -> AI class names
        reverse_mappings = {}
        for ai_name, standard_name in product_mappings.items():
            if standard_name not in reverse_mappings:
                reverse_mappings[standard_name] = set()
            reverse_mappings[standard_name].add(ai_name)

        # Calculate expected total instances
        expected_total = sum(p.get('quantity', 0) for p in expected_products)
        expected_names = {p['product'] for p in expected_products}

        if expected_total == 0:
            return None

        # Match detections against planogram
        matched_detections = []
        for det in detections:
            class_name = det.get('class_name', '')

            # Check if class_name matches any expected product (direct or via mapping)
            is_match = False
            for expected_name in expected_names:
                # Direct match
                if class_name == expected_name:
                    is_match = True
                    break
                # Check via reverse mapping
                if expected_name in reverse_mappings:
                    if class_name in reverse_mappings[expected_name]:
                        is_match = True
                        break
                # Partial match (class_name contained in expected or vice versa)
                if class_name.lower() in expected_name.lower() or expected_name.lower() in class_name.lower():
                    is_match = True
                    break

            if is_match:
                matched_detections.append(det)

        matched_count = len(matched_detections)
        match_ratio = matched_count / expected_total

        logger.info(f"[{visit_id}] [Planogram ROI] shelf_type={shelf_type}: matched {matched_count}/{expected_total} ({match_ratio:.1%})")

        if match_ratio < match_threshold:
            logger.info(f"[{visit_id}] [Planogram ROI] Below threshold ({match_threshold:.0%}), cannot infer ROI")
            return None

        if len(matched_detections) < 2:
            logger.info(f"[{visit_id}] [Planogram ROI] Need at least 2 matched products to infer ROI")
            return None

        # DENSITY-BASED CLUSTERING: Find the main dense cluster (ignore scattered outliers)
        # Use DBSCAN to identify the largest cluster of planogram products
        # This ensures we only wrap the main shelf cluster, not scattered products in corners
        centers = []
        for det in matched_detections:
            bbox = det.get('bbox_xyxy', [])
            if len(bbox) == 4:
                center_x = (bbox[0] + bbox[2]) / 2
                center_y = (bbox[1] + bbox[3]) / 2
                centers.append((center_x, center_y))
        
        if len(centers) < 3:
            logger.info(f"[{visit_id}] [Planogram ROI] Need at least 3 matched products for clustering")
            return None
        
        # Convert to numpy array for sklearn
        centers_array = np.array(centers)
        
        # Use DBSCAN clustering to find dense groups
        # eps = maximum distance between two samples to be considered neighbors
        # Use tighter eps to separate top products from bottom shelf products
        eps_ratio = FIXED_SHELF_CONFIG.get('dbscan_eps_ratio', 0.08)
        min_samples_ratio = FIXED_SHELF_CONFIG.get('dbscan_min_samples_ratio', 0.15)
        min_samples_absolute = FIXED_SHELF_CONFIG.get('dbscan_min_samples_absolute', 3)
        
        eps = img_width * eps_ratio
        min_samples = max(min_samples_absolute, int(len(centers) * min_samples_ratio))
        
        from sklearn.cluster import DBSCAN
        clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(centers_array)
        labels = clustering.labels_
        
        # Find the largest cluster (ignore noise labeled as -1)
        unique_labels, counts = np.unique(labels[labels >= 0], return_counts=True)
        
        if len(unique_labels) == 0:
            logger.info(f"[{visit_id}] [Planogram ROI] No dense cluster found (all products are scattered)")
            return None
        
        # If multiple clusters exist, prefer the LOWEST one (planograms are usually bottom shelf)
        # Calculate average Y coordinate for each cluster
        if len(unique_labels) > 1:
            cluster_avg_y = []
            for label in unique_labels:
                cluster_indices = np.where(labels == label)[0]
                cluster_y_coords = [centers[i][1] for i in cluster_indices]
                avg_y = np.mean(cluster_y_coords)
                cluster_avg_y.append((label, avg_y, counts[list(unique_labels).index(label)]))
            
            # Sort by Y coordinate (descending = lower on screen) and size
            # Prefer bottom cluster, but only if it has at least 50% of the largest cluster size
            cluster_avg_y.sort(key=lambda x: (-x[1], -x[2]))  # Sort by Y desc, then size desc
            largest_cluster_label = cluster_avg_y[0][0]
            largest_cluster_size = cluster_avg_y[0][2]
            logger.info(f"[{visit_id}] [Planogram ROI] Found {len(unique_labels)} clusters, chose lowest cluster (avg_y={cluster_avg_y[0][1]:.0f})")
        else:
            # Only one cluster
            largest_cluster_label = unique_labels[np.argmax(counts)]
            largest_cluster_size = counts[np.argmax(counts)]
        
        # Filter to only include products in the largest cluster
        clustered_detections = []
        noise_count = 0
        for i, label in enumerate(labels):
            if label == largest_cluster_label:
                clustered_detections.append(matched_detections[i])
            else:
                noise_count += 1
        
        if noise_count > 0:
            logger.info(f"[{visit_id}] [Planogram ROI] DBSCAN: kept {largest_cluster_size} products in main cluster, filtered {noise_count} scattered/outliers")
        
        if len(clustered_detections) < 3:
            logger.info(f"[{visit_id}] [Planogram ROI] Main cluster too small: {len(clustered_detections)} products")
            return None

        # Create CONVEX HULL polygon around clustered product centers (precise boundary)
        # This creates a tight polygon that follows the actual shape of the cluster
        # instead of a rectangular bounding box that includes empty space
        points = []
        for det in clustered_detections:
            bbox = det.get('bbox_xyxy', [])
            if len(bbox) == 4:
                # Use all 4 corners of each product box
                points.extend([
                    [bbox[0], bbox[1]],  # top-left
                    [bbox[2], bbox[1]],  # top-right
                    [bbox[0], bbox[3]],  # bottom-left
                    [bbox[2], bbox[3]]   # bottom-right
                ])

        if len(points) < 3:
            return None

        # Convert to numpy array for cv2
        points = np.array(points, dtype=np.float32)
        
        # Compute convex hull (tight polygon around points)
        hull = cv2.convexHull(points)
        
        # Expand polygon by margin (outward expansion)
        # Calculate centroid
        M = cv2.moments(hull)
        if M["m00"] == 0:
            return None
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]
        
        # Expand each vertex away from centroid
        expanded_hull = []
        for point in hull:
            px, py = point[0]
            # Vector from centroid to point
            dx = px - cx
            dy = py - cy
            # Normalize and expand
            length = np.sqrt(dx*dx + dy*dy)
            if length > 0:
                # Expand by margin percentage
                scale = 1.0 + margin
                new_x = cx + dx * scale
                new_y = cy + dy * scale
                # Clamp to image bounds
                new_x = max(0, min(img_width, new_x))
                new_y = max(0, min(img_height, new_y))
                expanded_hull.append([new_x, new_y])
        
        if len(expanded_hull) < 3:
            return None
        
        # Store as polygon vertices (not rectangular bbox)
        # Format: [[x1,y1], [x2,y2], [x3,y3], ...]
        inferred_roi = [[float(p[0]), float(p[1])] for p in expanded_hull]
        logger.info(f"[{visit_id}] [Planogram ROI] Inferred polygon ROI with {len(inferred_roi)} vertices")

        # Debug visualization (remove block to disable)
        if DEBUG_MODE and pil_image:
            save_planogram_roi_visualization(pil_image, detections, matched_detections, inferred_roi, match_ratio)

        return inferred_roi

    except Exception as e:
        logger.error(f"[{visit_id}] [Planogram ROI] Error inferring ROI: {e}")
        return None


def _check_exclusivity(worker_id: int, pil_image: Image.Image, image_path: str, visit_id: str, roi_box: Optional[list], conf: float,
                      shelf_type: Optional[str] = None, ubl_conf: float = 0.10) -> Dict:
    """
    Check if shelf has exclusivity using only the exclusivity model detections.
    Returns True (is_exclusive) only if no competitor products are detected by the exclusivity model.
    
    roi_box can be:
    - None: check full image
    - [x1, y1, x2, y2]: rectangular ROI
    - [[x1,y1], [x2,y2], ...]: polygon ROI (convex hull)
    
    Note: shelf_type and ubl_conf parameters are kept for backward compatibility but not used.
    """
    # Determine if ROI is polygon or rectangle
    is_polygon = False
    if roi_box is not None:
        if len(roi_box) > 0 and isinstance(roi_box[0], list):
            is_polygon = True
            logger.info(f"[{visit_id}] [Exclusivity] Using polygon ROI with {len(roi_box)} vertices")
        elif len(roi_box) == 4:
            logger.info(f"[{visit_id}] [Exclusivity] Using rectangular ROI")
        else:
            logger.warning(f"[{visit_id}] [Exclusivity] Invalid ROI format: {roi_box}")
            roi_box = None
    
    if roi_box is None:
        logger.info(f"[{visit_id}] [Exclusivity] No ROI, checking full image")
    
    # Always run detection on full image, then filter by ROI
    t1 = time.perf_counter()
    exclusivity_results = model_manager.predict('exclusivity', image_path, worker_id=worker_id, conf=conf, verbose=False)
    exclusivity_result = exclusivity_results[0] if exclusivity_results else None
    t_predict = (time.perf_counter() - t1) * 1000
    logger.info(f"[Worker {worker_id}] [{visit_id}] [Exclusivity] Timing: predict={t_predict:.0f}ms")

    # Process non-UBL detections from exclusivity model only
    non_ubl_breakdown = defaultdict(int)
    non_ubl_detections = []
    
    if exclusivity_result and exclusivity_result.boxes:
        boxes = exclusivity_result.boxes.xyxy.cpu().numpy()
        class_ids = exclusivity_result.boxes.cls.cpu().numpy().astype(int)
        exclusivity_model = model_manager.get_model('exclusivity', worker_id=worker_id)

        for box, class_id in zip(boxes, class_ids):
            class_name = exclusivity_model.names.get(int(class_id), str(class_id)) if exclusivity_model else str(class_id)
            
            # Filter by ROI if provided
            if roi_box is not None:
                # Calculate center point of detection
                center_x = (box[0] + box[2]) / 2
                center_y = (box[1] + box[3]) / 2
                
                if is_polygon:
                    # Check if center point is inside polygon
                    polygon = np.array(roi_box, dtype=np.float32)
                    result = cv2.pointPolygonTest(polygon, (float(center_x), float(center_y)), False)
                    if result < 0:  # Point is outside polygon
                        continue
                else:
                    # Rectangular ROI check
                    x1, y1, x2, y2 = roi_box
                    if not (x1 <= center_x <= x2 and y1 <= center_y <= y2):
                        continue
            
            # Count detection
            non_ubl_breakdown[class_name] += 1
            non_ubl_detections.append({'class_name': class_name, 'bbox': list(box)})
    
    total_violations = len(non_ubl_detections)
    is_exclusive = total_violations == 0

    # Debug visualization (remove block to disable)
    if DEBUG_MODE:
        save_exclusivity_visualization(pil_image, roi_box, non_ubl_detections, is_exclusive)

    return {
        "is_exclusive": is_exclusive,
        "non_ubl_count": total_violations,
        "non_ubl_products": dict(non_ubl_breakdown),
        "breakdown": {
            "non_ubl": dict(non_ubl_breakdown),
            "out_of_planogram": {}  # No longer checking UBL products outside planogram
        }
    }
