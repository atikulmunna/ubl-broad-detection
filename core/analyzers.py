"""
Analyzers Module

Contains all 4 image analyzers: Share of Shelf, Fixed Shelf (QPDS), Sachet, and POSM.
Each analyzer includes feature flag imports for optional compliance calculations.
"""

import sys
import os
import logging
import time
from collections import defaultdict

import numpy as np
from PIL import Image

from core.model_manager import model_manager
from core.detection import (
    _detect_shelftalker_roi, _validate_roi_quality,
    _detect_products_in_roi, _detect_products_full_image, _detect_products_two_stage,
    _detect_products_two_stage_sos,
    _check_exclusivity, _infer_roi_from_planogram_products
)
from config.loader import (
    BRAND_NORMS, SHARE_OF_SHELF_CONFIG, FIXED_SHELF_CONFIG,
    SACHET_CONFIG, POSM_CONFIG, SOVM_CONFIG
)

logger = logging.getLogger(__name__)

# Debug visualizer (only loads if DEBUG_MODE=true)
# To remove: delete this block and remove debug calls below
try:
    from utils.debug_visualizer import DEBUG_MODE, save_products_visualization
except ImportError:
    DEBUG_MODE = False

# Add current directory and /app to path for both local and Docker environments
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if '/app' not in sys.path:
    sys.path.insert(0, '/app')

# ============================================================================
# Feature Flag Imports (Optional Compliance Calculators)
# ============================================================================

# Category Mapping
try:
    from utils.category_analysis import CATEGORY_MAPPING
except ImportError:
    CATEGORY_MAPPING = {}

# Size Variant Detector
try:
    from utils.size_variant_detector import assign_size_variants_simple, get_size_summary
    SIZE_VARIANT_AVAILABLE = True
except ImportError:
    SIZE_VARIANT_AVAILABLE = False
    assign_size_variants_simple = None
    get_size_summary = None
    logger.warning("Size variant detector not available")

# QPDS Compliance
try:
    from utils.qpds_compliance import (
        calculate_compliance, check_planogram_adherence, check_shelftalker_adherence,
        evaluate_compliance_pass, calculate_overall_compliance_with_waivers,
        get_compliance_rules, get_category_brand
    )
    QPDS_AVAILABLE = True
except ImportError:
    QPDS_AVAILABLE = False
    calculate_compliance = None
    check_planogram_adherence = None
    check_shelftalker_adherence = None
    evaluate_compliance_pass = None
    calculate_overall_compliance_with_waivers = None
    get_compliance_rules = None
    get_category_brand = None
    logger.warning("QPDS compliance not available")

# Adjacency Detector (for PS Perfect Store)
try:
    from core.adjacency_detector import evaluate_adjacency_compliance
    ADJACENCY_AVAILABLE = True
except ImportError:
    ADJACENCY_AVAILABLE = False
    evaluate_adjacency_compliance = None
    logger.warning("Adjacency detector not available")

# SOS Compliance
try:
    from utils.sos_compliance import calculate_sos_compliance
    SOS_AVAILABLE = True
except ImportError:
    SOS_AVAILABLE = False
    calculate_sos_compliance = None
    logger.warning("SOS compliance not available")

# Sachet Compliance
try:
    from utils.sachet_compliance import calculate_sachet_compliance
    SACHET_AVAILABLE = True
except ImportError:
    SACHET_AVAILABLE = False
    calculate_sachet_compliance = None
    logger.warning("Sachet compliance not available")

# POSM Compliance
try:
    from utils.posm_compliance import calculate_posm_compliance
    POSM_AVAILABLE = True
except ImportError:
    POSM_AVAILABLE = False
    calculate_posm_compliance = None
    logger.warning("POSM compliance not available")


# ============================================================================
# Analyzer Functions
# ============================================================================

