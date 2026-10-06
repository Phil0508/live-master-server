# -*- coding: utf-8 -*-
"""📊 조종실에서 무엇을 많이 누르나 — 클릭 기록(옛 features/uistats.py · uistats.html 을 옮겼다).

대표님 09-22: 방송 뒤 이걸 보고 탭 정리를 정한다(자주 누르는 건 앞으로, 안 누르는 건 접기).
조종실이 20초마다 '무엇을 몇 번' 만 묶어 보낸다 → 방송별로 더해 쌓는다. 이름 · 금액 · 입력한 글자는 안 받는다(조종실이 거른다).
⚠️ 방송 흐름에 끼면 안 된다 — 명령 줄(bus)을 안 거친다. 20초마다 모든 화면에 빈 쪽지가 가지 않게,
   장부 표(ui_clicks)에 바로 더한다. 한 번에 받는 양을 자른다(200가지 · 한 가지 5,000번).
   옛 것은 Supabase(Postgres) 표였다. v2 는 같은 SQLite 장부 파일 안의 표 하나.

표  ui_clicks(session, key, label, tab, n, at) — (session, key) 하나에 한 줄
    session = 방송 중이면 그 방송 번호(session.id), 아니면 'off-YYYYMMDD'(한국 날짜 — 방송 밖)
GET  /api/uistats                 (로그인) 방송 목록(최근 순) · 지금 쌓이는 곳
GET  /api/uistats?session=<id>    (로그인) 그 방송의 순위
POST /api/uistats {counts:[{key, label, tab, n}]}  (로그인)
"""
import time

from fastapi.responses import JSONResponse

from .legacy import route

UI_CLICK_MAX_KEYS = 200
UI_CLICK_MAX_N = 5000
TABLE = """
CREATE TABLE IF NOT EXISTS ui_clicks (
    session TEXT NOT NULL,
    key TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    tab TEXT NOT NULL DEFAULT '',
    n INTEGER NOT NULL DEFAULT 0,
    at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (session, key)
)"""


def _ready(store):
    if not getattr(store, '_ui_clicks_ready', False):
        store.db.execute(TABLE)
        store._ui_clicks_ready = True
    return store.db


def ui_session(bus, now=None):
    """지금 클릭이 어느 방송 것인지 — 방송 중이면 방송 번호, 아니면 '방송 밖 + 한국 날짜'."""
    s = bus.state.get('session')
    if s.get('live') and s.get('id'):
        return s['id']
    return 'off-' + time.strftime('%Y%m%d', time.gmtime((now or time.time()) + 9 * 3600))


def clean_counts(rows):
    out = {}
    for r in (rows or [])[:UI_CLICK_MAX_KEYS]:
        if not isinstance(r, dict):
            continue
        key = str(r.get('key') or '').strip()[:80]
        try:
            n = int(r.get('n') or 0)
        except (TypeError, ValueError):
            n = 0
        if not key or n <= 0:
            continue
        label, tab = str(r.get('label') or '')[:60], str(r.get('tab') or '')[:30]
        prev = out.get(key)
        out[key] = (label, tab, min(UI_CLICK_MAX_N, n + (prev[2] if prev else 0)))
    return [(k, l, t, n) for k, (l, t, n) in out.items()]


def _err(msg, code):
    return JSONResponse({'status': 'error', 'message': msg}, status_code=code)


@route('/api/uistats')
async def uistats_add(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    try:
        body = await req.json()
    except Exception:
        body = None
    rows = body.get('counts') if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return _err('counts 목록이 필요합니다', 400)
    clean = clean_counts(rows)
    if not clean:
        return {'status': 'success', 'saved': 0}
    session, now = ui_session(bus), time.time()
    db = _ready(bus.store)
    # ⚠️ 여기서 기다리지(await) 않는다 — 명령(BEGIN … COMMIT)과 같은 갈래라 사이에 끼어들 수 없다
    db.execute('BEGIN')
    try:
        db.executemany('INSERT INTO ui_clicks(session, key, label, tab, n, at) VALUES(?, ?, ?, ?, ?, ?) '
                       'ON CONFLICT(session, key) DO UPDATE SET n = ui_clicks.n + excluded.n, '
                       'label = excluded.label, tab = excluded.tab, at = excluded.at',
                       [(session, k, l, t, n, now) for k, l, t, n in clean])
        db.execute('COMMIT')
    except Exception as e:
        try:
            db.execute('ROLLBACK')
        except Exception:
            pass
        return _err('클릭 기록을 못 적었습니다: %s' % type(e).__name__, 500)
    return {'status': 'success', 'saved': len(clean), 'session': session}


@route('/api/uistats', methods=('GET',))
async def uistats_get(req, bus, authed, answer):
    """?session= 없으면 방송 목록(최근 순), 있으면 그 방송의 순위."""
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    db = _ready(bus.store)
    session = (req.query_params.get('session') or '').strip()
    if not session:
        cur = db.execute('SELECT session, SUM(n) AS total, COUNT(*) AS kinds, MAX(at) AS last_at '
                         'FROM ui_clicks GROUP BY session ORDER BY MAX(at) DESC LIMIT 200')
        out = [{'session': r['session'], 'total': int(r['total'] or 0), 'kinds': int(r['kinds'] or 0),
                'last_at': r['last_at']} for r in cur]
        return {'status': 'success', 'sessions': out, 'now': ui_session(bus)}
    cur = db.execute('SELECT key, label, tab, n FROM ui_clicks WHERE session = ? ORDER BY n DESC, key', (session,))
    rows = [{'key': r['key'], 'label': r['label'], 'tab': r['tab'], 'n': int(r['n'] or 0)} for r in cur]
    return {'status': 'success', 'session': session, 'rows': rows}
