# -*- coding: utf-8 -*-
"""🎬 고액후원 영상이 떠 있으면 계좌 줄이 영상 **뒤로** 간다 (2026-10-03 대표님 "고액영상 틀 때 계좌만 영상 앞으로 나와 있네")

원인: 계좌는 머리 줄(#headrow, z-index 100000) 안에 있고, 영상 상자(#acct_video-container)는 88000 이다.
      둘 다 #master-container 의 자식이라 숫자 큰 쪽이 늘 위 — 다른 위젯은 다 영상 뒤로 가는데 계좌만 앞에 남았다.
고침: 영상이 떠 있는 동안 body.acct-video-on → 머리 줄 z-index 87000(영상 바로 아래).

여기서 지키는 것 — 진짜 방송판(헤드리스 크롬)에서 진짜 함수(acctVideoPlay · acctVideoStop)를 불러 잰다
  ① 영상 전: 계좌 한가운데를 찍으면 계좌가 나온다
  ② 영상 중: 같은 점을 찍으면 영상 상자가 나온다(계좌가 앞으로 안 튀어나온다) — 유튜브 · 파일 두 길 다
  ③ 영상이 끝나면(acctVideoStop) 계좌가 다시 맨 위
  ④ 시그니처 가리개(90000)는 여전히 영상 위 — 내린 건 머리 줄 하나뿐

pt 서버가 필요하다(LM_PT_PORT, 기본 5199). 크롬이 없으면 브라우저 부분은 건너뛴다.
⚠️ 크롬은 이 검사가 띄운 것 하나만 끈다 — 이름으로 찾아 죽이면 앱 브라우저까지 죽는다.
"""
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = (os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(HERE, '..')))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:200]) if detail else ''))


def head(s):
    print()
    print('=' * 74)
    print(s)
    print('=' * 74)


