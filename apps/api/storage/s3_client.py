"""Thin boto3 wrapper for MinIO / S3."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import boto3
from botocore.client import BaseClient

from config import Settings, get_settings

if TYPE_CHECKING:
    pass


@lru_cache
def get_s3_client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def put_object(*, key: str, body: bytes, settings: Settings | None = None) -> None:
    s = settings or get_settings()
    client = get_s3_client()
    client.put_object(Bucket=s.s3_bucket, Key=key, Body=body)


def get_object_bytes(*, key: str, settings: Settings | None = None) -> bytes:
    s = settings or get_settings()
    client = get_s3_client()
    response = client.get_object(Bucket=s.s3_bucket, Key=key)
    body = response["Body"].read()
    if not isinstance(body, bytes):
        raise TypeError("S3 Body.read() did not return bytes")
    return body
