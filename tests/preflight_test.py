# -*- coding: utf-8 -*-
"""🛫 방송 전 점검 · 🚨 방송 중 경보 — 대표님 2026-10-06 "사고 막기 해볼까, 소리는 안 나도 돼".

여기서 지키는 것
  ① 서버 /api/preflight — 로그인해야 본다 · 읽기만 한다(저장 · 방송 알림 없음)
  ② 📺 방송 화면 — kind=overlay 만 센다 · 미리보기(monitor=1)는 따로 센다
  ③ 🎧 후원 받기 — 리스너가 적는 상태 파일로 ok · 붙는 중 · 멈춤 · 없음을 가른다
  ④ 📮 못 보낸 후원 수 · 🎵 시그니처 목록(deep 일 때만)
  ⑤ 조종실(헤드리스 크롬) — 머리줄 점 두 개 · 방송 전 점검표 · 방송 중 경보 띠(잠깐은 넘어가고 · [알겠어요] · 다시 붙으면 내려감)
  ⑥ ⭐ 소리는 안 낸다
pt 서버(5199)가 필요하다. LM_SANDBOX_PT(서버 폴더)에 상태 파일을 잠깐 썼다 지운다.
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
PORT_SV = int(os.environ.get('LM_PT_PORT', '5199'))
B = 'http://127.0.0.1:%d' % PORT_SV
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(HERE, '..'))
SBOX = os.environ.get('LM_SANDBOX_PT') or ''
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:220]) if detail else ''))


def head(s):
    print()
    print('=' * 74)
    print(s)
    print('=' * 74)


def call(method, path, obj=None, auth=True):
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(B + path, data, H if auth else {'Content-Type': 'application/json'}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'err': str(e)}


def pf(deep=False):
    return call('GET', '/api/preflight' + ('?deep=1' if deep else ''))


def open_stream(path):
    s2 = socket.create_connection(('127.0.0.1', PORT_SV), timeout=10)
    s2.sendall(('GET %s HTTP/1.1\r\nHost: 127.0.0.1\r\nAccept: text/event-stream\r\n\r\n' % path).encode())
    s2.settimeout(10)
    s2.recv(65536)
    return s2


PF = io.open(os.path.join(ROOT, 'features', 'preflight.py'), encoding='utf-8').read()
CT = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
SV = io.open(os.path.join(ROOT, 'server.py'), encoding='utf-8').read()

head('① 서버 — 로그인 · 읽기만')
chk('server.py 가 불러온다', 'import features.preflight' in SV)
chk('읽기만 한다(저장 · 방송 알림 · 잠금 없음)', 'save_data(' not in PF and 'broadcast_event(' not in PF and 'file_lock' not in PF.split('"""', 2)[2])
c, _ = call('GET', '/api/preflight', auth=False)
chk('로그인 없이는 못 본다', c in (401, 403), c)
c, d = pf()
chk('로그인하면 본다', c == 200 and d.get('status') == 'success', c)
chk('칸이 다 있다', all(k in d for k in ('broadcast_active', 'screens', 'listener', 'spool', 'storage', 'server')), list(d))
chk('deep 이 아니면 시그니처 서버를 안 묻는다', 'sig' not in d)
chk('저장소 정상', (d.get('storage') or {}).get('ok') is True, d.get('storage'))

head('② 방송 화면 — 미리보기는 따로 센다')
base = (pf()[1].get('screens') or {})
s_ov = open_stream('/api/stream?kind=overlay&obs=1')
s_mon = open_stream('/api/stream?kind=overlay&monitor=1')
time.sleep(0.6)
sc = pf()[1].get('screens') or {}
chk('⭐ OBS 방송 화면을 센다', sc.get('overlay') == base.get('overlay', 0) + 1 and sc.get('overlay_obs') == base.get('overlay_obs', 0) + 1, (base, sc))
chk('미리보기(폰 · 편집기 안)는 방송 화면으로 안 센다', sc.get('monitor') == base.get('monitor', 0) + 1, sc)
for x in (s_ov, s_mon):
    try:
        x.close()
    except Exception:
        pass

