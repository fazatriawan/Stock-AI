"""
Chat assistant route — powered by Claude Opus via TokenPlus.
Membantu pengguna memahami fitur, istilah keuangan, dan data portofolio mereka.

Batasan keamanan:
- Tidak memberikan rekomendasi beli/jual saham spesifik
- Tidak mengarang angka harga atau return
- Hanya untuk riset dan edukasi pribadi
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.core.config import get_settings

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = """Kamu adalah asisten Stock Intelligence — aplikasi riset ekuitas pribadi untuk pasar IDX (Indonesia) dan US.

Tugasmu:
1. Jelaskan cara menggunakan fitur-fitur aplikasi ini dengan bahasa sederhana
2. Bantu pengguna memahami istilah keuangan (RSI, PER, PBV, ROE, DER, WAC, lot, dll)
3. Bantu interpretasikan data portofolio yang diberikan pengguna
4. Berikan edukasi investasi yang netral, faktual, dan seimbang
5. Arahkan pengguna ke halaman yang tepat jika mereka bingung navigasi

Halaman yang tersedia di aplikasi:
- Overview (/): ringkasan portofolio & status market
- Portofolio (/portfolio): posisi saham, P/L, alokasi sektor — bisa tambah/edit/hapus posisi
- Cari Saham (/explorer): cari saham IDX & US, lihat fundamental dan harga
- Rekomendasi (/decisions): sinyal beli/jual/tahan berbasis analisis fundamental + teknikal + AI
- Daftar Pantau (/watchlist): pantau saham incar + set price target
- Screener (/screener): filter saham multibagger IDX
- Alert Rules (/alerts): notifikasi otomatis saat kondisi harga/RSI/makro terpenuhi
- Daily Intelligence (/daily): ringkasan pergerakan pasar hari ini
- Macro & Policy (/macro): yield curve, indikator ekonomi makro
- Settings (/settings): setup data pasar, bootstrap harga historis

Batasan WAJIB — jangan pernah dilanggar:
- TIDAK memberikan rekomendasi beli/jual saham tertentu secara eksplisit
- TIDAK mengarang angka harga saham, valuasi, atau proyeksi return
- TIDAK menjanjikan keuntungan investasi
- Selalu ingatkan: "ini hanya alat riset, bukan nasihat investasi"
- Jika ditanya angka spesifik yang tidak ada di konteks, arahkan ke halaman yang relevan

Gaya komunikasi:
- Gunakan Bahasa Indonesia yang ramah dan mudah dipahami
- Untuk istilah teknis, selalu sertakan penjelasan singkat
- Jawaban ringkas tapi lengkap (maks 3-4 paragraf kecuali perlu penjelasan panjang)
- Gunakan bullet point untuk daftar, bold untuk istilah penting"""


class ChatMessage(BaseModel):
    role: str  # "user" atau "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    context: Optional[dict] = None  # data konteks opsional (halaman aktif, ringkasan portfolio)


class ChatResponse(BaseModel):
    reply: str
    model_used: str
    skipped: bool = False
    skip_reason: Optional[str] = None


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    """
    Kirim pesan ke AI assistant. Mendukung riwayat percakapan multi-turn.
    Membutuhkan ANTHROPIC_API_KEY dan ANTHROPIC_BASE_URL di .env.
    """
    settings = get_settings()

    if not settings.anthropic_api_key:
        return ChatResponse(
            reply="Maaf, fitur chat belum dikonfigurasi. Tambahkan ANTHROPIC_API_KEY di .env server.",
            model_used="none",
            skipped=True,
            skip_reason="ANTHROPIC_API_KEY tidak diset",
        )

    try:
        import anthropic
    except ImportError:
        raise HTTPException(status_code=500, detail="Package anthropic tidak terinstall")

    # Bangun system prompt dengan konteks tambahan jika ada
    system = SYSTEM_PROMPT
    if body.context:
        ctx_lines = []
        if page := body.context.get("page"):
            ctx_lines.append(f"Halaman aktif: {page}")
        if portfolio := body.context.get("portfolio_summary"):
            ctx_lines.append(f"Ringkasan portofolio pengguna: {portfolio}")
        if ctx_lines:
            system += "\n\nKONTEKS SESI INI:\n" + "\n".join(ctx_lines)

    # Susun messages — riwayat + pesan baru
    messages = [
        {"role": m.role, "content": m.content}
        for m in body.history
    ]
    messages.append({"role": "user", "content": body.message})

    client_kwargs: dict = {"api_key": settings.anthropic_api_key}
    if settings.anthropic_base_url:
        client_kwargs["base_url"] = settings.anthropic_base_url

    model_id = settings.anthropic_model

    try:
        client = anthropic.AsyncAnthropic(**client_kwargs)
        resp = await client.messages.create(
            model=model_id,
            max_tokens=1024,
            system=system,
            messages=messages,  # type: ignore[arg-type]
        )

        # Ekstrak teks (skip ThinkingBlock jika ada)
        reply = ""
        for block in resp.content:
            text = getattr(block, "text", None)
            if text:
                reply = text
                break

        if not reply:
            reply = "Maaf, tidak ada respons dari AI. Coba lagi."

        log.info("chat.success", model=model_id,
                 tokens_in=resp.usage.input_tokens,
                 tokens_out=resp.usage.output_tokens)

        return ChatResponse(reply=reply, model_used=model_id)

    except Exception as exc:
        log.error("chat.error", error=str(exc))
        # Graceful degradation — jangan crash, kembalikan pesan error yang berguna
        return ChatResponse(
            reply=f"Maaf, terjadi kesalahan saat menghubungi AI: {type(exc).__name__}. Coba lagi dalam beberapa saat.",
            model_used=model_id,
            skipped=True,
            skip_reason=str(exc),
        )
