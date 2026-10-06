# -*- coding: utf-8 -*-
"""🗓️ 월별 후원 순위 — 수요일 방송 시간에 들어온 후원만(옛 features/archive.py api_ranking_monthly 를 옮겼다).

GET /api/ranking/monthly[?month=YYYY-MM]   (로그인) 없으면 자료가 있는 가장 최근 달

옛 규칙 그대로
  - 방송 창: **수요일 17:00 ~ 목요일 03:00(한국 시각)**. 17:00 정각은 창 안, 03:00 정각은 창 밖(끝난 시각).
    그 밖에 들어온 후원(계좌로 딴 날 들어온 것 등)은 안 센다 — 순위는 방송에 온 사람들 것이다.
  - 목요일 새벽 후원은 그 방송이 시작한 **수요일** 에 붙는다(월말에 걸친 한 방송이 두 달로 쪼개지지 않게).
  - 같은 사람 묶기는 norm_donor(' 홍길동님 ' → '홍길동'). 익명과 순위에서 뺀 이름(donor_rules.excluded)은 뺀다.
  - 달 목록(months)은 창 안 후원이 있는 달 전부(뺀 이름도 센다), 순위는 합계 순(같으면 먼저 온 사람이 위).
  - days = 그 달에 몇 번의 방송(수요일)에 왔나.
v2 에서 달라진 것
  - 옛 장부는 서버 지역시 글자로 적혀 있어 BROADCAST_TZ_SHIFT 로 맞췄다(UTC 서버면 한 건도 안 잡히는 사고).
    v2 장부(donations.at)는 epoch 초라 한국 시각(UTC+9)으로 바로 옮긴다 — 서버 시간대와 상관없다.
  - 세는 후원 = rules.COUNTED(pending · assigned · ignored · archived — 옛 프로그램에서 옮겨 온 장부도 센다).
    1만 원 미만 '화면에만'(display)은 옛 장부에도 없었다.
"""
import datetime
import re
import time

from fastapi.responses import JSONResponse

from .legacy import route
from .rules import COUNTED, norm_donor

BC_START_H = 17      # 수요일 17:00 시작(정각은 창 안)
BC_END_H = 3         # 목요일 03:00 끝(정각은 창 밖 — 끝난 시각이다)
KST = datetime.timezone(datetime.timedelta(hours=9))
_MONTH_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


def bc_day(at):
    """이 후원(epoch 초)이 수요일 방송 창 안인가. 창 안이면 그 방송이 시작한 수요일 날짜, 아니면 None."""
    try:
        t = datetime.datetime.fromtimestamp(float(at), KST)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    wd = t.weekday()          # 월0 화1 수2 목3
    if wd == 2 and t.hour >= BC_START_H:
        return t.date()                                  # 수요일 저녁
    if wd == 3 and t.hour < BC_END_H:
        return (t - datetime.timedelta(days=1)).date()   # 목요일 새벽 → 어제(수)
    return None


def monthly(rows, excluded, want=''):
    """rows = [(at, name, amount)] 들어온 순서대로. 돌려받는 값: (고른 달, 순위 줄들, 달 목록)"""
    months, per = {}, {}
    for at, name, amount in rows:
        day = bc_day(at)
        if not day:
            continue                       # 방송 시간 밖 — 안 센다
        mon = '%04d-%02d' % (day.year, day.month)
        months[mon] = months.get(mon, 0) + 1
        per.setdefault(mon, []).append((day, name, amount))
    if not want:
        want = max(months) if months else datetime.datetime.now(KST).strftime('%Y-%m')
    tally = {}
    for day, name, amount in per.get(want, []):
        who = norm_donor(name)
        # ⚠️ 익명은 사람이 아니다 — 안 빼면 익명 여러 건이 한 덩어리로 순위 위쪽에 사람처럼 앉는다(옛 is_excluded)
        if who == '익명' or who in excluded:
            continue
        row = tally.setdefault(who, {'name': ' '.join(str(name or '').split()) or who, 'total': 0, 'count': 0, 'days': set()})
        row['total'] += int(amount or 0)
        row['count'] += 1
        row['days'].add(str(day))
    out = sorted(tally.values(), key=lambda r: -r['total'])
    for r in out:
        r['days'] = len(r['days'])
    return want, out, sorted(months, reverse=True)


@route('/api/ranking/monthly', methods=('GET',))
async def ranking_monthly(req, bus, authed, answer):
    if not authed(req):
        return JSONResponse({'status': 'error', 'message': '로그인이 필요합니다'}, status_code=401)
    want = (req.query_params.get('month') or '').strip()
    if want and not _MONTH_RE.match(want):
        return JSONResponse({'status': 'error', 'message': '달은 2026-10 모양으로 주세요'}, status_code=400)
    rows = [(r['at'], r['name'], r['amount']) for r in bus.store.db.execute(
        'SELECT at, name, amount FROM donations WHERE status IN (%s) ORDER BY at, rowid' % ','.join('?' * len(COUNTED)), COUNTED)]
    excluded = set(bus.state.get('donor_rules').get('excluded') or [])
    month, out, months = monthly(rows, excluded, want)
    now = datetime.datetime.now(KST)
    return {'status': 'success', 'month': month, 'rows': out, 'total': sum(r['total'] for r in out), 'months': months,
            'clock': {'server_kst': now.strftime('%Y-%m-%d %H:%M:%S'), 'tz': 'KST(UTC+9)', 'epoch': int(time.time())},
            'window': '수요일 %02d:00 ~ 목요일 %02d:00' % (BC_START_H, BC_END_H)}
