"""
QPDS (Quality Product Display Standards) Compliance Calculator

Compares AI detections against planned QPDS quantities and calculates compliance scores.
Supports per-planogram compliance rules and product waivers.
"""

import yaml
import os
import logging
from typing import Dict, List, Tuple, Optional, Set
from pathlib import Path

logger = logging.getLogger(__name__)

# Module-level cache for waivers
_WAIVERS_CACHE = None


def _load_waivers() -> Set[str]:
    """Load waived products from config (cached)"""
    global _WAIVERS_CACHE
    if _WAIVERS_CACHE is None:
        try:
            waiver_path = Path(__file__).parent.parent / "config" / "waivers.yaml"
            if waiver_path.exists():
                with open(waiver_path) as f:
                    data = yaml.safe_load(f)
                    _WAIVERS_CACHE = set()
                    for waiver in data.get('waivers', []):
                        if waiver.get('enabled', False):
                            _WAIVERS_CACHE.add(waiver.get('product', ''))
                    logger.info(f"Loaded {len(_WAIVERS_CACHE)} active product waivers")
            else:
                _WAIVERS_CACHE = set()
        except Exception as e:
            logger.warning(f"Could not load waivers: {e}")
            _WAIVERS_CACHE = set()
    return _WAIVERS_CACHE