head('③ 후원 받기 — 리스너 상태 파일')
if not SBOX or not os.path.isdir(SBOX):
    print('  (LM_SANDBOX_PT 가 없어 상태 파일 검사는 건너뜁니다)')
else:
    STF = os.path.join(SBOX, 'toon_listener_status.json')
    SPF = os.path.join(SBOX, 'donation_spool.jsonl')
    had_st = os.path.exists(STF)
    had_sp = os.path.exists(SPF)
    try:
        def put(updated, state, note=''):
            with open(STF, 'w', encoding='utf-8') as f:
                json.dump({'updated': updated, 'accounts': {'main': {'label': '투네이션', 'state': state, 'note': note,
                                                                      'connected_at': time.time() - 3700, 'last_donation': time.time() - 600}}}, f)
        if os.path.exists(STF):
            os.remove(STF)
        chk('상태 파일이 없으면 "없음"(경보 안 함)', (pf()[1].get('listener') or {}).get('level') == 'none')
        put(time.time(), 'connected')
        li = pf()[1].get('listener') or {}
        chk('⭐ 연결됨 → ok · 몇 분째 · 마지막 후원', li.get('level') == 'ok' and 3600 <= (li.get('connected_sec') or 0) < 3800
            and 590 <= (li.get('last_donation_sec') or 0) < 700, li)
        put(time.time(), 'connecting', '연결이 닫혀 다시 붙습니다')
        chk('붙는 중 → connecting', (pf()[1].get('listener') or {}).get('level') == 'connecting')
        put(time.time(), 'error', 'ConnectionClosed: 1006')
        li = pf()[1].get('listener') or {}
        chk('오류 → down · 까닭을 같이', li.get('level') == 'down' and 'ConnectionClosed' in (li.get('note') or ''), li)
        put(time.time() - 120, 'connected')
        li = pf()[1].get('listener') or {}
        chk('⭐ 1분 넘게 소식이 없으면(프로그램이 죽음) → down', li.get('level') == 'down', li)
        with open(SPF, 'w', encoding='utf-8') as f:
            f.write('{"tx_id":"a"}\n{"tx_id":"b"}\n\n')
        chk('📮 못 보낸 후원 수를 센다', pf()[1].get('spool') == 2, pf()[1].get('spool'))
    finally:
        try:
            if not had_st and os.path.exists(STF):
                os.remove(STF)
            if not had_sp and os.path.exists(SPF):
                os.remove(SPF)
        except Exception:
            pass

head('④ 시그니처 목록(deep)')
c, d = pf(deep=True)
sg = d.get('sig') or {}
chk('deep 이면 시그니처 서버를 묻는다 · 개수 · 제일 싼 값', c == 200 and sg.get('ok') is True and (sg.get('count') or 0) > 0
    and isinstance(sg.get('cheapest'), int), sg)
c, d2 = pf(deep=True)
chk('60초 동안은 다시 안 묻는다(기억)', (d2.get('sig') or {}).get('cached') is True, d2.get('sig'))

head('⑥ 소리는 안 낸다 · 조종실 짜임')
js = CT[CT.index('🛫 방송 전 점검표 · 🚨 방송 중 경보'):]
js = js[:js.index('</script>')]
chk('⭐ 경보에 소리가 없다(대표님 "소리는 안 나도 돼")', not any(w in js for w in ('Audio(', 'playSfx', '.play(', 'beep', 'speechSynthesis', 'vibrate')))
chk('머리줄 점 두 개 · 경보 띠 · 점검표', 'id="pf-chip-ov"' in CT and 'id="pf-chip-li"' in CT and 'id="pf-alarm"' in CT and 'id="pf-list"' in CT)
chk('경보 띠는 sticky-top 맨 위(스크롤해도 보인다)', CT.index('id="pf-alarm"') - CT.index('<div id="sticky-top">') < 300)
_sbf = CT.find('function startBroadcast(')
chk('점검표는 [방송 시작] 바로 위 · 막지 않는다(급할 땐 그냥 시작)', CT.index('id="pf-list"') < CT.index('onclick="startBroadcast()"')
    and _sbf > 0 and 'pf' not in CT[_sbf:_sbf + 1500])


