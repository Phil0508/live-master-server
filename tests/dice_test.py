# -*- coding: utf-8 -*-
"""주사위게임 — 서버가 유일한 진실인지, 점수·큐가 안 틀어지는지.

굴림 사이에 move 를 끼우면 연타 방지(직전 action 이 ROLL 일 때만)를 지나갈 수 있어
검사가 몇십 초씩 기다리지 않아도 된다.
"""
import io
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


def post(path, obj=None, authed=True):
    hdr = H if authed else {'Content-Type': 'application/json'}
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), hdr)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get(authed=True):
    hdr = H if authed else {}
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=hdr), timeout=25) as r:
        return json.loads(r.read().decode())


def dg():
    return get().get('dicegame') or {}


def reset_all():
    post('/api/restore', {'broadcast_active': True,
                          'bjs': [{'name': '제이양', 'score': 0, 'contribution': 0},
                                  {'name': '밍밍', 'score': 0, 'contribution': 0}],
                          'pending_donations': [], 'logs': [], 'reaction_queue': []})


print('=' * 74)
print('① 판 깔기 — 고리 칸 수와 잘라내기')
print('=' * 74)
reset_all()
c, r = post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'dice': 2})
chk('7×5 → 테두리 20칸', c == 200 and r.get('tiles') == 20, r)
g = dg()
chk('0번 칸은 출발', (g['tiles'][0] or {}).get('type') == 'start')
chk('말은 출발에, 켜짐', g.get('pos') == 0 and g.get('enabled') is True)
c, r = post('/api/dicegame/setup', {'cols': 999, 'rows': -3, 'dice': 9})
g = dg()
chk('말도 안 되는 크기는 잘라낸다 (10×3, 주사위 2)',
    g.get('cols') == 10 and g.get('rows') == 3 and g.get('dice') == 2,
    (g.get('cols'), g.get('rows'), g.get('dice')))
c, _ = post('/api/dicegame/setup', {'cols': '일곱'})
chk('숫자가 아니면 잘라내지 않고 400', c == 400, c)

print()
print('=' * 74)
print('② 로그인 없이는 못 만진다 · 황금열쇠 덱은 감춘다')
print('=' * 74)
for p in ('setup', 'roll', 'tile', 'keys', 'move', 'reset', 'enable'):
    c, _ = post('/api/dicegame/' + p, {}, authed=False)
    chk('/api/dicegame/%s → 막힘' % p, c == 401, c)
post('/api/dicegame/setup', {'cols': 7, 'rows': 5})
post('/api/dicegame/keys', {'keys': ['비밀1', '비밀2']})
pub = get(False).get('dicegame') or {}
chk('무인증에는 덱이 빈 목록', pub.get('keys') == [], pub.get('keys'))
chk('장수는 알려준다(화면 표시용)', pub.get('keys_count') == 2, pub.get('keys_count'))
chk('판 자체는 보인다', len(pub.get('tiles') or []) == 20)

print()
print('=' * 74)
print('③ 칸 편집')
print('=' * 74)
c, _ = post('/api/dicegame/tile', {'id': 3, 'type': 'mission', 'label': '팔굽혀펴기'})
chk('미션 칸 저장', c == 200)
c, _ = post('/api/dicegame/tile', {'id': 5, 'type': 'score', 'points': 99999})
chk('점수 칸 저장(±1000 으로 잘림)', c == 200 and (dg()['tiles'][5] or {}).get('points') == 1000)
c, _ = post('/api/dicegame/tile', {'id': 6, 'type': 'sig', 'sig_id': 10003})
t6 = dg()['tiles'][6] or {}
chk('시그니처 칸 — 재생 정보까지 미리 담긴다', c == 200 and (t6.get('sig') or {}).get('sound_url'),
    list((t6.get('sig') or {}).keys())[:4])
