# -*- coding: utf-8 -*-
"""🏦 bank-watch(엔젤 입금확인) — 진짜 크롬에 확장을 끼워 **가짜 은행 화면**(bank-watch/test/mock_ibk.html)에서 돌려 본다.

  · 처음 있던 거래는 알리지 않는다(기준만 잡는다)
  · 자동 조회가 [조회] 버튼을 누른다 — 위 메뉴의 '조회' 링크(다른 화면으로 가는 것)는 누르지 않는다
  · 새 입금만 상자에 뜬다 — 출금은 안 뜬다 · 똑같은 입금 두 번도 두 번 뜬다
  · 머리줄 · 몸통이 따로인 표, 조회할 때 alert 를 띄우는 화면도 멈추지 않고 돈다
⚠️ 진짜 은행 · 운영 서버는 건드리지 않는다.
⚠️ 최신 크롬은 명령줄(--load-extension)로 확장을 끼우는 것을 막는다(2026-10 확인: 확장이 안 붙음).
   그래서 가짜 은행 화면이 ?harness=1 일 때 확장과 **같은 파일**(page_hook.js · content.js)을 직접 싣고,
   확장 저장소만 브라우저 저장소로 흉내 낸다. 확장 묶음(manifest) 자체는 manifest 검사로 따로 본다.
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
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(HERE, '..'))
EXT = os.path.join(ROOT, 'bank-watch')
PORT_WEB, PORT_CDP = 5466, 9336
CHROME = os.environ.get('LM_CHROME') or r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:200]) if detail else ''))


try:
    import websocket
except ImportError:
    print('websocket-client 가 없어 건너뜁니다'); sys.exit(0)
if not os.path.exists(CHROME):
    print('크롬이 없어 건너뜁니다'); sys.exit(0)

tmp = tempfile.mkdtemp(prefix='lmtest_bankwatch_')
print('⓪ 확장 묶음(manifest)')
man = json.load(io.open(os.path.join(EXT, 'manifest.json'), encoding='utf-8'))
cs = man.get('content_scripts') or []
chk('기업은행 주소에만 붙는다', all(set(c['matches']) == {'https://mybank.ibk.co.kr/*', 'https://www.ibk.co.kr/*'} for c in cs), [c['matches'] for c in cs])
chk('알림창 고리는 은행 화면 쪽(MAIN) · 문서 시작 때', any(c['js'] == ['page_hook.js'] and c.get('world') == 'MAIN' and c.get('run_at') == 'document_start' for c in cs))
chk('틀(iframe) 안에서도 돈다', all(c.get('all_frames') for c in cs))
chk('권한은 저장소 하나 — 다른 사이트로 보내는 권한 없음(시험판)', man.get('permissions') == ['storage'] and not man.get('host_permissions'))

web = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT_WEB), '--bind', '127.0.0.1'],
                       cwd=EXT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run(label, query, wait_s):
    prof = os.path.join(tmp, 'prof_' + label)
    p = subprocess.Popen([CHROME, '--headless=new', '--remote-debugging-port=%d' % PORT_CDP, '--remote-allow-origins=*',
                          '--user-data-dir=' + prof, '--no-first-run', '--no-default-browser-check',
                          'about:blank'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        pg = None
        for _ in range(60):
            try:
                tabs = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT_CDP, timeout=2).read())
                pg = next((t for t in tabs if t.get('type') == 'page'), None)
                if pg:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        ws = websocket.create_connection(pg['webSocketDebuggerUrl'], timeout=30, suppress_origin=True)
        n = [0]

        def call(method, params=None):
            n[0] += 1
            ws.send(json.dumps({'id': n[0], 'method': method, 'params': params or {}}))
            while True:
                m = json.loads(ws.recv())
                if m.get('method') == 'Page.javascriptDialogOpening':
                    return {'dialog': m['params'].get('message')}
                if m.get('id') == n[0]:
                    return m.get('result') or {}

        def ev(js):
            r = call('Runtime.evaluate', {'expression': js, 'returnByValue': True, 'awaitPromise': True})
            if 'dialog' in r:
                return {'__dialog': r['dialog']}
            return (r.get('result') or {}).get('value')

        call('Page.enable')
        call('Page.navigate', {'url': 'http://127.0.0.1:%d/test/mock_ibk.html?harness=1&awfast=1%s' % (PORT_WEB, query)})
        time.sleep(3.5)
        SH = "document.getElementById('angel-bankwatch') && document.getElementById('angel-bankwatch').shadowRoot"
        st0 = ev("(()=>{const r=%s;return r?r.querySelector('.st').textContent:null})()" % SH)
        ev("%s.querySelector('[data-a=toggle]').click()" % SH)
        time.sleep(wait_s)
        out = ev("""(()=>{const r=%s;return {
              st: r.querySelector('.st').textContent,
              deps: Array.from(r.querySelectorAll('.dep')).map(d=>d.innerText.replace(/\\s+/g,' ')),
              q: window.__queries||0, title: document.title,
              cols: (r.querySelector('.mut + .mut')||{}).textContent||'' }})()""" % SH)
        ws.close()
        return st0, out
    finally:
        p.kill()
        time.sleep(1.5)


try:
    print('① 한 표 · 알림창 없음')
    st0, o = run('a', '', 21)
    chk('켜기 전: 표를 찾았고 자동 조회는 꺼져 있다', bool(st0) and '표를 찾았어요' in st0, st0)
    chk('자동 조회가 [조회]를 여러 번 눌렀다', isinstance(o, dict) and o.get('q', 0) >= 5, o)
    chk('위 메뉴의 \'조회\' 링크(다른 화면 가기)는 안 눌렀다', isinstance(o, dict) and not str(o.get('title', '')).startswith('NAV'), o and o.get('title'))
    deps = (o or {}).get('deps') or []
    chk('새 입금 세 건만 뜬다(처음 있던 거래 · 출금은 안 뜸)', len(deps) == 3, deps)
    chk('최근 것부터: 2만 원 구름빵 → 1천 원 → 1천 원(똑같은 입금 두 번 다)',
        len(deps) == 3 and deps[0].startswith('20,000원') and '구름빵' in deps[0]
        and all(d.startswith('1,000원') and '테스트/안녕' in d for d in deps[1:]), deps)

    print('② 머리줄 · 몸통이 따로인 표 + 조회할 때마다 alert')
    st0, o = run('b', '&split=1&alert=1', 21)
    chk('따로 나뉜 표도 찾는다', bool(st0) and '표를 찾았어요' in st0, st0)
    chk('alert 에 멈추지 않고 계속 조회한다(page_hook)', isinstance(o, dict) and '__dialog' not in o and o.get('q', 0) >= 5, o)
    deps = (o or {}).get('deps') or []
    chk('여기서도 새 입금 세 건', len(deps) == 3, deps)
finally:
    web.kill()
    shutil.rmtree(tmp, ignore_errors=True)

print()
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
