# -*- coding: utf-8 -*-
"""🏃 퇴근빵은 '실제 번 돈'으로만 찬다.

■ 사장님이 정한 것
  "실제 번돈이 낫지"
  퇴근빵 막대는 **점수(그날 일당)** 로만 찬다. 게임에서 딴 기여도는 안 들어간다.
  퇴근 = 오늘 목표한 돈을 벌었다는 뜻이라, 게임 점수가 섞이면 그 뜻이 없어진다.

■ ⚠️ 왜 이 검사를 따로 두나
  이 규칙에는 검사가 하나도 없었다. 그래서 실제로 이런 일이 있었다 —
  기여도 셈을 손보다가 '후원은 기여도를 안 올린다' 로 바꿨는데, 그러면 점수와
  기여도의 관계가 통째로 달라지면서 퇴근빵도 조용히 딴 값을 보게 된다.
  아무도 안 보고 있으면 방송 중에야 알게 된다.

  헷갈리기 쉬운 자리이기도 하다. 게임에서 기여도를 받으면 엑셀판에는 목표를
  채운 것처럼 보이는데 퇴근빵 막대는 안 움직인다. 그게 맞는 동작이다.

■ 세 곳이 같은 기준을 써야 한다
  ① 방송 화면 막대(overlay)  ② 조종실 현재값(controller)  ③ 퇴근 카드 판정
  한 곳만 어긋나도 '막대는 안 찼는데 퇴근 카드가 뜨는' 꼴이 난다.
"""
import io
import json
import os
import sys
import time
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


def post(p, d=None):
    r = urllib.request.Request(B + p, data=json.dumps(d or {}).encode(), headers=H, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}


def get():
    r = urllib.request.Request(B + '/api/data', headers={'Authorization': H['Authorization']})
    return json.loads(urllib.request.urlopen(r, timeout=25).read().decode())


def who(name):
    for b in get().get('bjs') or []:
        if b.get('name') == name:
            return int(b.get('score') or 0), int(b.get('contribution') or 0)
    return 0, 0


def cards():
    return [p.get('name') for p in (get().get('pending_donations') or [])
            if p.get('type') == 'off_work']


def reset():
    post('/api/restore', {
        'broadcast_active': True, 'home_race_enabled': True,
        'home_goals': {'가': 50000, '나': 50000},
        'bjs': [{'name': '가', 'score': 0, 'contribution': 0},
                {'name': '나', 'score': 0, 'contribution': 0}],
        'bottom_fixed': {'name': '운영비', 'score': 0},
        'pending_donations': [], 'logs': [], 'home_race_notified': []})


print('=' * 74)
print('① 게임에서 딴 기여도로는 퇴근빵이 안 찬다  ← 핵심')
print('=' * 74)
"""⚠️ 여기가 뒤집히면 게임만 잘해도 퇴근한다. '오늘 목표한 돈을 벌었다' 는 뜻이 없어진다."""
reset()
post('/api/score/add', {'name': '나', 'delta': 30000, 'reason': '후원'})
s0, c0 = who('나')
chk('후원 3만원 — 점수가 올랐다', s0 == 30000, s0)

# 게임에서 기여도 2만점. 기여도로는 목표(5만)를 넘지만 점수는 3만 그대로다.
post('/api/score/add', {'name': '나', 'delta': 0, 'contribution': 20000, 'reason': '게임'})
s1, c1 = who('나')
chk('게임 기여도를 받아도 점수는 안 오른다', s1 == 30000, s1)
chk('기여도만 목표를 넘었다 (엑셀판에는 다 찬 것처럼 보인다)', c1 >= 50000, c1)
time.sleep(0.5)
chk('⚠️ 그래도 퇴근 카드가 안 뜬다', '나' not in cards(), cards())

print()
print('=' * 74)
print('② 실제로 번 돈이 목표를 채우면 퇴근한다')
print('=' * 74)
post('/api/score/add', {'name': '나', 'delta': 20000, 'reason': '후원'})
s2, _ = who('나')
chk('점수가 목표에 닿았다', s2 == 50000, s2)
code, _ = post('/api/offwork/pending', {'name': '나'})
chk('퇴근 카드가 만들어진다', code == 200 and '나' in cards(), cards())
chk('목표를 안 채운 사람은 카드가 없다', '가' not in cards(), cards())

print()
print('=' * 74)
print('③ 같은 사람에게 카드가 두 번 안 생긴다')
print('=' * 74)
"""⚠️ 퇴근 카드는 조종실이 점수가 바뀔 때마다 확인해서 만든다. 막지 않으면
   후원이 들어올 때마다 같은 사람의 퇴근 카드가 계속 쌓인다."""
post('/api/offwork/pending', {'name': '나'})
post('/api/offwork/pending', {'name': '나'})
chk('세 번 불러도 카드는 하나', cards().count('나') == 1, cards())

print()
print('=' * 74)
print('④ 세 곳이 같은 기준(점수)을 쓰는가')
print('=' * 74)
"""⚠️ 한 곳만 어긋나면 '막대는 안 찼는데 퇴근 카드가 뜨는' 꼴이 난다."""
ov = io.open(os.path.join(PROJ, 'overlay.html'), encoding='utf-8', errors='replace').read()
ctl = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8', errors='replace').read()
chk('① 방송 화면 막대 — 점수', "const cur = b.score || 0;   // 진행 기준은 점수(score)" in ov)
chk('② 조종실 현재값 — 점수', 'const cur = b.score || 0;' in ctl)
chk('③ 퇴근 카드 판정 — 점수',
    "if (goal > 0 && (b.score || 0) >= goal) addOffWorkPendingCard(b.name);" in ctl)
chk('세 곳 어디에도 기여도가 안 들어간다',
    'contribution' not in ctl.split('function checkHomeRaceGoals')[1].split('}')[0])

print()
print('=' * 74)
print('⑤ 목표를 새로 정하면 다시 퇴근할 수 있다')
print('=' * 74)
# ⚠️ 목표를 올렸는데 '이미 퇴근했다' 는 기록이 남아 있으면 두 번 다시 카드를 못 받는다
reset()
post('/api/score/add', {'name': '가', 'delta': 60000, 'reason': '후원'})
post('/api/offwork/pending', {'name': '가'})
chk('첫 퇴근 카드', '가' in cards())
st = get()
chk("'이미 알렸다' 기록이 남는다", '가' in (st.get('home_race_notified') or []),
    st.get('home_race_notified'))
ctl_ok = "delete gd.home_race_notified" in ctl or 'home_race_notified' in ctl
chk('목표를 다시 정하면 그 기록을 지운다 (조종실)', ctl_ok)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
sys.exit(1 if BAD else 0)