c, _ = post('/api/dicegame/tile', {'id': 0, 'type': 'mission', 'label': 'x'})
chk('출발 칸은 못 바꾼다', c == 400, c)
c, _ = post('/api/dicegame/tile', {'id': 999, 'type': 'mission'})
chk('없는 칸 → 400', c == 400, c)
c, _ = post('/api/dicegame/tile', {'id': 4, 'type': '함정'})
chk('모르는 종류 → 400', c == 400, c)
c, _ = post('/api/dicegame/tile', {'id': 4, 'type': 'sig'})
chk('시그니처를 안 고르면 400', c == 400, c)
post('/api/dicegame/setup', {'cols': 6, 'rows': 4})   # 16칸으로 줄여도
t = dg()['tiles']
chk('크기를 바꿔도 같은 번호 칸 내용은 남는다',
    (t[3] or {}).get('label') == '팔굽혀펴기' and (t[6] or {}).get('type') == 'sig',
    (t[3], (t[6] or {}).get('type')))

print()
print('=' * 74)
print('④ 굴리기 — 서버가 유일한 진실')
print('=' * 74)
post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'dice': 2})
c, r = post('/api/dicegame/roll')
g = dg()
act = g.get('action') or {}
chk('굴려진다', c == 200 and len(r.get('dice') or []) == 2, r.get('dice'))
chk('눈은 1~6', all(1 <= d <= 6 for d in (r.get('dice') or [])), r.get('dice'))
chk('말 위치 = 눈의 합', g.get('pos') == sum(r['dice']) % 20, (g.get('pos'), r['dice']))
chk('경로 길이 = 눈의 합', len(act.get('path') or []) == sum(r['dice']))
chk('연출 신호에 눈·경로·도착이 실린다',
    act.get('type') == 'ROLL' and act.get('to') == g.get('pos') and act.get('ts'))
c2, r2 = post('/api/dicegame/roll')
chk('연출이 끝나기 전의 연타는 거절(429)', c2 == 429, c2)

print()
print('=' * 74)
print('⑤ 한 바퀴')
print('=' * 74)
post('/api/dicegame/move', {'pos': 19})
laps0 = dg().get('laps') or 0
c, r = post('/api/dicegame/roll')
g = dg()
chk('19번에서 굴리면 반드시 한 바퀴', c == 200 and (g.get('laps') or 0) == laps0 + 1,
    (laps0, g.get('laps')))
chk('신호에도 한 바퀴 표시', (g.get('action') or {}).get('lap') is True)
chk('감아 돈 위치가 맞다', g.get('pos') == (19 + sum(r['dice'])) % 20, (g.get('pos'), r['dice']))

print()
print('=' * 74)
print('⑥ 점수 칸 — 기여도만 오른다 (점수는 그날 일당이라 안 건드린다)')
print('=' * 74)
reset_all()
post('/api/dicegame/setup', {'cols': 4, 'rows': 3, 'dice': 1})   # 10칸 — 어디 떨어져도 점수 칸
for i in range(1, 10):
    post('/api/dicegame/tile', {'id': i, 'type': 'score', 'points': 2})
post('/api/dicegame/move', {'pos': 0})
c, r = post('/api/dicegame/roll', {'player': '제이양'})
d = get()
sc = {b['name']: (b.get('score'), b.get('contribution')) for b in d['bjs']}
# 사장님: "점수 칸은 점수라고만 써있지 기여도 5점만 올라가는거야"
chk('제이양 점수 그대로 0 · 기여도 +2', sc.get('제이양') == (0, 2), sc)
chk('로그에 기여도라고 남는다', any(l.get('name') == '제이양' and l.get('val') == 2 and l.get('kind') == 'contrib' for l in (d.get('logs') or [])),
    (d.get('logs') or [])[:1])
