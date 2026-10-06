# -*- coding: utf-8 -*-
"""📒 장부 보기 — 이번 방송 · 지난 방송 후원 기록, 점수 기록.

GET /api/ledger?session=<id|current>&q=<이름>&limit=200   (로그인)
GET /api/sessions                                          (로그인) 방송 회차 목록 · 회차별 합계
GET /api/scores?session=<id|current>&limit=200             (로그인) 점수 장부(되돌린 것 표시)
⚠️ 옛 서버는 방송을 끝낼 때 장부를 보관 표로 옮기고 지웠다(옮기다 실패하면 500). v2 는 지우지 않는다 —
   후원마다 방송 회차(session)가 적혀 있어서 회차로 골라 보면 된다.
"""
from fastapi.responses import JSONResponse

from .legacy import route
from .rules import COUNTED


def _need(req, authed):
    if not authed(req):
        return JSONResponse({'status': 'error', 'message': '로그인이 필요합니다'}, status_code=401)
    return None


def _session(req, bus):
    s = req.query_params.get('session') or 'current'
    return bus.state.get('session').get('id') or '' if s == 'current' else s


def _limit(req):
    try:
        return max(1, min(2000, int(req.query_params.get('limit') or 200)))
    except ValueError:
        return 200


@route('/api/ledger', methods=('GET',))
async def ledger(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    q = (req.query_params.get('q') or '').strip().casefold()
    rows = bus.store.donations(session=_session(req, bus), limit=2000 if q else _limit(req))   # 찾을 땐 넓게 보고 거른다
    if q:
        rows = [r for r in rows if q in (r['name'] or '').casefold()]
    total = sum(r['amount'] for r in rows if r['status'] in COUNTED)
    return {'status': 'success', 'rows': rows, 'total': total, 'count': len(rows)}


@route('/api/sessions', methods=('GET',))
async def sessions(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    out = {}
    for r in bus.store.db.execute(
            "SELECT session, MIN(at) AS first_at, MAX(at) AS last_at, COUNT(*) AS n, "
            "SUM(CASE WHEN status IN (%s) THEN amount ELSE 0 END) AS total " % ','.join("'%s'" % s for s in COUNTED) +
            "FROM donations GROUP BY session"):
        out[r['session']] = dict(r, scores=0, started_at=None, ended_at=None)
    for r in bus.store.db.execute("SELECT session, MIN(at) AS first_at, MAX(at) AS last_at, COUNT(*) AS k "
                                  "FROM score_log GROUP BY session"):
        row = out.setdefault(r['session'], {'session': r['session'], 'first_at': r['first_at'], 'last_at': r['last_at'],
                                            'n': 0, 'total': 0, 'started_at': None, 'ended_at': None})
        row['scores'] = r['k']
        row['first_at'] = min(row['first_at'] or r['first_at'], r['first_at'])
        row['last_at'] = max(row['last_at'] or r['last_at'], r['last_at'])
    # 방송 시작 · 끝 기록 — 후원 · 점수가 하나도 없던 방송도 여기서 나온다
    for s in bus.state.get('session_log') or []:
        row = out.setdefault(s['id'], {'session': s['id'], 'first_at': s['started_at'], 'last_at': s['ended_at'] or s['started_at'],
                                       'n': 0, 'total': 0, 'scores': 0})
        row['started_at'], row['ended_at'] = s['started_at'], s['ended_at'] or None
    cur = bus.state.get('session').get('id') or ''
    rows = sorted(out.values(), key=lambda r: r.get('started_at') or r.get('first_at') or 0, reverse=True)[:100]
    for r in rows:
        r['current'] = r['session'] == cur and bool(bus.state.get('session').get('live'))
    return {'status': 'success', 'sessions': rows}


@route('/api/scores', methods=('GET',))
async def scores(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    cur = bus.store.db.execute('SELECT * FROM score_log WHERE session = ? ORDER BY id DESC LIMIT ?',
                               (_session(req, bus), _limit(req)))
    return {'status': 'success', 'rows': [dict(r) for r in cur]}
