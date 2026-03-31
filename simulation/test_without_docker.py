#!/usr/bin/env python3
"""
Full Analysis Test - Tests complete AI server logic with compliance
Usage: python3 test_full_analysis.py
"""

import sys
import asyncio
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent / 'ai-server'))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import AI server functions
from main import (
    analyze_fixed_shelf,
    analyze_share_of_shelf,
    analyze_sachet,
    analyze_posm
)

async def test_full_analysis():
    print("\n" + "="*60)
    print("FULL AI ANALYSIS TEST (With Compliance)")
    print("="*60)
    
    # Get image path
    print("\nStep 1: Which image do you want to test?")
    print("Example: examples/DA/01.jpg")
    image_path = input("\nImage path: ").strip()
    
    if not Path(image_path).exists():
        print(f"\n✗ Error: File not found: {image_path}")
        return
    
    # Get task type
    print("\n" + "-"*60)
    print("Step 2: What type of analysis?")
    print("  1. Fixed Shelf (QPDS) - Full compliance")
    print("  2. Share of Shelf")
    print("  3. Sachet")
    print("  4. POSM")
    task_choice = input("\nEnter number (1-4): ").strip()
    
    # Read image
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    print("\n" + "="*60)
    print("PROCESSING WITH FULL AI SERVER LOGIC")
    print("="*60)
    
    # Run analysis
    if task_choice == '1':
        # Get shelf type
        print("\nShelf types:")
        shelf_types = [
            "Hair Care Premium QPDS",
            "Winter Lotion QPDS",
            "Perfect Store - Hair",
            "Perfect Store - Glow & Lovely",
            "Perfect Store - Ponds",
            "Lux Bodywash QPDS",
            "Vim Liquid QPDS",
            "Oral Care QPDS",
            "Junior Clean Corner QPDS",
            "Nutrition Store QPDS Single Shelf (1:1)",
            "Nutrition Store QPDS Single Shelf (1:2)",
            "Nutrition Store QPDS Double Shelf (2:1)",
            "Nutrition Store QPDS Double Shelf (2:2)"
        ]
        
        for i, st in enumerate(shelf_types, 1):
            print(f"  {i}. {st}")
        
        shelf_choice = input("\nEnter number (1-13): ").strip()
        shelf_type = shelf_types[int(shelf_choice) - 1] if shelf_choice.isdigit() else None
        
        print(f"\n🔍 Running Fixed Shelf analysis...")
        print(f"   Shelf Type: {shelf_type}")
        result = await analyze_fixed_shelf(image_data, worker_id=0, shelf_type=shelf_type)
        
    elif task_choice == '2':
        print(f"\n🔍 Running Share of Shelf analysis...")
        result = await analyze_share_of_shelf(image_data, worker_id=0)
        
    elif task_choice == '3':
        print(f"\n🔍 Running Sachet analysis...")
        result = await analyze_sachet(image_data, worker_id=0)
        
    elif task_choice == '4':
        print(f"\n🔍 Running POSM analysis...")
        result = await analyze_posm(image_data, worker_id=0)
    else:
        print("Invalid choice")
        return
    
    # Print results
    print("\n" + "="*60)
    print("COMPLETE RESULTS (WITH COMPLIANCE)")
    print("="*60)
    
    import json
    print(json.dumps(result, indent=2))
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"\n{result.get('summary', 'Complete')}")
    
    # Highlight compliance metrics
    if 'variant_compliance' in result:
        print(f"\n📊 Variant Compliance: {result['variant_compliance']}%")
    
    if 'planogram_adherence' in result:
        status = "✅ PASS" if result['planogram_adherence'] else "❌ FAIL"
        print(f"📋 Planogram Adherence: {status}")
    
    if 'shelftalker_adherence' in result:
        status = "✅ PASS" if result['shelftalker_adherence'] else "❌ FAIL"
        print(f"🏷️  Shelftalker Adherence: {status}")
    
    if 'exclusivity_status' in result:
        status = "✅ YES" if result['exclusivity_status'] == 'yes' else "❌ NO"
        print(f"🔒 Exclusivity: {status}")
        if result.get('non_ubl_count', 0) > 0:
            print(f"   Non-UBL Products: {result['non_ubl_products']}")
    
    if 'size_summary' in result and result['size_summary']:
        print(f"\n📏 Size Variants Detected:")
        for product, sizes in result['size_summary'].items():
            print(f"   {product}: {sizes}")
    
    if 'product_accuracy' in result and result['product_accuracy']:
        print(f"\n🎯 Product Accuracy:")
        for item in result['product_accuracy']:
            print(f"   {item['name']}: {item['visible']}/{item['planned']} = {item['accuracy']}%")
    
    if 'compliance_score' in result:
        print(f"\n📊 Overall Compliance: {result['compliance_score']}%")
    
    print("\n" + "="*60)
    print("✓ Test completed!")
    print("="*60 + "\n")


if __name__ == '__main__':
    try:
        asyncio.run(test_full_analysis())
    except KeyboardInterrupt:
        print("\n\n✗ Test cancelled\n")
    except Exception as e:
        print(f"\n\n✗ Error: {e}\n")
        import traceback
        traceback.print_exc()
