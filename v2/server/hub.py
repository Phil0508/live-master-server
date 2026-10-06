# -*- coding: utf-8 -*-
"""📡 실시간 연결 — WebSocket.

화면마다 줄(queue) 하나와 보내는 일꾼(task) 하나. 서버는 줄에 넣기만 하고 기다리지 않는다.
- 줄이 꽉 차면(화면이 멈춰 못 받아 감) 그 화면을 끊는다 → 화면은 다시 붙어 통째(snapshot)를 받는다.
- 숨쉬기: 서버가 15초마다 ping 을 보낸다. 화면도 45초 동안 아무것도 못 받으면 스스로 다시 붙는다.
- 공개 조각만 방송판(로그인 없음)으로 간다.
⚠️ 옛 서버(09-30): 연결 하나에 스레드 하나 + 반쯤 끊긴 연결을 몰라 161개가 쌓였다. 여기선 연결이 가볍고,
   보내기가 실패하면 그 자리에서 치운다.
"""
import asyncio
import json
import time

from .state import is_hidden, is_public

QUEUE_MAX = 200
PING_SEC = 15
KINDS = ('overlay', 'controller', 'mobile', 'editor', 'console', 'bot', 'other')   # bot = 진행봇(v2/tools/bot_v2.py)


def device(ua, obs_hint=False):
    """어떤 기기인지 대충만(옛 _sse_device) — 이름표용. 주소 · IP 는 안 남긴다."""
    ua = ua or ''
    if obs_hint or 'OBS/' in ua:
        return 'obs'
    for key, name in (('iPhone', 'iphone'), ('iPad', 'ipad'), ('Android', 'android'), ('Windows', 'windows'), ('Macintosh', 'mac')):
        if key in ua:
            return name
    return 'other'


class Client:
    def __init__(self, ws, authed, kind, monitor=False, dev='other'):
        self.ws = ws
        self.authed = authed
        self.kind = kind if kind in KINDS else 'other'
        self.monitor = monitor          # 미리보기(폰 · 편집기 안의 방송판) — 방송에 나가지 않는다
        self.dev = dev                  # obs · iphone · windows … (점검표가 'OBS 에 붙은 방송판'을 센다)
        self.q = asyncio.Queue(maxsize=QUEUE_MAX)
        self.born = time.time()
        self.last_sent = time.time()
        self.closed = False


class Hub:
    def __init__(self):
        self.clients = set()
        self.dropped = 0

    def add(self, c):
        self.clients.add(c)

    def remove(self, c):
        c.closed = True
        self.clients.discard(c)

    def _push(self, c, msg):
        try:
            c.q.put_nowait(msg)
        except asyncio.QueueFull:
            self.dropped += 1
            c.closed = True                 # 보내는 일꾼이 보고 끊는다
            self.clients.discard(c)

    async def publish(self, seq, changed):
        changed = {k: v for k, v in changed.items() if not is_hidden(k)}
        pub = {k: v for k, v in changed.items() if is_public(k)}
        now = int(time.time() * 1000)          # 서버 시각 — 화면이 카운트다운을 서버 시계에 맞춘다
        full = json.dumps({'t': 'patch', 'seq': seq, 'now': now, 'slices': changed}, ensure_ascii=False)
        part = full if len(pub) == len(changed) else json.dumps({'t': 'patch', 'seq': seq, 'now': now, 'slices': pub}, ensure_ascii=False)
        for c in list(self.clients):
            self._push(c, full if c.authed else part)

    def send(self, c, obj):
        self._push(c, json.dumps(obj, ensure_ascii=False))

    def screens(self):
        now = time.time()
        return [{'kind': c.kind, 'monitor': c.monitor, 'authed': c.authed, 'dev': c.dev,
                 'since_sec': int(now - c.born), 'idle_sec': int(now - c.last_sent)} for c in self.clients]

    async def pump(self, c):
        """한 화면의 보내는 일꾼 — 줄에서 꺼내 보낸다. 15초 동안 보낼 게 없으면 ping."""
        while not c.closed:
            try:
                msg = await asyncio.wait_for(c.q.get(), timeout=PING_SEC)
            except asyncio.TimeoutError:
                msg = json.dumps({'t': 'ping', 'now': int(time.time() * 1000)})
            if c.closed:
                break
            try:
                await c.ws.send_text(msg)
                c.last_sent = time.time()
            except Exception:
                break
        self.remove(c)
        # ⚠️ 줄이 넘쳐 끊을 때도 소켓을 닫아 준다 — 안 닫으면 화면은 붙어 있는 줄 알고 45초를 기다린다
        try:
            await c.ws.close(code=4000)
        except Exception:
            pass
