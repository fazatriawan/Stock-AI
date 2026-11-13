"""
Unit tests FREE-02 FreshnessStatus enum.
"""
from __future__ import annotations

from app.domain.freshness import FreshnessStatus


class TestFreshnessStatus:
    def test_all_values_defined(self):
        expected = {
            "FRESH", "STALE", "NOT_COVERED", "UNAVAILABLE",
            "CONFLICTED", "QUOTA_EXHAUSTED", "LICENSE_BLOCKED",
        }
        assert {s.value for s in FreshnessStatus} == expected

    def test_is_usable_only_fresh(self):
        assert FreshnessStatus.is_usable(FreshnessStatus.FRESH) is True
        for status in FreshnessStatus:
            if status != FreshnessStatus.FRESH:
                assert FreshnessStatus.is_usable(status) is False

    def test_str_enum_values(self):
        # Pastikan bisa dipakai sebagai string default di DB column
        assert FreshnessStatus.FRESH == "FRESH"
        assert FreshnessStatus.STALE == "STALE"

    def test_migration_default_matches_enum(self):
        # Default di migration 008 adalah "FRESH" — harus match enum value
        assert FreshnessStatus("FRESH") == FreshnessStatus.FRESH
