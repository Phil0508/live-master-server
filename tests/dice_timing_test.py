# -*- coding: utf-8 -*-
"""🎲⏱️ 주사위 연출 시간표 — 서버(_dicegame_plan)와 방송판(dgRollPlan)이 같은 값을 내는가.

서버는 이 값으로 연타를 막고(429), 방송판은 이 값으로 연출 · 가리개 문을 맞춘다.
둘이 어긋나면 ① 연출 중간에 다음 굴림이 끼어들거나(블랙홀 역주행 중 3.2초에 끼어든 적 있다)
② 연출이 끝났는데도 굴림이 막힌다. 서버 없이 돈다 — 두 함수를 파일에서 꺼내 같은 굴림을 넣는다.
"""
import ast
import io
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:140]) if detail else ''))


def _proj():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.exists(os.path.join(d, 'server.py')) and os.path.isdir(os.path.join(d, 'features')):
            return d
        d = os.path.dirname(d)
    return os.environ.get('LM_ROOT') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


ROOT = _proj()
PY_SRC = io.open(os.path.join(ROOT, 'features', 'dicegame.py'), encoding='utf-8').read()
OV = io.open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8', errors='replace').read()

# ── 서버 쪽: 상수 셋 + _dicegame_plan 만 꺼내 돌린다(server 를 import 하면 서버가 통째로 뜬다)
tree = ast.parse(PY_SRC)
keep = [n for n in tree.body
        if (isinstance(n, ast.Assign) and any(getattr(t, 'id', '') in ('DG_SIG_BEAT', 'DG_CARD_BEAT', 'DG_KEY_DRAW')
                                               for t in n.targets))
        or (isinstance(n, ast.FunctionDef) and n.name == '_dicegame_plan')]
ns = {}
exec(compile(ast.Module(body=keep, type_ignores=[]), 'dicegame_plan', 'exec'), ns)
py_plan = ns['_dicegame_plan']

# ── 방송판 쪽: 상수 줄 + dgRollPlan 함수를 꺼내 node 로 돌린다
i0 = OV.index('const DG_SIG_BEAT = ')
i1 = OV.index('function dgRollPlan(act)')
depth, j = 0, OV.index('{', i1)
while True:
    if OV[j] == '{':
        depth += 1
    elif OV[j] == '}':
        depth -= 1
        if depth == 0:
            break
    j += 1
JS = OV[i0:OV.index('\n', i0)] + '\n' + OV[i1:j + 1]


def P(n):   # 경로 n 칸
    return list(range(1, n + 1))


CASES = {
    '무작위 1개 · 3칸 · 점수 칸': {'dice': [3], 'path': P(3), 'tile': {'type': 'score'}},
    '현실 주사위 · 6칸 · 시그 칸': {'manual': True, 'dice': [6], 'path': P(6), 'tile': {'type': 'sig'}},
    '무작위 2개 · 12칸 · 시그 칸': {'dice': [6, 6], 'path': P(12), 'tile': {'type': 'sig'}},
    '열쇠 → 뒤로 7칸': {'manual': True, 'dice': [4], 'path': P(4), 'tile': {'type': 'key'},
                     'after': {'rev': True, 'path': P(7), 'tile': {'type': 'score'}}},
    '열쇠 → 출발지로 18칸 역주행': {'manual': True, 'dice': [2], 'path': P(2), 'tile': {'type': 'key'},
                          'after': {'rev': True, 'path': P(18), 'tile': {'type': 'start'}}},
    '싱크홀 5칸 → 열쇠 칸': {'dice': [5], 'path': P(5), 'tile': {'type': 'move'},
                      'after': {'rev': True, 'path': P(5), 'tile': {'type': 'key'}}},
    '블랙홀 21칸 역주행': {'manual': True, 'dice': [3], 'path': P(3), 'tile': {'type': 'goto'},
                    'after': {'rev': True, 'path': P(21), 'tile': {'type': 'start'}}},
    '앞으로 9칸(역주행 아님)': {'dice': [1], 'path': P(1), 'tile': {'type': 'key'},
                       'after': {'rev': False, 'path': P(9), 'tile': {'type': 'blank'}}},
    '칸 정보 없음': {'dice': [2], 'path': P(2)},
}
# 역주행 길이 9~31 을 전부 — 빨리 밟는 칸당 시간(2400/칸수 반올림)이 두 언어에서 같아야 한다
for n in range(9, 32):
    CASES['역주행 %d칸' % n] = {'manual': True, 'dice': [1], 'path': P(1), 'tile': {'type': 'goto'},
                            'after': {'rev': True, 'path': P(n), 'tile': {'type': 'start'}}}

