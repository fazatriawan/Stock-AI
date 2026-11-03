"""
Fingerprint deterministik untuk dedup transaksi import.
Hash yang sama = transaksi yang sama = tidak boleh diimport dua kali.
"""
from __future__ import annotations

import hashlib
from datetime import date


def generate_fingerprint(
    canonical_symbol: str,
    trade_date: date,
    side: str,
    shares: float,
    price: float,
    broker: str = "IMPORT",
) -> str:
    """
    Buat fingerprint 32-char dari atribut transaksi yang tidak boleh duplikat.

    Deterministik: input yang sama selalu menghasilkan fingerprint yang sama.
    Tidak menyertakan fee/tax karena bisa bervariasi antar sumber tapi trade sama.
    """
    raw = (
        f"{canonical_symbol.upper()}"
        f"|{trade_date.isoformat()}"
        f"|{side.upper()}"
        f"|{round(shares, 2)}"
        f"|{round(price, 4)}"
        f"|{broker.upper()}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
