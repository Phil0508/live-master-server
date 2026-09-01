# -*- coding: utf-8 -*-
"""🧩 배치(위젯 자리·크기)가 방송판까지 닿는가.

왜 만들었나
  2026-08-31 에 방송판이 위젯 **18개 전부** 의 자리·크기를 배치 파일에서 읽게 바꿨다.
  그 전에는 넷(popup·takeover·karaoke·acct_video)만 읽었고, 나머지는 자리를 HTML 에
  못 박아 편집기에서 끌어도 방송이 안 들었다.

  전부 읽게 되면서 새 위험이 생겼다.
    · 배치 파일 하나가 방송 화면 전체를 옮길 수 있다
    · 저장소에 있던 옛 파일에는 게이지 y=1598(폰에서 안 보이는 구역),
      엑셀판 362,178(옛 크기 기준) 이 남아 있었다 — 그대로 읽으면 방송이 되돌아간다
    · 아무나 배치를 바꾸면 방송을 망칠 수 있다

여기서 지키는 것
  ① 인증 없이는 배치를 못 바꾼다
  ② 저장하면 SSE 로 즉시 퍼진다 (오버레이가 새로고침 없이 따라온다)
  ③ 새로 붙는 창에도 처음에 배치를 실어 보낸다 (OBS 새로고침 복구)
  ④ 방송판이 판 번호(__v)를 보고 옛 파일을 무시한다

⚠️ 브라우저에서 실제로 화면이 옮겨지는지까지는 여기서 못 본다. 그건 2026-08-31 에
   손으로 확인했다 — 엑셀판을 (120,200) 배율 0.8 로 저장하니 오버레이가 그대로 섰고,
   새로고침 뒤에도 유지됐다.
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
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = r'C:\Users\Administrator\Desktop\새로다시시작'


def _find_proj():
    d = HERE
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.exists(os.path.join(d, 'overlay.html')):
            return d
    return REPO


PROJ = _find_proj()
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


def req(path, obj=None, authed=True, method='POST'):
    hdr = dict(H) if authed else {'Content-Type': 'application/json'}
    r = urllib.request.Request(B + path, json.dumps(obj or {}).encode() if obj is not None else None,
                               hdr, method=method)
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


print('=' * 74)
print('① 아무나 배치를 바꿀 수 없는가')
print('=' * 74)
"""⚠️ 배치 하나로 방송 화면 전체가 옮겨진다. 인증이 빠지면 그게 곧 방송 사고다."""
code, _ = req('/api/layout', {'__v': 2, 'ranking': {'x_px': 0, 'y_px': 0, 'scale': 1}}, authed=False)
chk('인증 없이 저장하면 막힌다', code in (401, 403), 'HTTP %d' % code)

print()
print('=' * 74)
print('② 저장한 배치가 되읽히는가')
print('=' * 74)
LAY = {'__v': 2, '__free': False,
       'ranking': {'x_px': 120, 'y_px': 200, 'scale': 0.8},
       'account': {'x_px': 300, 'y_px': 400, 'scale': 1.0}}
code, _ = req('/api/layout', LAY)
chk('인증하면 저장된다', code == 200, 'HTTP %d' % code)
code, got = req('/api/layout', None, method='GET')
chk('저장한 그대로 돌아온다', got.get('ranking') == LAY['ranking'], got.get('ranking'))
chk('판 번호가 남는다 (없으면 방송판이 통째로 무시한다)', got.get('__v') == 2, got.get('__v'))

print()
print('=' * 74)
print('③ 방송판이 배치를 어떻게 다루는가')
print('=' * 74)
ov = io.open(os.path.join(PROJ, 'overlay.html'), 'rb').read().replace(b'\x00', b'').decode('utf-8')
srv = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8', errors='replace').read()
# ⚠️ 새로 붙는 창(OBS 새로고침)에도 처음에 배치를 실어 보내야 자리가 복구된다
chk('새로 붙는 창에 배치를 실어 보낸다 (OBS 새로고침 복구)',
    "event: layout" in srv and 'LAYOUT_FILE' in srv)
chk('저장하면 붙어 있는 모두에게 퍼진다', "broadcast_event('layout'" in srv)
# ⚠️ 옛 파일에는 게이지 y=1598 같은 값이 남아 있었다. 판 번호로 막는다.
chk('판 번호가 2 미만이면 통째로 무시한다', "(ly.__v || 0) >= 2" in ov)
chk('무시할 때 조용히 넘어가지 않고 알린다', '옛 배치 파일이라 무시합니다' in ov)
# ⚠️ 배치에 없는 위젯은 HTML 에 적힌 기본 자리에 서야 한다. 안 그러면 손대기 전부터 흐트러진다
chk('배치에 없으면 기본 자리를 그대로 둔다', 'if (!el || !coord) return;' in ov)
mm = __import__('re').search(r'const LAY_IDS = \[([\s\S]*?)\];', ov)
n = len(__import__('re').findall(r"'[\w-]+'", mm.group(1))) if mm else 0
chk('열여덟 개를 다 읽는다', n == 18, '%d개' % n)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
