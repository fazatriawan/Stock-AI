"""
Settings API — Investment Policy Statement (IPS) dan konfigurasi user.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import InvestmentPolicyResponse, InvestmentPolicyUpdateRequest
from app.db.session import get_db
from app.domain.investment_policy import get_or_create_default, update_policy

router = APIRouter(prefix="/settings", tags=["settings"])


def _to_response(policy) -> InvestmentPolicyResponse:
    return InvestmentPolicyResponse(
        profile_name=policy.profile_name,
        mode=policy.mode,
        max_position_weight=float(policy.max_position_weight),
        max_sector_weight=float(policy.max_sector_weight),
        buy_score_threshold=float(policy.buy_score_threshold),
        min_core_coverage=float(policy.min_core_coverage),
        max_staleness_days=policy.max_staleness_days,
        horizon=policy.horizon,
        notes=policy.notes,
        updated_at=policy.updated_at,
    )


@router.get("/policy", response_model=InvestmentPolicyResponse)
async def get_policy(
    db: AsyncSession = Depends(get_db),
) -> InvestmentPolicyResponse:
    """Ambil Investment Policy Statement yang aktif (profil 'default')."""
    policy = await get_or_create_default(db)
    await db.commit()
    return _to_response(policy)


@router.put("/policy", response_model=InvestmentPolicyResponse)
async def update_investment_policy(
    body: InvestmentPolicyUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> InvestmentPolicyResponse:
    """
    Update parameter IPS.
    Hanya kirim field yang ingin diubah — field lain tidak berubah.
    Perubahan berlaku di run engine berikutnya.
    """
    policy = await get_or_create_default(db)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tidak ada field yang dikirim untuk diupdate.",
        )

    try:
        await update_policy(db, policy, **updates)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    policy.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(policy)
    return _to_response(policy)
