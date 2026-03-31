"""
POSM (Point of Sale Materials) Standards Compliance Calculator
"""

import yaml
from typing import Dict, List, Tuple
from config.loader import POSM_CONFIG


class POSMCompliance:
    """Calculate compliance scores for POSM items"""

    def __init__(self, standards_file: str = "config/standards/posm_standards.yaml"):
        """Load POSM standards from YAML file"""
        self.standards_file = standards_file
        self.item_mappings = {}  # standard_name -> {ai_class, category}
        self._ai_to_standards = {}  # ai_class -> [standard_names]
        self._ai_to_category = {}  # ai_class -> category
        self._load_standards()

    def _load_standards(self):
        """Load POSM standards from YAML file"""
        try:
            with open(self.standards_file, 'r') as f:
                data = yaml.safe_load(f)
                self.item_mappings = data.get('item_mappings', {})
        except Exception as e:
            print(f"Warning: Could not load POSM standards: {e}")
            self.item_mappings = {}

        # Build reverse maps: ai_class -> standard names and category
        # ai_class may be a string or list of strings
        self._ai_to_standards = {}
        self._ai_to_category = {}
        for std_name, mapping in self.item_mappings.items():
            if not isinstance(mapping, dict):
                continue
            ai_class = mapping.get('ai_class', '')
            category = mapping.get('category', 'unknown')
            classes = ai_class if isinstance(ai_class, list) else [ai_class] if ai_class else []
            for cls in classes:
                self._ai_to_standards.setdefault(cls, []).append(std_name)
                self._ai_to_category[cls] = category

    def map_ai_item_to_standard(self, ai_item_name: str) -> str:
        """Map AI detection class name to POSM standard name"""
        names = self._ai_to_standards.get(ai_item_name)
        return names[0] if names else ai_item_name

    def get_all_names(self, ai_item_name: str) -> list:
        """Return all standard names for an AI class"""
        return self._ai_to_standards.get(ai_item_name, [ai_item_name])

    def get_posm_category(self, ai_item_name: str) -> str:
        """Get category for a POSM item by AI class name"""
        return self._ai_to_category.get(ai_item_name, 'unknown')

    def calculate_compliance(
        self,
        detected_items: Dict[str, int],
        planned_items: Dict[str, int] = None
    ) -> Tuple[float, List[Dict]]:
        """Calculate compliance for detected POSM items

        Args:
            detected_items: Dict of AI class names to detected counts
            planned_items: Optional dict of standard names to planned counts
        """
        if not detected_items:
            return 0.0, []

        if planned_items is None:
            planned_items = {}

        item_accuracy = []
        total_accuracy = 0.0

        cap_visible = POSM_CONFIG.get('cap_visible_to_planned', True)

        for std_name, planned_qty in planned_items.items():
            mapping = self.item_mappings.get(std_name, {})
            if isinstance(mapping, dict):
                raw = mapping.get('ai_class', std_name)
                classes = raw if isinstance(raw, list) else [raw]
            else:
                classes = [std_name]
            raw_visible = sum(detected_items.get(cls, 0) for cls in classes)
            visible_qty = min(raw_visible, planned_qty) if cap_visible else raw_visible
            accuracy = visible_qty / planned_qty * 100

            item_accuracy.append({
                "name": std_name,
                "class_name": classes[0] if classes else "",
                "planned": planned_qty,
                "visible": visible_qty,
                "accuracy": round(accuracy, 2)
            })

            total_accuracy += accuracy

        compliance_score = total_accuracy / len(planned_items) if planned_items else 0.0
        return round(compliance_score, 2), item_accuracy


# Global instance
posm_compliance = POSMCompliance()


def calculate_posm_compliance(detected_items: Dict[str, int], planned_items: Dict[str, int] = None) -> Tuple[float, List[Dict]]:
    """Convenience function to calculate POSM compliance"""
    return posm_compliance.calculate_compliance(detected_items, planned_items)


def get_posm_category(ai_item_name: str) -> str:
    """Convenience function to get POSM category"""
    return posm_compliance.get_posm_category(ai_item_name)


def get_category_display_name(category_id: str) -> str:
    """Get display name for a category ID"""
    from utils.sos_category_mapping import get_category_display_name as sos_display
    return sos_display(category_id)
