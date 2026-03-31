"""
Simple Production Uploader - Uses Existing Backend Endpoints

Workflow:
1. Create visit_call → get visit_id
2. Submit images via /visit-call-submit/{visit_id}
3. Upload to S3 using presigned URLs
4. AI processes automatically
"""

import os
import time
import threading
import numpy as np
import requests
import boto3
from typing import Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8081")
# BACKEND_URL = "https://cleaning-door-virgin-holdings.trycloudflare.com"
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")

# Dev login credentials
LOGIN_EMAIL = "cm@example.com"
LOGIN_PASSWORD = "cm@example.com"
LOGIN_SECRET_KEY = "your_secret_key_here_change_in_production"

# S3 Configuration for metadata verification
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:4566")
S3_BUCKET = os.getenv("S3_BUCKET", "ubl-shop-audits")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "test")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")



def auto_login() -> str:
    """Auto-login with dev credentials, return access_token"""
    url = f"{BACKEND_URL}/login"
    payload = {
        "secret_key": LOGIN_SECRET_KEY,
        "email": LOGIN_EMAIL,
        "password": LOGIN_PASSWORD,
        "app_version": "1.0.0"
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()["access_token"]


def create_visit_call(pjp_mapping_id: str, outlet_id: str, visitor_id: str, execution_date: str) -> str:
    """Create visit call and return visit_id"""
    url = f"{BACKEND_URL}/visit-calls"
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "pjp_mapping_id": pjp_mapping_id,
        "outlet_id": outlet_id,
        "visitor_id": visitor_id,
        "execution_date": execution_date,
        "is_executed": True
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()["data"]["visit_id"]


def get_visit_call(visit_id: str) -> Dict:
    """Fetch visit call data from backend"""
    url = f"{BACKEND_URL}/visit-calls/{visit_id}"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()["data"]


def list_images_from_visit(visit_call: Dict) -> list:
    """Extract all images with upload_ids from visit call"""
    images = []
    # Extract from category_shelf_display
    for display in visit_call.get("category_shelf_display", []):
        if display.get("upload_id"):
            images.append({
                "index": len(images) + 1,
                "category": "fixed_shelf",
                "name": display.get("name"),
                "upload_id": display.get("upload_id"),
                "slab": display.get("slab", ""),
                "channel": display.get("channel", "")
            })
    # Extract from share_of_posm
    for posm in visit_call.get("share_of_posm", []):
        for img in posm.get("images", []):
            if img.get("upload_id"):
                images.append({
                    "index": len(images) + 1,
                    "category": "posm",
                    "name": posm.get("name"),
                    "upload_id": img.get("upload_id"),
                    "image_index": img.get("image_index")
                })
    # Extract from share_of_shelf
    for shelf in visit_call.get("share_of_shelf", []):
        for subcat in shelf.get("sub_categories", []):
            for img in subcat.get("images", []):
                if img.get("upload_id"):
                    images.append({
                        "index": len(images) + 1,
                        "category": "share_of_shelf",
                        "name": shelf.get("name"),
                        "sub_category": subcat.get("sub_category"),
                        "upload_id": img.get("upload_id")
                    })
    # Extract from share_of_sachet
    sachet = visit_call.get("share_of_sachet", {})
    for img in sachet.get("images", []):
        if img.get("upload_id"):
            images.append({
                "index": len(images) + 1,
                "category": "sachet",
                "name": "sachet",
                "upload_id": img.get("upload_id")
            })
    # Extract from sovm
    sovm = visit_call.get("sovm", {})
    for img in sovm.get("images", []):
        if img.get("upload_id"):
            images.append({
                "index": len(images) + 1,
                "category": "sovm",
                "name": "sovm",
                "upload_id": img.get("upload_id")
            })
    return images


def submit_retake_image(visit_id: str, upload_id: str, retake_count: int, slab: str = "", channel: str = "") -> Dict:
    """Submit single retake and get presigned URL"""
    url = f"{BACKEND_URL}/retake-submit"
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "visit_id": visit_id,
        "upload_id": upload_id,
        "is_retake": True,
        "retake_count": retake_count,
        "slab": slab,
        "channel": channel
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def submit_images(visit_id: str, outlet_id: str, user_id: str, images: list, expected_count: int) -> Dict:
    """Submit images and get presigned URLs"""
    url = f"{BACKEND_URL}/visit-call-submit/{visit_id}"
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }

    # Build payload based on image types
    category_shelf_display = []
    share_of_shelf = []
    share_of_posm = []
    share_of_sachet = {}
    sovm = {}
    sachet_count = 0
    sachet_remarks = ""
    sachet_retake = False
    sachet_retake_count = 0
    sovm_count = 0
    sovm_retake = False
    sovm_retake_count = 0

    for img in images:
        if img["image_type"] == "fixed_shelf":
            category_shelf_display.append({
                "name": os.path.basename(img["image_path"]),
                "remarks": img.get("remarks", ""),
                "slab": img.get("slab", ""),
                "channel": img.get("channel", ""),
                "retake": img.get("retake", False),
                "retake_count": img.get("retake_count", 0)
            })
        elif img["image_type"] == "share_of_shelf":
            sub_cat = img.get("sub_category", "hair_care")
            share_of_shelf.append({
                "name": "Share of Shelf",
                "sub_categories": {
                    sub_cat: 1
                },
                "retake": img.get("retake", False),
                "retake_count": img.get("retake_count", 0)
            })
        elif img["image_type"] == "posm":
            share_of_posm.append({
                "name": img.get("posm_name", ""),
                "posm_id": img.get("posm_id", ""),
                "attached_posm": img.get("attached_posm", 0),
                "image_upload_quantity": img.get("image_upload_quantity", 1),
                "retake": img.get("retake", False),
                "retake_count": img.get("retake_count", 0)
            })
        elif img["image_type"] == "sachet":
            if sachet_count == 0:
                # Store retake info from first sachet
                sachet_retake = img.get("retake", False)
                sachet_retake_count = img.get("retake_count", 0)
            sachet_count += 1
            sachet_remarks = img.get("remarks", "")
        elif img["image_type"] == "sovm":
            if sovm_count == 0:
                # Store retake info from first sovm
                sovm_retake = img.get("retake", False)
                sovm_retake_count = img.get("retake_count", 0)
            sovm_count += 1

    # Build share_of_sachet payload based on count
    if sachet_count > 0:
        share_of_sachet = {
            "sachet_image": sachet_count,
            "remarks": sachet_remarks,
            "retake": sachet_retake,
            "retake_count": sachet_retake_count
        }

    # Build sovm payload based on count
    if sovm_count > 0:
        sovm = {
            "sovm_image": sovm_count,
            "retake": sovm_retake,
            "retake_count": sovm_retake_count
        }

    payload = {
        "user_id": user_id,
        "outlet_id": outlet_id,
        "expected_images_count": expected_count,
        "category_shelf_display": category_shelf_display,
        "share_of_shelf": share_of_shelf,
        "share_of_posm": share_of_posm,
        "share_of_sachet": share_of_sachet,
        "sovm": sovm
    }

    # Debug: print what we're sending
    import json
    print("\n[DEBUG] Sending payload:")
    print(json.dumps(payload, indent=2)[:1000])

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def upload_image(image_path: str, presigned_url: Dict) -> bool:
    """Upload image using presigned URL"""
    
    # DEBUG: Print what we're sending
    print(f"\n[DEBUG] Uploading to: {presigned_url['url']}")
    print(f"[DEBUG] Metadata fields being sent:")
    for key, value in presigned_url['fields'].items():
        if key.startswith('x-amz-meta-'):
            print(f"  {key}: {value}")
    
    with open(image_path, 'rb') as f:
        response = requests.post(
            presigned_url['url'],
            data=presigned_url['fields'],
            files={'file': f}
        )
    
    print(f"[DEBUG] Upload response status: {response.status_code}")
    if response.status_code not in [200, 204]:
        print(f"[DEBUG] Upload response text: {response.text}")
    
    return response.status_code in [200, 204]


