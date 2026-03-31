import os
import requests
import json
from typing import Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8081")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
S3_BUCKET = os.getenv("S3_BUCKET", "u-lens-production-audit-images")

def upload_image(image_path: str, presigned_url: Dict) -> bool:
    """
    Upload image using presigned URL
    Reference: simulation/client/upload_production.py
    """
    print(f"Uploading {os.path.basename(image_path)} to S3...")
    
    # The presigned_url dict contains 'url' and 'fields'
    url = presigned_url.get('url')
    fields = presigned_url.get('fields')
    
    if not url or not fields:
        print("❌ Error: Invalid presigned URL structure")
        return False

    try:
        with open(image_path, 'rb') as f:
            files = {'file': (os.path.basename(image_path), f)}
            response = requests.post(
                url,
                data=fields,
                files=files
            )
            
        if response.status_code in [200, 204]:
            return True
        else:
            print(f"❌ Upload failed with status code: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception during upload: {e}")
        return False

def submit_retake(visit_id: str, upload_id: str, retake_count: int, auth_token: str) -> Dict:
    """
    Submit retake request to backend and get presigned URL
    """
    url = f"{BACKEND_URL}/retake-submit"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "visit_id": visit_id,
        "upload_id": upload_id,
        "is_retake": True,
        "retake_count": retake_count
    }

    print(f"\n[POST] {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

def confirm_retake_completion(visit_id: str, original_upload_id: str, new_upload_id: str, auth_token: str) -> bool:
    """
    Notify backend that retake upload is complete.
    This tells the AI worker to process using the original_upload_id (not new_upload_id).
    """
    url = f"{BACKEND_URL}/retake-confirm"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "visit_id": visit_id,
        "original_upload_id": original_upload_id,
        "new_upload_id": new_upload_id,
        "is_retake": True
    }

    print(f"\n[POST] {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        if result.get("status_code") == 200:
            print("✓ Backend confirmed - AI will process using original upload_id")
            return True
        else:
            print(f"⚠️  Warning: {result.get('message')}")
            return False
    except requests.exceptions.HTTPError as e:
        print(f"⚠️  Confirmation failed: {e}")
        if e.response is not None:
            print(f"   Response: {e.response.text}")
        return False
    except Exception as e:
        print(f"⚠️  Error: {e}")
        return False

def main():
    global AUTH_TOKEN
    print("=" * 60)
    print("Interactive Retake Image Uploader")
    print("=" * 60)

    # 0. Handle Auth Token
    if not AUTH_TOKEN:
        print("\n🔐 Auth Token Required")
        AUTH_TOKEN = input("Enter JWT token: ").strip()
    else:
        print(f"\n✓ Found token in environment (ends in ...{AUTH_TOKEN[-8:] if len(AUTH_TOKEN) > 8 else AUTH_TOKEN})")
        override = input("Override with new token? (y/N): ").strip().lower()
        if override == 'y':
            AUTH_TOKEN = input("Enter new JWT token: ").strip()

    if not AUTH_TOKEN:
        print("❌ Error: Auth token is required for this operation.")
        return

    # 1. Get user input
    visit_id = input("\nEnter Visit ID (e.g., VISIT_82139763E313): ").strip()
    if not visit_id:
        print("❌ Visit ID is required")
        return

    upload_id = input("Enter Upload ID (e.g., b4febaaa-e4b5-4e46-a3b0-3cc688fd9d3b): ").strip()
    if not upload_id:
        print("❌ Upload ID is required")
        return

    try:
        retake_count_str = input("Enter Retake Count (default 1): ").strip()
        retake_count = int(retake_count_str) if retake_count_str else 1
    except ValueError:
        print("❌ Invalid retake count, using 1")
        retake_count = 1

    image_path = input("Enter Image Path: ").strip()
    image_path = os.path.expanduser(image_path)
    
    if not os.path.exists(image_path):
        print(f"❌ File not found: {image_path}")
        return

    # 2. Submit retake request
    try:
        print("\nStep 1: Requesting presigned URL from backend...")
        result = submit_retake(visit_id, upload_id, retake_count, AUTH_TOKEN)
        
        if result.get("status_code") == 200:
            print("✓ Retake presigned URL generated successfully")
            data = result.get("data", {})
            presigned_url_data = data.get("presigned_url")
            
            if not presigned_url_data:
                print("❌ Error: No presigned URL found in response data")
                return

            # 3. Upload to S3
            print("\nStep 2: Uploading image to S3...")
            if upload_image(image_path, presigned_url_data):
                new_upload_id = data.get('new_upload_id')
                s3_key = data.get('s3_key')
                
                print("\n" + "=" * 60)
                print("✓ SUCCESS: Retake image uploaded to S3!")
                print(f"  Original Upload ID: {upload_id}")
                print(f"  New Upload ID (for versioning): {new_upload_id}")
                print(f"  S3 Key: {s3_key}")
                
                # Step 3: Confirm retake completion to backend
                print("\nStep 3: Confirming retake with backend...")
                if confirm_retake_completion(visit_id, upload_id, new_upload_id, AUTH_TOKEN):
                    print("\n✓ Retake workflow completed!")
                    print(f"✓ AI worker will process using: {upload_id}")
                else:
                    print("\n⚠️  Retake uploaded but confirmation pending")
                    print(f"   AI worker should use upload_id: {upload_id}")
                print("=" * 60)
            else:
                print("\n❌ FAILED: S3 upload failed")
        else:
            print(f"\n❌ FAILED: Backend returned {result.get('status_code')}: {result.get('message')}")

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP Error: {e}")
        if e.response is not None:
            print(f"   Response Body: {e.response.text}")
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")

if __name__ == "__main__":
    main()
