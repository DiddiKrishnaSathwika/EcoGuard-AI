"""Local and Vercel Blob storage for persistent application files."""
import json
from pathlib import Path, PurePosixPath

from config import FILE_STORAGE_BACKEND, IS_VERCEL_RUNTIME


LOCAL_STORAGE_ROOT = Path(__file__).resolve().parents[1]


class StorageConfigurationError(RuntimeError):
    """Raised when persistent storage is not configured for this runtime."""


def _storage_key(key):
    if not isinstance(key, str) or not key or "\\" in key or "//" in key:
        raise ValueError("Storage keys must be non-empty relative paths.")

    path = PurePosixPath(key)
    if (
        path.is_absolute()
        or path.as_posix() == "."
        or any(part in ("", ".", "..") or ":" in part for part in path.parts)
    ):
        raise ValueError("Storage keys must be non-empty relative paths.")

    return path.as_posix()


def _backend():
    if FILE_STORAGE_BACKEND not in ("local", "vercel_blob"):
        raise StorageConfigurationError(
            "FILE_STORAGE_BACKEND must be 'local' or 'vercel_blob'."
        )
    if IS_VERCEL_RUNTIME and FILE_STORAGE_BACKEND != "vercel_blob":
        raise StorageConfigurationError(
            "Vercel requires FILE_STORAGE_BACKEND=vercel_blob; local disk is not persistent."
        )
    return FILE_STORAGE_BACKEND


def _local_path(key):
    root = LOCAL_STORAGE_ROOT.resolve()
    path = (root / Path(*PurePosixPath(key).parts)).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError("Storage key resolves outside the local storage root.") from error
    return path


def _blob_client():
    try:
        from vercel import blob
        from vercel.blob import sync as blob_sync
    except ImportError as error:
        raise StorageConfigurationError(
            "Vercel Blob storage requires the 'vercel-blob' package."
        ) from error
    return blob_sync, blob.BlobNotFoundError


def put_bytes(key, content, content_type="application/octet-stream"):
    """Persist bytes and return a local path or Blob pathname."""
    key = _storage_key(key)
    if _backend() == "local":
        path = _local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    client, _ = _blob_client()
    uploaded = client.put_blob(
        key,
        content,
        access="private",
        content_type=content_type,
        allow_overwrite=True,
    )
    return uploaded.pathname


def get_bytes(key):
    """Read bytes, returning None only when the object does not exist."""
    key = _storage_key(key)
    if _backend() == "local":
        try:
            return _local_path(key).read_bytes()
        except FileNotFoundError:
            return None

    client, blob_not_found_error = _blob_client()
    try:
        return client.get_blob(key, access="private").body
    except blob_not_found_error:
        return None


def put_json(key, value):
    content = json.dumps(value, indent=4, ensure_ascii=False).encode("utf-8")
    return put_bytes(key, content, content_type="application/json")


def get_json(key):
    content = get_bytes(key)
    if content is None:
        return None
    return json.loads(content.decode("utf-8"))
