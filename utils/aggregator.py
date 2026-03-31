"""
Visit Result Aggregation
TODO-REFACTOR: REMOVE ENTIRE MODULE when backend ready
Future: Backend handles ALL aggregation via database
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

# Module-level cache for brand shelving norms
_BRAND_NORMS_CACHE = None
_CONFIG_CACHE = None
_COMPETITOR_POSM_CACHE = None


def _load_config():
    """Load main config.yaml (cached)"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        try:
            config_path = Path(__file__).parent.parent / "config" / "config.yaml"
            with open(config_path) as f:
                _CONFIG_CACHE = yaml.safe_load(f)
                logger.info("Loaded config.yaml")
        except Exception as e:
            logger.warning(f"Could not load config.yaml: {e}")
            _CONFIG_CACHE = {}
    return _CONFIG_CACHE


def _load_brand_norms():
    """Load SOS brand shelving norms from YAML (cached)"""
    global _BRAND_NORMS_CACHE
    if _BRAND_NORMS_CACHE is None:
        try:
            norm_path = Path(__file__).parent.parent / "config" / "standards" / "sos_brand_shelving_norm.yaml"
            with open(norm_path) as f:
                data = yaml.safe_load(f)
                _BRAND_NORMS_CACHE = data.get('brands', {})
                logger.info(f"Loaded {len(_BRAND_NORMS_CACHE)} brand shelving norms")
        except Exception as e:
            logger.warning(f"Could not load brand norms: {e}")
            _BRAND_NORMS_CACHE = {}
    return _BRAND_NORMS_CACHE


def _load_competitor_posm_standards():
    """Load competitor POSM standards from YAML (cached)"""
    global _COMPETITOR_POSM_CACHE
    if _COMPETITOR_POSM_CACHE is None:
        try:
            standards_path = Path(__file__).parent.parent / "config" / "standards" / "competitor_posm_standards.yaml"
            with open(standards_path) as f:
                data = yaml.safe_load(f)
                _COMPETITOR_POSM_CACHE = data.get('item_mappings', {})
                logger.info(f"Loaded {len(_COMPETITOR_POSM_CACHE)} competitor POSM standards")
        except Exception as e:
            logger.warning(f"Could not load competitor POSM standards: {e}")
            _COMPETITOR_POSM_CACHE = {}
    return _COMPETITOR_POSM_CACHE


_SACHET_STANDARDS_CACHE = None


def _load_sachet_standards():
    """Load sachet standards from YAML (cached)"""
    global _SACHET_STANDARDS_CACHE
    if _SACHET_STANDARDS_CACHE is None:
        try:
            standards_path = Path(__file__).parent.parent / "config" / "standards" / "sachet_standards.yaml"
            with open(standards_path) as f:
                data = yaml.safe_load(f)
                _SACHET_STANDARDS_CACHE = {
                    'product_mappings': data.get('product_mappings', {}),
                    'unilever_hangers': data.get('unilever_hangers', [])
                }
                logger.info(f"Loaded sachet standards with {len(_SACHET_STANDARDS_CACHE['unilever_hangers'])} UBL hangers")
        except Exception as e:
            logger.warning(f"Could not load sachet standards: {e}")
            _SACHET_STANDARDS_CACHE = {'product_mappings': {}, 'unilever_hangers': []}
    return _SACHET_STANDARDS_CACHE


