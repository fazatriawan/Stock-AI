"""
Domain logic untuk Investment Policy Statement (IPS).
Satu profil 'default' per instalasi — dibuat otomatis saat pertama kali diakses.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InvestmentPolicy, new_uuid

DEFAULT_PROFILE = "default"

# Nilai default sesuai PRD — sama dengan hardcode lama di engine
_DEFAULTS = {
    "mode": "BALANCED",
    "max_position_weight": Decimal("0.1000"),
    "max_sector_weight": Decimal("0.3000"),
    "buy_score_threshold": Decimal("60.00"),
    "min_core_coverage": Decimal("0.600"),
    "max_staleness_days": 3,
    "horizon": "3-12 months",
    "notes": None,
}

VALID_MODES = {"CONSERVATIVE", "BALANCED", "EXPLORATORY"}


async def get_or_create_default(db: AsyncSession) -> InvestmentPolicy:
    """Ambil policy default; buat jika belum ada."""
    result = await db.execute(
        select(InvestmentPolicy).where(InvestmentPolicy.profile_name == DEFAULT_PROFILE)
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        policy = InvestmentPolicy(id=new_uuid(), profile_name=DEFAULT_PROFILE, **_DEFAULTS)
        db.add(policy)
        await db.flush()
    return policy


async def update_policy(
    db: AsyncSession,
    policy: InvestmentPolicy,
    **fields,
) -> InvestmentPolicy:
    """
    Update field yang dikirim; validasi sederhana di sini.
    Caller wajib commit setelah memanggil ini.
    """
    if "mode" in fields:
        if fields["mode"] not in VALID_MODES:
            raise ValueError(f"mode harus salah satu dari {VALID_MODES}")
        policy.mode = fields["mode"]

    if "max_position_weight" in fields:
        v = Decimal(str(fields["max_position_weight"]))
        if not (Decimal("0.01") <= v <= Decimal("1.0")):
            raise ValueError("max_position_weight harus antara 0.01 dan 1.0")
        policy.max_position_weight = v

    if "max_sector_weight" in fields:
        v = Decimal(str(fields["max_sector_weight"]))
        if not (Decimal("0.05") <= v <= Decimal("1.0")):
            raise ValueError("max_sector_weight harus antara 0.05 dan 1.0")
        policy.max_sector_weight = v

    if "buy_score_threshold" in fields:
        v = Decimal(str(fields["buy_score_threshold"]))
        if not (Decimal("0") <= v <= Decimal("100")):
            raise ValueError("buy_score_threshold harus antara 0 dan 100")
        policy.buy_score_threshold = v

    if "min_core_coverage" in fields:
        v = Decimal(str(fields["min_core_coverage"]))
        if not (Decimal("0") <= v <= Decimal("1")):
            raise ValueError("min_core_coverage harus antara 0 dan 1")
        policy.min_core_coverage = v

    if "max_staleness_days" in fields:
        days_val = int(fields["max_staleness_days"])
        if days_val < 1:
            raise ValueError("max_staleness_days harus >= 1")
        policy.max_staleness_days = days_val  # type: ignore[assignment]

    if "horizon" in fields:
        h = str(fields["horizon"]).strip()
        if not h:
            raise ValueError("horizon tidak boleh kosong")
        policy.horizon = h

    if "notes" in fields:
        policy.notes = fields["notes"]

    return policy
