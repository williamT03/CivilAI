"""Public Storage feature entry points."""

from .Tools.storage import FileStorage, get_file_storage


def get_storage_backend() -> FileStorage:
    """Return the configured file storage backend."""

    return get_file_storage()


__all__ = ["FileStorage", "get_file_storage", "get_storage_backend"]
