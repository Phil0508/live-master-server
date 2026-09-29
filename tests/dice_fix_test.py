# -*- coding: utf-8 -*-
"""🎲 주사위게임 고친 것 (2026-09-30 대표님 "고쳐") — 서버가 정말 그렇게 하는가.

시험 서버에서 직접 굴려 찾은 것들이다. 번호는 대표님께 보여 드린 '주사위게임 고칠 목록' 번호와 같다.
방송판 순서(1 · 2 · 7번)는 tests/dice_order_test.py 가 브라우저로 잰다.
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
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:150]) if detail else ''))


def post(path, obj=None):
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), H)
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


def bd():
    return {x['name']: x['pts'] for x in dg().get('board') or []}


def reset(names=('가', '나', '다', '라'), **extra):
    body = {'broadcast_active': True, 'extra_game_active': False, 'extra_bjs': [], 'reaction_queue': [],
            'reaction_mode': False, 'reaction_paused': False, 'pending_donations': [], 'logs': [],
            'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in names]}
    body.update(extra)
    post('/api/restore', body)


def board(tile_type='blank', **tile):
    post('/api/dicegame/setup', {'cols': 8, 'rows': 5, 'dice': 1, 'roll_price': 0})
    for i in range(1, 22):
        post('/api/dicegame/tile', dict({'id': i, 'type': tile_type}, **tile))


def _proj():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.exists(os.path.join(d, 'controller.html')):
            return d
        d = os.path.dirname(d)
    return os.environ.get('LM_ROOT') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


CTL = io.open(os.path.join(_proj(), 'controller.html'), encoding='utf-8', errors='replace').read()

print('=' * 74)
print('3. 연타 막기가 연출 끝까지 센다 — 블랙홀 역주행 중에 다음 굴림이 끼어들지 않는다')
print('=' * 74)
reset()
board()
post('/api/dicegame/tile', {'id': 21, 'type': 'goto', 'label': '블랙홀', 'points': 0})
post('/api/dicegame/move', {'piece': '다', 'pos': 18})
c, r = post('/api/dicegame/roll', {'piece': '다', 'value': 3})
chk('18 + 3 → 블랙홀', c == 200 and (r.get('tile') or {}).get('type') == 'goto', (c, r.get('tile')))
time.sleep(3.5)          # 예전 연타 막기(3칸×0.3 + 2.2 = 3.1초)는 여기서 이미 풀려 있었다
c, r = post('/api/dicegame/roll', {'value': 2})
chk('⭐ 3.5초(역주행 중)에 누른 굴림은 거절 (예전: 받아서 순간이동)', c == 429, (c, r.get('message')))
chk('거절에 남은 시간이 실린다', (r.get('wait_ms') or 0) > 2000 and '초 뒤' in (r.get('message') or ''), r)
time.sleep((r.get('wait_ms') or 0) / 1000.0 + 0.3)
c, r = post('/api/dicegame/roll', {'value': 2})
chk('연출이 끝나면 굴린다', c == 200, (c, r.get('message')))

print()
print('=' * 74)
print('4. 거절된 굴림은 아무것도 안 바꾼다 — "원하는 곳으로" 선택권이 안 사라진다')
print('=' * 74)
reset()
board()
post('/api/dicegame/tile', {'id': 3, 'type': 'key'})
post('/api/dicegame/tile', {'id': 10, 'type': 'score', 'points': 10})
post('/api/dicegame/keys', {'keys': ['원하는 곳으로']})
post('/api/dicegame/move', {'piece': '가', 'pos': 0})
c, r = post('/api/dicegame/roll', {'piece': '가', 'value': 3})
chk('열쇠: 원하는 곳으로', r.get('key') == '원하는 곳으로' and pieces()['가'].get('choose'), r.get('key'))
lp0 = dg().get('last_player')
c, r = post('/api/dicegame/roll', {'piece': '가', 'value': 1, 'player': '라'})
chk('연출 중 또 누르면 429', c == 429, c)
chk('⭐ 거절됐는데도 선택권이 남아 있다 (예전: 지워졌다)', pieces()['가'].get('choose') is True, pieces()['가'])
chk('거절된 굴림은 "마지막 사람" 도 안 바꾼다', dg().get('last_player') == lp0, (lp0, dg().get('last_player')))
c, r = post('/api/dicegame/move', {'piece': '가', 'pos': 10})
chk('원하는 칸(10번 · 10점)으로 옮기면 점수가 들어간다', (r.get('scored') or {}).get('points') == 10 and bd().get('가') == 10,
    (r.get('scored'), bd()))

print()
print('=' * 74)
print('5. 엑셀판에서 이름을 고쳤다 되돌려도 주사위 기록이 돌아온다')
print('=' * 74)
reset()
board('score', points=10)
post('/api/dicegame/move', {'piece': '나', 'pos': 0})
post('/api/dicegame/roll', {'piece': '나', 'value': 4})
post('/api/dicegame/keys', {'keys': ['실드권']})
p0 = pieces()['나']
chk('처음: 나 4번 칸 · 10점', p0['pos'] == 4 and bd().get('나') == 10, (p0, bd()))
post('/api/data', {'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ('가', '나나', '다', '라')]})
g = dg()
# ✏️ 2026-09-30: 같은 자리에서 이름만 바뀌면 개명으로 보고 기록을 물려준다(엑셀판과 같은 규칙).
#    예전엔 '나나' 가 0번 · 0점에서 시작하고 '나' 는 보관함에 맡겨졌다 — 방송을 끝내면 보관함째 비워져 점수가 사라졌다.
chk("⭐ '나나' 로 고치면 4번 칸 · 10점을 물려받는다 (개명)", pieces().get('나나', {}).get('pos') == 4 and bd().get('나나') == 10,
    (pieces().get('나나'), bd()))
chk('개명한 옛 이름은 보관함에 안 남는다', '나' not in (g.get('parked') or {}), g.get('parked'))
post('/api/data', {'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ('가', '나', '다', '라')]})
chk("⭐ '나' 로 되돌리면 4번 칸 · 10점 그대로 (예전: 0번 · 0점)", pieces()['나']['pos'] == 4 and bd().get('나') == 10,
    (pieces()['나'], bd()))
chk('되돌린 뒤 보관함에 나 · 나나가 없다', not ({'나', '나나'} & set(dg().get('parked') or {})), dg().get('parked'))
# 🅿️ 진짜로 뺀 사람(대신 들어온 사람 없음)은 예전처럼 맡겨 뒀다가 돌아오면 되살린다
post('/api/data', {'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ('가', '다', '라')]})
g = dg()
chk('⭐ 빠진 이름의 기록은 맡아 둔다', (g.get('parked') or {}).get('나', {}).get('pos') == 4
    and (g.get('parked') or {}).get('나', {}).get('pts') == 10, g.get('parked'))
post('/api/data', {'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ('가', '나', '다', '라')]})
chk("⭐ 다시 넣으면 4번 칸 · 10점 그대로", pieces()['나']['pos'] == 4 and bd().get('나') == 10,
    (pieces()['나'], bd()))
chk('되살린 이름은 보관함에서 빠진다', '나' not in (dg().get('parked') or {}), dg().get('parked'))
chk('출발 칸 · 0점인 이름은 맡아 두지 않는다 (보관함이 안 불어난다)',
    not any(n in (dg().get('parked') or {}) for n in ('가', '다', '라')), dg().get('parked'))
# 번외 게임 — 명단이 통째로 바뀌었다 돌아와도 (조종실이 하는 그대로 /api/data 로)
# ⚠️ /api/restore 는 상태를 통째로 갈아끼운다(주사위판까지) — 방송 중 조작을 흉내 내는 데 쓰면 안 된다
post('/api/data', {'extra_game_active': True, 'extra_bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ('X', 'Y')]})
chk('번외 게임 중에는 말이 번외 명단', sorted(pieces()) == ['X', 'Y'], sorted(pieces()))
chk('번외 게임 중에도 나의 기록은 맡아 둔다', (dg().get('parked') or {}).get('나', {}).get('pts') == 10, dg().get('parked'))
post('/api/data', {'extra_game_active': False, 'extra_bjs': []})
chk('⭐ 번외 게임이 끝나면 나 4번 칸 · 10점이 돌아온다', pieces().get('나', {}).get('pos') == 4 and bd().get('나') == 10,
    (pieces().get('나'), bd()))
chk('조종실: 이름 고치기 · 빼기가 주사위 기록을 먼저 묻는다',
    CTL.count("onchange=\"rkRename('${listKey}', ${i}, this)\"") == 2 and CTL.count("onclick=\"rkRemove('${listKey}', ${i})\"") == 2
    and 'function rkDiceGuard(listKey, name)' in CTL)
chk('조종실: 옛 바로-지우기 손잡이는 없다', "gd.${listKey}.splice(${i},1); pushAPI" not in CTL)

print()
print('=' * 74)
print('6. 방송이 끝나면(또는 새로 시작하면) 주사위 점수판 · 실드 · 선택권 · 보관함을 비운다')
print('=' * 74)
reset()
board('score', points=10)
post('/api/dicegame/tile', {'id': 2, 'type': 'key'})
post('/api/dicegame/keys', {'keys': ['실드권']})
post('/api/dicegame/move', {'piece': '가', 'pos': 0})
post('/api/dicegame/roll', {'piece': '가', 'value': 2})       # 가 실드
post('/api/dicegame/move', {'piece': '나', 'pos': 0})
post('/api/dicegame/roll', {'piece': '나', 'value': 5})       # 나 +10
post('/api/data', {'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ('가', '다', '라')]})   # 나 → 보관함
chk('끝내기 전: 가 실드 · 나 보관함 10점', pieces()['가'].get('shield') and (dg().get('parked') or {}).get('나', {}).get('pts') == 10,
    (pieces()['가'], dg().get('parked')))
c, r = post('/api/server/end_broadcast', {})
chk('방송 종료', c == 200, (c, r.get('message')))
g = dg()
chk('⭐ 전용 점수판이 0 (예전: 남아 있다가 다음 주 기여도에 섞였다)', all(not x.get('pts') for x in g.get('board') or []), g.get('board'))
chk('실드 · 선택권이 풀린다', not any(p.get('shield') or p.get('choose') for p in g.get('pieces') or []), g.get('pieces'))
chk('보관함이 빈다', not (g.get('parked') or {}), g.get('parked'))
c, r = post('/api/server/start_broadcast', {'names': ['가', '나', '다', '라']})
chk('새 방송도 0점에서 시작', c == 200 and all(v == 0 for v in bd().values()), bd())
chk('조종실: 끝낼 때 점수가 남아 있으면 옮길지 묻는다 (옮기고 끝내기 · 버리고 끝내기 · 취소)',
    'function premiumChoice(message, title, choices)' in CTL and "label: '엑셀판으로 옮기고 끝내기', value: 'apply'" in CTL
    and "label: '버리고 끝내기', value: 'drop'" in CTL)

print()
print('=' * 74)
print('10. 주사위 시그는 후원이 아니다 — 누가 밟았는지만 · 금액 0 · 팝업 없음')
print('=' * 74)
reset()
board('sig', sig_id=10040)
post('/api/dicegame/move', {'piece': '가', 'pos': 0})
t0 = int(time.time() * 1000)
c, r = post('/api/dicegame/roll', {'piece': '가', 'value': 2})
q = get().get('reaction_queue') or []
it = q[0] if q else {}
chk('시그가 줄에 들어간다', len(q) == 1, len(q))
chk("⭐ 이름은 밟은 사람('가') — 예전: '주사위게임' 님", it.get('donator') == '가', it.get('donator'))
chk('⭐ 금액 0 (예전: 시그 값 → 10만 원 이상이면 업 배너 · 클립 저장)', it.get('amount') == 0, it.get('amount'))
chk('후원 팝업 없음 · 주사위 표시 · 제목', it.get('skip_popup') is True and it.get('source') == 'dice'
    and it.get('banner') == '가 · 시그 칸 도착', (it.get('skip_popup'), it.get('source'), it.get('banner')))
exp = 380 + 2 * 300 + 120 + 1500
chk('재생 시각 = 말이 닿고 + 카드 1.5초 (%dms)' % exp, abs((it.get('play_after') or 0) - t0 - exp) <= 600,
    (it.get('play_after') or 0) - t0)
chk('시그 순위 집계에 안 센다', not (get().get('sig_tally') or {}), get().get('sig_tally'))
chk("조종실 대기열: '0' 대신 '🎲 주사위'", "it.source === 'dice' ? '🎲 주사위'" in CTL)

print()
print('=' * 74)
print('11-1. 다른 판이 무대에 있을 때 굴리면 — 맞는 안내 · 눈 단추도 막는다')
print('=' * 74)
reset()
board()
post('/api/show', {'stage': 'siggame'})
c, r = post('/api/dicegame/roll', {'value': 3})
chk("⭐ '지금 무대에 시그뒤집기' 라고 알린다 (예전: '먼저 판을 깔아주세요')",
    c == 400 and '시그뒤집기' in (r.get('message') or '') and '무대' in (r.get('message') or ''), (c, r.get('message')))
post('/api/show', {'stage': None})
c, r = post('/api/dicegame/roll', {'value': 3})
chk('무대가 비어 있으면 "방송에 안 떠 있어요"', c == 400 and '안 떠 있어요' in (r.get('message') or ''), (c, r.get('message')))
chk('조종실: 눈 1~6 단추도 굴리기와 같이 막는다', "panel.querySelectorAll('button.dgc-eye').forEach" in CTL and 'b.disabled = !rollOk;' in CTL)

print()
print('=' * 74)
print('11-3. 황금열쇠 "출발지로" — 블랙홀처럼 거꾸로 걸어간다')
print('=' * 74)
reset()
board()
post('/api/dicegame/tile', {'id': 5, 'type': 'key'})
post('/api/dicegame/keys', {'keys': ['출발지로 (뒤)']})
post('/api/dicegame/move', {'piece': '가', 'pos': 0})
c, r = post('/api/dicegame/roll', {'piece': '가', 'value': 5})
af = (dg().get('action') or {}).get('after') or {}
chk('출발로 간다', af.get('to') == 0 and pieces()['가']['pos'] == 0, (af.get('to'), pieces()['가']))
chk('⭐ 거꾸로 한 칸씩 (예전: 경로가 비어 순간이동)', af.get('path') == [4, 3, 2, 1, 0] and af.get('rev') is True,
    (af.get('path'), af.get('rev')))

print()
print('=' * 74)
print('11-4. [엑셀판으로 옮기기] — 못 찾은 사람은 점수를 남기고 알린다')
print('=' * 74)
reset(('가', '나'))
board()
post('/api/dicegame/board', {'do': 'add', 'name': '가', 'pts': 10})
post('/api/dicegame/board', {'do': 'add', 'name': '나', 'pts': 7})
# 엑셀판 명단을 비웠다 — 주사위 말 · 점수판은 그대로 남는다('명단이 비면 있던 말을 그대로 둔다')
post('/api/data', {'bjs': []})
c, r = post('/api/dicegame/board', {'do': 'apply'})
sk = {x['name']: x['points'] for x in r.get('skipped') or []}
chk('⭐ 엑셀판에 없는 사람은 못 옮겼다고 알린다', sk == {'가': 10, '나': 7}, r.get('skipped'))
chk('⭐ 못 옮긴 점수는 남는다 (예전: 옮기지도 않고 지웠다)', bd() == {'가': 10, '나': 7}, bd())
post('/api/data', {'bjs': [{'name': '나', 'score': 0, 'contribution': 100}]})   # 나만 돌아왔다
c, r = post('/api/dicegame/board', {'do': 'apply'})
chk('돌아온 나는 옮긴다', any(x['name'] == '나' and x['points'] == 7 for x in r.get('moved') or []), r.get('moved'))
chk('옮긴 나는 비워진다 · 기여도 107', bd().get('나') == 0 and get()['bjs'][0].get('contribution') == 107, (bd(), get()['bjs']))
chk('조종실: 못 옮긴 사람을 창으로 알린다', "'🎯 못 옮긴 사람'" in CTL)

print()
print('=' * 74)
print('12. 굴려도 굴리는 사람은 그대로 — 바꿀 때만 바뀐다')
print('=' * 74)
"""대표님(2026-09-30): "한 명 굴리면 다른 사람으로 굴리는 게 바뀌던데 내가 바꾸기 전까진 그대로 냅두게 해줘"
   예전엔 두 곳에서 바뀌었다 — 서버가 차례를 다음 말로 넘기고, 조종실 · 폰이 고른 사람을 지웠다."""
reset()
board()
post('/api/dicegame/move', {'piece': '나', 'pos': 0})
c, r = post('/api/dicegame/roll', {'piece': '나', 'value': 1})
g = dg()
chk('⭐ 서버: 나가 굴린 뒤에도 차례는 나 (예전: 다로 넘어갔다)', g['pieces'][g['turn']]['name'] == '나', g['pieces'][g['turn']]['name'])
time.sleep(3.0)      # 연타 막기(말 닿음 0.8초 + 카드 1.5초 + 0.3초)
c, r = post('/api/dicegame/roll', {'value': 1})               # 사람을 안 고르고 또 굴린다
chk('안 고르고 또 굴려도 나', c == 200 and r.get('piece') == '나', (c, r.get('piece'), r.get('message')))
_toast = CTL[CTL.index('function dgcRollToast(d)'):CTL.index('function dgcLogAdd(m)')]
chk('⭐ 조종실: 굴린 뒤 고른 사람을 안 지운다', "sel.value = ''" not in _toast, _toast[-300:])
_mv = CTL[CTL.index('async function dgcMove()'):CTL.index('function dgcRenderBoard(g)')]
chk('조종실: 말을 옮긴 뒤에도 고른 사람 그대로', "sel.value = ''" not in _mv)
MOB = io.open(os.path.join(_proj(), 'mobile.html'), encoding='utf-8', errors='replace').read()
_mr = MOB[MOB.index('async function dgMobRoll()'):MOB.index('async function dgMobShow()')]
chk('⭐ 폰: 굴린 뒤 고른 사람을 안 지운다', "sel.value = ''" not in _mr)
chk('안내 문구: 굴려도 안 바뀌어요', '굴려도 안 바뀌어요 — 바꿀 때만 이름을 누르세요' in CTL and '굴리고 나면 다음 사람으로 넘어가요' not in CTL)

print()
print('=' * 74)
print('2 · 8. 조종실 — 시그 재생 중 경고 · 옛 안내 문구')
print('=' * 74)
chk('시그 재생 중이면 경고 띠 · 흐린 단추 · 누르면 한 번 더 묻는다',
    'id="dgc-rx-warn"' in CTL and 'function dgcRxBusy()' in CTL and CTL.count('if (!(await dgcRxOk())) return;') == 2)
chk('멈춰 두기만 했으면 경고하지 않는다', '!g.reaction_paused' in CTL[CTL.index('function dgcRxBusy()'):CTL.index('function dgcRxBusy()') + 300])
chk("⭐ '말은 손으로 옮겨주세요' 안내가 없다 (그대로 하면 벌칙이 두 번)", '말은 손으로 옮겨주세요' not in CTL)
chk('새 안내: 자동으로 움직여요', '칸은 자동으로 움직여요 — 손대지 않아도 돼요' in CTL)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
