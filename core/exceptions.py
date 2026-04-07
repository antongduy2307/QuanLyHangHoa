from __future__ import annotations


class AppError(Exception):
    """Base exception for the desktop application."""


class ValidationError(AppError):
    """Raised when incoming data breaks domain rules."""


class RepositoryError(AppError):
    """Raised when persistence operations fail."""


class NotFoundError(AppError):
    """Raised when a requested entity cannot be found."""
