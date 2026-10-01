# -*- coding: utf-8 -*-
"""🎲🎵 방송판에서 실제로 굴려 순서를 잰다 — 코드 글자가 아니라 브라우저가 한 일을 본다.

대표님(2026-09-30): "주사위를 굴리고 이동을 하고 시그니처 걸린 게 뜨고 리액션모드로 들어가서 시그가
재생되어야 하는데, 지금 시그니처칸에 걸리면 냅다 리액션모드로 가고 말이 이동하고 시그니처가 걸렸다고 떠"

⚠️ 예전 검사는 overlay.html 에 어떤 글자가 있는지만 봤다. 그래서 가리개가 표지판보다 먼저 판단하는
   순서가 뒤집혀도 전부 통과했다. 여기서는 헤드리스 크롬으로 방송판을 열고, 몸통 클래스 · 카드 · 시그 화면 ·
   말 자리가 바뀌는 순간을 방송판 안에서 직접 적는다(파이썬 왕복 지연이 끼지 않게).

pt 서버(5199)가 필요하다. 크롬이 없으면 건너뛴다(검사 실패로 치지 않고 그렇게 적는다).
⚠️ 크롬은 이 검사가 띄운 것 하나만 끈다 — 이름으로 찾아 죽이면 앱 브라우저까지 죽는다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:160]) if detail else ''))


def post(path, obj=None):
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), H)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=H), timeout=25) as r:
        return json.loads(r.read().decode())


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
    print('⚠️ 크롬 또는 websocket-client 가 없어 방송판 순서 검사를 건너뜁니다 (%s)'
          % ('크롬 없음' if not CHROME else 'pip install websocket-client'))
    print('통과 0 · 실패 0')
    sys.exit(0)

NAMES = ('가', '나', '다', '라')


def reset(**extra):
    body = {'broadcast_active': True, 'extra_game_active': False, 'reaction_queue': [], 'reaction_mode': False,
            'reaction_paused': False, 'pending_donations': [], 'logs': [],
            'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in NAMES]}
    body.update(extra)
    post('/api/restore', body)


def board(tile_type='blank', n_cols=8, **tile):
    post('/api/dicegame/setup', {'cols': n_cols, 'rows': 5, 'dice': 1, 'roll_price': 0})
    n = len((get().get('dicegame') or {}).get('tiles') or [])
    for i in range(1, n):
        post('/api/dicegame/tile', dict({'id': i, 'type': tile_type}, **tile))
    return n


PORT = 9437
PROF = tempfile.mkdtemp(prefix='dgorder_')
proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                         '--user-data-dir=' + PROF, '--autoplay-policy=no-user-gesture-required',
                         '--remote-debugging-port=%d' % PORT, '--remote-allow-origins=*', 'about:blank'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ws = None
try:
    tabs = None
    for _ in range(60):
        try:
            tabs = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=2).read())
            break
        except Exception:
            time.sleep(0.3)
    ws = websocket.create_connection(next(t for t in tabs if t.get('type') == 'page')['webSocketDebuggerUrl'], timeout=60)
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

    send('Page.enable'); send('Runtime.enable')
    send('Emulation.setDeviceMetricsOverride', width=1080, height=1920, deviceScaleFactor=1, mobile=False)

    # 방송판 안에서 바뀌는 순간을 적는 도구 — 몸통 가리개 · 결과 카드 · 시그 화면 · 말 자리
    REC = r"""(() => {
        window.__ev = []; window.__t0 = performance.now();
        const T = () => Math.round(performance.now() - window.__t0);
        const put = (k, v) => window.__ev.push([T(), k, v]);
        const b = document.body;
        let rm = b.classList.contains('reaction-mode');
        new MutationObserver(() => { const n = b.classList.contains('reaction-mode'); if (n !== rm) { rm = n; put('RM', n); } })
            .observe(b, { attributes: true, attributeFilter: ['class'] });
        const watch = (id, k) => { const el = document.getElementById(id); if (!el) return; let on = el.classList.contains('show');
            new MutationObserver(() => { const n = el.classList.contains('show'); if (n !== on) { on = n; put(k, n); } })
                .observe(el, { attributes: true, attributeFilter: ['class'] }); };
        watch('dg-card', 'CARD'); watch('reaction-screen-overlay', 'SIG');
        window.__pieceAt = (nm) => { const c = [...document.querySelectorAll('.dg-piece')].find(x => x.textContent === nm);
            const t = c && c.closest('.dg-tile'); return t ? parseInt(t.id.replace('dg-tile-', '')) : null; };
        let last = null;
        window.__pw = setInterval(() => { const p = window.__pieceAt(window.__watchName || '가'); if (p !== last) { last = p; put('PIECE', p); } }, 25);
        return true; })()"""

    def open_overlay():
        send('Page.navigate', url=B + '/overlay.html')
        for _ in range(60):
            time.sleep(0.25)
            if ev("!!(window.globalData && document.getElementById('dg-tile-1'))"):
                break
        time.sleep(0.8)
        ev(REC)

    def now_ms():
        return ev('Math.round(performance.now() - window.__t0)')

    def events():
        return ev('window.__ev') or []

    def first(evs, k, v, after=-1):
        for t, kk, vv in evs:
            if kk == k and vv == v and t > after:
                return t
        return None

    # ════════════════════════════════════════════════════════════════
    print('=' * 74)
    print('① 시그 칸 — 굴림 → 말 이동 → "시그니처 재생!" 카드 → (1.5초 뒤) 가리개 + 시그 재생')
    print('=' * 74)
    reset()
    n = board('sig', sig_id=10040)
    post('/api/dicegame/move', {'piece': '가', 'pos': 0})
    open_overlay()
    chk('방송판에 주사위판이 떴다', ev("getComputedStyle(document.getElementById('dicegame-container')).opacity") == '1')
    t_roll = now_ms()
    c, r = post('/api/dicegame/roll', {'piece': '가', 'value': 3})
    chk('3칸 굴림 → 시그 칸', c == 200 and (r.get('tile') or {}).get('type') == 'sig', (c, r.get('tile')))
    time.sleep(5.5)
    E = events()
    rel = [(t - t_roll, k, v) for t, k, v in E if t >= t_roll]
    print('     ' + ' · '.join('%s=%s@%d' % (k, v, t) for t, k, v in rel[:14]))
    arrive = first([(t, k, v) for t, k, v in rel], 'PIECE', 3)
    card = first(rel, 'CARD', True)
    rm_on = first(rel, 'RM', True)
    sig_on = first(rel, 'SIG', True)
    chk('말이 3번 칸에 닿았다', arrive is not None, arrive)
    chk('⭐ 말이 닿기 전에는 판을 안 가린다 (예전: 굴리자마자 0.0초에 가렸다)',
        rm_on is not None and arrive is not None and rm_on > arrive, (arrive, rm_on))
    # 마지막 칸을 밟고(한 칸 0.3초) 착지 여유 0.12초 뒤에 카드가 뜬다 — 0.42초가 설계 값
    chk('닿으면 카드가 뜬다 (마지막 걸음 뒤 0.6초 안)', card is not None and arrive is not None and 0 <= card - arrive <= 600, (arrive, card))
    chk('⭐ 카드를 읽을 틈이 있다 (카드 → 가리개 1.2초 이상 · 예전 0.06초)',
        rm_on is not None and card is not None and rm_on - card >= 1200, (card, rm_on))
    chk('가리개와 시그 재생이 같이 시작한다 (0.6초 안)',
        sig_on is not None and rm_on is not None and -100 <= sig_on - rm_on <= 600, (rm_on, sig_on))
    chk('연출 끝(닿음 + 1.5초)에 맞춰 연다 — 굴림 뒤 2.9초 안팎',
        rm_on is not None and 2500 <= rm_on <= 3700, rm_on)
    q = get().get('reaction_queue') or []
    # 가짜 시그 음원은 주소가 없어 금방 끝난다 — 줄에 남아 있으면 그 모양도 본다
    ok_text = ev("reactionUpText({source: 'dice', banner: '가 · 시그 칸 도착', donator: '가', amount: 0})")
    chk('주사위 시그 제목은 "누가 밟았나" 다 (후원 · 업 이 아니다)', ok_text == '가 · 시그 칸 도착', ok_text)

    # ════════════════════════════════════════════════════════════════
    print()
    print('=' * 74)
    print('② 알림 일시정지 — 대기만 있고 틀고 있는 게 없으면 판을 안 가린다')
    print('=' * 74)
    reset()
    board('blank')
    open_overlay()
    post('/api/reaction/pause', {'paused': True})
    c, r = post('/api/signature/play', {'sig_id': 10005, 'name': '손님A'})
    time.sleep(1.2)
    d = get()
    chk('서버: 멈춤 · 대기 1건 · 리액션 모드 켜짐', d.get('reaction_paused') and len(d.get('reaction_queue') or []) == 1
        and d.get('reaction_mode'), (d.get('reaction_paused'), len(d.get('reaction_queue') or []), d.get('reaction_mode')))
    chk('⭐ 방송판: 가리개가 안 켜진다 (예전: 주사위판 · 점수판이 통째로 사라진 채 멈춤)',
        ev("document.body.classList.contains('reaction-mode')") is False)
    chk('주사위판이 보인다', ev("getComputedStyle(document.getElementById('dicegame-container')).opacity") == '1')
    t_un = now_ms()
    post('/api/reaction/pause', {'paused': False})
    time.sleep(4.5)   # 보통 후원 시그는 후원 팝업(2초) 뒤에 튼다
    E = events()
    chk('멈춤을 풀면 가리고 튼다', first(E, 'RM', True, t_un) is not None and first(E, 'SIG', True, t_un) is not None,
        [e for e in E if e[0] > t_un][:6])
    post('/api/reaction/stop', {})

    # ════════════════════════════════════════════════════════════════
    print()
    print('=' * 74)
    print('③ 굴리는 중에 무대가 바뀌었다 돌아오면 서버 자리에 선다')
    print('=' * 74)
    reset()
    board('blank')
    post('/api/dicegame/move', {'piece': '가', 'pos': 0})
    open_overlay()
    post('/api/dicegame/roll', {'piece': '가', 'value': 6})          # 닿음 2.3초
    time.sleep(1.0)
    mid = ev("window.__pieceAt('가')")
    post('/api/show', {'stage': 'siggame'})
    time.sleep(0.8)
    post('/api/dicegame/enable', {'on': True})
    time.sleep(0.9)
    at = ev("window.__pieceAt('가')")
    chk('굴리던 중(중간 칸 %s)에 무대를 바꿨다' % mid, mid is not None and 0 < mid < 6, mid)
    chk('⭐ 돌아오면 서버 자리(6번)에 선다 (예전: 중간 칸에 멈춰 있었다)', at == 6, at)
    chk('돌아온 판에 걷던 표시가 안 남는다', ev("document.querySelectorAll('.dg-piece.dg-moving').length") == 0)
    chk('기다리던 표지판도 걷혔다', ev('(window.dgBusyUntil || 0) <= Date.now()') is True)

    # ════════════════════════════════════════════════════════════════
    print()
    print('=' * 74)
    print('④ 끌려간 자리가 뺏어오기 칸이면 카드에 누가 누구에게서 얼마를 뺏었는지 적는다')
    print('=' * 74)
    reset()
    board('blank')
    post('/api/dicegame/tile', {'id': 5, 'type': 'move', 'label': '싱크홀', 'points': -3})
    post('/api/dicegame/tile', {'id': 2, 'type': 'steal', 'label': '5점씩', 'points': 5})
    post('/api/dicegame/move', {'piece': '가', 'pos': 0})
    open_overlay()
    ev("window.__cards = []; (() => { const el = document.getElementById('dg-card'); new MutationObserver(() => { if (el.classList.contains('show')) window.__cards.push(el.innerText); }).observe(el, { attributes: true, attributeFilter: ['class'] }); })()")
    c, r = post('/api/dicegame/roll', {'piece': '가', 'value': 5})
    af = ((get().get('dicegame') or {}).get('action') or {}).get('after') or {}
    chk('서버: 싱크홀 → 2번 뺏어오기', af.get('to') == 2 and (af.get('steal') or {}).get('taker') == '가', af.get('steal'))
    time.sleep(5.2)
    cards = ev('window.__cards') or []
    chk('⭐ 두 번째 카드에 뺏은 내용이 있다 (예전: 빠져 있었다)',
        len(cards) >= 2 and '+15' in cards[-1] and '−5' in cards[-1], cards)

    # ════════════════════════════════════════════════════════════════
    print()
    print('=' * 74)
    print('⑤ 주사위 점수판은 숫자가 바뀔 때만 다시 그린다 (세어 올라가던 숫자가 안 끊긴다)')
    print('=' * 74)
    same = ev("(() => { const g = globalData.dicegame; renderDiceBoard(g); const a = document.querySelector('#dgb-left .excel-row');"
              " renderDiceBoard(g); const b = document.querySelector('#dgb-left .excel-row'); return !!a && a === b; })()")
    chk('같은 점수로 또 그려도 줄을 새로 만들지 않는다', same is True, same)
    changed = ev("(() => { const g = JSON.parse(JSON.stringify(globalData.dicegame)); const a = document.querySelector('#dgb-left .excel-row');"
                 " g.board[0].pts += 7; renderDiceBoard(g); const b = document.querySelector('#dgb-left .excel-row'); return !!a && a !== b; })()")
    chk('점수가 바뀌면 다시 그린다', changed is True, changed)
finally:
    try:
        if ws:
            ws.close()
    except Exception:
        pass
    proc.kill()
    # ⚠️ 윈도우에선 크롬이 완전히 꺼질 때까지 파일을 쥐고 있어 바로 지우면 일부가 남는다
    #    (2026-10-01 Temp 에 검사용 크롬 폴더 117개 · 4.6GB 가 쌓였다). 꺼질 때까지 기다렸다 몇 번 지운다.
    try:
        proc.wait(timeout=10)
    except Exception:
        pass
    for _ in range(10):
        shutil.rmtree(PROF, ignore_errors=True)
        if not os.path.exists(PROF):
            break
        time.sleep(0.5)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