class QPDSCompliance:
    """Calculate variant compliance scores based on QPDS standards"""

    def __init__(self, qpds_file: str = None):
        """Load QPDS standards from YAML file"""
        if qpds_file is None:
            # Default to qpds_standards.yaml in the project root
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            qpds_file = os.path.join(project_root, "config/standards/qpds_standards.yaml")
        self.qpds_file = qpds_file
        self.standards = {}
        self.product_mappings = {}
        self.shelf_categories = {}
        self.adjacency_rules = {}
        self._load_standards()
        self.waived_products = _load_waivers()

    def _load_standards(self):
        """Load QPDS standards from YAML file"""
        try:
            with open(self.qpds_file, 'r') as f:
                data = yaml.safe_load(f)
                self.standards = data.get('shelf_types', {})
                self.product_mappings = data.get('product_mappings', {})
                self.shelf_categories = data.get('shelf_categories', {})
                self.adjacency_rules = data.get('adjacency_rules', {})
        except Exception as e:
            logger.warning(f"Could not load QPDS standards: {e}")
            self.standards = {}
            self.product_mappings = {}
            self.shelf_categories = {}
            self.adjacency_rules = {}

    def map_ai_product_to_qpds(self, ai_product_name: str) -> str:
        """Map AI detection class name to QPDS product name"""
        # Try direct mapping first (includes composite keys like class_name:size_variant)
        if ai_product_name in self.product_mappings:
            return self.product_mappings[ai_product_name]

        # Fallback: strip size suffix for single-variant products
        if ':' in ai_product_name:
            base = ai_product_name.split(':')[0]
            if base in self.product_mappings:
                return self.product_mappings[base]

        # If no mapping found, return original name
        return ai_product_name

    def get_shelf_category(self, shelf_type: str) -> str:
        """Get category for a shelf type"""
        return self.shelf_categories.get(shelf_type, "General")

    def is_product_waived(self, product_name: str) -> bool:
        """Check if a product is waived from compliance"""
        return product_name in self.waived_products

    def get_compliance_rules(self, shelf_type: str) -> Dict:
        """
        Get compliance rules for a shelf type.

        Returns dict with:
        - overall_threshold: float or None
        - variant_threshold: float or None
        - planogram_affects_success: bool
        - shelftalker_affects_success: bool
        - exclusivity_affects_success: bool
        - adjacency_affects_success: bool
        """
        if shelf_type not in self.standards:
            # Default rules if shelf type not found
            return {
                'overall_threshold': 80.0,
                'variant_threshold': None,
                'planogram_affects_success': False,
                'shelftalker_affects_success': False,
                'exclusivity_affects_success': False,
                'adjacency_affects_success': False
            }

        shelf_data = self.standards[shelf_type]
        if isinstance(shelf_data, dict) and 'compliance_rules' in shelf_data:
            return shelf_data['compliance_rules']

        # Default rules for old format
        return {
            'overall_threshold': 80.0,
            'variant_threshold': None,
            'planogram_affects_success': False,
            'shelftalker_affects_success': False,
            'exclusivity_affects_success': False,
            'adjacency_affects_success': False
        }

    def get_category_brand(self, shelf_type: str) -> Optional[str]:
        """Get category brand for adjacency rules (PONDS, GAL, HAIRCARE)"""
        if shelf_type not in self.standards:
            return None

        shelf_data = self.standards[shelf_type]
        if isinstance(shelf_data, dict):
            return shelf_data.get('category_brand')
        return None

    def evaluate_compliance_pass(
        self,
        shelf_type: str,
        overall_compliance: float,
        variant_compliance: float,
        planogram_adherence: bool,
        shelftalker_adherence: bool,
        exclusivity: bool,
        adjacency_pass: bool = True,
        shelftalker_waived: bool = False
    ) -> Tuple[bool, Dict]:
        """
        Evaluate if a CSD passes based on its specific compliance rules.

        Args:
            shelf_type: QPDS shelf type
            overall_compliance: Overall compliance percentage
            variant_compliance: Variant compliance percentage
            planogram_adherence: True if planogram order is correct
            shelftalker_adherence: True if shelftalker count meets minimum
            exclusivity: True if exclusive (no competitor products)
            adjacency_pass: True if adjacency rules pass (PS Perfect Store)
            shelftalker_waived: True if shelftalker check is waived (common leg)

        Returns:
            (passed: bool, details: dict with individual check results)
        """
        rules = self.get_compliance_rules(shelf_type)

        details = {
            'overall_check': None,
            'variant_check': None,
            'planogram_check': None,
            'shelftalker_check': None,
            'exclusivity_check': None,
            'adjacency_check': None
        }

        passed = True

        # Check overall threshold
        if rules.get('overall_threshold') is not None:
            threshold = rules['overall_threshold']
            details['overall_check'] = overall_compliance >= threshold
            if not details['overall_check']:
                passed = False
                logger.debug(f"[QPDS] {shelf_type}: overall {overall_compliance}% < {threshold}% ❌")

        # Check variant threshold (only if specified)
        if rules.get('variant_threshold') is not None:
            threshold = rules['variant_threshold']
            details['variant_check'] = variant_compliance >= threshold
            if not details['variant_check']:
                passed = False
                logger.debug(f"[QPDS] {shelf_type}: variant {variant_compliance}% < {threshold}% ❌")

        # Check planogram (only if affects_success)
        if rules.get('planogram_affects_success', False):
            details['planogram_check'] = planogram_adherence
            if not planogram_adherence:
                passed = False
                logger.debug(f"[QPDS] {shelf_type}: planogram failed ❌")

        # Check shelftalker (only if affects_success AND not waived)
        if rules.get('shelftalker_affects_success', False) and not shelftalker_waived:
            details['shelftalker_check'] = shelftalker_adherence
            if not shelftalker_adherence:
                passed = False
                logger.debug(f"[QPDS] {shelf_type}: shelftalker failed ❌")
        elif shelftalker_waived:
            details['shelftalker_check'] = True  # waived = pass
            logger.debug(f"[QPDS] {shelf_type}: shelftalker waived (common leg)")

        # Check exclusivity (only if affects_success)
        if rules.get('exclusivity_affects_success', False):
            details['exclusivity_check'] = exclusivity
            # Only fail if explicitly False, not if None/NA
            if exclusivity is False:
                passed = False
                logger.debug(f"[QPDS] {shelf_type}: exclusivity failed ❌")
            elif exclusivity is None:
                logger.debug(f"[QPDS] {shelf_type}: exclusivity NA (not checked)")

        # Check adjacency (only if affects_success)
        if rules.get('adjacency_affects_success', False):
            details['adjacency_check'] = adjacency_pass
            if not adjacency_pass:
                passed = False
                logger.debug(f"[QPDS] {shelf_type}: adjacency failed ❌")

        logger.info(f"[QPDS] {shelf_type}: criteria_met={passed}")
        return passed, details

    def get_qpds_plan(self, shelf_type: str, channel: str = None) -> Dict[str, int]:
        """
        Get planned quantities for a shelf type.
        Returns dict of {product_name: quantity}
        If channel is provided and shelf type has channel-specific plans, use channel data.
        """
        if shelf_type not in self.standards:
            return {}

        shelf_data = self.standards[shelf_type]
        plan = {}

        # Handle channel-specific format (dict with 'channels' key)
        if isinstance(shelf_data, dict) and 'channels' in shelf_data:
            if channel and channel in shelf_data['channels']:
                # Use channel-specific products
                for item in shelf_data['channels'][channel]:
                    plan[item['product']] = item['quantity']
            elif channel:
                # Channel requested but not found, return empty
                return {}
            else:
                # No channel specified but channels exist, return first channel as default
                first_channel = list(shelf_data['channels'].keys())[0]
                for item in shelf_data['channels'][first_channel]:
                    plan[item['product']] = item['quantity']
        # Handle old format (list)
        elif isinstance(shelf_data, list):
            for item in shelf_data:
                plan[item['product']] = item['quantity']
        # Handle old format (dict with 'products' key)
        elif isinstance(shelf_data, dict) and 'products' in shelf_data:
            for item in shelf_data['products']:
                plan[item['product']] = item['quantity']

        return plan

    def get_product_order(self, shelf_type: str, channel: str = None) -> Dict[str, int]:
        """
        Get planned product order for a shelf type.
        Returns dict of {product_name: order_number}
        If channel is provided and shelf type has channel-specific plans, use channel data.
        """
        if shelf_type not in self.standards:
            return {}

        shelf_data = self.standards[shelf_type]
        order_map = {}

        # Handle channel-specific format (dict with 'channels' key)
        if isinstance(shelf_data, dict) and 'channels' in shelf_data:
            if channel and channel in shelf_data['channels']:
                # Use channel-specific products
                for item in shelf_data['channels'][channel]:
                    if 'order' in item:
                        order_map[item['product']] = item['order']
            elif not channel:
                # No channel specified, return first channel as default
                first_channel = list(shelf_data['channels'].keys())[0]
                for item in shelf_data['channels'][first_channel]:
                    if 'order' in item:
                        order_map[item['product']] = item['order']
        # Handle old format (dict with 'products' key)
        elif isinstance(shelf_data, dict) and 'products' in shelf_data:
            for item in shelf_data['products']:
                if 'order' in item:
                    order_map[item['product']] = item['order']

        return order_map

    def get_min_shelftalkers(self, shelf_type: str) -> int:
        """
        Get minimum required shelftalkers for a shelf type.
        Returns 0 if not specified.
        """
        if shelf_type not in self.standards:
            return 0

        shelf_data = self.standards[shelf_type]

        # Only new format has min_shelftalkers field
        if isinstance(shelf_data, dict):
            return shelf_data.get('min_shelftalkers', 0)

        return 0

    def calculate_product_accuracy(self, planned: int, visible: int) -> float:
        """
        Calculate accuracy percentage for a single product.

        Formula: min(visible, planned) / planned * 100
        - If visible == planned: 100%
        - If visible < planned: (visible / planned) * 100
        - If visible > planned: 100% (overstocking is not penalized)
        """
        if planned == 0:
            return 100.0 if visible == 0 else 0.0

        # Don't penalize overstocking (cap at 100%)
        accuracy = min(visible, planned) / planned * 100
        return round(accuracy, 2)

    def calculate_variant_compliance(
        self,
        shelf_type: str,
        detected_products: Dict[str, int],  # {ai_class_name: count}
        channel: str = None,
        apply_waivers: bool = True
    ) -> Tuple[float, List[Dict]]:
        """
        Calculate variant compliance score for a shelf type.

        Returns:
            (compliance_score, product_accuracy_list)

        compliance_score: 0-100 overall score
        product_accuracy_list: List of {name, planned, visible, accuracy, waived}
        channel: Optional channel (e.g., 'PBS', 'GBS') for channel-specific plans
        apply_waivers: If True, exclude waived products from score calculation
        """
        # Get QPDS plan for this shelf type
        qpds_plan = self.get_qpds_plan(shelf_type, channel)

        if not qpds_plan:
            # No QPDS plan for this shelf type
            return 0.0, []

        # Map AI detections to QPDS product names
        detected_qpds = {}
        for ai_name, count in detected_products.items():
            qpds_name = self.map_ai_product_to_qpds(ai_name)
            detected_qpds[qpds_name] = detected_qpds.get(qpds_name, 0) + count

        # Calculate accuracy for each product
        product_accuracy = []
        total_accuracy = 0.0
        counted_products = 0

        for product_name, planned_qty in qpds_plan.items():
            visible_qty = detected_qpds.get(product_name, 0)
            accuracy = self.calculate_product_accuracy(planned_qty, visible_qty)
            is_waived = self.is_product_waived(product_name)

            product_accuracy.append({
                "name": product_name,
                "planned": planned_qty,
                "visible": visible_qty,
                "accuracy": accuracy,
                "waived": is_waived
            })

            # Only include non-waived products in score calculation
            if not (apply_waivers and is_waived):
                total_accuracy += accuracy
                counted_products += 1
            else:
                logger.debug(f"[QPDS] Waived product excluded from variant compliance: {product_name}")

        # Calculate overall compliance score
        if counted_products > 0:
            compliance_score = total_accuracy / counted_products
        else:
            compliance_score = 100.0 if len(qpds_plan) > 0 else 0.0  # All waived = 100%

        return round(compliance_score, 2), product_accuracy

    def check_planogram_adherence(
        self,
        shelf_type: str,
        detected_products: List[Dict],  # List of {product_name, bbox_xyxy}
        channel: str = None
    ) -> bool:
        """
        Simplified planogram adherence check:
        1. Match the sequence (left-to-right order)
        2. At least one variant of each expected product is present
        3. Waived products are excluded from the check
        
        That's it - no hard quantity checks, no "extra product" penalties.

        Args:
            shelf_type: QPDS shelf type
            detected_products: List of detected products with bounding boxes
                               Each item: {product_name: str, bbox_xyxy: [x1, y1, x2, y2]}
            channel: Optional channel (e.g., 'PBS', 'GBS') for channel-specific plans

        Returns:
            True if sequence is correct and at least one of each non-waived product present
        """
        # Get expected order from QPDS standards
        expected_order = self.get_product_order(shelf_type, channel)

        if not expected_order:
            # No order defined for this shelf type
            logger.debug(f"[Planogram] {shelf_type}: No order defined, passing by default")
            return True

        # NOTE: Planogram uses BASE AI class names, NOT size variants.
        # Size variant detection (width-based clustering) is unreliable for multi-row
        # shelves — perspective causes width to vary more by row than by actual size.
        # So "gl_mltvit_crm:50g" and "gl_mltvit_crm:100g" both collapse to "gl_mltvit_crm".
        # If size variant detection improves later (e.g. per-row clustering), revert
        # core/analyzers.py to pass composite keys (class_name:size_variant) and remove
        # the base-class collapsing below.
        #
        # Collapse expected order to base AI class level
        # Multiple QPDS variants (e.g. "Cream 50g", "Cream 100g") may map from the
        # same AI class. Use min order among variants sharing a base class.
        # Build reverse map: qpds_name -> base AI class
        reverse_map = {}
        for ai_key, qpds_name in self.product_mappings.items():
            base_class = ai_key.split(':')[0] if ':' in str(ai_key) else str(ai_key)
            if qpds_name in expected_order:
                if qpds_name not in reverse_map:
                    reverse_map[qpds_name] = base_class

        # Build base_class -> min order, and track which base classes are non-waived
        base_class_order = {}  # base_class -> min order
        base_class_waived = {}  # base_class -> True only if ALL variants waived
        for qpds_name, order in expected_order.items():
            base_class = reverse_map.get(qpds_name, qpds_name)
            if base_class not in base_class_order or order < base_class_order[base_class]:
                base_class_order[base_class] = order
            is_waived = self.is_product_waived(qpds_name)
            if base_class not in base_class_waived:
                base_class_waived[base_class] = is_waived
            else:
                base_class_waived[base_class] = base_class_waived[base_class] and is_waived

        expected_base_classes_non_waived = {bc for bc, w in base_class_waived.items() if not w}

        logger.info(f"[Planogram] {shelf_type}: Expected {len(base_class_order)} base classes "
                    f"({len(expected_base_classes_non_waived)} non-waived)")
        logger.debug(f"[Planogram] Base class order: {base_class_order}")

        # Map detections using raw AI class name -> base class order
        detected_base_classes = set()
        relevant_detections = []

        for detection in detected_products:
            ai_name = detection.get('product_name', '')
            base_class = ai_name.split(':')[0] if ':' in ai_name else ai_name

            if base_class in base_class_order:
                detected_base_classes.add(base_class)
                bbox = detection.get('bbox_xyxy', [0, 0, 0, 0])
                center_x = (bbox[0] + bbox[2]) / 2
                relevant_detections.append({
                    'base_class': base_class,
                    'center_x': center_x,
                    'expected_order': base_class_order[base_class],
                    'waived': base_class_waived.get(base_class, False)
                })

        logger.debug(f"[Planogram] Detected {len(detected_base_classes)} unique base classes")
        logger.debug(f"[Planogram] Relevant detections: {len(relevant_detections)}")

        # Check 1: At least one of each non-waived base class must be present
        detected_non_waived = {d['base_class'] for d in relevant_detections if not d['waived']}
        missing = expected_base_classes_non_waived - detected_non_waived

        if missing:
            logger.warning(f"[Planogram] {shelf_type}: Missing non-waived base classes: {missing}")
            return False

        logger.info(f"[Planogram] {shelf_type}: All non-waived products present ✓")

        if not relevant_detections:
            # No relevant products detected
            logger.warning(f"[Planogram] {shelf_type}: No relevant products detected")
            return False

        # Check 2: Sequence must match (left-to-right order)
        # IMPORTANT: Only check sequence for NON-WAIVED products
        # Waived products don't affect planogram adherence
        non_waived_detections = [d for d in relevant_detections if not d['waived']]
        
        if not non_waived_detections:
            logger.warning(f"[Planogram] {shelf_type}: No non-waived products to check sequence")
            return True  # All expected products are waived, pass by default
        
        # Sort detections by x-coordinate (left to right)
        non_waived_detections.sort(key=lambda d: d['center_x'])

        # Extract expected order numbers in the sequence they appear
        actual_order_sequence = [d['expected_order'] for d in non_waived_detections]
        
        logger.debug(f"[Planogram] Actual sequence (non-waived only): {actual_order_sequence}")
        logger.debug(f"[Planogram] Detection sequence: {[(d['base_class'], d['expected_order']) for d in non_waived_detections]}")

        # The actual sequence should be in ascending order
        for i in range(len(actual_order_sequence) - 1):
            if actual_order_sequence[i] > actual_order_sequence[i + 1]:
                # Order is broken
                logger.warning(f"[Planogram] {shelf_type}: Order broken at position {i}: "
                             f"{non_waived_detections[i]['base_class']} (order {actual_order_sequence[i]}) -> "
                             f"{non_waived_detections[i+1]['base_class']} (order {actual_order_sequence[i+1]})")
                return False

        logger.info(f"[Planogram] {shelf_type}: Sequence correct ✓")
        return True

    def check_shelftalker_adherence(
        self,
        shelf_type: str,
        shelftalker_count: int
    ) -> bool:
        """
        Check if shelftalker count meets minimum requirement.

        Args:
            shelf_type: QPDS shelf type
            shelftalker_count: Number of shelftalkers detected

        Returns:
            True if count >= minimum, False otherwise
        """
        min_required = self.get_min_shelftalkers(shelf_type)

        if min_required == 0:
            # No requirement defined
            return True

        return shelftalker_count >= min_required


