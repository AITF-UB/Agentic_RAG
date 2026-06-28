import os
import re
import hashlib
import boto3
import asyncio
import base64
import mimetypes
from pathlib import Path
from typing import Optional, Dict
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

_s3_client = None
_upload_locks: Dict[str, asyncio.Lock] = {}
_policy_set = False

def get_s3_client():
    global _s3_client, _policy_set
    if _s3_client is None:
        endpoint = os.getenv("MINIO_ENDPOINT")
        user = os.getenv("MINIO_ROOT_USER")
        password = os.getenv("MINIO_ROOT_PASSWORD")
        
        if endpoint and user and password:
            _s3_client = boto3.client(
                's3',
                endpoint_url=endpoint,
                aws_access_key_id=user,
                aws_secret_access_key=password,
                region_name='us-east-1'
            )
            
            # Set Public Read Policy if not set yet
            if not _policy_set:
                bucket = os.getenv("MINIO_BUCKET_NAME")
                if bucket:
                    try:
                        import json
                        policy = {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Sid": "PublicRead",
                                    "Effect": "Allow",
                                    "Principal": "*",
                                    "Action": ["s3:GetObject"],
                                    "Resource": [f"arn:aws:s3:::{bucket}/*"]
                                }
                            ]
                        }
                        _s3_client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
                        _policy_set = True
                    except Exception as e:
                        print(f"⚠️ MinIO: Failed to set public policy for bucket '{bucket}': {e}")
    return _s3_client

def get_public_url(key: str) -> str:
    """Returns the public URL for a given MinIO key."""
    # Use public URL if available, else fallback to internal endpoint
    endpoint = os.getenv("MINIO_PUBLIC_URL") or os.getenv("MINIO_ENDPOINT", "")
    bucket = os.getenv("MINIO_BUCKET_NAME", "")
    return f"{endpoint.rstrip('/')}/{bucket}/{key}"

def upload_file_sync(img_bytes: bytes, img_path: str, mime_type: str) -> Optional[str]:
    """Upload ke MinIO secara synchronous, return public URL atau None jika gagal."""
    client = get_s3_client()
    bucket = os.getenv("MINIO_BUCKET_NAME")
    if not client or not bucket:
        return None

    path_hash = hashlib.md5(img_path.encode('utf-8', errors='replace')).hexdigest()[:8]
    basename = re.sub(r'[^\w\-.]', '_', Path(img_path).name) or "img"
    key = f"{path_hash}_{basename}"

    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            try:
                client.put_object(
                    Bucket=bucket, 
                    Key=key,
                    Body=img_bytes, 
                    ContentType=mime_type
                )
            except Exception as err:
                print(f"❌ MinIO upload failed: {err}")
                return None
        else:
            print(f"❌ MinIO check error: {e}")
            return None

    return get_public_url(key)

async def upload_base64_async(filename: str, base64_str: str) -> bool:
    """Uploads base64 image to MinIO if it doesn't already exist. Asynchronous."""
    client = get_s3_client()
    bucket = os.getenv("MINIO_BUCKET_NAME")
    
    if not client or not bucket or not base64_str:
        return False
        
    if filename not in _upload_locks:
        _upload_locks[filename] = asyncio.Lock()
        
    async with _upload_locks[filename]:
        def _do():
            try:
                client.head_object(Bucket=bucket, Key=filename)
                return True # Sudah ada, skip upload
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    try:
                        clean_b64 = base64_str.replace("\n", "").replace("\r", "").strip()
                        image_data = base64.b64decode(clean_b64)
                        
                        content_type, _ = mimetypes.guess_type(filename)
                        content_type = content_type or 'image/jpeg'
                        
                        client.put_object(
                            Bucket=bucket,
                            Key=filename,
                            Body=image_data,
                            ContentType=content_type
                        )
                        return True
                    except Exception as upload_err:
                        print(f"❌ Error uploading to MinIO: {upload_err}")
                        return False
                else:
                    print(f"❌ Error checking MinIO object: {e}")
                    return False
                    
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do)
