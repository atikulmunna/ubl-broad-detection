#!/usr/bin/env python3
"""
Category analysis script for UBL products.

Analyzes detected products and groups them into broad categories:
- Haircare
- Oralcare
- Skincare
- Home and Hygiene
- Food and Nutrition

This script uses a trained model to detect products and then categorizes them
based on their class names to provide insights into product mix.
"""

import argparse
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLO
from collections import defaultdict


# Category mapping: maps class names to broader categories
CATEGORY_MAPPING = {
    # Haircare
    'sunsilk_black_large': 'haircare',
    'sunsilk_black_small': 'haircare',
    'sunsilk_fresh': 'haircare',
    'sunsilk_hfs': 'haircare',
    'sunsilk_hfs_rinse': 'haircare',
    'sunsilk_hrr': 'haircare',
    'sunsilk_onion': 'haircare',
    'sunsilk_serum_25': 'haircare',
    'sunsilk_tl_large': 'haircare',
    'sunsilk_tl_small': 'haircare',
    'sunsilk_volume': 'haircare',
    'tresemme_cr': 'haircare',
    'treseme_sampoo_bond_plex': 'haircare',
    'tresemme_ks_large': 'haircare',
    'tresemme_ks_small': 'haircare',
    'tresemme_ks_white': 'haircare',
    'tresemme_mask_25': 'haircare',
    'tresemme_serum_25': 'haircare',
    'dove_cond': 'haircare',
    'dove_hfr_large': 'haircare',
    'dove_hfr_small': 'haircare',
    'dove_hg': 'haircare',
    'dove_irp_large': 'haircare',
    'dove_irp_small': 'haircare',
    'dove_mask_25': 'haircare',
    'dove_no': 'haircare',
    'dove_oxg': 'haircare',
    'clear_ahf': 'haircare',
    'clear_cac': 'haircare',
    'clear_csm_large': 'haircare',
    'clear_csm_small': 'haircare',

    # Oralcare
    'pepsodent_advanced_salt': 'oralcare',
    'pepsodent_germicheck': 'oralcare',
    'pepsodent_sensitive_expert': 'oralcare',
    'closeup_lemon_salt': 'oralcare',

    # Skincare
    'gl_aryuvedic_crm': 'skincare',
    'gl_foundation_crm': 'skincare',
    'gl_insta_glow_fw': 'skincare',
    'gl_mltvit_crm': 'skincare',
    'gl_sunscrn_crm': 'skincare',
    'ponds_oil_control_fw': 'skincare',
    'ponds_pure_white_clay_fw': 'skincare',
    'ponds_pure_white_fw': 'skincare',
    'ponds_white_beauty_clay_fw': 'skincare',
    'ponds_white_beauty_crm': 'skincare',
    'ponds_white_beauty_fw': 'skincare',
    'dove_nr_lotion': 'skincare',
    'lux_blk_orchd': 'skincare',
    'lux_brightening_vitamin': 'skincare',
    'lux_freeasia_scnt': 'skincare',
    'lux_french_rose': 'skincare',
    'vaseline_aloe': 'skincare',
    'vaseline_gluta_flawless': 'skincare',
    'vaseline_gluta_rad': 'skincare',
    'vaseline_hw': 'skincare',
    'vaseline_tm': 'skincare',

    # Home and Hygiene
    'lifebuoy_pump': 'homeandhygiene',
    'lifebuoy_refill_pouch': 'homeandhygiene',
    'surf_excel_matic_1l': 'homeandhygiene',
    'surf_excel_matic_500ml': 'homeandhygiene',
    'vim_liquid_500ml': 'homeandhygiene',

    # Food and Nutrition
    'horlicks_choco': 'foodandnutrition',
    'horlicks_junior': 'foodandnutrition',
    'horlicks_junior_s1': 'foodandnutrition',
    'horlicks_lite': 'foodandnutrition',
    'horlicks_mother': 'foodandnutrition',
    'horlicks_std': 'foodandnutrition',
    'horlicks_women': 'foodandnutrition',
    'boost_std': 'foodandnutrition',
    'maltova_std': 'foodandnutrition',
}

# Category colors for visualization (BGR format)
CATEGORY_COLORS = {
    'haircare': (0, 165, 255),      # Orange
    'oralcare': (255, 255, 0),      # Cyan
    'skincare': (203, 192, 255),    # Pink
    'homeandhygiene': (0, 255, 0),  # Green
    'foodandnutrition': (0, 0, 255),# Red
}

# Friendly category names for display
CATEGORY_DISPLAY_NAMES = {
    'haircare': 'Haircare',
    'oralcare': 'Oralcare',
    'skincare': 'Skincare',
    'homeandhygiene': 'Home & Hygiene',
    'foodandnutrition': 'Food & Nutrition',
}


def categorize_detections(results, model):
    """
    Categorize detected products into broad categories.

    Returns:
        dict: Category counts and detection information
    """
    category_counts = defaultdict(int)
    category_detections = defaultdict(list)

    boxes = results.boxes
    for i, box in enumerate(boxes):
        # Get class ID and name
        class_id = int(box.cls[0])
        class_name = model.names[class_id]

        # Get category from mapping
        category = CATEGORY_MAPPING.get(class_name, 'unknown')

        # Increment count
        category_counts[category] += 1

        # Store detection info
        category_detections[category].append({
            'box': box.xyxy[0].cpu().numpy(),
            'class_name': class_name,
            'confidence': float(box.conf[0]),
        })

    return dict(category_counts), dict(category_detections)