def verify_s3_metadata(s3_key: str) -> Dict:
    """Verify metadata on uploaded S3 object"""
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY,
            region_name=AWS_REGION
        )
        
        response = s3_client.head_object(Bucket=S3_BUCKET, Key=s3_key)
        metadata = response.get('Metadata', {})
        
        print(f"\n[VERIFICATION] S3 Metadata for: {s3_key}")
        print(f"  Total metadata keys: {len(metadata)}")
        
        # Check retake fields
        retake = metadata.get('retake', 'NOT FOUND')
        retake_count = metadata.get('retake-count', 'NOT FOUND')
        upload_id = metadata.get('upload-id', 'NOT FOUND')
        
        print(f"  retake: {retake}")
        print(f"  retake-count: {retake_count}")
        print(f"  upload-id: {upload_id}")
        
        if retake == 'true':
            print(f"  ✅ Retake flag is set correctly")
        else:
            print(f"  ❌ WARNING: Retake flag is '{retake}' (expected 'true')")
        
        return metadata
    except Exception as e:
        print(f"  ❌ Error verifying metadata: {e}")
        return {}


def main():
    global AUTH_TOKEN

    print("=" * 60)
    print("Simple Production S3 Uploader")
    print("=" * 60)

    # Choose upload method
    print("\nUpload Method:")
    print("1) Upload new images")
    print("2) Retake images for completed visit")
    print("3) Stress test - upload N visits with same image(s)")
    print("4) Quick test - automated with example images")
    upload_method = input("Select (1/2/3/4): ").strip()

    # Auto-login if no token
    if not AUTH_TOKEN:
        try:
            AUTH_TOKEN = auto_login()
            print(f"✓ Auto-login OK ({LOGIN_EMAIL})")
        except Exception as e:
            print(f"Auto-login failed: {e}")
            AUTH_TOKEN = input("Enter JWT token manually: ").strip()
            if not AUTH_TOKEN:
                print("❌ ERROR: Token cannot be empty")
                return

    if upload_method == "2":

        print("\n--- Retake Mode ---")
        visit_id = input("Visit ID: ").strip()

        try:
            # Fetch visit call
            print("Fetching visit call data...")
            visit_call = get_visit_call(visit_id)

            # List all images
            all_images = list_images_from_visit(visit_call)
            if not all_images:
                print("❌ No images found in visit call")
                return

            # Filter images by Retake field from AI results
            ai_result = visit_call.get("ai_result", {})
            ai_summary = ai_result.get("ai_summary", {})
            results = ai_summary.get("results", {})

            retake_images = []
            for img in all_images:
                upload_id = img["upload_id"]
                category = img["category"]
                needs_retake = False
                retake_reason = ""

                # Check CSD
                if category == "fixed_shelf":
                    csd_data = results.get("category_shelf_display", {})
                    for key, item in csd_data.items():
                        if item.get("upload_id") == upload_id:
                            if item.get("Retake") == "Yes":
                                needs_retake = True
                                retake_reason = f"Compliance: {item.get('overall_compliance', 0):.1f}%"
                            break

                # Check SOS
                elif category == "share_of_shelf":
                    brand_details = results.get("share_of_shelf", {}).get("brand_details", {})
                    for key, brand in brand_details.items():
                        if brand.get("upload_id") == upload_id:
                            if brand.get("Retake") == "Yes":
                                needs_retake = True
                                # Find UBL percentage for reason
                                category_name = brand.get("category_name")
                                for summary in results.get("share_of_shelf", {}).get("overall_summary", []):
                                    if summary.get("category_name") == category_name:
                                        retake_reason = f"UBL Share: {summary['share_percentage']['ubl']:.1f}%"
                                        break
                            break

                # Check POSM
                elif category == "posm":
                    posm_data = results.get("share_of_posm", {}).get("detailed_analysis", {})
                    if posm_data.get("Retake") == "Yes":
                        needs_retake = True
                        retake_reason = f"Accuracy: {posm_data.get('ubl_posm_ai_accuracy', 0):.1f}%"

                # Check SOVM
                elif category == "sovm":
                    sovm_data = results.get("sovm", {}).get("detailed_analysis", {})
                    if sovm_data.get("Retake") == "Yes":
                        needs_retake = True
                        retake_reason = f"UBL%: {sovm_data.get('ubl_percentage_by_count', 0):.1f}%"

                if needs_retake:
                    img["retake_reason"] = retake_reason
                    retake_images.append(img)

            if not retake_images:
                print("✓ All images passed quality thresholds - no retakes needed!")
                print(f"   Total images: {len(all_images)}")
                return

            # Re-index
            for idx, img in enumerate(retake_images, 1):
                img["index"] = idx

            print(f"\n--- Images Needing Retake ({len(retake_images)}/{len(all_images)}) ---")
            for img in retake_images:
                print(f"{img['index']}) [{img['category']}] {img['name']}")
                print(f"    Reason: {img['retake_reason']}")
                print(f"    upload_id: {img['upload_id']}")

            images = retake_images  # Use filtered list for rest of flow

            # Select images to retake
            retakes = []
            while True:
                choice = input("\nSelect image number to retake (or 'done'): ").strip()
                if choice == 'done':
                    break
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(images):
                        selected = images[idx]
                        retake_count = int(input(f"  Retake count for {selected['name']}: ").strip() or "1")
                        image_path = input(f"  Image path: ").strip()
                        image_path = os.path.expanduser(image_path)

                        if not os.path.exists(image_path):
                            print(f"  ❌ File not found: {image_path}")
                            continue

                        # For fixed_shelf, optionally provide slab and channel
                        slab = ""
                        channel = ""
                        if selected["category"] == "fixed_shelf":
                            slab = input(f"  Slab (planogram, e.g. ORAL_QPDS_JAN_26) [optional]: ").strip()
                            channel = input(f"  Channel (GBS/PBS/NPS) [optional]: ").strip()

                        retakes.append({
                            "upload_id": selected["upload_id"],
                            "retake_count": retake_count,
                            "image_path": image_path,
                            "name": selected["name"],
                            "slab": slab,
                            "channel": channel
                        })
                        print(f"  ✓ Added {selected['name']} for retake")
                    else:
                        print("  ❌ Invalid selection")
                except ValueError:
                    print("  ❌ Invalid input")

            if not retakes:
                print("No retakes selected. Exiting.")
                return

            # Process retakes
            print(f"\n--- Processing {len(retakes)} retakes ---")
            for i, retake in enumerate(retakes, 1):
                print(f"\n[{i}/{len(retakes)}] Retaking {retake['name']}...")

                # Submit retake
                result = submit_retake_image(
                    visit_id=visit_id,
                    upload_id=retake["upload_id"],
                    retake_count=retake["retake_count"],
                    slab=retake.get("slab", ""),
                    channel=retake.get("channel", "")
                )

                presigned_url = result["data"]["presigned_url"]
                s3_key = result["data"]["s3_key"]
                print("  ✓ Got presigned URL")
                
                # DEBUG: Show expected metadata
                print(f"\n[DEBUG] Expected metadata from presigned URL:")
                print(f"  upload-id: {presigned_url['fields'].get('x-amz-meta-upload-id')}")
                print(f"  retake: {presigned_url['fields'].get('x-amz-meta-retake')}")
                print(f"  retake-count: {presigned_url['fields'].get('x-amz-meta-retake-count')}")

                # Upload to S3
                if upload_image(retake["image_path"], presigned_url):
                    print(f"  ✓ Uploaded successfully")
                    
                    # VERIFY: Check if metadata was actually set on S3
                    time.sleep(1)  # Give S3 a moment
                    verify_s3_metadata(s3_key)
                else:
                    print(f"  ❌ Upload failed")

            print("\n" + "=" * 60)
            print("✓ Retake complete!")
            print("=" * 60)

        except Exception as e:
            print(f"❌ Error: {e}")
            if hasattr(e, 'response'):
                print(f"   Response: {e.response.text}")
        return

    elif upload_method == "3":
        # Stress test mode
        print("\n--- Stress Test Mode ---")

        # Get number of visits to create
        try:
            num_visits = int(input("Number of visits to create (e.g., 1000): ").strip())
            if num_visits <= 0:
                print("❌ Number must be positive")
                return
        except ValueError:
            print("❌ Invalid number")
            return

        # Get visit parameters
        print("\n--- Visit Call Template ---")
        pjp_mapping_id = input("PJP Mapping ID: ").strip()
        outlet_id_prefix = input("Outlet ID prefix (will append index): ").strip()
        visitor_id = input("Visitor ID: ").strip()
        execution_date = input("Execution Date (YYYY-MM-DD): ").strip()

        # Collect image template
        print("\n--- Image Template (will be uploaded to all visits) ---")
        template_images = []

        while True:
            print("\nImage types: 1) fixed_shelf  2) share_of_shelf  3) posm  4) sachet  5) sovm")
            choice = input("Select (or 'done'): ").strip()

            if choice == 'done':
                break

            image_path = input("Image path: ").strip()
            image_path = os.path.expanduser(image_path)

            if not os.path.exists(image_path):
                print(f"❌ File not found: {image_path}")
                continue

            img_config = {"image_path": image_path, "retake": False, "retake_count": 0}

            if choice == "1":
                img_config["image_type"] = "fixed_shelf"
                img_config["slab"] = input("  Slab: ").strip()
            elif choice == "2":
                img_config["image_type"] = "share_of_shelf"
                print("  Categories: hair_care, skin_care, oral_care, nutrition, fabric, skin_cleansing, home_and_hygiene, mini_meals")
                img_config["sub_category"] = input("  Sub-category: ").strip()
            elif choice == "3":
                img_config["image_type"] = "posm"
                posm_name = input("    POSM Name: ").strip()
                try:
                    attached_posm = int(input("    Quantity attached: ").strip() or "0")
                except:
                    attached_posm = 0
                try:
                    image_upload_quantity = int(input("    Photos to take: ").strip() or "1")
                except:
                    image_upload_quantity = 1
                img_config["posm_name"] = posm_name
                img_config["posm_id"] = ""
                img_config["attached_posm"] = attached_posm
                img_config["image_upload_quantity"] = image_upload_quantity
            elif choice == "4":
                img_config["image_type"] = "sachet"
            elif choice == "5":
                img_config["image_type"] = "sovm"
            else:
                print("❌ Invalid choice")
                continue

            template_images.append(img_config)
            print(f"✓ Added {img_config['image_type']}")

        if not template_images:
            print("No images. Exiting.")
            return

        # Confirm stress test
        print(f"\n{'=' * 60}")
        print(f"⚠️  STRESS TEST SUMMARY")
        print(f"{'=' * 60}")
        print(f"Visits to create: {num_visits}")
        print(f"Images per visit: {len(template_images)}")
        print(f"Total uploads: {num_visits * len(template_images)}")
        print(f"Image types: {', '.join([img['image_type'] for img in template_images])}")
        print(f"{'=' * 60}")
        confirm = input("\nProceed with stress test? (yes/no): ").strip().lower()

        if confirm != "yes":
            print("Cancelled.")
            return

        workers = int(input(f"Concurrent workers (default 10): ").strip() or "10")

        # Thread-safe counters
        lock = threading.Lock()
        progress = {"successful": 0, "failed": 0, "uploads": 0, "completed": 0}
        all_upload_times: List[float] = []

        def _process_single_visit(
            visit_num: int,
            images: list,
            pjp_mapping_id: str,
            outlet_id_prefix: str,
            visitor_id: str,
            execution_date: str,
        ) -> Tuple[bool, int, List[float]]:
            """Process one visit end-to-end. Returns (success, upload_count, upload_times)."""
            outlet_id = f"{outlet_id_prefix}_{visit_num}"
            upload_count = 0
            upload_times: List[float] = []

            try:
                # Create visit
                visit_id = create_visit_call(pjp_mapping_id, outlet_id, visitor_id, execution_date)

                # Submit images
                result = submit_images(visit_id, outlet_id, visitor_id, images, len(images))

                # Upload images sequentially (matches real app behavior)
                type_counters = {"fixed_shelf": 0, "share_of_shelf": 0, "posm": 0, "sachet": 0, "sovm": 0}
                all_ok = True

                for img in images:
                    img_type = img["image_type"]

                    try:
                        if img_type == "fixed_shelf":
                            idx = type_counters["fixed_shelf"]
                            presigned_url = result["data"]["category_shelf_display"][idx]["presigned_url"]
                            type_counters["fixed_shelf"] += 1
                        elif img_type == "share_of_shelf":
                            idx = type_counters["share_of_shelf"]
                            presigned_url = result["data"]["share_of_shelf"][idx]["sub_categories"][0]["images"][0]["presigned_url"]
                            type_counters["share_of_shelf"] += 1
                        elif img_type == "posm":
                            idx = type_counters["posm"]
                            presigned_url = result["data"]["share_of_posm"][idx]["images"][0]["presigned_url"]
                            type_counters["posm"] += 1
                        elif img_type == "sachet":
                            idx = type_counters["sachet"]
                            presigned_url = result["data"]["share_of_sachet"]["images"][idx]["presigned_url"]
                            type_counters["sachet"] += 1
                        elif img_type == "sovm":
                            idx = type_counters["sovm"]
                            presigned_url = result["data"]["sovm"]["images"][idx]["presigned_url"]
                            type_counters["sovm"] += 1

                        t0 = time.time()
                        with open(img["image_path"], 'rb') as f:
                            response = requests.post(
                                presigned_url['url'],
                                data=presigned_url['fields'],
                                files={'file': f}
                            )
                        elapsed_upload = time.time() - t0
                        upload_times.append(elapsed_upload)

                        if response.status_code in [200, 204]:
                            upload_count += 1
                        else:
                            all_ok = False

                    except Exception:
                        all_ok = False

                return (all_ok, upload_count, upload_times)

            except Exception:
                return (False, upload_count, upload_times)

        # Execute stress test
        start_time = time.time()

        print(f"\n{'=' * 60}")
        print(f"🚀 STARTING STRESS TEST ({workers} workers)")
        print(f"{'=' * 60}\n")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_single_visit,
                    i + 1,
                    template_images,
                    pjp_mapping_id,
                    outlet_id_prefix,
                    visitor_id,
                    execution_date,
                ): i + 1
                for i in range(num_visits)
            }

            for future in as_completed(futures):
                try:
                    success, uploads, times = future.result()
                except Exception:
                    success, uploads, times = False, 0, []

                with lock:
                    if success:
                        progress["successful"] += 1
                    else:
                        progress["failed"] += 1
                    progress["uploads"] += uploads
                    progress["completed"] += 1
                    all_upload_times.extend(times)

                    done = progress["completed"]
                    if done % 10 == 0 or done == num_visits:
                        elapsed = time.time() - start_time
                        rate = done / elapsed if elapsed > 0 else 0
                        eta = (num_visits - done) / rate if rate > 0 else 0
                        print(
                            f"  📊 Progress: {done}/{num_visits} visits | "
                            f"{progress['uploads']} uploads | "
                            f"{rate:.1f} visits/sec | ETA: {eta:.0f}s"
                        )

        # Final summary
        elapsed = time.time() - start_time
        total_expected_uploads = num_visits * len(template_images)

        print(f"\n{'=' * 60}")
        print(f"✅ STRESS TEST COMPLETE")
        print(f"{'=' * 60}")
        print(f"Total wall time: {elapsed:.2f}s")
        print(f"Workers: {workers}")
        print(f"Successful visits: {progress['successful']}/{num_visits}")
        print(f"Failed visits: {progress['failed']}/{num_visits}")
        print(f"Total uploads: {progress['uploads']}/{total_expected_uploads}")

        if all_upload_times:
            arr = np.array(all_upload_times)
            print(f"\nTIMING SUMMARY")
            print(
                f"  Uploads: {len(arr)} "
                f"(min={arr.min():.3f}s avg={arr.mean():.3f}s "
                f"max={arr.max():.3f}s p95={np.percentile(arr, 95):.3f}s)"
            )

        if elapsed > 0:
            print(f"  Throughput: {progress['uploads'] / elapsed:.1f} uploads/sec, {num_visits / elapsed:.1f} visits/sec")

        print(f"{'=' * 60}")
        return

    elif upload_method == "4":
        # Automated test — pre-configured with StressTest examples
        print("\n--- Quick Test (automated) ---")
        try:
            num_visits = int(input("Number of visits (default 10): ").strip() or "10")
        except ValueError:
            num_visits = 10
        workers = int(input("Concurrent upload workers (default 10): ").strip() or "10")

        # Auto-configured
        script_dir = os.path.dirname(os.path.abspath(__file__))
        examples_dir = os.path.join(script_dir, "../../examples/StressTest")
        pjp_mapping_id = "auto_test"
        outlet_id_prefix = "auto"
        visitor_id = "auto_tester"
        execution_date = time.strftime("%Y-%m-%d")

        template_images = [
            {
                "image_path": os.path.join(examples_dir, "DOUBLE_SHELF-fixed.jpeg"),
                "image_type": "fixed_shelf",
                "slab": "DOUBLE_SHELF",
                "retake": False, "retake_count": 0,
            },
            {
                "image_path": os.path.join(examples_dir, "hair_care-sos.jpeg"),
                "image_type": "share_of_shelf",
                "sub_category": "hair_care",
                "retake": False, "retake_count": 0,
            },
            {
                "image_path": os.path.join(examples_dir, "sachet.jpg"),
                "image_type": "sachet",
                "retake": False, "retake_count": 0,
            },
            {
                "image_path": os.path.join(examples_dir, "Wheel Poster Jan26-posm.jpg"),
                "image_type": "posm",
                "posm_name": "Wheel Poster Jan26",
                "posm_id": "",
                "attached_posm": 2,
                "image_upload_quantity": 1,
                "retake": False, "retake_count": 0,
            },
        ]

        # Verify images exist
        for img in template_images:
            if not os.path.exists(img["image_path"]):
                print(f"❌ Missing: {img['image_path']}")
                return

        print(f"\n{'=' * 60}")
        print(f"QUICK TEST: {num_visits} visits x {len(template_images)} images = {num_visits * len(template_images)} uploads")
        print(f"Images: fixed_shelf (DOUBLE_SHELF), SOS (hair_care), sachet, POSM (Wheel Poster Jan26)")
        print(f"{'=' * 60}")

        # Thread-safe counters
        lock = threading.Lock()
        progress = {"successful": 0, "failed": 0, "uploads": 0, "completed": 0}
        all_upload_times: List[float] = []

        def _process_single_visit_auto(visit_num):
            outlet_id = f"{outlet_id_prefix}_{visit_num}"
            upload_count = 0
            upload_times_local: List[float] = []
            try:
                visit_id = create_visit_call(pjp_mapping_id, outlet_id, visitor_id, execution_date)
                result = submit_images(visit_id, outlet_id, visitor_id, template_images, len(template_images))

                type_counters = {"fixed_shelf": 0, "share_of_shelf": 0, "posm": 0, "sachet": 0, "sovm": 0}
                all_ok = True
                for img in template_images:
                    img_type = img["image_type"]
                    try:
                        if img_type == "fixed_shelf":
                            idx = type_counters["fixed_shelf"]
                            presigned_url = result["data"]["category_shelf_display"][idx]["presigned_url"]
                            type_counters["fixed_shelf"] += 1
                        elif img_type == "share_of_shelf":
                            idx = type_counters["share_of_shelf"]
                            presigned_url = result["data"]["share_of_shelf"][idx]["sub_categories"][0]["images"][0]["presigned_url"]
                            type_counters["share_of_shelf"] += 1
                        elif img_type == "posm":
                            idx = type_counters["posm"]
                            presigned_url = result["data"]["share_of_posm"][idx]["images"][0]["presigned_url"]
                            type_counters["posm"] += 1
                        elif img_type == "sachet":
                            idx = type_counters["sachet"]
                            presigned_url = result["data"]["share_of_sachet"]["images"][idx]["presigned_url"]
                            type_counters["sachet"] += 1
                        elif img_type == "sovm":
                            idx = type_counters["sovm"]
                            presigned_url = result["data"]["sovm"]["images"][idx]["presigned_url"]
                            type_counters["sovm"] += 1

                        t0 = time.time()
                        with open(img["image_path"], 'rb') as f:
                            resp = requests.post(presigned_url['url'], data=presigned_url['fields'], files={'file': f})
                        upload_times_local.append(time.time() - t0)
                        if resp.status_code in [200, 204]:
                            upload_count += 1
                        else:
                            all_ok = False
                    except Exception:
                        all_ok = False
                return (all_ok, upload_count, upload_times_local)
            except Exception:
                return (False, upload_count, upload_times_local)

        start_time = time.time()
        print(f"\n🚀 Running ({workers} upload workers)...\n")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_process_single_visit_auto, i + 1): i + 1
                for i in range(num_visits)
            }
            for future in as_completed(futures):
                try:
                    success, uploads, times = future.result()
                except Exception:
                    success, uploads, times = False, 0, []

                with lock:
                    if success:
                        progress["successful"] += 1
                    else:
                        progress["failed"] += 1
                    progress["uploads"] += uploads
                    progress["completed"] += 1
                    all_upload_times.extend(times)

                    done = progress["completed"]
                    if done % max(1, num_visits // 10) == 0 or done == num_visits:
                        elapsed = time.time() - start_time
                        rate = done / elapsed if elapsed > 0 else 0
                        eta = (num_visits - done) / rate if rate > 0 else 0
                        print(
                            f"  Progress: {done}/{num_visits} visits | "
                            f"{progress['uploads']} uploads | "
                            f"{rate:.1f} visits/sec | ETA: {eta:.0f}s"
                        )

        elapsed = time.time() - start_time
        total_expected = num_visits * len(template_images)
        print(f"\n{'=' * 60}")
        print(f"COMPLETE")
        print(f"{'=' * 60}")
        print(f"Wall time: {elapsed:.2f}s")
        print(f"Visits: {progress['successful']}/{num_visits} ok, {progress['failed']} failed")
        print(f"Uploads: {progress['uploads']}/{total_expected}")
        if all_upload_times:
            arr = np.array(all_upload_times)
            print(f"Upload timing: min={arr.min():.3f}s avg={arr.mean():.3f}s max={arr.max():.3f}s p95={np.percentile(arr, 95):.3f}s")
        if elapsed > 0:
            print(f"Throughput: {progress['uploads'] / elapsed:.1f} uploads/sec, {num_visits / elapsed:.1f} visits/sec")
        print(f"{'=' * 60}")
        return

    # Backend endpoint mode (option 1)
    print("✓ Using backend endpoints")

    # Step 1: Create or use existing visit
    choice = input("\nCreate new visit? (yes/no): ").strip().lower()

    if choice == "yes":
        print("\n--- Create Visit Call ---")
        pjp_mapping_id = "123"
        outlet_id = "123"
        visitor_id = "123"
        execution_date = time.strftime("%Y-%m-%d")
        print(f"  Using defaults: pjp={pjp_mapping_id}, outlet={outlet_id}, date={execution_date}")

        try:
            visit_id = create_visit_call(pjp_mapping_id, outlet_id, visitor_id, execution_date)
            print(f"✓ Visit created: {visit_id}")
        except Exception as e:
            print(f"❌ Failed: {e}")
            return
    else:
        visit_id = input("Visit ID: ").strip()
        outlet_id = input("Outlet ID: ").strip() or "123"
        visitor_id = "123"

    # Step 2: Collect images
    print("\n--- Add Images ---")
    images = []

    while True:
        print("\nImage types: 1) fixed_shelf  2) share_of_shelf  3) posm  4) sachet  5) sovm")
        choice = input("Select (or 'done'): ").strip()

        if choice == 'done':
            break

        # Image selection
        _test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../examples/Test")
        _test_images = sorted([f for f in os.listdir(_test_dir) if os.path.isfile(os.path.join(_test_dir, f))]) if os.path.isdir(_test_dir) else []
        print("  Image source:")
        print("    a) Select from test images")
        print("    b) Paste path")
        _src = input("  Select (a/b): ").strip().lower()
        if _src == "a" and _test_images:
            for _i, _f in enumerate(_test_images, 1):
                print(f"    {_i}) {_f}")
            _pick = input(f"  Select (1-{len(_test_images)}): ").strip()
            try:
                image_path = os.path.join(_test_dir, _test_images[int(_pick) - 1])
            except (ValueError, IndexError):
                print("  Invalid selection")
                continue
        else:
            image_path = os.path.expanduser(input("  Path: ").strip())

        if not os.path.exists(image_path):
            print(f"❌ File not found: {image_path}")
            continue

        img_config = {"image_path": image_path, "retake": False, "retake_count": 0}

        if choice == "1":
            img_config["image_type"] = "fixed_shelf"
            # Load slab options from YAML
            try:
                import yaml
                yaml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../config/standards/qpds_standards.yaml")
                with open(yaml_path) as _f:
                    _slabs = list(yaml.safe_load(_f).get("shelf_types", {}).keys())
            except Exception:
                _slabs = []
            if _slabs:
                print("  Slabs:")
                for _i, _s in enumerate(_slabs, 1):
                    print(f"    {_i}) {_s}")
                _pick = input(f"  Select (1-{len(_slabs)}): ").strip()
                try:
                    img_config["slab"] = _slabs[int(_pick) - 1]
                except (ValueError, IndexError):
                    img_config["slab"] = _pick  # fallback to raw input
            else:
                img_config["slab"] = input("  Slab: ").strip()
        elif choice == "2":
            img_config["image_type"] = "share_of_shelf"
            print("  Categories: hair_care, skin_care, oral_care, nutrition, fabric, skin_cleansing, home_and_hygiene, mini_meals")
            img_config["sub_category"] = input("  Sub-category: ").strip()
        elif choice == "3":
            img_config["image_type"] = "posm"
            posm_name = input("  POSM Name: ").strip()
            try:
                attached_posm = int(input("  Quantity attached: ").strip() or "0")
            except:
                attached_posm = 0
            img_config["posm_name"] = posm_name
            img_config["posm_id"] = ""
            img_config["attached_posm"] = attached_posm
            img_config["image_upload_quantity"] = 1
        elif choice == "4":
            img_config["image_type"] = "sachet"
        elif choice == "5":
            img_config["image_type"] = "sovm"
        else:
            print("❌ Invalid choice")
            continue

        images.append(img_config)
        print(f"✓ Added {img_config['image_type']}")

    if not images:
        print("No images. Exiting.")
        return

    expected_count = len(images)

    # Step 3: Submit and upload
    print(f"\n--- Uploading {len(images)} images ---")

    # Backend submission with presigned URLs
    try:
        result = submit_images(visit_id, outlet_id, visitor_id, images, expected_count)
        print("✓ Got presigned URLs")

        # Debug: print response structure
        import json
        print("\n[DEBUG] Response structure:")
        print(json.dumps(result.get("data", {}), indent=2)[:2000])

        # Upload each image - track indices per type
        type_counters = {"fixed_shelf": 0, "share_of_shelf": 0, "posm": 0, "sachet": 0, "sovm": 0}

        for i, img in enumerate(images, 1):
            img_type = img["image_type"]
            print(f"\n[{i}/{len(images)}] Uploading {img_type}...")

            # Find presigned URL for this image
            try:
                if img_type == "fixed_shelf":
                    idx = type_counters["fixed_shelf"]
                    presigned_data = result["data"]["category_shelf_display"][idx]
                    presigned_url = presigned_data["presigned_url"]
                    type_counters["fixed_shelf"] += 1

                elif img_type == "share_of_shelf":
                    # share_of_shelf structure: [{"sub_categories": [{"images": [...]}]}]
                    idx = type_counters["share_of_shelf"]
                    presigned_data = result["data"]["share_of_shelf"][idx]["sub_categories"][0]["images"][0]
                    presigned_url = presigned_data["presigned_url"]
                    type_counters["share_of_shelf"] += 1

                elif img_type == "posm":
                    idx = type_counters["posm"]
                    presigned_data = result["data"]["share_of_posm"][idx]["images"][0]
                    presigned_url = presigned_data["presigned_url"]
                    type_counters["posm"] += 1

                elif img_type == "sachet":
                    idx = type_counters["sachet"]
                    presigned_data = result["data"]["share_of_sachet"]["images"][idx]
                    presigned_url = presigned_data["presigned_url"]
                    type_counters["sachet"] += 1

                elif img_type == "sovm":
                    idx = type_counters["sovm"]
                    presigned_data = result["data"]["sovm"]["images"][idx]
                    presigned_url = presigned_data["presigned_url"]
                    type_counters["sovm"] += 1

                if upload_image(img["image_path"], presigned_url):
                    print(f"  ✓ Uploaded successfully")
                else:
                    print(f"  ❌ Upload failed")
            except (KeyError, IndexError) as e:
                print(f"  ❌ Error finding presigned URL: {e}")
                print(f"     Debug: {img_type} at index {type_counters.get(img_type, 0)}")

        print("\n" + "=" * 60)
        print("✓ Upload complete!")
        print(f"📊 SQS will process when all {expected_count} images uploaded")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Error: {e}")
        if hasattr(e, 'response'):
            print(f"   Response: {e.response.text}")


if __name__ == "__main__":
    main()
