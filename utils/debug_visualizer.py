"""
Debug Visualizer Module

Standalone module for visualizing detection results.
Only activated when DEBUG_MODE=true env var is set.

To remove: delete this file and remove imports from detection.py
"""
from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Check if debug mode is enabled
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
DEBUG_OUTPUT_DIR = os.getenv("DEBUG_OUTPUT_DIR", "debug_output")

# Only import heavy deps if debug mode is on
if DEBUG_MODE:
    try:
        from PIL import Image, ImageDraw, ImageFont
        VISUALIZER_AVAILABLE = True
        os.makedirs(DEBUG_OUTPUT_DIR, exist_ok=True)
        logger.info(f"[DEBUG] Visualizer enabled, output dir: {DEBUG_OUTPUT_DIR}")
    except ImportError:
        VISUALIZER_AVAILABLE = False
        logger.warning("[DEBUG] PIL not available, visualizer disabled")
else:
    VISUALIZER_AVAILABLE = False


def _get_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def _get_font():
    """Get a font for drawing text."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        return ImageFont.load_default()


def save_roi_visualization(
    pil_image: Image.Image,
    shelftalker_boxes: List[Dict],
    combined_roi: Optional[List],
    prefix: str = "roi"
) -> Optional[str]:
    """
    Save visualization of shelftalker ROI detection.

    Args:
        pil_image: Original PIL image
        shelftalker_boxes: List of shelftalker detections with bbox info
        combined_roi: Combined ROI box [x1, y1, x2, y2] or None
        prefix: Filename prefix

    Returns:
        Path to saved image or None
    """
    if not DEBUG_MODE or not VISUALIZER_AVAILABLE:
        return None

    try:
        img = pil_image.copy()
        draw = ImageDraw.Draw(img)
        font = _get_font()

        # Draw individual shelftalker boxes in blue
        for i, st in enumerate(shelftalker_boxes):
            if 'bbox' in st:
                box = st['bbox']
                draw.rectangle(box, outline="blue", width=2)
                draw.text((box[0], box[1] - 16), f"ST{i}: {st.get('class_name', '?')}", fill="blue", font=font)

        # Draw combined ROI in green (polygon or rectangle)
        if combined_roi:
            if len(combined_roi) > 0 and isinstance(combined_roi[0], list):
                # Polygon ROI
                polygon_points = [(p[0], p[1]) for p in combined_roi]
                draw.polygon(polygon_points, outline="lime", width=3)
                # Draw label at first vertex
                draw.text((combined_roi[0][0], combined_roi[0][1] - 20), f"SHELFTALKER ROI ({len(combined_roi)} vertices)", fill="lime", font=font)
            elif len(combined_roi) == 4:
                # Rectangle ROI
                draw.rectangle(combined_roi, outline="lime", width=3)
                draw.text((combined_roi[0], combined_roi[1] - 20), "SHELFTALKER ROI", fill="lime", font=font)

        # Save
        filename = f"{prefix}_{_get_timestamp()}.jpg"
        filepath = os.path.join(DEBUG_OUTPUT_DIR, filename)
        img.save(filepath, quality=95)
        logger.info(f"[DEBUG] Saved ROI visualization: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"[DEBUG] Failed to save ROI visualization: {e}")
        return None


def save_exclusivity_visualization(
    pil_image: Image.Image,
    roi_box: Optional[List],
    non_ubl_detections: List[Dict],
    is_exclusive: bool,
    prefix: str = "exclusivity"
) -> Optional[str]:
    """
    Save visualization of exclusivity check.

    Args:
        pil_image: Original PIL image
        roi_box: ROI used for check. Can be:
                 - None: full image
                 - [x1, y1, x2, y2]: rectangular ROI
                 - [[x1,y1], [x2,y2], ...]: polygon ROI
        non_ubl_detections: List of non-UBL detections with bbox and class
        is_exclusive: Whether shelf is exclusive
        prefix: Filename prefix

    Returns:
        Path to saved image or None
    """
    if not DEBUG_MODE or not VISUALIZER_AVAILABLE:
        return None

    try:
        img = pil_image.copy()
        draw = ImageDraw.Draw(img)
        font = _get_font()

        # Draw ROI in cyan
        if roi_box:
            # Check if polygon or rectangle
            if len(roi_box) > 0 and isinstance(roi_box[0], list):
                # Polygon ROI - draw as connected lines
                for i in range(len(roi_box)):
                    p1 = roi_box[i]
                    p2 = roi_box[(i + 1) % len(roi_box)]
                    draw.line([tuple(p1), tuple(p2)], fill="cyan", width=3)
                # Label at first vertex
                draw.text((roi_box[0][0], roi_box[0][1] - 20), "POLYGON ROI", fill="cyan", font=font)
            elif len(roi_box) == 4:
                # Rectangular ROI
                draw.rectangle(roi_box, outline="cyan", width=3)
                draw.text((roi_box[0], roi_box[1] - 20), "RECT ROI", fill="cyan", font=font)

        # Draw non-UBL products in red
        for det in non_ubl_detections:
            if 'bbox' in det:
                box = det['bbox']
                draw.rectangle(box, outline="red", width=2)
                label = det.get('class_name', 'non-UBL')
                draw.text((box[0], box[1] - 16), label, fill="red", font=font)

        # Draw status
        status_color = "lime" if is_exclusive else "red"
        status_text = f"EXCLUSIVE: {'YES' if is_exclusive else 'NO'} ({len(non_ubl_detections)} non-UBL)"
        draw.text((10, 10), status_text, fill=status_color, font=font)

        # Save
        filename = f"{prefix}_{_get_timestamp()}.jpg"
        filepath = os.path.join(DEBUG_OUTPUT_DIR, filename)
        img.save(filepath, quality=95)
        logger.info(f"[DEBUG] Saved exclusivity visualization: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"[DEBUG] Failed to save exclusivity visualization: {e}")
        return None


def save_planogram_roi_visualization(
    pil_image: Image.Image,
    all_detections: List[Dict],
    matched_detections: List[Dict],
    inferred_roi: Optional[List],
    match_ratio: float,
    prefix: str = "planogram_roi"
) -> Optional[str]:
    """
    Save visualization of planogram-inferred ROI.

    Args:
        pil_image: Original PIL image
        all_detections: All product detections
        matched_detections: Detections that matched planogram
        inferred_roi: Inferred ROI. Can be:
                      - [x1, y1, x2, y2]: rectangular bbox
                      - [[x1,y1], [x2,y2], ...]: polygon vertices
        match_ratio: Ratio of matched products
        prefix: Filename prefix

    Returns:
        Path to saved image or None
    """
    if not DEBUG_MODE or not VISUALIZER_AVAILABLE:
        return None

    try:
        img = pil_image.copy()
        draw = ImageDraw.Draw(img)
        font = _get_font()

        # Draw all detections in gray
        for det in all_detections:
            bbox = det.get('bbox_xyxy', [])
            if len(bbox) == 4:
                draw.rectangle(bbox, outline="gray", width=1)

        # Draw matched detections in green
        for det in matched_detections:
            bbox = det.get('bbox_xyxy', [])
            if len(bbox) == 4:
                draw.rectangle(bbox, outline="lime", width=2)
                label = det.get('class_name', '?')[:20]
                draw.text((bbox[0], bbox[1] - 16), label, fill="lime", font=font)

        # Draw inferred ROI in yellow
        if inferred_roi:
            # Check if polygon or rectangle
            if len(inferred_roi) > 0 and isinstance(inferred_roi[0], list):
                # Polygon ROI - draw as connected lines
                for i in range(len(inferred_roi)):
                    p1 = inferred_roi[i]
                    p2 = inferred_roi[(i + 1) % len(inferred_roi)]
                    draw.line([tuple(p1), tuple(p2)], fill="yellow", width=3)
                # Label at first vertex
                draw.text((inferred_roi[0][0], inferred_roi[0][1] - 20), 
                         f"POLYGON ROI ({len(inferred_roi)} vertices)", fill="yellow", font=font)
            elif len(inferred_roi) == 4:
                # Rectangular ROI
                draw.rectangle(inferred_roi, outline="yellow", width=3)
                draw.text((inferred_roi[0], inferred_roi[1] - 20), "INFERRED ROI", fill="yellow", font=font)
        
        # Draw match ratio
        draw.text((10, 10), f"PLANOGRAM MATCH: {match_ratio:.1%}", fill="yellow", font=font)

        # Save
        filename = f"{prefix}_{_get_timestamp()}.jpg"
        filepath = os.path.join(DEBUG_OUTPUT_DIR, filename)
        img.save(filepath, quality=95)
        logger.info(f"[DEBUG] Saved planogram ROI visualization: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"[DEBUG] Failed to save planogram ROI visualization: {e}")
        return None


def save_products_visualization(
    pil_image: Image.Image,
    detections: List[Dict],
    method: str = "unknown",
    prefix: str = "products",
    shelftalkers: Optional[List[Dict]] = None,
    roi_box: Optional[List] = None
) -> Optional[str]:
    """
    Save visualization of detected products with optional shelftalkers and ROI.

    Args:
        pil_image: Original PIL image
        detections: List of product detections
        method: Detection method used (roi/full_image)
        prefix: Filename prefix
        shelftalkers: Optional list of shelftalker detections
        roi_box: Optional ROI box [x1, y1, x2, y2]

    Returns:
        Path to saved image or None
    """
    if not DEBUG_MODE or not VISUALIZER_AVAILABLE:
        return None

    try:
        img = pil_image.copy()
        draw = ImageDraw.Draw(img)
        font = _get_font()

        # Draw shelftalkers first (in blue, behind products)
        if shelftalkers:
            for i, st in enumerate(shelftalkers):
                # Shelftalkers might not have bbox in the dict, skip if missing
                st_name = st.get('class_name', '?')
                st_conf = st.get('confidence', 0)
                # Try to find bbox from position if available
                if 'bbox' in st:
                    bbox = st['bbox']
                    draw.rectangle(bbox, outline="blue", width=2)
                    draw.text((bbox[0], bbox[1] - 16), f"ST: {st_name[:12]} {st_conf:.2f}", fill="blue", font=font)

        # Draw ROI if provided (in magenta)
        if roi_box:
            # Check if polygon or rectangle
            if len(roi_box) > 0 and isinstance(roi_box[0], list):
                # Polygon ROI - draw as connected lines
                for i in range(len(roi_box)):
                    p1 = roi_box[i]
                    p2 = roi_box[(i + 1) % len(roi_box)]
                    draw.line([tuple(p1), tuple(p2)], fill="magenta", width=3)
                # Label at first vertex
                draw.text((roi_box[0][0], roi_box[0][1] - 20), f"ROI ({len(roi_box)} vertices)", fill="magenta", font=font)
            elif len(roi_box) == 4:
                # Rectangular ROI
                draw.rectangle(roi_box, outline="magenta", width=3)
                draw.text((roi_box[0], roi_box[1] - 20), "ROI", fill="magenta", font=font)

        # Draw all product detections
        colors = ["lime", "cyan", "yellow", "orange", "white"]
        for i, det in enumerate(detections):
            bbox = det.get('bbox_xyxy', [])
            if len(bbox) == 4:
                color = colors[i % len(colors)]
                draw.rectangle(bbox, outline=color, width=2)
                label = f"{det.get('class_name', '?')[:15]} {det.get('confidence', 0):.2f}"
                draw.text((bbox[0], bbox[1] - 16), label, fill=color, font=font)

        # Draw info
        info_text = f"METHOD: {method} | PRODUCTS: {len(detections)}"
        if shelftalkers:
            info_text += f" | SHELFTALKERS: {len(shelftalkers)}"
        draw.text((10, 10), info_text, fill="white", font=font)

        # Save
        filename = f"{prefix}_{_get_timestamp()}.jpg"
        filepath = os.path.join(DEBUG_OUTPUT_DIR, filename)
        img.save(filepath, quality=95)
        logger.info(f"[DEBUG] Saved products visualization: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"[DEBUG] Failed to save products visualization: {e}")
        return None
