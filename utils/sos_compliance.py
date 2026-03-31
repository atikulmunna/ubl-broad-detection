"""
SOS (Share of Shelf) Compliance Calculator

Compares AI detections against planned SOS shelving norms.
"""

import yaml
from typing import Dict, List, Tuple
from pathlib import Path


class SOSCompliance:
    """Calculate compliance scores for Share of Shelf based on shelving norms"""

    def __init__(self, standards_file: str = "config/standards/sos_shelving_norm.yaml"):
        """Load SOS standards from YAML file"""
        self.standards_file = standards_file
        self.products = []
        self.product_mappings = {}
        self._load_standards()

    def _load_standards(self):
        """Load SOS standards from YAML file"""
        try:
            with open(self.standards_file, 'r') as f:
                data = yaml.safe_load(f)
                self.products = data.get('products', [])
                self.product_mappings = data.get('product_mappings', {})
        except Exception as e:
            print(f"Warning: Could not load SOS standards: {e}")
            self.products = []
            self.product_mappings = {}

    def map_ai_product_to_standard(self, ai_product_name: str) -> str:
        """Map AI detection class name to SOS standard name"""
        if ai_product_name in self.product_mappings:
            return self.product_mappings[ai_product_name]
        return ai_product_name

    def get_product_plan(self) -> Dict[str, int]:
        """Get planned quantities for all products"""
        plan = {}
        for item in self.products:
            plan[item['product']] = item['quantity']
        return plan

    def calculate_compliance(
        self,
        detected_products: Dict[str, int]
    ) -> Tuple[float, List[Dict]]:
        """Calculate variant compliance only for detected SOS products"""
        plan = self.get_product_plan()
        
        if not plan or not detected_products:
            return 0.0, []
        
        # Map AI detections to standard names
        detected_standard = {}
        for ai_name, count in detected_products.items():
            std_name = self.map_ai_product_to_standard(ai_name)
            detected_standard[std_name] = detected_standard.get(std_name, 0) + count
        
        # Calculate accuracy ONLY for detected products that have a plan
        product_accuracy = []
        total_accuracy = 0.0
        
        for std_name, visible_qty in detected_standard.items():
            planned_qty = plan.get(std_name, 0)
            if planned_qty > 0:
                accuracy = min(visible_qty, planned_qty) / planned_qty * 100
            else:
                # Product detected but not in plan - 100% accuracy (reward visibility)
                accuracy = 100
            
            product_accuracy.append({
                "name": std_name,
                "planned": planned_qty,
                "visible": visible_qty,
                "accuracy": round(accuracy, 2)
            })
            
            total_accuracy += accuracy
        
        compliance_score = total_accuracy / len(detected_standard) if detected_standard else 0.0
        return round(compliance_score, 2), product_accuracy


# Global instance
sos_compliance = SOSCompliance()


def calculate_sos_compliance(detected_products: Dict[str, int]) -> Tuple[float, List[Dict]]:
    """Convenience function to calculate SOS compliance"""
    return sos_compliance.calculate_compliance(detected_products)

