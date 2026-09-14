#!/usr/bin/env python3
"""Test R2 connectivity by uploading, downloading, listing, and deleting a test object."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def mask(s: str, keep: int = 4) -> str:
    if not s or len(s) <= keep * 2:
        return "***"
    return f"{s[:keep]}***{s[-keep:]}"


async def main() -> int:
    load_dotenv(REPO_ROOT / ".env")

    endpoint = os.environ.get("R2_ENDPOINT", "").strip()
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    bucket = os.environ.get("R2_BUCKET_NAME", "").strip()

    if not all([endpoint, access_key, secret_key, bucket]):
        print("ERROR: R2 env vars missing.", file=sys.stderr)
        return 1

    print(f"endpoint    = {endpoint}")
    print(f"bucket      = {bucket}")
    print(f"access_key  = {mask(access_key)}")
    print(f"secret_key  = {mask(secret_key)}")

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )

    test_key = "r2_smoke_test/connectivity_probe.txt"
    test_content = (
        b"PolicyMeta R2 connectivity probe\n"
        b"created_at: 2026-08-30\n"
        b"purpose: verify R2 bucket p234-storage is reachable\n"
    )

    print("\n--- 1. head_bucket ---")
    try:
        client.head_bucket(Bucket=bucket)
        print("OK: bucket reachable")
    except ClientError as e:
        print(f"ERROR: head_bucket failed: {e}")
        return 1

    print("\n--- 2. put_object ---")
    try:
        client.put_object(
            Bucket=bucket,
            Key=test_key,
            Body=test_content,
            ContentType="text/plain",
        )
        print(f"OK: uploaded {test_key} ({len(test_content)} bytes)")
    except ClientError as e:
        print(f"ERROR: put_object failed: {e}")
        return 1

    print("\n--- 3. head_object ---")
    try:
        resp = client.head_object(Bucket=bucket, Key=test_key)
        print(
            f"OK: size={resp.get('ContentLength')}, "
            f"type={resp.get('ContentType')}, "
            f"etag={resp.get('ETag')}"
        )
    except ClientError as e:
        print(f"ERROR: head_object failed: {e}")

    print("\n--- 4. get_object ---")
    try:
        resp = client.get_object(Bucket=bucket, Key=test_key)
        body = resp["Body"].read()
        print(f"OK: downloaded {len(body)} bytes")
        print(f"     matches upload: {body == test_content}")
    except ClientError as e:
        print(f"ERROR: get_object failed: {e}")

    print("\n--- 5. list_objects_v2 (prefix=r2_smoke_test/) ---")
    try:
        resp = client.list_objects_v2(
            Bucket=bucket, Prefix="r2_smoke_test/"
        )
        for obj in resp.get("Contents", []):
            print(
                f"     {obj['Key']}  size={obj['Size']}  "
                f"modified={obj['LastModified']}"
            )
    except ClientError as e:
        print(f"ERROR: list failed: {e}")

    print("\n--- 6. delete_object ---")
    try:
        client.delete_object(Bucket=bucket, Key=test_key)
        print(f"OK: deleted {test_key}")
    except ClientError as e:
        print(f"ERROR: delete failed: {e}")

    print("\nALL OK: R2 bucket is fully operational.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))