def draw_category_results(image, category_detections):
    """
    Draw bounding boxes on image with different colors for each category.
    """
    img_draw = image.copy()

    for category, detections in category_detections.items():
        color = CATEGORY_COLORS.get(category, (128, 128, 128))  # Gray for unknown

        for detection in detections:
            box = detection['box']
            x1, y1, x2, y2 = map(int, box)

            # Draw bounding box
            cv2.rectangle(img_draw, (x1, y1), (x2, y2), color, 2)

            # Draw label with category and product name
            label = CATEGORY_DISPLAY_NAMES.get(category, category)
            cv2.putText(img_draw, label, (x1, y1-5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    return img_draw


def draw_category_pie_chart(image, category_counts, total):
    """
    Draw a simple pie chart visualization on the image.
    """
    # This is a simple bar chart instead of pie for simplicity
    # Position it on the right side of the image
    height, width = image.shape[:2]
    chart_width = 300
    chart_x = width - chart_width - 20
    chart_y = 150

    # Sort categories by count
    sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)

    bar_height = 40
    for i, (category, count) in enumerate(sorted_categories):
        y_pos = chart_y + i * (bar_height + 10)

        # Calculate bar width based on percentage
        percentage = (count / total * 100) if total > 0 else 0
        bar_width = int((chart_width - 100) * (count / total)) if total > 0 else 0

        # Draw bar background
        cv2.rectangle(image, (chart_x, y_pos),
                     (chart_x + chart_width - 100, y_pos + bar_height),
                     (50, 50, 50), -1)

        # Draw bar
        color = CATEGORY_COLORS.get(category, (128, 128, 128))
        cv2.rectangle(image, (chart_x, y_pos),
                     (chart_x + bar_width, y_pos + bar_height),
                     color, -1)

        # Draw text
        display_name = CATEGORY_DISPLAY_NAMES.get(category, category)
        text = f"{display_name}: {count} ({percentage:.1f}%)"
        cv2.putText(image, text, (chart_x + 5, y_pos + 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    return image


def analyze_categories(image_path, model_path, confidence=0.25, output_dir='results'):
    """
    Run detection and categorize products into broad categories.
    """
    print("="*60)
    print("UBL Category Analysis")
    print("="*60)
    print(f"Image: {image_path}")
    print(f"Model: {model_path}")
    print(f"Confidence threshold: {confidence}")
    print("="*60)
    print()

    # Load image
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"Error: Could not load image {image_path}")
        return

    # Load model
    print("Loading model...")
    model = YOLO(model_path)
    print("Model loaded successfully!")
    print()

    # Run detection
    print("Detecting products...")
    results = model(image, conf=confidence, verbose=False)[0]
    total_detections = len(results.boxes)
    print(f"Detected {total_detections} products")
    print()

    # Categorize detections
    print("Categorizing products...")
    category_counts, category_detections = categorize_detections(results, model)
    print()

    # Print results
    print("="*60)
    print("CATEGORY BREAKDOWN")
    print("="*60)
    print(f"Total Products Detected: {total_detections}")
    print()

    # Sort by count
    sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    for category, count in sorted_categories:
        display_name = CATEGORY_DISPLAY_NAMES.get(category, category)
        percentage = (count / total_detections * 100) if total_detections > 0 else 0
        print(f"{display_name:20s}: {count:3d} products ({percentage:5.1f}%)")

    print("="*60)
    print()

    # Visualize results
    print("Creating visualization...")
    result_image = draw_category_results(image, category_detections)

    # Add title
    overlay = result_image.copy()
    height, width = result_image.shape[:2]

    # Draw semi-transparent background for title
    cv2.rectangle(overlay, (10, 10), (400, 60), (0, 0, 0), -1)
    result_image = cv2.addWeighted(result_image, 0.7, overlay, 0.3, 0)

    # Add title text
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(result_image, f'Total Products: {total_detections}',
               (20, 45), font, 1.0, (255, 255, 255), 2)

    # Add category breakdown chart
    result_image = draw_category_pie_chart(result_image, category_counts, total_detections)

    # Save result
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    image_name = Path(image_path).stem
    output_file = output_path / f"{image_name}_category_analysis.jpg"
    cv2.imwrite(str(output_file), result_image)

    print(f"Result saved to: {output_file}")
    print()

    return {
        'total_products': total_detections,
        'category_counts': category_counts,
        'output_file': str(output_file),
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description='Category analysis for UBL products'
    )
    parser.add_argument('image', type=str, help='Path to input image')
    parser.add_argument('--model', type=str,
                       default='models/best_ubl_shelf.pt',
                       help='Path to trained YOLO model')
    parser.add_argument('--confidence', type=float, default=0.25,
                       help='Confidence threshold for detections')
    parser.add_argument('--output-dir', type=str, default='results',
                       help='Output directory for results')
    return parser.parse_args()


def main():
    args = parse_args()

    # Check if files exist
    if not Path(args.image).exists():
        print(f"Error: Image not found: {args.image}")
        return

    if not Path(args.model).exists():
        print(f"Error: Model not found: {args.model}")
        return

    # Run analysis
    analyze_categories(
        args.image,
        args.model,
        args.confidence,
        args.output_dir
    )


if __name__ == '__main__':
    main()
