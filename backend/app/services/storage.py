"""Object storage (MinIO/S3) for uploaded files."""
import io
from typing import BinaryIO

from app.core.config import settings

# Optional MinIO; fallback to in-memory / filesystem if not available
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from minio import Minio
        from urllib.parse import urlparse
        o = urlparse(settings.minio_url)
        _client = Minio(
            o.netloc or "localhost:9000",
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=o.scheme == "https",
        )
        return _client
    except Exception:
        return None


def ensure_bucket():
    """Create bucket if it does not exist."""
    c = _get_client()
    if c is None:
        return
    try:
        if not c.bucket_exists(settings.minio_bucket):
            c.make_bucket(settings.minio_bucket)
    except Exception:
        pass


def upload_file(object_key: str, data: BinaryIO, size: int, content_type: str = "application/octet-stream") -> str:
    """Upload file to object store. Returns object_key."""
    c = _get_client()
    if c is None:
        raise RuntimeError("MinIO not configured or unavailable")
    ensure_bucket()
    c.put_object(settings.minio_bucket, object_key, data, size, content_type=content_type)
    return object_key


def download_file(object_key: str) -> bytes:
    """Download file from object store."""
    c = _get_client()
    if c is None:
        raise RuntimeError("MinIO not configured or unavailable")
    resp = c.get_object(settings.minio_bucket, object_key)
    try:
        return resp.read()
    finally:
        resp.close()


def get_stream(object_key: str) -> BinaryIO:
    """Get a readable stream for the object."""
    data = download_file(object_key)
    return io.BytesIO(data)