class VisitResultAggregator:
    """
    Aggregates AI results per visit.

    When all images for a visit are processed, sends one combined message to SQS.

    TODO-REFACTOR: DELETE THIS ENTIRE CLASS when backend ready
    """

    def __init__(self):
        # Structure: {visit_id: {"results": {image_type: [result1, result2, ...]}, "metadata": {...}, "expected_count": N}}
        self.visits = defaultdict(lambda: {"results": defaultdict(list), "metadata": {}, "expected_count": 0, "processed_count": 0})
        self.visit_locks = defaultdict(threading.Lock)  # Per-visit locks for concurrent aggregation
        self.global_lock = threading.Lock()  # Only for dict structure modifications

    def add_result(self, visit_id: str, image_type: str, result: dict, metadata: dict, expected_count: int, is_retake: bool = False) -> Optional[dict]:
        """
        Add a result for a visit.

        Args:
            visit_id: Visit identifier
            image_type: Type of image (category_shelf_display, share_of_shelf, etc.)
            result: AI analysis result
            metadata: Visit metadata (shop_id, upload_id, s3_key, etc.)
            expected_count: Total number of images expected for this visit
            is_retake: Whether this is a retake (resets existing visit data)

        Returns:
            Aggregated result dict if visit is complete, None otherwise
        """
        # Get visit data and lock (fast global lock only for dict access)
        with self.global_lock:
            # If retake, clear existing data for this visit
            if is_retake and visit_id in self.visits:
                logger.info(f"[AGGREGATOR] Retake detected for visit {visit_id}, resetting aggregation")
                del self.visits[visit_id]
                del self.visit_locks[visit_id]
            
            visit_data = self.visits[visit_id]
            visit_lock = self.visit_locks[visit_id]

        # Use per-visit lock for all data operations (allows concurrent visits)
        with visit_lock:
            # Set expected count (should be same for all images in visit)
            if visit_data["expected_count"] == 0:
                visit_data["expected_count"] = expected_count
                logger.info(f"[AGGREGATOR] Visit {visit_id}: Expecting {expected_count} images")

            # Store visit-level metadata from first image
            if not visit_data["metadata"]:
                visit_data["metadata"] = {
                    "visit_id": visit_id,
                    "shop_id": metadata.get("shop_id"),
                    "outlet_id": metadata.get("shop_id"),  # Same as shop_id
                    "is_retake": is_retake,
                    "retake_count": metadata.get("retake_count", 0)
                }

            # Transform result to desired format
            transformed_result = self._transform_result(image_type, result, metadata, is_retake)

            # Add to results
            visit_data["results"][image_type].append(transformed_result)
            visit_data["processed_count"] += 1

            logger.info(f"[AGGREGATOR] Visit {visit_id}: {visit_data['processed_count']}/{visit_data['expected_count']} images processed")

            # Check if visit is complete
            if visit_data["processed_count"] >= visit_data["expected_count"]:
                logger.info(f"[AGGREGATOR] ✓✓✓ Visit {visit_id} is COMPLETE! Generating aggregated result...")
                aggregated = self._build_aggregated_result(visit_id)

                # Clean up memory (global lock for dict deletion)
                with self.global_lock:
                    del self.visits[visit_id]
                    del self.visit_locks[visit_id]

                return aggregated

            return None

    def _transform_result(self, image_type: str, ai_result: dict, metadata: dict, is_retake: bool = False) -> dict:
        """Transform AI result to API format"""
        retake_count = metadata.get("retake_count", 0)

        base = {
            "upload_id": metadata.get("upload_id"),
            "s3_key": metadata.get("s3_key"),
            "processing_status": "completed",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "retake_count": retake_count,
            "processing_time_ms": metadata.get("processing_time_ms"),
            "s3_download_ms": metadata.get("s3_download_ms"),
            "analyzer_timing": ai_result.get("timing")
        }

        if image_type == "category_shelf_display":
            slab = metadata.get("slab", "Unknown")
            planogram_adherence = ai_result.get("planogram_adherence", "No")

            # Get overall_compliance (already calculated with waivers in analyzer)
            overall_compliance = float(ai_result.get("overall_compliance", 0))

            # Get criteria_met from analyzer (per-planogram compliance rules)
            criteria_met = ai_result.get("criteria_met", False)

            # Load retake threshold from config
            config = _load_config()
            csd_threshold = config.get('retake_thresholds', {}).get('csd_overall_compliance', 80)

            # Retake based on criteria_met, not just overall_compliance
            retake_needed = "No" if criteria_met else "Yes"

            # Get totals
            totals = ai_result.get("totals", {})
            total_visible = int(totals.get("total_visible", 0))
            total_planned = int(totals.get("total_planned", 0))

            # Build shelftalker summary by class name
            shelftalkers_detected = ai_result.get("shelftalkers_detected", [])
            shelftalker_summary = {}
            for st in shelftalkers_detected:
                cls_name = st.get("class_name", "unknown")
                shelftalker_summary[cls_name] = shelftalker_summary.get(cls_name, 0) + 1

            return {
                **base,
                "display_name": slab,
                "status": "passed" if criteria_met else "failed",
                "overall_compliance": overall_compliance,
                "criteria_met": criteria_met,
                "Retake": retake_needed,
                "planogram_adherence": planogram_adherence,
                "exclusively": ai_result.get("exclusively", "NA"),
                "variant_compliance": float(ai_result.get('variant_compliance', 0)),
                "shelf_talker_present": ai_result.get("shelf_talker_present", "No"),
                "shelf_talker_orientation_correct": ai_result.get("shelf_talker_orientation_correct", "No"),
                "shelftalker_waived": ai_result.get("shelftalker_waived", False),
                "shelftalker_count": len(shelftalkers_detected),
                "shelftalker_details": shelftalker_summary,  # {class_name: count}
                "products": [
                    {
                        "sku_name": p["sku_name"],
                        "planned_qty": int(p["planned_qty"]),
                        "visible_qty": int(p["visible_qty"]),
                        "accuracy": int(p['accuracy']),
                        "waived": p.get("waived", False)
                    }
                    for p in ai_result.get("products", [])
                ],
                "totals": {
                    "total_planned": total_planned,
                    "total_visible": total_visible
                },
                "adjacency": ai_result.get("adjacency")
            }

        elif image_type == "share_of_shelf":
            # TODO-REFACTOR: This transform will move to backend when backend ready
            # Future: Backend receives raw category_breakdown and aggregates across images in DB

            from collections import defaultdict
            from config.loader import BRAND_NORMS

            category_breakdown = ai_result.get("category_breakdown", {})
            competitor_breakdown = ai_result.get("competitor_product_breakdown", {})

            # Filter by sub_category if provided in metadata
            sub_category = metadata.get("sub_category")
            if sub_category:
                category_breakdown = {sub_category: category_breakdown.get(sub_category, {})}

            # Return dict of categories (not single object)
            results_by_category = {}

            for category, products in category_breakdown.items():
                if not products:  # Skip empty categories
                    continue

                # category_breakdown already keyed by brand (no extraction needed)
                total_visible = sum(products.values())
                competitor_count_in_category = sum(
                    count for brand_name, count in products.items()
                    if brand_name in competitor_breakdown
                )

                results_by_category[category] = {
                    **base,
                    "category_name": category.replace('_', ' ').title(),
                    "total_visible": total_visible,
                    "competitor_count": competitor_count_in_category,
                    "results": {
                        "brands": [
                            {
                                "company_name": "Unilever Bangladesh Limited"
                                    if BRAND_NORMS.get(brand_key, {}).get('is_ubl') == 'yes'
                                    else "Competitor",
                                "brand": BRAND_NORMS.get(brand_key, {}).get('display_name', brand_key),
                                "brand_key": brand_key,  # raw cls key for norm lookup in finalization
                                "visible_qty": count,
                                "shelving_norm": "N/A"  # Filled later in aggregation
                            }
                            for brand_key, count in products.items()
                        ]
                    }
                }

            return results_by_category  # Dict[str, Any] instead of single dict

        elif image_type == "share_of_sachet":
            from utils.sachet_compliance import sachet_compliance
            from collections import defaultdict

            # Get raw adherence data (dicts, not formatted strings)
            orientation_data = ai_result.get("orientation_adherence_details", {})
            slot_data = ai_result.get("slot_adherence_details", {})

            # Build sets of rotated and misplaced class names for quick lookup
            rotated_classes = set()
            for item in orientation_data.get("rotated_sachets", []):
                rotated_classes.add(item.get("class", ""))

            # Count misplaced sachets per base class (not just track presence)
            misplaced_counts = defaultdict(int)
            for item in slot_data.get("misplaced_sachets", []):
                # Store base class name (strip rotation suffix)
                sachet_class = item.get("sachet", "")
                base_class = sachet_class.replace('_rotate', '').replace('_rot', '')
                misplaced_counts[base_class] += 1

            # Group by mapped product name (combine rotation variants)
            product_groups = defaultdict(lambda: {"ai_classes": [], "total_qty": 0})
            for ai_class_name, count in ai_result.get("product_breakdown", {}).items():
                # Skip hangers
                if sachet_compliance.is_hanger(ai_class_name):
                    continue

                mapped_name = sachet_compliance.map_ai_product_to_standard(ai_class_name)
                product_groups[mapped_name]["ai_classes"].append(ai_class_name)
                product_groups[mapped_name]["total_qty"] += count

            # Build sachets list with per-product adherence
            sachets_list = []
            for mapped_name, group_data in product_groups.items():
                ai_classes = group_data["ai_classes"]
                # Use first AI class for category/company lookup
                primary_class = ai_classes[0]
                company_name = sachet_compliance.get_company_name(primary_class)

                # Calculate per-product orientation adherence
                has_rotation = any(cls in rotated_classes for cls in ai_classes)
                orientation_adh = "No" if has_rotation else "Yes"

                # Calculate per-product slot adherence based on placement percentage
                base_classes = [cls.replace('_rotate', '').replace('_rot', '') for cls in ai_classes]
                
                # Count total misplaced for this product
                total_misplaced = sum(misplaced_counts.get(base_cls, 0) for base_cls in base_classes)
                total_visible = group_data["total_qty"]
                correctly_placed = total_visible - total_misplaced
                
                # Calculate placement percentage
                placement_percentage = (correctly_placed / total_visible * 100) if total_visible > 0 else 0

                # Check if ANY hanger was detected in the image
                has_hanger_detected = ai_result.get("combined_hanger", False) or ai_result.get("brand_exclusive_hanger", False)

                # Check if product has hanger mapping (N/A if no mapping like Clinic Plus)
                has_hanger_mapping = any(
                    sachet_compliance.sachet_to_hanger_mapping.get(base_cls)
                    for base_cls in base_classes
                )

                if not has_hanger_detected:
                    # No hanger in image → N/A regardless of mapping
                    slot_adh = "N/A"
                elif not has_hanger_mapping:
                    # Sachet has no hanger mapping in config (e.g., Clinic Plus) → N/A
                    slot_adh = "N/A"
                else:
                    # Hanger detected and sachet has mapping → check placement %
                    config = _load_config()
                    threshold = config.get('sachet', {}).get('slot_adherence_threshold', 80)
                    # Use configured threshold: >= threshold% correctly placed = "Yes"
                    slot_adh = "Yes" if placement_percentage >= threshold else "No"

                sachets_list.append({
                    "company_name": company_name,
                    "sachet_name": mapped_name,
                    "ai_class_name": primary_class,  # For category lookup
                    "visible_qty": group_data["total_qty"],
                    "orientation_adherence": orientation_adh,
                    "slot_adherence": slot_adh
                })

            # Extract hangers separately for SOVM aggregation
            hangers_list = []
            for ai_class_name, count in ai_result.get("product_breakdown", {}).items():
                if sachet_compliance.is_hanger(ai_class_name):
                    mapped_name = sachet_compliance.map_ai_product_to_standard(ai_class_name)
                    company_name = sachet_compliance.get_company_name(ai_class_name)
                    hangers_list.append({
                        "company_name": company_name,
                        "hanger_name": mapped_name,
                        "ai_class_name": ai_class_name,
                        "visible_qty": count
                    })

            return {
                **base,
                "combined_sachet_hanger": "Yes" if ai_result.get("combined_hanger", False) else "No",
                "brand_exclusive_hanger": "Yes" if ai_result.get("brand_exclusive_hanger", False) else "No",
                "Retake": "No",
                "results": {
                    "sachets": sachets_list,
                    "hangers": hangers_list  # Include hangers for SOVM aggregation
                }
            }

        elif image_type == "share_of_posm":
            # Load retake threshold
            config = _load_config()
            posm_threshold = config.get('retake_thresholds', {}).get('posm_accuracy', 60)

            compliance_score = ai_result.get('compliance_score', 0)
            retake_needed = "Yes" if compliance_score < posm_threshold else "No"

            return {
                **base,
                "ubl_posm_accuracy": compliance_score,
                "Retake": retake_needed,
                "results": {
                    "posm_items": [
                        {
                            "company": "Unilever Bangladesh Limited",
                            "material_name": item.get("name", "Unknown"),
                            "ai_class_name": item.get("class_name", ""),  # Add AI class name for category mapping
                            "input_qty": item.get("planned", 0),
                            "visible_qty": item.get("visible", 0),
                            "accuracy": f"{item.get('accuracy', 0)}%"
                        }
                        for item in ai_result.get("item_accuracy", [])
                    ]
                }
            }

        elif image_type == "sovm":
            # SOVM - Share of Voice Measurement (POSM vs Competitor without input qty)
            config = _load_config()
            sovm_enabled = config.get('retake_thresholds', {}).get('sovm_enabled', False)
            if sovm_enabled:
                sovm_threshold = config.get('retake_thresholds', {}).get('sovm_ubl_percentage', 60)
                ubl_pct = ai_result.get('ubl_percentage_by_count', 0)
                retake_needed = "Yes" if ubl_pct < sovm_threshold else "No"
            else:
                retake_needed = "No"

            # Load competitor standards for company mapping
            competitor_standards = _load_competitor_posm_standards()

            # Build UBL items list
            ubl_items_list = []
            for item_name, count in ai_result.get('ubl_items', {}).items():
                ubl_items_list.append({
                    "company": "Unilever Bangladesh Limited",
                    "material_name": item_name,
                    "visible_qty": count
                })

            # Build competitor items list
            competitor_items_list = []
            for item_name, count in ai_result.get('competitor_items', {}).items():
                # Try to get company from standards
                company = "Competitor"
                for class_name, standard in competitor_standards.items():
                    if standard.get('name') == item_name:
                        company = standard.get('company', 'Competitor')
                        break
                competitor_items_list.append({
                    "company": company,
                    "material_name": item_name,
                    "visible_qty": count
                })

            return {
                **base,
                "ubl_count": ai_result.get('ubl_count', 0),
                "competitor_count": ai_result.get('competitor_count', 0),
                "ubl_percentage_by_count": ai_result.get('ubl_percentage_by_count', 0),
                "competitor_percentage_by_count": ai_result.get('competitor_percentage_by_count', 0),
                "ubl_percentage_by_area": ai_result.get('ubl_percentage_by_area', 0),
                "competitor_percentage_by_area": ai_result.get('competitor_percentage_by_area', 0),
                "Retake": retake_needed,
                "results": {
                    "ubl_items": ubl_items_list,
                    "competitor_items": competitor_items_list
                }
            }

        else:
            # Fallback for unknown types
            return {**base, "raw_results": ai_result}

    def _build_aggregated_result(self, visit_id: str) -> dict:
        """Build the final aggregated result for a visit"""
        visit_data = self.visits[visit_id]
        metadata = visit_data["metadata"]
        results = visit_data["results"]
        
        # Extract retake info for header
        is_retake = metadata.get("is_retake", False)
        retake_count = metadata.get("retake_count", 0)

        # TODO-REFACTOR: Remove this entire aggregation logic when backend ready
        # Future: Backend receives per-image results and aggregates in DB after all images processed

        # Transform results to match ai_summary.json format
        aggregated_results = {}

        # Convert category_shelf_display list to numbered dict
        if "category_shelf_display" in results:
            aggregated_results["category_shelf_display"] = {
                str(i+1): item for i, item in enumerate(results["category_shelf_display"])
            }

        # Aggregate share_of_shelf by category
        if "share_of_shelf" in results:
            aggregated_by_category = defaultdict(lambda: {
                "brand_details": {},
                "total_visible": 0,
                "competitor_count": 0,
                "image_count": 0
            })

            # Each result is dict of categories
            for per_image_result in results["share_of_shelf"]:
                for category, cat_data in per_image_result.items():
                    agg = aggregated_by_category[category]
                    agg["image_count"] += 1
                    agg["total_visible"] += cat_data.get("total_visible", 0)
                    agg["competitor_count"] += cat_data.get("competitor_count", 0)

                    # Merge brand details (keyed by upload_id)
                    upload_id = cat_data.get("upload_id")
                    if upload_id:
                        agg["brand_details"][upload_id] = cat_data

            # Build final structure matching ai_summary.json format
            overall_summary = []
            flat_brand_details = {}
            brand_counter = 1

            for category, agg in aggregated_by_category.items():
                ubl_count = agg["total_visible"]
                comp_count = agg["competitor_count"]
                total = ubl_count + comp_count

                ubl_pct = (ubl_count / total * 100) if total > 0 else 0
                comp_pct = (comp_count / total * 100) if total > 0 else 0

                # Add to overall_summary
                overall_summary.append({
                    "category_name": category.replace('_', ' ').title(),
                    "total_visible": ubl_count,
                    "share_percentage": {
                        "ubl": round(ubl_pct, 2),
                        "competitor": round(comp_pct, 2)
                    }
                })

                # Flatten brand_details with category_name field
                # Load brand norms for min_qty and shelving_norm calculation
                brand_norms = _load_brand_norms()

                for upload_id, brand_data in agg["brand_details"].items():
                    # Extract brands from nested results
                    for brand_item in brand_data.get("results", {}).get("brands", []):
                        brand_name = brand_item.get("brand", "")       # display name
                        brand_key = brand_item.get("brand_key", brand_name)  # raw cls key
                        visible_qty = brand_item.get("visible_qty", 0)

                        # Lookup brand norm (min_qty and is_ubl) — flat dict keyed by cls class name
                        brand_norm = brand_norms.get(brand_key)

                        if brand_norm:
                            min_qty = brand_norm.get('min_qty')
                            is_ubl = brand_norm.get('is_ubl')
                        else:
                            min_qty = None
                            is_ubl = 'no'  # Default to competitor if not in config

                        # Calculate shelving_norm (only for UBL brands)
                        if is_ubl == 'yes' and min_qty is not None:
                            shelving_norm = "Yes" if visible_qty >= min_qty else "No"
                            min_qty_str = str(min_qty)
                        else:
                            # Competitor brands get N/A for shelving norms
                            shelving_norm = "N/A"
                            min_qty_str = "N/A"

                        flat_brand_details[str(brand_counter)] = {
                            "upload_id": upload_id,
                            "category_name": category.replace('_', ' ').title(),
                            "company_name": brand_item.get("company_name", "Unilever Bangladesh Limited"),
                            "brand": brand_name,
                            "min_qty": min_qty_str,
                            "visible_qty": visible_qty,
                            "shelving_norm": shelving_norm
                        }
                        brand_counter += 1

            # Add Retake field to each brand_detail based on category UBL percentage
            config = _load_config()
            sos_threshold = config.get('retake_thresholds', {}).get('sos_ubl_percentage', 60)

            for brand_key, brand in flat_brand_details.items():
                category_name = brand.get("category_name")
                # Find this category in overall_summary
                for summary in overall_summary:
                    if summary["category_name"] == category_name:
                        ubl_pct = summary["share_percentage"]["ubl"]
                        brand["Retake"] = "Yes" if ubl_pct < sos_threshold else "No"
                        break

            aggregated_results["share_of_shelf"] = {
                "overall_summary": overall_summary,
                "brand_details": flat_brand_details
            }

        # Aggregate share_of_posm
        if "share_of_posm" in results:
            from utils.posm_compliance import get_posm_category, get_category_display_name

            posm_materials = {}
            material_counter = 1
            total_accuracy = 0
            accuracy_count = 0
            category_counts = defaultdict(int)  # Changed from type_counts to category_counts
            total_posm_count = 0

            for posm_result in results["share_of_posm"]:
                for item in posm_result.get("results", {}).get("posm_items", []):
                    material_name = item.get("material_name", "")
                    ai_class_name = item.get("ai_class_name", "")
                    visible_qty = item.get("visible_qty", 0)

                    # Get category first (used for both detailed materials and aggregation)
                    category = get_posm_category(ai_class_name or material_name)

                    # Store in detailed materials dict (with type/category instead of company)
                    posm_materials[str(material_counter)] = {
                        "upload_id": posm_result.get("upload_id", ""),
                        "type": get_category_display_name(category),  # Show category display name (e.g., "Hair Care")
                        "material_name": material_name,
                        "input_qty": item.get("input_qty", 0),
                        "visible_qty": visible_qty,
                        "accuracy": int(float(str(item.get("accuracy", "0")).rstrip('%')))
                    }
                    material_counter += 1

                    # Aggregate by category (not individual items)
                    category_counts[category] += visible_qty
                    total_posm_count += visible_qty

                    try:
                        acc = float(str(item.get("accuracy", "0")).rstrip('%'))
                        total_accuracy += acc
                        accuracy_count += 1
                    except:
                        pass

            avg_accuracy = int(total_accuracy / accuracy_count) if accuracy_count > 0 else 0

            # Build overall_summary: aggregate by company (UBL + Competitor)
            ubl_total_count = sum(category_counts.values())
            competitor_count = 0  # TODO: Detect competitor POSM in future
            grand_total = ubl_total_count + competitor_count

            overall_summary = []
            if ubl_total_count > 0:
                ubl_percentage = (ubl_total_count / grand_total * 100) if grand_total > 0 else 0
                overall_summary.append({
                    "company": "Unilever Bangladesh Limited",
                    "present_count": ubl_total_count,
                    "posm_by_count_percentage": round(ubl_percentage, 2),
                    "posm_by_surface_area_percentage": 0.0  # TODO: Calculate from bounding boxes
                })

            # Always include competitor entry (even if 0)
            competitor_percentage = (competitor_count / grand_total * 100) if grand_total > 0 else 0
            overall_summary.append({
                "company": "Competitor",
                "present_count": competitor_count,
                "posm_by_count_percentage": round(competitor_percentage, 2),
                "posm_by_surface_area_percentage": 0.0
            })

            # Add Retake field to detailed_analysis based on accuracy threshold
            config = _load_config()
            posm_threshold = config.get('retake_thresholds', {}).get('posm_accuracy', 60)
            posm_retake = "Yes" if avg_accuracy < posm_threshold else "No"

            aggregated_results["share_of_posm"] = {
                "overall_summary": overall_summary,
                "detailed_analysis": {
                    "ubl_posm_ai_accuracy": avg_accuracy,
                    "Retake": posm_retake,
                    "materials": posm_materials
                }
            }

        # Aggregate share_of_sachet
        if "share_of_sachet" in results:
            from utils.sachet_compliance import get_sachet_category, get_category_display_name

            sachet_items = {}
            sachet_counter = 1
            combined_hanger = "No"
            exclusive_hanger = "No"
            category_counts = defaultdict(lambda: {"ubl": 0, "competitor": 0})

            for sachet_result in results["share_of_sachet"]:
                if sachet_result.get("combined_sachet_hanger") == "Yes":
                    combined_hanger = "Yes"
                if sachet_result.get("brand_exclusive_hanger") == "Yes":
                    exclusive_hanger = "Yes"

                for item in sachet_result.get("results", {}).get("sachets", []):
                    sachet_name = item.get("sachet_name", "")
                    ai_class_name = item.get("ai_class_name", "")
                    visible_qty = item.get("visible_qty", 0)
                    company = item.get("company_name", "Unilever Bangladesh Limited")

                    # Debug logging
                    logger.info(f"[AGGREGATOR] Adding sachet: {sachet_name} from upload_id={sachet_result.get('upload_id')}")

                    # Determine category from AI class name (fallback to sachet_name)
                    category = get_sachet_category(ai_class_name or sachet_name)

                    # Aggregate by category (UBL vs competitor)
                    if "Unilever" in company:
                        category_counts[category]["ubl"] += visible_qty
                    else:
                        category_counts[category]["competitor"] += visible_qty

                    sachet_items[str(sachet_counter)] = {
                        "upload_id": sachet_result.get("upload_id", ""),
                        "company_name": company,
                        "sachet_name": sachet_name,
                        "visible_qty": visible_qty,
                        "orientation_adherence": item.get("orientation_adherence", "No"),
                        "slot_adherence": item.get("slot_adherence", "NA")
                    }
                    sachet_counter += 1

            # Build summary_table by category
            summary_table = []
            for category, counts in category_counts.items():
                total = counts["ubl"] + counts["competitor"]
                ubl_pct = (counts["ubl"] / total * 100) if total > 0 else 0
                comp_pct = (counts["competitor"] / total * 100) if total > 0 else 0

                summary_table.append({
                    "category": get_category_display_name(category),
                    "ubl_percentage": round(ubl_pct, 2),
                    "competitor_percentage": round(comp_pct, 2)
                })

            aggregated_results["share_of_sachet"] = {
                "summary_table": summary_table,
                "detailed_hanger_analysis": {
                    "combined_sachet_hanger_info": combined_hanger,
                    "brand_exclusive_hanger_info": exclusive_hanger,
                    "sachets": sachet_items
                }
            }

        # Aggregate sovm (SOVM - Share of Voice Measurement)
        if "sovm" in results:
            # Aggregate across multiple images
            total_ubl_count = 0
            total_competitor_count = 0
            ubl_items_merged = defaultdict(int)
            competitor_items_merged = defaultdict(int)
            avg_ubl_pct_by_count = 0
            avg_comp_pct_by_count = 0
            avg_ubl_pct_by_area = 0
            avg_comp_pct_by_area = 0
            image_count = 0

            for sovm_result in results["sovm"]:
                total_ubl_count += sovm_result.get("ubl_count", 0)
                total_competitor_count += sovm_result.get("competitor_count", 0)
                avg_ubl_pct_by_count += sovm_result.get("ubl_percentage_by_count", 0)
                avg_comp_pct_by_count += sovm_result.get("competitor_percentage_by_count", 0)
                avg_ubl_pct_by_area += sovm_result.get("ubl_percentage_by_area", 0)
                avg_comp_pct_by_area += sovm_result.get("competitor_percentage_by_area", 0)
                image_count += 1

                # Merge items
                for item in sovm_result.get("results", {}).get("ubl_items", []):
                    ubl_items_merged[item.get("material_name", "")] += item.get("visible_qty", 0)
                for item in sovm_result.get("results", {}).get("competitor_items", []):
                    competitor_items_merged[item.get("material_name", "")] += item.get("visible_qty", 0)

            # Include sachet hangers in SOVM (if sachet task present and hangers detected)
            if "share_of_sachet" in results:
                for sachet_result in results["share_of_sachet"]:
                    # Get hangers from the new hangers field
                    for hanger_item in sachet_result.get("results", {}).get("hangers", []):
                        hanger_name = hanger_item.get("hanger_name", "")
                        visible_qty = hanger_item.get("visible_qty", 0)
                        company = hanger_item.get("company_name", "")

                        if "Unilever" in company:
                            # UBL hanger - add to SOVM UBL items
                            ubl_items_merged[hanger_name] += visible_qty
                            total_ubl_count += visible_qty
                            logger.info(f"[SOVM] Added UBL sachet hanger to SOVM: {hanger_name} x{visible_qty}")
                        else:
                            # Competitor hanger - add to competitor items
                            competitor_items_merged[hanger_name] += visible_qty
                            total_competitor_count += visible_qty
                            logger.info(f"[SOVM] Added competitor sachet hanger to SOVM: {hanger_name} x{visible_qty}")

            # Calculate averages for area (not affected by sachet hangers)
            if image_count > 0:
                avg_ubl_pct_by_area /= image_count
                avg_comp_pct_by_area /= image_count

            # Recalculate count percentages after including sachet hangers
            grand_total = total_ubl_count + total_competitor_count
            final_ubl_pct_by_count = (total_ubl_count / grand_total * 100) if grand_total > 0 else 0
            final_comp_pct_by_count = (total_competitor_count / grand_total * 100) if grand_total > 0 else 0

            # Build overall_summary
            overall_summary = [
                {
                    "company": "Unilever Bangladesh Limited",
                    "present_count": total_ubl_count,
                    "posm_by_count_percentage": round(final_ubl_pct_by_count, 2),
                    "posm_by_surface_area_percentage": round(avg_ubl_pct_by_area, 2)
                },
                {
                    "company": "Competitor",
                    "present_count": total_competitor_count,
                    "posm_by_count_percentage": round(final_comp_pct_by_count, 2),
                    "posm_by_surface_area_percentage": round(avg_comp_pct_by_area, 2)
                }
            ]

            # Build detailed materials
            sovm_materials = {}
            material_counter = 1
            for item_name, count in ubl_items_merged.items():
                sovm_materials[str(material_counter)] = {
                    "company": "Unilever Bangladesh Limited",
                    "material_name": item_name,
                    "visible_qty": count
                }
                material_counter += 1
            for item_name, count in competitor_items_merged.items():
                # Get company from standards
                competitor_standards = _load_competitor_posm_standards()
                company = "Competitor"
                for class_name, standard in competitor_standards.items():
                    if standard.get('name') == item_name:
                        company = standard.get('company', 'Competitor')
                        break
                sovm_materials[str(material_counter)] = {
                    "company": company,
                    "material_name": item_name,
                    "visible_qty": count
                }
                material_counter += 1

            # Retake logic (check if enabled in config)
            config = _load_config()
            sovm_enabled = config.get('retake_thresholds', {}).get('sovm_enabled', False)
            if sovm_enabled:
                sovm_threshold = config.get('retake_thresholds', {}).get('sovm_ubl_percentage', 60)
                sovm_retake = "Yes" if final_ubl_pct_by_count < sovm_threshold else "No"
            else:
                sovm_retake = "No"

            aggregated_results["sovm"] = {
                "overall_summary": overall_summary,
                "detailed_analysis": {
                    "ubl_percentage_by_count": round(final_ubl_pct_by_count, 2),
                    "ubl_percentage_by_area": round(avg_ubl_pct_by_area, 2),
                    "Retake": sovm_retake,
                    "materials": sovm_materials
                }
            }

        # Task types matching ai_summary.json enum
        task_types = []
        if "category_shelf_display" in aggregated_results:
            task_types.append("CATEGORY SHELF DISPLAY")
        if "share_of_shelf" in aggregated_results:
            task_types.append("SOS")
        if "share_of_posm" in aggregated_results:
            task_types.append("POSM")
        if "sovm" in aggregated_results:
            task_types.append("SOVM")
        if "share_of_sachet" in aggregated_results:
            task_types.append("SACHET")

        # Calculate store compliance (Pass/Fail format)
        config = _load_config()
        total_compliance_threshold = config.get("store_compliance", {}).get("total_compliance_pass", 80)

        store_compliance = {}

        # CSD compliance: avg of per-image scores (100 if all passed, else partial)
        if "category_shelf_display" in aggregated_results:
            csd_items = list(aggregated_results["category_shelf_display"].values())
            if csd_items:
                csd_scores = [100 if item.get("criteria_met", False) else 0 for item in csd_items]
                csd_compliance = sum(csd_scores) / len(csd_scores)
                store_compliance["CSD"] = csd_compliance
                logger.info(f"[STORE] CSD: {sum(1 for s in csd_scores if s == 100)}/{len(csd_items)} passed = {csd_compliance}%")

        # SOS compliance: raw avg UBL%
        if "share_of_shelf" in aggregated_results:
            sos_values = [cat["share_percentage"]["ubl"]
                          for cat in aggregated_results["share_of_shelf"]["overall_summary"]]
            if sos_values:
                avg_sos = sum(sos_values) / len(sos_values)
                store_compliance["SOS"] = round(avg_sos, 2)
                logger.info(f"[STORE] SOS: {avg_sos:.1f}%")

        # Sachet compliance: raw avg UBL%
        if "share_of_sachet" in aggregated_results:
            sachet_values = [cat["ubl_percentage"]
                             for cat in aggregated_results["share_of_sachet"]["summary_table"]]
            if sachet_values:
                avg_sachet = sum(sachet_values) / len(sachet_values)
                store_compliance["Sachet"] = round(avg_sachet, 2)
                logger.info(f"[STORE] Sachet: {avg_sachet:.1f}%")

        # POSM compliance: raw accuracy
        if "share_of_posm" in aggregated_results:
            posm_accuracy = aggregated_results["share_of_posm"]["detailed_analysis"].get("ubl_posm_ai_accuracy", 0)
            store_compliance["POSM"] = posm_accuracy
            logger.info(f"[STORE] POSM: {posm_accuracy}%")

        # SOVM compliance: raw UBL%
        elif "sovm" in aggregated_results:
            sovm_ubl_pct = aggregated_results["sovm"]["detailed_analysis"].get("ubl_percentage_by_count", 0)
            store_compliance["SOVM"] = round(sovm_ubl_pct, 2)
            logger.info(f"[STORE] SOVM: {sovm_ubl_pct:.1f}%")

        # Calculate Total_Compliance and Status
        if store_compliance:
            compliance_values = [v for v in store_compliance.values() if isinstance(v, (int, float))]
            if compliance_values:
                total_compliance = sum(compliance_values) / len(compliance_values)
                store_compliance["Total_Compliance"] = round(total_compliance, 2)

            # CSD == 100 → auto-pass; otherwise use total_compliance threshold
            csd_value = store_compliance.get("CSD")
            if csd_value is not None:
                passed = csd_value == 100
            else:
                passed = store_compliance.get("Total_Compliance", 0) >= total_compliance_threshold

            store_compliance["Status"] = "Success" if passed else "Failed"
            logger.info(f"[STORE] Final: {store_compliance}")

        # Reorder results with store_compliance first
        final_results = {}
        if store_compliance:
            final_results["store_compliance"] = store_compliance
        final_results.update(aggregated_results)

        # Sum processing times across all images
        total_ai_ms = 0
        total_s3_ms = 0
        for result_list in results.values():
            for r in result_list if not isinstance(result_list, dict) else [result_list]:
                if isinstance(r, dict):
                    total_ai_ms += r.get("processing_time_ms") or 0
                    total_s3_ms += r.get("s3_download_ms") or 0

        # For retakes, include upload_id in header so backend can find the result to replace
        header = {
            "visit_id": visit_id,
            "outlet_code": metadata.get("shop_id"),
            "task": ", ".join(task_types) if task_types else "UNKNOWN",
            "is_retake": is_retake,
            "total_ai_processing_time_ms": round(total_ai_ms, 1),
            "total_s3_download_time_ms": round(total_s3_ms, 1)
        }
        
        # Add upload_id to header for retakes (critical for backend update matching)
        if is_retake:
            # Get upload_id from the first result (all retakes for same visit should have same upload_id)
            for result_list in results.values():
                if result_list and len(result_list) > 0:
                    upload_id = result_list[0].get("upload_id")
                    if upload_id:
                        header["upload_id"] = upload_id
                        logger.info(f"[AGGREGATOR] Retake header includes upload_id: {upload_id}")
                        break

        return {
            "ai_summary": {
                "header": header,
                "results": final_results
            }
        }

    def _calculate_overall_status(self, results: dict) -> dict:
        """Calculate overall visit status from all results"""
        # Check category_shelf_display results for pass/fail
        category_results = results.get("category_shelf_display", [])

        all_passed = True
        for result in category_results:
            status = result.get("status", "failed")
            if status != "passed":
                all_passed = False
                break

        return {
            "status": "Passed" if all_passed else "Failed",
            "needs_review": not all_passed
        }
