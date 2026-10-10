# -*- coding: utf-8 -*-
"""🎱 핀볼 — 끼어서 끊은 판 표시(cut) · 시간 상한 없앤 뒤 (2026-10-11)

10-08 52판(구슬 186개 · 끝까지 남기)이 정확히 3분에 잘려 2개가 남은 채 '밍밍 우승'이 떴다.
대표님: "제한 없이 끝까지". 그래서 시간 상한을 빼고, 끼어서 끊은 판만 그렇다고 밝힌다.

서버가 정말 그렇게 하는가:
  · 방송판이 cut='stall' 로 보고하면 상태에 cut 이 남고, 기록에도 적힌다
  · 모르는 cut 값은 '제대로 갈림'('')으로 받는다
  · 새 판 · 명단 · 초기화 때 cut 이 지워진다
  · 끊긴 판이어도 당첨자 셈(끝까지 남기 = 뒤에서부터)은 그대로다

pt 서버가 필요하다(LM_PT_PORT, 기본 5199). ⚠️ 샌드박스 서버에만 돌린다.
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:150]) if detail else ''))


def post(path, obj=None):
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), H)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get(path='/api/data'):
    with urllib.request.urlopen(urllib.request.Request(B + path, headers=H), timeout=40) as r:
        return json.loads(r.read().decode())


def pb():
    return get().get('pinball') or {}


NAMES = ['가가', '나나', '다다']

print('① 끼어서 끊은 판')
st, _ = post('/api/pinball/setup', {'names': NAMES, 'rule': 'last', 'picks': 1})
chk('명단을 넣는다', st == 200, st)
st, r = post('/api/pinball/start', {})
rid = ((r or {}).get('pinball') or {}).get('round_id')
chk('한 판 시작', st == 200 and rid, st)
chk('시작하면 끊김 표시가 비어 있다', pb().get('cut') == '', pb().get('cut'))

st, _ = post('/api/pinball/result', {'round_id': rid, 'result': NAMES, 'cut': 'stall'})
chk('끊긴 판 결과를 받는다', st == 200, st)
g = pb()
chk('상태에 끊김이 남는다', g.get('cut') == 'stall', g.get('cut'))
chk('끝까지 남기 = 뒤에서부터(끊겨도 셈은 같다)', g.get('winners') == ['다다'], g.get('winners'))
logs = get().get('logs') or []
top = (logs[0].get('name') if logs else '') or ''
chk('기록에 끊긴 판이라고 적는다', '다다' in top and '구슬이 껴서' in top, top)
st, _ = post('/api/pinball/result', {'round_id': rid, 'result': list(reversed(NAMES)), 'cut': ''})
chk('두 번째 보고는 409 (문이 닫혔다)', st == 409, st)
chk('늦은 보고가 끊김 표시를 안 바꾼다', pb().get('cut') == 'stall', pb().get('cut'))

print('② 새 판 · 모르는 값 · 초기화')
st, r = post('/api/pinball/start', {})
rid = ((r or {}).get('pinball') or {}).get('round_id')
chk('새 판이면 끊김 표시를 지운다', st == 200 and pb().get('cut') == '', pb().get('cut'))
st, _ = post('/api/pinball/result', {'round_id': rid, 'result': NAMES, 'cut': '<b>x</b>'})
chk('모르는 값은 제대로 갈린 판으로 받는다', st == 200 and pb().get('cut') == '', pb().get('cut'))
logs = get().get('logs') or []
top = (logs[0].get('name') if logs else '') or ''
chk('제대로 갈린 판 기록엔 끊김 말이 없다', '구슬이 껴서' not in top, top)

st, r = post('/api/pinball/start', {})
rid = ((r or {}).get('pinball') or {}).get('round_id')
post('/api/pinball/result', {'round_id': rid, 'result': NAMES, 'cut': 'stall'})
st, _ = post('/api/pinball/reset', {})
chk('초기화하면 끊김 표시를 지운다', st == 200 and pb().get('cut') == '', pb().get('cut'))
post('/api/pinball/result', {'round_id': rid, 'result': NAMES, 'cut': 'stall'})
st, _ = post('/api/pinball/setup', {'names': NAMES})
chk('명단을 다시 넣어도 지운다', st == 200 and pb().get('cut') == '', pb().get('cut'))

post('/api/pinball/enable', {'enabled': False})      # 뒷정리 — 다음 검사에 무대를 남기지 않는다

print()
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
