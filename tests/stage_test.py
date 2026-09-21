# -*- coding: utf-8 -*-
"""🎬 방송 시작·끝 화면 — 서버가 제대로 받고, 방송판이 제자리에서 그리는가.

왜 만들었나
  대표님이 고른 것(2026-09-18): "핀볼이랑 글꼴 시작끝화면 자리 연출 테마별연출 한방 후원".
  방송 들어가기 전 '곧 시작합니다 + 카운트다운', 끝날 때 '오늘도 고마워요 + 오늘의 기록' 을
  방송판 전체에 깐다.

여기서 지키는 것
  ① /api/screen 이 값을 다듬어 받는다 (분 0~180 · 문구 40자 · 이름 10명 · 모르는 모드는 400)
  ② 조종실이 상태를 통째로 보내도, 설정 패치로도 안 바뀐다 (SERVER_OWNED · PATCH_DENY)
  ③ 끝 화면 기록 — 방송 중이면 지금 상태로 매번 만든다(stage_live). 후원 순위판과 같은 규칙
     (익명 빼기 · 금액 순) · 응답 전용이라 되돌려 보내도 상태에 눌러앉지 않는다
  ④ 방송 종료가 지우기 전에 기록을 떠 두고, 방송 시작은 지난 끝 화면을 내린다
  ⑤ 방송판 · 조종실 — 방송 꺼짐 return 앞에서 그리고, 알림보다 아래 · 위젯판은 내린다
  ⑥ 방송 시작·종료의 '남길 설정' SQL 물음표를 손으로 세지 않는다 (500 으로 죽을 뻔했다)

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
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:140]) if detail else ''))


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


def ss():
    return get().get('stage_screen') or {}


def donate(name, amount):
    tx = 'stagetest_%s_%d_%d' % (name, amount, int(time.time() * 1000))
    return post('/api/donation', {'name': name, 'amount': amount, 'message': '끝 화면 시험', 'tx_id': tx})


rd = lambda f: io.open(os.path.join(PROJ, f), encoding='utf-8', errors='replace').read()
SV, OV, CTL = rd('server.py'), rd('overlay.html'), rd('controller.html')

print('=' * 74)
print('① /api/screen 이 값을 다듬어 받는다')
print('=' * 74)
chk('처음엔 꺼져 있다', ss().get('mode', 'off') == 'off', ss())
t0 = int(time.time() * 1000)
code, res = post('/api/screen', {'mode': 'start', 'minutes': 5, 'title': '  오늘은   추석 특집!  ',
                                 'names': ['하율', ' 서아 ', '하율', '', None]})
s1 = ss()
chk('시작 전 화면이 켜진다', code == 200 and s1.get('mode') == 'start', (code, res))
chk('카운트다운은 서버 시계로 5분 뒤', abs(int(s1.get('start_at') or 0) - (t0 + 300000)) < 5000, s1.get('start_at'))
chk('문구 공백을 다듬는다', s1.get('title') == '오늘은 추석 특집!', s1.get('title'))
chk('이름은 다듬고 겹친 건 하나로', s1.get('names') == ['하율', '서아'], s1.get('names'))

post('/api/screen', {'mode': 'start', 'minutes': 0, 'title': '가' * 80})
s2 = ss()
chk('0분이면 카운트다운 없이 문구만', int(s2.get('start_at') or 0) == 0, s2.get('start_at'))
chk('문구는 40자까지', len(s2.get('title') or '') == 40, len(s2.get('title') or ''))
post('/api/screen', {'mode': 'start', 'minutes': 9999})
chk('카운트다운은 180분까지', int(ss().get('start_at') or 0) - int(time.time() * 1000) <= 180 * 60000 + 2000)
post('/api/screen', {'mode': 'start', 'minutes': '숫자아님', 'names': '문자열'})
chk('이상한 값이어도 안 죽는다', ss().get('mode') == 'start' and ss().get('names') == [], ss())
code, _ = post('/api/screen', {'mode': 'party'})
chk('모르는 모드는 400', code == 400 and ss().get('mode') == 'start', code)
code, _ = post('/api/screen', {'mode': 'off'})
chk('끄기', code == 200 and ss().get('mode') == 'off')

print()
print('=' * 74)
print('② 조종실이 통째로 보내도 · 설정 패치로도 안 바뀐다')
print('=' * 74)
st = get()
st['stage_screen'] = {'mode': 'end', 'title': '가짜', 'last_snap': {'donors': [{'name': '가짜', 'total': 1}]}}
post('/api/data', st)
chk('상태를 통째로 보내도 그대로다', ss().get('mode') == 'off' and ss().get('title') != '가짜', ss())
post('/api/settings/patch', {'stage_screen': {'mode': 'end'}})
chk('설정 패치로도 못 바꾼다', ss().get('mode') == 'off', ss())

print()
print('=' * 74)
print('③ 끝 화면 기록 — 방송 중이면 지금 상태로')
print('=' * 74)
# (예전엔 연습용 서버가 init_db 를 안 불러 '방송 시작' 이 500 이었다 — 2026-09-21 boot_sig.py 에서 고쳤다)
_c0, _r0 = post('/api/server/start_broadcast', {'names': ['서아', '하율']})
chk('방송 시작이 된다', _c0 == 200, (_c0, _r0))
chk('방송 중이다', get().get('broadcast_active') is True)
donate('별빛요정', 30000)
donate('딸기우유', 50000)
donate('익명', 70000)
donate('솜사탕', 10000)
chk('끝 화면이 안 떠 있으면 기록을 안 싣는다 (매 전송마다 계산하지 않게)', 'stage_live' not in get())

post('/api/screen', {'mode': 'end', 'title': '다음 방송 · 금요일 밤 9시'})
d = get()
live = d.get('stage_live') or {}
names = [r.get('name') for r in (live.get('donors') or [])]
chk('끝 화면이 켜지면 기록을 싣는다', d.get('stage_screen', {}).get('mode') == 'end' and bool(live), list(d.keys())[:3])
chk('후원해 주신 분은 금액 순', names[:3] == ['딸기우유', '별빛요정', '솜사탕'], names)
chk('익명은 순위판처럼 뺀다 (익명 넣기가 꺼져 있으면)', '익명' not in names, names)
chk('한 방 최고가 같이 온다', (live.get('best') or {}).get('amount') in (50000, 70000), live.get('best'))
chk('멤버 순위가 같이 온다', [m.get('name') for m in (live.get('members') or [])][:1] != [], live.get('members'))

donate('늦은밤달', 20000)   # ⚠️ '님' 으로 끝나는 이름은 순위 열쇠에서 '님' 이 떼인다(원래 동작) — 검사를 흔들지 않게 피한다
names2 = [r.get('name') for r in ((get().get('stage_live') or {}).get('donors') or [])]
chk('끝 화면을 띄운 뒤 들어온 후원도 나온다', '늦은밤달' in names2, names2)

post('/api/settings/patch', {'donor_rank_amount': False})
live3 = get().get('stage_live') or {}
chk('금액 보이기를 끄면 금액을 안 싣는다',
    live3.get('show_amount') is False and all(r.get('total') is None for r in (live3.get('donors') or [])), live3.get('donors'))
post('/api/settings/patch', {'donor_rank_amount': True})

st = get()
chk('받은 상태에 기록이 실려 있다 (되돌려 보내기 준비)', 'stage_live' in st)
post('/api/data', st)
post('/api/screen', {'mode': 'off'})
d_off = get()
chk('기록은 응답 전용 — 되돌려 보내도 상태에 눌러앉지 않는다', 'stage_live' not in d_off, [k for k in d_off if 'stage' in k])

print()
print('=' * 74)
print('④ 방송 종료는 기록을 떠 두고, 방송 시작은 지난 끝 화면을 내린다')
print('=' * 74)
_c, _r = post('/api/server/end_broadcast', {})
chk('방송 종료가 된다', _c == 200, (_c, _r))
snap = ss().get('last_snap') or {}
chk('방송을 끝내도 오늘 기록이 남는다', any(r.get('name') == '딸기우유' for r in (snap.get('donors') or [])), snap)
post('/api/screen', {'mode': 'end'})
d = get()
chk('끝낸 뒤 끝 화면은 떠 둔 기록을 쓴다 (stage_live 없음)', 'stage_live' not in d
    and (d.get('stage_screen') or {}).get('last_snap'))
# 방송 시작 — 지난 끝 화면은 내리고, 시작 전 화면은 그대로 둔다 (진짜로 시작해 본다)
post('/api/server/start_broadcast', {'names': ['서아', '하율']})
chk('방송 시작은 지난 끝 화면을 내린다', ss().get('mode') == 'off', ss().get('mode'))
post('/api/screen', {'mode': 'start', 'minutes': 5})
post('/api/server/start_broadcast', {'names': ['서아', '하율']})
chk('방송 시작은 시작 전 화면을 그대로 둔다 (선수 먼저 등록하고 기다리는 흐름)', ss().get('mode') == 'start', ss().get('mode'))
post('/api/screen', {'mode': 'off'})
_rs = SV.split('def reset_session_keys(')[1].split('\ndef ')[0]
chk('방송 1회분 초기화가 끝 화면 기록을 안 지운다 (종료 뒤에 띄우는 것이다)', 'stage_screen' not in _rs)

print()
print('=' * 74)
print('⑤ 방송판 · 조종실')
print('=' * 74)
_hd = OV.split('function handleData(d) {')[1]
chk('방송 꺼짐 return 앞에서 그린다 (방송 시작 전에 띄우는 화면이다)',
    0 <= _hd.find('renderStageScreen(d);') < _hd.find('if (!isActive) {'))
_z = re.search(r'#stage-screen \{[^}]*z-index:\s*(\d+)', OV)
chk('후원 알림·시그니처·고액 영상보다 아래에 깐다', _z is not None and int(_z.group(1)) < 88000, _z and _z.group(1))
chk('위젯판·게임판은 내린다 (z-index 가 더 높아 위로 비친다)',
    all(('body.stage-on ' + s) in OV for s in ('#ui-layer', '#headrow', '#siggame-container', '#dicegame-container', '#pinball-container')))
chk('카운트다운은 서버 시계로 센다', 'ssStartAt - (Date.now() + serverTimeOffset)' in OV)
chk('이름·문구는 글자로만 넣는다 (태그 주입 막기)', 'ssEsc(ss.title)' in OV and 'ssEsc(n)' in OV and 'ssEsc(r.name)' in OV)
chk('테마 액자·모서리 장식을 입는다', '.best-board, .ss-card) {' in OV and '.best-board, .ss-card)::after {' in OV)
chk('파스텔 밝은 속에서도 읽히게 잉크 토큰으로 칠한다', ':is(.ss-big, .ss-chip, .ss-donor b) {' in OV)
chk('조종실 두 군데(방송 준비 · 방송 중)에 칸이 있다',
    'id="ss-min-setup"' in CTL and 'id="ss-min-live"' in CTL and "stageScreen('end', 'live')" in CTL)
_rn = CTL.split('try { renderPending(); } catch(e) {}')[1][:200]
chk('입력칸을 누르고 있어도 켜짐 표시는 맞춘다', 'renderStageStatus()' in _rn)

print()
print('=' * 74)
print('⑥ 방송 시작·종료 SQL')
print('=' * 74)
chk('남길 설정 칸 물음표를 손으로 세지 않는다', 'NOT IN (?, ?' not in SV
    and SV.count("', '.join('?' * len(BROADCAST_KEEP_KEYS))") == 2)
_keep = re.search(r'BROADCAST_KEEP_KEYS = \(([^)]*)\)', SV)
chk('테마·테마 연출은 방송을 끝내도 남는다', _keep is not None and "'theme'" in _keep.group(1) and "'theme_fx_enabled'" in _keep.group(1))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
