import io
import uuid
from datetime import timedelta
from pathlib import PurePosixPath

from minio import Minio
from minio.error import S3Error

from app.config import settings


def _get_client() -> Minio:
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def ensure_bucket() -> None:
    """Create the default bucket if it doesn't exist."""
    client = _get_client()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)


def upload_file(
    file_data: bytes,
    original_filename: str,
    content_type: str,
    folder: str = "",
) -> dict:
    """
    Upload bytes to MinIO.
    Returns metadata dict with object_name, size, etc.
    """
    client = _get_client()
    ext = PurePosixPath(original_filename).suffix
    unique_name = f"{uuid.uuid4().hex}{ext}"
    object_name = f"{folder}/{unique_name}" if folder else unique_name

    client.put_object(
        bucket_name=settings.MINIO_BUCKET,
        object_name=object_name,
        data=io.BytesIO(file_data),
        length=len(file_data),
        content_type=content_type,
    )

    return {
        "object_name": object_name,
        "original_filename": original_filename,
        "content_type": content_type,
        "size_bytes": len(file_data),
    }


def get_presigned_url(object_name: str, expires_hours: int = 1) -> str:
    """Generate a temporary presigned download URL."""
    client = _get_client()
    return client.presigned_get_object(
        bucket_name=settings.MINIO_BUCKET,
        object_name=object_name,
        expires=timedelta(hours=expires_hours),
    )


def get_file(object_name: str) -> tuple[bytes, str]:
    """Download a file and return (bytes, content_type)."""
    client = _get_client()
    response = client.get_object(settings.MINIO_BUCKET, object_name)
    data = response.read()
    content_type = response.headers.get("Content-Type", "application/octet-stream")
    response.close()
    response.release_conn()
    return data, content_type


def delete_file(object_name: str) -> None:
    """Delete an object from the bucket."""
    client = _get_client()
    client.remove_object(settings.MINIO_BUCKET, object_name)


def list_files(prefix: str = "", max_keys: int = 100) -> list[dict]:
    """List objects in the bucket, optionally filtered by prefix."""
    client = _get_client()
    objects = client.list_objects(
        settings.MINIO_BUCKET, prefix=prefix or None, recursive=True
    )
    results = []
    for obj in objects:
        results.append(
            {
                "object_name": obj.object_name,
                "size_bytes": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                "content_type": obj.content_type,
            }
        )
        if len(results) >= max_keys:
            break
    return results
