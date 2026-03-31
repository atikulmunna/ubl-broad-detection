"""
Adjacency Detector Module

Detects spatial relationships between product categories on shelves.
Used for Perfect Store compliance where category placement rules apply.

Adjacency Rules for PS Perfect Store:
- Priority: PONDS > GAL > HAIRCARE
- When adjacent, higher priority gets 4 legs, lower gets 3
- Common leg shelftalker: waive shelftalker compliance when categories share a leg
"""

import logging
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

# Load adjacency rules from QPDS standards (cached)
_ADJACENCY_RULES_CACHE = None


def _load_adjacency_rules() -> Dict:
    """Load adjacency rules from QPDS standards (cached)"""
    global _ADJACENCY_RULES_CACHE
    if _ADJACENCY_RULES_CACHE is None:
        try:
            from utils.qpds_compliance import get_adjacency_rules
            _ADJACENCY_RULES_CACHE = get_adjacency_rules()
            logger.info(f"Loaded adjacency rules: {list(_ADJACENCY_RULES_CACHE.keys())}")
        except Exception as e:
            logger.warning(f"Could not load adjacency rules: {e}")
            _ADJACENCY_RULES_CACHE = {}
    return _ADJACENCY_RULES_CACHE


def _detect_orientation_from_shelftalkers(shelftalker_dets: List[Dict]) -> Optional[str]:
    """
    Determine adjacency orientation by comparing y-positions of haircare vs skincare shelftalkers.

    If haircare shelftalkers are entirely above or below skincare → vertical.
    If they overlap in y (same horizontal band) → horizontal.
    Returns None if either group is absent.
    """
    if not shelftalker_dets:
        return None

    haircare = [d['bbox'] for d in shelftalker_dets if d['class_name'].startswith('da_hair_care_st')]
    skincare = [d['bbox'] for d in shelftalker_dets
                if d['class_name'].startswith('da_ponds_st') or d['class_name'].startswith('da_gal_st')]

    if not haircare or not skincare:
        return None

    # Use center_y of each shelftalker rather than full y-range.
    # Left/right shelftalkers span the full section height so their y-range
    # bleeds into the adjacent section — centers stay within their own section.
    hair_centers_y = [(b[1] + b[3]) / 2 for b in haircare]
    skin_centers_y = [(b[1] + b[3]) / 2 for b in skincare]

    if max(hair_centers_y) < min(skin_centers_y) or min(hair_centers_y) > max(skin_centers_y):
        logger.info(f"[Shelftalker orientation] vertical: hair cy={hair_centers_y} skin cy={skin_centers_y}")
        return 'vertical'

    logger.info(f"[Shelftalker orientation] horizontal: hair cy={hair_centers_y} skin cy={skin_centers_y}")
    return 'horizontal'


def calculate_bbox_center(bbox_xyxy: List[float]) -> Tuple[float, float]:
    """
    Calculate center point of a bounding box.

    Args:
        bbox_xyxy: [x1, y1, x2, y2]

    Returns:
        (center_x, center_y)
    """
    x1, y1, x2, y2 = bbox_xyxy
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def get_category_from_product(product_name: str) -> Optional[str]:
    """
    Extract category from product name for Perfect Store analysis.

    Maps product names to categories (PONDS, GAL, HAIRCARE).

    Args:
        product_name: QPDS standard product name

    Returns:
        Category name or None if not categorized
    """
    product_lower = product_name.lower()

    if "pond" in product_lower or "ponds" in product_lower:
        return "PONDS"
    elif "glow" in product_lower or "gal" in product_lower or "g&l" in product_lower:
        return "GAL"
    elif any(brand in product_lower for brand in ["dove", "clear", "sunsilk", "tresemme"]):
        return "HAIRCARE"

    return None