# ⑤ 조종실(헤드리스 크롬)
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
CHROME = chrome_path()
if not CHROME or websocket is None:
    print('\n⚠️ 크롬 · websocket-client 가 없어 조종실 검사를 건너뜁니다')
else:
    head('⑤ 조종실(헤드리스 크롬)')
    _s = socket.socket(); _s.bind(('127.0.0.1', 0)); DPORT = _s.getsockname()[1]; _s.close()
    PROF = tempfile.mkdtemp(prefix='pft_')
    proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                             '--user-data-dir=' + PROF, '--remote-debugging-port=%d' % DPORT, '--remote-allow-origins=*', 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    errs = []
    try:
        tabs = None
        for _ in range(80):
            try:
                tabs = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % DPORT, timeout=2).read())
                if any(t.get('type') == 'page' for t in tabs):
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not tabs or not any(t.get('type') == 'page' for t in tabs):
            raise RuntimeError('검사용 크롬이 뜨지 않았다(포트 %d)' % DPORT)
        ws = websocket.create_connection(next(t for t in tabs if t.get('type') == 'page')['webSocketDebuggerUrl'], timeout=60)
        st = {'id': 0}

        def send(method, **params):
            st['id'] += 1
            ws.send(json.dumps({'id': st['id'], 'method': method, 'params': params}))
            while True:
                m = json.loads(ws.recv())
                if m.get('method') == 'Runtime.exceptionThrown':
                    dd = m['params']['exceptionDetails']
                    errs.append((dd.get('exception') or {}).get('description', dd.get('text', ''))[:200])
                if m.get('id') == st['id']:
                    return m.get('result', {})

        def ev(expr):
            r = send('Runtime.evaluate', expression=expr, returnByValue=True, awaitPromise=True)
            return (r.get('result') or {}).get('value')

        send('Page.enable'); send('Runtime.enable')
        send('Emulation.setDeviceMetricsOverride', width=1440, height=900, deviceScaleFactor=1, mobile=False)
        send('Page.navigate', url=B + '/login'); time.sleep(1.5)
        ev("fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:'sandboxpw'})}).then(r=>r.status)")
        send('Page.navigate', url=B + '/controller'); time.sleep(6)
        chips = ev("[document.getElementById('pf-chip-ov').className, document.getElementById('pf-chip-li').className, typeof pfLast]")
        chk('머리줄 점 두 개가 그려진다(첫 확인이 끝났다)', bool(chips) and chips[2] == 'object' and 'pf-chip' in chips[0], chips)
        # 방송 전 — 점검표
        bo = ev("!!(gd && gd.broadcast_active)")
        if not bo:
            for _ in range(20):
                time.sleep(0.5)
                if ev("document.querySelectorAll('#pf-items .pf-item').length >= 5"):
                    break
            items = ev("[...document.querySelectorAll('#pf-items .pf-item')].map(x => x.innerText.replace(/\\n/g, ' / '))") or []
            chk('⭐ 방송 전 점검표 — 방송 화면 · 후원 받기 · 시그니처 · 저장소 · 서버 · OBS 리플레이 버퍼', len(items) >= 6
                and any('방송 화면' in x for x in items) and any('후원 받기' in x for x in items) and any('시그니처 목록' in x for x in items)
                and any('리플레이 버퍼' in x for x in items), items)
            chk('요약 줄(확인할 것 N개 / 모두 준비됐어요)', (ev("document.getElementById('pf-sum').textContent") or '') in ('모두 준비됐어요',) or '확인할 것' in (ev("document.getElementById('pf-sum').textContent") or ''))
            ev("(() => { const c = document.querySelector('#pf-items input[type=checkbox]'); c.checked = true; c.dispatchEvent(new Event('change')); })()")
            chk('OBS 리플레이 버퍼 확인 표시는 오늘 기억한다', ev("localStorage.getItem(pfObsKey()) === '1'") is True)
        else:
            print('  (pt 서버가 방송 중이라 점검표 검사는 건너뜁니다)')
        # 🚨 경보 — 서버 대신 같은 모양의 답을 넣어 본다(시간을 기다리지 않게 '처음 나빠진 때' 만 앞당긴다)
        FAKE = ("({status:'success', broadcast_active:true, screens:{overlay:%d, overlay_obs:0, overlay_idle:0, monitor:0, total:1},"
                " listener:{level:'%s', note:''}, spool:%d, storage:{ok:true, ms:1}, server:{}})")
        r1 = ev("(() => { pfDown = {ov:0, li:0, sp:0}; pfAck = {ov:-1, li:-1, sp:-1}; pfRender(%s); return document.getElementById('pf-alarm').classList.contains('on'); })()" % (FAKE % (0, 'ok', 0)))
        chk('⭐ 막 끊긴 것은 바로 안 띄운다(새로고침 · 재연결은 넘어간다)', r1 is False, r1)
        r2 = ev("(() => { pfDown.ov = Date.now() - 16000; pfRender(%s); const a = document.getElementById('pf-alarm'); return [a.classList.contains('on'), a.innerText]; })()" % (FAKE % (0, 'ok', 0)))
        chk('⭐ 방송 중 방송 화면이 15초 넘게 없으면 빨간 띠', bool(r2) and r2[0] is True and '방송 화면(OBS)' in (r2[1] or ''), r2)
        chip = ev("document.getElementById('pf-chip-ov').className")
        chk('머리줄 점도 빨강', 'bad' in (chip or ''), chip)
        r3 = ev("(() => { pfDismiss('ov'); return document.getElementById('pf-alarm').classList.contains('on'); })()")
        chk('[알겠어요] → 그 건은 내려간다', r3 is False, r3)
        r4 = ev("(() => { pfRender(%s); pfRender(%s); pfDown.ov = Date.now() - 16000; pfRender(%s); return document.getElementById('pf-alarm').classList.contains('on'); })()"
                % (FAKE % (1, 'ok', 0), FAKE % (0, 'ok', 0), FAKE % (0, 'ok', 0)))
        chk('다시 붙었다 또 끊기면 새로 뜬다', r4 is True, r4)
        r5 = ev("(() => { pfRender(%s); return document.getElementById('pf-alarm').classList.contains('on'); })()" % (FAKE % (1, 'ok', 0)))
        chk('⭐ 다시 붙으면 저절로 내려간다', r5 is False, r5)
        r6 = ev("(() => { pfRender(%s); pfDown.li = Date.now() - 31000; pfRender(%s); const a = document.getElementById('pf-alarm'); return [a.classList.contains('on'), a.innerText]; })()"
                % (FAKE % (1, 'down', 0), FAKE % (1, 'down', 0)))
        chk('⭐ 후원 받기가 30초 넘게 멈추면 띠(후원 콘솔로 넣으라고 알려 준다)', bool(r6) and r6[0] is True and '후원 받기' in (r6[1] or '') and '후원 콘솔' in (r6[1] or ''), r6)
        r7 = ev("(() => { const f = %s; f.broadcast_active = false; pfRender(f); return document.getElementById('pf-alarm').classList.contains('on'); })()" % (FAKE % (0, 'down', 3)))
        chk('방송 전에는 띠를 안 띄운다(점검표가 대신)', r7 is False, r7)
        r8 = ev("(() => { pfRender(%s); pfDown.sp = Date.now() - 31000; pfRender(%s); return document.getElementById('pf-alarm').innerText; })()"
                % (FAKE % (1, 'ok', 3), FAKE % (1, 'ok', 3)))
        chk('📮 못 보낸 후원이 30초 넘게 쌓여 있으면 노란 줄', '못 보낸 후원 3건' in (r8 or ''), r8)
        ev("pfRender(%s)" % (FAKE % (1, 'ok', 0)))
        chk('JS 오류 없음', not errs, errs[:3])
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

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
