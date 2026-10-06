# -*- coding: utf-8 -*-
"""🛫 방송 전 점검 · 방송 중 경보 (대표님 2026-10-06 "사고 막기 해볼까 — 소리는 안 나도 돼").

조종실이 부른다(로그인 필요 · GET /api/preflight). 한 번에 다 본다:
  📺 방송 화면(OBS)   실시간 연결 중 kind=overlay 이고 미리보기(monitor)가 아닌 것.
                      예전엔 ⚙ 설정 → 시스템 탭의 '붙은 화면' 에서만 보여, 방송 중에 끊겨도 아무도 몰랐다.
  🔔 알림창 · 시그니처 화면 · 슬롯 화면   있으면 몇 개(안 쓰는 날도 있어 경보는 안 한다)
  🎧 후원 받기        리스너(toon_listener.py)가 10초마다 적는 toon_listener_status.json.
                      죽으면 후원이 하나도 안 들어오는데 '후원이 뜸한 건지' 와 구분이 안 됐다.
  📮 못 보낸 후원      리스너 대기줄(donation_spool.jsonl) 줄 수 — 쌓여 있으면 서버가 후원을 못 받고 있는 것
  🎵 시그니처 목록 서버(Supabase)   ?deep=1 일 때만 · 60초 기억 · 한 번에 하나만 물어본다(죽어 있으면 10초 걸린다)
  💾 저장소 · 🧠 서버  SELECT 1 · 메모리 · 붙은 화면 수 · 치운 죽은 연결 수
⚠️ 읽기만 한다 — 상태를 바꾸지 않는다(저장 · 방송 알림 없음). file_lock 도 안 쥔다.
⚠️ 조종실은 방송 중 10초마다 부른다 — 무거운 것(시그니처 서버)은 deep 일 때만.
"""
import os
import threading
import time
from flask import jsonify, request
import server
from server import app

PF_OVERLAY_IDLE = 45        # 방송 화면이 이만큼 한 줄도 못 받아 갔으면 '멈춤 의심'(서버는 15초마다 ping 을 보낸다)
PF_SIG_TTL = 60             # 시그니처 서버 확인 결과를 기억하는 시간
_pf_sig = {'at': 0.0, 'res': None}
_pf_sig_lock = threading.Lock()


def _screens():
    """붙은 화면을 종류별로 센다. 방송 화면은 미리보기(monitor)를 빼고 센다."""
    now = time.time()
    out = {'overlay': 0, 'overlay_obs': 0, 'overlay_idle': 0, 'monitor': 0,
           'alertbox': 0, 'sigdisp': 0, 'slot': 0, 'controller': 0, 'total': 0}
    with server.sse_lock:
        clients = list(server.sse_clients)
    for q in clients:
        out['total'] += 1
        k = getattr(q, '_kind', 'unknown')
        if k == 'overlay':
            if getattr(q, '_monitor', False):
                out['monitor'] += 1
                continue
            if now - getattr(q, '_drained', now) > PF_OVERLAY_IDLE:
                out['overlay_idle'] += 1          # 붙어 있다고는 하는데 받아 가지를 않는다 — 세지 않는다
                continue
            out['overlay'] += 1
            if getattr(q, '_dev', '') == 'obs':
                out['overlay_obs'] += 1
        elif k in out:
            out[k] += 1
    return out


def _listener():
    """후원 받기(리스너) — 'ok' · 'connecting' · 'down' · 'none'(이 서버엔 리스너가 없다)."""
    try:
        from features.toon_accounts import _view
        v = (_view() or {}).get('listener') or {}
    except Exception as e:
        return {'level': 'down', 'note': '상태를 못 읽었습니다: %s' % type(e).__name__}
    age = v.get('age_sec')
    main = v.get('main') if isinstance(v.get('main'), dict) else {}
    if age is None:
        return {'level': 'none', 'note': '리스너 상태 파일이 없습니다(이 서버에선 안 씀)'}
    if not v.get('alive'):
        return {'level': 'down', 'age_sec': age, 'note': '%d초째 소식이 없습니다' % age}
    st = main.get('state')
    now = time.time()
    since = main.get('connected_at') or 0
    last = main.get('last_donation') or 0
    base = {'age_sec': age, 'state': st,
            'connected_sec': int(now - since) if since else None,
            'last_donation_sec': int(now - last) if last else None,
            'note': str(main.get('note') or '')[:120]}
    if st == 'connected':
        return dict(base, level='ok')
    if st in ('connecting', 'starting'):
        return dict(base, level='connecting')
    return dict(base, level='down')


def _spool():
    """리스너가 서버에 못 보내 쌓아 둔 후원 수."""
    p = os.path.join(server.BASE_DIR, 'donation_spool.jsonl')
    try:
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            return sum(1 for ln in f if ln.strip())
    except FileNotFoundError:
        return 0
    except Exception:
        return None


def _storage():
    t0 = time.perf_counter()
    try:
        with server.get_db_connection() as conn:
            conn.cursor().execute('SELECT 1')
        return {'ok': True, 'ms': round((time.perf_counter() - t0) * 1000, 1)}
    except Exception as e:
        return {'ok': False, 'error': type(e).__name__}


def _sig_server():
    """시그니처 목록 서버 — 60초 기억. 누가 이미 물어보는 중이면 기다리지 않고 지난 결과를 준다."""
    now = time.time()
    if _pf_sig['res'] is not None and now - _pf_sig['at'] < PF_SIG_TTL:
        return dict(_pf_sig['res'], cached=True)
    if not _pf_sig_lock.acquire(blocking=False):
        return dict(_pf_sig['res'] or {'ok': None, 'note': '확인하는 중'}, cached=True)
    try:
        t0 = time.perf_counter()
        try:
            rows = server.supabase_list_signatures() or []
            amts = sorted(int(r.get('amount') or 0) for r in rows if r.get('amount') is not None)
            res = {'ok': bool(rows), 'count': len(rows), 'cheapest': amts[0] if amts else None,
                   'ms': round((time.perf_counter() - t0) * 1000), 'note': '' if rows else '목록이 비어 있습니다(설정을 확인)'}
        except Exception as e:
            res = {'ok': False, 'ms': round((time.perf_counter() - t0) * 1000), 'note': type(e).__name__}
        _pf_sig.update({'at': time.time(), 'res': res})
        return dict(res, cached=False)
    finally:
        _pf_sig_lock.release()


@app.route('/api/preflight', methods=['GET'])
def api_preflight():
    deep = request.args.get('deep') == '1'
    try:
        state = server.load_data()
        on = bool(state.get('broadcast_active'))
    except Exception:
        on = None
    out = {'status': 'success', 'now': time.time(), 'broadcast_active': on,
           'screens': _screens(), 'listener': _listener(), 'spool': _spool(),
           'storage': _storage(),
           'server': {'rss_mb': server._rss_mb(), 'uptime_sec': int(time.time() - server.SERVER_BOOT_TS),
                      'evicted': server._sse_evicted}}
    if deep:
        out['sig'] = _sig_server()
    return jsonify(out)
