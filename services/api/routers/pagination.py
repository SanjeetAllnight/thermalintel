"""Pagination utilities and validation for ThermalIntel API endpoints."""

import math
from typing import Any, List, Optional, Tuple, TypeVar
from pydantic import BaseModel, Field
from services.api.routers.errors import InvalidRequestError

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


class PaginationMeta(BaseModel):
    """Pagination metadata describing a window of results."""
    page: int = Field(..., description="Current 1-based page index")
    page_size: int = Field(..., description="Maximum items per page")
    total_items: int = Field(..., description="Total items in the collection")
    total_pages: int = Field(..., description="Total calculated pages")
    has_next: bool = Field(..., description="True if subsequent pages exist")
    has_prev: bool = Field(..., description="True if preceding pages exist")


def validate_pagination_params(
    page: Optional[int] = 1,
    page_size: Optional[int] = DEFAULT_PAGE_SIZE,
    limit: Optional[int] = None,
    max_limit: int = MAX_PAGE_SIZE,
) -> Tuple[int, int]:
    """Validate and sanitize page index and page limit.
    
    Prefers explicit `limit` if passed, falling back to `page_size`.
    Raises InvalidRequestError if page < 1 or limit < 1 or limit > max_limit.
    """
    effective_page = page if page is not None else 1
    effective_limit = limit if limit is not None else (page_size if page_size is not None else DEFAULT_PAGE_SIZE)

    if effective_page < 1:
        raise InvalidRequestError(
            message=f"Invalid page parameter: {effective_page}. Page must be >= 1.",
            details={"field": "page", "value": effective_page, "minimum": 1},
        )

    if effective_limit < 1:
        raise InvalidRequestError(
            message=f"Invalid limit/page_size parameter: {effective_limit}. Must be >= 1.",
            details={"field": "page_size", "value": effective_limit, "minimum": 1},
        )

    if effective_limit > max_limit:
        raise InvalidRequestError(
            message=f"Requested page size {effective_limit} exceeds maximum allowed of {max_limit}.",
            details={"field": "page_size", "value": effective_limit, "maximum": max_limit},
        )

    return effective_page, effective_limit


def paginate_list(
    items: List[T],
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Tuple[List[T], PaginationMeta]:
    """Slice an in-memory list deterministically and compute pagination metadata."""
    total_items = len(items)
    total_pages = max(1, math.ceil(total_items / page_size)) if total_items > 0 else 1

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    sliced = items[start_idx:end_idx]

    meta = PaginationMeta(
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )
    return sliced, meta
