# -*- coding: utf-8 -*-
"""🎆 방송판 시그니처 미리받기 목록 · 📺 따로 띄우는 화면의 옛 주소.

GET /api/sigfx/sigs — **로그인 없이**(방송판은 로그인이 없다). 방송판이 켜질 때 시그니처 사진 · 소리를 미리 받아 두고
    사진 대표색을 뽑는 데 쓴다(옛 overlay.html preloadSignatures 가 옛 /api/signatures 를 읽던 것).
    v2 의 /api/signatures 는 조종실 전용(로그인)이라 따로 둔다. 주는 것은 id · 금액 · 이름 · 그림 · 소리 · 길이**만** —
    시그니처 표의 다른 칸이 늘어도 새지 않게 칸을 골라 담는다. 목록은 bus.sigs 가 10분 기억한다(바깥 왕복은 명령 밖, to_thread).
    못 읽으면(보관소가 안 답함) 빈 목록 — 방송판은 미리받기만 건너뛰고 시그니처는 그대로 나간다.

옛 주소 이어주기 — 옛 OBS 소스 · 즐겨찾기를 그대로 열면 v2 방송판의 그 화면으로(주소 뒤 ?… 는 그대로 붙여 넘긴다):
    /alertbox · /alertbox.html                                        → /overlay/?only=alert  (후원 카드 + 시그니처)
    /signature-display · /signature-display.html · /signature_display.html → /overlay/?only=sig  (출연진 전광판)
    /slot · /slot.html                                                → /overlay/?only=slot   (슬롯머신만)
"""
import asyncio

from fastapi.responses import JSONResponse, RedirectResponse

from .legacy import route

PUBLIC_KEYS = ('id', 'amount', 'title', 'image_url', 'sound_url', 'duration')


def public_rows(rows):
    """시그니처 줄 → 방송판에 줘도 되는 칸만(금액순 그대로)."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict) or r.get('amount') is None:
            continue
        out.append({k: r.get(k) for k in PUBLIC_KEYS})
    return out


@route('/api/sigfx/sigs', methods=('GET',))
async def sigfx_sigs(req, bus, authed, answer):
    sigs = getattr(bus, 'sigs', None)
    try:
        rows = await asyncio.to_thread(sigs.rows) if sigs is not None else []
    except Exception:
        rows = []
    out = public_rows(rows)
    return JSONResponse({'status': 'success', 'signatures': out, 'count': len(out)},
                        headers={'Cache-Control': 'no-store'})


VIEW_REDIRECTS = {
    '/alertbox': 'alert', '/alertbox.html': 'alert',
    '/signature-display': 'sig', '/signature-display.html': 'sig', '/signature_display.html': 'sig',
    '/slot': 'slot', '/slot.html': 'slot',
}


def view_url(only, query=''):
    q = 'only=' + only
    extra = '&'.join(p for p in str(query or '').split('&') if p and not p.startswith('only='))
    return '/overlay/?' + q + ('&' + extra if extra else '')


def _make_redirect(only):
    async def go(req, bus, authed, answer):
        return RedirectResponse(view_url(only, req.url.query), status_code=302)
    return go


for _path, _only in VIEW_REDIRECTS.items():
    route(_path, methods=('GET',))(_make_redirect(_only))
