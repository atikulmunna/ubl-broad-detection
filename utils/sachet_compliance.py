"""
Sachet Display Standards Compliance Calculator
"""

import yaml
import os
from typing import Dict, List, Tuple, Optional


class SachetCompliance:
    """Calculate compliance scores for Sachet displays"""

    def __init__(self, standards_file: str = None, config_file: str = None):
        """Load Sachet standards from YAML file"""
        if standards_file is None:
            # Default to sachet_standards.yaml in the config/standards directory
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            standards_file = os.path.join(project_root, "config", "standards", "sachet_standards.yaml")
        if config_file is None:
            # Default to config.yaml
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_file = os.path.join(project_root, "config", "config.yaml")

        self.standards_file = standards_file
        self.config_file = config_file
        self.products = {}
        self.product_mappings = {}
        self.sachet_to_hanger_mapping = {}
        self.horizontal_overlap_threshold = 0.5  # Default
        self._load_config()
        self._load_standards()

    def _load_config(self):
        """Load configuration from config.yaml"""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
                sachet_config = config.get('sachet', {})
                self.horizontal_overlap_threshold = sachet_config.get('horizontal_overlap_threshold', 0.5)
        except Exception as e:
            print(f"Warning: Could not load config file: {e}, using defaults")

    def _load_standards(self):
        """Load Sachet standards from YAML file"""
        try:
            with open(self.standards_file, 'r') as f:
                data = yaml.safe_load(f)
                products_list = data.get('products', [])
                self.products = {item['product']: item['quantity'] for item in products_list}
                self.product_mappings = data.get('product_mappings', {})
                
                # Load sachet-to-hanger mapping from YAML
                self.sachet_to_hanger_mapping = data.get('sachet_to_hanger', {})
                
                # Load Unilever brand hangers list
                self.unilever_hangers = set(data.get('unilever_hangers', []))
        except Exception as e:
            print(f"Warning: Could not load Sachet standards: {e}")
            self.products = {}
            self.product_mappings = {}
            self.sachet_to_hanger_mapping = {}
            self.unilever_hangers = set()

    def _build_sachet_hanger_mapping(self):
        """Build mapping between sachets and their corresponding hangers"""
        # This method is now deprecated - mappings loaded from YAML
        pass

    def map_ai_product_to_standard(self, ai_product_name: str) -> str:
        """Map AI detection class name to Sachet standard name"""
        if ai_product_name in self.product_mappings:
            mapping = self.product_mappings[ai_product_name]
            # Handle both old (string) and new (dict) format
            if isinstance(mapping, dict):
                return mapping.get('name', ai_product_name)
            return mapping
        return ai_product_name

    def get_sachet_category(self, ai_product_name: str) -> str:
        """Get category for a sachet product"""
        if ai_product_name in self.product_mappings:
            mapping = self.product_mappings[ai_product_name]
            if isinstance(mapping, dict):
                return mapping.get('category', 'unknown')
        return 'unknown'

    def is_hanger(self, ai_product_name: str) -> bool:
        """Check if item is a hanger"""
        if ai_product_name in self.product_mappings:
            mapping = self.product_mappings[ai_product_name]
            if isinstance(mapping, dict):
                return mapping.get('is_hanger', False)
        return ai_product_name in self.unilever_hangers

    def get_company_name(self, ai_product_name: str) -> str:
        """Get company name for a sachet product"""
        if ai_product_name in self.product_mappings:
            mapping = self.product_mappings[ai_product_name]
            if isinstance(mapping, dict):
                return mapping.get('company', 'Unilever Bangladesh Limited')
        return 'Unilever Bangladesh Limited'

    def _is_below(self, sachet_bbox: List[float], hanger_bbox: List[float]) -> bool:
        """Check if sachet is below the hanger using bounding box coordinates

        A sachet is considered "below" a hanger if:
        1. It's vertically below (sachet top > hanger bottom)
        2. There's horizontal overlap between sachet and hanger (based on config threshold)
        """
        # bbox format: [x1, y1, x2, y2]
        sachet_left, sachet_top, sachet_right, sachet_bottom = sachet_bbox
        hanger_left, hanger_top, hanger_right, hanger_bottom = hanger_bbox

        # Check if sachet is vertically below hanger
        is_vertically_below = sachet_top > hanger_bottom

        # Check horizontal overlap: sachets should have X-overlap with hanger
        # Calculate overlap percentage
        overlap_left = max(sachet_left, hanger_left)
        overlap_right = min(sachet_right, hanger_right)
        overlap_width = max(0, overlap_right - overlap_left)
        sachet_width = sachet_right - sachet_left

        # Sachet is horizontally aligned if at least threshold% of its width overlaps with hanger
        # Threshold comes from config (default 0.5, can be 1.0 for 100%)
        has_horizontal_overlap = overlap_width >= (sachet_width * self.horizontal_overlap_threshold)

        return is_vertically_below and has_horizontal_overlap

    def _check_slot_adherence(self, detections: List[Dict]) -> Dict:
        """Check if sachets are positioned below their corresponding hangers"""
        import logging
        logger = logging.getLogger(__name__)

        # Group detections by type
        sachets = []
        hangers = []

        for det in detections:
            class_name = det.get('class_name', '')
            if self.is_hanger(class_name):
                hangers.append(det)
            else:
                # Include all sachets (both normal and rotated)
                sachets.append(det)

        logger.info(f"[Slot Adherence] Found {len(hangers)} hangers: {[h['class_name'] for h in hangers]}")
        logger.info(f"[Slot Adherence] Checking {len(sachets)} sachets")

        if not hangers:
            logger.warning("[Slot Adherence] No hangers detected!")
            return {
                'status': 'No hangers detected',
                'adherence': False,
                'misplaced_sachets': []
            }

        misplaced = []
        correctly_placed = 0
        total_sachets = len(sachets)

        for sachet in sachets:
            sachet_class = sachet['class_name']
            # Remove _rot and _rotate suffixes for matching
            base_sachet_class = sachet_class.replace('_rotate', '').replace('_rot', '')
            expected_hanger = self.sachet_to_hanger_mapping.get(base_sachet_class)

            if not expected_hanger:
                # No hanger mapping (e.g., Clinic Plus) - skip slot adherence check
                continue

            # Find corresponding hanger
            found_below_correct_hanger = False
            for hanger in hangers:
                if hanger['class_name'] == expected_hanger:
                    if self._is_below(sachet['bbox_xyxy'], hanger['bbox_xyxy']):
                        found_below_correct_hanger = True
                        correctly_placed += 1
                        break

            if not found_below_correct_hanger:
                logger.warning(f"[Slot Adherence] MISPLACED: {base_sachet_class} expects {expected_hanger} but not found below it")
                misplaced.append({
                    'sachet': sachet_class,
                    'expected_hanger': expected_hanger,
                    'bbox': sachet['bbox_xyxy']
                })

        adherence_passed = len(misplaced) == 0 and total_sachets > 0

        logger.info(f"[Slot Adherence] Result: {correctly_placed}/{total_sachets} correctly placed, {len(misplaced)} misplaced")
        logger.info(f"[Slot Adherence] Status: {'PASS' if adherence_passed else 'FAIL'}")

        return {
            'status': 'Pass' if adherence_passed else 'Fail',
            'adherence': adherence_passed,
            'correctly_placed': correctly_placed,
            'total_sachets': total_sachets,
            'misplaced_sachets': misplaced
        }

    def _check_orientation_adherence(self, detections: List[Dict]) -> Dict:
        """Check if sachets are in correct orientation (not rotated)"""
        import logging
        logger = logging.getLogger(__name__)

        rotated_sachets = []
        total_sachets = 0

        for det in detections:
            class_name = det.get('class_name', '')

            # Skip hangers using is_hanger method
            if self.is_hanger(class_name):
                continue

            total_sachets += 1

            # Check if sachet is rotated (ends with _rot or _rotate)
            # Strip rotation suffix variations to detect rotations
            base_class = class_name.replace('_rotate', '').replace('_rot', '')
            if base_class != class_name:  # Was rotated
                logger.warning(f"[Orientation] ROTATED: {class_name}")
                rotated_sachets.append({
                    'class': class_name,
                    'bbox': det['bbox_xyxy']
                })

        adherence_passed = len(rotated_sachets) == 0 and total_sachets > 0

        logger.info(f"[Orientation] Found {len(rotated_sachets)} rotated out of {total_sachets} total sachets")
        logger.info(f"[Orientation] Status: {'PASS' if adherence_passed else 'FAIL'}")

        return {
            'status': 'Pass' if adherence_passed else 'Fail',
            'adherence': adherence_passed,
            'correctly_oriented': total_sachets - len(rotated_sachets),
            'total_sachets': total_sachets,
            'rotated_sachets': rotated_sachets
        }

    def _check_combined_hanger(self, detections: List[Dict]) -> bool:
        """Check if there are multiple brand hangers in the image (combined hanger display)"""
        detected_brands = set()

        for det in detections:
            class_name = det.get('class_name', '')
            if self.is_hanger(class_name):
                # Extract brand name from new hanger format
                # e.g., 'dove' from 'dove_hanger' or 'glow_n_lovely' from 'glow_n_ lovely_hanger'
                # Handle old format too: 'dove' from 'dove_sachet_hanger'
                brand = class_name.replace('_hanger', '').replace('_sachet_hanger', '')
                detected_brands.add(brand)

        # Combined hanger if more than one brand type (e.g., dove + sunsilk)
        return len(detected_brands) > 1

    def _check_brand_exclusive_hanger(self, detections: List[Dict]) -> bool:
        """Check if the display has only a single brand (brand exclusive display)"""
        detected_brands = set()

        for det in detections:
            class_name = det.get('class_name', '')
            if self.is_hanger(class_name):
                # Extract brand name from new hanger format
                # e.g., 'dove' from 'dove_hanger' or 'glow_n_lovely' from 'glow_n_ lovely_hanger'
                # Handle old format too: 'dove' from 'dove_sachet_hanger'
                brand = class_name.replace('_hanger', '').replace('_sachet_hanger', '')
                detected_brands.add(brand)

        # Brand exclusive if exactly one brand (e.g., only dove or only sunsilk)
        return len(detected_brands) == 1

    def calculate_compliance(
        self,
        detected_products: Dict[str, int],
        detections: Optional[List[Dict]] = None
    ) -> Tuple[float, List[Dict], Dict]:
        """
        Calculate variant compliance for detected sachet products
        
        Args:
            detected_products: Dict mapping product names to counts
            detections: Optional list of detection dicts with bbox_xyxy and class_name
            
        Returns:
            Tuple of (compliance_score, product_accuracy, additional_checks)
        """
        # Run additional checks even without planogram (slot adherence, orientation, etc.)
        additional_checks = {}
        
        if detections:
            additional_checks['slot_adherence'] = self._check_slot_adherence(detections)
            additional_checks['orientation_adherence'] = self._check_orientation_adherence(detections)
            additional_checks['combined_hanger'] = self._check_combined_hanger(detections)
            additional_checks['brand_exclusive_hanger'] = self._check_brand_exclusive_hanger(detections)
        
        # If no planogram defined, only return adherence checks
        if not self.products or not detected_products:
            return 0.0, [], additional_checks
        
        # Map AI detections to standard names (preserve AI class name)
        detected_standard = {}
        ai_name_map = {}  # Track which AI name maps to each standard name
        for ai_name, count in detected_products.items():
            std_name = self.map_ai_product_to_standard(ai_name)
            detected_standard[std_name] = detected_standard.get(std_name, 0) + count
            ai_name_map[std_name] = ai_name  # Store first AI name for this standard name

        # Calculate accuracy ONLY for detected products that have a plan
        product_accuracy = []
        total_accuracy = 0.0

        for std_name, visible_qty in detected_standard.items():
            planned_qty = self.products.get(std_name, 0)
            ai_class = ai_name_map.get(std_name, "")

            # Skip hangers (they shouldn't appear in product_accuracy)
            if self.is_hanger(ai_class):
                continue

            # Calculate accuracy
            if planned_qty > 0:
                accuracy = min(visible_qty, planned_qty) / planned_qty * 100
            else:
                # Item detected but not in plan - 100% accuracy (reward visibility)
                accuracy = 100

            product_accuracy.append({
                "name": std_name,
                "class_name": ai_class,  # Add AI class name
                "is_hanger": self.is_hanger(ai_class),  # Add flag
                "company_name": self.get_company_name(ai_class),  # Add company
                "planned": planned_qty,
                "visible": visible_qty,
                "accuracy": round(accuracy, 2)
            })

            total_accuracy += accuracy

        compliance_score = total_accuracy / len(product_accuracy) if product_accuracy else 0.0
        
        return round(compliance_score, 2), product_accuracy, additional_checks


# Global instance
sachet_compliance = SachetCompliance()


def calculate_sachet_compliance(
    detected_products: Dict[str, int],
    detections: Optional[List[Dict]] = None
) -> Tuple[float, List[Dict], Dict]:
    """Convenience function to calculate Sachet compliance"""
    return sachet_compliance.calculate_compliance(detected_products, detections)


def get_sachet_category(ai_product_name: str) -> str:
    """Convenience function to get sachet category"""
    return sachet_compliance.get_sachet_category(ai_product_name)


def get_category_display_name(category_id: str) -> str:
    """Get display name for a category ID"""
    from utils.sos_category_mapping import get_category_display_name as sos_display
    return sos_display(category_id)
