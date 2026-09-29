# -*- coding: utf-8 -*-
"""🧮 로그에 '몇에 몇을 더해 몇' — before · after 가 실제 점수와 맞는가.

대표님(2026-09-30): "로그에도 지금은 +5 라고만 나와있지만 몇에다가 몇을 더해서 몇이 되었다 라고도 뜨게 해줘"
- 점수 배정 · 나눠주기 · 기여도만 · 운영비 · 대결 · 주사위 전용 판 · 주사위 정산 줄 모두
- 앞 + 더한 값 = 뒤, 그리고 뒤 = 그 순간 서버의 실제 값
- 되돌리기는 여전히 원래 줄을 찾아 지운다(짝 맞추기는 time · name · val 만 본다)
"""
import io
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


def top_log(d=None, key='logs'):
    return ((d or get()).get(key) or [{}])[0]


def consistent(l):
    return l.get('before') is not None and l.get('after') is not None and l['before'] + l['val'] == l['after']


post('/api/restore', {'broadcast_active': True, 'extra_game_active': False, 'extra_bjs': [], 'logs': [], 'match_logs': [],
                      'bjs': [{'name': '밍밍', 'score': 12, 'contribution': 30},
                              {'name': '콩콩', 'score': 3, 'contribution': 7}],
                      'bottom_fixed': {'name': '운영비', 'score': 100},
                      'match_data': {'active': True, 'players': [{'name': 'A팀', 'score': 40, 'members': []}]}})

print('=' * 74)
print('① 점수 배정 — 12 + 5 = 17 (기여도 30 + 5 = 35)')
print('=' * 74)
post('/api/score/add', {'scope': 'rank', 'name': '밍밍', 'delta': 5})
d = get(); l = top_log(d)
chk('점수 줄에 앞 · 뒤가 있다', l.get('before') == 12 and l.get('after') == 17, l)
chk('앞 + 더한 값 = 뒤', consistent(l), l)
chk('뒤 = 서버의 실제 점수', l.get('after') == next(b['score'] for b in d['bjs'] if b['name'] == '밍밍'))
chk('기여도도 같이 적는다 (30 + 5 = 35)', l.get('cbefore') == 30 and l.get('cval') == 5 and l.get('cafter') == 35, l)

print()
print('=' * 74)
print('② 나눠주기 — 사람마다 따로 맞는다')
print('=' * 74)
post('/api/score/add', {'scope': 'rank', 'items': [{'name': '밍밍', 'delta': 2}, {'name': '콩콩', 'delta': 1}]})
d = get()
ls = (d.get('logs') or [])[:2]
chk('두 줄 모두 앞 + 더한 값 = 뒤', len(ls) == 2 and all(consistent(x) for x in ls), ls)
real = {b['name']: b['score'] for b in d['bjs']}
chk('두 줄의 뒤 = 각자 실제 점수', all(x.get('after') == real.get(x.get('name')) for x in ls), (ls, real))

print()
print('=' * 74)
print('③ 기여도만 · 운영비 · 대결')
print('=' * 74)
post('/api/score/add', {'scope': 'rank', 'name': '콩콩', 'delta': 0, 'contribution': 4, 'reason': '손으로 고침'})
l = top_log()
chk('기여도만 움직인 줄: 기여도 앞 · 뒤', l.get('kind') == 'contrib' and consistent(l), l)
post('/api/score/add', {'scope': 'bot', 'name': '', 'delta': 3})
d = get(); l = top_log(d)
chk('운영비 줄: 100 + 3 = 103', l.get('before') == 100 and l.get('after') == 103 and d['bottom_fixed']['score'] == 103, l)
post('/api/score/add', {'scope': 'match', 'name': 'A팀', 'delta': 7})
d = get(); l = top_log(d, 'match_logs')
chk('대결 줄: 40 + 7 = 47', l.get('before') == 40 and l.get('after') == 47, l)

print()
print('=' * 74)
print('④ 되돌리기는 여전히 원래 줄을 지운다')
print('=' * 74)
post('/api/score/add', {'scope': 'rank', 'name': '밍밍', 'delta': 9})
l = top_log()
n0 = len(get().get('logs') or [])
post('/api/score/add', {'scope': 'rank', 'name': '밍밍', 'delta': -9, 'log': False,
                        'undo_log': {'time': l['time'], 'name': l['name'], 'val': l['val']}})
d = get()
chk('되돌리면 그 줄이 사라진다', len(d.get('logs') or []) == n0 - 1 and top_log(d).get('val') != 9, top_log(d))

print()
print('=' * 74)
print('⑤ 주사위 전용 판 · 정산')
print('=' * 74)
post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'dice': 1, 'roll_price': 0})
post('/api/dicegame/board', {'do': 'add', 'name': '밍밍', 'pts': 10})
post('/api/dicegame/board', {'do': 'add', 'name': '밍밍', 'pts': 5})
l = top_log()
chk('주사위 줄: 10 + 5 = 15', l.get('kind') == 'dice' and l.get('before') == 10 and l.get('after') == 15, l)
c0 = next(b['contribution'] for b in get()['bjs'] if b['name'] == '밍밍')
post('/api/dicegame/board', {'do': 'apply'})
d = get()
l = next((x for x in d.get('logs') or [] if x.get('why') == '🎲 주사위게임 정산'), {})
chk('정산 줄: 기여도 앞 + 15 = 뒤 (실제 기여도)', l.get('before') == c0 and l.get('after') == c0 + 15
    and l.get('after') == next(b['contribution'] for b in d['bjs'] if b['name'] == '밍밍'), l)

print()
print('=' * 74)
print('⑥ 화면 — 조종실 · 폰이 앞 · 뒤를 그린다 (안 맞으면 빨갛게)')
print('=' * 74)


def _proj():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.exists(os.path.join(d, 'controller.html')):
            return d
        d = os.path.dirname(d)
    return os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


CTL = io.open(os.path.join(_proj(), 'controller.html'), encoding='utf-8', errors='replace').read()
MOB = io.open(os.path.join(_proj(), 'mobile.html'), encoding='utf-8', errors='replace').read()
chk('조종실 점수 로그가 logMath 를 쓴다', "logMath(log.before, log.val, log.after, isC ? '기여도 ' : '')" in CTL and 'function logMath(before, val, after, pre)' in CTL)
chk('조종실 대결 로그 두 곳도', CTL.count("${logMath(log.before, log.val, log.after, '')}") == 2)
chk('앞뒤가 안 맞으면 빨갛게 표시', "앞뒤가 안 맞아요" in CTL)
chk('폰 로그도 앞→뒤', "${Number(l.before).toLocaleString()}→${Number(l.after).toLocaleString()}" in MOB)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
