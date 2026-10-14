# -*- coding: utf-8 -*-
"""🏦 bank-watch(엔젤 입금확인) — 진짜 크롬에 확장을 끼워 **가짜 은행 화면**(bank-watch/test/mock_ibk.html)에서 돌려 본다.

  · 처음 있던 거래는 알리지 않는다(기준만 잡는다)
  · 자동 조회가 [조회] 버튼을 누른다 — 위 메뉴의 '조회' 링크(다른 화면으로 가는 것)는 누르지 않는다
  · 새 입금만 상자에 뜬다 — 출금은 안 뜬다 · 똑같은 입금 두 번도 두 번 뜬다
  · 머리줄 · 몸통이 따로인 표, 조회할 때 alert 를 띄우는 화면도 멈추지 않고 돈다
  · (0.2) 새 입금 · 살아 있음 신호를 확장 배경으로 넘긴다 — 무엇을 넘겼는지 그대로 받아
    **서버 사본**에 넣어 보고 후원 콘솔 추천 카드가 제대로 만들어지는지 본다(형식이 서로 맞는지)
⚠️ 진짜 은행 · 운영 서버는 건드리지 않는다.
⚠️ 최신 크롬은 명령줄(--load-extension)로 확장을 끼우는 것을 막는다(2026-10 확인: 확장이 안 붙음).
   그래서 가짜 은행 화면이 ?harness=1 일 때 확장과 **같은 파일**(page_hook.js · content.js)을 직접 싣고,
   확장 저장소 · 배경으로 넘기기(chrome.runtime.sendMessage)만 흉내 낸다. 배경(background.js)의 보낼 곳 제한 ·
   대기줄은 node 검사(bankwatch_test.js)가, 확장 묶음(manifest)은 아래 manifest 검사가 본다.
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
PROD = 'https://xn--9i1b547a0ublxlz4f.xn--h32bi4v.xn--3e0b707e'
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
chk('기업은행 주소에만 붙는다', all(set(c['matches']) == {'https://mybank.ibk.co.kr/*', 'https://www.ibk.co.kr/*', 'https://kiup.ibk.co.kr/*'} for c in cs), [c['matches'] for c in cs])
chk('알림창 고리는 은행 화면 쪽(MAIN) · 문서 시작 때', any(c['js'] == ['page_hook.js'] and c.get('world') == 'MAIN' and c.get('run_at') == 'document_start' for c in cs))
chk('틀(iframe) 안에서도 돈다', all(c.get('all_frames') for c in cs))
chk('권한은 저장소 하나 · 보낼 곳은 방송 서버와 내 PC 시험 서버뿐',
    man.get('permissions') == ['storage']
    and man.get('host_permissions') == [PROD + '/*', 'http://127.0.0.1/*', 'http://localhost/*'], man.get('host_permissions'))
chk('보내는 일은 배경(background.js)이 한다',
    (man.get('background') or {}).get('service_worker') == 'background.js' and os.path.exists(os.path.join(EXT, 'background.js')))

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
              ln: (r.querySelector('.ln')||{}).textContent||'',
              deps: Array.from(r.querySelectorAll('.dep')).map(d=>d.innerText.replace(/\\s+/g,' ')),
              q: window.__queries||0, title: document.title, sent: window.__sent||[],
              cols: (r.querySelector('.mut + .mut')||{}).textContent||'' }})()""" % SH)
        ws.close()
        return st0, out
    finally:
        p.kill()
        time.sleep(1.5)


