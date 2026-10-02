# -*- coding: utf-8 -*-
"""🏺 모금함 깃발 자리 — 점수판 왼쪽 / 오른쪽 (2026-10-03 대표님 "모금함은 왼쪽 오른쪽 고를 수 있게")

여기서 지키는 것
  ① 오른쪽: 점수판은 그대로, 깃발은 점수판 바로 오른쪽(같은 높이 · 같은 배율)
  ② 왼쪽: 깃발이 점수판이 있던 자리로, 점수판은 깃발 폭만큼 오른쪽으로 비킨다
  ③ 왼쪽 → 오른쪽으로 돌아오면 점수판도 제자리(왕복해도 안 밀린다)
  ④ 이상한 값 · 옛 배치 파일 · 로그인 없이 바꾸기는 거절
  ⑤ 조종실 단추 · 편집기가 바뀐 배치를 받는 길이 있다(편집기가 옛 자리로 되돌려 저장하지 않게)
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:200]) if detail else ''))


def head(s):
    print()
    print('=' * 74)
    print(s)
    print('=' * 74)


def call(method, path, obj=None, auth=True):
    req = urllib.request.Request(B + path, json.dumps(obj).encode() if obj is not None else None,
                                 H if auth else {'Content-Type': 'application/json'}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'err': str(e)}


CT = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
AD = io.open(os.path.join(ROOT, 'admin.html'), encoding='utf-8').read()
LY = io.open(os.path.join(ROOT, 'features', 'layout.py'), encoding='utf-8').read()

head('⑤ 조종실 단추 · 편집기 받기')
chk('조종실 모금함 줄에 [◀ 왼쪽] [오른쪽 ▶]', "fundjarSide('left')" in CT and "fundjarSide('right')" in CT and 'class="fj-side"' in CT)
chk('조종실은 처음 열 때 · 배치가 바뀔 때 깃발 자리를 다시 센다',
    "fundjarSideLoad();   // 🏺" in CT and "addEventListener('layout', function() { fundjarSideLoad(); })" in CT)
_ad = AD[AD.index("adminEs.addEventListener('layout'"):][:1600] if "adminEs.addEventListener('layout'" in AD else ''
chk('편집기는 받은 배치를 위젯에 입힌다(다음 저장 때 옛 자리로 안 되돌린다)', 'layout[el.id] =' in _ad and 'el.style.left' in _ad, len(_ad))
chk('편집기는 끄는 중 · 크기 바꾸는 중에는 손대지 않는다', 'if (isDragging || isResizing) return;' in _ad)
chk('서버 길은 로그인 예외 목록에 없다', "'/api/fundjar/side'" not in io.open(os.path.join(ROOT, 'server.py'), encoding='utf-8').read())
chk('깃발 배율 = 점수판 배율(키가 같게 그렸다 — 878×262 · 108×262)', '_RANK_W, _FLAG_W, _CANVAS_W, _EDGE = 878, 108, 1080, 6' in LY)

c0, ORIG = call('GET', '/api/layout')
chk('지금 배치를 읽어 둔다(끝나고 되돌린다)', c0 == 200 and isinstance(ORIG, dict), c0)
try:
    # 운영 배치와 같은 숫자(2026-10-02 서버에서 읽은 값)
    BASE = {'__v': 2, '__free': True,
            'ranking': {'x_px': 10, 'y_px': 263, 'scale': 0.88},
            'fundjar': {'x_px': 820, 'y_px': 1532, 'scale': 0.687},
            'account': {'x_px': 55, 'y_px': 455, 'scale': 1.512}}
    call('POST', '/api/layout', BASE)

    head('① 오른쪽')
    c, d = call('GET', '/api/fundjar/side')
    chk('처음엔 따로 놓여 있다(free)', c == 200 and d.get('side') == 'free', (c, d))
    c, d = call('POST', '/api/fundjar/side', {'side': 'right'})
    chk('오른쪽 → 200', c == 200 and d.get('side') == 'right', (c, d))
    _, ly = call('GET', '/api/layout')
    r, f = ly.get('ranking', {}), ly.get('fundjar', {})
    chk('점수판은 그대로(10, 263, 0.88)', (r.get('x_px'), r.get('y_px'), r.get('scale')) == (10, 263, 0.88), r)
    # 10 + 878×0.88(772.6) + 사이 9 = 791.6 → 792
    chk('깃발은 점수판 바로 오른쪽(792, 263, 0.88)', (f.get('x_px'), f.get('y_px'), f.get('scale')) == (792, 263, 0.88), f)
    chk('깃발이 화면 안에 있다(오른쪽 끝 ≤ 1080)', f.get('x_px', 0) + 108 * f.get('scale', 1) <= 1080, f)
    chk('다른 위젯은 안 건드린다(계좌 그대로)', ly.get('account') == BASE['account'], ly.get('account'))
    chk('판 번호 · 안전지대 표시가 남는다', ly.get('__v') == 2 and ly.get('__free') is True)
    c, d = call('GET', '/api/fundjar/side')
    chk('지금 자리 = 오른쪽', d.get('side') == 'right', d)

    head('② 왼쪽')
    c, d = call('POST', '/api/fundjar/side', {'side': 'left'})
    _, ly = call('GET', '/api/layout')
    r, f = ly.get('ranking', {}), ly.get('fundjar', {})
    chk('깃발이 점수판 자리로(10, 263)', (f.get('x_px'), f.get('y_px'), f.get('scale')) == (10, 263, 0.88), f)
    # 10 + 108×0.88(95.0) + 9 = 114
    chk('점수판은 깃발 폭만큼 비킨다(114)', (r.get('x_px'), r.get('y_px'), r.get('scale')) == (114, 263, 0.88), r)
    chk('점수판 오른쪽 끝도 화면 안(114 + 772.6 ≤ 1080)', r.get('x_px', 0) + 878 * r.get('scale', 1) <= 1080, r)
    c, d = call('GET', '/api/fundjar/side')
    chk('지금 자리 = 왼쪽', d.get('side') == 'left', d)
    call('POST', '/api/fundjar/side', {'side': 'left'})
    _, ly2 = call('GET', '/api/layout')
    chk('왼쪽을 또 눌러도 안 밀린다', ly2.get('ranking') == ly.get('ranking') and ly2.get('fundjar') == ly.get('fundjar'),
        (ly2.get('ranking'), ly2.get('fundjar')))

    head('③ 다시 오른쪽 — 왕복')
    call('POST', '/api/fundjar/side', {'side': 'right'})
    _, ly = call('GET', '/api/layout')
    chk('점수판이 제자리(10)로 · 깃발은 792', ly.get('ranking', {}).get('x_px') == 10 and ly.get('fundjar', {}).get('x_px') == 792,
        (ly.get('ranking'), ly.get('fundjar')))

    head('④ 거절')
    c, d = call('POST', '/api/fundjar/side', {'side': 'up'})
    chk("이상한 값('up') → 400", c == 400, (c, d))
    c, d = call('POST', '/api/fundjar/side', {'side': 'left'}, auth=False)
    chk('로그인 없이 → 거절(200 아님)', c not in (200, 0), c)
    _, ly = call('GET', '/api/layout')
    chk('거절된 요청은 배치를 안 바꾼다', ly.get('fundjar', {}).get('x_px') == 792, ly.get('fundjar'))
    call('POST', '/api/layout', {'__v': 1, 'ranking': {'x_px': 362, 'y_px': 178, 'scale': 1}})
    c, d = call('POST', '/api/fundjar/side', {'side': 'right'})
    chk('옛 배치 파일(판 번호 1)은 409 — 판 번호만 올려 옛 자리를 살리지 않는다', c == 409, (c, d))
    _, ly = call('GET', '/api/layout')
    chk('옛 배치 파일은 그대로', ly.get('__v') == 1 and 'fundjar' not in ly, ly)
    call('POST', '/api/layout', {'__v': 2})
    c, d = call('POST', '/api/fundjar/side', {'side': 'right'})
    _, ly = call('GET', '/api/layout')
    # 편집기에서 안 잡은 점수판 = 방송판 기본(오른쪽 42 · 위 167 · 배율 1) → x 160
    chk('점수판을 안 잡았으면 방송판 기본 자리 기준 — 둘이 화면 안에 들어오게 당긴다',
        c == 200 and ly.get('fundjar', {}).get('x_px', 9999) + 108 <= 1080 and ly.get('ranking', {}).get('y_px') == 167,
        (c, ly.get('ranking'), ly.get('fundjar')))
finally:
    if isinstance(ORIG, dict):
        call('POST', '/api/layout', ORIG)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
