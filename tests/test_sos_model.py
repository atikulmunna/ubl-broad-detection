#!/usr/bin/env python3
"""
Interactive SOS Model Inference Test
Tests DA_YOLO11X.pt model on ShareOfShelf images
"""
import os
import sys
from pathlib import Path
from ultralytics import YOLO
from PIL import Image

# Add parent directory to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.brand_mapper import extract_brand_from_product
from utils.sos_category_mapping import get_sos_category

# Paths (relative to project root)
MODEL_PATH = PROJECT_ROOT / "models" / "DA_YOLO11X.pt"
EXAMPLES_DIR = PROJECT_ROOT / "examples" / "ShareOfShelf"

def list_images():
    """List all images in ShareOfShelf examples directory"""
    if not EXAMPLES_DIR.exists():
        print(f"Error: {EXAMPLES_DIR} not found")
        return []

    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
    images = [f for f in EXAMPLES_DIR.iterdir()
              if f.suffix.lower() in image_extensions]

    return sorted(images)

def display_detections(results, show_details=True):
    """Display detection results with brand and category info"""
    if not results or len(results) == 0:
        print("No detections found")
        return

    result = results[0]

    if not result.boxes or len(result.boxes) == 0:
        print("No objects detected")
        return

    # Group detections by class
    from collections import defaultdict
    detections_by_class = defaultdict(int)

    for box, cls_id, conf in zip(result.boxes.xyxy, result.boxes.cls, result.boxes.conf):
        class_name = result.names[int(cls_id)]
        detections_by_class[class_name] += 1

    print(f"\n{'='*80}")
    print(f"TOTAL DETECTIONS: {len(result.boxes)}")
    print(f"UNIQUE CLASSES: {len(detections_by_class)}")
    print(f"{'='*80}\n")

    # Show detections grouped by class
    print(f"{'CLASS NAME':<40} {'COUNT':>6} {'BRAND':<20} {'CATEGORY':<20}")
    print(f"{'-'*40} {'-'*6} {'-'*20} {'-'*20}")

    for class_name in sorted(detections_by_class.keys()):
        count = detections_by_class[class_name]
        brand = extract_brand_from_product(class_name)
        category = get_sos_category(class_name) or "unknown"

        print(f"{class_name:<40} {count:>6} {brand:<20} {category:<20}")

    # Show detailed detection info if requested
    if show_details:
        print(f"\n{'='*80}")
        print("DETAILED DETECTIONS (with confidence scores)")
        print(f"{'='*80}\n")

        print(f"{'CLASS NAME':<40} {'CONF':>6} {'BOX (x1,y1,x2,y2)':<40}")
        print(f"{'-'*40} {'-'*6} {'-'*40}")

        for box, cls_id, conf in zip(result.boxes.xyxy, result.boxes.cls, result.boxes.conf):
            class_name = result.names[int(cls_id)]
            conf_val = float(conf)
            x1, y1, x2, y2 = box.tolist()

            print(f"{class_name:<40} {conf_val:>6.2f} ({int(x1)},{int(y1)},{int(x2)},{int(y2)})")

def run_inference(image_path, conf=0.20):
    """Run inference on an image"""
    print(f"\nLoading model: {MODEL_PATH}")
    model = YOLO(MODEL_PATH)

    # Get model info
    print(f"Model loaded successfully!")
    print(f"Total classes in model: {len(model.names)}")
    print(f"Confidence threshold: {conf}")

    print(f"\nRunning inference on: {image_path}")
    results = model.predict(
        source=str(image_path),
        conf=conf,
        verbose=False
    )

    return results

def main():
    """Main interactive loop"""
    print("="*80)
    print("SOS MODEL INFERENCE TESTER (DA_YOLO11X.pt)")
    print("="*80)

    # Check if model exists
    if not MODEL_PATH.exists():
        print(f"\nError: Model not found at {MODEL_PATH}")
        return

    while True:
        print("\n" + "="*80)
        print("OPTIONS:")
        print("  1. Select from example images")
        print("  2. Enter custom image path")
        print("  3. Quit")
        print("="*80)

        choice = input("\nEnter choice (1/2/3): ").strip()

        if choice == "3":
            print("Exiting...")
            break

        elif choice == "1":
            # List available images
            images = list_images()
            if not images:
                continue

            print(f"\nAvailable images in examples/ShareOfShelf:")
            for i, img in enumerate(images, 1):
                print(f"  {i}. {img.name}")

            try:
                img_choice = int(input(f"\nSelect image (1-{len(images)}): ").strip())
                if 1 <= img_choice <= len(images):
                    selected_image = images[img_choice - 1]
                else:
                    print("Invalid selection")
                    continue
            except ValueError:
                print("Invalid input")
                continue

        elif choice == "2":
            # Custom path
            custom_path = input("\nEnter image path: ").strip()
            selected_image = Path(custom_path)

            if not selected_image.exists():
                print(f"Error: File not found at {custom_path}")
                continue

        else:
            print("Invalid choice")
            continue

        # Ask for confidence threshold
        try:
            conf_input = input("\nConfidence threshold (0.0-1.0 or 0-100%, default 0.20, press Enter to use default): ").strip()
            if conf_input:
                conf = float(conf_input)
                # Auto-convert if user entered percentage (>1.0)
                if conf > 1.0:
                    conf = conf / 100.0
                    print(f"  → Converted to {conf:.2f}")
                # Validate range
                if not (0.0 <= conf <= 1.0):
                    print(f"  → Invalid confidence {conf}, using default 0.20")
                    conf = 0.20
            else:
                conf = 0.20
        except ValueError:
            print("  → Invalid input, using default 0.20")
            conf = 0.20

        # Ask if user wants detailed view
        details_input = input("Show detailed detections with bounding boxes? (y/n, default n): ").strip().lower()
        show_details = details_input == 'y'

        # Run inference
        try:
            results = run_inference(selected_image, conf=conf)
            display_detections(results, show_details=show_details)
        except Exception as e:
            print(f"Error during inference: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
