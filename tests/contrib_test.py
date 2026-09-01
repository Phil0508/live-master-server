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
import time
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
print('① 시그니처 칸을 밟으면 기여도가 저절로 들어가는가')
print('=' * 74)
# ⚠️ 한 판 값을 0 으로 둔다. 가짜 시그니처가 전부 14,000원 이하라, 기본값(2만원)
#    이면 뺄 게 더 커서 기여도가 0 이 되고 아무 일도 안 일어난다.
#    '빼는 규칙' 자체는 ⑤ 에서 따로 본다.
post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'roll_price': 0})
d = get().get('dicegame') or {}
n = len(d.get('tiles') or [])
chk('판이 만들어졌다', n > 0, '%d칸' % n)

# 굴림은 무작위다. 어디에 서든 시그니처 칸이 되게 출발칸 빼고 전부 시그로 채운다.
made = 0
for i in range(1, n):
    c, _ = post('/api/dicegame/tile', {'id': i, 'type': 'sig', 'sig_id': 10003})
    if c == 200:
        made += 1
chk('시그니처 칸을 깔았다', made >= n - 1, '%d칸' % made)

s0, c0 = who(NAME)
code, r = post('/api/dicegame/roll', {'player': NAME})
chk('굴렸다', code == 200, r.get('tile'))
got = r.get('contrib') or {}
chk('누구에게 얼마가 갔는지 응답에 실린다', got.get('name') == NAME and got.get('points'), got)
s1, c1 = who(NAME)
chk('기여도가 저절로 올랐다 (누를 것 없이)', c1 > c0, '%d → %d' % (c0, c1))
chk('점수는 한 점도 안 올랐다 (그날 일당이다)', s1 == s0, '%d → %d' % (s0, s1))
# ⚠️ 슬롯은 3.3초 뒤 타이머가 카드를 올린다. 앞 구간의 슬롯이 끼어들 수 있으니
#    여기서는 '주사위 것' 만 센다.
chk('대기함에 누를 것이 안 남는다',
    not [p for p in (get().get('pending_donations') or [])
         if p.get('kind') == 'contrib' and '주사위' in str(p.get('name'))])

print()
print('=' * 74)
print('② 얼마가 들어갔나 ((시그 값 − 한 판 값) ÷ 10,000)')
print('=' * 74)
# 가짜 시그니처 10003 은 amount 10,300원. 한 판 값 0 이므로 반올림하면 1
chk('그 셈이 맞는다', got.get('points') == 1, got.get('points'))
# ⚠️ '어떻게 셈했는지' 가 같이 와야 한다. 운영자가 "왜 8점이지?" 를 알 수 있어야
#    셈이 틀려도 알아챈다.
_why = str(got.get('why') or '')
chk('셈한 근거가 붙어 있다', '원' in _why and '한 판' in _why, _why)

print()
print('=' * 74)
print('③ 한 번도 안 골랐으면 대기함에 남기는가 (아무에게나 주지 않는다)')
print('=' * 74)
# ⚠️ 기억이 없는데도 자동으로 넣으면 아무에게나 주는 것이 된다. 그때만 대기함으로.
d = get().get('dicegame') or {}
d['last_player'] = ''
post('/api/data', {'dicegame': d})
post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'roll_price': 0})
_n = len((get().get('dicegame') or {}).get('tiles') or [])
for i in range(1, _n):
    post('/api/dicegame/tile', {'id': i, 'type': 'sig', 'sig_id': 10003})
post('/api/data', {'pending_donations': []})
code, r = post('/api/dicegame/roll', {})
_items = [p for p in (get().get('pending_donations') or []) if p.get('kind') == 'contrib']
if (get().get('dicegame') or {}).get('last_player'):
    # 기억을 못 지웠다면 자동으로 들어간 것이 맞다 — 그것도 통과다
    chk('기억이 있으면 자동으로 들어간다 (대기함을 안 거친다)',
        r.get('contrib') and not [p for p in _items if '주사위' in str(p.get('name'))],
        r.get('contrib'))
else:
    chk('기억이 없으면 대기함에 남긴다', len(_items) == 1, '%d건' % len(_items))
    if _items:
        chk('무엇인지 알아볼 수 있다', '주사위' in str(_items[0].get('name')), _items[0].get('name'))
        chk('얼마를 줄지가 들어 있다', _items[0].get('contrib') == 1, _items[0].get('contrib'))

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
chk('누구에게 줄지 모르면 대기함에 남긴다 (주사위·슬롯이 같이 쓴다)',
    'def _contrib_alert(' in src)

print()
print('=' * 74)
print('⑥ 누르지 않아도 기여도가 올라가는가')
print('=' * 74)
# 사장님 말: "누르지말고 기여도가 자동으로 올라가게 해줘. 이미 플레이어를 고르고 게임하니까"
# ⚠️ 예전에는 굴릴 때 사람을 안 고르면 대기함에 알림으로 남아 한 번 더 눌러야 했다.
#    주사위를 굴리는 것도 폰, 누르는 것도 폰이라 같은 일을 두 번 하는 셈이었다.
#    이제 마지막으로 굴린 사람을 기억해 그 사람에게 넣는다.
src2 = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8', errors='replace').read()
chk('마지막으로 굴린 사람을 기억한다', '"last_player": ""' in src2)
chk('고르면 기억해 둔다', "g['last_player'] = player" in src2)
chk('안 고르면 기억한 사람에게 간다',
    "contrib_player = player or str(g.get('last_player') or '').strip()" in src2)