def call(method, path, obj=None):
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(B + path, data, H, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {'err': str(e)}


OV = io.open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8').read()
head('글자로 먼저 — 켜는 곳 둘 · 끄는 곳 하나')
chk('규칙: 영상 중에는 머리 줄이 영상(88000) 바로 아래', 'body.acct-video-on #headrow { z-index: 87000 !important; }' in OV)
chk('유튜브 · 파일 두 길 모두 켠다', OV.count("document.body.classList.add('acct-video-on')") == 2)
chk('끌 때(acctVideoStop) 끈다', "document.body.classList.remove('acct-video-on')" in OV[OV.index('function acctVideoStop'):][:1400])


def chrome_path():
    for p in (os.environ.get('LM_CHROME') or '',
              r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
              '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
              shutil.which('google-chrome') or '', shutil.which('chromium') or ''):
        if p and os.path.exists(p):
            return p
    return None


try:
    import websocket
except Exception:
    websocket = None
alive = call('GET', '/api/ping')[0] == 200 or call('GET', '/api/data')[0] == 200
CHROME = chrome_path()
if not alive or not CHROME or websocket is None:
    print('\n⚠️ 서버 · 크롬 · websocket-client 중 없는 것이 있어 방송판(브라우저) 검사를 건너뜁니다')
else:
    _, ORIG_LY = call('GET', '/api/layout')
    _, ORIG_ST = call('GET', '/api/data')
    # ⚠️ 시각으로 포트를 뽑으면 바로 앞 검사(같은 식)의 크롬이 아직 쥐고 있는 번호와 겹칠 수 있다(전체 검사에서 실제로 났다)
    #    → 운영체제에게 빈 번호를 받는다
    _s = socket.socket(); _s.bind(('127.0.0.1', 0)); PORT = _s.getsockname()[1]; _s.close()
    PROF = tempfile.mkdtemp(prefix='acctvid_')
    proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                             '--autoplay-policy=no-user-gesture-required',
                             '--user-data-dir=' + PROF, '--remote-debugging-port=%d' % PORT,
                             '--remote-allow-origins=*', 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    try:
        # 운영과 같은 계좌 자리(55, 455, 1.512) + 그 위를 덮는 영상 자리
        call('POST', '/api/layout', {'__v': 2, '__free': True,
                                     'account': {'x_px': 55, 'y_px': 455, 'scale': 1.512},
                                     'acct_video': {'x_px': 0, 'y_px': 380, 'scale': 0.84}})
        # ⚠️ /api/restore 는 상태를 통째로 갈아끼운다(bjs 가 있어야 받는다) — 끝나고 원래 상태로 되돌린다
        call('POST', '/api/restore', {'broadcast_active': True, 'reaction_queue': [],
                                      'bjs': [{'name': '하율', 'score': 1, 'contribution': 1}],
                                      'account': {'bank': '기업은행', 'acc_num': '464-000000-00-000', 'name': '검사계좌'}})
        tabs = None
        for _ in range(80):   # 크롬이 느리게 뜨는 날도 있다(최대 ~40초)
            try:
                tabs = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=2).read())
                if any(t.get('type') == 'page' for t in tabs):
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not tabs or not any(t.get('type') == 'page' for t in tabs):
            raise RuntimeError('검사용 크롬이 뜨지 않았다(포트 %d)' % PORT)
        ws = websocket.create_connection(next(t for t in tabs if t.get('type') == 'page')['webSocketDebuggerUrl'],
                                         timeout=60)
        st = {'id': 0}

        def send(method, **params):
            st['id'] += 1
            ws.send(json.dumps({'id': st['id'], 'method': method, 'params': params}))
            while True:
                m = json.loads(ws.recv())
                if m.get('id') == st['id']:
                    return m.get('result', {})

        def ev(expr):
            r = send('Runtime.evaluate', expression=expr, returnByValue=True, awaitPromise=True)
            return (r.get('result') or {}).get('value')

        send('Page.enable')
        send('Runtime.enable')
        send('Emulation.setDeviceMetricsOverride', width=1080, height=1920, deviceScaleFactor=1, mobile=False)
        send('Page.navigate', url=B + '/overlay.html')
        for _ in range(80):
            time.sleep(0.25)
            if ev("!!(document.getElementById('account-box-ui') && getComputedStyle(document.getElementById('account-box-ui')).visibility === 'visible')"):
                break
        time.sleep(1.5)   # 위젯 자리 전환(0.8초)이 끝난 뒤에 잰다

        # 계좌 한가운데 점을 찍어 맨 위에 무엇이 있나 본다
        PROBE = """(() => { const a = document.getElementById('account-box-ui').getBoundingClientRect();
            const x = a.left + a.width / 2, y = a.top + a.height / 2;
            const top = document.elementFromPoint(x, y);
            const vid = document.getElementById('acct_video-container');
            return JSON.stringify({ x: Math.round(x), y: Math.round(y),
                acc: !!(top && top.closest('#account-container')), vid: !!(top && vid.contains(top)),
                tag: top ? (top.id || top.tagName) : null,
                on: document.body.classList.contains('acct-video-on'),
                z: getComputedStyle(document.getElementById('headrow')).zIndex,
                vshow: getComputedStyle(vid).display }); })()"""

        head('① 영상 전 — 계좌가 맨 위')
        p0 = json.loads(ev(PROBE) or '{}')
        chk('계좌 한가운데 = 계좌', p0.get('acc') is True and p0.get('vid') is False, p0)
        chk('머리 줄은 원래 높이(100000)', p0.get('z') == '100000', p0)

        head('② 유튜브 영상 중 — 계좌가 영상 뒤로')
        ev("acctVideoPlay('dQw4w9WgXcQ'); true")
        time.sleep(0.4)
        p1 = json.loads(ev(PROBE) or '{}')
        chk('⭐ 같은 점을 찍으면 영상 상자가 나온다(계좌가 앞으로 안 튀어나온다)', p1.get('vid') is True and p1.get('acc') is False, p1)
        chk('머리 줄이 영상 바로 아래(87000)', p1.get('on') is True and p1.get('z') == '87000', p1)
        chk('⑤ 시그니처 가리개 자리(90000)는 영상보다 위 그대로',
            ev("+getComputedStyle(document.getElementById('acct_video-container')).zIndex < 90000") is True)

        head('③ 영상이 끝나면 — 계좌가 다시 맨 위')
        ev("acctVideoStop(); true")
        time.sleep(0.3)
        p2 = json.loads(ev(PROBE) or '{}')
        chk('⭐ 끝나면 계좌가 다시 보인다', p2.get('acc') is True and p2.get('on') is False and p2.get('z') == '100000', p2)

        head('② 파일 영상 중 — 같은 규칙')
        # 실제 파일이 없어도 재생 실패(onerror)가 오기 전, 상자가 뜬 순간을 잰다
        p3 = json.loads(ev("""(() => { const box = document.getElementById('acct_video-container');
            const frame = document.getElementById('acct-video-frame');
            acctVideoPlayFile('/videos/__no_such_file__.mp4', box, frame);
            return %s; })()""" % PROBE) or '{}')
        chk('⭐ 파일 영상도 계좌를 덮는다', p3.get('vid') is True and p3.get('acc') is False and p3.get('z') == '87000', p3)
        time.sleep(1.5)
        p4 = json.loads(ev(PROBE) or '{}')
        chk('재생 실패로 내려가면 계좌가 다시 맨 위(눌러앉지 않는다)', p4.get('acc') is True and p4.get('on') is False, p4)
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            pass
        shutil.rmtree(PROF, ignore_errors=True)
        if isinstance(ORIG_LY, dict):
            call('POST', '/api/layout', ORIG_LY)
        if isinstance(ORIG_ST, dict) and 'bjs' in ORIG_ST:
            call('POST', '/api/restore', ORIG_ST)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
