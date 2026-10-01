# -*- coding: utf-8 -*-
"""🌸 끝 화면(엔젤 오락실 B) — 방송판을 브라우저로 열어 실제로 잰다.

대표님(2026-09-30): "종료화면 반투명한 거 없애줘" → "B로 가자"
- 뒤가 비치지 않는다: 뒤에 알록달록한 무늬를 깔아도 바탕 색이 그대로다
- 제일 꽉 찬 경우(다음 방송 문구 · 1등 · 한 방 최고 · 후원자 여덟 분 · 외 N분)도 안전지대(115~954) 안이다
  (폰에서는 그 아래가 채팅에, 위가 제목 줄에 가린다)
- 테마를 바꿔도 모양이 같다(테마 옷을 안 입는다 — 시작 화면처럼)
- 이름이 길면 칸 밖으로 안 넘치고 … 으로 줄인다 · 기록이 없으면 인사 한 줄

pt 서버(5199)가 필요하다. 크롬이 없으면 건너뛴다.
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
SAFE_TOP, SAFE_BOTTOM = 115, 954


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
    print('⚠️ 크롬 또는 websocket-client 가 없어 끝 화면 검사를 건너뜁니다')
    print('통과 0 · 실패 0')
    sys.exit(0)

FULL = {n: {'name': n, 'total': t, 'count': 1} for n, t in
        (('엄청나게긴닉네임을가진후원자님', 1300000), ('재성', 150000), ('영원', 100000), ('코코몽', 50000),
         ('앞뒤', 30000), ('별빛', 20000), ('도토리', 10000), ('하늘', 10000), ('바다', 10000), ('구름', 10000))}


def setup(tally, best, bjs, title):
    post('/api/restore', {'broadcast_active': True, 'reaction_queue': [], 'reaction_mode': False,
                          'bjs': [{'name': n, 'score': s, 'contribution': c} for n, s, c in bjs],
                          'donor_tally': tally, 'donor_rank_amount': True, 'best_single': best})
    return post('/api/screen', {'mode': 'end', 'title': title})


PORT = 9478
PROF = tempfile.mkdtemp(prefix='stend_')
proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                         '--user-data-dir=' + PROF, '--remote-debugging-port=%d' % PORT, '--remote-allow-origins=*', 'about:blank'],
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

    MEASURE = """JSON.stringify((() => {
        const w = document.querySelector('.se-wrap'), c = document.querySelector('.se-card');
        const bg = document.getElementById('ss-end-bg');
        return { shown: !!w && getComputedStyle(w).display !== 'none' && document.getElementById('stage-screen').classList.contains('show'),
                 top: w ? Math.round(w.getBoundingClientRect().top) : null,
                 bottom: c ? Math.round(c.getBoundingClientRect().bottom) : null,
                 over: [...document.querySelectorAll('.se-wrap *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.left < 0 || r.right > 1080); }).length,
                 cut: [...document.querySelectorAll('.se-chip b, .se-big, .se-small, .se-sub')].filter(e => e.scrollWidth > e.clientWidth + 1).map(e => getComputedStyle(e).textOverflow),
                 bg: bg ? getComputedStyle(bg).backgroundColor : null, chips: document.querySelectorAll('.se-chip').length,
                 tiles: document.querySelectorAll('.se-tile').length, text: w ? w.innerText.replace(/\\s+/g, ' ').slice(0, 140) : '' };
    })())"""

    def load():
        send('Page.navigate', url=B + '/overlay.html')
        for _ in range(60):
            time.sleep(0.25)
            if ev("!!(window.globalData && document.querySelector('.se-card'))"):
                break
        time.sleep(1.2)   # 들어오는 움직임(0.7초)이 끝난 뒤에 잰다

    print('=' * 74)
    print('① 제일 꽉 찬 끝 화면도 안전지대(%d~%d) 안' % (SAFE_TOP, SAFE_BOTTOM))
    print('=' * 74)
    setup(FULL, {'name': '엄청나게긴닉네임을가진후원자님', 'amount': 1300000, 'at': 1, 'id': 'x', 'member': '하율'},
          (('하율', 148, 478), ('서아', 134, 387), ('채원', 100, 269), ('유나', 61, 65)),
          '다음 방송은 금요일 밤 9시 스페셜 무대 — 꼭 와 주세요 고마워요')   # 40자 상한 근처
    load()
    m = json.loads(ev(MEASURE) or '{}')
    print('     ' + m.get('text', ''))
    print('     ' + str(ev("JSON.stringify({fonts: document.fonts.status, jua: document.fonts.check('32px Jua'), parts: [...document.querySelector('.se-wrap').children].map(e => e.className + ':' + Math.round(e.getBoundingClientRect().height)), card: [...document.querySelector('.se-card').children].map(e => e.className + ':' + Math.round(e.getBoundingClientRect().height))})")))
    chk('끝 화면이 떴다', m.get('shown'), m)
    chk('두 칸(1등 · 한 방 최고) · 후원자 여덟 분', m.get('tiles') == 2 and m.get('chips') == 8, (m.get('tiles'), m.get('chips')))
    chk('⭐ 위끝이 안전지대 안 (%d 이상)' % SAFE_TOP, (m.get('top') or 0) >= SAFE_TOP, m.get('top'))
    chk('⭐ 아래끝이 채팅선 위 (%d 이하)' % SAFE_BOTTOM, 0 < (m.get('bottom') or 9999) <= SAFE_BOTTOM, m.get('bottom'))
    chk('화면 옆으로 넘치는 것이 없다', m.get('over') == 0, m.get('over'))
    chk('긴 이름은 … 으로 줄인다 (칸 밖으로 안 나간다)', m.get('cut') and all(x == 'ellipsis' for x in m.get('cut')), m.get('cut'))

    print()
    print('=' * 74)
    print('② 뒤가 비치지 않는다 · 테마를 바꿔도 같다')
    print('=' * 74)
    ev("document.documentElement.style.background = 'repeating-linear-gradient(45deg, #e8a33c 0 90px, #3c8ee8 90px 180px)'; 1")
    time.sleep(0.3)
    px = ev("getComputedStyle(document.getElementById('ss-end-bg')).backgroundColor")
    chk('바탕 층은 불투명 분홍 (rgb(255, 225, 238))', px == 'rgb(255, 225, 238)', px)
    shot = send('Page.captureScreenshot', format='png', clip={'x': 0, 'y': 1300, 'width': 40, 'height': 40, 'scale': 1})
    import base64, struct, zlib
    raw = base64.b64decode(shot.get('data') or '')

    # PNG 첫 점을 직접 풀어 본다(외부 모듈 없이) — 무늬가 비치면 분홍이 아닌 색이 섞인다.
    # 첫 줄 첫 점은 어떤 필터든 원래 값 그대로다(왼쪽 · 위가 0 이라서).
    def png_first_pixel(b):
        pos, idat = 8, b''
        while pos < len(b):
            ln = struct.unpack('>I', b[pos:pos + 4])[0]
            if b[pos + 4:pos + 8] == b'IDAT':
                idat += b[pos + 8:pos + 8 + ln]
            pos += 12 + ln
        return tuple(zlib.decompress(idat)[1:4])
    try:
        rgb = png_first_pixel(raw)
    except Exception as e:
        rgb = ('풀기 실패', str(e))
    chk('⭐ 뒤에 무늬를 깔아도 화면에는 바탕색만 (뒤가 안 비친다)', rgb in ((255, 225, 238), (255, 208, 228)), rgb)
    for th in ('hospital', 'halloween'):
        post('/api/data', {'theme': th})
        time.sleep(1.5)
        m2 = json.loads(ev(MEASURE) or '{}')
        chk('테마(%s)를 입어도 같은 모양 · 같은 자리' % th,
            m2.get('bg') == 'rgb(255, 225, 238)' and m2.get('top') == m.get('top') and m2.get('bottom') == m.get('bottom'),
            (m2.get('bg'), m2.get('top'), m2.get('bottom')))
    post('/api/data', {'theme': 'default'})

    print()
    print('=' * 74)
    print('③ 기록이 하나도 없으면 빈 칸 대신 인사 한 줄')
    print('=' * 74)
    setup({}, {'name': '', 'amount': 0}, (('하율', 0, 0), ('서아', 0, 0)), '')
    load()
    m = json.loads(ev(MEASURE) or '{}')
    chk('인사 한 줄만 · 칸 · 칩 없음', '다음 방송에서 또 만나요' in (m.get('text') or '') and m.get('tiles') == 0 and m.get('chips') == 0,
        m.get('text'))
    post('/api/screen', {'mode': 'off'})
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
