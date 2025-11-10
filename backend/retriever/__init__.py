"""Retrieval helpers for thin/local catalog lookup and server-side ranking."""

from .index_manager import (
    ensure_company_index,
    ensure_index,
    get_index_stats,
    index_stats,
    rebuild_index,
    search_index,
    update_index,
    update_index_incremental,
)
from .main import get_company_index, rank_main
from .thin import search_catalog_thin

__all__ = [
    "ensure_index",
    "ensure_company_index",
    "get_index_stats",
    "index_stats",
    "rebuild_index",
    "search_index",
    "update_index",
    "update_index_incremental",
    "get_company_index",
    "rank_main",
    "search_catalog_thin",
]