def group_detections_by_category(detections: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Group product detections by category.

    Args:
        detections: List of detection dicts with 'product_name' and 'bbox_xyxy'

    Returns:
        Dictionary of {category: [detections]}
    """
    grouped = defaultdict(list)

    for detection in detections:
        product_name = detection.get('product_name', '')
        category = get_category_from_product(product_name)

        if category:
            grouped[category].append(detection)

    return dict(grouped)


def calculate_category_bounds(detections: List[Dict]) -> Dict[str, float]:
    """
    Calculate spatial bounds for a category's detections.

    Args:
        detections: List of detection dicts with 'bbox_xyxy'

    Returns:
        Dictionary with min_x, max_x, min_y, max_y, center_x, center_y
    """
    if not detections:
        return {
            'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0,
            'center_x': 0, 'center_y': 0, 'count': 0
        }

    all_x = []
    all_y = []

    for det in detections:
        bbox = det.get('bbox_xyxy', [])
        if len(bbox) >= 4:
            x1, y1, x2, y2 = bbox[:4]
            all_x.extend([x1, x2])
            all_y.extend([y1, y2])

    if not all_x:
        return {
            'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0,
            'center_x': 0, 'center_y': 0, 'count': 0
        }

    return {
        'min_x': min(all_x),
        'max_x': max(all_x),
        'min_y': min(all_y),
        'max_y': max(all_y),
        'center_x': (min(all_x) + max(all_x)) / 2,
        'center_y': (min(all_y) + max(all_y)) / 2,
        'count': len(detections)
    }


def detect_category_adjacency(
    detections: List[Dict],
    horizontal_threshold: float = 50.0
) -> Dict[str, Dict]:
    """
    Detect spatial adjacency relationships between product categories.

    Analyzes horizontal positioning to determine which categories are adjacent.
    Used for Perfect Store compliance rules (e.g., GAL legs increase if next to Haircare).

    Args:
        detections: List of detection dicts with 'product_name' and 'bbox_xyxy'
        horizontal_threshold: Max horizontal gap (pixels) to consider categories adjacent

    Returns:
        Dictionary with category adjacency info:
        {
            'categories': {
                'PONDS': {'bounds': {...}, 'position': 'left', 'adjacent_to': ['GAL']},
                'GAL': {'bounds': {...}, 'position': 'middle', 'adjacent_to': ['PONDS', 'HAIRCARE']},
                'HAIRCARE': {'bounds': {...}, 'position': 'right', 'adjacent_to': ['GAL']}
            },
            'layout_order': ['PONDS', 'GAL', 'HAIRCARE'],
            'adjacency_detected': True
        }
    """
    # Group detections by category
    grouped = group_detections_by_category(detections)

    if not grouped:
        logger.debug("No categorized products found for adjacency detection")
        return {
            'categories': {},
            'layout_order': [],
            'adjacency_detected': False
        }

    # Calculate bounds for each category
    category_info = {}
    for category, cat_detections in grouped.items():
        bounds = calculate_category_bounds(cat_detections)
        category_info[category] = {
            'bounds': bounds,
            'position': None,
            'adjacent_to': [],
        }

    # Sort categories by horizontal position (left to right)
    sorted_categories = sorted(
        category_info.keys(),
        key=lambda cat: category_info[cat]['bounds']['center_x']
    )

    # Determine adjacency based on horizontal gaps
    for i, category in enumerate(sorted_categories):
        # Assign relative position
        if i == 0:
            category_info[category]['position'] = 'left'
        elif i == len(sorted_categories) - 1:
            category_info[category]['position'] = 'right'
        else:
            category_info[category]['position'] = 'middle'

        # Check adjacency with next category
        if i < len(sorted_categories) - 1:
            next_category = sorted_categories[i + 1]

            current_bounds = category_info[category]['bounds']
            next_bounds = category_info[next_category]['bounds']

            horizontal_gap = next_bounds['min_x'] - current_bounds['max_x']

            if horizontal_gap <= horizontal_threshold:
                category_info[category]['adjacent_to'].append(next_category)
                category_info[next_category]['adjacent_to'].append(category)

                logger.debug(
                    f"Adjacency detected: {category} <-> {next_category} "
                    f"(gap: {horizontal_gap:.1f}px)"
                )

    adjacency_detected = any(
        len(info['adjacent_to']) > 0
        for info in category_info.values()
    )

    result = {
        'categories': category_info,
        'layout_order': sorted_categories,
        'adjacency_detected': adjacency_detected
    }

    if adjacency_detected:
        logger.info(
            f"Category layout detected: {' -> '.join(sorted_categories)}"
        )

    return result


def count_category_facings(detections: List[Dict], category: str) -> int:
    """
    Count number of facings (unique horizontal positions) for a category.

    Facings are estimated by counting unique x-centers of bounding boxes.

    Args:
        detections: List of all product detections
        category: Category name (PONDS, GAL, HAIRCARE)

    Returns:
        Number of facings/legs for the category
    """
    category_detections = [
        det for det in detections
        if get_category_from_product(det.get('product_name', '')) == category
    ]

    if not category_detections:
        return 0

    # Get x-centers of all bounding boxes
    x_centers = []
    for det in category_detections:
        bbox = det.get('bbox_xyxy', [])
        if len(bbox) >= 4:
            center_x, _ = calculate_bbox_center(bbox)
            x_centers.append(center_x)

    if not x_centers:
        return 0

    # Cluster x-centers to estimate facings
    # Sort centers and group those within threshold distance
    x_centers.sort()
    facing_threshold = 30.0  # pixels

    facings = 1
    for i in range(1, len(x_centers)):
        if x_centers[i] - x_centers[i-1] > facing_threshold:
            facings += 1

    return facings


def get_required_legs(category: str, adjacency_info: Dict, orientation: Optional[str] = None) -> int:
    """
    Get required number of legs (facings) for a category based on adjacency.

    Rules (PS Perfect Store):
    - Priority: PONDS > GAL > HAIRCARE
    - When adjacent to higher priority: 3 legs
    - When not adjacent or highest priority: 4 legs
    - Vertical layout: HAIRCARE takes priority (4 legs), SKINCARE gets 3

    Args:
        category: Category brand (PONDS, GAL, HAIRCARE)
        adjacency_info: Result from detect_category_adjacency()
        orientation: 'vertical', 'horizontal', or None

    Returns:
        Required number of legs (3 or 4)
    """
    rules = _load_adjacency_rules()

    if not rules or not adjacency_info.get('adjacency_detected'):
        return rules.get('default_legs', {}).get(category, 4)

    categories = adjacency_info.get('categories', {})
    cat_info = categories.get(category, {})
    adjacent_to = cat_info.get('adjacent_to', [])

    if not adjacent_to:
        return rules.get('default_legs', {}).get(category, 4)

    if orientation == 'vertical':
        vert_adjustments = rules.get('vertical_adjacency_adjustments', {})
        # Find the right key: parse format "{lhs}_vertical_to_{A}" or "{lhs}_vertical_to_{A}_and_{B}"
        # All participants in the key = {lhs} | rhs_parts
        for adj_key, adj_val in vert_adjustments.items():
            if category not in adj_val:
                continue
            if '_vertical_to_' not in adj_key:
                continue
            lhs, rhs = adj_key.split('_vertical_to_', 1)
            key_participants = set(rhs.split('_and_')) | {lhs}
            if set(adjacent_to).issubset(key_participants):
                return adj_val[category]
        # Fallback: try individual neighbor keys
        for neighbor in adjacent_to:
            key = f"{category}_vertical_to_{neighbor}"
            if key in vert_adjustments and category in vert_adjustments[key]:
                return vert_adjustments[key][category]
        return rules.get('default_legs', {}).get(category, 4)

    # Horizontal (or unknown): use existing priority rules
    priority_order = rules.get('priority_order', ['PONDS', 'GAL', 'HAIRCARE'])
    try:
        my_priority = priority_order.index(category)
    except ValueError:
        return 4

    for adj_cat in adjacent_to:
        try:
            if priority_order.index(adj_cat) < my_priority:
                return 3
        except ValueError:
            continue

    return 4


def check_adjacency_leg_compliance(
    category: str,
    actual_facings: int,
    adjacency_info: Dict,
    orientation: Optional[str] = None
) -> Tuple[bool, int]:
    """
    Check if category has required number of legs based on adjacency rules.

    Args:
        category: Category brand (PONDS, GAL, HAIRCARE)
        actual_facings: Detected number of facings/legs
        adjacency_info: Result from detect_category_adjacency()
        orientation: 'vertical', 'horizontal', or None

    Returns:
        (passed: bool, required_legs: int)
    """
    required = get_required_legs(category, adjacency_info, orientation=orientation)
    passed = actual_facings >= required

    if not passed:
        logger.info(
            f"Adjacency compliance: {category} has {actual_facings} legs, "
            f"needs {required} ❌"
        )
    else:
        logger.debug(
            f"Adjacency compliance: {category} has {actual_facings} legs, "
            f"needs {required} ✓"
        )

    return passed, required


def should_waive_shelftalker(
    category: str,
    adjacency_info: Dict,
    orientation: Optional[str] = None
) -> bool:
    """
    Check if shelftalker compliance should be waived due to common leg.

    For PS Perfect Store: when a category gets fewer required legs than default
    due to adjacency, shelftalker is waived.

    Args:
        category: Category brand (PONDS, GAL, HAIRCARE)
        adjacency_info: Result from detect_category_adjacency()
        orientation: 'vertical', 'horizontal', or None

    Returns:
        True if shelftalker compliance should be waived
    """
    rules = _load_adjacency_rules()

    if not rules.get('common_leg_shelftalker_waiver', False):
        return False

    if not adjacency_info.get('adjacency_detected'):
        return False

    cat_info = adjacency_info.get('categories', {}).get(category, {})
    if not cat_info.get('adjacent_to'):
        return False

    default = rules.get('default_legs', {}).get(category, 4)
    required = get_required_legs(category, adjacency_info, orientation=orientation)
    waived = required < default

    if waived:
        logger.info(f"Shelftalker waived for {category}: required {required} < default {default}")
    else:
        logger.debug(f"Shelftalker NOT waived for {category}: required {required} == default {default}")

    return waived


def evaluate_adjacency_compliance(
    detections: List[Dict],
    shelf_type: str,
    shelftalker_dets: Optional[List[Dict]] = None
) -> Dict:
    """
    Full adjacency compliance evaluation for a shelf type.

    Args:
        detections: List of product detections with bounding boxes
        shelf_type: QPDS shelf type
        shelftalker_dets: List of shelftalker dicts with 'class_name' and 'bbox' (for orientation)

    Returns:
        Dict with:
        - adjacency_info: Raw adjacency detection result
        - category_brand: Category brand for this shelf type
        - required_legs: Required number of legs
        - actual_legs: Detected number of legs
        - adjacency_pass: True if leg count meets requirement
        - shelftalker_waived: True if shelftalker should be waived
        - orientation: 'vertical', 'horizontal', or None
    """
    # Get category brand for this shelf type
    try:
        from utils.qpds_compliance import get_category_brand
        category_brand = get_category_brand(shelf_type)
    except ImportError:
        category_brand = None

    if not category_brand:
        # Not a PS Perfect Store shelf type - no adjacency rules
        return {
            'adjacency_info': {},
            'category_brand': None,
            'required_legs': 0,
            'actual_legs': 0,
            'adjacency_pass': True,
            'shelftalker_waived': False,
            'orientation': None
        }

    # Detect adjacency
    adjacency_info = detect_category_adjacency(detections)

    # Determine orientation from shelftalker bboxes
    orientation = _detect_orientation_from_shelftalkers(shelftalker_dets) if shelftalker_dets else None

    # Count facings for this category
    actual_legs = count_category_facings(detections, category_brand)

    # Check leg compliance
    adjacency_pass, required_legs = check_adjacency_leg_compliance(
        category_brand,
        actual_legs,
        adjacency_info,
        orientation=orientation
    )

    # Check shelftalker waiver
    shelftalker_waived = should_waive_shelftalker(category_brand, adjacency_info, orientation=orientation)

    return {
        'adjacency_info': adjacency_info,
        'category_brand': category_brand,
        'required_legs': required_legs,
        'actual_legs': actual_legs,
        'adjacency_pass': adjacency_pass,
        'shelftalker_waived': shelftalker_waived,
        'orientation': orientation
    }