INPROC = r'''
import os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
os.environ.update(HEADLESS='1', ADMIN_PASSWORD='sandboxpw', SESSION_SECRET='sandboxsecret123456', SELF_PING='off')
os.environ.pop('NVIDIA_API_KEY', None)
sys.path.insert(0, os.getcwd())
import server
server.init_db()
c = server.app.test_client()
H = {'Authorization': 'Bearer sandboxsecret123456'}
def say(ok, name, detail=''):
    print(('OK ' if ok else 'BAD ') + name + ((' -- ' + str(detail)[:200]) if detail else ''), flush=True)
sent = json.load(open('_sent.json', encoding='utf-8'))
K = c.get('/api/bank/key', headers=H).get_json()['key']
codes = [c.post('/api/bank/deposit', json={'source': 'web', 'deposits': m.get('deposits') or [], 'note': m.get('note')},
                headers={'X-Bank-Key': K}).status_code for m in sent]
say(codes and all(x == 200 for x in codes), '확장이 넘긴 그대로 서버가 받는다(%d번)' % len(codes), codes)
items = c.get('/api/bank/inbox', headers=H).get_json()['items']
say(sorted(i['amount'] for i in items) == [1000, 1000, 20000], '후원 콘솔 추천 카드 세 장(1천 · 1천 · 2만)', [i['amount'] for i in items])
small = [i for i in items if i['amount'] == 1000]
say(all(i['memo'] == '테스트/안녕' and i['holder'] == '홍길동' and i['name'] == '테스트' and i['message'] == '안녕' for i in small),
    '메모 칸(거래내용)과 예금주 칸을 갈라 읽고 메모를 나눈다', [(i['memo'], i['holder'], i['name'], i['message']) for i in small])
big = next((i for i in items if i['amount'] == 20000), {})
say(big.get('how') == 'no_memo' and big.get('name') == '구름빵', '메모가 예금주와 같으면 메모 없이 보낸 입금(금액 · 입금자명만)', big)
'''

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

    print('①-b 방송 서버로 넘기기(0.2)')
    sent = (o or {}).get('sent') or []
    flat = [d for m in sent for d in (m.get('deposits') or [])]
    chk('모두 aw-send 로 넘긴다', sent and all(m.get('t') == 'aw-send' for m in sent), [m.get('t') for m in sent])
    chk('살아 있음 신호(빈 목록)를 보낸다', any(not m.get('deposits') for m in sent), len(sent))
    chk('새 입금 세 건만 넘긴다(처음 있던 거래 · 출금 8천 원은 안 넘김)', sorted(d['amount'] for d in flat) == [1000, 1000, 20000],
        [d.get('amount') for d in flat])
    chk('입금마다 다른 번호(ref) — 똑같은 1천 원 두 번도 따로', len({d['ref'] for d in flat}) == len(flat) == 3, [d.get('ref') for d in flat])
    one = next((d for d in flat if d['amount'] == 1000), {})
    chk('이름/내용 칸은 [머리글, 값] 으로', one.get('fields') == [['거래내용', '테스트/안녕'], ['상대계좌예금주명', '홍길동']], one.get('fields'))
    chk('보내는 것: 번호 · 금액 · 시각 · 이름/내용 칸뿐(잔액 · 줄 전체는 안 보냄)',
        all(sorted(d.keys()) == ['amount', 'fields', 'ref', 'when'] for d in flat), [sorted(d.keys()) for d in flat])
    chk('상자에 \'방송 서버로 보냄 ✓\'', str((o or {}).get('ln', '')).startswith('방송 서버로 보냄'), (o or {}).get('ln'))

    print('①-c 넘긴 그대로 서버 사본에 넣어 보기(형식 맞물림)')
    srv = os.path.join(tmp, 'srv')
    os.makedirs(srv)
    for f in ('server.py', 'show.py'):
        shutil.copy(os.path.join(ROOT, f), srv)
    shutil.copytree(os.path.join(ROOT, 'features'), os.path.join(srv, 'features'), ignore=shutil.ignore_patterns('__pycache__'))
    with open(os.path.join(srv, '_inproc.py'), 'w', encoding='utf-8') as fh:
        fh.write(INPROC)
    with open(os.path.join(srv, '_sent.json'), 'w', encoding='utf-8') as fh:
        json.dump(sent, fh, ensure_ascii=False)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    for k in ('DATABASE_URL', 'NVIDIA_API_KEY'):
        env.pop(k, None)
    p = subprocess.run([sys.executable, '_inproc.py'], cwd=srv, capture_output=True, timeout=300, env=env)
    lines = p.stdout.decode('utf-8', 'replace').splitlines()
    for ln in lines:
        if ln.startswith('OK '):
            chk(ln[3:].split(' -- ')[0], True)
        elif ln.startswith('BAD '):
            chk(ln[4:].split(' -- ')[0], False, ln.split(' -- ', 1)[1] if ' -- ' in ln else '')
    if p.returncode != 0 or not any(ln.startswith(('OK ', 'BAD ')) for ln in lines):
        chk('서버 사본 검사가 끝까지 돌았다', False, p.stderr.decode('utf-8', 'replace')[-800:])

    print('② 머리줄 · 몸통이 따로인 표 + 조회할 때마다 alert')
    st0, o = run('b', '&split=1&alert=1', 21)
    chk('따로 나뉜 표도 찾는다', bool(st0) and '표를 찾았어요' in st0, st0)
    chk('alert 에 멈추지 않고 계속 조회한다(page_hook)', isinstance(o, dict) and '__dialog' not in o and o.get('q', 0) >= 5, o)
    deps = (o or {}).get('deps') or []
    chk('여기서도 새 입금 세 건', len(deps) == 3, deps)

    print('③ 열쇠가 틀렸을 때')
    st0, o = run('c', '&keybad=1', 9)
    chk('상자에 \'열쇠가 맞지 않아요\' — 후원 콘솔에서 다시 복사하라고', '열쇠가 맞지 않아요' in str((o or {}).get('ln', '')), (o or {}).get('ln'))
finally:
    web.kill()
    shutil.rmtree(tmp, ignore_errors=True)

print()
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
