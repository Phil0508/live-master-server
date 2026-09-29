# -*- coding: utf-8 -*-
"""🎮 게임 · 점수 구멍 넷 (2026-09-30 점검에서 재현한 것) — 서버가 정말 막는가.

  1. 주사위 — 엑셀판에서 이름을 고치면(개명) 주사위 기록이 새 이름으로 넘어간다.
     예전엔 옛 이름이 보관함에 맡겨지고 새 이름은 0점에서 시작했다. [엑셀판으로 옮기기] ·
     방송 종료 확인은 판만 봐서, 방송을 끝내면 보관함째 비워져 **점수가 소리 없이 사라졌다.**
     진짜로 뺀 사람(대신 들어온 사람 없음)은 예전처럼 맡겨 두고, 옮기기 때 '못 옮김' 으로 알린다.
  2. 슬롯 — 0.3초 사이로 두 번 돌리면 당첨 시그 둘 · 기여도 카드 두 장이 나갔다 → 두 번째는 409.
  3. 번외 게임 — 하는 중에 [개시] 를 또 누르면 번외 점수가 0으로 돌아갔다 → 409.
  4. 룰렛 — 결과가 난 뒤 로그인한 두 번째 방송판이 늦게 보고하면 당첨자를 덮었다 → 한 판에 한 번.

돌리는 법: 연습 서버(tests/boot_sig.py)를 띄우고  LM_PT_PORT=5314 python tests/fix_games_test.py
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
NOAUTH = {'Content-Type': 'application/json'}      # ← 오버레이(OBS)와 같은 조건
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:150]) if detail else ''))


def post(path, obj=None, hdr=H):
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), hdr)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=H), timeout=25) as r:
        return json.loads(r.read().decode())


def dg():
    return get().get('dicegame') or {}


def pieces():
    return {p['name']: p for p in dg().get('pieces') or []}


def order():
    return [p['name'] for p in dg().get('pieces') or []]


def bd():
    return {x['name']: x['pts'] for x in dg().get('board') or []}


def parked():
    return dg().get('parked') or {}


def roster(names):
    post('/api/data', {'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in names]})


def reset(names=('가', '나', '다', '라'), **extra):
    body = {'broadcast_active': True, 'extra_game_active': False, 'extra_bjs': [], 'reaction_queue': [],
            'reaction_mode': False, 'reaction_paused': False, 'pending_donations': [], 'logs': [],
            'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in names]}
    body.update(extra)
    post('/api/restore', body)


def board():
    post('/api/dicegame/setup', {'cols': 8, 'rows': 5, 'dice': 1, 'roll_price': 0})
    for i in range(1, 22):
        post('/api/dicegame/tile', {'id': i, 'type': 'score', 'points': 10})


def na_at_4():
    """나: 4번 칸 · 10점 · 실드 (dice_fix_test 5번과 같은 시작)"""
    reset()
    board()
    post('/api/dicegame/keys', {'keys': ['실드권']})
    post('/api/dicegame/move', {'piece': '나', 'pos': 0})
    post('/api/dicegame/roll', {'piece': '나', 'value': 4})


print('=' * 74)
print('1-1. 이름을 고치면(개명) 주사위 기록이 새 이름으로 넘어간다')
print('=' * 74)
na_at_4()
chk('처음: 나 4번 칸 · 10점', pieces()['나']['pos'] == 4 and bd().get('나') == 10, (pieces()['나'], bd()))
post('/api/dicegame/move', {'piece': '가', 'pos': 0})   # 차례를 '다'(2번 자리)에 둔다
_turn0 = dg().get('turn')
roster(('가', '나나', '다', '라'))
p = pieces().get('나나') or {}
chk("⭐ '나나' 가 4번 칸 · 10점을 물려받는다 (예전: 0번 · 0점, 나는 보관함)",
    p.get('pos') == 4 and bd().get('나나') == 10, (p, bd()))
chk('⭐ 옛 이름은 보관함에 안 남는다 (두 벌로 늘지 않는다)', '나' not in parked() and '나' not in bd(), (parked(), bd()))
chk('말 자리(차례 순서)도 그대로 — 나나는 2번째', order() == ['가', '나나', '다', '라'], order())
chk('차례가 안 바뀐다', dg().get('turn') == _turn0, (_turn0, dg().get('turn')))
c, r = post('/api/dicegame/board', {'do': 'apply'})
chk("⭐ [엑셀판으로 옮기기] 가 나나 10점을 옮긴다", any(x['name'] == '나나' and x['points'] == 10 for x in r.get('moved') or []),
    (r.get('moved'), r.get('skipped')))
chk('옮긴 뒤 나나 기여도 10', next((b for b in get()['bjs'] if b['name'] == '나나'), {}).get('contribution') == 10, get()['bjs'])

print()
print('=' * 74)
print('1-2. 고쳤다 되돌리면(나 → 나나 → 나) 다시 되돌아온다')
print('=' * 74)
na_at_4()
roster(('가', '나나', '다', '라'))
roster(('가', '나', '다', '라'))
chk("⭐ '나' 로 되돌리면 4번 칸 · 10점", pieces()['나']['pos'] == 4 and bd().get('나') == 10, (pieces()['나'], bd()))
chk('나나는 흔적이 없다', '나나' not in pieces() and '나나' not in parked() and '나나' not in bd(), (parked(), bd()))

print()
print('=' * 74)
print('1-3. 진짜로 뺀 사람(대신 들어온 사람 없음)은 예전처럼 맡겨 두고, 옮기기 때 알린다')
print('=' * 74)
na_at_4()
roster(('가', '다', '라'))
chk('나는 보관함에 4번 칸 · 10점', parked().get('나', {}).get('pos') == 4 and parked().get('나', {}).get('pts') == 10, parked())
post('/api/dicegame/board', {'do': 'add', 'name': '가', 'pts': 3})
c, r = post('/api/dicegame/board', {'do': 'apply'})
sk = {x['name']: x for x in r.get('skipped') or []}
chk("⭐ 보관함 점수를 '못 옮김' 으로 알린다 (예전: 아무 말 없이 지나가 방송 종료 때 사라졌다)",
    sk.get('나', {}).get('points') == 10 and sk.get('나', {}).get('parked') is True, r.get('skipped'))
chk('가는 옮겨진다', any(x['name'] == '가' and x['points'] == 3 for x in r.get('moved') or []), r.get('moved'))
chk('보관함 점수는 그대로 남는다', parked().get('나', {}).get('pts') == 10, parked())
roster(('가', '나', '다', '라'))
chk('나가 돌아오면 4번 칸 · 10점', pieces()['나']['pos'] == 4 and bd().get('나') == 10, (pieces()['나'], bd()))

print()
print('=' * 74)
print('1-4. 확신할 수 없는 변경은 개명으로 안 본다 (맡겨 둔다 — 남의 점수를 주지 않는다)')
print('=' * 74)
na_at_4()
roster(('가', '다', '나나', '라'))        # 자리가 다르다
chk('자리가 다르면: 나나는 0점 · 나는 보관함', bd().get('나나') == 0 and parked().get('나', {}).get('pts') == 10,
    (bd(), parked()))
na_at_4()
roster(('가', '나나', '다', '라', '마'))  # 고치고 한 명 더
chk('고치면서 사람을 더하면: 나나는 0점 · 나는 보관함', bd().get('나나') == 0 and parked().get('나', {}).get('pts') == 10,
    (bd(), parked()))
na_at_4()
roster(('가', '다', '라'))                # 나 빠짐 → 보관함
roster(('가', '다', '라', '마'))
roster(('가', '다', '라', '나'))          # 맡겨 둔 나가 돌아온다(마 대신) — 되살리기가 먼저
chk('맡겨 둔 이름이 돌아오면 되살린다', pieces().get('나', {}).get('pos') == 4 and bd().get('나') == 10, (pieces().get('나'), bd()))
na_at_4()
post('/api/data', {'extra_game_active': True, 'extra_bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ('가', 'X', '다', '라')]})
chk('번외 게임으로 명단이 바뀐 것은 개명이 아니다 (X 는 0점)', bd().get('X') == 0 and parked().get('나', {}).get('pts') == 10,
    (bd(), parked()))
post('/api/data', {'extra_game_active': False, 'extra_bjs': []})
chk('번외 게임이 끝나면 나 4번 칸 · 10점', pieces().get('나', {}).get('pos') == 4 and bd().get('나') == 10, (pieces().get('나'), bd()))

print()
print('=' * 74)
print('2. 슬롯 — 도는 중에 또 돌리면 409 (예전: 당첨 시그 둘 · 기여도 카드 두 장)')
print('=' * 74)
reset()
post('/api/settings/patch', {'slot_price': 4000, 'slot_pool': [10040]})   # 40번 = 14,000원 → 기여도 1점
time.sleep(6.5)            # 앞에서 돌린 슬롯이 남아 있으면 먼저 흘려보낸다
post('/api/data', {'pending_donations': [], 'reaction_queue': []})
res = []


def _spin():
    res.append(post('/api/slot/spin', {}))


c1 = post('/api/slot/spin', {})
time.sleep(0.3)
c2 = post('/api/slot/spin', {})
# 동시에 여럿 — 시그니처 조회 사이에 끼어드는 경우
ts = [threading.Thread(target=_spin) for _ in range(3)]
[t.start() for t in ts]
[t.join() for t in ts]
chk('첫 번째는 돈다', c1[0] == 200, c1)
chk('⭐ 0.3초 뒤 두 번째는 409 + 한국어 안내', c2[0] == 409 and '돌고 있' in (c2[1].get('message') or ''), c2)
chk('⭐ 동시에 3번 더 눌러도 전부 409', all(c == 409 for c, _ in res), [c for c, _ in res])
time.sleep(5.0)
d = get()
cards = [x for x in (d.get('pending_donations') or []) if x.get('kind') == 'contrib' and '슬롯' in str(x.get('name'))]
sigs = [x for x in (d.get('reaction_queue') or []) if '슬롯' in str(x.get('donator') or '') + str(x.get('message') or '')]
chk('⭐ 기여도 카드는 한 장', len(cards) == 1, len(cards))
chk('⭐ 당첨 시그는 하나', len(sigs) == 1, [(x.get('donator'), x.get('message')) for x in d.get('reaction_queue') or []])
c3 = post('/api/slot/spin', {})
chk('당첨 처리가 끝나면 다시 돌릴 수 있다', c3[0] == 200, c3)
time.sleep(5.0)
post('/api/settings/patch', {'slot_price': 20000, 'slot_pool': []})
post('/api/data', {'pending_donations': [], 'reaction_queue': [], 'reaction_mode': False})

print()
print('=' * 74)
print('3. 번외 게임 — 하는 중에 [개시] 를 또 누르면 409, 번외 점수는 그대로')
print('=' * 74)
reset()
c, _ = post('/api/extra_game/start')
chk('개시', c == 200 and get().get('extra_game_active') is True, c)
post('/api/score/add', {'name': '가', 'delta': 5})
_s0 = {b['name']: b.get('score') for b in get().get('extra_bjs') or []}
chk('번외판에 가 5점', _s0.get('가') == 5, _s0)
c, r = post('/api/extra_game/start')
chk("⭐ 또 개시하면 409 '이미 번외 게임 중이에요'", c == 409 and '이미 번외 게임 중' in (r.get('message') or ''), (c, r))
_s1 = {b['name']: b.get('score') for b in get().get('extra_bjs') or []}
chk('⭐ 번외 점수가 안 지워진다 (예전: 0점)', _s1.get('가') == 5, _s1)
post('/api/extra_game/cancel')
c, _ = post('/api/extra_game/start')
chk('취소한 뒤에는 다시 개시할 수 있다', c == 200, c)
post('/api/extra_game/cancel')

print()
print('=' * 74)
print('4. 룰렛 — 한 판에 결과는 한 번, 먼저 온 것만')
print('=' * 74)


def spin():
    d = get()
    d['roulette'] = dict(d.get('roulette') or {}, command='spin',
                         command_time=int(time.time() * 1000), is_spinning=True, winner_name=None)
    post('/api/data', d)


reset()
spin()
r0 = int((get().get('roulette') or {}).get('round_id') or 0)
c, _ = post('/api/roulette/winner', {'name': '제이양'}, NOAUTH)
chk('방송판(무세션) 보고가 통한다', c == 200, c)
chk('판 번호가 하나 오른다', int(get()['roulette'].get('round_id') or 0) == r0 + 1, get()['roulette'].get('round_id'))
c, r = post('/api/roulette/winner', {'name': '늦은이름'}, H)
chk('⭐ 로그인한 두 번째 방송판이 늦게 보고하면 409 (예전: 당첨자를 덮었다)', c == 409, (c, r.get('message')))
chk('⭐ 당첨자가 그대로', get()['roulette'].get('winner_name') == '제이양', get()['roulette'].get('winner_name'))
c, r = post('/api/roulette/winner', {'name': '남의이름'}, NOAUTH)
chk('무세션 늦은 보고도 409', c == 409, c)
_logs = [l for l in (get().get('logs') or []) if '룰렛 결과' in str(l.get('name'))]
chk('룰렛 결과 로그는 한 줄', len(_logs) == 1, len(_logs))
spin()
c, r = post('/api/roulette/winner', {'name': '다음판', 'round_id': r0 + 1}, NOAUTH)
chk('다음 판에 지난 판 번호로 온 보고는 409', c == 409 and '지난 판' in (r.get('message') or ''), (c, r.get('message')))
c, _ = post('/api/roulette/winner', {'name': '다음판', 'round_id': r0 + 2}, NOAUTH)
chk('다음 판은 새로 받는다 (맞는 판 번호)', c == 200 and get()['roulette'].get('winner_name') == '다음판',
    (c, get()['roulette'].get('winner_name')))
spin()
c, _ = post('/api/roulette/winner', {'name': '조종실'}, H)
chk('돌고 있을 때 로그인한 보고(시험·조종실)는 그대로 통한다', c == 200, c)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
