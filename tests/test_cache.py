"""Tests for the SQLite TTL cache."""
from __future__ import annotations

import time


def test_set_and_get_roundtrip(cache):
    cache.set("k1", {"name": "Ødegaard"}, ttl=60)
    assert cache.get("k1") == {"name": "Ødegaard"}


def test_get_missing_returns_none(cache):
    assert cache.get("missing") is None


def test_expired_entry_is_evicted(cache):
    cache.set("k1", {"a": 1}, ttl=0)  # expires immediately
    assert cache.get("k1") is None


def test_get_or_set_invokes_loader_once(cache):
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return {"value": 42}

    assert cache.get_or_set("k1", loader, ttl=60) == {"value": 42}
    assert cache.get_or_set("k1", loader, ttl=60) == {"value": 42}
    assert calls["n"] == 1


def test_overwrite_updates_value(cache):
    cache.set("k1", "old", ttl=60)
    cache.set("k1", "new", ttl=60)
    assert cache.get("k1") == "new"


def test_delete_and_clear(cache):
    cache.set("a", 1, ttl=60)
    cache.set("b", 2, ttl=60)
    cache.delete("a")
    assert cache.get("a") is None
    assert cache.get("b") == 2
    cache.clear()
    assert cache.get("b") is None


def test_purge_expired_removes_stale(cache):
    cache.set("a", 1, ttl=0)
    cache.set("b", 2, ttl=3600)
    removed = cache.purge_expired()
    assert removed == 1
    assert cache.get("a") is None
    assert cache.get("b") == 2
