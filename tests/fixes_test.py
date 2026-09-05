# -*- coding: utf-8 -*-
"""🩹 2026-09-05 전체 점검에서 나온 문제들 — 고친 것이 되돌아가지 않게.

사장님 말
  "문제점들 싹 파악해서 전체적으로 ui랑 컨트롤러랑 잘 되나 테스트해봐"
  → 새 DB 로 방송 시작부터 종료까지 밟아 나온 것들.

여기서 지키는 것
  ① 대기함에서 배정해도 후원 팝업·1등 탈환이 방송에 나간다
     (수동 '+ 점수' 길만 popup/takeover 를 보내고 있었다 — 모든 후원이 대기함을
      거치니 스위치를 켜놔도 사실상 안 나왔다)
  ② 5분 주기 브라우저 백업은 방송 중에만 쓴다
     (종료 뒤에도 빈 상태를 저장해, 종료 때 지운 백업이 되살아나 '서버 초기화 감지 — 복구?'
      모달이 떴다. 실제 재현: 종료 18:32 → 18:34:28 에 플레이어 0명 백업)
  ③ 방송을 시작·종료하면 게임판 진행 상태가 걷힌다 — 칸 배치·고른 시그니처는 남긴다
     (종료 뒤 오버레이에 CLEAR 카드판과 주사위 말이 그대로 남아 있었다)
  ④ 게임판이 떠 있는 동안 후원 순위판을 내린다 (주사위판 오른쏙 열을 덮었다)
  ⑤ 종료 성공 뒤 '지난 방송 후원내역' 캐시를 비운다 (방금 보관된 회차가 "없다"고 보였다)
  ⑥ AI 배정 제안은 같은 후원을 10분 동안 기억한다 (폰·PC 가 각각 물어 NIM 이 두 번 갔다)

③·⑥ 은 살아 있는 서버(5199)로 실제로 밟는다. 나머지는 코드를 읽어서 본다.
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
PROJ = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
rd = lambda f: io.open(os.path.join(PROJ, f), encoding='utf-8', errors='replace').read()
OV, CT, MB, SV = rd('overlay.html'), rd('controller.html'), rd('mobile.html'), rd('server.py')

OK, BAD = [], []


def chk(n, c, d=''):
    (OK if c else BAD).append(n)
    print(('  [OK] ' if c else '  [!!] ') + n + (('  -- ' + str(d)[:110]) if d else ''))


def post(p, d=None):
    r = urllib.request.Request(B + p, data=json.dumps(d or {}).encode(), headers=H, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


def get():
    r = urllib.request.Request(B + '/api/data', headers={'Authorization': H['Authorization']})
    return json.loads(urllib.request.urlopen(r, timeout=25).read().decode())


print('=' * 74)
print('① 대기함 배정에도 팝업·1등 탈환 신호가 실린다')
print('=' * 74)
# ⚠️ 호출 인자 전체를 본다. 예전 정규식은 첫 '}' 나 pending_id 에서 잘라서, popup 이
#    pending_id 뒤에 있으면 못 보고 실패했다(코드는 맞는데 검사가 틀렸다).
def _calls(src, fn):
    out = []
    for m in re.finditer(re.escape(fn) + r'\(\{', src):
        win = src[m.start():m.start() + 700]
        if 'pending_id' in win.split(');')[0]:
            out.append(win.split(');')[0])
    return out
pend_calls = _calls(CT, 'addScoreAPI')
chk('조종실 배정 호출이 둘이다(단건·나눠주기)', len(pend_calls) == 2, len(pend_calls))
chk('둘 다 popup·takeover 를 보낸다',
    bool(pend_calls) and all('popup: true' in c and 'takeover: true' in c for c in pend_calls))
mb_calls = _calls(MB, 'addScore')
chk('폰 배정 호출도 둘이다', len(mb_calls) == 2, len(mb_calls))
chk('폰도 둘 다 보낸다',
    bool(mb_calls) and all('popup:true' in c and 'takeover:true' in c for c in mb_calls))
# 서버는 body 값을 그대로 따른다 — 안 보내면 False
chk('서버는 보낸 값을 따른다', "want_popup = bool(body.get('popup', False))" in SV
    and "want_takeover = bool(body.get('takeover', False))" in SV)

print()
print('=' * 74)
print('② 5분 주기 백업은 방송 중에만')
print('=' * 74)
fn = CT.split('function performAutoPeriodicBackup(')[1].split('\n        }\n')[0]
chk('방송 중이 아니면 쓰지 않는다', 'if (!gd.broadcast_active)' in fn and 'return;' in fn)
chk('그 확인이 저장보다 앞에 있다',
    fn.index('if (!gd.broadcast_active)') < fn.index("setItem('active_broadcast_backup'"))
chk('종료 성공 시 백업을 지우는 줄은 그대로',
    "localStorage.removeItem('active_broadcast_backup');" in CT.split('async function endBroadcast()')[1][:1500])

print()
print('=' * 74)
print('③ 시작·종료가 게임판 진행 상태를 걷는다 (살아 있는 서버)')
print('=' * 74)
rs = SV.split('def reset_session_keys(')[1].split('\ndef ')[0]
chk('reset_session_keys 가 주사위 보이기·말·바퀴를 걷는다',
    "_dg.update({'enabled': False, 'pos': 0, 'laps': 0, 'action': {}})" in rs)
chk('시그뒤집기 카드·타이머를 걷는다', "'cards': []" in rs and "'timer': {'status': 'STOPPED'" in rs)
chk('칸 배치(tiles)와 고른 시그니처(picks)는 안 건드린다',
    "'tiles'" not in rs and "'picks'" not in rs)

# 실제로: 방송 시작 → 판 깔고 켜기 → 주사위 굴려 말 이동 → 시그 딜 → 종료 → 전부 걷혔나
post('/api/server/start_broadcast', {'names': ['가', '나']})
post('/api/dicegame/setup', {'cols': 7, 'rows': 5, 'dice': 1, 'roll_price': 20000})
post('/api/dicegame/enable', {'on': True})
post('/api/dicegame/move', {'pos': 4})
post('/api/siggame/picks', {'picks': [10001, 10002, 10003]})
post('/api/siggame/deal', {'minutes': 10, 'target': 3})
g0 = get()
chk('종료 전: 주사위 켜짐·말 4번·카드 3장',
    g0['dicegame'].get('enabled') is True and g0['dicegame'].get('pos') == 4
    and len(g0['siggame'].get('cards') or []) == 3,
    (g0['dicegame'].get('enabled'), g0['dicegame'].get('pos'), len(g0['siggame'].get('cards') or [])))
post('/api/server/end_broadcast', {})
time.sleep(1)
g1 = get()
chk('종료 뒤: 주사위 꺼짐·말 출발로', g1['dicegame'].get('enabled') is False and g1['dicegame'].get('pos') == 0,
    (g1['dicegame'].get('enabled'), g1['dicegame'].get('pos')))
chk('종료 뒤: 칸 배치는 남는다 (다음 주에 다시 안 깔게)', len(g1['dicegame'].get('tiles') or []) == 20,
    len(g1['dicegame'].get('tiles') or []))
chk('종료 뒤: 시그 카드 걷힘·판 꺼짐', not g1['siggame'].get('cards') and g1['siggame'].get('enabled') is False,
    (len(g1['siggame'].get('cards') or []), g1['siggame'].get('enabled')))
chk('종료 뒤: 고른 시그니처는 남는다', len(g1['siggame'].get('picks') or []) == 3,
    len(g1['siggame'].get('picks') or []))
# 시작 경로도 같은 함수를 탄다
post('/api/dicegame/enable', {'on': True})
post('/api/server/start_broadcast', {'names': ['가', '나']})
g2 = get()
chk('시작해도 주사위 보이기는 꺼진 채로', g2['dicegame'].get('enabled') is False, g2['dicegame'].get('enabled'))

print()
print('=' * 74)
print('④ 게임판이 떠 있으면 후원 순위판을 내린다')
print('=' * 74)
chk('규칙이 있다', 'body.game-on #donor-rank-container { opacity: 0 !important' in OV)
chk('게이지 딱지 규칙 옆에 있다 (같은 스위치)',
    abs(OV.index('body.game-on #donor-rank-container') - OV.index('body.game-on .goal-rail-tip')) < 400)

print()
print('=' * 74)
print('⑤ 종료 성공 뒤 보관 패널 캐시를 비운다')
print('=' * 74)
eb = CT.split('async function endBroadcast()')[1].split('\n        }\n')[0]
chk('_archLoaded 를 false 로 돌린다', "_archLoaded = false" in eb)
chk('성공 분기 안에 있다', eb.index("if (data.status === 'success')") < eb.index('_archLoaded = false'))
chk('캐시 가드는 여전히 있다 (강제 새로고침만 다시 읽음)', 'if (_archLoaded && !force) return;' in CT)

print()
print('=' * 74)
print('⑥ AI 배정 제안은 같은 후원을 10분 기억한다 (살아 있는 서버)')
print('=' * 74)
chk('캐시가 있다', '_SUGGEST_CACHE = {}' in SV)
sug = SV.split('def api_audit_suggest():')[1].split('\n@app.route')[0]
chk('키는 이름·금액·메시지·플레이어', "_ck = (name, int(amount or 0), message, tuple(players or []))" in sug)
chk('10분 안이면 다시 안 묻는다', '_now - _hit[0] < 600' in sug)
chk('무한히 커지지 않는다', 'len(_SUGGEST_CACHE) > 500' in sug)
body = {'name': '홍길동', 'amount': 15000, 'message': '플레이어1 힘내', 'players': ['가', '나']}
c1, r1 = post('/api/audit/suggest', body)
c2, r2 = post('/api/audit/suggest', body)
chk('첫 답은 캐시가 아니다', c1 == 200 and not r1.get('cached'), (c1, r1.get('cached')))
chk('같은 것을 다시 물으면 캐시에서 온다', c2 == 200 and r2.get('cached') is True, (c2, r2.get('cached')))
chk('내용은 같다', r1.get('target') == r2.get('target') and r1.get('confidence') == r2.get('confidence'))
c3, r3 = post('/api/audit/suggest', dict(body, message='다른 말'))
chk('메시지가 다르면 새로 묻는다', c3 == 200 and not r3.get('cached'), (c3, r3.get('cached')))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
