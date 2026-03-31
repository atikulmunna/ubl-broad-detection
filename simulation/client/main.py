"""
Script to upload images to localstack S3 using presigned URLs from the client and backend
"""
import os
import sys
import requests
from pathlib import Path

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
IMAGES_DIR = os.getenv("IMAGES_DIR", "./sample-images")

# Image types (Sample types for the simulation)
IMAGE_TYPES = [
    "share_of_shelf",
    "sachet",
    "posm",
]

def request_presigned_urls(visit_id: str, shop_id: str, merchandiser_id: str):
    """Request presigned URLs from backend"""
    print(f"\n{'='*60}")
    print(f"REQUESTING PRESIGNED URLS")
    print(f"{'='*60}")
    print(f"Visit ID: {visit_id}")
    print(f"Shop ID: {shop_id}")
    print(f"Merchandiser ID: {merchandiser_id}")
    
    url = f"{BACKEND_URL}/api/audits/{visit_id}/upload-urls"
    payload = {
        "visit_id": visit_id,
        "shop_id": shop_id,
        "merchandiser_id": merchandiser_id
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        urls = response.json()
        print(f"Received presigned URLs for {len(urls)} image types")
        print(f"{'='*60}\n")
        return urls
    except Exception as e:
        print(f"Error requesting presigned URLs: {e}")
        sys.exit(1)

def upload_image_to_s3(image_path: str, presigned_data: dict, image_type: str):
    """Upload image to S3 using presigned URL"""
    print(f"\nUploading {image_type}...")
    print(f"File: {image_path}")
    
    if not os.path.exists(image_path):
        print(f"File not found, skipping...")
        return False
    
    try:
        print(f"presigned_data: {presigned_data}")
        presigned_url = presigned_data['presigned_url']
        
        with open(image_path, 'rb') as f:
            files = {'file': f}
            
            response = requests.post(
                presigned_url['url'],
                data=presigned_url['fields'],
                files=files
            )
            
            if response.status_code in [200, 204]:
                print(f"Upload successful!")
                print(f"Upload ID: {presigned_data['upload_id']}")
                return True
            else:
                print(f"Upload failed: {response.status_code}")
                print(f"Response: {response.text}")
                return False
                
    except Exception as e:
        print(f"Error uploading: {e}")
        return False

def main():
    """Main function"""
    print("\n" + "="*60)
    print("IMAGE UPLOAD SCRIPT")
    print("="*60)
    
    visit_id = input("\nEnter Visit ID (default: aud_123456): ").strip() or "aud_123456"
    shop_id = input("Enter Shop ID (default: shop_789): ").strip() or "shop_789"
    merchandiser_id = input("Enter Merchandiser ID (default: user_456): ").strip() or "user_456"
    
    presigned_urls = request_presigned_urls(visit_id, shop_id, merchandiser_id)
    
    print(f"\n{'='*60}")
    print(f"UPLOADING IMAGES")
    print(f"{'='*60}")
    
    # images_dir = Path(IMAGES_DIR)
    uploaded_count = 0
    
    for image_type in IMAGE_TYPES:
        possible_paths = [
            Path("sample-images") / f"{image_type}.jpg",
        ]
        
        image_path = None
        for p in possible_paths:
            if p.exists():
                image_path = p
                break
        
        if not image_path:
            print(f"\n Image not found for {image_type}")
            print(f"Checked: {[str(p) for p in possible_paths]}")
            continue

        
        if image_type in presigned_urls:
            if upload_image_to_s3(str(image_path), presigned_urls[image_type], image_type):
                uploaded_count += 1
        else:
            print(f"\n  No presigned URL for {image_type}")
    
    print(f"\n{'='*60}")
    print(f"UPLOAD COMPLETE")
    print(f"{'='*60}")
    print(f"Uploaded: {uploaded_count}/{len(IMAGE_TYPES)} images")
    print(f"\nCheck the results at:")
    print(f"{BACKEND_URL}/api/audits/{visit_id}/images")
    print(f"{BACKEND_URL}/api/audits/{visit_id}/results")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
