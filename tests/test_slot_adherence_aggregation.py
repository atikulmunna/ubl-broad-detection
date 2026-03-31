#!/usr/bin/env python3
"""
Test script to verify slot adherence aggregation logic
Simulates the exact scenario from the user's backend test
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from collections import defaultdict
from utils.sachet_compliance import sachet_compliance

def test_slot_adherence_logic():
    """Test the slot adherence percentage-based logic"""
    
    print("=" * 80)
    print("SLOT ADHERENCE AGGREGATION TEST")
    print("=" * 80)
    
    # Simulate AI result from main.py analyze_sachet()
    ai_result = {
        "product_breakdown": {
            "clear_shmp_cac": 11,  # Clear Anti Dandruff
            "clear_men_shamp_csm": 12,  # Clear Men (non-rotated)
            "clear_men_shamp_csm_rotate": 3,  # Clear Men (rotated)
            "sunsilk_sm_blk_sprk": 6  # Sunsilk
        },
        "slot_adherence_details": {
            "misplaced_sachets": [
                # All 11 Clear Anti Dandruff are misplaced (under dove hanger)
                {"sachet": "clear_shmp_cac"},
                {"sachet": "clear_shmp_cac"},
                {"sachet": "clear_shmp_cac"},
                {"sachet": "clear_shmp_cac"},
                {"sachet": "clear_shmp_cac"},
                {"sachet": "clear_shmp_cac"},
                {"sachet": "clear_shmp_cac"},
                {"sachet": "clear_shmp_cac"},
                {"sachet": "clear_shmp_cac"},
                {"sachet": "clear_shmp_cac"},
                {"sachet": "clear_shmp_cac"},
                # 2 Sunsilk are misplaced (in clear men portion)
                {"sachet": "sunsilk_sm_blk_sprk"},
                {"sachet": "sunsilk_sm_blk_sprk"},
                # 1 Clear Men is misplaced (under dove hanger on left side)
                {"sachet": "clear_men_shamp_csm"},
            ]
        },
        "orientation_adherence_details": {
            "rotated_sachets": [
                {"class": "clear_men_shamp_csm_rotate"},
                {"class": "clear_men_shamp_csm_rotate"},
                {"class": "clear_men_shamp_csm_rotate"},
            ]
        }
    }
    
    # Simulate aggregation logic (from aggregator.py)
    orientation_data = ai_result.get("orientation_adherence_details", {})
    slot_data = ai_result.get("slot_adherence_details", {})
    
    # Build rotated classes set
    rotated_classes = set()
    for item in orientation_data.get("rotated_sachets", []):
        rotated_classes.add(item.get("class", ""))
    
    # Count misplaced sachets per base class
    misplaced_counts = defaultdict(int)
    for item in slot_data.get("misplaced_sachets", []):
        sachet_class = item.get("sachet", "")
        base_class = sachet_class.replace('_rotate', '').replace('_rot', '')
        misplaced_counts[base_class] += 1
    
    print(f"\n📊 Misplaced counts: {dict(misplaced_counts)}")
    print(f"🔄 Rotated classes: {rotated_classes}")
    
    # Group by mapped product name
    product_groups = defaultdict(lambda: {"ai_classes": [], "total_qty": 0})
    for ai_class_name, count in ai_result.get("product_breakdown", {}).items():
        if sachet_compliance.is_hanger(ai_class_name):
            continue
        mapped_name = sachet_compliance.map_ai_product_to_standard(ai_class_name)
        product_groups[mapped_name]["ai_classes"].append(ai_class_name)
        product_groups[mapped_name]["total_qty"] += count
    
    # Build sachets list with per-product adherence
    print("\n" + "=" * 80)
    print("PER-PRODUCT ADHERENCE RESULTS")
    print("=" * 80)
    
    sachets_list = []
    for mapped_name, group_data in product_groups.items():
        ai_classes = group_data["ai_classes"]
        primary_class = ai_classes[0]
        company_name = sachet_compliance.get_company_name(primary_class)
        
        # Calculate orientation adherence
        has_rotation = any(cls in rotated_classes for cls in ai_classes)
        orientation_adh = "No" if has_rotation else "Yes"
        
        # Calculate slot adherence based on placement percentage
        base_classes = [cls.replace('_rotate', '').replace('_rot', '') for cls in ai_classes]
        total_misplaced = sum(misplaced_counts.get(base_cls, 0) for base_cls in base_classes)
        total_visible = group_data["total_qty"]
        correctly_placed = total_visible - total_misplaced
        placement_percentage = (correctly_placed / total_visible * 100) if total_visible > 0 else 0
        
        # Check if product has hanger mapping
        has_hanger_mapping = any(
            sachet_compliance.sachet_to_hanger_mapping.get(base_cls)
            for base_cls in base_classes
        )
        
        if not has_hanger_mapping:
            slot_adh = "N/A"
        else:
            # Use 80% threshold (from config)
            threshold = 80
            slot_adh = "Yes" if placement_percentage >= threshold else "No"
        
        sachets_list.append({
            "company_name": company_name,
            "sachet_name": mapped_name,
            "visible_qty": total_visible,
            "orientation_adherence": orientation_adh,
            "slot_adherence": slot_adh
        })
        
        # Print detailed analysis
        print(f"\n📦 {mapped_name}")
        print(f"   Company: {company_name}")
        print(f"   Total visible: {total_visible}")
        print(f"   Misplaced: {total_misplaced}")
        print(f"   Correctly placed: {correctly_placed}")
        print(f"   Placement percentage: {placement_percentage:.1f}%")
        print(f"   Orientation adherence: {orientation_adh}")
        print(f"   Slot adherence: {slot_adh}")
        
        # Validation
        expected_slot = None
        if "Clear Anti" in mapped_name:
            expected_slot = "No"  # All 11 misplaced
        elif "Clear Men" in mapped_name:
            expected_slot = "Yes"  # 14/15 correct (93.3%)
        elif "Sunsilk" in mapped_name:
            expected_slot = "No"  # 4/6 correct (66.7%)
        
        if expected_slot:
            status = "✓" if slot_adh == expected_slot else "✗"
            print(f"   {status} Expected: {expected_slot}, Got: {slot_adh}")
    
    # Final summary
    print("\n" + "=" * 80)
    print("FINAL JSON OUTPUT (simulated backend response)")
    print("=" * 80)
    
    import json
    final_output = {
        "sachets": {}
    }
    for idx, sachet in enumerate(sachets_list, 1):
        final_output["sachets"][str(idx)] = {
            "company_name": sachet["company_name"],
            "sachet_name": sachet["sachet_name"],
            "visible_qty": sachet["visible_qty"],
            "orientation_adherence": sachet["orientation_adherence"],
            "slot_adherence": sachet["slot_adherence"]
        }
    
    print(json.dumps(final_output, indent=4))
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_slot_adherence_logic()