# ⚠️ 그 기억은 기여도에만 쓴다. 점수 칸에 쓰면 안 고른 판의 '그날 일당' 이
#    앞사람에게 들어가 정산이 틀어진다. 실제로 한 번 그렇게 만들었다가
#    dice_test 의 '차례를 안 고르면 점수는 안 움직인다' 가 잡았다.
chk('점수 칸은 기억을 안 쓴다 (그날 일당이라 위험하다)',
    "_dicegame_apply_score(state, player, int(tile['points']))" in src2)
chk('기여도만 기억을 쓴다',
    src2.count('_dicegame_apply_contrib(state, contrib_player') == 2)
# ⚠️ 자동으로 들어가는 값은 '누구에게 갔는지' 가 보여야 한다. 안 보이면 차례가
#    넘어갔는데 안 바꿔서 앞사람에게 들어가도 아무도 모른다.
mob = io.open(os.path.join(PROJ, 'mobile.html'), encoding='utf-8', errors='replace').read()
chk('폰 화면이 받은 사람을 보여준다',
    "d.contrib.name + ' 기여도 +'" in mob and "d.lap_contrib.name + ' 기여도 +'" in mob)

# 실제로 한 번 고르고, 그 뒤 안 고르고 굴려 본다
post('/api/data', {'bjs': [{'name': NAME, 'score': 0, 'contribution': 0}],
                   'pending_donations': []})
post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'roll_price': 0})
_n = len((get().get('dicegame') or {}).get('tiles') or [])
for i in range(1, _n):
    post('/api/dicegame/tile', {'id': i, 'type': 'sig', 'sig_id': 10040})
code, r = post('/api/dicegame/roll', {'player': NAME})
chk('고르고 굴리면 바로 들어간다', (r.get('contrib') or {}).get('name') == NAME, r.get('contrib'))
# ⚠️ 슬롯은 3.3초 뒤 타이머가 카드를 올린다. 앞 구간의 슬롯이 끼어들 수 있으니
#    여기서는 '주사위 것' 만 센다.
chk('대기함에 누를 것이 안 남는다',
    not [p for p in (get().get('pending_donations') or [])
         if p.get('kind') == 'contrib' and '주사위' in str(p.get('name'))])
d2 = get().get('dicegame') or {}
chk('그 사람을 기억했다', d2.get('last_player') == NAME, d2.get('last_player'))

print()
print('=' * 74)
print('⑦ 슬롯머신도 같은 셈인가')
print('=' * 74)
# 사장님 말: "슬롯머신도 아까 방식으로 2점 빼고 기여도만 올릴 수 있게"
# ⚠️ 주사위와 다른 점: 슬롯은 '굴린 사람' 이 없다. 차례가 없으니 서버가 누구 것인지
#    알 길이 없어 대기함 카드로 올린다 — 아무에게나 자동으로 넣으면 틀린 사람에게 준다.
src3 = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8', errors='replace').read()
# ⚠️ 지금 값이 아니라 '코드 기본값' 을 본다. 방송마다 바꾸는 값이라 지금 값은
#    무엇이든 될 수 있다 — 검사가 볼 것은 '안 정하면 2만원인가' 다.
chk('슬롯 한 판 값 기본이 2만원이다', '"slot_price": 20000,' in src3)
chk('당첨 값에서 한 판 값을 뺀다', 'round((_amt - _price) / 10000)' in src3)
chk('한 판 값 이하면 0 으로 둔다', 'max(0, round((_amt - _price) / 10000))' in src3)
chk('슬롯은 대기함 카드로 올린다 (굴린 사람이 없다)',
    "_contrib_alert(" in src3.split('def _slot_finish(')[1].split('def ')[0])
chk('점수는 안 건드린다 (슬롯 처리에 score 가 없다)',
    "'score'" not in src3.split('def _slot_finish(')[1].split('def ')[0])

# 실제로 돌려 본다 — 한 판 값을 낮춰 기여도가 나오게
post('/api/settings/patch', {'slot_price': 4000, 'slot_pool': [10040]})   # 40번 = 14,000원
time.sleep(4.5)   # 앞 구간에서 돌린 슬롯이 남아 있으면 먼저 흘려보낸다
post('/api/data', {'pending_donations': []})
code, _ = post('/api/slot/spin', {})
chk('슬롯이 돌았다', code == 200, code)
time.sleep(4.5)   # SLOT_RESULT_DELAY_SEC 뒤에 처리된다
_it = [p for p in (get().get('pending_donations') or [])
       if p.get('kind') == 'contrib' and '슬롯' in str(p.get('name'))]
chk('기여도 카드가 올라왔다', len(_it) >= 1, '%d건' % len(_it))
if _it:
    chk('셈이 맞는다 (14,000 − 4,000 = 1점)', _it[0].get('contrib') == 1, _it[0].get('contrib'))
    chk('슬롯 것이라고 알아볼 수 있다', '슬롯' in str(_it[0].get('name')), _it[0].get('name'))
    chk('셈한 근거가 적혀 있다', '한 판' in str(_it[0].get('message')), _it[0].get('message'))
post('/api/settings/patch', {'slot_price': 20000, 'slot_pool': []})

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
