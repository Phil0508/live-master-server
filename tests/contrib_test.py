# -*- coding: utf-8 -*-
"""🎯 게임에서 나온 것은 기여도로만 — 점수(그날 일당)에 섞이면 안 된다.

왜 만들었나
  사장님 말: "점수는 정말 그날 일당이고, 기여도는 게임 점수로 얼마든지 오르락
  내리락 할 수 있게 만들어 놓은 거야. 주사위게임에서 시그니처가 재생되면 점수가
  아니라 기여도로만 들어가야 한다."

  그런데 조종실의 지급 버튼은 늘 delta 만 보냈고, 서버는 contribution 이 없으면
  delta 를 기여도에도 그대로 넣는다(server.py 의 `contrib = delta if ... is None`).
  그래서 무엇을 주든 점수와 기여도가 같이 올랐다.

여기서 지키는 것
  ① 주사위 시그니처 칸을 밟으면 '기여도만' 알림이 대기함에 생긴다
  ② 그 알림에는 얼마를 줄지가 들어 있다 — (시그니처 값 − 한 판 값) ÷ 10,000
  ③ 그걸 지급하면 점수는 한 점도 안 오르고 기여도만 오른다
  ④ 기존 후원은 예전 그대로 — 점수와 기여도가 같이 오른다 (한 줄도 안 바뀌어야 한다)

⚠️ 돈이 움직이는 길이다. ④ 가 깨지면 그날 정산이 통째로 틀어진다.
"""
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
REPO = r'C:\Users\Administrator\Desktop\새로다시시작'


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


def post(path, obj=None, authed=True):
    hdr = H if authed else {'Content-Type': 'application/json'}
    r = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), hdr)
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=H), timeout=25) as r:
        return json.loads(r.read().decode())


def who(name):
    for b in (get().get('bjs') or []):
        if b.get('name') == name:
            return int(b.get('score') or 0), int(b.get('contribution') or 0)
    return None


NAME = '기여도시험'
post('/api/data', {'bjs': [{'name': NAME, 'score': 0, 'contribution': 0}],
                   'pending_donations': []})

print('=' * 74)
print('① 주사위 시그니처 칸을 밟으면 기여도 알림이 생기는가')
print('=' * 74)
# ⚠️ 한 판 값을 0 으로 둔다. 가짜 시그니처가 전부 14,000원 이하라, 기본값(2만원)
#    이면 뺄 게 더 커서 기여도가 0 이 되고 알림 자체가 안 생긴다.
#    '빼는 규칙' 자체는 ⑤ 에서 따로 본다.
post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'roll_price': 0})
d = get().get('dicegame') or {}
n = len(d.get('tiles') or [])
chk('판이 만들어졌다', n > 0, '%d칸' % n)

# ⚠️ 굴림은 무작위다. 어디에 서든 시그니처 칸이 되게 출발칸 빼고 전부 시그로 채운다.
made = 0
for i in range(1, n):
    c, _ = post('/api/dicegame/tile', {'id': i, 'type': 'sig', 'sig_id': 10003})
    if c == 200:
        made += 1
chk('시그니처 칸을 깔았다', made >= n - 1, '%d칸' % made)

before = len(get().get('pending_donations') or [])
c, r = post('/api/dicegame/roll', {})
chk('굴렸다', c == 200, r.get('tile'))
pend = get().get('pending_donations') or []
contrib_items = [p for p in pend if p.get('kind') == 'contrib']
chk('기여도 전용 알림이 대기함에 생겼다', len(contrib_items) == 1,
    '대기함 %d건 중 기여도 %d건' % (len(pend), len(contrib_items)))

print()
print('=' * 74)
print('② 얼마를 줄지가 들어 있는가 ((시그 값 − 한 판 값) ÷ 10,000)')
print('=' * 74)
item = contrib_items[0] if contrib_items else {}
# 가짜 시그니처 10003 은 amount 10300 (boot_sig.py) → 반올림하면 1
chk('기여도 값이 들어 있다', isinstance(item.get('contrib'), int) and item['contrib'] >= 1,
    item.get('contrib'))
# ⚠️ 알림에는 금액이 아니라 '어떻게 셈했는지' 가 들어간다. 운영자가 카드만 보고
#    "왜 8점이지?" 를 알 수 있어야 한다 — 안 그러면 셈이 틀려도 아무도 모른다.
_msg = str(item.get('message') or '')
chk('셈한 근거가 적혀 있다 (시그 값 − 한 판 값)',
    '원' in _msg and '한 판' in _msg, _msg)
# 한 판 값을 0 으로 뒀으므로 시그니처 값(10,300원)이 그대로 환산돼 1 이다
chk('그 셈이 맞는다', item.get('contrib') == 1, item.get('contrib'))
chk('무엇인지 알아볼 수 있다', '주사위' in str(item.get('name')), item.get('name'))

print()
print('=' * 74)
print('③ 지급하면 점수는 그대로, 기여도만 오르는가')
print('=' * 74)
"""⚠️ 조종실은 delta 0 · contribution N 으로 부른다. contribution 을 빼먹으면
   서버가 delta 를 기여도에도 넣어(=0) 아무것도 안 오른다 — 그것도 사고다."""