chk('응답에도 반영 결과', (r.get('scored') or {}).get('name') == '제이양', r.get('scored'))
post('/api/dicegame/move', {'pos': 0})
c, r = post('/api/dicegame/roll')                      # 차례 없이
d = get()
sc2 = {b['name']: (b.get('score'), b.get('contribution')) for b in d['bjs']}
# 기여도라서 시그·한 바퀴처럼 방금 굴린 사람을 기억해 준다 — 점수는 여전히 0
chk('차례를 안 골라도 기억한 사람 기여도로 간다 (점수는 0 그대로)', sc2.get('제이양') == (0, 4) and sc2.get('밍밍') == (0, 0), sc2)
c, r = post('/api/dicegame/move', {'pos': 0}) and post('/api/dicegame/roll', {'player': '없는사람'})
chk('없는 사람이면 기여도 안 넣고 알린다', '못 찾아' in ((r or {}).get('note') or ''), (r or {}).get('note'))

print()
print('=' * 74)
print('⑦ 시그니처 칸 — 기존 재생 경로, 집계는 안 부풀린다')
print('=' * 74)
reset_all()
post('/api/dicegame/setup', {'cols': 4, 'rows': 3, 'dice': 1})
for i in range(1, 10):
    post('/api/dicegame/tile', {'id': i, 'type': 'sig', 'sig_id': 10003})
q0 = len(get().get('reaction_queue') or [])
t0 = json.dumps(get().get('sig_tally') or {})
post('/api/dicegame/move', {'pos': 0})
post('/api/dicegame/roll')
d = get()
chk('재생 대기줄에 올라간다', len(d.get('reaction_queue') or []) == q0 + 1,
    len(d.get('reaction_queue') or []))
chk('시그니처 순위 집계는 안 는다(재생 전용)', json.dumps(d.get('sig_tally') or {}) == t0)

print()
print('=' * 74)
print('⑧ 황금열쇠 — 뽑기도 서버가')
print('=' * 74)
reset_all()
post('/api/dicegame/setup', {'cols': 4, 'rows': 3, 'dice': 1})
for i in range(1, 10):
    post('/api/dicegame/tile', {'id': i, 'type': 'key'})
post('/api/dicegame/keys', {'keys': ['가위', '바위', '보']})
post('/api/dicegame/move', {'pos': 0})
c, r = post('/api/dicegame/roll')
chk('뽑힌 카드가 응답과 신호에 실린다', r.get('key') in ('가위', '바위', '보'), r.get('key'))
chk('신호의 카드 = 응답의 카드 (화면끼리 안 갈린다)',
    (dg().get('action') or {}).get('key') == r.get('key'))
c, _ = post('/api/dicegame/keys', {'keys': '목록아님'})
chk('덱이 목록이 아니면 400', c == 400, c)

print()
print('=' * 74)
print('⑨ 밖에서 못 덮는다')
print('=' * 74)
c, _ = post('/api/settings/patch', {'dicegame': {}})
chk('설정 패치로 못 덮는다', c == 400, c)
before = dg()
whole = get()
whole['dicegame'] = {'enabled': False, 'tiles': [], 'pos': 99}
for k in ('bjs', 'extra_bjs', 'bottom_fixed', 'logs', 'match_logs'):
    whole.pop(k, None)
post('/api/data', whole)
time.sleep(0.4)
after = dg()
chk('상태 전체 POST 로도 못 덮는다(SERVER_OWNED)',
    after.get('pos') == before.get('pos') and len(after.get('tiles') or []) == 10,
    (after.get('pos'), len(after.get('tiles') or [])))

print()
print('=' * 74)
print('⑩ 정리')
print('=' * 74)
c, _ = post('/api/dicegame/move', {'pos': 999})
chk('없는 칸으로는 못 옮긴다', c == 400, c)
post('/api/dicegame/reset')
g = dg()
chk('초기화 — 말은 출발로, 화면에서 내려감', g.get('pos') == 0 and g.get('enabled') is False)
chk('칸 구성과 덱은 남는다', len(g.get('tiles') or []) == 10 and len(g.get('keys') or []) == 3)

