"""Custom pagination classes for the BodiAgent API."""

from rest_framework.pagination import CursorPagination


class CreatedAtCursorPagination(CursorPagination):
    """CursorPagination with -created_at ordering (project convention).

    DRF's default CursorPagination.ordering is '-created', but all models
    in this project use `created_at` for the creation timestamp field.
    """

    ordering = "-created_at"
