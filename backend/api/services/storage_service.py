"""
Storage service abstraction — supports local filesystem and MinIO (S3-compatible).

Configuration via environment variables:
  STORAGE_BACKEND=local|minio  (default: local)
  MINIO_ENDPOINT=localhost:9000
  MINIO_ACCESS_KEY=minioadmin
  MINIO_SECRET_KEY=minioadmin
  MINIO_BUCKET=minutes-audio
  MINIO_SECURE=false
"""
import os
import tempfile
from pathlib import Path
from abc import ABC, abstractmethod
from loguru import logger


class StorageBackend(ABC):
    """Abstract storage backend."""

    @abstractmethod
    def save(self, data: bytes, key: str) -> str:
        """Save file data. Returns the storage key."""
        ...

    @abstractmethod
    def load(self, key: str) -> bytes:
        """Load file data by key."""
        ...

    @abstractmethod
    def get_local_path(self, key: str) -> str:
        """Return a local file path for the given key.
        For local storage this is the actual path.
        For MinIO this downloads to a temp file and returns its path.
        Caller is responsible for cleanup of temp files.
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete file by key."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if file exists."""
        ...

    @abstractmethod
    def get_url(self, key: str, expires: int = 3600) -> str:
        """Get a URL to access the file. For local storage, returns an API path.
        For MinIO, returns a presigned URL."""
        ...


class LocalStorage(StorageBackend):
    """Store files on local filesystem."""

    def __init__(self, base_dir: str = "storage/meetings"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _full_path(self, key: str) -> Path:
        return self.base_dir / key

    def save(self, data: bytes, key: str) -> str:
        path = self._full_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def load(self, key: str) -> bytes:
        path = self._full_path(key)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        return path.read_bytes()

    def get_local_path(self, key: str) -> str:
        path = self._full_path(key)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {key}")
        return str(path)

    def delete(self, key: str) -> None:
        path = self._full_path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._full_path(key).exists()

    def get_url(self, key: str, expires: int = 3600) -> str:
        # For local storage, return an API path that the frontend can fetch
        return f"/api/meetings/audio/{key}"


class MinIOStorage(StorageBackend):
    """Store files in MinIO (S3-compatible object storage)."""

    def __init__(self):
        try:
            from minio import Minio
        except ImportError:
            raise ImportError(
                "minio package required for MinIO storage. "
                "Install with: pip install minio"
            )

        self.endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.bucket = os.getenv("MINIO_BUCKET", "minutes-audio")
        self.secure = os.getenv("MINIO_SECURE", "false").lower() == "true"

        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
        )

        # Ensure bucket exists
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
            logger.info(f"Created MinIO bucket: {self.bucket}")

    def save(self, data: bytes, key: str) -> str:
        from io import BytesIO

        self.client.put_object(
            self.bucket,
            key,
            BytesIO(data),
            length=len(data),
            content_type=self._guess_content_type(key),
        )
        logger.info(f"Uploaded to MinIO: {key} ({len(data)} bytes)")
        return key

    def load(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def get_local_path(self, key: str) -> str:
        """Download to a temp file and return its path.
        Caller must clean up the temp file when done."""
        suffix = Path(key).suffix or ".webm"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            data = self.load(key)
            tmp.write(data)
            tmp.flush()
            return tmp.name
        except Exception:
            os.unlink(tmp.name)
            raise
        finally:
            tmp.close()

    def delete(self, key: str) -> None:
        self.client.remove_object(self.bucket, key)
        logger.info(f"Deleted from MinIO: {key}")

    def exists(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
            return True
        except Exception:
            return False

    def get_url(self, key: str, expires: int = 3600) -> str:
        from datetime import timedelta

        return self.client.presigned_get_object(
            self.bucket, key, expires=timedelta(seconds=expires)
        )

    @staticmethod
    def _guess_content_type(key: str) -> str:
        ext = Path(key).suffix.lower()
        return {
            ".webm": "audio/webm",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
        }.get(ext, "application/octet-stream")


def get_storage() -> StorageBackend:
    """Factory — returns the configured storage backend (singleton)."""
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    if backend == "minio":
        return MinIOStorage()
    return LocalStorage()


# Module-level singleton
_storage_instance = None


def storage() -> StorageBackend:
    """Get or create the storage singleton."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = get_storage()
        logger.info(f"Storage backend initialized: {type(_storage_instance).__name__}")
    return _storage_instance