print()
print('=' * 74)
print('⑪ 주사위는 한 개, 한 번, 최대 6')
print('=' * 74)
"""사장님 말: "주사위를 1개로 1번만 돌려서 최대 6만 나오게 한다는거였어"

⚠️ 서버는 원래 맞았다. 조종실이 되돌리고 있었다 —
   판 만들기 칸이 <option value="2" selected> 였고, 22칸 기본판이 dice: 2 를 박아
   보냈다. 무엇보다 그 칸들이 서버 상태를 안 읽어와서, 실제 판이 무엇이든 화면에는
   늘 '2회' 로 보였다. 그래서 다른 것 하나 고치려고 [판 만들기] 를 누르면 그 순간
   주사위가 조용히 두 개가 됐다. 화면이 거짓말을 하면 사장님은 바뀐 줄도 모른다.
   그래서 여기서는 '서버가 한 개인가' 만 보지 않고 '조종실이 사실을 보여주는가' 도 본다.
"""
import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_FALLBACK = r'C:\Users\Administrator\Desktop\새로다시시작'


def _proj():
    d = _HERE
    for _ in range(4):
        d = _os.path.dirname(d)
        if _os.path.exists(_os.path.join(d, 'server.py')):
            return d
    return _FALLBACK


post('/api/dicegame/setup', {'cols': 8, 'rows': 5})       # 개수를 일부러 안 보낸다
chk('개수를 안 보내면 한 개로 깔린다', dg().get('dice') == 1, dg().get('dice'))

# 실제로 굴려 본다. ⚠️ 굴림 사이에는 연출을 지키는 쿨다운(429)이 있어 기다려야 한다.
_vals, _counts, _tries = [], set(), 0
while len(_vals) < 12 and _tries < 120:
    _tries += 1
    _c, _d = post('/api/dicegame/roll', {})
    if _c == 429:
        time.sleep(0.6)
        continue
    _counts.add(len(_d.get('dice') or []))
    _vals += (_d.get('dice') or [])
    time.sleep(0.4)
chk('굴릴 때마다 주사위는 딱 한 개', _counts == {1}, sorted(_counts))
chk('눈은 1~6 을 벗어나지 않는다',
    bool(_vals) and min(_vals) >= 1 and max(_vals) <= 6,
    '최소 %s 최대 %s' % (min(_vals) if _vals else '-', max(_vals) if _vals else '-'))
chk('한 번에 7 이상은 안 나온다', all(v <= 6 for v in _vals))

# 기능 자체는 남긴다 — 사장님이 나중에 두 개로 바꾸고 싶을 수 있다
post('/api/dicegame/setup', {'cols': 8, 'rows': 5, 'dice': 2})
chk('두 개로도 깔 수 있다(기능은 남긴다)', dg().get('dice') == 2, dg().get('dice'))
post('/api/dicegame/setup', {'cols': 8, 'rows': 5, 'dice': 9})
chk('아홉 개를 보내도 두 개로 막힌다', dg().get('dice') == 2, dg().get('dice'))
post('/api/dicegame/setup', {'cols': 8, 'rows': 5, 'dice': 1})
chk('다시 한 개로 돌아온다', dg().get('dice') == 1, dg().get('dice'))

_ctl = io.open(_os.path.join(_proj(), 'controller.html'),
               encoding='utf-8', errors='replace').read()
chk('조종실 고르는 칸의 기본이 한 개', 'value="1" selected>1개' in _ctl)
chk('22칸 기본판도 한 개로 깐다', 'cols: 8, rows: 5, dice: 1' in _ctl)
chk('⚠️ 판 만들기 칸이 서버 상태를 따라간다 (진짜 원인)', "['dgc-dice', g.dice]" in _ctl)
chk('지금 주사위가 몇 개인지 화면에 뜬다', "' · 주사위 ' + (g.dice || 1) + '개'" in _ctl)

print()
print('=' * 74)
print('⑫ 꽝은 아무것도 안 준다 · 주사위는 점수를 안 건드린다')
print('=' * 74)
"""사장님 말
   "꽝에 가면 기여도 2점도 안 올라가게 해줘"
   "주사위게임은 기여도만 올릴 뿐 점수엔 영향 없는거지?"

⚠️ 꽝은 label 이 '꽝!' 인 점수 칸이고 points 가 2 였다. 그래서 밟으면 기여도 +2 가
   붙었다. 0 으로 두면 서버가 아예 안 준다 — if … and tile.get('points') 에서 걸린다.
"""


