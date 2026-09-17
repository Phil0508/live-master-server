# -*- coding: utf-8 -*-
"""💥 한 방 최고 후원 — 서버가 제대로 기록하는가.

왜 만들었나
  대표님이 XL 방송의 '한 방 최고 후원' 을 보고 우리도 만들자고 했다(2026-09-18).
  이번 방송에서 한 번에 가장 크게 보낸 후원을 방송판에 띄우고, 기록이 깨지면 연출한다.

여기서 지키는 것
  ① 더 큰 후원이 오면 바꾸고, 작거나 **같으면** 먼저 보낸 분이 지킨다
  ② 조종실에서 그 후원을 멤버에게 배정하면 받은 멤버가 붙는다 (다른 후원을 배정하면 안 붙는다)
  ③ 조종실이 상태를 통째로 보내도 기록이 안 덮인다 (SERVER_OWNED)
  ④ 방송을 새로 시작하면 비워진다 (방송 1회분)
  ⑤ 방송판에 위젯이 있고, 첫 그림에서는 '기록 갱신' 을 안 띄운다

⚠️ pausetest 서버(5199)가 필요하다 — runall 이 띄운다.
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
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))


def _find_proj():
    d = HERE
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.exists(os.path.join(d, 'server.py')):
            return d
    return REPO


PROJ = _find_proj()
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


def best():
    return get().get('best_single') or {}


def donate(name, amount):
    tx = 'besttest_%s_%d_%d' % (name, amount, int(time.time() * 1000))
    return post('/api/donation', {'name': name, 'amount': amount, 'message': '한방 시험', 'tx_id': tx})


def pending_of(name, amount):
    for p in (get().get('pending_donations') or []):
        if p.get('name') == name and int(p.get('amount') or 0) == amount:
            return p.get('id')
    return None


print('=' * 74)
print('① 더 큰 후원만 기록을 바꾼다')
print('=' * 74)
# ⚠️ 새로 띄운 연습용 서버는 보관용 표(donation_archive)가 없어 '방송 시작' 이 500 으로 실패한다
#    (boot_sig.py 가 init_db 를 안 부른다 — 이 검사와 무관한 원래 사정). 선수는 직접 넣는다.
_c, _r = post('/api/server/start_broadcast', {'names': ['하율', '서아']})
_st = get()
if not any(b.get('name') == '하율' for b in (_st.get('bjs') or [])):
    _st['bjs'] = [{'name': '하율', 'score': 0, 'contribution': 0}, {'name': '서아', 'score': 0, 'contribution': 0}]
    post('/api/data', _st)
chk('선수가 준비됐다', {'하율', '서아'} <= {b.get('name') for b in (get().get('bjs') or [])})
chk('처음엔 비어 있다', int(best().get('amount') or 0) == 0, best())

donate('별빛요정', 30000)
b1 = best()
chk('첫 후원이 기록이 된다', b1.get('name') == '별빛요정' and int(b1.get('amount') or 0) == 30000, b1)
chk('받은 멤버는 아직 비어 있다', not b1.get('member'), b1.get('member'))
chk('언제 기록됐는지 적는다 (방송판 연출 기준)', int(b1.get('at') or 0) > 0)

time.sleep(0.02)
donate('솜사탕', 10000)
chk('작은 후원은 기록을 안 바꾼다', best().get('name') == '별빛요정')

time.sleep(0.02)
donate('밤하늘', 30000)
b2 = best()
chk('같은 금액이면 먼저 보낸 분이 지킨다', b2.get('name') == '별빛요정' and b2.get('at') == b1.get('at'), b2)

time.sleep(0.02)
donate('딸기우유', 50000)
b3 = best()
chk('더 큰 후원이 오면 바뀐다', b3.get('name') == '딸기우유' and int(b3.get('amount') or 0) == 50000, b3)
chk('바뀌면 기록 시각도 바뀐다 (방송판이 이걸 보고 연출한다)', b3.get('at') != b1.get('at'))

print()
print('=' * 74)
print('② 배정하면 받은 멤버가 붙는다')
print('=' * 74)
pid_small = pending_of('솜사탕', 10000)
code, res = post('/api/score/add', {'scope': 'rank', 'name': '서아', 'delta': 1, 'pending_id': pid_small})
chk('다른 후원을 배정하면 안 붙는다', code == 200 and not best().get('member'), (code, res, pid_small, best().get('member')))

pid_best = pending_of('딸기우유', 50000)
chk('기록된 후원이 대기함에 있다', bool(pid_best) and pid_best == best().get('id'), (pid_best, best().get('id')))
code, res = post('/api/score/add', {'scope': 'rank', 'name': '하율', 'delta': 5, 'pending_id': pid_best})
chk('기록된 후원을 배정하면 받은 멤버가 붙는다', code == 200 and best().get('member') == '하율', (code, res, best()))
chk('배정해도 금액·보낸 분은 그대로', best().get('name') == '딸기우유' and int(best().get('amount') or 0) == 50000)

print()
print('=' * 74)
print('③ 조종실이 통째로 보내도 안 덮인다')
print('=' * 74)
st = get()
st['best_single'] = {'name': '가짜', 'amount': 999999999, 'at': 1, 'id': 'x', 'member': '가짜'}
post('/api/data', st)
chk('상태를 통째로 보내도 기록이 그대로다', best().get('name') == '딸기우유', best())
post('/api/settings/patch', {'best_single': {'name': '가짜', 'amount': 1}})
chk('설정 패치로도 못 바꾼다', best().get('name') == '딸기우유', best())

print()
print('=' * 74)
print('④ 방송 1회분이다')
print('=' * 74)
_c, _r = post('/api/server/start_broadcast', {'names': ['하율', '서아']})
if _c == 200:
    chk('방송을 새로 시작하면 비워진다', int(best().get('amount') or 0) == 0 and not best().get('name'), best())
else:
    # 연습용 서버에서 방송 시작이 안 되면 — 비우는 줄이 방송 시작·종료가 부르는 곳에 있는지 본다
    _SV = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8').read()
    _rs = _SV.split('def reset_session_keys(')[1].split('\ndef ')[0]
    chk('방송을 새로 시작하면 비워진다 (reset_session_keys 에 있다)',
        "state['best_single'] = {\"name\": \"\", \"amount\": 0" in _rs, (_c, _r))

print()
print('=' * 74)
print('⑤ 방송판 · 편집기 · 조종실')
print('=' * 74)
rd = lambda f: io.open(os.path.join(PROJ, f), encoding='utf-8', errors='replace').read()
OV, AD, CTL = rd('overlay.html'), rd('admin.html'), rd('controller.html')
chk('방송판에 위젯이 있다', 'id="best-container"' in OV and 'function renderBest(' in OV)
chk('편집기로 옮길 수 있다 (LAY_IDS)', re.search(r"const LAY_IDS = \[[^\]]*'best'", OV, re.S) is not None)
chk('편집기에 손잡이와 이름표가 있다', 'id="best" data-id="best"' in AD and "'best': '💥 한 방 최고 후원'" in AD)
chk('조종실에 켜기 스위치가 있다', "toggleOption('best_enabled')" in CTL and "setChk('chk-best'" in CTL)
# ⚠️ 방송판을 처음 열 때 '기록 갱신' 이 뜨면 OBS 를 켤 때마다 가짜 연출이 나간다
chk('첫 그림에서는 기록 갱신을 안 띄운다', 'bestSeenAt !== null && at && at !== bestSeenAt' in OV)
chk('게임판이 뜨면 비킨다', 'body.game-on #best-container' in OV)
chk('자릿수가 늘면 금액 글씨를 줄인다 (메달 밖으로 안 나가게)', '--best-amt-size' in OV)
chk('테마 옷을 입는다', '.donation-popup-content, .best-board)' in OV and '.best-head) {' in OV)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
