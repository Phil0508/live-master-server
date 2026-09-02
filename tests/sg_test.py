# -*- coding: utf-8 -*-
"""시그게임 처음부터 끝까지 돌려본다."""
import sys, json, urllib.request, urllib.error, time
sys.stdout.reconfigure(encoding='utf-8')

B = 'http://127.0.0.1:5199'
TOK = 'sandboxsecret123456'
ok = fail = 0


def req(path, data=None, auth=True):
    # /api/siggame/* 는 전부 POST 다. 본문이 없어도 POST 로 보내야 한다.
    if data is None and path.startswith('/api/siggame/'):
        data = {}
    body = json.dumps(data).encode() if data is not None else None
    h = {'Content-Type': 'application/json'}
    if auth:
        h['Authorization'] = 'Bearer ' + TOK
    r = urllib.request.Request(B + path, data=body,
                               method='POST' if body is not None else 'GET', headers=h)
    try:
        with urllib.request.urlopen(r, timeout=10) as f:
            return f.status, json.loads(f.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def chk(label, cond, extra=''):
    global ok, fail
    if cond:
        ok += 1
        print('  ✅ ' + label)
    else:
        fail += 1
        print('  ❌ ' + label + '  ' + str(extra))


def game():
    return req('/api/data')[1].get('siggame') or {}


print('1) 무인증 접근 차단')
for p, body in [('/api/siggame/deal', {}), ('/api/siggame/flip', {'id': 1}),
                ('/api/siggame/clear', {}), ('/api/siggame/set', {'enabled': True})]:
    st, _ = req(p, body, auth=False)
    chk(p + ' → 401', st == 401, st)

print('\n2) 시그니처 고르기')
sigs = req('/api/signatures')[1].get('signatures') or []
ids = [s['id'] for s in sigs[:16]]
st, d = req('/api/siggame/picks', {'picks': ids})
chk('16장 저장', st == 200 and d.get('count') == 16, (st, d))
st, d = req('/api/siggame/picks', {'picks': []})
chk('빈 목록은 거부', st == 400, st)
st, d = req('/api/siggame/picks', {'picks': list(range(1, 50))})
chk('36장 초과는 거부', st == 400, st)

print('\n3) 카드 깔기')
st, d = req('/api/siggame/deal', {'minutes': 10, 'target': 5})
chk('16장 배치', st == 200 and d.get('count') == 16, (st, d))
chk('4x4 격자', (d.get('cols'), d.get('rows')) == (4, 4), (d.get('cols'), d.get('rows')))
g = game()
chk('전부 덮여 있음', all(c['state'] == 'HIDDEN' for c in g['cards']), [c['state'] for c in g['cards']][:4])
chk('덮인 카드에 사진·이름이 안 실린다',
    all('image' not in c and 'title' not in c and 'sig_id' not in c for c in g['cards']),
    g['cards'][0])
chk('picks 는 번호만 나간다',
    all(set(p.keys()) == {'sig_id'} for p in g.get('picks') or []),
    (g.get('picks') or [None])[0])

print('\n4) 뒤집기')
st, d = req('/api/siggame/flip', {'id': 3})
chk('3번 뒤집힘 (이름·금액이 온다)', st == 200 and d.get('title'), (st, d))
first_title = d.get('title')
g = game()
c3 = next(c for c in g['cards'] if c['id'] == 3)
chk('공개된 카드에는 사진이 실린다', c3['state'] == 'REVEALED' and c3.get('image') is not None, c3)
chk('다른 카드는 여전히 덮여 있다',
    all(c['state'] == 'HIDDEN' for c in g['cards'] if c['id'] != 3))
st, d = req('/api/siggame/flip', {'id': 3})
chk('같은 카드 다시 뒤집으면 already', st == 200 and d.get('already'), (st, d))
st, d = req('/api/siggame/flip', {'id': 999})
chk('없는 번호는 404', st == 404, st)

for cid in (1, 2, 4, 5):
    req('/api/siggame/flip', {'id': cid})
st, d = req('/api/siggame/flip', {'id': 6})
chk('목표(5장)를 넘겨 뒤집을 수 없다', st == 400, (st, d))
g = game()
chk('뒤집은 카드 정확히 5장', sum(1 for c in g['cards'] if c['state'] == 'REVEALED') == 5)

print('\n5) 달성 표시')
st, d = req('/api/siggame/done', {'id': 7})
chk('안 뒤집은 카드는 달성 못 찍음', st == 400, st)
for cid in (3, 1, 2, 4):
    req('/api/siggame/done', {'id': cid})
g = game()
chk('4장 달성됨', sum(1 for c in g['cards'] if c.get('doneAt')) == 4)
req('/api/siggame/done', {'id': 5})
st, d = req('/api/siggame/done', {'id': 5, 'done': False})
chk('달성 취소됨', st == 200 and d.get('done') is False, (st, d))
# 5번 한 장을 비워둔 채 올클리어 → 남은 것까지 한 번에 달성하며 터진다 ('한 방' 버튼)
st, d = req('/api/siggame/allclear')
chk('남은 1장을 채우며 올클리어', st == 200 and d.get('count') == 5 and d.get('filled') == 1, (st, d))
g = game()
chk('전부 달성 상태가 됐다', sum(1 for c in g['cards'] if c.get('doneAt')) == 5)
g = game()
chk('올클리어 신호 전달', (g.get('action') or {}).get('type') == 'ALLCLEAR', g.get('action'))

print('\n6) 타이머')
st, d = req('/api/siggame/timer', {'action': 'START'})
chk('시작됨', st == 200 and d['timer']['status'] == 'PLAYING', d)
chk('끝나는 시각이 서버 시계로 온다',
    abs(d['timer']['expiresAt'] - (time.time() * 1000 + 600000)) < 3000, d['timer'])
time.sleep(1.2)
st, d = req('/api/siggame/timer', {'action': 'PAUSE'})
chk('일시정지 시 남은 시간 보존', st == 200 and 596 <= d['timer']['timeLeft'] <= 599, d['timer'])
st, d = req('/api/siggame/timer', {'action': 'STOP', 'minutes': 3})
chk('초기화 3분', st == 200 and d['timer']['timeLeft'] == 180, d['timer'])
st, d = req('/api/siggame/timer', {'action': 'WAT'})
chk('모르는 동작은 거부', st == 400, st)

print('\n7) 전체 공개 / 섞기 / 치우기')
st, d = req('/api/siggame/reveal')
g = game()
chk('전부 공개됨', st == 200 and all(c['state'] == 'REVEALED' for c in g['cards']))
goals = [c for c in g['cards'] if c.get('flippedAt')]
chk('구경용 공개는 목표에 안 들어간다 (목표는 5장 그대로)', len(goals) == 5, len(goals))
st, d = req('/api/siggame/shuffle')
g = game()
chk('섞으면 전부 다시 덮인다', st == 200 and all(c['state'] == 'HIDDEN' for c in g['cards']))
chk('섞으면 달성 기록도 지워진다', not any(c.get('doneAt') for c in g['cards']))
st, d = req('/api/siggame/clear')
g = game()
chk('판을 치우면 카드가 사라진다', st == 200 and not g['cards'])
chk('고른 시그니처는 남는다', len(g.get('picks') or []) == 16, len(g.get('picks') or []))
chk('치우면 표시도 꺼진다', g.get('enabled') is False)

print('\n8) 카드 없이 켜기')
st, d = req('/api/siggame/set', {'enabled': True})
chk('켜지긴 한다', st == 200 and d.get('enabled') is True, d)
st, d = req('/api/siggame/shuffle')
chk('카드 없이 섞기는 거부', st == 400, st)
st, d = req('/api/siggame/allclear')
chk('카드 없이 올클리어는 거부', st == 400, st)

print('\n═══ 통과 %d / 실패 %d ═══' % (ok, fail))

print('\n9) 시그니처 목록 공개 범위')
st, d = req('/api/signatures')
full = (d.get('signatures') or [])
chk('로그인 상태에서는 이름·금액이 온다',
    st == 200 and full and 'title' in full[0] and 'amount' in full[0], full[:1])
st, d = req('/api/signatures', auth=False)
pub = (d.get('signatures') or [])
chk('로그인 안 하면 목록은 열리되', st == 200 and len(pub) == len(full), (st, len(pub), len(full)))
chk('이름·금액은 빠진다', all('title' not in s and 'amount' not in s for s in pub), pub[:1])
chk('오버레이 미리받기에 필요한 것은 남는다',
    all('image_url' in s and 'sound_url' in s and 'id' in s for s in pub), pub[:1])

print('\n10) 목표 장수 제한')
sigs2 = full or pub
req('/api/siggame/picks', {'picks': [s['id'] for s in sigs2[:6]]})
req('/api/siggame/deal', {'minutes': 5, 'target': 3})
st, d = req('/api/siggame/set', {'target': 99})
chk('깔린 장수(6)를 넘겨 잡을 수 없다', st == 200 and d.get('target') == 6, d)
st, d = req('/api/siggame/set', {'target': 0})
chk('0 이하도 못 잡는다', st == 200 and d.get('target') == 1, d)
st, d = req('/api/siggame/set', {'target': 'x'})
chk('숫자가 아니면 그대로 둔다', st == 200 and d.get('target') == 1, d)
st, d = req('/api/siggame/deal', {'minutes': 5, 'target': 20})
chk('깔 때도 고른 장수를 넘지 않는다', st == 200 and d.get('target') == 6, d)

print('\n11) 이상한 입력')
for body, why in [({'id': 'abc'}, '카드 번호가 글자'), ({}, '번호 없음'), ({'id': None}, '번호가 null')]:
    st, _ = req('/api/siggame/flip', body)
    chk('뒤집기 — ' + why + ' → 400', st == 400, st)
st, _ = req('/api/siggame/picks', {'picks': 'notalist'})
chk('고르기 — 목록이 아니면 400', st == 400, st)
st, d = req('/api/siggame/deal', {'minutes': 9999})
chk('말도 안 되는 분은 잘라낸다', st == 200, st)
g = game()
chk('타이머가 180분으로 제한됨', g['timer']['timeLeft'] == 180 * 60, g['timer'])

print('\n12) 총금액은 받아낸 것을 뺀다')
"""사장님 말: "총금액이 100만원인데 5만원짜리 시그를 클리어하면 95만원으로
   빠졌으면 좋겠어. 올리지는 말고."

⚠️ 예전에는 뒤집힌 카드를 전부 더해서, 클리어를 해도 숫자가 안 줄었다. 올라가기만
   하고 안 내려가면 '얼마 남았나' 를 알 수가 없다. 바로 옆 주석도 '다 받아내려면
   얼마인가' 라고 적혀 있으니 뜻으로도 이쪽이 맞다."""
import io as _io
import os as _os

_H = _os.path.dirname(_os.path.abspath(__file__))
_FALLBACK = r'C:\Users\Administrator\Desktop\새로다시시작'


def _proj():
    d = _H
    for _ in range(4):
        d = _os.path.dirname(d)
        if _os.path.exists(_os.path.join(d, 'overlay.html')):
            return d
    return _FALLBACK


_ov = _io.open(_os.path.join(_proj(), 'overlay.html'), encoding='utf-8', errors='replace').read()
chk('받아낸 카드(doneAt)는 총금액에서 뺀다',
    'const sum = goals.reduce((a, c) => a + (c.doneAt ? 0 : (Number(c.amount) || 0)), 0);' in _ov)
chk('예전처럼 전부 더하지 않는다',
    'goals.reduce((a, c) => a + (Number(c.amount) || 0), 0)' not in _ov)

# 실제로 뒤집고 클리어해서 남는 금액이 줄어드는지 본다
_g = game()
_cards = _g.get('cards') or []
if len(_cards) >= 2:
    for _c in _cards[:2]:
        req('/api/siggame/flip', {'id': _c['id']})
    _g = game()
    _fl = [c for c in (_g.get('cards') or []) if c.get('flippedAt')]
    _before = sum(int(c.get('amount') or 0) for c in _fl if not c.get('doneAt'))
    _one = _fl[0]
    req('/api/siggame/done', {'id': _one['id'], 'done': True})
    _g = game()
    _fl = [c for c in (_g.get('cards') or []) if c.get('flippedAt')]
    _after = sum(int(c.get('amount') or 0) for c in _fl if not c.get('doneAt'))
    chk('클리어하면 그 금액만큼 줄어든다',
        _after == _before - int(_one.get('amount') or 0),
        '%s → %s (뺀 값 %s)' % (_before, _after, _one.get('amount')))
    chk('클리어해도 금액이 늘지는 않는다', _after <= _before, '%s → %s' % (_before, _after))

print('\n═══ 최종 통과 %d / 실패 %d ═══' % (ok, fail))
