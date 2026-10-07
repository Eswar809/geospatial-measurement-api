"""Safe zip extraction for shapefile uploads."""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from app.core.errors import InvalidArchiveError

logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = {".shp", ".shx", ".dbf", ".prj", ".cpg"}

_FIXED_NAMES = {
    ".shp": "data.shp",
    ".shx": "data.shx",
    ".dbf": "data.dbf",
    ".prj": "data.prj",
    ".cpg": "data.cpg",
}


class ArchiveError(InvalidArchiveError):
    """Raised when a zip archive fails a safety check."""


def safe_extract(
    zip_path: Path,
    dest_dir: Path,
    max_entries: int,
    max_bytes: int,
) -> Path:
    """Extract a shapefile zip safely, returning the directory of parts.

    Rules: reject absolute or `..` member names (Zip Slip), skip
    `__MACOSX/` and dotfiles, keep only shapefile parts (case-insensitive)
    written under fixed names, cap member count and total bytes actually
    written (declared sizes can lie), reject encrypted or corrupt archives,
    require exactly one `.shp`.

    Args:
        zip_path: Path to the uploaded zip file.
        dest_dir: Directory to extract the parts into.
        max_entries: Maximum number of archive members allowed.
        max_bytes: Maximum total uncompressed bytes allowed.

    Returns:
        The destination directory containing the extracted parts.

    Raises:
        ArchiveError: If any safety check fails.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.infolist()
            if len(members) > max_entries:
                raise ArchiveError(
                    f"too many archive members ({len(members)} > {max_entries})"
                )
            seen_shp = 0
            written = 0
            for info in members:
                name = info.filename
                if _is_unsafe(name):
                    raise ArchiveError(f"unsafe archive member name: {name!r}")
                if _is_skipped(name):
                    logger.debug("skipping archive member %r", name)
                    continue
                suffix = Path(name).suffix.lower()
                if suffix not in ALLOWED_SUFFIXES:
                    continue
                if info.flag_bits & 0x1:
                    raise ArchiveError(f"encrypted archive member: {name!r}")
                if suffix == ".shp":
                    seen_shp += 1
                target = dest_dir / _FIXED_NAMES[suffix]
                with zf.open(info) as src, target.open("wb") as dst:
                    while chunk := src.read(1024 * 1024):
                        written += len(chunk)
                        if written > max_bytes:
                            raise ArchiveError(
                                f"uncompressed size exceeds {max_bytes} bytes"
                            )
                        dst.write(chunk)
            if seen_shp == 0:
                raise ArchiveError("archive contains no .shp file")
            if seen_shp > 1:
                raise ArchiveError("archive contains more than one .shp file")
    except zipfile.BadZipFile as e:
        raise ArchiveError(f"corrupt zip archive: {e}") from e
    return dest_dir


def _is_unsafe(name: str) -> bool:
    """Check for absolute paths or parent-directory traversal.

    Parses with both POSIX and Windows rules so backslash traversal and
    drive-letter paths are caught on every platform.
    """
    if name.startswith(("/", "\\")):
        return True
    for parser in (PurePosixPath, PureWindowsPath):
        parsed = parser(name)
        if parsed.is_absolute() or ".." in parsed.parts:
            return True
    return False


def _is_skipped(name: str) -> bool:
    """Skip directories, macOS metadata, and dotfiles."""
    if name.endswith("/"):
        return True
    parts = Path(name).parts
    return any(
        (part.startswith(".") and part not in (".", "..")) or part == "__MACOSX__"
        for part in parts
    )
