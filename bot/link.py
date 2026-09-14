# -*- coding: utf-8 -*-
"""🔗 진행봇 계정 연동 — 한 번만 하면 된다.

    python bot/link.py          # 연동하기
    python bot/link.py --check  # 지금 어느 계정에 묶여 있나 확인

브라우저가 열리면 **봇 계정으로** 로그인하고 허용을 누르면 끝입니다.
받은 열쇠는 bot/token.json 에 저장되고, 그 파일은 저장소에 안 올라갑니다.

⚠️ 제일 흔한 실수가 **본계정으로 로그인하는 것**이다. 그래서 연동이 끝나면
   '어느 채널에 묶였는지' 를 반드시 찍어서 보여준다 — 틀렸으면 바로 다시 하면 된다.
⚠️ 표준 라이브러리만 쓴다. 구글 클라이언트 라이브러리를 깔지 않는다.
"""
import argparse
import http.server
import io
import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(HERE, 'token.json')
# 🌐 IPv4 로만 나간다. 이 컴퓨터는 나갈 수 없는 IPv6 주소를 갖고 있어서, 그대로 두면
#    구글에 한 번 붙는 데 48~168초가 걸린다(실측). IPv4 로만 붙으면 0.1초다.
from net import force_ipv4
force_ipv4()

SECRET_FILE = None            # --secrets 로 받은 경로 (없으면 알아서 찾는다)
LOG_PATH = os.path.join(HERE, 'link.log')


class _Tee:
    """화면에 찍는 것을 파일에도 남긴다 — 막혔을 때 무엇 때문인지 봐야 한다.

    ⚠️ 비밀은 안 남는다. 보안 비밀·갱신 토큰은 애초에 화면에 안 찍는다.
    """

    def __init__(self, path, real):
        self.real = real
        try:
            self.f = io.open(path, 'w', encoding='utf-8')
        except Exception:
            self.f = None

    def write(self, s):
        self.real.write(s)
        if self.f:
            try:
                self.f.write(s)
                self.f.flush()
            except Exception:
                pass

    def flush(self):
        self.real.flush()
        if self.f:
            try:
                self.f.flush()
            except Exception:
                pass
AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
API = 'https://www.googleapis.com/youtube/v3'
SCOPE = 'https://www.googleapis.com/auth/youtube.force-ssl'

DONE_HTML = """<!doctype html><meta charset="utf-8">
<title>연동 완료</title>
<body style="font-family:Malgun Gothic,sans-serif;background:#14141a;color:#eee;
             display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center">
  <div style="font-size:64px">%s</div>
  <h1 style="margin:14px 0 6px">%s</h1>
  <p style="color:#aaa">%s</p>
</div></body>"""


