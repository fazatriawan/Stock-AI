"""
Import routes — Phase 2.
Upload CSV/XLSX/PDF, preview, lalu konfirmasi.

Flow:
  POST /portfolio/import/preview  → parse file, kembalikan ParsedTrade[]
  POST /portfolio/import/confirm  → commit ParsedTrade[] yang dipilih user ke DB

Tidak ada auto-commit: semua keputusan import ada di tangan user.
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportPreviewResponse,
    ParsedTradePreview,
)
from app.db.models import Instrument, Trade
from app.db.session import get_db
from app.portfolio.importers import parse_csv, parse_pdf, parse_xlsx
from app.portfolio.importers.base import ValidationStatus
from app.portfolio.seeder import get_or_create_default_portfolio

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/portfolio/import", tags=["portfolio-import"])

_SUPPORTED_EXTENSIONS = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "pdf": "application/pdf",
}
MAX_FILE_SIZE_MB = 10


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    broker: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
) -> ImportPreviewResponse:
    """
    Parse file broker dan kembalikan daftar transaksi untuk diverifikasi.
    File tidak di-commit ke DB — hanya preview.

    Mendukung: CSV, XLSX, PDF
    """
    if not file.filename:
        raise HTTPException(status_code=422, detail="Nama file kosong")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Format file tidak didukung: .{ext}. Gunakan CSV, XLSX, atau PDF.",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File terlalu besar (maks {MAX_FILE_SIZE_MB} MB)",
        )

    if not content:
        raise HTTPException(status_code=422, detail="File kosong")

    broker_hint = broker.strip() or None

    # Parse berdasarkan tipe file
    if ext == "csv":
        result = parse_csv(content, broker_hint)
    elif ext in ("xlsx", "xls"):
        result = parse_xlsx(content, broker_hint)
    elif ext == "pdf":
        result = parse_pdf(content, broker_hint)
    else:
        raise HTTPException(status_code=422, detail=f"Format {ext} belum didukung")

    # Cek fingerprint yang sudah ada di DB
    existing_fps = set()
    if result.trades:
        fps = [t.fingerprint for t in result.trades if t.fingerprint]
        if fps:
            dup_result = await db.execute(
                select(Trade.import_fingerprint).where(Trade.import_fingerprint.in_(fps))
            )
            existing_fps = {row[0] for row in dup_result.fetchall()}

    # Build preview response
    preview_trades: list[ParsedTradePreview] = []
    duplicate_count = 0

    for trade in result.trades:
        is_dup = trade.fingerprint in existing_fps

        if is_dup:
            duplicate_count += 1
            trade.warnings.append("Trade ini sudah ada di portofolio (fingerprint duplikat)")
            if trade.status == ValidationStatus.OK:
                trade.status = ValidationStatus.WARNING

        preview_trades.append(ParsedTradePreview(
            row_number=trade.row_number,
            canonical_symbol=trade.canonical_symbol,
            trade_date=trade.trade_date,
            side=trade.side,
            lots=trade.lots,
            shares=trade.shares,
            price=trade.price,
            fee=trade.fee,
            tax=trade.tax,
            currency=trade.currency,
            source_broker=trade.source_broker,
            fingerprint=trade.fingerprint,
            status=trade.status.value,
            warnings=trade.warnings,
            errors=trade.errors,
        ))

    log.info(
        "import.preview",
        filename=file.filename,
        format=result.broker_format,
        total=result.total_rows,
        valid=result.valid_count,
        errors=result.error_count,
        duplicates=duplicate_count,
    )

    return ImportPreviewResponse(
        broker_format=result.broker_format.value,
        total_rows=result.total_rows,
        valid_count=result.valid_count,
        error_count=result.error_count,
        duplicate_count=duplicate_count,
        trades=preview_trades,
        parse_errors=result.parse_errors,
        warnings=result.warnings,
    )


@router.post("/confirm", response_model=ImportConfirmResponse)
async def confirm_import(
    body: ImportConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> ImportConfirmResponse:
    """
    Commit trade yang dipilih user setelah verifikasi preview.

    Semua keputusan commit ada di tangan user — endpoint ini hanya menyimpan
    apa yang dikirim, tidak memodifikasi atau menambah data sendiri.
    """
    if not body.trades:
        raise HTTPException(status_code=422, detail="Tidak ada trade yang dikirim")

    portfolio = await get_or_create_default_portfolio(db)

    created = 0
    skipped_duplicates = 0
    skipped_errors = 0
    errors: list[str] = []

    for preview in body.trades:
        # Lewati trade dengan error
        if preview.status == "ERROR":
            skipped_errors += 1
            continue

        # Cek duplikat (jika ada fingerprint)
        if preview.fingerprint and body.skip_duplicates:
            dup = await db.execute(
                select(Trade).where(Trade.import_fingerprint == preview.fingerprint)
            )
            if dup.scalar_one_or_none() is not None:
                skipped_duplicates += 1
                continue

        # Resolve instrument dari canonical_symbol
        instr_result = await db.execute(
            select(Instrument).where(
                Instrument.canonical_symbol == preview.canonical_symbol
            )
        )
        instrument = instr_result.scalar_one_or_none()

        if instrument is None:
            skipped_errors += 1
            errors.append(
                f"Instrumen {preview.canonical_symbol!r} tidak ditemukan — "
                "jalankan /admin/bootstrap lebih dulu"
            )
            continue

        trade = Trade(
            id=str(uuid.uuid4()),
            portfolio_id=portfolio.id,
            instrument_id=instrument.id,
            trade_date=preview.trade_date,
            side=preview.side,
            shares=preview.shares,
            price=preview.price,
            fee=preview.fee or 0.0,
            tax=preview.tax or 0.0,
            currency=preview.currency or instrument.currency,
            source_broker=preview.source_broker,
            import_fingerprint=preview.fingerprint or None,
            notes=None,
        )
        db.add(trade)
        created += 1

    await db.flush()

    log.info(
        "import.confirm",
        created=created,
        skipped_duplicates=skipped_duplicates,
        skipped_errors=skipped_errors,
    )

    return ImportConfirmResponse(
        message=f"Import selesai: {created} transaksi berhasil ditambahkan",
        created=created,
        skipped_duplicates=skipped_duplicates,
        skipped_errors=skipped_errors,
        errors=errors,
    )