def analyze_share_of_shelf(image_path: str, worker_id: int = 0, visit_id: str = "",
                            sub_category: str = "unknown") -> dict:
    """Analyze Share of Shelf using two-stage detection+classification pipeline"""
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS] Starting SOS analysis (sub_category={sub_category})")
    try:
        t_start = time.perf_counter()

        det_conf = SHARE_OF_SHELF_CONFIG.get('det_conf', 0.25)
        cls_conf = SHARE_OF_SHELF_CONFIG.get('cls_conf', 0.50)
        cls_batch_size = SHARE_OF_SHELF_CONFIG.get('cls_batch_size', 8)

        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS] det_conf={det_conf}, cls_conf={cls_conf}, batch={cls_batch_size}")

        t_detect = time.perf_counter()
        detections = _detect_products_two_stage_sos(
            worker_id, image_path, det_conf, cls_conf, cls_batch_size, visit_id=visit_id
        )
        detection_ms = (time.perf_counter() - t_detect) * 1000

        # Classify each detection as UBL or competitor via brand norm lookup
        t_classify = time.perf_counter()
        ubl_brands = defaultdict(int)
        competitor_brands = defaultdict(int)

        for det in detections:
            brand = det['brand']
            entry = BRAND_NORMS.get(brand)
            if entry and entry.get('is_ubl') == 'yes':
                ubl_brands[brand] += 1
            else:
                competitor_brands[brand] += 1

        classify_ms = (time.perf_counter() - t_classify) * 1000

        ubl_count = sum(ubl_brands.values())
        competitor_count = sum(competitor_brands.values())
        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS] UBL: {dict(ubl_brands)}")
        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS] Competitor: {dict(competitor_brands)}")

        # Compliance: check each UBL brand against min_qty
        t_compliance = time.perf_counter()
        compliance_score = 0.0
        product_accuracy = []
        ubl_norms = {k: v for k, v in BRAND_NORMS.items() if v.get('is_ubl') == 'yes'}
        if ubl_norms:
            met = 0
            for brand, norm in ubl_norms.items():
                min_qty = norm.get('min_qty', 1)
                detected = ubl_brands.get(brand, 0)
                passed = detected >= min_qty
                if passed:
                    met += 1
                product_accuracy.append({
                    'brand': brand,
                    'detected': detected,
                    'min_qty': min_qty,
                    'passed': passed,
                })
            compliance_score = round((met / len(ubl_norms)) * 100, 1)
        compliance_ms = (time.perf_counter() - t_compliance) * 1000

        # Category breakdown — all detections belong to client-supplied sub_category
        category_breakdown = {
            sub_category: {
                **{b: c for b, c in ubl_brands.items()},
                **{b: c for b, c in competitor_brands.items()},
            }
        }

        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOS] ✓ {ubl_count} UBL + {competitor_count} competitor | compliance={compliance_score}%")

        return {
            "model_version": "SOS-Detection + SOS-Classification (47 brands)",
            "confidence": {"det": det_conf, "cls": cls_conf},
            "total_products": ubl_count + competitor_count,
            "ubl_product_breakdown": dict(ubl_brands),
            "competitor_product_breakdown": dict(competitor_brands),
            "category_breakdown": category_breakdown,
            "competitor_count": competitor_count,
            "compliance_score": compliance_score,
            "product_accuracy": product_accuracy,
            "timing": {
                "total_ms": round(total_ms, 1),
                "detection_ms": round(detection_ms, 1),
                "classification_ms": round(classify_ms, 1),
                "compliance_ms": round(compliance_ms, 1),
            },
            "summary": f"Detected {ubl_count} UBL + {competitor_count} competitor products",
        }

    except Exception as e:
        logger.error(f"[{visit_id}] [SOS] Error in analyze_share_of_shelf: {e}", exc_info=True)
        return {
            "error": str(e),
            "summary": "Error processing Share of Shelf"
        }


