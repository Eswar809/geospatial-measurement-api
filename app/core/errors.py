"""Application error hierarchy, mapped to HTTP responses by the API layer."""

from __future__ import annotations


class AppError(Exception):
    """Base error carrying a machine-readable code and HTTP status."""

    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UnsupportedFileTypeError(AppError):
    code = "UNSUPPORTED_FILE_TYPE"
    status_code = 415


class EmptyFileError(AppError):
    code = "EMPTY_FILE"
    status_code = 400


class FileTooLargeError(AppError):
    code = "FILE_TOO_LARGE"
    status_code = 413


class InvalidArchiveError(AppError):
    code = "INVALID_ARCHIVE"
    status_code = 422


class InvalidGeoDataError(AppError):
    code = "INVALID_GEODATA"
    status_code = 422


class UnsupportedCRSError(AppError):
    code = "UNSUPPORTED_CRS"
    status_code = 422


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404


class NotReadyError(AppError):
    code = "NOT_READY"
    status_code = 409