def _roll_until(player='제이양'):
    """굴림에는 연출을 지키는 쿨다운(429)이 있다. 될 때까지 기다린다."""
    for _ in range(60):
        c, r = post('/api/dicegame/roll', {'player': player})
        if c == 200:
            return r
        time.sleep(0.5)
    return {}


def _fill(tile):
    post('/api/dicegame/setup', {'cols': 8, 'rows': 5, 'dice': 1, 'roll_price': 20000})
    n = len(dg().get('tiles') or [])
    for i in range(1, n):
        t = dict(tile); t['id'] = i
        post('/api/dicegame/tile', t)
    post('/api/dicegame/move', {'pos': 0})


def _who(nm='제이양'):
    for b in get().get('bjs') or []:
        if b.get('name') == nm:
            return int(b.get('score') or 0), int(b.get('contribution') or 0)
    return 0, 0


reset_all()
_fill({'type': 'score', 'label': '꽝!', 'points': 0})
s0, c0 = _who()
r = _roll_until()
s1, c1 = _who()
chk('꽝(0점)은 기여도도 안 올린다', (s1, c1) == (s0, c0), '점수 %d→%d 기여도 %d→%d' % (s0, s1, c0, c1))
chk('꽝은 지급 알림도 안 남긴다', not r.get('scored'), r.get('scored'))

reset_all()
_fill({'type': 'score', 'label': '', 'points': 5})
s0, c0 = _who()
_roll_until()
s1, c1 = _who()
chk('점수 칸 5점 → 기여도만 +5', s1 == s0 and c1 == c0 + 5,
    '점수 %d→%d 기여도 %d→%d' % (s0, s1, c0, c1))

# 한 바퀴도 점수를 안 건드린다
reset_all()
_fill({'type': 'blank', 'label': ''})
post('/api/dicegame/move', {'pos': 20})
s0, c0 = _who()
r = _roll_until()
s1, c1 = _who()
chk('한 바퀴도 점수는 그대로', s1 == s0, '점수 %d→%d' % (s0, s1))

print()
print('=' * 74)
print('⑬ 시그니처는 말이 다 간 뒤에 나온다')
print('=' * 74)
"""사장님 말: "먼저 리액션모드로 가고나서 주사위가 가서 주사위 가는게 안보여.
   로직 자체를 주사위 이동후 나온 시그가 나오게 해줘"

⚠️ 화면을 덮는 것은 재생이 아니라 리액션 모드다 —
   body.reaction-mode 가 #dicegame-container 를 숨긴다. 그래서 '재생 시작' 만
   미뤄서는 안 되고, 큐 항목에 '이 시각 이후' (play_after) 를 실어 화면 전환까지
   같이 미뤄야 한다."""
reset_all()
post('/api/dicegame/setup', {'cols': 8, 'rows': 5, 'dice': 1, 'roll_price': 0})
_n = len(dg().get('tiles') or [])
for i in range(1, _n):
    post('/api/dicegame/tile', {'id': i, 'type': 'sig', 'sig_id': 10040})
post('/api/dicegame/move', {'pos': 0})
_before = int(time.time() * 1000)
r = _roll_until()
_q = get().get('reaction_queue') or []
chk('시그니처가 곧바로 큐에 들어간다 (서버가 재시작해도 안 잃게)', len(_q) == 1, len(_q))
_pa = (_q[0].get('play_after') if _q else 0) or 0
chk('play_after 가 실려 있다', _pa > _before, _pa)
_act = (dg().get('action') or {})
_exp = 370 + 1300 * len(_act.get('dice') or []) + 300 * len(_act.get('path') or []) + 500
chk('미루는 시간이 화면 연출과 같은 식이다 (370 + 눈×1300 + 칸×300 + 500)',
    abs((_pa - _before) - _exp) <= 400, '기대 %d · 실제 %d' % (_exp, _pa - _before))

