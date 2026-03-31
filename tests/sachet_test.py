#!/usr/bin/env python3
"""
Sachet Detection Debug Script
Tests SACHET_YOLO11X model and compliance checks to diagnose detection issues
"""

import os
import sys
from pathlib import Path
from PIL import Image
import yaml

# Add project to path
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

from ultralytics import YOLO
from utils.sachet_compliance import calculate_sachet_compliance

# ============================================================================
# Configuration
# ============================================================================

MODEL_PATH = "models/SACHET_YOLO11X.pt"
TEST_IMAGE = "examples/SACHET/02.jpg"  # The image from your attachment
CONFIDENCE_THRESHOLD = 0.25

# ============================================================================
# Main Test
# ============================================================================

def print_section(title):
    """Print formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def main():
    print_section("SACHET DETECTION DEBUG TEST")
    
    # Check files exist
    if not os.path.exists(MODEL_PATH):
        print(f"❌ Model not found: {MODEL_PATH}")
        return
    
    if not os.path.exists(TEST_IMAGE):
        print(f"❌ Test image not found: {TEST_IMAGE}")
        return
    
    print(f"✓ Model: {MODEL_PATH}")
    print(f"✓ Image: {TEST_IMAGE}")
    print(f"✓ Confidence threshold: {CONFIDENCE_THRESHOLD}")
    
    # ========================================================================
    # STEP 1: Load Model
    # ========================================================================
    
    print_section("STEP 1: Loading SACHET_YOLO11X Model")
    
    try:
        model = YOLO(MODEL_PATH)
        print(f"✓ Model loaded successfully")
        print(f"✓ Model type: {type(model)}")
        
        # Print model classes
        if hasattr(model, 'names'):
            print(f"\n📋 Model has {len(model.names)} classes:")
            for idx, name in model.names.items():
                print(f"  {idx:3d}: {name}")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return
    
    # ========================================================================
    # STEP 2: Run Inference
    # ========================================================================
    
    print_section("STEP 2: Running Inference on Test Image")
    
    try:
        results = model.predict(
            source=TEST_IMAGE,
            conf=CONFIDENCE_THRESHOLD,
            verbose=False
        )
        
        if not results or len(results) == 0:
            print("❌ No results returned from model")
            return
        
        result = results[0]
        print(f"✓ Inference complete")
        print(f"✓ Results type: {type(result)}")
        print(f"✓ Number of detections: {len(result.boxes)}")
        
    except Exception as e:
        print(f"❌ Inference failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # ========================================================================
    # STEP 3: Parse Raw Detections
    # ========================================================================
    
    print_section("STEP 3: Raw AI Model Detections")
    
    boxes = result.boxes.xyxy.cpu().numpy()
    scores = result.boxes.conf.cpu().numpy()
    class_ids = result.boxes.cls.cpu().numpy().astype(int)
    
    print(f"\n📊 Total detections: {len(boxes)}")
    print(f"\nDetailed breakdown:\n")
    
    detections = []
    detected_products = {}
    hanger_count = 0
    sachet_count = 0
    rotated_count = 0
    
    for idx, (box, score, class_id) in enumerate(zip(boxes, scores, class_ids)):
        class_name = result.names[int(class_id)]
        
        # Count types
        if 'hanger' in class_name.lower():
            hanger_count += 1
            item_type = "🎯 HANGER"
        elif '_rotate' in class_name or '_rot' in class_name:
            rotated_count += 1
            sachet_count += 1
            item_type = "🔄 ROTATED SACHET"
        else:
            sachet_count += 1
            item_type = "📦 SACHET"
        
        print(f"  [{idx+1:2d}] {item_type:20s} | {class_name:40s} | conf: {score:.3f}")
        print(f"       bbox: [{box[0]:.1f}, {box[1]:.1f}, {box[2]:.1f}, {box[3]:.1f}]")
        
        # Build detections list (same format as main.py)
        detections.append({
            'bbox_xyxy': [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
            'class_name': class_name,
            'confidence': float(score)
        })
        
        # Count products
        detected_products[class_name] = detected_products.get(class_name, 0) + 1
    
    print(f"\n📈 Summary:")
    print(f"  • Total hangers detected: {hanger_count}")
    print(f"  • Total sachets detected: {sachet_count}")
    print(f"  • Rotated sachets: {rotated_count}")
    
    # ========================================================================
    # STEP 4: Check Hanger Detection
    # ========================================================================
    
    print_section("STEP 4: Hanger Detection Analysis")
    
    from utils.sachet_compliance import sachet_compliance
    
    hanger_detections = [d for d in detections if sachet_compliance.is_hanger(d['class_name'])]
    
    print(f"\n🎯 Hangers identified by is_hanger() method: {len(hanger_detections)}")
    
    if hanger_detections:
        print("\nHanger details:")
        for h in hanger_detections:
            class_name = h['class_name']
            bbox = h['bbox_xyxy']
            # Try to extract brand
            brand = class_name.replace('_hanger', '').replace('_sachet_hanger', '')
            print(f"  • {class_name} → brand: '{brand}'")
            print(f"    bbox: [{bbox[0]:.1f}, {bbox[1]:.1f}, {bbox[2]:.1f}, {bbox[3]:.1f}]")
    else:
        print("\n⚠️  WARNING: No hangers identified!")
        print("   This means slot adherence and brand checks will FAIL")
        
        # Check if any detections have 'hanger' in name
        possible_hangers = [d['class_name'] for d in detections if 'hanger' in d['class_name'].lower()]
        if possible_hangers:
            print(f"\n   Found {len(possible_hangers)} detections with 'hanger' in name:")
            for h in possible_hangers:
                print(f"     - {h}")
            print("\n   These might be hangers but aren't recognized by is_hanger()")
    
    # ========================================================================
    # STEP 5: Check Sachet-to-Hanger Mapping
    # ========================================================================
    
    print_section("STEP 5: Sachet-to-Hanger Mapping Check")
    
    print("\n📋 Sachet to hanger mappings from config:")
    sachet_detections = [d for d in detections if not sachet_compliance.is_hanger(d['class_name'])]
    
    if sachet_detections:
        for s in sachet_detections:
            class_name = s['class_name']
            # Remove rotation suffix for mapping lookup
            base_class = class_name.replace('_rotate', '').replace('_rot', '')
            expected_hanger = sachet_compliance.sachet_to_hanger_mapping.get(base_class)
            
            if expected_hanger:
                has_hanger = any(h['class_name'] == expected_hanger for h in hanger_detections)
                status = "✓" if has_hanger else "❌"
                print(f"  {status} {class_name:40s} → expects: {expected_hanger:20s} (found: {has_hanger})")
            else:
                print(f"  ⚪ {class_name:40s} → No hanger required (e.g., Clinic Plus)")
    else:
        print("  No sachets detected")
    
    # ========================================================================
    # STEP 6: Run Compliance Checks
    # ========================================================================
    
    print_section("STEP 6: Running Compliance Checks")
    
    try:
        compliance_score, product_accuracy, additional_checks = calculate_sachet_compliance(
            detected_products,
            detections
        )
        
        print(f"\n📊 Compliance Score: {compliance_score}%")
        
        print(f"\n🔍 Slot Adherence Check:")
        slot_check = additional_checks.get('slot_adherence', {})
        print(f"  Status: {slot_check.get('status', 'N/A')}")
        print(f"  Adherence: {slot_check.get('adherence', 'N/A')}")
        print(f"  Correctly placed: {slot_check.get('correctly_placed', 0)}/{slot_check.get('total_sachets', 0)}")
        
        misplaced = slot_check.get('misplaced_sachets', [])
        if misplaced:
            print(f"\n  ⚠️  Misplaced sachets: {len(misplaced)}")
            for m in misplaced:
                print(f"    • {m.get('sachet_name', 'Unknown')}: {m.get('reason', 'No reason')}")
        
        print(f"\n🔄 Orientation Adherence Check:")
        orientation_check = additional_checks.get('orientation_adherence', {})
        print(f"  Status: {orientation_check.get('status', 'N/A')}")
        print(f"  Adherence: {orientation_check.get('adherence', 'N/A')}")
        print(f"  Correctly oriented: {orientation_check.get('correctly_oriented', 0)}/{orientation_check.get('total_sachets', 0)}")
        
        rotated = orientation_check.get('rotated_sachets', [])
        if rotated:
            print(f"\n  ⚠️  Rotated sachets: {len(rotated)}")
            for r in rotated:
                print(f"    • {r.get('sachet_name', 'Unknown')}")
        
        print(f"\n🏢 Hanger Analysis:")
        print(f"  Combined hanger: {additional_checks.get('combined_hanger', 'N/A')}")
        print(f"  Brand exclusive: {additional_checks.get('brand_exclusive_hanger', 'N/A')}")
        
        print(f"\n📦 Product Accuracy:")
        for p in product_accuracy:
            if not p.get('is_hanger', False):  # Don't show hangers
                print(f"  • {p['name']:40s} | visible: {p['visible']:2d} | planned: {p['planned']:2d} | accuracy: {p['accuracy']}%")
        
    except Exception as e:
        print(f"❌ Compliance check failed: {e}")
        import traceback
        traceback.print_exc()
    
    # ========================================================================
    # STEP 7: Configuration Check
    # ========================================================================
    
    print_section("STEP 7: Configuration Verification")
    
    print(f"\n🔧 Horizontal overlap threshold: {sachet_compliance.horizontal_overlap_threshold}")
    print(f"   (1.0 = 100% overlap required, 0.5 = 50% overlap)")
    
    print(f"\n📋 Expected hanger classes in config:")
    unilever_hangers = sachet_compliance.unilever_hangers if hasattr(sachet_compliance, 'unilever_hangers') else []
    for h in sorted(unilever_hangers):
        detected = any(d['class_name'] == h for d in detections)
        status = "✓ DETECTED" if detected else "❌ NOT FOUND"
        print(f"  {status:15s} | {h}")
    
    print_section("TEST COMPLETE")
    print("\n💡 Analysis:")
    print(f"  • Model detected {hanger_count} hangers and {sachet_count} sachets")
    print(f"  • Compliance system identified {len(hanger_detections)} hangers")
    
    if hanger_count == 0:
        print("\n⚠️  ISSUE: Model is NOT detecting any hanger classes!")
        print("   → The SACHET_YOLO11X model may not be trained to detect hangers")
        print("   → Or hanger class names in model don't match config expectations")
    elif len(hanger_detections) == 0 and hanger_count > 0:
        print("\n⚠️  ISSUE: Model detects hangers but is_hanger() doesn't recognize them!")
        print("   → Check class name mismatches between model and config")
    elif len(hanger_detections) > 0:
        print("\n✓ Hanger detection appears to be working")
        if slot_check.get('adherence') == False:
            print("   But slot adherence failed - sachets may be misaligned")
    
    if rotated_count > 0:
        print(f"\n✓ Model detects {rotated_count} rotated sachets (_rotate suffix)")
    else:
        print("\n⚠️  Model may not distinguish rotated sachets")
        print("   → Orientation adherence will always pass")
    
    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    main()
