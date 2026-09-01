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
  ② 그 알림에는 얼마를 줄지(기여도)가 들어 있다 — 시그니처 값 ÷ 10,000
  ③ 그걸 지급하면 점수는 한 점도 안 오르고 기여도만 오른다
  ④ 기존 후원은 예전 그대로 — 점수와 기여도가 같이 오른다 (한 줄도 안 바뀌어야 한다)

⚠️ 돈이 움직이는 길이다. ④ 가 깨지면 그날 정산이 통째로 틀어진다.
"""
import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
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
post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'dice': 2})
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
print('② 얼마를 줄지가 들어 있는가 (시그니처 값 ÷ 10,000)')
print('=' * 74)
item = contrib_items[0] if contrib_items else {}
# 가짜 시그니처 10003 은 amount 10300 (boot_sig.py) → 반올림하면 1
chk('기여도 값이 들어 있다', isinstance(item.get('contrib'), int) and item['contrib'] >= 1,
    item.get('contrib'))
chk('시그니처 값과 자가 맞는다 (금액÷10000 반올림)',
    item.get('contrib') == max(1, round(int(item.get('amount') or 0) / 10000)),
    '금액 %s → 기여도 %s' % (item.get('amount'), item.get('contrib')))
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
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
