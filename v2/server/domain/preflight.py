# -*- coding: utf-8 -*-
"""🛫 방송 전 점검 · 방송 중 경보 — 옛 features/preflight.py 와 같은 답 모양(조종실이 그대로 쓴다).

GET /api/preflight[?deep=1] (로그인) — 읽기만 한다.
  screens  방송 화면(OBS) 수(미리보기 monitor 는 빼고) · 종류별
  listener 리스너가 10초마다 적는 toon_listener_status.json → ok · connecting · down · none
  spool    리스너가 못 보낸 후원 수(donation_spool.jsonl)
  sig      (deep) 시그니처 목록 — 개수 · 제일 싼 값
"""
import asyncio
import json
import os
import time

from .legacy import route

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
STATUS_FILE = os.environ.get('TOON_STATUS_FILE') or os.path.join(REPO, 'toon_listener_status.json')
SPOOL_FILE = os.environ.get('SPOOL_FILE') or os.path.join(REPO, 'donation_spool.jsonl')


def listener():
    try:
        with open(STATUS_FILE, encoding='utf-8') as f:
            st = json.load(f)
    except FileNotFoundError:
        return {'level': 'none', 'note': '리스너 상태 파일이 없습니다(이 서버에선 안 씀)'}
    except Exception as e:
        return {'level': 'down', 'note': '상태를 못 읽었습니다: %s' % type(e).__name__}
    age = int(time.time() - float(st.get('updated') or 0))
    main = (st.get('accounts') or {}).get('main') or {}
    if age >= 60:
        return {'level': 'down', 'age_sec': age, 'note': '%d초째 소식이 없습니다' % age}
    now = time.time()
    base = {'age_sec': age, 'state': main.get('state'), 'note': str(main.get('note') or '')[:120],
            'connected_sec': int(now - main['connected_at']) if main.get('connected_at') else None,
            'last_donation_sec': int(now - main['last_donation']) if main.get('last_donation') else None}
    lv = 'ok' if main.get('state') == 'connected' else 'connecting' if main.get('state') in ('connecting', 'starting') else 'down'
    return dict(base, level=lv)


def spool():
    try:
        with open(SPOOL_FILE, encoding='utf-8', errors='replace') as f:
            return sum(1 for ln in f if ln.strip())
    except FileNotFoundError:
        return 0
    except Exception:
        return None


@route('/api/preflight', methods=('GET',))
async def preflight(req, bus, authed, answer):
    if not authed(req):
        from fastapi.responses import JSONResponse
        return JSONResponse({'status': 'error', 'message': '로그인이 필요합니다'}, status_code=401)
    sc = {'overlay': 0, 'overlay_obs': 0, 'monitor': 0, 'controller': 0, 'total': 0}
    for c in list(bus.hub.clients):
        sc['total'] += 1
        if c.kind == 'overlay':
            sc['monitor' if c.monitor else 'overlay'] += 1
            if not c.monitor and c.dev == 'obs':
                sc['overlay_obs'] += 1
        elif c.kind in sc:
            sc[c.kind] += 1
    from .health import _db_ms, _rss_mb
    ms = _db_ms(bus.store)
    out = {'status': 'success', 'broadcast_active': bool(bus.state.get('session').get('live')), 'screens': sc,
           'listener': listener(), 'spool': spool(),
           'storage': {'ok': ms is not None, 'kind': 'sqlite', 'ms': ms, 'note': '' if ms is not None else '장부(SQLite)가 답하지 않습니다'},
           'server': {'dropped': bus.hub.dropped, 'rss_mb': _rss_mb()}}
    # ⚠️ 받아 가지 않는(멈춘) 방송판은 줄이 차면 hub 가 끊는다 — 옛 overlay_idle 은 여기선 늘 0 이라 따로 세지 않는다
    if req.query_params.get('deep') == '1':
        t = time.perf_counter()
        rows = await asyncio.to_thread(bus.sigs.rows)
        out['sig'] = {'ok': bool(rows), 'count': len(rows), 'cheapest': int(rows[0]['amount']) if rows else None,
                      'ms': int((time.perf_counter() - t) * 1000),
                      'note': bus.sigs.last_error or ('' if rows else '목록이 비어 있습니다')}
    return out
