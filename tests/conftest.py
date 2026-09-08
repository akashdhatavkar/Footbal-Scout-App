"""Shared pytest fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cache.sqlite_cache import SQLiteCache  # noqa: E402


@pytest.fixture
def cache(tmp_path):
    c = SQLiteCache(path=str(tmp_path / "test_cache.db"))
    yield c
    c.close()

