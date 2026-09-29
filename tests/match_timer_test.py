# -*- coding: utf-8 -*-
"""⏱️ 대결 타이머 — 리액션 모드에 멈추고 이어 가기(누가 켰든) · 키보드로 시간 넣기.

대표님(2026-09-30): "후원으로 리액션모드로 진입하면 타이머가 자동으로 안 멈추는데,
손으로 직접 리액션모드 누르면 멈춰" · "타이머 설정을 냅다 키보드로 · 분 단위 초 단위로"
"""
import io
import json
import os
import sys
import time
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


def md():
    return get().get('match_data') or {}


def start_match(left_ms=120000):
    now = int(time.time() * 1000)
    post('/api/restore', {'broadcast_active': True, 'reaction_queue': [], 'reaction_mode': False, 'reaction_paused': False,
                          'bjs': [{'name': '철수', 'score': 0, 'contribution': 0}],
                          'match_data': {'active': True, 'is_running': True, 'end_time_ms': now + left_ms,
                                         'time_left_ms': left_ms, 'players': [{'name': 'A팀', 'score': 0, 'members': []}]}})


print('=' * 74)
print('① 후원 시그니처(서버가 켜는 리액션)에도 타이머가 멈춘다')
print('=' * 74)
start_match(120000)
post('/api/data', {'ticker_speed': 70})      # 저장 한 번 — 서버가 '지금은 리액션 아님' 을 기억하게
time.sleep(1.0)
st, r = post('/api/signature/play', {'sig_id': 10005, 'name': '손님A'})
m = md()
chk('시그가 줄에 들어가 리액션 모드가 켜졌다', st == 200 and get().get('reaction_mode') is True, (st, r.get('message')))
chk('⭐ 타이머가 멈췄다 (예전: 계속 흘렀다)', m.get('is_running') is False and m.get('was_running_before_reaction') is True, m)
chk('남은 시간을 붙잡아 둔다 (약 119초)', 110000 <= (m.get('time_left_ms') or 0) <= 120000, m.get('time_left_ms'))
left_frozen = m.get('time_left_ms')
time.sleep(2.0)
chk('멈춘 동안 남은 시간이 안 줄어든다', md().get('time_left_ms') == left_frozen, md().get('time_left_ms'))

print()
print('=' * 74)
print('② 시그가 끝나 리액션 모드가 꺼지면 그 자리부터 이어서 돈다')
print('=' * 74)
post('/api/reaction/stop', {})
m = md()
now = int(time.time() * 1000)
chk('⭐ 다시 돈다', m.get('is_running') is True and m.get('was_running_before_reaction') is False, m)
chk('멈춘 만큼 끝나는 시각이 밀렸다 (남은 시간 그대로)', abs((m.get('end_time_ms') or 0) - now - left_frozen) < 2500,
    ((m.get('end_time_ms') or 0) - now, left_frozen))

print()
print('=' * 74)
print('③ 손으로 멈춘 타이머는 리액션이 끝나도 저절로 안 돈다')
print('=' * 74)
start_match(90000)
post('/api/data', {'ticker_speed': 70})
s = get()
s['match_data']['is_running'] = False
s['match_data']['time_left_ms'] = 60000
post('/api/data', s)
post('/api/signature/play', {'sig_id': 10005, 'name': '손님B'})
post('/api/reaction/stop', {})
m = md()
chk('손으로 멈춘 것은 그대로 멈춰 있다', m.get('is_running') is False and m.get('time_left_ms') == 60000, m)

print()
print('=' * 74)
print('④ 손으로 켜는 리액션(조종실이 먼저 얼려 보냄)도 두 번 얼리지 않는다')
print('=' * 74)
start_match(100000)
post('/api/data', {'ticker_speed': 70})
s = get()
s['match_data'].update({'is_running': False, 'time_left_ms': 95000, 'was_running_before_reaction': True,
                        'paused_time_left': 95000})
s['reaction_mode'] = True
post('/api/data', s)
m = md()
chk('조종실이 얼린 값 그대로 (95초)', m.get('is_running') is False and m.get('time_left_ms') == 95000, m)
s = get()
s['match_data'].update({'is_running': True, 'end_time_ms': int(time.time() * 1000) + 95000,
                        'was_running_before_reaction': False})
s['reaction_mode'] = False
post('/api/data', s)
m = md()
chk('조종실이 이어 보낸 뒤에도 한 번만 이어진다', m.get('is_running') is True and m.get('was_running_before_reaction') is False, m)

print()
print('=' * 74)
print('⑤ 조종실 — 분 · 초를 키보드로 넣는다')
print('=' * 74)


def _proj():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.exists(os.path.join(d, 'controller.html')):
            return d
        d = os.path.dirname(d)
    return os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


CTL = io.open(os.path.join(_proj(), 'controller.html'), encoding='utf-8', errors='replace').read()
chk('분 · 초 입력칸과 Enter 맞추기', 'id="timer-set-m"' in CTL and 'id="timer-set-s"' in CTL
    and 'onsubmit="event.preventDefault(); setTimerFromInputs();"' in CTL)
chk('맞추기는 서버 시계 기준 · 돌고 있으면 이어서', 'function setTimerFromInputs()' in CTL
    and 'md.end_time_ms = (Date.now() + serverTimeOffset) + ms' in CTL)
SV = io.open(os.path.join(_proj(), 'server.py'), encoding='utf-8', errors='replace').read()
chk('서버가 저장할 때 리액션 켜짐/꺼짐을 보고 타이머를 맞춘다', 'def _match_follow_reaction(state)' in SV
    and '_match_follow_reaction(new_data)' in SV)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
