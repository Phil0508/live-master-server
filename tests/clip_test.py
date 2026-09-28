# -*- coding: utf-8 -*-
"""✂️ 쇼츠 클립 — 명장면마다 OBS 가 '방금 90초' 를 저장하게 하는 길이 살아 있는가.

왜 만들었나
  대표님 2026-09-28: "9시간 방송을 토대로 쇼츠를 몇 개 만들 수 있게". 녹화본을 나중에 뒤지지 않도록
  OBS 리플레이 버퍼(블랙박스)를 쓴다. OBS 는 다른 컴퓨터(회사)라 조종실이 직접 못 붙고,
  OBS 안의 방송판(브라우저 소스)이 window.obsstudio.saveReplayBuffer() 로 대신 말한다.

여기서 지키는 것
  ① [✂ 클립] → 목록에 적히고 방송판에 'clip' 신호가 간다
  ② 방송판 상태 알림(/api/clip/hello)은 로그인 없이 받지만 상태·DB 는 안 바뀐다
  ③ 권한 낮은 방송판이 권한 있는 쪽 상태를 덮지 못한다
  ④ 기준 금액 이상 시그 · 올클리어는 목록에 '자동' 으로 적힌다, 끄면 안 적힌다
  ⑤ 조종실이 상태를 통째로 보내도 클립 목록이 안 지워진다
  ⑥ 방송판·조종실에 필요한 코드가 있다

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


def req(path, obj=None, method=None, auth=True):
    data = json.dumps(obj).encode() if obj is not None else None
    hd = H if auth else {'Content-Type': 'application/json'}
    r = urllib.request.Request(B + path, data, hd, method=method or ('POST' if data is not None else 'GET'))
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def clip():
    return req('/api/clip')[1]


print('=' * 72)
print('① [✂ 클립] — 목록에 적힌다')
print('=' * 72)
req('/api/clip/settings', {'clear': True, 'auto': True, 'auto_min': 100000})
st, d = req('/api/clip', {'label': '웃긴 장면'})
chk('누르면 받는다', st == 200 and d.get('id'), (st, d))
log = clip().get('clip', {}).get('log', [])
chk('목록에 한 줄', len(log) == 1 and log[0]['label'] == '웃긴 장면' and log[0]['kind'] == 'manual', log)
st, _ = req('/api/clip', {}, auth=False)
chk('로그인 없이는 못 누른다', st in (401, 403, 302), st)

print()
print('=' * 72)
print('② 방송판 상태 알림 — 로그인 없이 받되 메모리에만')
print('=' * 72)
before = req('/api/data')[1]
st, _ = req('/api/clip/hello', {'level': 4, 'rb': True}, auth=False)
chk('방송판(무인증)이 알릴 수 있다', st == 200, st)
o = clip().get('obs', {})
chk('조종실에 연결됨으로 보인다', o.get('alive') and o.get('level') == 4 and o.get('rb') is True, o)
after = req('/api/data')[1]
chk('상태(clip 목록)는 안 바뀐다', (before.get('clip') or {}).get('log') == (after.get('clip') or {}).get('log'))
st, _ = req('/api/clip/hello', {'level': 1, 'rb': False}, auth=False)
o = clip().get('obs', {})
chk('③ 권한 낮은 방송판이 덮지 못한다', o.get('level') == 4 and o.get('rb') is True, o)
req('/api/clip/hello', {'level': 4, 'rb': True, 'saved': True}, auth=False)
o = clip().get('obs', {})
chk('저장 알림이 오면 마지막 저장 시각이 생긴다', o.get('saved_ago') is not None and o['saved_ago'] < 5, o)
st, _ = req('/api/clip/hello', {'level': 'x' * 5000, 'err': 'y' * 5000}, auth=False)
o = clip().get('obs', {})
chk('이상한 값은 잘라서 받는다', st == 200 and len(o.get('err') or '') <= 80, o)

print()
print('=' * 72)
print('④ 자동 — 기준 금액 이상 시그 · 올클리어')
print('=' * 72)
req('/api/clip/settings', {'clear': True, 'auto': True, 'auto_min': 100000})
st, sg = req('/api/signatures')
sigs = (sg or {}).get('signatures') or []
if sigs:
    big = max(sigs, key=lambda x: x.get('amount') or 0)
    req('/api/signature/play', {'name': '테스트', 'amount': max(100000, big.get('amount') or 0), 'message': ''})
    log = clip().get('clip', {}).get('log', [])
    chk('큰 시그는 자동으로 적힌다', any(x['kind'] == 'auto' and '테스트' in x['label'] for x in log), log)
    req('/api/clip/settings', {'clear': True, 'auto': False})
    req('/api/signature/play', {'name': '테스트2', 'amount': max(100000, big.get('amount') or 0), 'message': ''})
    log = clip().get('clip', {}).get('log', [])
    chk('자동을 끄면 안 적힌다', not any('테스트2' in x['label'] for x in log), log)
    req('/api/reaction/stop', {})
else:
    print('  (시그니처가 없는 서버 — 큰 시그 자동은 코드로만 본다)')
SRV = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8').read()
chk('시그를 큐에 넣을 때 기준 금액을 본다', "int(amount or 0) >= int(_c['auto_min'])" in SRV)
chk('올클리어도 적는다', "'시그뒤집기 올클리어 (%d장)'" in SRV)

print()
print('=' * 72)
print('⑤ 조종실이 상태를 통째로 보내도 목록이 산다')
print('=' * 72)
req('/api/clip/settings', {'clear': True, 'auto': True, 'auto_min': 100000})
req('/api/clip', {'label': '지켜야 할 순간'})
stale = req('/api/data')[1]
stale['clip'] = {'auto': False, 'auto_min': 0, 'log': []}
req('/api/data', stale)
c = clip().get('clip', {})
chk('통째 저장이 목록을 못 지운다', any(x['label'] == '지켜야 할 순간' for x in c.get('log', [])) and c.get('auto') is True, c)
st, _ = req('/api/settings/patch', {'clip': {'log': []}})
c = clip().get('clip', {})
chk('설정 패치로도 못 지운다', any(x['label'] == '지켜야 할 순간' for x in c.get('log', [])), (st, c))

print()
print('=' * 72)
print('⑥ 방송판 · 조종실 코드')
print('=' * 72)
OV = io.open(os.path.join(PROJ, 'overlay.html'), encoding='utf-8').read()
CTL = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8').read()
chk('방송판이 OBS 에 저장을 시킨다', 'o.saveReplayBuffer()' in OV)
chk('권한(고급 접근 4) 이상일 때만', 'CLIP.level >= 4' in OV)
chk('OBS 밖에서는 아무 일도 안 한다', "function clipObs() { return (window.obsstudio" in OV)
chk('리플레이 버퍼가 꺼져 있으면 켠다', 'o.startReplayBuffer()' in OV)
chk('clip 신호를 받는다', "sseSource.addEventListener('clip'" in OV)
chk('큰 시그는 재생 뒤에 저장', 'clipSave(CLIP_AUTO_WAIT' in OV)
chk('겹치는 순간은 한 번에, 먼 순간은 다음 저장으로', 'CLIP.later = Math.max(CLIP.later, at)' in OV)
chk('조종실 맨 윗줄에 [✂ 클립]', 'id="btn-clip" onclick="clipNow()"' in CTL)
chk('시스템 탭에 쇼츠 클립 칸', 'id="clip-box"' in CTL and 'id="clip-log"' in CTL)
chk('처음 한 번 할 것을 적어 뒀다', '리플레이 버퍼 사용' in CTL and 'OBS에 대한 고급 접근 권한' in CTL)

req('/api/clip/settings', {'clear': True, 'auto': True, 'auto_min': 100000})
print()
print('=' * 72)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 72)
sys.exit(1 if BAD else 0)