def analyze_fixed_shelf(image_path: str, worker_id: int = 0, shelf_type: str = None, selected_category: str = "all", visit_id: str = "") -> dict:
    """Analyze Fixed Shelf (QPDS) - FULL IMPLEMENTATION with all features"""
    logger.info(f"[Worker {worker_id}] [{visit_id}] [QPDS] Starting Fixed Shelf analysis (shelf_type={shelf_type}, category={selected_category})")
    try:
        t_start = time.perf_counter()
        pil_image = Image.open(image_path).convert("RGB")
        image = np.array(pil_image)
        img_height, img_width = image.shape[:2]
        logger.info(f"[Worker {worker_id}] [{visit_id}] [QPDS] Image dimensions: {img_width}x{img_height}")

        # Get config
        use_two_stage = FIXED_SHELF_CONFIG.get('use_two_stage', False)
        st_conf = FIXED_SHELF_CONFIG.get('shelftalker_conf', 0.15)
        exclusivity_conf = FIXED_SHELF_CONFIG.get('exclusivity_conf', 0.35)
        expand_margin = FIXED_SHELF_CONFIG.get('expand_margin', 0.05)
        
        # Pipeline-specific config
        if use_two_stage:
            seg_conf = FIXED_SHELF_CONFIG.get('seg_conf', 0.25)
            cls_conf = FIXED_SHELF_CONFIG.get('cls_conf', 0.30)
            cls_batch_size = FIXED_SHELF_CONFIG.get('cls_batch_size', 32)
            ubl_conf = seg_conf  # Use seg_conf for exclusivity check (same threshold purpose)
            logger.info(f"[Worker {worker_id}] [{visit_id}] [QPDS] Using 2-stage pipeline (seg_conf={seg_conf}, cls_conf={cls_conf}, batch={cls_batch_size})")
        else:
            ubl_conf = FIXED_SHELF_CONFIG.get('ubl_conf', 0.25)
            logger.info(f"[Worker {worker_id}] [{visit_id}] [QPDS] Using legacy single-stage pipeline (ubl_conf={ubl_conf})")
        
        logger.debug(f"[Worker {worker_id}] [{visit_id}] [QPDS] Config: st_conf={st_conf}, exclusivity_conf={exclusivity_conf}")

        # Step 1: Detect shelftalkers and create combined ROI
        t_shelftalker = time.perf_counter()
        combined_roi, shelftalkers, all_shelftalkers = _detect_shelftalker_roi(worker_id, pil_image, image_path, st_conf, expand_margin, shelf_type, visit_id=visit_id)
        logger.info(f"[{visit_id}] [QPDS] Shelftalkers detected: {len(shelftalkers)}")
        if shelftalkers:
            for st in shelftalkers:
                logger.info(f"[{visit_id}]- {st['position']}: {st['class_name']} (conf: {st['confidence']:.2f})")

        # Step 2: Use shelftalker ROI if any shelftalkers detected (no quality validation)
        if combined_roi is not None:
            logger.info(f"[{visit_id}] [QPDS] Using shelftalker ROI (polygon with {len(combined_roi)} vertices from {len(shelftalkers)} shelftalkers)")
        else:
            logger.info(f"[{visit_id}] [QPDS] No valid shelftalker ROI ({len(shelftalkers)} shelftalkers detected but ROI creation failed)")

        # Preserve the original ROI for exclusivity check
        exclusivity_roi = combined_roi
        detections = []
        method = "full_image"

        shelftalker_ms = (time.perf_counter() - t_shelftalker) * 1000

        # Step 3: Detect products using selected pipeline
        t_products = time.perf_counter()
        if use_two_stage:
            logger.info(f"[Worker {worker_id}] [{visit_id}] [QPDS] Using 2-stage seg+cls detection")
            detections = _detect_products_two_stage(worker_id, pil_image, image_path, seg_conf, cls_conf, cls_batch_size, selected_category, visit_id=visit_id)
            method = "two_stage (seg+cls)"
        else:
            logger.info(f"[Worker {worker_id}] [{visit_id}] [QPDS] Using legacy single-stage detection")
            detections = _detect_products_full_image(worker_id, pil_image, image_path, ubl_conf, selected_category, visit_id=visit_id)
            method = "full_image (legacy single-stage)"

        product_detection_ms = (time.perf_counter() - t_products) * 1000
        logger.info(f"[Worker {worker_id}] [{visit_id}] [QPDS] Product detection complete: {len(detections)} products found")
        if len(detections) == 0:
            logger.warning(f"[Worker {worker_id}] [{visit_id}] [QPDS] ⚠ NO PRODUCTS DETECTED (conf={ubl_conf}, method={method})")

        # Debug visualization (remove block to disable)
        if DEBUG_MODE and detections:
            save_products_visualization(pil_image, detections, method, prefix="qpds_products", 
                                       shelftalkers=shelftalkers, roi_box=combined_roi)

        # Step 4: Check exclusivity (ROI still used here)
        # Priority: 1) Shelftalker ROI, 2) Planogram-inferred ROI, 3) NA
        t_exclusivity = time.perf_counter()
        planogram_roi_threshold = FIXED_SHELF_CONFIG.get('planogram_roi_match_threshold', 0.70)
        planogram_roi_margin = FIXED_SHELF_CONFIG.get('planogram_roi_margin', 0.10)

        if exclusivity_roi is not None:
            # Shelftalker ROI detected - use it for exclusivity
            logger.info(f"[{visit_id}] [QPDS] Exclusivity check: using shelftalker ROI")
            exclusivity_data = _check_exclusivity(worker_id, pil_image, image_path, visit_id, exclusivity_roi, exclusivity_conf, shelf_type, ubl_conf)
        elif detections:
            # Fallback: try to infer ROI from planogram-matched products
            inferred_roi = _infer_roi_from_planogram_products(
                detections, shelf_type, img_width, img_height,
                match_threshold=planogram_roi_threshold, margin=planogram_roi_margin,
                pil_image=pil_image, visit_id=visit_id
            )
            if inferred_roi:
                logger.info(f"[{visit_id}] [QPDS] Exclusivity check: using planogram-inferred ROI")
                exclusivity_data = _check_exclusivity(worker_id, pil_image, image_path, visit_id, inferred_roi, exclusivity_conf, shelf_type, ubl_conf)
            else:
                # Cannot determine ROI reliably
                logger.warning(f"[{visit_id}] [QPDS] Exclusivity check: insufficient data, marking as NA")
                exclusivity_data = {"is_exclusive": None, "non_ubl_count": 0, "non_ubl_products": {}}
        else:
            # No detections or no shelf_type - cannot determine
            logger.warning(f"[{visit_id}] [QPDS] Exclusivity check: no detections or shelf_type, marking as NA")
            exclusivity_data = {"is_exclusive": None, "non_ubl_count": 0, "non_ubl_products": {}}

        exclusivity_ms = (time.perf_counter() - t_exclusivity) * 1000

        if exclusivity_data["is_exclusive"] is None:
            exclusivity_status = "na"
        elif exclusivity_data["is_exclusive"]:
            exclusivity_status = "yes"
        else:
            exclusivity_status = "no"
        non_ubl_count = exclusivity_data["non_ubl_count"]
        non_ubl_products = exclusivity_data["non_ubl_products"]
        breakdown = exclusivity_data.get("breakdown", {})
        if non_ubl_products:
            if breakdown.get("non_ubl"):
                logger.info(f"[{visit_id}] [QPDS] Non-UBL products detected: {breakdown['non_ubl']}")
            if breakdown.get("out_of_planogram"):
                logger.info(f"[{visit_id}] [QPDS] UBL products outside planogram: {breakdown['out_of_planogram']}")

        # Step 5: Apply size variants
        size_summary = {}
        if SIZE_VARIANT_AVAILABLE and detections and assign_size_variants_simple:
            detections = assign_size_variants_simple(detections)
            size_summary = get_size_summary(detections)

        # Build product breakdown from ALL detections (full image, no ROI filtering)
        # Use composite key (class_name:size_variant) when size_variant is available
        breakdown = defaultdict(int)
        for det in detections:
            sv = det.get('size_variant', 'N/A')
            if sv and sv != 'N/A':
                key = f"{det['class_name']}:{sv}"
            else:
                key = det['class_name']
            breakdown[key] += 1

        # Log detected products
        logger.info(f"[{visit_id}] [QPDS] Shelf Type: {shelf_type}")
        logger.info(f"[{visit_id}] [QPDS] Total products detected: {len(detections)} (full image, no ROI filtering)")
        logger.info(f"[{visit_id}] [QPDS] Product breakdown: {dict(breakdown)}")

        # Step 6: Calculate variant compliance if QPDS is available and shelf_type is provided
        t_compliance = time.perf_counter()
        variant_compliance = 0.0
        product_accuracy = []
        planogram_adherence = True
        shelftalker_adherence = True
        adjacency_result = {}
        adjacency_pass = True
        shelftalker_waived = False
        criteria_met = False

        if QPDS_AVAILABLE and shelf_type:
            # Calculate variant compliance with waivers applied
            variant_compliance, product_accuracy = calculate_compliance(shelf_type, dict(breakdown))

            # Check planogram adherence (product order left-to-right)
            # NOTE: uses raw class_name (no size variant) — see qpds_compliance.py comment
            detection_list = []
            for det in detections:
                detection_list.append({
                    'product_name': det['class_name'],
                    'bbox_xyxy': det['bbox_xyxy']
                })
            logger.info(f"[{visit_id}] [QPDS] Checking planogram adherence for {len(detection_list)} detections")
            planogram_adherence = check_planogram_adherence(shelf_type, detection_list)
            logger.info(f"[{visit_id}] [QPDS] Planogram adherence (order): {'Pass' if planogram_adherence else 'Fail'}")

            # Check shelftalker adherence (minimum shelftalker count)
            shelftalker_adherence = check_shelftalker_adherence(shelf_type, len(shelftalkers))

            # Step 6b: Evaluate adjacency for PS Perfect Store shelf types
            if ADJACENCY_AVAILABLE and evaluate_adjacency_compliance:
                adjacency_result = evaluate_adjacency_compliance(detection_list, shelf_type, shelftalker_dets=all_shelftalkers)
                adjacency_pass = adjacency_result.get('adjacency_pass', True)
                shelftalker_waived = adjacency_result.get('shelftalker_waived', False)
                if shelftalker_waived:
                    shelftalker_adherence = True

                if adjacency_result.get('category_brand'):
                    logger.info(f"[{visit_id}] [QPDS] Adjacency: {adjacency_result['category_brand']} - "
                               f"{adjacency_result['actual_legs']}/{adjacency_result['required_legs']} legs, "
                               f"pass={adjacency_pass}, shelftalker_waived={shelftalker_waived}")

            # Log planogram comparison
            logger.info(f"[{visit_id}] [QPDS] Planogram comparison for {shelf_type}:")
            for item in product_accuracy:
                waived_tag = " [WAIVED]" if item.get('waived', False) else ""
                logger.info(f"[{visit_id}]- {item['name']}: planned={item['planned']}, visible={item['visible']}, accuracy={item['accuracy']}%{waived_tag}")
            logger.info(f"[{visit_id}] [QPDS] Variant compliance: {variant_compliance}%")
            logger.info(f"[{visit_id}] [QPDS] Planogram adherence (order): {'Pass' if planogram_adherence else 'Fail'}")
            
            # Planogram adherence is ONLY about sequence, not quantity
            # Quantity check removed as per requirements
            logger.info(f"[{visit_id}] [QPDS] Shelftalker adherence: {'Pass' if shelftalker_adherence else 'Fail'} ({len(shelftalkers)} detected)")

        # Format products array with correct field names
        products_formatted = []
        total_planned = 0
        total_visible = 0
        total_planned_non_waived = 0
        total_visible_non_waived = 0

        for item in product_accuracy:
            is_waived = item.get('waived', False)
            products_formatted.append({
                "sku_name": item["name"],
                "planned_qty": item["planned"],
                "visible_qty": item["visible"],
                "accuracy": item["accuracy"],
                "waived": is_waived
            })
            total_planned += item["planned"]
            total_visible += item["visible"]

            # Track non-waived totals separately
            if not is_waived:
                total_planned_non_waived += item["planned"]
                total_visible_non_waived += item["visible"]

        # Calculate overall compliance excluding waived products
        if total_planned_non_waived > 0:
            overall_compliance = min((total_visible_non_waived / total_planned_non_waived * 100), 100.0)
        elif total_planned > 0:
            # All products waived = 100% compliance
            overall_compliance = 100.0
        else:
            overall_compliance = 0.0

        # Step 7: Evaluate criteria_met based on per-planogram compliance rules
        exclusivity_bool = exclusivity_status != "no"
        if QPDS_AVAILABLE and evaluate_compliance_pass and shelf_type:
            criteria_met, compliance_details = evaluate_compliance_pass(
                shelf_type=shelf_type,
                overall_compliance=overall_compliance,
                variant_compliance=variant_compliance,
                planogram_adherence=planogram_adherence,
                shelftalker_adherence=shelftalker_adherence,
                exclusivity=exclusivity_bool,
                adjacency_pass=adjacency_pass,
                shelftalker_waived=shelftalker_waived
            )
            logger.info(f"[{visit_id}] [QPDS] Compliance evaluation: criteria_met={criteria_met}, details={compliance_details}")
        else:
            # Fallback: use 80% threshold
            criteria_met = overall_compliance >= 80.0
            compliance_details = {}

        # Log final results
        logger.info(f"[{visit_id}] [QPDS] Final Results:")
        logger.info(f"[{visit_id}]Overall Compliance: {round(overall_compliance, 2)}% (excl. waived)")
        logger.info(f"[{visit_id}]Total Planned: {total_planned} ({total_planned_non_waived} non-waived)")
        logger.info(f"[{visit_id}]Total Visible: {total_visible} ({total_visible_non_waived} non-waived)")
        logger.info(f"[{visit_id}]Exclusivity: {exclusivity_status} (non-UBL: {non_ubl_count})")
        logger.info(f"[{visit_id}]Criteria Met: {criteria_met}")

        result = {
            "model_version": "QPDS + Shelftalker + Exclusivity",
            "shelf_type": shelf_type or "Unknown",
            "status": "completed",

            # API output fields (matching ai_summary.json)
            "overall_compliance": round(overall_compliance, 2),
            "planogram_adherence": "Yes" if planogram_adherence else "No",
            "exclusively": "No" if exclusivity_status == "no" else "Yes",
            "variant_compliance": variant_compliance,
            "shelf_talker_present": "Yes" if len(shelftalkers) > 0 else "No",
            "shelf_talker_orientation_correct": "Yes" if shelftalker_adherence else "No",

            # NEW: Per-planogram compliance evaluation
            "criteria_met": criteria_met,
            "shelftalker_waived": shelftalker_waived,

            "products": products_formatted,
            "totals": {
                "total_planned": total_planned,
                "total_visible": total_visible,
                "total_planned_non_waived": total_planned_non_waived,
                "total_visible_non_waived": total_visible_non_waived
            },

            # Non-redundant metadata
            "no_of_shelftalker": len(shelftalkers),
            "shelftalkers_detected": shelftalkers,
            "total_products": len(detections),
            "product_breakdown": dict(breakdown),
            "selected_category": selected_category,
            "size_summary": size_summary,
            "method": method,
            "non_ubl_count": non_ubl_count,
            "non_ubl_products": non_ubl_products,

            # Adjacency info (PS Perfect Store) - only for shelftalker waiver
            "adjacency": {
                "category_brand": adjacency_result.get('category_brand'),
                "adjacent_to": adjacency_result.get('adjacency_info', {}).get('categories', {}).get(
                    adjacency_result.get('category_brand'), {}
                ).get('adjacent_to', []),
                "orientation": adjacency_result.get('orientation'),
                "shelftalker_waived": shelftalker_waived,
                "all_shelftalkers_detected": [st['class_name'] for st in all_shelftalkers],
            } if adjacency_result.get('category_brand') else None,

            "summary": f"Fixed Shelf: {len(detections)} products, {round(overall_compliance, 2)}% compliance, " +
                      f"Criteria: {'Pass' if criteria_met else 'Fail'}, " +
                      f"Exclusivity: {exclusivity_status}"
        }

        compliance_ms = (time.perf_counter() - t_compliance) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000
        result["timing"] = {
            "total_ms": round(total_ms, 1),
            "shelftalker_detection_ms": round(shelftalker_ms, 1),
            "product_detection_ms": round(product_detection_ms, 1),
            "exclusivity_check_ms": round(exclusivity_ms, 1),
            "compliance_calc_ms": round(compliance_ms, 1)
        }

        logger.info(f"[Worker {worker_id}] [{visit_id}] [QPDS] ✓ Analysis complete: {len(detections)} products, {round(overall_compliance, 2)}% compliance in {total_ms:.0f}ms")
        return result

    except Exception as e:
        logger.error(f"[Worker {worker_id}] [{visit_id}] [QPDS] ❌ Error in analyze_fixed_shelf: {e}", exc_info=True)
        return {
            "error": str(e),
            "summary": "Error processing Fixed Shelf"
        }


