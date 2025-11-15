"""Allow importing `backend.*` when running inside the backend folder."""

from __future__ import annotations

from pathlib import Path

# When `uvicorn backend.main:app` is executed from the `backend/` directory,
# Python discovers this package at `backend/backend`. We forward the package
# search path to the real code located one directory up so submodules like
# `backend.main` can still be resolved.
_pkg_dir = Path(__file__).resolve().parent
_parent_backend_dir = _pkg_dir.parent

_parent_backend_dir_str = str(_parent_backend_dir)
if _parent_backend_dir_str not in __path__:  # type: ignore[name-defined]
    __path__.append(_parent_backend_dir_str)  # type: ignore[attr-defined]
