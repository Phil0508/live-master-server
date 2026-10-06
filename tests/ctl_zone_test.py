# -*- coding: utf-8 -*-
"""⚙ 조종실 ↔ 설정 화면 — 방송 중에 누르는 것만 조종실에, 세부 설정은 설정 화면에.

대표님(2026-10-02): "진짜로 누르는 것들은 조정실에 냅두고 세부사항들 전용 페이지를 만들어서 거기에 다 몰아넣자"
나눈 기준 = 방송 3번의 클릭 기록(Supabase ui_clicks, 2,515번):
  ⚙ 설정으로: 시스템 · 공지 · 이펙트(네온 · 8번 열고 1번) · 특별 후원자(7번 열고 0번) · 진행봇(8번 열고 0번)
              지옥·퇴근 탭의 노래방 · 계좌 고액후원 영상 · 번외 임시 게임판 (0번)
  조종실에 남김: 룰렛의 선관위 리모컨(입력칸이라 기록엔 0 이지만 31번 열었다) · 로그(9/30 에도 14번 봤다)

여기서 지키는 것
  ① 조종실엔 방송용 탭만 — 설정용 탭 · ⋯ 는 안 보인다
  ② 설정 화면엔 설정용 탭만 — 오른쪽 칸(대기함 · 콘솔) · 방송 화면 줄은 숨긴다
  ③ 같은 화면 안에서 바꾼다(조종실을 하나 더 띄우지 않는다) · 새로 열면 늘 조종실부터
  ④ 어디서 불러도(명령창 · 안내 단추) 그 탭이 있는 화면으로 같이 넘어간다
  ⑤ 방송 시작 전에도 설정 화면이 열린다
  ⑥ 반 화면(1920 의 절반 ~945px)에서도 새 옷 · 오른쪽 칸 — 폭 따라 260~380px
pt 서버(5199)가 필요하다. 크롬이 없으면 브라우저 부분은 건너뛴다.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
try:
    import websocket
except Exception:
    websocket = None

ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
PORT = int(os.environ.get('LM_PT_PORT', '5199'))
B = 'http://127.0.0.1:%d' % PORT
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:160]) if detail else ''))


def head(s):
    print()
    print('=' * 74)
    print(s)
    print('=' * 74)


CT = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()

head('① 어느 칸이 어디로 가는지는 HTML 이 정한다(data-zone)')
for ds in ('공지', '시스템', '이펙트', '특별후원', '진행봇'):
    m = re.search(r'<button[^>]*data-s="%s"[^>]*>' % ds, CT)
    chk('탭 [%s] → 설정 화면' % ds, bool(m) and 'data-zone="setup"' in m.group(0), m.group(0)[:90] if m else '없음')
for ds in ('랭킹', 'BGM', '대결', '룰렛', '슬롯', '주사위', '시그뒤집기', '지옥·퇴근', '핀볼', '로그'):
    m = re.search(r'<button[^>]*data-s="%s"[^>]*>' % ds, CT)
    chk('탭 [%s] → 조종실에 남는다' % ds, bool(m) and 'data-zone="setup"' not in m.group(0), m.group(0)[:90] if m else '없음')
mode = CT[CT.index('<div id="tab-mode"'):CT.index('<div id="tab-mode"') + 12000]
chk('지옥·퇴근 탭: 노래방 · 계좌 영상 · 번외 판은 설정 화면으로',
    mode.count('class="group-box" data-zone="setup"') == 2 and 'id="extra-game-banner" data-zone="setup"' in mode)
chk('지옥·퇴근 탭: 지옥탈출 · 퇴근전쟁은 조종실에', 'id="hell-box" data-zone' not in CT and 'id="home-race-box" data-zone' not in CT)
chk('룰렛 선관위 리모컨은 조종실에(31번 열었다)', 'id="roulette-remote-card" data-zone' not in CT)
chk('조종실 쪽 [⚙ 설정] · 설정 쪽 [조종실로] · [모드 설정] 단추',
    'data-s="설정" onclick="ctlView(\'setup\')" data-zone="live"' in CT
    and 'data-s="조종실로" onclick="ctlView(\'live\')" data-zone="setup"' in CT
    and 'data-s="모드설정" onclick="openTab(event, \'tab-mode\')" data-zone="setup"' in CT)
chk('방송 시작 전 화면에도 [⚙ 설정]', "onclick=\"ctlView('setup')\"" in CT[CT.index('id="setup-broadcast-area"'):])

head('② 모양 규칙')
css = CT[CT.index('<style id="view-zone-css">'):CT.index('</style>', CT.index('<style id="view-zone-css">'))]
chk('조종실에선 설정 칸을, 설정 화면에선 방송 칸을 숨긴다',
    'body:not(.view-setup) [data-zone="setup"] { display: none !important; }' in css
    and 'body.view-setup [data-zone="live"] { display: none !important; }' in css)
chk('설정 화면: 오른쪽 칸 · 방송 화면 줄 숨김 · 한 칸으로 넓게',
    'body.view-setup #shell-rail' in css and '#show-bar' in css and 'grid-template-columns: minmax(0, 1fr) !important' in css)
chk('설정 화면: 방송 전에도 열린다', 'body.view-setup #active-broadcast-area { display: block !important; }' in css)
chk('후원 콘솔 [송출]: 보내는 중엔 또 안 보낸다 · 이름 칸 엔터는 한글 조합이 끝난 뒤',
    "if (_rb && _rb.disabled) return;" in CT[CT.index('async function railSend()'):CT.index('async function railSend()') + 300]
    and "onkeydown=\"if(event.key==='Enter'&&!event.isComposing)railSend()\"" in CT)
chk('설정 화면: 목표 달성 알림은 안 숨긴다 · 미확인 후원 [🔔 N건] 단추가 있다',
    'body.view-setup #goal-alert-box' not in css and 'id="setup-pend"' in CT and "document.getElementById('setup-pend')" in CT)
chk('조종실: ⋯ 를 없애고 후원 콘솔 · 전광판을 늘 보인다(⋯ 를 방송 3번에 65번 눌렀다)',
    'body:not(.view-setup) .tabs .tab-btn.tab-dots { display: none !important; }' in css
    and 'body:not(.view-setup) .tabs-2row a.tab-x { display: contents !important; }' in css)
chk('규칙이 새 옷 규칙보다 뒤에 있다(같은 무게면 뒤가 이긴다)', CT.index('<style id="view-zone-css">') > CT.index('<style id="skin-glass-css">'))

head('③ 같은 화면 안에서 바꾼다 · 새로 열면 늘 조종실부터')
fn = CT[CT.index('const CTL_SETUP_ONLY'):CT.index('function ctlView(')+1400]
chk("설정 화면 전용 탭 목록", "const CTL_SETUP_ONLY = ['tab-system', 'tab-notice', 'tab-neon', 'tab-vip', 'tab-bot'];" in CT)
chk('openTab 이 그 탭이 있는 화면으로 같이 넘어간다', 'function openTab(evt, tabId) { try { ctlZoneFor(tabId); } catch (e) {}' in CT)
chk('설정 화면을 기억하지 않는다(새로 열면 조종실)', "localStorage" not in fn and 'sessionStorage' not in fn and 'location.hash' not in fn)
chk('조종실을 새 창으로 하나 더 띄우지 않는다', "window.open" not in fn)


def chrome_path():
    for p in (os.environ.get('LM_CHROME') or '',
              r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
              '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'):
        if p and os.path.exists(p):
            return p
    return None


CHROME = chrome_path()
if not CHROME or websocket is None:
    print('\n(브라우저 부분 건너뜀 — %s)' % ('크롬 없음' if not CHROME else 'pip install websocket-client'))
else:
    head('④ 진짜 브라우저로 눌러 본다 (새 옷 1440 · 옛 모습 1440 · 폰 420)')
    now = int(time.time() * 1000)
    urllib.request.urlopen(urllib.request.Request(B + '/api/restore', json.dumps({
        'broadcast_active': True, 'broadcast_started_at': now - 3600000,
        'bjs': [{'name': '앙앙', 'score': 10, 'contribution': 10}, {'name': '밍밍', 'score': 5, 'contribution': 5}],
        'bottom_fixed': {'name': '운영비', 'score': 0}, 'logs': [], 'reaction_queue': [], 'pending_donations': []}).encode(), H),
        timeout=20).read()
    CPORT = 9545
    PROF = tempfile.mkdtemp(prefix='lmtest_ctlzone_')
    proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                             '--mute-audio', '--user-data-dir=' + PROF, '--remote-debugging-port=%d' % CPORT,
                             '--remote-allow-origins=*', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    errs = []
    ws = None
    try:
        for _ in range(60):
            try:
                tabs = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % CPORT, timeout=2).read())
                break
            except Exception:
                time.sleep(0.3)
        ws = websocket.create_connection(next(t for t in tabs if t.get('type') == 'page')['webSocketDebuggerUrl'], timeout=90)
        st = {'id': 0}

        def send(m, **pa):
            st['id'] += 1
            ws.send(json.dumps({'id': st['id'], 'method': m, 'params': pa}))
            while True:
                x = json.loads(ws.recv())
                if x.get('method') == 'Runtime.exceptionThrown':
                    d = x['params']['exceptionDetails']
                    errs.append((d.get('exception') or {}).get('description', d.get('text', ''))[:200])
                if x.get('id') == st['id']:
                    return x.get('result', {})

        def ev(e):
            return (send('Runtime.evaluate', expression=e, returnByValue=True, awaitPromise=True).get('result') or {}).get('value')

        VIS = ("(sel)=>{const e=document.querySelector(sel); if(!e) return false; const r=e.getBoundingClientRect();"
               " return getComputedStyle(e).display!=='none' && r.width>0 && r.height>0;}")
        BTNS = ("[...document.querySelectorAll('.tabs .tab-btn')].filter(b=>{const r=b.getBoundingClientRect();"
                " return r.width>0&&r.height>0;}).map(b=>b.dataset.s)")
        send('Page.enable'); send('Runtime.enable')
        send('Page.navigate', url=B + '/login'); time.sleep(1.5)
        ev("fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:'sandboxpw'})}).then(r=>r.status)")
        for skin, w in (('glass', 1440), ('classic', 1440), ('glass', 420)):
            tag = '%s %d' % ('새 옷' if skin == 'glass' else '옛 모습', w)
            send('Emulation.setDeviceMetricsOverride', width=w, height=900 if w > 600 else 844, deviceScaleFactor=1, mobile=w < 768)
            ev("localStorage.setItem('ctl_skin','%s')" % skin)
            send('Page.navigate', url=B + '/controller'); time.sleep(6)
            b = ev(BTNS) or []
            chk('[%s] 새로 열면 조종실 — 설정용 탭 없음 · [⚙ 설정] 있음' % tag,
                not ev("document.body.classList.contains('view-setup')")
                and not any(x in b for x in ('시스템', '공지', '이펙트', '특별후원', '진행봇', '더보기')) and '설정' in b, b)
            ev("[...document.querySelectorAll('.tabs .tab-btn')].find(x=>x.dataset.s==='설정').click()"); time.sleep(1.2)
            b = ev(BTNS) or []
            chk('[%s] ⚙ 설정 → 설정용 탭만 · 시스템이 열린다' % tag,
                all(x in b for x in ('조종실로', '공지', '시스템', '이펙트', '특별후원', '진행봇', '모드설정'))
                and not any(x in b for x in ('랭킹', '대결', '로그', '설정'))
                and ev("(%s)('#tab-system')" % VIS) and not ev("(%s)('#shell-rail')" % VIS), b)
            ev("[...document.querySelectorAll('.tabs .tab-btn')].find(x=>x.dataset.s==='모드설정').click()"); time.sleep(0.6)
            chk('[%s] 모드 설정 → 노래방 · 번외 판만(지옥탈출은 조종실에)' % tag,
                ev("(%s)('#extra-game-banner')" % VIS) and not ev("(%s)('#hell-box')" % VIS))
            ev("[...document.querySelectorAll('.tabs .tab-btn')].find(x=>x.dataset.s==='조종실로').click()"); time.sleep(0.8)
            chk('[%s] 조종실로 → 랭킹' % tag, not ev("document.body.classList.contains('view-setup')")
                and ev("document.getElementById('tab-ranking').classList.contains('active')"))
            ev("openTabById('tab-bot')"); time.sleep(0.6)
            chk('[%s] 조종실에서 진행봇을 부르면 설정 화면으로 같이' % tag,
                ev("document.body.classList.contains('view-setup')") and ev("(%s)('#tab-bot')" % VIS))
            # ⭐ 설정 화면에선 대기함(오른쪽 칸)이 숨는다 — 미확인 후원이 들어오면 머리줄에 [🔔 N건] (10-06 점검)
            st_ = ev("fetch('/api/donation',{method:'POST',headers:{'Content-Type':'application/json'},"
                     "body:JSON.stringify({name:'설정점검',amount:1000,message:'',tx_id:'zone_'+Date.now()})}).then(r=>r.status)")
            sp_ = None
            for _ in range(16):
                time.sleep(0.4)
                sp_ = ev("(() => { const e = document.getElementById('setup-pend'); if (!e) return null; const r = e.getBoundingClientRect();"
                         " return [getComputedStyle(e).display !== 'none' && r.width > 0 && r.height > 0, (e.querySelector('b') || {}).textContent,"
                         " (document.getElementById('pending-count-badge') || {}).textContent]; })()")
                if sp_ and sp_[0]:
                    break
            chk('[%s] ⭐ 설정 화면에서도 미확인 후원이 보인다(머리줄 🔔 N건 = 대기함 수)' % tag,
                st_ == 200 and bool(sp_) and sp_[0] and (sp_[1] or '') + '건' == sp_[2], (st_, sp_))
            ev("openTabById('tab-match')"); time.sleep(0.6)
            chk('[%s] 설정 화면에서 대결을 부르면 조종실로 같이' % tag,
                not ev("document.body.classList.contains('view-setup')") and ev("(%s)('#tab-match')" % VIS))
        # 🪟 반 화면 — 대표님(2026-10-02) "1920 인데 절반 전용으로도 만들어서 유동적으로"
        #    1920 을 둘로 나누면 창 ~945px. 예전엔 1280 아래면 옛 모습이 되고 오른쪽 칸(후원 콘솔)이 사라졌다.
        MEAS = """(()=>{
          const tr=document.querySelector('#tab-ranking .table-responsive'), t=tr&&tr.querySelector('table');
          const rail=document.getElementById('shell-rail'), rb=rail.getBoundingClientRect();
          const badge=document.querySelector('#pending-list .audit-badge');
          return { glass: getComputedStyle(document.querySelector('.tabs')).position==='fixed',
                   rail: getComputedStyle(rail).display!=='none' ? Math.round(rb.width) : 0,
                   pendingInRail: document.getElementById('pending-box').parentElement.id==='shell-rail',
                   tableFits: t ? t.scrollWidth <= tr.clientWidth + 1 : null,
                   pageFits: document.documentElement.scrollWidth <= innerWidth };
        })()"""
        for skin, w, want_glass, rail_lo, rail_hi in (('glass', 945, True, 260, 300), ('glass', 1100, True, 300, 340),
                                                       ('classic', 945, False, 260, 300), ('glass', 1440, True, 380, 380)):
            send('Emulation.setDeviceMetricsOverride', width=w, height=980, deviceScaleFactor=1, mobile=False)
            ev("localStorage.setItem('ctl_skin','%s')" % skin)
            send('Page.navigate', url=B + '/controller'); time.sleep(5)
            m = ev(MEAS) or {}
            tag = '%s %d' % ('새 옷' if skin == 'glass' else '옛 모습', w)
            chk('[%s] %s · 오른쪽 칸(후원 콘솔 · 대기함) %d~%dpx' % (tag, '새 옷이 입혀진다' if want_glass else '옛 모습 그대로', rail_lo, rail_hi),
                m.get('glass') == want_glass and rail_lo <= (m.get('rail') or 0) <= rail_hi and m.get('pendingInRail'), m)
            chk('[%s] 점수판이 칸 안에 들어온다 · 가로로 안 넘친다' % tag, m.get('tableFits') and m.get('pageFits'), m)
        chk('JS 오류 없음', not errs, errs[:3])
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass
        for _ in range(10):      # 윈도우에선 크롬이 꺼질 때까지 파일을 쥐고 있다
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