s0, c0 = who(NAME)
add = int(item.get('contrib') or 0)
code, _ = post('/api/score/add', {'scope': 'rank', 'name': NAME,
                                  'delta': 0, 'contribution': add,
                                  'pending_id': item.get('id')})
chk('지급이 받아들여졌다', code == 200, code)
s1, c1 = who(NAME)
chk('점수는 한 점도 안 올랐다 (그날 일당이다)', s1 == s0, '%d → %d' % (s0, s1))
chk('기여도만 올랐다', c1 == c0 + add, '%d → %d (+%d)' % (c0, c1, add))
left = [p for p in (get().get('pending_donations') or []) if p.get('id') == item.get('id')]
chk('대기함에서 빠졌다', not left)

print()
print('=' * 74)
print('④ 기존 후원은 예전 그대로인가 (점수와 기여도가 같이 오른다)')
print('=' * 74)
"""⚠️ 여기가 깨지면 그날 정산이 통째로 틀어진다. 기여도 기능을 넣으면서
   기존 후원 경로를 건드리지 않았는지 보는 검사다."""
s0, c0 = who(NAME)
code, _ = post('/api/score/add', {'scope': 'rank', 'name': NAME, 'delta': 5})
chk('후원 지급이 받아들여졌다', code == 200, code)
s1, c1 = who(NAME)
chk('점수가 올랐다', s1 == s0 + 5, '%d → %d' % (s0, s1))
chk('기여도도 같이 올랐다 (contribution 을 안 보내면 delta 를 따라간다)',
    c1 == c0 + 5, '%d → %d' % (c0, c1))

print()
print('=' * 74)
print('⑤ 주사위 규칙 — 사장님이 정한 셈')
print('=' * 74)
# ① 주사위는 하나로 굴린다
# ② 시그니처 기여도 = (시그 값 − 한 판 값) ÷ 10,000
#    한 판이 2만원이면 그 후원으로 이미 2점이 올라갔다. 10만원짜리 시그가 걸리면
#    10 − 2 = 8점만 더 준다. 통째로 또 주면 2점이 두 번 셈된다.
# ③ 출발 칸을 넘어가면 기여도 5점
#
# ⚠️ 굴림은 앞 연출이 끝나야 받아준다(429). 여기서는 그 사이를 기다리지 않고
#    '셈이 맞는가' 만 본다 — 기다리며 굴리는 것은 2026-08-31 에 손으로 확인했다.
#      한 판 20,000원 · 시그 14,000원 → 기여도 0
#      한 판  4,000원 · 시그 14,000원 → 기여도 1
#      한 바퀴 → 기여도 +5, 점수 0 그대로
c, g0 = post('/api/dicegame/setup', {'cols': 7, 'rows': 5})
d = get().get('dicegame') or {}
chk('주사위가 한 개다', d.get('dice') == 1, d.get('dice'))
chk('한 판 값이 있다 (기본 2만원)', d.get('roll_price') == 20000, d.get('roll_price'))
chk('한 바퀴 기여도가 있다 (기본 5)', d.get('lap_contrib') == 5, d.get('lap_contrib'))

# ⚠️ 한 판 값을 바꿀 길이 없으면 방송마다 단가가 달라질 때 손을 못 댄다
c, r = post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'roll_price': 30000, 'lap_contrib': 7})
chk('설정으로 바꿀 수 있다', r.get('roll_price') == 30000 and r.get('lap_contrib') == 7, r)
# 크기만 바꿨다고 단가가 기본값으로 되돌아가면 그게 사고다
c, r = post('/api/dicegame/setup', {'cols': 8, 'rows': 5})
chk('크기만 바꾸면 단가는 그대로 이어받는다',
    r.get('roll_price') == 30000 and r.get('lap_contrib') == 7, r)
post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'roll_price': 20000, 'lap_contrib': 5})

src = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8', errors='replace').read()
chk('시그니처에서 한 판 값을 뺀다',
    'round((_sig_amt - _price) / 10000)' in src)
chk('한 판 값보다 싼 시그는 0 으로 둔다 (빼앗지 않는다)',
    'max(0, round((_sig_amt - _price) / 10000))' in src)
chk('한 바퀴에 기여도를 준다', "_lap_c = max(0, _as_int(g.get('lap_contrib'), 5) or 0)" in src)
# ⚠️ 점수(그날 일당)에 섞이면 안 된다 — 기여도만 넣는 도우미를 쓴다
chk('기여도만 넣는 길로 간다 (점수 도우미가 아니다)',
    'def _dicegame_apply_contrib(' in src and "t['contribution'] = (t.get('contribution') or 0) + contrib" in src)
chk('그 도우미는 점수를 안 건드린다',
    "def _dicegame_apply_contrib(" in src
    and "t['score']" not in src.split('def _dicegame_apply_contrib(')[1].split('def ')[0])
# ⚠️ 누구 차례인지 안 골랐으면 잃어버리지 말고 조종실에 남긴다
chk('누구 차례인지 모르면 대기함에 남긴다', 'def _dicegame_contrib_alert(' in src)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