# Global instance
qpds_compliance = QPDSCompliance()


def calculate_compliance(shelf_type: str, detected_products: Dict[str, int], channel: str = None) -> Tuple[float, List[Dict]]:
    """
    Convenience function to calculate variant compliance.

    Args:
        shelf_type: QPDS shelf type (e.g., "Hair Care Premium QPDS")
        detected_products: Dict of AI detections {class_name: count}
        channel: Optional channel (e.g., 'PBS', 'GBS') for channel-specific plans

    Returns:
        (compliance_score, product_accuracy_list)
    """
    return qpds_compliance.calculate_variant_compliance(shelf_type, detected_products, channel)


def check_planogram_adherence(shelf_type: str, detected_products: List[Dict], channel: str = None) -> bool:
    """
    Convenience function to check planogram adherence.

    Args:
        shelf_type: QPDS shelf type
        detected_products: List of detections with product names and bounding boxes
                          Each item: {product_name: str, bbox_xyxy: [x1, y1, x2, y2]}
        channel: Optional channel (e.g., 'PBS', 'GBS') for channel-specific plans

    Returns:
        True if planogram order is correct, False otherwise
    """
    return qpds_compliance.check_planogram_adherence(shelf_type, detected_products, channel)


def check_shelftalker_adherence(shelf_type: str, shelftalker_count: int) -> bool:
    """
    Convenience function to check shelftalker adherence.

    Args:
        shelf_type: QPDS shelf type
        shelftalker_count: Number of shelftalkers detected

    Returns:
        True if shelftalker count meets minimum, False otherwise
    """
    return qpds_compliance.check_shelftalker_adherence(shelf_type, shelftalker_count)