def post_form(url, data, deadline=30):
    """구글에 값을 보내고 답을 받는다.

    ⚠️ urlopen 의 timeout 은 '소켓 한 번의 대기' 에만 걸린다. 프록시나 보안 프로그램이
       끼어들어 '연결은 살아 있는데 아무것도 안 오는' 상태가 되면 영원히 기다린다
       (실제로 40분을 서 있었다). 그래서 **바깥에서 시간을 재서** 무슨 일이 있어도 끝낸다.
    """
    box = {}

    def _run():
        try:
            body = urllib.parse.urlencode(data).encode()
            req = urllib.request.Request(
                url, data=body, method='POST',
                headers={'Content-Type': 'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(req, timeout=20) as r:
                box['ok'] = json.loads(r.read().decode('utf-8'))
        except BaseException as e:          # HTTPError 도 여기로 모은다
            box['err'] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(deadline)
    if t.is_alive():
        raise TimeoutError(
            f'구글이 {deadline}초 안에 답하지 않았습니다. 프록시·VPN·백신(nProtect 등)이'
            ' 막고 있을 수 있습니다 — 잠시 끄고 다시 해보세요.')
    if 'err' in box:
        raise box['err']
    return box['ok']


def get_json(url, token, deadline=20):
    """조회도 바깥에서 시간을 잰다 — 여기에 제한이 없어서 연동이 영영 멈춘 적이 있다."""
    box = {}

    def _run():
        try:
            req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
            with urllib.request.urlopen(req, timeout=15) as r:
                box['ok'] = json.loads(r.read().decode('utf-8'))
        except BaseException as e:
            box['err'] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(deadline)
    if t.is_alive():
        raise TimeoutError(f'구글이 {deadline}초 안에 답하지 않았습니다')
    if 'err' in box:
        raise box['err']
    return box['ok']


def load_token():
    try:
        with io.open(TOKEN_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def whoami(access):
    """어느 채널에 묶였는지. 본계정으로 잘못 로그인한 걸 여기서 잡는다."""
    j = get_json(API + '/channels?part=snippet&mine=true', access)
    items = j.get('items') or []
    if not items:
        return None, None
    sn = items[0].get('snippet') or {}
    return sn.get('title'), items[0].get('id')


def from_secret_file(path):
    """구글이 내려준 client_secret_*.json 에서 두 값을 꺼낸다.

    ⚠️ 파일을 저장소로 복사하지 않는다 — 있는 자리에서 읽기만 한다.
    ⚠️ 'installed' 가 데스크톱 앱, 'web' 은 웹 애플리케이션이다. 웹으로 만들면
       되돌아올 주소를 미리 등록해야 해서 이 방식이 막힌다 — 그때는 알려준다.
    """
    with io.open(path, encoding='utf-8') as f:
        j = json.load(f)
    if 'web' in j and 'installed' not in j:
        raise ValueError('웹 애플리케이션으로 만든 열쇠입니다. 데스크톱 앱으로 다시 만들어주세요.')
    o = j.get('installed') or {}
    cid, sec = o.get('client_id', ''), o.get('client_secret', '')
    if not cid or not sec:
        raise ValueError('client_id / client_secret 이 파일에 없습니다')
    return cid, sec


def find_secret_file():
    """따로 안 알려줘도 흔한 자리에서 찾아본다 — bot 폴더 · 지금 폴더 · 바탕화면.

    ⚠️ **가장 최근 것**을 고른다. 이름순으로 골랐더니 몇 달 전 다른 프로젝트에서
       받아둔 옛 파일을 집었다(실제로 그랬다). 그러면 엉뚱한 프로젝트로 연동돼
       원인을 찾기 어렵다. 여러 개면 무엇을 골랐는지 반드시 찍어준다.
    """
    import glob
    spots = [HERE, os.getcwd(), os.path.join(os.path.expanduser('~'), 'Desktop')]
    hits = []
    for d in spots:
        hits += glob.glob(os.path.join(d, 'client_secret*.json'))
    if not hits:
        return None
    hits.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    if len(hits) > 1:
        print('⚠️ 열쇠 파일이 %d 개 있습니다. **가장 최근 것**을 씁니다:' % len(hits))
        for p in hits:
            import time as _t
            print('   %s  %s' % (_t.strftime('%Y-%m-%d %H:%M', _t.localtime(os.path.getmtime(p))),
                                 os.path.basename(p)))
        print('   다른 것을 쓰려면: python bot/link.py --secrets "경로"')
        print()
    return hits[0]


def ask(prompt, current=''):
    if current:
        v = input(f'{prompt} [엔터 치면 그대로: ...{current[-8:]}]: ').strip()
        return v or current
    while True:
        v = input(f'{prompt}: ').strip()
        if v:
            return v


def check():
    t = load_token()
    missing = [k for k in ('client_id', 'client_secret', 'refresh_token') if not t.get(k)]
    if missing:
        print('❌ 아직 연동 안 됐습니다. 없는 값:', ', '.join(missing))
        print('   python bot/link.py 를 먼저 돌려주세요.')
        return 1
    try:
        j = post_form(TOKEN_URL, {'client_id': t['client_id'], 'client_secret': t['client_secret'],
                                  'refresh_token': t['refresh_token'],
                                  'grant_type': 'refresh_token'})
        name, cid = whoami(j['access_token'])
    except urllib.error.HTTPError as e:
        print('❌ 열쇠가 더 이상 안 통합니다:', e.code,
              (e.read() or b'').decode('utf-8', 'replace')[:200])
        # ⏳ 십중팔구 이것이다 — 동의 화면이 '테스트' 면 7일마다 만료된다
        print('   ⏳ 구글 클라우드 > OAuth 동의 화면 이 "테스트" 상태면 7일마다 만료됩니다.')
        print('      "프로덕션으로 게시" 로 바꾸면 안 만료됩니다.')
        print('   python bot/link.py 로 다시 연동해주세요.')
        return 1
    except Exception as e:
        print('❌ 확인 실패:', e)
        return 1
    print(f'✅ 연동돼 있습니다 — 채널: {name}  ({cid})')
    print('   이 이름으로 채팅이 올라갑니다. 본계정이면 다시 연동해주세요.')
    return 0


def link():
    print('=' * 66)
    print('🔗 진행봇 계정 연동')
    print('=' * 66)
    print('구글 클라우드 콘솔에서 만든 **데스크톱 앱** OAuth 클라이언트 값이 필요합니다.')
    print('아직 없으면 bot/README.md 의 2단계를 먼저 봐주세요.')
    print()
    old = load_token()
    # 구글이 내려준 파일이 있으면 그걸 읽는다 — 손으로 옮기다 한 글자 틀리면 원인 찾기가 괴롭다
    sf = SECRET_FILE or find_secret_file()
    cid = csec = ''
    if sf:
        try:
            cid, csec = from_secret_file(sf)
            print(f'📄 열쇠 파일을 찾았습니다: {sf}')
            print(f'   클라이언트 ID …{cid[-28:]}')
            print()
        except Exception as e:
            print(f'⚠️ 열쇠 파일을 못 읽었습니다 ({e}) — 손으로 넣어주세요')
            cid = csec = ''
    if not (cid and csec):
        cid = ask('클라이언트 ID', old.get('client_id', ''))
        csec = ask('클라이언트 보안 비밀', old.get('client_secret', ''))

    # 되돌아올 자리를 잡는다. 데스크톱 앱은 localhost 아무 포트나 쓸 수 있다.
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    # ⚠️ 구글이 준 파일의 redirect_uris 가 ['http://localhost'] 다. 데스크톱 앱은 포트를
    #    아무거나 써도 되지만 이름은 등록된 것과 맞춰둔다. 서버는 127.0.0.1 에 붙어 있고
    #    localhost 는 거기로 풀리므로 같은 곳이다.
    redirect = f'http://localhost:{port}'
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            # ⚠️ 브라우저는 /favicon.ico 같은 것을 먼저 보내기도 한다. 그걸 '응답' 으로
            #    받아버리면 진짜 응답을 놓친다 — code 나 error 가 있는 것만 받는다.
            if 'code' not in q and 'error' not in q:
                self.send_response(204)
                self.end_headers()
                return
            got['code'] = (q.get('code') or [''])[0]
            got['error'] = (q.get('error') or [''])[0]
            ok = bool(got['code'])
            page = DONE_HTML % (('✅', '연동 완료', '이 창은 닫으셔도 됩니다.') if ok else
                                ('❌', '연동 실패', got['error'] or '허용을 누르지 않으셨습니다.'))
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(page.encode('utf-8'))

        def log_message(self, *a):
            pass          # 콘솔을 어지럽히지 않는다

    httpd = http.server.HTTPServer(('127.0.0.1', port), Handler)

    def _serve_until_answer():
        """답이 올 때까지 계속 받는다 — 한 번만 받으면 favicon 하나에 놓친다."""
        while not (got.get('code') or got.get('error')):
            try:
                httpd.handle_request()
            except Exception:
                return

    threading.Thread(target=_serve_until_answer, daemon=True).start()

    url = AUTH_URL + '?' + urllib.parse.urlencode({
        'client_id': cid, 'redirect_uri': redirect, 'response_type': 'code',
        'scope': SCOPE,
        # ⚠️ 둘 다 있어야 **갱신 토큰**이 온다. 없으면 한 시간 뒤에 봇이 조용히 멈춘다.
        'access_type': 'offline', 'prompt': 'consent',
    })
    print()
    print('⚠️  브라우저가 열립니다. **봇 계정으로** 로그인하세요.')
    print('   (본계정으로 로그인하면 본계정 이름으로 채팅이 올라갑니다)')
    print()
    print('   안 열리면 이 주소를 직접 붙여넣으세요:')
    print('   ' + url)
    print()
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print('⏳ 브라우저에서 허용을 누르기를 기다립니다…')
    for _ in range(600):
        if got:
            break
        threading.Event().wait(0.5)
    httpd.server_close()

    if not got.get('code'):
        print('❌ 허용을 못 받았습니다:', got.get('error') or '시간 초과')
        return 1

    print('🔑 열쇠를 받는 중… (구글에 연결합니다)')
    try:
        j = post_form(TOKEN_URL, {'code': got['code'], 'client_id': cid, 'client_secret': csec,
                                  'redirect_uri': redirect, 'grant_type': 'authorization_code'})
    except urllib.error.HTTPError as e:
        _d = (e.read() or b'').decode('utf-8', 'replace')[:400]
        print('❌ 열쇠 교환 실패:', e.code, _d)
        if 'redirect_uri' in _d:
            print('   → 구글 클라우드에서 이 열쇠를 **데스크톱 앱**으로 만들었는지 확인해주세요.')
            print('     (웹 애플리케이션으로 만들면 이 방식이 막힙니다)')
        if 'invalid_client' in _d:
            print('   → 클라이언트 ID·보안 비밀이 서로 다른 프로젝트 것일 수 있습니다.')
            print('     바탕화면에 열쇠 파일이 여러 개면 --secrets 로 콕 집어주세요.')
        if 'invalid_grant' in _d:
            print('   → 허용을 누른 지 오래됐을 수 있습니다(코드는 몇 분이면 만료됩니다).')
            print('     python bot/link.py 를 다시 돌려 바로 허용해주세요.')
        return 1
    except Exception as e:
        # ⚠️ 연결 끊김·시간 초과는 HTTPError 가 아니다. 그대로 두면 시커먼 추적문만 남는다.
        print('❌ 열쇠 교환 중 통신이 막혔습니다:', e)
        print('   인터넷·방화벽·백신을 한 번 보시고 다시 돌려주세요.')
        return 1
    if not j.get('refresh_token'):
        print('❌ 갱신 토큰이 안 왔습니다. 구글 계정의 [보안 → 타사 앱] 에서 이 앱의 접근을')
        print('   지운 뒤 다시 해보세요. (한 번 허용한 계정은 갱신 토큰을 다시 안 줍니다)')
        return 1

    # ⚠️ **먼저 저장한다.** 예전에는 채널 이름을 알아본 뒤에 저장했는데, 그 조회가
    #    멈추는 바람에 정작 제일 중요한 열쇠가 저장되지 않았다(실제로 두 번 그랬다).
    #    채널 이름은 '있으면 좋은 것' 이지 저장을 막을 이유가 없다.
    with io.open(TOKEN_PATH, 'w', encoding='utf-8') as f:
        json.dump({'client_id': cid, 'client_secret': csec,
                   'refresh_token': j['refresh_token']}, f, ensure_ascii=False, indent=2)
    print()
    print('=' * 66)
    print(f'✅ 연동 끝났습니다 — {os.path.relpath(TOKEN_PATH)} 에 저장했습니다')

    name, chan = None, None
    try:
        print('📺 어느 채널에 묶였는지 확인하는 중…')
        name, chan = whoami(j['access_token'])
    except Exception as e:
        print(f'   (확인은 못 했습니다 — {e})')
        print('   나중에 python bot/link.py --check 로 보시면 됩니다.')
    if name:
        print(f'📺 묶인 채널: **{name}**  ({chan})')
        print('   이 이름으로 채팅이 올라갑니다. 본계정이면 다시 연동해주세요.')
    print('⚠️  token.json 은 남에게 보내지 마세요. 이 파일만 있으면 봇 계정으로 글을 쓸 수 있습니다.')
    print('=' * 66)
    print('이제 이렇게 돌리면 진짜로 칩니다:  python bot/announce.py --live')
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='지금 어느 계정에 묶여 있나 확인')
    ap.add_argument('--secrets', metavar='파일',
                    help='구글이 내려준 client_secret_*.json 경로 (안 주면 알아서 찾는다)')
    a = ap.parse_args()
    SECRET_FILE = a.secrets
    sys.stdout = _Tee(LOG_PATH, sys.stdout)      # 막혔을 때 읽을 수 있게 남긴다
    try:
        sys.exit(check() if a.check else link())
    except KeyboardInterrupt:
        print('\n👋 그만뒀습니다.')
        sys.exit(1)
    except Exception:
        # ⚠️ 여기까지 온 예외는 시커먼 추적문만 남기고 끝난다. 파일에도 남겨야 잡는다.
        import traceback
        print('❌ 뜻밖의 오류로 멈췄습니다:')
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
