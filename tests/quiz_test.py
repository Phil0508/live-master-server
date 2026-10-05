# -*- coding: utf-8 -*-
"""🧩 퀴즈판(초성 · 사자성어) — 2026-10-06 대표님 "방송 화면에서도 띄우고".

여기서 지키는 것
  ① 문제집이 온전하다(초성 100개 넘게 · 사자성어 100개 넘게, 겹침 없음, 사자성어는 한글 네 글자)
  ② [다음 문제] → 퀴즈가 무대에 오르고 칸이 생긴다. 초성은 초성만, 사자성어는 앞 두 글자 + 빈칸 둘
  ③ [힌트 한 글자] → 앞에서부터 한 칸씩 · [정답 공개] → 칸이 다 열린다
  ④ ⭐ 방송판(로그인 없는 쪽)에는 정답 · 분류가 안 간다 — 칸만, 그것도 열린 칸에만 글자
  ⑤ 내 문제 더하기 · 형식 틀린 줄 거르기 · 비우기 · [퀴즈판 내리기] · 통째 저장으로 못 바꿈
  ⑥ 방송판(헤드리스 크롬)에 네모칸이 실제로 뜨고, 열면 글자가 바뀐다 · 무대에서 내리면 사라진다

pt 서버가 필요하다(LM_PT_PORT, 기본 5199). 크롬이 없으면 브라우저 부분은 건너뛴다.
⚠️ 크롬은 이 검사가 띄운 것 하나만 끈다 — 이름으로 찾아 죽이면 앱 브라우저까지 죽는다.
"""
import importlib.util
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


head('① 문제집')
spec = importlib.util.spec_from_file_location('qb', os.path.join(ROOT, 'features', 'quiz_bank.py'))
qb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qb)
ch = [a for a, _ in qb.CHOSUNG]
idm = [a for a, _ in qb.IDIOMS]
chk('초성 100문제 넘게 · 겹침 없음', len(ch) >= 100 and len(ch) == len(set(ch)), len(ch))
chk('사자성어 100문제 넘게 · 겹침 없음', len(idm) >= 100 and len(idm) == len(set(idm)), len(idm))
chk('사자성어는 모두 한글 네 글자 · 뜻이 있다', all(len(a) == 4 and all('가' <= c <= '힣' for c in a) and b for a, b in qb.IDIOMS))
chk('초성 정답은 모두 한글 두 글자 이상 · 분류가 있다', all(len(a) >= 2 and all('가' <= c <= '힣' for c in a) and b for a, b in qb.CHOSUNG))

OV = io.open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8').read()
CT = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
SV = io.open(os.path.join(ROOT, 'server.py'), encoding='utf-8').read()
SH = io.open(os.path.join(ROOT, 'show.py'), encoding='utf-8').read()
head('글자로 — 연결')
chk('무대 목록에 퀴즈', "'hell', 'quiz')" in SH and "'quiz': '퀴즈'" in SH)
chk('통째 저장 · 설정 패치로 못 바꾼다', "'pinball', 'quiz', 'best_single'" in SV and "\n    'quiz',\n" in SV)
QZ = io.open(os.path.join(ROOT, 'features', 'quiz.py'), encoding='utf-8').read()
chk('방송 시작 · 종료 때 나온 문제 목록을 비운다(내 문제는 남긴다)', 'quiz_reset_session(state)' in SV.split('def reset_session_keys(')[1].split('\ndef ')[0]
    and "g.update({'cur': None, 'tiles': [], 'revealed': False, 'used': {k: [] for k in KINDS}})" in QZ)
chk('방송판: 시그니처 재생 · 시작/끝 화면 때 숨긴다', 'body.reaction-mode #quiz-container' in OV and 'body.stage-on #quiz-container' in OV)
chk('방송판: 방송 꺼짐 return 보다 앞에서 그린다', OV.index('qzUpdate(d);') < OV.index('pbUpdate(d.pinball);') + 200)
chk('방송판: 바탕 · 제목 · 남은 초 없이 칸만', '<div id="quiz-container" aria-hidden="true"></div>' in OV)
chk('조종실: 퀴즈 탭 · 단추 넷 · 무대 칩', 'id="tab-quiz"' in CT and "onclick=\"qzNext()\"" in CT and "qzCall('hint')" in CT
    and "qzCall('reveal')" in CT and 'onclick="qzShow(false)"' in CT and "['quiz', '퀴즈']" in CT)
