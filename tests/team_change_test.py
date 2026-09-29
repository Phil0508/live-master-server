# -*- coding: utf-8 -*-
"""⚔️ 팀을 바꾼 뒤에도 점수가 맞는 팀으로 가는가.

대표님(2026-09-30): "팀교체로 팀을 바꾸고도 원래 팀으로 들어가는 버그 같은 건 당연히 없겠지?"
→ 있었다(시험 서버 재현).
  ① 폰이 옛 사본으로 대결 타이머를 누르면 팀원이 옛 구성으로 돌아가, 옮긴 사람 점수가 다시 옛 팀으로 들어갔다
  ② A팀일 때 받은 점수를 B팀으로 옮긴 뒤 되돌리면 B팀에서 빠졌다(A팀은 그대로)
"""
import copy
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


def teams():
    return {p['name']: (p['score'], list(p.get('members') or [])) for p in get()['match_data']['players']}


def reset():
    post('/api/restore', {'broadcast_active': True, 'logs': [], 'match_logs': [],
                          'bjs': [{'name': '철수', 'score': 0, 'contribution': 0},
                                  {'name': '영희', 'score': 0, 'contribution': 0}],
                          'match_data': {'active': True, 'team_mode': True, 'players': [
                              {'name': 'A팀', 'score': 0, 'members': ['철수']},
                              {'name': 'B팀', 'score': 0, 'members': ['영희']}]}})


def move_to_b():
    s = get()
    s['match_data']['players'][0]['members'] = []
    s['match_data']['players'][1]['members'] = ['영희', '철수']
    post('/api/data', s)


print('=' * 74)
print('① 팀을 옮기면 그다음 점수는 새 팀으로')
print('=' * 74)
reset()
post('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': 5})
l1 = get()['logs'][0]
chk('A팀일 때 +5 → A팀 5', teams()['A팀'][0] == 5, teams())
chk('로그 줄에 그때 들어간 팀이 적힌다 (A팀)', l1.get('team') == 'A팀', l1)
phone = copy.deepcopy(get())            # 폰이 들고 있던 사본 — 팀을 옮기기 전
move_to_b()
post('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': 3})
chk('B팀으로 옮긴 뒤 +3 → B팀 3 · A팀 5 그대로', teams()['B팀'][0] == 3 and teams()['A팀'][0] == 5, teams())

print()
print('=' * 74)
print('② 되돌리기는 그 점수가 들어갔던 팀에서 뺀다')
print('=' * 74)
post('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': -5, 'log': False,
                        'undo_log': {'time': l1['time'], 'name': l1['name'], 'val': l1['val']}})
t = teams()
chk('⭐ A팀 때 받은 +5 를 되돌리면 A팀에서 빠진다 (예전: B팀에서 빠져 -2)', t['A팀'][0] == 0 and t['B팀'][0] == 3, t)
l2 = get()['logs'][0]
post('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': -3, 'log': False,
                        'undo_log': {'time': l2['time'], 'name': l2['name'], 'val': l2['val']}})
t = teams()
chk('B팀 때 받은 +3 을 되돌리면 B팀에서 빠진다', t['A팀'][0] == 0 and t['B팀'][0] == 0, t)

print()
print('=' * 74)
print('③ 폰이 옛 사본으로 타이머를 눌러도 팀 구성은 안 돌아간다')
print('=' * 74)
md = phone['match_data']
md['time_left_ms'] = 60000
st, _ = post('/api/settings/patch', {'match_data': md})
d = get()
t = teams()
chk('타이머는 바뀐다', st == 200 and d['match_data'].get('time_left_ms') == 60000, d['match_data'].get('time_left_ms'))
chk('⭐ 팀원은 서버 값 그대로 (철수 = B팀)', t['B팀'][1] == ['영희', '철수'] and t['A팀'][1] == [], t)
post('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': 2})
t = teams()
chk('⭐ 그 뒤 철수 점수는 B팀으로 (예전: A팀으로 되돌아감)', t['B팀'][0] == 2 and t['A팀'][0] == 0, t)
md2 = copy.deepcopy(get()['match_data'])
md2['active'] = False
post('/api/settings/patch', {'match_data': md2})
chk('폰의 대결 켜기/끄기는 그대로 된다', get()['match_data'].get('active') is False)

print()
print('=' * 74)
print('④ 팀 기록이 없는 옛 줄을 되돌리면 예전처럼 지금 소속으로')
print('=' * 74)
reset()
post('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': 4})
s = get()
s['logs'][0].pop('team', None)          # 이 수정 전에 남은 줄 흉내
post('/api/data', dict(s, logs=s['logs']))
l = get()['logs'][0]
post('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': -4, 'log': False,
                        'undo_log': {'time': l['time'], 'name': l['name'], 'val': l['val']}})
chk('옛 줄 되돌리기도 동작한다 (A팀 4 → 0)', teams()['A팀'][0] == 0, teams())

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
