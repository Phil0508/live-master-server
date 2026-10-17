# -*- coding: utf-8 -*-
"""📒 장부 보기 — 이번 방송 · 지난 방송 후원 기록, 점수 기록.

GET /api/ledger?session=<id|current>&q=<이름>&limit=200   (로그인)
GET /api/sessions                                          (로그인) 방송 회차 목록 · 회차별 합계
GET /api/scores?session=<id|current>&limit=200             (로그인) 점수 장부(되돌린 것 표시)
GET /api/ledger/settle?session=<id|current>                (로그인) 💱 정산 차액 — 실제 받은 돈 · 점수로 들어간 돈 · 차액과 그 까닭(settle())
⚠️ 옛 서버는 방송을 끝낼 때 장부를 보관 표로 옮기고 지웠다(옮기다 실패하면 500). v2 는 지우지 않는다 —
   후원마다 방송 회차(session)가 적혀 있어서 회차로 골라 보면 된다.
"""
from fastapi.responses import JSONResponse

from .legacy import route
from .rules import COUNTED, POINT_WON, man_won


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
    # 🙈 금칙어 · 전화 · 계좌 · 주소에 걸린 줄 — 원문(message)은 그대로, 방송에 나가는 글을 mask{hits, text} 로 곁들인다(mask.py)
    from . import mask as mk
    m = bus.state.get('mask')
    out = []
    for r in rows:
        n = mk.note(r.get('message'), m)
        out.append(dict(r, mask=n) if n else r)
    rows = out
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


# ── 💱 정산 차액(대표님 10-17) ─────────────────────────────
# 조종실 랭킹 탭 숫자 카드 밑 한 줄 — '실제 받은 돈' 과 '점수로 들어간 돈' 이 왜 다른지 서버가 센다(화면은 받아 적기만).
SETTLE_WHY = (
    ('cut', '만 원 단위로 맞추며 버린 자투리', '5,999원까지는 점수가 안 돼요(예: 15,000원 → 1점)'),
    ('up', '만 원 단위로 올려 준 몫', '6천 원부터 1만 원으로 쳐요(예: 6,000원 → 1점)'),
    ('pending', '아직 대기함에 있는 후원', '누구에게 줄지 고르면 점수로 들어가요'),
    ('ignored', '무시한 후원', '대기함에서 [무시] 를 눌러 점수로 안 넣은 것'),
    ('test', '테스트 후원을 점수로 준 것', '🧪 투네이션 테스트 — 실제 돈이 아니에요'),
    ('archived', '옛 프로그램 장부에서 옮긴 것', '누구에게 갔는지 몰라 점수로 안 셌어요'),
)


def settle(rows, logged=None):
    """이번 방송 장부 줄들 → 정산 차액.

       실제 받은 돈 = 합계에 세는 줄(COUNTED — 화면에만 · 🔁 다시 보기 · 🧪 대시보드 테스트는 'display' 라 이미 빠짐)에서
                      🧪 투네이션 테스트(source 'toonation_test')까지 뺀 금액 합.
       점수로 들어간 돈 = 배정한 후원(status 'assigned')마다 만 원 단위 점수(man_won = (금액+4000)//10000) × 1만 원.
       차액 = 실제 − 점수, 그리고 **까닭들의 합이 언제나 차액과 같다**(검사가 지킨다):
         cut(+) 자투리 버림 · up(−) 올림 · pending(+) 대기함 · ignored(+) 무시 · test(−) 테스트를 준 것 · archived(+) 옛 장부
       logged — {후원 id: 점수 기록에 실제로 남은 점수 합}(되돌린 것 빼고). 있으면 규칙 점수와 다른 배정(나눠 줄 때 점수를 손으로
                바꾼 것)을 '참고' 로 따로 센다(차액 셈에는 안 넣는다 — 차액은 만 원 규칙으로 센다)."""
    out = {'real': 0, 'real_n': 0, 'scored': 0, 'scored_pts': 0, 'scored_n': 0, 'small_zero_n': 0}
    why = {k: {'won': 0, 'n': 0} for k, _, _ in SETTLE_WHY}
    gap_pts, gap_n = 0, 0
    for r in rows or []:
        st = r.get('status')
        if st not in COUNTED:
            continue
        try:
            a = int(r.get('amount') or 0)
        except (TypeError, ValueError):
            a = 0
        test = r.get('source') == 'toonation_test'
        pts = man_won(a)
        if not test:
            out['real'] += a
            out['real_n'] += 1
        if st == 'assigned':
            out['scored'] += pts * POINT_WON
            out['scored_pts'] += pts
            out['scored_n'] += 1
            if test:
                why['test']['won'] -= pts * POINT_WON
                why['test']['n'] += 1
            else:
                rest = a - pts * POINT_WON
                if rest > 0:
                    why['cut']['won'] += rest
                    why['cut']['n'] += 1
                    if pts == 0:
                        out['small_zero_n'] += 1
                elif rest < 0:
                    why['up']['won'] += rest
                    why['up']['n'] += 1
            if logged is not None and r.get('id') in logged and int(logged[r.get('id')] or 0) != pts:
                gap_pts += pts - int(logged[r.get('id')] or 0)
                gap_n += 1
        elif not test and st in why:
            why[st]['won'] += a
            why[st]['n'] += 1
    out['diff'] = out['real'] - out['scored']
    out['why'] = [{'key': k, 'label': lb, 'hint': hint, 'won': why[k]['won'], 'n': why[k]['n']} for k, lb, hint in SETTLE_WHY]
    out['hand'] = {'won': gap_pts * POINT_WON, 'n': gap_n}     # 참고: 점수 기록이 만 원 규칙과 다른 배정
    return out


def logged_points(store, session):
    """후원 id → 점수 기록에 남은 점수 합(되돌린 것 · 기여도 · 운영비 · 모금함 빼고 본판 · 번외 판만)."""
    cur = store.db.execute("SELECT ref, SUM(delta) AS d FROM score_log WHERE session = ? AND field = 'score' AND undone = 0 "
                           "AND list IN ('list', 'extra') AND substr(ref, 1, 4) = 'don_' GROUP BY ref", (session,))
    return {r['ref']: int(r['d'] or 0) for r in cur}


@route('/api/ledger/settle', methods=('GET',))
async def ledger_settle(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    sid = _session(req, bus)
    try:
        rows = bus.store.donations(session=sid, limit=100000)
        return {'status': 'success', 'session': sid, 'settle': settle(rows, logged_points(bus.store, sid))}
    except Exception as e:
        print('⚠️ [정산 차액] 셈 실패: %s' % type(e).__name__, flush=True)
        return {'status': 'error', 'message': '정산 차액을 못 셌어요'}