def get_shelf_category(shelf_type: str) -> str:
    """
    Convenience function to get category for a shelf type.

    Args:
        shelf_type: QPDS shelf type

    Returns:
        Category name (e.g., "Hair Care", "Nutrition", etc.)
    """
    return qpds_compliance.get_shelf_category(shelf_type)


def get_compliance_rules(shelf_type: str) -> Dict:
    """
    Convenience function to get compliance rules for a shelf type.

    Args:
        shelf_type: QPDS shelf type

    Returns:
        Dict with threshold and toggle settings
    """
    return qpds_compliance.get_compliance_rules(shelf_type)


def evaluate_compliance_pass(
    shelf_type: str,
    overall_compliance: float,
    variant_compliance: float,
    planogram_adherence: bool,
    shelftalker_adherence: bool,
    exclusivity: bool,
    adjacency_pass: bool = True,
    shelftalker_waived: bool = False
) -> Tuple[bool, Dict]:
    """
    Convenience function to evaluate if CSD passes its compliance rules.

    Returns:
        (passed: bool, details: dict)
    """
    return qpds_compliance.evaluate_compliance_pass(
        shelf_type,
        overall_compliance,
        variant_compliance,
        planogram_adherence,
        shelftalker_adherence,
        exclusivity,
        adjacency_pass,
        shelftalker_waived
    )


def calculate_overall_compliance_with_waivers(
    product_accuracy: List[Dict]
) -> float:
    """
    Calculate overall compliance excluding waived products.

    Args:
        product_accuracy: List of {name, planned, visible, accuracy, waived}

    Returns:
        Overall compliance percentage (total_visible / total_planned * 100)
    """
    total_planned = 0
    total_visible = 0

    for item in product_accuracy:
        if not item.get('waived', False):
            total_planned += item['planned']
            total_visible += item['visible']

    if total_planned == 0:
        return 100.0  # All waived = 100%

    return min((total_visible / total_planned) * 100, 100.0)


def is_product_waived(product_name: str) -> bool:
    """Check if a product is waived from compliance"""
    return qpds_compliance.is_product_waived(product_name)


def get_category_brand(shelf_type: str) -> Optional[str]:
    """Get category brand for adjacency (PONDS, GAL, HAIRCARE)"""
    return qpds_compliance.get_category_brand(shelf_type)


def get_adjacency_rules() -> Dict:
    """Get adjacency rules configuration"""
    return qpds_compliance.adjacency_rules
