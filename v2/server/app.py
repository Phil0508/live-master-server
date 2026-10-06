# -*- coding: utf-8 -*-
"""🚪 v2 서버 입구 — 주소 · 로그인 · 실시간 연결 · 배포 잠금 · 옛 주소 호환.

실행:  python -m v2.server.app            (저장소 루트에서)
환경:  LM2_DB(기본 v2/data/lm2.db) · LM2_PORT(기본 5300) · ADMIN_PASSWORD · SESSION_SECRET
"""
import asyncio
import os
import time

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth
from .bus import Bus
from .hub import Client, Hub, device
from .store import Store
from . import domain  # noqa: F401  (조각 · 명령 등록)

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.dirname(HERE)
REPO = os.path.dirname(V2)


def create_app(db_path=None, password=None, secret=None, sig_fetch=None):
    db_path = db_path or os.environ.get('LM2_DB') or os.path.join(V2, 'data', 'lm2.db')
    password = password or os.environ.get('ADMIN_PASSWORD') or ''
    secret = secret or os.environ.get('SESSION_SECRET') or ''
    if not password or len(secret) < 16:
        raise SystemExit('ADMIN_PASSWORD 와 SESSION_SECRET(16자 이상)이 필요합니다')

    store = Store(db_path)
    hub = Hub()
    bus = Bus(store, hub)
    from .domain.signatures import Signatures
    bus.sigs = Signatures(fetch=sig_fetch)        # 검사는 가짜 목록을 넣는다
    app = FastAPI(title='라이브 마스터 v2', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.bus, app.state.hub, app.state.store = bus, hub, store
    boot = time.time()

    def authed(req):
        return auth.is_authed(secret, req.cookies, req.headers, req.query_params)

    def answer(res):
        code = 200 if res.get('ok') else int(res.get('code') or 400)
        return JSONResponse(res, status_code=code)

    # ── 로그인 ──
    @app.post('/login')
    async def login(req: Request):
        body = await _json(req)
        if not auth.hmac.compare_digest(str(body.get('password') or ''), password):
            return JSONResponse({'ok': False, 'error': '비밀번호가 틀렸습니다'}, status_code=401)
        r = JSONResponse({'ok': True})
        r.set_cookie(auth.COOKIE, auth.make_cookie(secret), max_age=auth.MAX_AGE, httponly=True, samesite='lax')
        return r

    @app.post('/logout')
    async def logout():
        r = JSONResponse({'ok': True})
        r.delete_cookie(auth.COOKIE)
        return r

    # ── 상태 · 명령 ──
    @app.get('/api/state')
    async def state(req: Request):
        a = authed(req)
        return {'ok': True, 'seq': bus.state.seq, 'now': int(time.time() * 1000), 'authed': a, 'slices': bus.state.snapshot(a)}

    @app.post('/api/cmd')
    async def cmd(req: Request):
        body = await _json(req)
        return answer(await bus.run(str(body.get('type') or ''), body.get('data'), by='http', authed=authed(req)))

    # ── 상태판 · 배포 잠금 ──
    from .domain import health as _health

    @app.get('/api/health')
    async def api_health():
        return _health.view(bus, boot)

    @app.get('/health')
    async def health(req: Request):
        """무인증 상태판 — 브라우저면 페이지, 아니면 JSON(자동 배포 · 검사가 쓴다)."""
        if 'text/html' in (req.headers.get('accept') or ''):
            return FileResponse(os.path.join(V2, 'web', 'health', 'index.html'))
        return _health.view(bus, boot)

    @app.get('/api/time')
    async def server_time():
        """서버 시계(ms) — 방송판이 PC 시계 어긋남을 잰다(타이머 · 대결 끝 시각)."""
        return {'now': int(time.time() * 1000)}

    # ── 🔊 효과음 — 방송판은 로그인이 없다. sounds/ 안의 소리 파일만(옛 /sfx 그대로) ──
    sfx_dir = os.path.join(REPO, 'sounds')
    sfx_exts = {'.mp3', '.m4a', '.ogg', '.wav', '.webm'}

    @app.get('/sfx/list')
    async def sfx_list():
        out = {}
        for root_, _dirs, files in os.walk(sfx_dir):
            for fn in sorted(files):
                stem, ext = os.path.splitext(fn)
                if ext.lower() in sfx_exts:
                    rel = os.path.relpath(root_, sfx_dir)
                    pre = '' if rel in ('.', '') else rel.replace(os.sep, '/') + '/'
                    out.setdefault(pre + stem, pre + fn)
        return {'status': 'success', 'files': out, 'names': sorted(out)}

    @app.get('/sfx/{name:path}')
    async def sfx(name: str):
        full = os.path.normpath(os.path.join(sfx_dir, name))
        if (os.path.splitext(name)[1].lower() not in sfx_exts or not full.startswith(os.path.normpath(sfx_dir) + os.sep)
                or not os.path.isfile(full)):
            return JSONResponse({'error': 'File not found'}, status_code=404)
        return FileResponse(full)

    @app.get('/api/deploy/ok')
    async def deploy_ok():
        """자동 배포가 재시작 전에 묻는다 — 방송 중이면 409(끝날 때까지 기다린다)."""
        if bus.state.get('session').get('live'):
            return JSONResponse({'ok': False, 'error': '방송 중 — 끝난 뒤에 배포합니다'}, status_code=409)
        return {'ok': True}

    @app.get('/api/screens')
    async def screens(req: Request):
        if not authed(req):
            return JSONResponse({'ok': False, 'error': '로그인이 필요합니다'}, status_code=401)
        return {'ok': True, 'screens': hub.screens(), 'dropped': hub.dropped}

    # ── 실시간 ──
    @app.websocket('/ws')
    async def ws(sock: WebSocket):
        await sock.accept()
        a = auth.is_authed(secret, sock.cookies, sock.headers, sock.query_params)
        c = Client(sock, a, sock.query_params.get('kind') or 'other', sock.query_params.get('monitor') == '1',
                   device(sock.headers.get('user-agent'), sock.query_params.get('obs') == '1'))
        # ⚠️ 붙이기 · 통째 보내기 사이에 await 가 없어야 한다 — 그래야 그 뒤 쪽지가 통째 다음에 줄을 선다
        hub.add(c)
        hub.send(c, {'t': 'snapshot', 'seq': bus.state.seq, 'now': int(time.time() * 1000), 'authed': a, 'slices': bus.state.snapshot(a)})
        pump = asyncio.create_task(hub.pump(c))
        try:
            while True:
                msg = await sock.receive_json()
                t = msg.get('t')
                if t == 'resync':
                    hub.send(c, {'t': 'snapshot', 'seq': bus.state.seq, 'now': int(time.time() * 1000), 'authed': a, 'slices': bus.state.snapshot(a)})
                elif t == 'cmd':
                    res = await bus.run(str(msg.get('type') or ''), msg.get('data'), by='ws:' + c.kind, authed=a)
                    hub.send(c, dict(res, t='result', id=msg.get('id')))
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception:
            pass
        finally:
            hub.remove(c)
            pump.cancel()

    # ── 옛 주소 호환(리스너 · 후원 콘솔) ──
    from .domain import legacy
    legacy.mount(app, bus, authed, answer)

    # ── 화면 파일은 매번 새것인지 묻게 한다 ──
    # ⚠️ Cache-Control 이 없으면 브라우저가 JS 모듈을 제멋대로 오래 쥐고 있다(10-07: 고친 util.js 를 새로 고침해도 옛 것을 썼다).
    #    방송 PC · OBS 가 옛 화면을 계속 그리면 고친 게 안 먹는다. no-cache = 쓰기 전에 물어본다(안 바뀌었으면 304 — 가볍다).
    #    글꼴 · 라이브러리(/vendor)는 안 바뀌니 그대로 둔다.
    @app.middleware('http')
    async def no_stale_screens(req: Request, call_next):
        resp = await call_next(req)
        p = req.url.path
        if p.startswith(('/controller', '/overlay', '/shared', '/health', '/streamdeck', '/mobile')) and 'cache-control' not in resp.headers:
            resp.headers['Cache-Control'] = 'no-cache'
        return resp

    # ── 화면 ──
    # 🎛️ /streamdeck — 스트림덱 가상 단추판(단추는 로그인 쿠키로 /api/streamdeck/* 를 부른다)
    for path, folder in (('/overlay', 'overlay'), ('/controller', 'controller'), ('/shared', 'shared'), ('/streamdeck', 'streamdeck')):
        d = os.path.join(V2, 'web', folder)
        os.makedirs(d, exist_ok=True)
        app.mount(path, StaticFiles(directory=d, html=True), name=folder)
    vendor = os.path.join(REPO, 'vendor')
    if os.path.isdir(vendor):
        app.mount('/vendor', StaticFiles(directory=vendor), name='vendor')

    @app.get('/')
    async def root():
        return RedirectResponse('/controller/')

    return app


async def _json(req):
    try:
        b = await req.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


if __name__ == '__main__':
    import uvicorn
    # ws_ping — 소켓 수준 숨쉬기(답 없는 연결을 끊는다). 검사는 LM2_WS_PING 으로 짧게 한다
    ping = float(os.environ.get('LM2_WS_PING', '20'))
    uvicorn.run(create_app(), host=os.environ.get('LM2_HOST', '127.0.0.1'), port=int(os.environ.get('LM2_PORT', '5300')),
                ws_ping_interval=ping, ws_ping_timeout=ping, log_level='warning')
