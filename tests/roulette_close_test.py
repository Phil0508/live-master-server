# -*- coding: utf-8 -*-
"""🎡 룰렛이 제대로 닫히는가.

■ 왜 이 검사가 있나
  진행자가 [정지] 를 누르면 조종실이 곧바로 is_spinning=false 로 만들었다.
  그런데 원판은 그 순간 서는 게 아니라 몇 초 더 돌다 멈춘다. 실제로 멈췄을 때
  오버레이가 /api/roulette/winner 로 당첨자를 보고하는데, 서버는 '돌고 있지도
  않은데 결과가 들어왔다' 며 409 로 거부했다 — 오버레이는 OBS 라 로그인 세션이
  없어서 그 예외에도 못 걸린다.

  거부되면 roulette_enabled 가 안 꺼지고, 화면은 그걸 보고 위젯을 내리므로
  **룰렛이 영영 안 닫혔다.** 당첨자도 기록되지 않았다.

■ 무엇을 지키나
  · 정지를 눌러도 원판이 멈출 때까지는 '도는 중' 이어야 한다
  · 세션 없는 오버레이가 보내는 당첨 보고가 통해야 한다
  · 보고가 통하면 룰렛이 꺼지고 당첨자·로그가 남아야 한다
  · 돌지도 않는데 밖에서 결과를 밀어넣는 것은 여전히 막아야 한다 (원래 그 방어의 목적)
"""
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
AUTH = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
NOAUTH = {'Content-Type': 'application/json'}      # ← 오버레이(OBS)와 같은 조건
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


def post(path, obj, hdr):
    req = urllib.request.Request(B + path, json.dumps(obj).encode(), hdr)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=AUTH), timeout=25) as r:
        return json.loads(r.read().decode())


def spin():
    d = get()
    d['roulette_enabled'] = True
    d['roulette'] = dict(d.get('roulette') or {}, command='spin',
                         command_time=int(time.time() * 1000), is_spinning=True, winner_name=None)
    post('/api/data', d, AUTH)


def press_stop():
    """고친 조종실이 보내는 그대로 — is_spinning 을 건드리지 않는다."""
    d = get()
    d['roulette'] = dict(d['roulette'], command='stop', command_time=int(time.time() * 1000))
    post('/api/data', d, AUTH)


print('=' * 74)
print('① 정지를 눌러도 원판이 멈출 때까지는 도는 중이어야 한다')
print('=' * 74)
spin()
chk('돌리면 도는 중이 된다', get()['roulette'].get('is_spinning') is True)
press_stop()
chk('정지를 눌러도 아직 도는 중이다', get()['roulette'].get('is_spinning') is True,
    '여기서 꺼지면 당첨 보고가 409 로 거부된다')

print()
print('=' * 74)
print('② 세션 없는 오버레이의 당첨 보고가 통하고, 룰렛이 닫힌다')
print('=' * 74)
c, _ = post('/api/roulette/winner', {'name': '제이양'}, NOAUTH)
chk('오버레이(무세션) 당첨 보고가 통한다', c == 200, c)
d = get()
chk('룰렛이 꺼진다', d.get('roulette_enabled') is False, d.get('roulette_enabled'))
chk('당첨자가 남는다', d['roulette'].get('winner_name') == '제이양', d['roulette'].get('winner_name'))
chk('도는 중이 풀린다', d['roulette'].get('is_spinning') is False)
chk('로그에 결과가 적힌다',
    any('룰렛 결과' in str(l.get('name')) for l in (d.get('logs') or [])),
    str((d.get('logs') or [])[:1])[:90])

print()
print('=' * 74)
print('③ 돌지도 않는데 밖에서 결과를 밀어넣는 것은 여전히 막는다')
print('=' * 74)
c, r = post('/api/roulette/winner', {'name': '남의이름'}, NOAUTH)
chk('무세션 + 안 도는 중 → 409 거부', c == 409, (c, r.get('message')))
d = get()
chk('당첨자가 안 바뀐다', d['roulette'].get('winner_name') == '제이양', d['roulette'].get('winner_name'))

print()
print('=' * 74)
print('④ 초기화는 그대로 원판을 세운다')
print('=' * 74)
spin()
d = get()
d['roulette'] = dict(d['roulette'], command='reset', command_time=int(time.time() * 1000),
                     is_spinning=False, winner_name=None)
post('/api/data', d, AUTH)
chk('초기화하면 도는 중이 풀린다', get()['roulette'].get('is_spinning') is False)

print()
print('=' * 74)
print('⑤ 화면 쪽 회귀 — 정지에서 is_spinning 을 끄지 않는가')
print('=' * 74)
for f in ('controller.html', 'mobile.html'):
    s = io.open(os.path.join(ROOT, f), encoding='utf-8', errors='replace').read()
    m = re.search(r"cmd === 'stop'\s*\)\s*\{(.*?)\}", s, re.S)
    body = m.group(1) if m else ''
    chk('%s 의 정지가 is_spinning 을 안 건드린다' % f,
        m is not None and 'is_spinning = false' not in body.replace(' ', ' '),
        body.strip()[:70] if m else '패턴 못 찾음')

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