def analyze_sachet(image_path: str, worker_id: int = 0, visit_id: str = "") -> dict:
    """Analyze Sachet Display"""
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SACHET] Starting Sachet analysis")
    try:
        t_start = time.perf_counter()

        # Run sachet detection
        conf = SACHET_CONFIG.get('confidence', 0.30)
        logger.debug(f"[Worker {worker_id}] [{visit_id}] [SACHET] Running detection with conf={conf}")
        t_detect = time.perf_counter()
        results = model_manager.predict(
            'sachet',
            source=image_path,
            worker_id=worker_id,
            conf=conf,
            verbose=False
        )

        detection_ms = (time.perf_counter() - t_detect) * 1000

        # Process detections with bounding boxes
        detected_products = defaultdict(int)
        detections = []
        model_result = results[0] if results else None

        # Diagnostic logging for model results
        if not model_result:
            logger.warning(f"[Worker {worker_id}] [{visit_id}] [SACHET] ⚠ Model returned no results object")
        elif not model_result.boxes:
            logger.warning(f"[Worker {worker_id}] [{visit_id}] [SACHET] ⚠ Model returned results but no boxes detected (conf={conf})")
        else:
            raw_detection_count = len(model_result.boxes)
            logger.info(f"[Worker {worker_id}] [{visit_id}] [SACHET] Model detected {raw_detection_count} boxes with conf>={conf}")

        if model_result and model_result.boxes:
            boxes = model_result.boxes.xyxy.cpu().numpy()
            scores = model_result.boxes.conf.cpu().numpy()
            class_ids = model_result.boxes.cls.cpu().numpy().astype(int)

            # OPTIMIZED: Vectorized detection processing
            # Build all detections at once (no loop)
            detections = [
                {
                    'bbox_xyxy': [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
                    'class_name': model_result.names[int(class_id)],
                    'confidence': float(score)
                }
                for box, score, class_id in zip(boxes, scores, class_ids)
            ]
            
            # Count products (vectorized)
            for det in detections:
                detected_products[det['class_name']] += 1

            logger.info(f"[Worker {worker_id}] [{visit_id}] [SACHET] Detected products: {dict(detected_products)}")

        # Calculate compliance with additional checks
        t_compliance = time.perf_counter()
        compliance_score = 0.0
        product_accuracy = []
        additional_checks = {}

        if SACHET_AVAILABLE and calculate_sachet_compliance:
            compliance_score, product_accuracy, additional_checks = calculate_sachet_compliance(
                dict(detected_products),
                detections
            )

        # Build summary with additional checks
        summary_parts = [f"Detected {sum(detected_products.values())} sachets with {compliance_score}% compliance"]

        # Extract additional checks data
        slot_adherence_data = additional_checks.get('slot_adherence', {})
        orientation_adherence_data = additional_checks.get('orientation_adherence', {})
        combined_hanger = additional_checks.get('combined_hanger', False)
        brand_exclusive = additional_checks.get('brand_exclusive_hanger', False)

        # Format orientation adherence for API
        orientation_adherence_formatted = "NA"
        if orientation_adherence_data:
            orientation_adherence_formatted = "Yes" if orientation_adherence_data.get('adherence', False) else "No"
            if orientation_adherence_data.get('adherence'):
                summary_parts.append(f"Orientation: Pass")
            else:
                summary_parts.append(f"Orientation: Fail")

        # Format slot adherence for API
        slot_adherence_formatted = "NA"
        if slot_adherence_data:
            # NA if no hangers detected, otherwise Yes/No based on adherence
            if slot_adherence_data.get('total_sachets', 0) == 0:
                slot_adherence_formatted = "NA"
            else:
                slot_adherence_formatted = "Yes" if slot_adherence_data.get('adherence', False) else "No"

            if slot_adherence_data.get('adherence'):
                summary_parts.append(f"Slot Adherence: Pass")
            else:
                summary_parts.append(f"Slot Adherence: Fail")

        # Format combined hanger info
        combined_hanger_info = "Combined hanger display detected" if combined_hanger else "Single brand hanger display"
        if combined_hanger:
            summary_parts.append("Combined Hanger: Yes")

        # Format brand exclusive hanger info
        brand_exclusive_info = "Brand exclusive display" if brand_exclusive else "Mixed brand display"
        if brand_exclusive:
            summary_parts.append("Brand Exclusive: Yes")

        compliance_ms = (time.perf_counter() - t_compliance) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000

        result = {
            "model_version": "SACHET_YOLO11X",
            "confidence": conf,
            "total_sachets": sum(detected_products.values()),
            "unique_products": len(detected_products),
            "product_breakdown": dict(detected_products),
            "compliance_score": compliance_score,
            "product_accuracy": product_accuracy,

            # Formatted output for API
            "orientation_adherence": orientation_adherence_formatted,
            "slot_adherence": slot_adherence_formatted,
            "combined_sachet_hanger_info": combined_hanger_info,
            "brand_exclusive_hanger_info": brand_exclusive_info,

            # Raw data (kept for backward compatibility)
            "slot_adherence_details": slot_adherence_data,
            "orientation_adherence_details": orientation_adherence_data,
            "combined_hanger": combined_hanger,
            "brand_exclusive_hanger": brand_exclusive,

            "timing": {
                "total_ms": round(total_ms, 1),
                "detection_ms": round(detection_ms, 1),
                "compliance_ms": round(compliance_ms, 1)
            },

            "summary": ", ".join(summary_parts)
        }
        logger.info(f"[Worker {worker_id}] [{visit_id}] [SACHET] ✓ Analysis complete: {result['total_sachets']} sachets, {compliance_score}% compliance in {total_ms:.0f}ms")
        return result

    except Exception as e:
        logger.error(f"[Worker {worker_id}] [{visit_id}] [SACHET] ❌ Error in analyze_sachet: {e}", exc_info=True)
        return {
            "error": str(e),
            "summary": "Error processing Sachet"
        }


# ============================================================================
# Competitor POSM Standards Loader (used by POSM and SOVM analyzers)
# ============================================================================

_COMPETITOR_POSM_CACHE = None


def _load_competitor_posm_standards():
    """Load competitor POSM standards from YAML (cached)"""
    global _COMPETITOR_POSM_CACHE
    if _COMPETITOR_POSM_CACHE is None:
        try:
            import yaml
            from pathlib import Path
            standards_path = Path(__file__).parent.parent / "config" / "standards" / "competitor_posm_standards.yaml"
            with open(standards_path) as f:
                data = yaml.safe_load(f)
                _COMPETITOR_POSM_CACHE = data.get('item_mappings', {})
                logger.info(f"Loaded {len(_COMPETITOR_POSM_CACHE)} competitor POSM standards")
        except Exception as e:
            logger.warning(f"Could not load competitor POSM standards: {e}")
            _COMPETITOR_POSM_CACHE = {}
    return _COMPETITOR_POSM_CACHE


def analyze_posm(image_path: str, worker_id: int = 0, posm_items: list = None, visit_id: str = "") -> dict:
    """Analyze POSM (Point of Sale Materials)

    Args:
        image_path: Path to image file on disk
        worker_id: Worker ID for GPU stream
        posm_items: List of planned POSM items [{"posm_name": "Lux", "attached_posm": 2}, ...]
    """
    logger.info(f"[Worker {worker_id}] [{visit_id}] [POSM] Starting POSM analysis (posm_items={len(posm_items) if posm_items else 0})")
    try:
        t_start = time.perf_counter()

        # Run POSM detection
        conf = POSM_CONFIG.get('confidence', 0.30)
        logger.debug(f"[Worker {worker_id}] [{visit_id}] [POSM] Running detection with conf={conf}")
        t_ubl_detect = time.perf_counter()
        results = model_manager.predict(
            'posm',
            source=image_path,
            worker_id=worker_id,
            conf=conf,
            verbose=False
        )

        # Process UBL POSM detections
        detected_items = defaultdict(int)
        ubl_total_area = 0.0
        model_result = results[0] if results else None

        # Diagnostic logging for model results
        if not model_result:
            logger.warning(f"[Worker {worker_id}] [{visit_id}] [POSM] ⚠ Model returned no results object")
        elif not model_result.boxes:
            logger.warning(f"[Worker {worker_id}] [{visit_id}] [POSM] ⚠ Model returned results but no boxes detected (conf={conf})")
        else:
            raw_detection_count = len(model_result.boxes)
            logger.info(f"[Worker {worker_id}] [{visit_id}] [POSM] Model detected {raw_detection_count} boxes with conf>={conf}")

        if model_result and model_result.boxes:
            for box in model_result.boxes:
                cls_id = int(box.cls[0])
                class_name = model_result.names[cls_id]
                detected_items[class_name] += 1
                # Calculate bbox area
                coords = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = coords
                ubl_total_area += (x2 - x1) * (y2 - y1)

            logger.info(f"[Worker {worker_id}] [{visit_id}] [POSM] Detected items: {dict(detected_items)}")

        ubl_detection_ms = (time.perf_counter() - t_ubl_detect) * 1000

        # Run Competitor POSM detection
        comp_conf = SOVM_CONFIG.get('comp_confidence', 0.30)
        logger.debug(f"[Worker {worker_id}] [{visit_id}] [POSM] Running Competitor detection with conf={comp_conf}")
        t_comp_detect = time.perf_counter()
        comp_results = model_manager.predict(
            'posm_comp',
            source=image_path,
            worker_id=worker_id,
            conf=comp_conf,
            verbose=False
        )

        comp_detection_ms = (time.perf_counter() - t_comp_detect) * 1000

        # Process Competitor detections
        competitor_items = defaultdict(int)
        competitor_total_area = 0.0
        comp_model_result = comp_results[0] if comp_results else None
        competitor_standards = _load_competitor_posm_standards()

        if comp_model_result and comp_model_result.boxes:
            for box in comp_model_result.boxes:
                cls_id = int(box.cls[0])
                class_name = comp_model_result.names[cls_id]
                # Map to display name if available
                standard = competitor_standards.get(class_name, {})
                display_name = standard.get('name', class_name)
                competitor_items[display_name] += 1
                # Calculate bbox area
                coords = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = coords
                competitor_total_area += (x2 - x1) * (y2 - y1)
            logger.info(f"[Worker {worker_id}] [{visit_id}] [POSM] Competitor detected: {len(comp_model_result.boxes)} items: {dict(competitor_items)}")
        else:
            logger.info(f"[Worker {worker_id}] [{visit_id}] [POSM] Competitor: 0 detections")

        # Calculate UBL vs Competitor percentages
        ubl_count = sum(detected_items.values())
        competitor_count = sum(competitor_items.values())
        total_count = ubl_count + competitor_count
        total_area = ubl_total_area + competitor_total_area

        ubl_percentage_by_count = (ubl_count / total_count * 100) if total_count > 0 else 0
        competitor_percentage_by_count = (competitor_count / total_count * 100) if total_count > 0 else 0
        ubl_percentage_by_area = (ubl_total_area / total_area * 100) if total_area > 0 else 0
        competitor_percentage_by_area = (competitor_total_area / total_area * 100) if total_area > 0 else 0

        # Calculate compliance
        t_compliance = time.perf_counter()
        compliance_score = 0.0
        item_accuracy = []

        if POSM_AVAILABLE and calculate_posm_compliance:
            # Build planned_items from posm_items array
            planned_items = {}
            if posm_items:
                for item in posm_items:
                    posm_name = item.get("name")
                    attached_posm = item.get("attached_posm", 0)
                    if posm_name and attached_posm > 0:
                        planned_items[posm_name] = attached_posm
                        logger.info(f"[{visit_id}] [POSM] Setting planned: '{posm_name}' = {attached_posm}")

            compliance_score, item_accuracy = calculate_posm_compliance(
                dict(detected_items),
                planned_items=planned_items
            )

        compliance_ms = (time.perf_counter() - t_compliance) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000

        result = {
            "model_version": "POSM_YOLO11X + POSM_COMP",
            "confidence": conf,
            "total_posm": ubl_count,
            "unique_items": len(detected_items),
            "detected_items": dict(detected_items),
            "compliance_score": compliance_score,
            "item_accuracy": item_accuracy,
            # Competitor data
            "competitor_count": competitor_count,
            "competitor_items": dict(competitor_items),
            # Percentage breakdowns
            "ubl_percentage_by_count": round(ubl_percentage_by_count, 2),
            "competitor_percentage_by_count": round(competitor_percentage_by_count, 2),
            "ubl_percentage_by_area": round(ubl_percentage_by_area, 2),
            "competitor_percentage_by_area": round(competitor_percentage_by_area, 2),
            "timing": {
                "total_ms": round(total_ms, 1),
                "ubl_detection_ms": round(ubl_detection_ms, 1),
                "competitor_detection_ms": round(comp_detection_ms, 1),
                "compliance_ms": round(compliance_ms, 1)
            },
            "summary": f"Detected {ubl_count} UBL + {competitor_count} Competitor POSM with {compliance_score}% compliance"
        }
        logger.info(f"[Worker {worker_id}] [{visit_id}] [POSM] ✓ Analysis complete: {ubl_count} UBL + {competitor_count} Competitor items, {compliance_score}% compliance in {total_ms:.0f}ms")
        return result

    except Exception as e:
        logger.error(f"[Worker {worker_id}] [{visit_id}] [POSM] ❌ Error in analyze_posm: {e}", exc_info=True)
        return {
            "error": str(e),
            "summary": "Error processing POSM"
        }


def analyze_sovm(image_path: str, worker_id: int = 0, visit_id: str = "") -> dict:
    """Analyze SOVM (Share of Voice Measurement) - UBL vs Competitor POSM detection

    Similar to POSM but:
    - No posm_items parameter (passive observation)
    - Runs both posm and posm_comp models
    - Calculates UBL vs Competitor percentages by count and area
    - No compliance score (no input qty to compare)
    """
    logger.info(f"[Worker {worker_id}] [{visit_id}] [SOVM] Starting Share of Voice analysis")
    try:
        t_start = time.perf_counter()
        # Get config
        ubl_conf = SOVM_CONFIG.get('ubl_confidence', 0.30)
        comp_conf = SOVM_CONFIG.get('comp_confidence', 0.30)

        # Run UBL POSM detection
        logger.debug(f"[Worker {worker_id}] [{visit_id}] [SOVM] Running UBL POSM detection with conf={ubl_conf}")
        t_ubl = time.perf_counter()
        ubl_results = model_manager.predict(
            'posm',
            source=image_path,
            worker_id=worker_id,
            conf=ubl_conf,
            verbose=False
        )

        ubl_detection_ms = (time.perf_counter() - t_ubl) * 1000

        # Run Competitor POSM detection
        logger.debug(f"[Worker {worker_id}] [{visit_id}] [SOVM] Running Competitor POSM detection with conf={comp_conf}")
        t_comp = time.perf_counter()
        comp_results = model_manager.predict(
            'posm_comp',
            source=image_path,
            worker_id=worker_id,
            conf=comp_conf,
            verbose=False
        )

        comp_detection_ms = (time.perf_counter() - t_comp) * 1000

        # Process UBL detections
        ubl_items = defaultdict(int)
        ubl_total_area = 0.0
        ubl_model_result = ubl_results[0] if ubl_results else None

        if ubl_model_result and ubl_model_result.boxes:
            for box in ubl_model_result.boxes:
                cls_id = int(box.cls[0])
                class_name = ubl_model_result.names[cls_id]
                ubl_items[class_name] += 1
                # Calculate bbox area
                coords = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = coords
                ubl_total_area += (x2 - x1) * (y2 - y1)
            logger.info(f"[Worker {worker_id}] [{visit_id}] [SOVM] UBL POSM: {len(ubl_model_result.boxes)} detections: {dict(ubl_items)}")
        else:
            logger.info(f"[Worker {worker_id}] [{visit_id}] [SOVM] UBL POSM: 0 detections")

        # Process Competitor detections
        competitor_items = defaultdict(int)
        competitor_total_area = 0.0
        comp_model_result = comp_results[0] if comp_results else None
        competitor_standards = _load_competitor_posm_standards()

        if comp_model_result and comp_model_result.boxes:
            for box in comp_model_result.boxes:
                cls_id = int(box.cls[0])
                class_name = comp_model_result.names[cls_id]
                # Map to display name if available
                standard = competitor_standards.get(class_name, {})
                display_name = standard.get('name', class_name)
                competitor_items[display_name] += 1
                # Calculate bbox area
                coords = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = coords
                competitor_total_area += (x2 - x1) * (y2 - y1)
            logger.info(f"[Worker {worker_id}] [{visit_id}] [SOVM] Competitor POSM: {len(comp_model_result.boxes)} detections: {dict(competitor_items)}")
        else:
            logger.info(f"[Worker {worker_id}] [{visit_id}] [SOVM] Competitor POSM: 0 detections")

        # Calculate totals
        ubl_count = sum(ubl_items.values())
        competitor_count = sum(competitor_items.values())
        total_count = ubl_count + competitor_count
        total_area = ubl_total_area + competitor_total_area

        # Calculate percentages
        ubl_percentage_by_count = (ubl_count / total_count * 100) if total_count > 0 else 0
        competitor_percentage_by_count = (competitor_count / total_count * 100) if total_count > 0 else 0
        ubl_percentage_by_area = (ubl_total_area / total_area * 100) if total_area > 0 else 0
        competitor_percentage_by_area = (competitor_total_area / total_area * 100) if total_area > 0 else 0

        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOVM] UBL: {ubl_count} items ({ubl_percentage_by_count:.1f}% by count, {ubl_percentage_by_area:.1f}% by area)")
        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOVM] Competitor: {competitor_count} items ({competitor_percentage_by_count:.1f}% by count, {competitor_percentage_by_area:.1f}% by area)")

        total_ms = (time.perf_counter() - t_start) * 1000

        result = {
            "model_version": "POSM_YOLO11X + POSM_COMP",
            "ubl_confidence": ubl_conf,
            "comp_confidence": comp_conf,
            "ubl_count": ubl_count,
            "competitor_count": competitor_count,
            "ubl_percentage_by_count": round(ubl_percentage_by_count, 2),
            "competitor_percentage_by_count": round(competitor_percentage_by_count, 2),
            "ubl_percentage_by_area": round(ubl_percentage_by_area, 2),
            "competitor_percentage_by_area": round(competitor_percentage_by_area, 2),
            "ubl_items": dict(ubl_items),
            "competitor_items": dict(competitor_items),
            "timing": {
                "total_ms": round(total_ms, 1),
                "ubl_detection_ms": round(ubl_detection_ms, 1),
                "competitor_detection_ms": round(comp_detection_ms, 1)
            },
            "summary": f"SOVM: {ubl_count} UBL ({ubl_percentage_by_count:.1f}%) vs {competitor_count} Competitor ({competitor_percentage_by_count:.1f}%)"
        }
        logger.info(f"[Worker {worker_id}] [{visit_id}] [SOVM] ✓ Analysis complete in {total_ms:.0f}ms")
        return result

    except Exception as e:
        logger.error(f"[Worker {worker_id}] [{visit_id}] [SOVM] ❌ Error in analyze_sovm: {e}", exc_info=True)
        return {
            "error": str(e),
            "summary": "Error processing SOVM"
        }