prog = JS + '\nconst C = ' + json.dumps(CASES, ensure_ascii=False) + ';\n' \
       'const out = {}; for (const k in C) { const p = dgRollPlan(C[k]); out[k] = { land: p.land, gate: p.gate }; }\n' \
       'process.stdout.write(JSON.stringify(out));'
r = subprocess.run(['node', '-e', prog], capture_output=True, text=True, encoding='utf-8')
if r.returncode != 0:
    print(r.stderr[-800:])
js = json.loads(r.stdout or '{}')

print('=' * 74)
print('① 서버와 방송판이 같은 시간표를 낸다')
print('=' * 74)
diff = [(k, py_plan(v), js.get(k)) for k, v in CASES.items() if py_plan(v) != js.get(k)]
chk('%d가지 굴림 모두 같다 (말 닿는 때 · 연출 끝)' % len(CASES), not diff and len(js) == len(CASES), diff[:3])
for k in ('무작위 1개 · 3칸 · 점수 칸', '현실 주사위 · 6칸 · 시그 칸', '열쇠 → 출발지로 18칸 역주행', '블랙홀 21칸 역주행'):
    print('     %-22s 닿음 %5dms · 끝 %5dms' % (k, py_plan(CASES[k])['land'], py_plan(CASES[k])['gate']))

print()
print('=' * 74)
print('② 시그 칸은 말이 닿고 카드를 1.5초 읽힌 뒤에 가리개 · 시그')
print('=' * 74)
s = py_plan(CASES['현실 주사위 · 6칸 · 시그 칸'])
chk('닿는 때 = 380 + 6칸×300 + 120', s['land'] == 380 + 1800 + 120, s)
chk('끝 = 닿는 때 + 1.5초', s['gate'] - s['land'] == 1500, s)
chk('방송판: 말이 닿는 순간 곧바로 틀지 않는다 (예전: dgBusyUntil = 0 + checkReactionQueue 를 landAt 에서)',
    'dgAfter(plan.gate, dgGateOpen);' in OV and "사장님: \"6나오고 이쿠욧이 딱 뜨면 바로 시그 재생하자\"\n                window.dgBusyUntil = 0;" not in OV)
chk('방송판: 문을 열 때 가리개와 시그를 같이 연다',
    'function dgGateOpen()' in OV and OV.index('try { shApply(globalData); } catch (e) {}', OV.index('function dgGateOpen()'))
    < OV.index('try { checkReactionQueue(); } catch (e) {}', OV.index('function dgGateOpen()')))

print()
print('=' * 74)
print('③ 끌려가기 · 열쇠 뽑기까지 센다 (예전 연타 막기는 걷는 시간까지만)')
print('=' * 74)
bh = py_plan(CASES['블랙홀 21칸 역주행'])
old_hold = 3 * 300 + 0 + 2200     # 예전 식: 칸×300 + 구르기 + 2.2초
chk('블랙홀: 예전 연타 막기(3.1초)는 역주행이 끝나기 전에 풀렸다 → 이제 끝까지 막는다',
    bh['gate'] + 300 > old_hold + 2000, '예전 %dms · 지금 %dms' % (old_hold, bh['gate'] + 300))
chk('서버 연타 막기는 시간표를 쓴다', '_dicegame_plan(prev)[\'gate\'] + 300' in PY_SRC)
chk('예전 식은 없다', 'hold = len(prev.get(\'path\') or []) * 300 + _tumble + 2200' not in PY_SRC)

print()
print('=' * 74)
print('④ 제일 긴 연출도 방송판의 마지막 방어선(DG_HOLD_CAP) 안이다')
print('=' * 74)
import re
m = re.search(r'const DG_HOLD_CAP = (\d+);', OV)
cap = int(m.group(1)) if m else 0
worst = py_plan({'dice': [6, 6], 'path': P(12), 'tile': {'type': 'key'},
                 'after': {'rev': True, 'path': P(31), 'tile': {'type': 'key'}}})
chk('상한 %dms > 제일 긴 연출 %dms (2개 · 12칸 · 열쇠 → 31칸 역주행 → 열쇠)' % (cap, worst['gate']),
    cap > worst['gate'], (cap, worst))
chk('상한 안에서만 참는다 (묵은 값이 노래를 붙잡지 않게)', 'if (left <= 0 || left > DG_HOLD_CAP) return 0;' in OV)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