chk('조종실: 주기 갱신 훅', 'try { qzSync(); } catch(e) {}' in CT)
chk('조종실: 방송 화면 줄이 무대 이름을 안다(예전엔 "무대 비어 있음" 으로 떴다)', "hell: '지옥탈출', quiz: '퀴즈' };" in CT)
chk('조종실: 점수 · 정답자 · 남은 초가 없다', '정답!' not in CT[CT.index('id="tab-quiz"'):CT.index('id="tab-pinball"')]
    and '+10초' not in CT[CT.index('id="tab-quiz"'):CT.index('id="tab-pinball"')])

alive = call('GET', '/api/data')[0] == 200
if not alive:
    print('\n⚠️ 서버가 없어 동작 검사를 건너뜁니다')
else:
    _, ST0 = call('GET', '/api/data')
    head('② 다음 문제 — 초성')
    c, r = call('POST', '/api/quiz/next', {'kind': 'chosung'})
    q = r.get('quiz') or {}
    cur = q.get('cur') or {}
    tiles = q.get('tiles') or []
    chk('다음 문제 → 200 · 정답 · 분류는 조종실에 온다', c == 200 and cur.get('answer') and cur.get('note'), (c, cur))
    chk('칸 수 = 정답 글자 수 · 전부 초성(q)', len(tiles) == len(cur.get('answer', '')) and all(t['s'] == 'q' for t in tiles), tiles)
    _ini = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
    chk('초성이 맞다', [t['c'] for t in tiles] == [_ini[(ord(x) - 0xAC00) // 588] for x in cur.get('answer', '')], tiles)
    d = call('GET', '/api/data')[1]
    chk('퀴즈가 무대에 올랐다', (d.get('show') or {}).get('stage') == 'quiz', (d.get('show') or {}).get('stage'))
    chk('조종실(로그인)은 정답을 본다', ((d.get('quiz') or {}).get('cur') or {}).get('answer') == cur.get('answer'))

    head('④ 방송판(로그인 없음)에는 정답이 안 간다')
    cp, pub = call('GET', '/api/data', auth=False)
    pq = pub.get('quiz') or {}
    raw = json.dumps(pub, ensure_ascii=False)
    chk('⭐ 로그인 없는 쪽: cur · 내 문제 · 나온 문제 목록이 없다', cp == 200 and 'cur' not in pq and 'custom' not in pq and 'used' not in pq, list(pq))
    chk('⭐ 로그인 없는 쪽: 정답 글자가 어디에도 없다', cur.get('answer', '#') not in raw)
    chk('로그인 없는 쪽도 칸은 받는다(방송판이 그린다)', pq.get('tiles') == tiles)

    head('③ 힌트 · 정답 공개')
    c, r = call('POST', '/api/quiz/hint')
    t1 = (r.get('quiz') or {}).get('tiles') or []
    chk('힌트 → 첫 칸만 글자로(h)', c == 200 and t1[0] == {'c': cur['answer'][0], 's': 'h'} and all(t['s'] == 'q' for t in t1[1:]), t1)
    cp, pub = call('GET', '/api/data', auth=False)
    chk('힌트로 연 글자만 방송판으로 간다', ((pub.get('quiz') or {}).get('tiles') or [{}])[0].get('c') == cur['answer'][0])
    c, r = call('POST', '/api/quiz/reveal')
    q = r.get('quiz') or {}
    t2 = q.get('tiles') or []
    chk('정답 공개 → 모든 칸이 정답 글자(o)', c == 200 and q.get('revealed') is True and ''.join(t['c'] for t in t2) == cur['answer']
        and all(t['s'] == 'o' for t in t2), t2)
    c, r = call('POST', '/api/quiz/hint')
    chk('공개한 뒤 힌트는 거절(400)', c == 400, (c, r.get('message')))

    head('② 다음 문제 — 사자성어')
    c, r = call('POST', '/api/quiz/next', {'kind': 'idiom'})
    q = r.get('quiz') or {}
    cur2 = q.get('cur') or {}
    t3 = q.get('tiles') or []
    chk('사자성어: 앞 두 글자(g) + 빈칸 둘(b) · 빈칸엔 글자 없음', c == 200 and len(t3) == 4 and [t['s'] for t in t3] == ['g', 'g', 'b', 'b']
        and t3[0]['c'] == cur2['answer'][0] and t3[2]['c'] == '' and t3[3]['c'] == '', t3)
    call('POST', '/api/quiz/hint')
    call('POST', '/api/quiz/hint')
    c, r = call('POST', '/api/quiz/hint')
    chk('빈칸을 다 열면 힌트는 거절(400) — [정답 공개]로', c == 400, (c, r.get('message')))
    c, r = call('POST', '/api/quiz/reveal')
    t4 = (r.get('quiz') or {}).get('tiles') or []
    chk('정답 공개 → 앞 둘은 그대로(g) · 뒤 둘은 금색(o)', [t['s'] for t in t4] == ['g', 'g', 'o', 'o'] and ''.join(t['c'] for t in t4) == cur2['answer'], t4)
    left0 = (r.get('quiz') or {}).get('left', {}).get('idiom')
    c, r = call('POST', '/api/quiz/next', {'kind': 'idiom'})
    chk('한 번 나온 문제는 그날 다시 안 나온다(남은 수가 준다)', (r.get('quiz') or {}).get('left', {}).get('idiom') == left0 - 1
        and (r.get('quiz') or {}).get('cur', {}).get('answer') != cur2['answer'], (left0, (r.get('quiz') or {}).get('left')))

    head('⑤ 내 문제 · 내리기 · 통째 저장')
    c, r = call('POST', '/api/quiz/custom', {'kind': 'idiom', 'text': '검사사자 | 검사용 뜻\n세글자 | 틀림\n일석이조 | 이미 있음\n\n검사두번 | 뜻'})
    chk('내 문제: 네 글자 둘만 들어가고 · 세 글자는 거른다 · 이미 있는 건 건너뛴다', c == 200 and r.get('added') == 2 and len(r.get('bad') or []) == 1
        and (r.get('quiz') or {}).get('custom', {}).get('idiom') == 2, (c, r.get('added'), r.get('bad')))
    c, r = call('POST', '/api/quiz/custom', {'kind': 'chosung', 'text': '검사단어 | 검사\nA | 영어 한 글자'})
    chk('초성 내 문제: 한글 두 글자 이상만', c == 200 and r.get('added') == 1 and len(r.get('bad') or []) == 1, (r.get('added'), r.get('bad')))
    c, r = call('POST', '/api/quiz/custom', {'kind': 'nope', 'text': 'x'})
    chk('없는 종류는 400', c == 400)
    call('POST', '/api/data', dict(call('GET', '/api/data')[1], quiz={'tiles': [], 'custom': {'chosung': [], 'idiom': []}}))
    d = call('GET', '/api/data')[1]
    chk('통째 저장으로 퀴즈를 못 바꾼다(내 문제가 남는다)', len(((d.get('quiz') or {}).get('custom') or {}).get('idiom') or []) == 2)
    c, r = call('POST', '/api/quiz/custom', {'kind': 'idiom', 'mode': 'clear'})
    chk('내 문제 비우기', c == 200 and r.get('cleared') == 2 and (r.get('quiz') or {}).get('custom', {}).get('idiom') == 0, r.get('cleared'))
    call('POST', '/api/quiz/custom', {'kind': 'chosung', 'mode': 'clear'})
    c, r = call('POST', '/api/quiz/show', {'on': False})
    d = call('GET', '/api/data')[1]
    chk('퀴즈판 내리기 → 무대가 빈다', c == 200 and r.get('on') is False and (d.get('show') or {}).get('stage') is None, (c, (d.get('show') or {}).get('stage')))
    c, r = call('POST', '/api/quiz/show', {'on': True})
    chk('다시 띄우기 → 무대에 오른다', c == 200 and r.get('on') is True)
    c, r = call('POST', '/api/quiz/next', {}, auth=False)
    chk('로그인 없이 문제를 못 낸다', c not in (200, 0), c)

    # ⑥ 방송판에 실제로 뜨는가
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
        print('\n⚠️ 크롬 · websocket-client 가 없어 방송판 검사를 건너뜁니다')
    else:
        head('⑥ 방송판(헤드리스 크롬)')
        _s = socket.socket(); _s.bind(('127.0.0.1', 0)); PORT = _s.getsockname()[1]; _s.close()
        PROF = tempfile.mkdtemp(prefix='quizt_')
        proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                                 '--user-data-dir=' + PROF, '--remote-debugging-port=%d' % PORT, '--remote-allow-origins=*', 'about:blank'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws = None
        try:
            tabs = None
            for _ in range(80):
                try:
                    tabs = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=2).read())
                    if any(t.get('type') == 'page' for t in tabs):
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            if not tabs or not any(t.get('type') == 'page' for t in tabs):
                raise RuntimeError('검사용 크롬이 뜨지 않았다(포트 %d)' % PORT)
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
            c, r = call('POST', '/api/quiz/next', {'kind': 'chosung'})
            ans = ((r.get('quiz') or {}).get('cur') or {}).get('answer', '')
            send('Page.navigate', url=B + '/overlay.html')
            for _ in range(80):
                time.sleep(0.25)
                if ev("document.querySelectorAll('#quiz-container .qz-tile').length > 0"):
                    break
            time.sleep(0.6)
            SNAP = """JSON.stringify((() => { const b = document.getElementById('quiz-container');
                const r = b.getBoundingClientRect();
                return { on: b.classList.contains('on'), vis: getComputedStyle(b).visibility, n: b.children.length,
                         text: [...b.children].map(e => e.textContent).join(''), cls: [...b.children].map(e => e.className.replace('qz-tile ', '').replace(' pop', '')),
                         w: Math.round(b.children[0] ? b.children[0].getBoundingClientRect().width : 0), top: Math.round(r.top) }; })())"""
            s1 = json.loads(ev(SNAP) or '{}')
            chk('⭐ 방송판에 네모칸이 뜬다(칸 수 = 글자 수 · 칸 120)', s1.get('on') is True and s1.get('n') == len(ans) and s1.get('w') == 120, s1)
            chk('⭐ 방송판에는 초성만 — 정답 글자가 없다', s1.get('text') and not any(ch_ in (s1.get('text') or '') for ch_ in ans), (s1.get('text'), ans))
            call('POST', '/api/quiz/reveal')
            for _ in range(20):
                time.sleep(0.25)
                if ev("[...document.querySelectorAll('#quiz-container .qz-tile')].every(e => e.classList.contains('s-o'))"):
                    break
            s2 = json.loads(ev(SNAP) or '{}')
            chk('⭐ 정답 공개 → 방송판 칸이 정답 글자 · 금색(s-o)', s2.get('text') == ans and all(x == 's-o' for x in s2.get('cls') or ['x']), s2)
            call('POST', '/api/quiz/show', {'on': False})
            for _ in range(20):
                time.sleep(0.25)
                if not ev("document.getElementById('quiz-container').classList.contains('on')"):
                    break
            s3 = json.loads(ev(SNAP) or '{}')
            chk('퀴즈판 내리기 → 방송판에서 사라진다', s3.get('on') is False, s3)
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
    # 무대 · 퀴즈를 처음 모습으로(다른 검사와 섞이지 않게)
    call('POST', '/api/quiz/show', {'on': False})

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
