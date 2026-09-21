# -*- coding: utf-8 -*-
"""🔥 지옥탈출 — 서버가 제대로 재는가.

왜 만들었나
  대표님 2026-09-21: 추석 방송 마지막을 퇴근빵 대신 '지옥탈출' 로 한다.
  1등 50만 · 2등 40 · 3등 30 · 4등 20 을 **지옥탈출을 시작한 뒤에** 받아야 탈출, 못 하면 벌칙 룰렛.

여기서 지키는 것
  ① 시작 순간 등수로 목표가 정해진다 (점수 높은 순)
  ② 시작 전 점수는 안 센다 — 시작 뒤 받은 것만
  ③ 목표를 채우면 '탈출 성공' 카드가 한 번만 생긴다 (퇴근빵 카드와 섞이지 않는다)
  ④ 끝내면 그 순간 값으로 굳고, 뒤에 들어온 점수는 판정에 안 들어간다
  ⑤ 조종실이 상태를 통째로 보내도 안 덮인다 · 방송을 새로 시작하면 비워진다
  ⑥ 방송판 · 조종실에 판과 버튼이 있다

⚠️ pausetest 서버(5199)가 필요하다 — runall 이 띄운다.
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
PROJ = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:120]) if detail else ''))


def post(path, obj=None):
    r = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), H)
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=H), timeout=25) as r:
        return json.loads(r.read().decode())


def add(name, pts):
    return post('/api/score/add', {'scope': 'rank', 'name': name, 'delta': pts})


def hell_cards():
    return [d for d in (get().get('pending_donations') or []) if d.get('type') == 'off_work' and d.get('kind') == 'hell']


print('=' * 74)
print('① 시작 순간 등수로 목표')
print('=' * 74)
c, r = post('/api/server/start_broadcast', {'names': ['하율', '서아', '유나', '채원']})
chk('방송 시작', c == 200, (c, r))
chk('처음엔 꺼져 있다', not (get().get('hell') or {}).get('on'))
for n, p in (('서아', 30), ('하율', 20), ('채원', 10), ('유나', 5)):
    add(n, p)
c, r = post('/api/hell/start', {'targets': [50, 40, 30, 20]})
h = (r or {}).get('hell') or {}
chk('시작된다', c == 200 and h.get('on') and not h.get('ended'), (c, r))
chk('1등 서아 50 · 2등 하율 40 · 3등 채원 30 · 4등 유나 20',
    h.get('goals') == {'서아': 50, '하율': 40, '채원': 30, '유나': 20}, h.get('goals'))
chk('시작 순간 점수를 적어 둔다', h.get('base') == {'서아': 30, '하율': 20, '채원': 10, '유나': 5}, h.get('base'))

print()
print('=' * 74)
print('② 시작 뒤 받은 것만 센다 · ③ 탈출 카드')
print('=' * 74)
add('유나', 19)
chk('유나 19만 — 아직 못 채웠다', not hell_cards())
chk('유나는 시작 뒤 19점', get()['bjs'] and next(b for b in get()['bjs'] if b['name'] == '유나')['score'] - 5 == 19)
post('/api/data', dict(get()))   # 조종실이 상태를 통째로 밀어도
chk('통째로 보내도 지옥탈출 기록이 그대로다', (get().get('hell') or {}).get('base', {}).get('유나') == 5)
st = get(); st['hell'] = {'on': False}
post('/api/data', st)
chk('조종실 저장으로 지옥탈출을 끌 수 없다', (get().get('hell') or {}).get('on') is True)
c, r = post('/api/settings/patch', {'hell': {'on': False}})
chk('설정 패치로도 못 바꾼다', (get().get('hell') or {}).get('on') is True)

# 탈출 카드 길 — 새로 시작하면 **그 순간 등수로 다시** 정한다: 서아 30 · 유나 24 · 하율 20 · 채원 10
c, r = post('/api/hell/start', {'targets': [50, 40, 30, 20]})
chk('다시 시작하면 지금 등수로 다시 정한다 (유나 2등 → 40)', (r.get('hell') or {}).get('goals', {}).get('유나') == 40, r.get('hell'))
add('유나', 40)
c, r = post('/api/offwork/pending', {'name': '유나', 'kind': 'hell'})
chk('탈출 카드가 생긴다', c == 200 and len(hell_cards()) == 1, (c, r, hell_cards()))
c, r = post('/api/offwork/pending', {'name': '유나', 'kind': 'hell'})
chk('두 번 불러도 한 장뿐', len(hell_cards()) == 1, len(hell_cards()))
chk("'탈출했다' 로 적힌다", '유나' in ((get().get('hell') or {}).get('escaped') or []))
home = [d for d in (get().get('pending_donations') or []) if d.get('type') == 'off_work' and (d.get('kind') or 'home') == 'home']
chk('퇴근빵 카드와 섞이지 않는다', not home, home)
c, r = post('/api/offwork/pending', {'name': '없는사람', 'kind': 'hell'})
chk('명단에 없는 이름은 거절', c == 409, c)

print()
print('=' * 74)
print('④ 끝내면 굳는다')
print('=' * 74)
add('서아', 50)
c, r = post('/api/hell/end')
chk('끝난다', c == 200 and (r.get('hell') or {}).get('ended'), (c, r))
chk('벌칙 = 하율 · 채원 (서아 50 · 유나 40 은 탈출)', sorted(r.get('failed') or []) == ['채원', '하율'], r.get('failed'))
chk('받은 값이 굳는다', (r.get('hell') or {}).get('final') == {'서아': 50, '하율': 0, '채원': 0, '유나': 40},
    (r.get('hell') or {}).get('final'))
add('하율', 99)
chk('끝난 뒤 들어온 점수는 판정에 안 들어간다', (get().get('hell') or {}).get('final', {}).get('하율') == 0)
c, r = post('/api/offwork/pending', {'name': '하율', 'kind': 'hell'})
chk('끝난 뒤에는 탈출 카드를 안 만든다', c == 409, c)
c, r = post('/api/hell/goal', {'name': '채원', 'goal': 0})
chk('목표를 고칠 수 있다', c == 200 and (r.get('hell') or {}).get('goals', {}).get('채원') == 0, (c, r))
c, r = post('/api/hell/off')
chk('화면에서 내린다', c == 200 and not (r.get('hell') or {}).get('on'))

print()
print('=' * 74)
print('⑤ 방송 1회분')
print('=' * 74)
post('/api/hell/start', {})
post('/api/server/start_broadcast', {'names': ['하율', '서아']})
h = get().get('hell') or {}
chk('방송을 새로 시작하면 비워진다', not h.get('on') and not h.get('goals') and not h.get('base'), h)

print()
print('=' * 74)
print('⑥ 방송판 · 조종실')
print('=' * 74)
rd = lambda f: io.open(os.path.join(PROJ, f), encoding='utf-8', errors='replace').read()
OV, CTL = rd('overlay.html'), rd('controller.html')
chk('방송판이 퇴근빵 판을 빌려 불색으로 그린다', "raceEl.classList.toggle('hell', !!hell);" in OV and '#home-race-container.hell {' in OV)
chk('방송판은 시작 뒤 받은 점수로 막대를 채운다', 'hellCur(b)' in OV and "(hell.base || {})[b.name]" in OV)
chk('탈출 팝업 문구', "kind === 'hell'" in OV and '지옥 탈출!' in OV)
chk('조종실에 시작 · 끝 · 벌칙 룰렛 버튼', all(k in CTL for k in ('onclick="hellStart()"', 'onclick="hellEnd()"', 'hellRoulette(')))
chk('벌칙 룰렛은 이름을 달고 벌칙 목록으로 띄운다',
    "gd.roulette.for_name = n;" in CTL and "gd.roulette.item_source = 'custom';" in CTL)
chk('룰렛 제목에 이름이 붙는다', '벌칙 룰렛' in OV and 'rState.for_name' in OV)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
