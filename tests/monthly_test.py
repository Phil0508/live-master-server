# -*- coding: utf-8 -*-
"""🗓️ 월별 후원 순위 — 수요일 방송 시간(수 17:00 ~ 목 03:00)만 센다.

사장님 말
  "월별 후원 순위를 만들고 싶어. 근데 다른 날에 말고 오로지 수요일 17:00부터
   목요일 03:00까지의 집계로."

여기서 지키는 것
  ① 창 판정이 경계에서 정확한가 — 여기가 틀리면 순위가 통째로 틀린다
  ② 자정을 넘겨도 '시작한 날(수요일)' 에 붙는가 — 안 그러면 월말 방송이 두 달로 쪼개진다
  ③ 아무나 남의 후원 장부를 못 보는가
  ④ 시간대가 어긋났을 때 눈으로 보이는가

⚠️ 후원 시각은 time.strftime 으로 **서버 지역시** 로 적힌다. 배포 설정에 시간대
   지정이 없어 우분투 기본대로면 UTC 다 — 그러면 KST 수요일 17시가 DB 에는 08시로
   적혀 있어, 그대로 걸러내면 한 건도 안 잡힌다. BROADCAST_TZ_SHIFT 로 맞춘다.
   화면이 서버 시계를 같이 띄우므로 어긋나면 바로 보인다.
"""
import datetime
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))


def _find_proj():
    d = HERE
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.exists(os.path.join(d, 'server.py')):
            return d
    return REPO


PROJ = _find_proj()
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:120]) if detail else ''))


def get(path, authed=True):
    hdr = {'Authorization': H['Authorization']} if authed else {}
    r = urllib.request.Request(B + path, headers=hdr)
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


# ── 창 판정은 서버와 같은 셈을 여기서도 돌려 경계를 본다.
#    ⚠️ 서버를 안 띄우고도 이 부분은 검사할 수 있어야 한다 — 제일 중요한 규칙이다.
BC_START_H, BC_END_H = 17, 3


def win(ts, shift=0):
    try:
        t = datetime.datetime.strptime(str(ts)[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None
    t += datetime.timedelta(hours=shift)
    wd = t.weekday()
    if wd == 2 and t.hour >= BC_START_H:
        return str(t.date())
    if wd == 3 and t.hour < BC_END_H:
        return str((t - datetime.timedelta(days=1)).date())
    return None


print('=' * 74)
print('① 창 판정이 경계에서 정확한가')
print('=' * 74)
# ⚠️ 정각이 제일 위험하다. 17:00 은 '시작했다'(안), 03:00 은 '끝났다'(밖).
CASES = [
    ('2026-09-02 16:59:59', None, '수 16:59 — 아직 시작 전'),
    ('2026-09-02 17:00:00', '2026-09-02', '수 17:00 정각 — 시작했다'),
    ('2026-09-03 00:00:00', '2026-09-02', '목 자정 — 같은 방송'),
    ('2026-09-03 02:59:59', '2026-09-02', '목 02:59 — 아직 방송 중'),
    ('2026-09-03 03:00:00', None, '목 03:00 정각 — 끝났다'),
    ('2026-09-05 20:00:00', None, '토요일 — 방송일이 아니다'),
    ('2026-09-02 09:00:00', None, '수 오전 — 창 밖'),
    ('망가진 값', None, '이상한 값도 안 터진다'),
    (None, None, '빈 값도 안 터진다'),
]
for ts, want, why in CASES:
    got = win(ts)
    chk('%s' % why, got == want, '%s → %s' % (ts, got or '(안 셈)'))

print()
print('=' * 74)
print('② 자정을 넘겨도 시작한 날에 붙는가')
print('=' * 74)
# ⚠️ 월말 방송이 두 달로 쪼개지면 '9월 순위' 가 틀린다.
chk('월말 수요일은 그 달에 붙는다', win('2026-09-30 22:00:00') == '2026-09-30')
chk('그 방송의 목요일 새벽도 같은 달(9월)에 붙는다',
    win('2026-10-01 01:00:00') == '2026-09-30', win('2026-10-01 01:00:00'))

print()
print('=' * 74)
print('③ 서버가 같은 셈을 쓰는가')
print('=' * 74)
src = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8', errors='replace').read()
chk('창 시각이 상수로 잡혀 있다', 'BC_START_H = 17' in src and 'BC_END_H = 3' in src)
chk('수요일 저녁을 센다', "if wd == 2 and t.hour >= BC_START_H:" in src)
chk('목요일 새벽은 어제(수)로 붙인다',
    "return (t - datetime.timedelta(days=1)).date()" in src)
# ⚠️ 시간대 보정이 없으면 서버가 UTC 일 때 한 건도 안 잡힌다
chk('시간대를 보정할 수 있다', "os.environ.get('BROADCAST_TZ_SHIFT'" in src)
chk('지난 방송분과 이번 방송분을 같이 본다',
    "for tbl in ('donation_archive', 'donation_history')" in src)

print()
print('=' * 74)
print('④ 아무나 남의 후원 장부를 볼 수 없는가')
print('=' * 74)
"""⚠️ 누가 얼마를 냈는지는 남의 돈 이야기다. 인증 없이 열리면 안 된다."""
code, _ = get('/api/ranking/monthly', authed=False)
chk('인증 없이는 막힌다', code in (401, 403), 'HTTP %d' % code)
code, d = get('/api/ranking/monthly')
chk('인증하면 열린다', code == 200, 'HTTP %d' % code)

print()
print('=' * 74)
print('⑤ 시간대가 어긋났을 때 눈으로 보이는가')
print('=' * 74)
# ⚠️ 창이 어긋나면 순위가 그냥 '비어' 보인다. 왜 비었는지 알 길이 없으면 못 고친다.
chk('서버 시계를 같이 알려준다', isinstance(d.get('clock'), dict) and d['clock'].get('server'),
    (d.get('clock') or {}).get('server'))
chk('몇 시간 보정했는지 알려준다', 'shift' in (d.get('clock') or {}))
chk('창이 무엇인지 알려준다', '수요일' in str(d.get('window')), d.get('window'))
ctl = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8', errors='replace').read()
chk('조종실이 서버 시계를 띄운다', "id=\"mon-clock\"" in ctl)
chk('어긋나면 경고한다', '서버 시계가 다릅니다' in ctl)
chk('조종실에 순위판이 있다', 'id="mon-rows"' in ctl and 'loadMonthly' in ctl)
chk('탭을 열 때 불러온다', 'loadMonthly(true);' in ctl)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
