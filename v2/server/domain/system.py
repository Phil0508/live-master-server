# -*- coding: utf-8 -*-
"""🖥️ 시스템 — 옛 조종실 '시스템' 탭의 '서버 로그 보기(최근 30건)' 자리.

GET /api/events?limit=30  (로그인) 최근 명령 기록(번호 · 때 · 무엇 · 누가 · 내용 요약) — 장부(events 표)에서 읽기만.
⚠️ 실패한 명령은 장부에 안 남는다(한 명령 = 전부 아니면 전무). 실패는 조종실 알림(토스트)으로만 보인다.
⚠️ 내용(data)은 120자까지만 — 화면이 길어지지 않게(이름 · 금액은 로그인한 운영자에게만 보인다).
"""
import json

from fastapi.responses import JSONResponse

from .legacy import route


@route('/api/events', methods=('GET',))
async def events(req, bus, authed, answer):
    if not authed(req):
        return JSONResponse({'status': 'error', 'message': '로그인이 필요합니다'}, status_code=401)
    try:
        n = max(1, min(200, int(req.query_params.get('limit') or 30)))
    except ValueError:
        n = 30
    rows = []
    for r in bus.store.db.execute('SELECT seq, at, type, by, data FROM events ORDER BY seq DESC LIMIT ?', (n,)):
        try:
            d = json.loads(r['data'] or '{}')
            text = json.dumps(d, ensure_ascii=False, separators=(',', ':')) if d else ''
        except Exception:
            text = str(r['data'] or '')
        rows.append({'seq': r['seq'], 'at': r['at'], 'type': r['type'], 'by': r['by'],
                     'data': text if len(text) <= 120 else text[:119] + '…'})
    return {'status': 'success', 'events': rows}
