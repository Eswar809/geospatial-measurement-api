"""Upload storage: stream the client bytes to disk with a size cap.

Never build paths from the client filename — uploads land at
``UPLOAD_DIR/<file_id>/original<ext>`` and the client name is metadata only.
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from app.core.errors import EmptyFileError, FileTooLargeError

_CHUNK = 1024 * 1024


def save_upload(
    file_obj: BinaryIO,
    *,
    file_id: str,
    ext: str,
    upload_dir: Path,
    max_bytes: int,
) -> tuple[Path, int]:
    """Stream upload bytes to disk, enforcing the size cap.

    Sync by design: routes are plain ``def`` so GDAL/Shapely work runs in
    the threadpool, and the service layer stays framework-agnostic (the
    FastAPI route passes ``UploadFile.file``; tests pass ``BytesIO``).

    Args:
        file_obj: Binary file-like object supporting ``read(size)``.
        file_id: Hex id used as the directory name.
        ext: Lowercase extension including the dot.
        upload_dir: Base upload directory.
        max_bytes: Abort with 413 past this many bytes.

    Returns:
        The stored file path and its size in bytes.

    Raises:
        EmptyFileError: No bytes received.
        FileTooLargeError: Size exceeded the cap.
    """
    target = upload_dir / file_id / f"original{ext}"
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target.open("wb") as f:
            while chunk := file_obj.read(_CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError(f"upload exceeds {max_bytes} bytes limit")
                f.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    if size == 0:
        target.unlink(missing_ok=True)
        raise EmptyFileError("uploaded file is empty")
    return target, size
