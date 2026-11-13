"""
FreshnessStatus — status ketersediaan dan kualitas data sesuai FREE-02.

Digunakan oleh PriceBar, FinancialFact, dan Data Health UI.
Null != 0 — data hilang tidak diisi atau diasumsikan dari data sebelumnya.
"""
from __future__ import annotations

from enum import Enum


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"                     # data valid dan terkini
    STALE = "STALE"                     # data ada tapi melewati batas freshness
    NOT_COVERED = "NOT_COVERED"         # provider tidak menyediakan data ini
    UNAVAILABLE = "UNAVAILABLE"         # provider down atau request gagal
    CONFLICTED = "CONFLICTED"           # nilai berbeda antar provider, belum direkonsiliasi
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED" # kuota provider habis
    LICENSE_BLOCKED = "LICENSE_BLOCKED" # provider diblokir budget guard

    @classmethod
    def is_usable(cls, status: "FreshnessStatus") -> bool:
        """Hanya FRESH yang dianggap dapat dipakai untuk perhitungan."""
        return status == cls.FRESH