# 보통 후원 시그니처는 안 미룬다
reset_all()
donate_sig = {'tx_id': 'ps' + str(int(time.time())), 'name': '별', 'amount': 100009,
              'message': '[시그니처 신청: 테스트]', 'time': '20:00'}
urllib.request.urlopen(urllib.request.Request(
    B + '/api/donation', json.dumps(donate_sig).encode(),
    {'Content-Type': 'application/json'}), timeout=20)
time.sleep(0.6)
_q2 = [x.get('play_after') or 0 for x in (get().get('reaction_queue') or [])]
chk('보통 후원 시그니처는 안 미룬다 (전부 0)', all(v == 0 for v in _q2), _q2)

_ov = io.open(_os.path.join(_proj(), 'overlay.html'), encoding='utf-8', errors='replace').read()
chk('화면이 리액션 모드 전환도 같이 미룬다',
    "if (d.reaction_mode && _rmHold === 0) document.body.classList.add('reaction-mode');" in _ov)
chk('참는 시간을 한 곳에서 답한다', 'function reactionHoldMs()' in _ov)
chk('⚠️ 서버 시각으로만 잰다 (브라우저가 들고 있는 묵는 값을 안 본다)',
    'const left = head.play_after - (Date.now() + off);' in _ov
    and 'window.dgBusyUntil - Date.now()' not in _ov)

print()
print('=' * 74)
print('⑭ 기여도가 어떻게 올랐는지 로그에 남는가')
print('=' * 74)
"""사장님 말: "기여도를 올리면 어떻게 올린건지 로그창에 로그도 만들어줘"

⚠️ 서버는 원래 kind:'contrib' 와 why 를 실어 보냈는데 조종실 로그창이 그걸 버리고
   전부 '+5점' 으로만 그렸다. 그래서 점수가 오른 것인지 기여도가 오른 것인지조차
   알 수 없었다. 손으로 고친 기여도는 아예 기록이 없었다(log:false)."""
reset_all()
post('/api/score/add', {'name': '제이양', 'delta': 30000, 'reason': '후원 배정'})
post('/api/score/add', {'name': '제이양', 'delta': 0, 'contribution': 7, 'reason': '손으로 고침'})
_fill({'type': 'score', 'label': '', 'points': 5})
_roll_until()
_lg = get().get('logs') or []
_c = [l for l in _lg if l.get('kind') == 'contrib']
_s = [l for l in _lg if l.get('kind') != 'contrib']
chk('기여도 줄이 따로 남는다', len(_c) >= 2, len(_c))
chk('점수 줄은 그대로 남는다', any(l.get('val') == 30000 for l in _s), [l.get('val') for l in _s][:3])
chk('손으로 고친 것도 남는다 (예전에는 아예 없었다)',
    any(l.get('val') == 7 and '손으로' in str(l.get('why')) for l in _c),
    [(l.get('val'), l.get('why')) for l in _c][:3])
chk('주사위 점수 칸은 왜인지도 남는다',
    any('점수 칸' in str(l.get('why')) for l in _c), [l.get('why') for l in _c][:3])
chk('기여도 줄에 점수 값이 안 섞인다 (0점 줄이 안 생긴다)',
    not any(l.get('kind') != 'contrib' and l.get('val') == 0 for l in _lg))

_ctl3 = io.open(_os.path.join(_proj(), 'controller.html'), encoding='utf-8', errors='replace').read()
chk('조종실이 기여도 딱지를 그린다', ">기여도</span>" in _ctl3 and "log.kind === 'contrib'" in _ctl3)
chk('조종실이 이유도 보여준다', 'escapeHTML(String(log.why))' in _ctl3)
chk('손으로 고칠 때 기록을 남긴다 (log:false 를 뺐다)',
    "contribution: diff, reason: '손으로 고침'" in _ctl3)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
