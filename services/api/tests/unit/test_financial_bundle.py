"""
Unit tests — GET /stocks/{symbol}/financial-bundle (integrasi plugin /comps /dcf /earnings).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.schemas import FinancialBundleResponse, PeerFundamentalSnapshot


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestFinancialBundleSchema:
    def _make_peer(self, symbol: str, is_subject: bool = False) -> PeerFundamentalSnapshot:
        return PeerFundamentalSnapshot(
            canonical_symbol=symbol,
            company_name=f"Company {symbol}",
            sector="Banking",
            pe_ratio=12.5,
            pb_ratio=1.8,
            roe=18.0,
            eps=500.0,
            gross_margin=None,
            net_margin=22.0,
            revenue=50_000_000_000_000,
            net_income=11_000_000_000_000,
            market_cap=100_000_000_000_000,
            dividend_yield=4.5,
            debt_to_equity=5.0,
            nim=5.2,
            npl_gross=2.1,
            car=22.0,
            data_freshness="FRESH",
            period_end=date(2024, 12, 31),
            is_subject=is_subject,
        )

    def test_bundle_fields_present(self):
        bundle = FinancialBundleResponse(
            canonical_symbol="IDX:BBCA",
            company_name="Bank Central Asia",
            exchange="IDX",
            sector="Banking",
            currency="IDR",
            country="ID",
            last_price=9450.0,
            price_date=date(2025, 1, 15),
            high_52w=10000.0,
            low_52w=8000.0,
            return_1y=12.5,
            return_ytd=None,
            beta_1y=None,
            market_cap=1_200_000_000_000_000,
            enterprise_value=1_300_000_000_000_000,
            revenue_ttm=100_000_000_000_000,
            ebitda_ttm=30_000_000_000_000,
            net_income_ttm=22_000_000_000_000,
            gross_margin=None,
            operating_margin=30.0,
            net_margin=22.0,
            roe=20.5,
            roa=None,
            debt_to_equity=5.5,
            current_ratio=None,
            pe_ratio=23.0,
            pb_ratio=4.5,
            ps_ratio=None,
            ev_ebitda=43.3,
            dividend_yield=3.2,
            peers=[self._make_peer("IDX:BBCA", is_subject=True), self._make_peer("IDX:BBRI")],
            peer_count=2,
            sector_median_pe=15.0,
            sector_median_pb=2.0,
            sector_median_roe=18.0,
            rsi_14=55.0,
            sma_200=9000.0,
            above_sma_200=True,
            nim=5.8,
            npl_gross=1.4,
            car=23.5,
            data_period=date(2024, 12, 31),
            as_of=datetime.now(tz=timezone.utc),
        )
        assert bundle.canonical_symbol == "IDX:BBCA"
        assert bundle.peer_count == 2
        assert bundle.nim == 5.8
        assert bundle.above_sma_200 is True

    def test_bundle_optional_fields_none(self):
        bundle = FinancialBundleResponse(
            canonical_symbol="IDX:TLKM",
            company_name="Telkom Indonesia",
            exchange="IDX",
            sector="Telecommunications",
            currency="IDR",
            country="ID",
            last_price=None,
            price_date=None,
            high_52w=None,
            low_52w=None,
            return_1y=None,
            return_ytd=None,
            beta_1y=None,
            market_cap=None,
            enterprise_value=None,
            revenue_ttm=None,
            ebitda_ttm=None,
            net_income_ttm=None,
            gross_margin=None,
            operating_margin=None,
            net_margin=None,
            roe=None,
            roa=None,
            debt_to_equity=None,
            current_ratio=None,
            pe_ratio=None,
            pb_ratio=None,
            ps_ratio=None,
            ev_ebitda=None,
            dividend_yield=None,
            peers=[],
            peer_count=0,
            sector_median_pe=None,
            sector_median_pb=None,
            sector_median_roe=None,
            rsi_14=None,
            sma_200=None,
            above_sma_200=None,
            nim=None,
            npl_gross=None,
            car=None,
            data_period=None,
            as_of=datetime.now(tz=timezone.utc),
        )
        assert bundle.pe_ratio is None
        assert bundle.peer_count == 0


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

def _make_instrument(symbol: str = "BBCA") -> MagicMock:
    instr = MagicMock()
    instr.id = "uuid-" + symbol.lower()
    instr.canonical_symbol = f"IDX:{symbol}"
    instr.local_symbol = symbol
    instr.company_name = f"Company {symbol}"
    instr.exchange = "IDX"
    instr.sector = "Banking"
    instr.currency = "IDR"
    instr.country = "ID"
    instr.timezone = "Asia/Jakarta"
    instr.asset_type = "equity"
    instr.industry = None
    instr.status = "active"
    instr.market_cap = None
    instr.last_updated = None
    return instr


def _make_fundamental_snap(symbol: str = "BBCA") -> MagicMock:
    snap = MagicMock()
    snap.instrument_id = "uuid-" + symbol.lower()
    snap.as_of = date.today()
    snap.sector = "Banking"
    snap.pe_ratio = 23.5
    snap.pb_ratio = 4.2
    snap.roe = 21.0
    snap.eps = 480.0
    snap.revenue = 100_000_000_000_000
    snap.net_income = 20_000_000_000_000
    snap.market_cap = 1_100_000_000_000_000
    snap.dividend_yield = 3.5
    snap.debt_to_equity = 5.8
    snap.gross_margin = None
    snap.operating_margin = 0.32
    snap.nim = 5.5
    snap.npl_gross = 1.5
    snap.car = 23.0
    snap.period_end = date(2024, 12, 31)
    snap.data_freshness = "FRESH"
    snap.metrics_available = ["pe_ratio", "pb_ratio", "roe"]
    snap.metrics_missing = []
    snap.integrity_status = "OK"
    snap.integrity_blocked = False
    return snap


class TestFinancialBundleEndpoint:
    @pytest.mark.asyncio
    async def test_returns_bundle_for_valid_symbol(self):
        import pandas as pd
        from app.api.routes.stocks import get_financial_bundle

        instr = _make_instrument("BBCA")
        fund_snap = _make_fundamental_snap("BBCA")

        # Mock DB: instrument + empty price bars + empty peer result
        db = MagicMock()
        empty_scalars = MagicMock()
        empty_scalars.scalars.return_value.all.return_value = []
        empty_scalars.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=empty_scalars)

        import asyncio

        async def _mock_load_fund(db, instrument, today):
            return fund_snap

        async def _mock_load_df(instrument_id, db, days=365):
            return pd.DataFrame()

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=instr)), \
             patch("app.api.routes.stocks.load_fundamental_snapshot", side_effect=_mock_load_fund), \
             patch("app.api.routes.stocks._load_price_df", new=AsyncMock(return_value=pd.DataFrame())):
            resp = await get_financial_bundle("BBCA", peer_limit=5, db=db)

        assert resp.canonical_symbol == "IDX:BBCA"
        assert resp.pe_ratio == 23.5
        assert resp.roe == 21.0
        assert resp.nim == 5.5

    @pytest.mark.asyncio
    async def test_unknown_symbol_raises(self):
        from fastapi import HTTPException
        from app.api.routes.stocks import get_financial_bundle
        from app.core.exceptions import DataNotFoundError

        db = MagicMock()

        with patch(
            "app.api.routes.stocks._get_instrument_or_404",
            new=AsyncMock(side_effect=DataNotFoundError("not found")),
        ):
            with pytest.raises((HTTPException, DataNotFoundError)):
                await get_financial_bundle("UNKNOWN", peer_limit=5, db=db)

    @pytest.mark.asyncio
    async def test_ev_ebitda_computed(self):
        import pandas as pd
        from app.api.routes.stocks import get_financial_bundle

        instr = _make_instrument("BBCA")
        fund_snap = _make_fundamental_snap("BBCA")
        # revenue + operating_margin set → ebitda_ttm harus dihitung

        db = MagicMock()
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        empty_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=empty_result)

        async def _mock_load_fund(db, instrument, today):
            return fund_snap

        with patch("app.api.routes.stocks._get_instrument_or_404", new=AsyncMock(return_value=instr)), \
             patch("app.api.routes.stocks.load_fundamental_snapshot", side_effect=_mock_load_fund), \
             patch("app.api.routes.stocks._load_price_df", new=AsyncMock(return_value=pd.DataFrame())):
            resp = await get_financial_bundle("BBCA", peer_limit=3, db=db)

        # ebitda_ttm = revenue * operating_margin (ratio, 0-1)
        expected_ebitda = fund_snap.revenue * fund_snap.operating_margin
        assert resp.ebitda_ttm == pytest.approx(expected_ebitda, rel=0.01)
        assert resp.enterprise_value is not None


# ---------------------------------------------------------------------------
# Commands sanity check
# ---------------------------------------------------------------------------

class TestCommandFiles:
    def _repo_root(self):
        import pathlib
        # test ada di services/api/tests/unit/ → 4 parent ke atas = repo root
        return pathlib.Path(__file__).parent.parent.parent.parent.parent

    def test_comps_command_exists(self):
        cmd = self._repo_root() / ".claude" / "commands" / "comps.md"
        assert cmd.exists(), f"comps.md tidak ada di {cmd}"
        content = cmd.read_text()
        assert "financial-bundle" in content
        assert "comps-analysis" in content

    def test_dcf_command_exists(self):
        cmd = self._repo_root() / ".claude" / "commands" / "dcf.md"
        assert cmd.exists(), f"dcf.md tidak ada di {cmd}"
        content = cmd.read_text()
        assert "financial-bundle" in content
        assert "dcf-model" in content

    def test_earnings_command_exists(self):
        cmd = self._repo_root() / ".claude" / "commands" / "earnings.md"
        assert cmd.exists(), f"earnings.md tidak ada di {cmd}"
        content = cmd.read_text()
        assert "financial-bundle" in content

    def test_thesis_command_exists(self):
        cmd = self._repo_root() / ".claude" / "commands" / "thesis.md"
        assert cmd.exists(), f"thesis.md tidak ada di {cmd}"
        content = cmd.read_text()
        assert "financial-bundle" in content
        assert "analysis" in content
