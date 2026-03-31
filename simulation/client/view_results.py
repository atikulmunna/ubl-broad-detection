"""
View processed results from S3
"""
import os
import json
import boto3
from datetime import datetime

# AWS Configuration
AWS_ENDPOINT_URL = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION = "ap-southeast-1"
S3_BUCKET = "ubl-shop-audits"

s3_client = boto3.client(
    's3',
    endpoint_url=AWS_ENDPOINT_URL,
    region_name=AWS_REGION,
    aws_access_key_id='test',
    aws_secret_access_key='test'
)

def list_results(visit_id=None):
    """List all results or results for specific audit"""
    prefix = f"results/{visit_id}/" if visit_id else "results/"
    
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        
        if 'Contents' not in response:
            print(f"No results found in {prefix}")
            return []
        
        results = []
        for obj in response['Contents']:
            key = obj['Key']
            size = obj['Size']
            modified = obj['LastModified']
            results.append({
                'key': key,
                'size': size,
                'modified': modified
            })
        
        return results
    except Exception as e:
        print(f"Error listing results: {e}")
        return []


def download_result(result_key):
    """Download and display a result file"""
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=result_key)
        content = response['Body'].read().decode('utf-8')
        result_data = json.loads(content)
        
        print("\n" + "="*60)
        print(f"RESULT: {result_key}")
        print("="*60)
        print(json.dumps(result_data, indent=2))
        print("="*60)
        
        return result_data
    except Exception as e:
        print(f"Error downloading result: {e}")
        return None


def main():
    print("="*60)
    print("VIEW PROCESSED RESULTS")
    print("="*60)
    
    # List all results
    visit_id = input("\nEnter Visit ID (press Enter for all): ").strip()
    
    results = list_results(visit_id if visit_id else None)
    
    if not results:
        print("\nNo results found.")
        return
    
    print(f"\nFound {len(results)} result(s):\n")
    
    for idx, result in enumerate(results, 1):
        print(f"{idx}. {result['key']}")
        print(f"   Size: {result['size']} bytes")
        print(f"   Modified: {result['modified']}")
        print()
    
    # Ask which one to view
    if len(results) == 1:
        choice = '1'
    else:
        choice = input(f"Select result to view (1-{len(results)}, or 'all'): ").strip()
    
    if choice.lower() == 'all':
        for result in results:
            download_result(result['key'])
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(results):
                download_result(results[idx]['key'])
            else:
                print("Invalid selection")
        except ValueError:
            print("Invalid input")


if __name__ == "__main__":
    main()
