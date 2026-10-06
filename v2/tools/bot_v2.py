# -*- coding: utf-8 -*-
"""🤖 진행봇 v2 — 옛 진행봇(bot/announce.py)의 '무엇을 언제 말할까' 를 **그대로 빌려** 쓰고, 붙는 곳만 v2 로 바꾼 것.

    v2 서버 ──WebSocket(/ws: 통째 → 바뀐 조각)──> 이 프로그램 ──(옛 모양으로 바꿔서)──> 옛 봇의 판단 · 말하기 ──> 유튜브

⚠️ 옛 봇 코드는 **복사하지 않는다.** bot/announce.py 를 불러와 Bot 을 이어받고(_listen 하나만 바꾼다),
   v2 조각은 v2/tools/oldshape.py 가 옛 상태 모양으로 바꾼다. 문구표(bot/messages.json) · 말수 설정(bot/config.json)도
   옛 것을 **읽기만** 한다 → 대표님이 문구를 한 곳에서 고치면 옛 봇 · v2 봇이 같이 바뀐다.
⚠️ bot/announce.py 를 불러오면 두 가지가 일어난다(그 파일 맨 위): 화면 글자를 utf-8 로 · 이 프로그램의 연결을 IPv4 로(force_ipv4).
   둘 다 이 프로그램 안에서만이다. 인자 읽기 · 유튜브 붙기는 옛 main() 안이라 불러오기만으로는 안 일어난다.
⚠️ 옛 봇과 **같이 --live 로 돌리지 말 것** — 같은 채팅에 같은 말을 두 번 친다(갈아탈 때 옛 livemaster-bot 을 먼저 끈다).

로그인(위에서부터 먼저 있는 것):
  1) BOT_V2_TOKEN      — v2 서버의 SESSION_SECRET 과 같은 값(Bearer)
  2) SESSION_SECRET    — v2 서버와 같은 env 파일을 쓰면 이것만으로 된다(Bearer)
  3) ADMIN_PASSWORD    — POST /login 으로 쿠키(lm2)를 받아 붙는다
  ⚠️ 로그인이 안 되면 설정 조각(announce_bot, 비공개)이 안 온다 → 78 로 끝낸다(시간이 지난다고 고쳐지지 않는다).
그 밖의 환경변수:
  BOT_V2_SERVER  서버 주소(기본 http://127.0.0.1:${LM2_PORT:-5300}) · BOT_V2_DRYLOG 입 막음 기록 파일(기본 v2/data/bot_dryrun.log)
  BOT_V2_CONFIG / BOT_V2_MESSAGES  말수 설정 · 문구표 파일(기본 bot/config.json · bot/messages.json)
  BOT_INTERVAL · BOT_IDLE · YT_CHANNEL_ID · YT_VIDEO_ID · YT_LIVE_CHAT_ID — 옛 봇과 같은 뜻

사용(저장소 루트에서):
    python -m v2.tools.bot_v2            # 입 막고 돌리기 — v2/data/bot_dryrun.log 에만 남긴다 (기본)
    python -m v2.tools.bot_v2 --once     # 붙어서 통째 한 번 받고 끝 (연결 · 로그인 확인용)
    python -m v2.tools.bot_v2 --live     # 진짜로 유튜브에 친다 (bot/youtube.py · bot/token.json 을 그대로 쓴다)
"""
import argparse
import http.cookiejar
import json
import os
import socket
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.dirname(HERE)
REPO = os.path.dirname(V2)
BOT_DIR = os.path.join(REPO, 'bot')
for _p in (REPO, BOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import announce as A                        # noqa: E402  옛 봇(bot/announce.py) — 판단 · 문구 · 말하기
from v2.tools.oldshape import to_old        # noqa: E402

DRY_PATH = os.path.join(V2, 'data', 'bot_dryrun.log')
RECV_TIMEOUT = 45          # 서버가 15초마다 ping 쪽지를 보낸다 — 45초 동안 아무것도 없으면 끊고 다시 붙는다(화면과 같은 규칙)
MAX_MSG = 16 * 1024 * 1024
EX_CONFIG = 78


def ws_url(server):
    s = server.rstrip('/')
    if s.startswith('https://'):
        s = 'wss://' + s[8:]
    elif s.startswith('http://'):
        s = 'ws://' + s[7:]
    return s + '/ws?kind=bot'


def auth_headers(server, env=None):
    """붙을 때 실을 머리말 — (머리말, 무엇으로 로그인했나). 아무것도 없으면 ({}, '')."""
    env = os.environ if env is None else env
    tok = (env.get('BOT_V2_TOKEN') or env.get('SESSION_SECRET') or '').strip()
    if tok:
        return {'Authorization': 'Bearer ' + tok}, 'bearer'
    pw = env.get('ADMIN_PASSWORD') or ''
    if not pw:
        return {}, ''
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    req = urllib.request.Request(server.rstrip('/') + '/login', data=json.dumps({'password': pw}).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        op.open(req, timeout=15).read()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return {}, 'bad_password'           # 비밀번호가 틀렸다 — 다시 붙어도 똑같다(서버가 꺼진 것과 다르다)
        raise
    for c in cj:
        if c.name == 'lm2':
            return {'Cookie': 'lm2=' + c.value}, 'cookie'
    return {}, ''


class V2Bot(A.Bot):
    """옛 Bot 그대로 — 받는 곳(_listen)만 v2 WebSocket. 판단(detect) · 시계 안내 · 질문 · 말하기(_tick/_say)는 옛 코드가 한다."""

    def __init__(self, cfg, tpl, live=False):
        super().__init__(cfg, tpl, live=live)
        self.dry_path = os.environ.get('BOT_V2_DRYLOG') or DRY_PATH     # ⚠️ 옛 bot/dryrun.log 와 섞지 않는다
        self.slices, self.seq, self.resyncing = None, 0, False
        self.exit_code = 0
        self.yt_note = ''
        self._warned = set()

    def _warn_once(self, key, text):
        if key not in self._warned:
            self._warned.add(key)
            print(text, flush=True)

    def _listen(self, once=False):
        from websockets.sync.client import connect     # 서버 venv 에 이미 있다(toon_listener · requirements.txt)
        headers, how = auth_headers(self.cfg['server'])
        if not headers:
            print('❌ ADMIN_PASSWORD 가 서버와 다릅니다' if how == 'bad_password' else
                  '❌ 로그인할 값이 없습니다 — BOT_V2_TOKEN · SESSION_SECRET · ADMIN_PASSWORD 중 하나가 필요합니다', flush=True)
            self.stop, self.exit_code = True, EX_CONFIG
            return
        url = ws_url(self.cfg['server'])
        print(f'📡 {url} 에 붙는 중… (로그인: {how})', flush=True)
        with connect(url, additional_headers=headers, open_timeout=15, max_size=MAX_MSG) as ws:
            print('📡 붙었습니다.' + ('' if self.live else f'  (입 막음 — {self.dry_path} 에만 남깁니다)'), flush=True)
            self.slices, self.resyncing = None, False
            while not self.stop:
                msg = json.loads(ws.recv(timeout=RECV_TIMEOUT))
                t = msg.get('t')
                if t == 'snapshot':
                    if not msg.get('authed'):
                        print('❌ 로그인이 안 됐습니다(토큰 · 비밀번호가 서버와 다름) — 설정 조각을 못 받습니다. 끝냅니다.', flush=True)
                        self.stop, self.exit_code = True, EX_CONFIG
                        return
                    first = self.slices is None
                    self.slices, self.seq, self.resyncing = dict(msg.get('slices') or {}), int(msg.get('seq') or 0), False
                    self._feed()
                    if first:
                        self._hello(ws)
                    if once:
                        return
                elif t == 'patch':
                    if self.slices is None or self.resyncing:
                        continue                     # 통째를 기다리는 중 — 그 전 쪽지는 통째에 다 들어 있다
                    seq = int(msg.get('seq') or 0)
                    if seq <= self.seq:
                        continue                     # 이미 본 번호
                    if seq != self.seq + 1:
                        # ⚠️ 빠진 쪽지가 있다 — 그대로 이어 붙이면 그 사이 바뀐 조각을 영영 모른다. 통째를 다시 받는다
                        print(f'↻ 쪽지 번호가 비었습니다({self.seq} → {seq}) — 통째로 다시 받습니다', flush=True)
                        self.resyncing = True
                        ws.send(json.dumps({'t': 'resync'}))
                        continue
                    self.seq = seq
                    ch = msg.get('slices') or {}
                    if ch:                           # 번호만 오는 쪽지(바뀐 조각 없음)는 볼 게 없다
                        self.slices.update(ch)
                        self._feed()
                elif t == 'result' and msg.get('id') == 'hello' and not msg.get('ok'):
                    self._warn_once('hello', f"ℹ️ 서버가 bot.hello 를 모릅니다({msg.get('error')}) — 조종실에 봇 상태가 안 보일 뿐, 봇은 돈다")

    def _feed(self):
        if 'announce_bot' not in self.slices:
            self._warn_once('missing', '⚠️ 서버에 announce_bot 조각이 없습니다(v2 에 announce 모듈을 안 붙였음) '
                                       '— 조종실이 끌 수 없는 봇은 입을 다뭅니다')
        try:
            self._on_state(to_old(self.slices))
        except Exception as e:
            print(f'⚠️ 상태를 읽다 넘어갔습니다 ({e})', flush=True)

    def _hello(self, ws):
        """조종실이 '봇이 어떤 모드로 붙어 있나' 를 알게 — 설정은 안 건드린다."""
        data = {'mode': 'live' if self.live else 'dry', 'pid': os.getpid(), 'host': socket.gethostname(), 'yt': self.yt_note}
        try:
            ws.send(json.dumps({'t': 'cmd', 'id': 'hello', 'type': 'bot.hello', 'data': data}, ensure_ascii=False))
        except Exception:
            pass


def load_cfg():
    cfg = A.load_json(os.environ.get('BOT_V2_CONFIG') or os.path.join(BOT_DIR, 'config.json'))
    port = os.environ.get('LM2_PORT') or '5300'
    cfg['server'] = os.environ.get('BOT_V2_SERVER') or 'http://127.0.0.1:' + port
    cfg['min_interval_sec'] = float(os.environ.get('BOT_INTERVAL') or cfg.get('min_interval_sec', 25))
    cfg['idle_after_sec'] = float(os.environ.get('BOT_IDLE') or cfg.get('idle_after_sec', 90))
    y = cfg.setdefault('youtube', {})
    for k in ('channel_id', 'video_id', 'live_chat_id'):
        v = os.environ.get('YT_' + k.upper())
        if v:
            y[k] = v.strip()
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description='진행봇 v2 (기본은 입 막음)')
    ap.add_argument('--live', action='store_true', help='진짜로 유튜브에 친다 (기본은 입 막음)')
    ap.add_argument('--once', action='store_true', help='통째 한 번 받고 끝 — 연결 · 로그인 확인용')
    args = ap.parse_args(argv)

    cfg = load_cfg()
    tpl = A.Templates(os.environ.get('BOT_V2_MESSAGES') or os.path.join(BOT_DIR, 'messages.json'))
    bot = V2Bot(cfg, tpl, live=args.live)
    if args.live:
        # 옛 main() 과 같은 순서 · 같은 끝내기 규칙(열쇠가 없으면 78 — systemd 가 되살리지 않는다)
        from youtube import YouTube                    # bot/youtube.py — 입 막고 돌릴 때는 아예 안 불러온다
        bot.yt = YouTube(cfg.get('youtube') or {})
        ok, why = bot.yt.ready()
        if not ok:
            print(f'❌ 유튜브 준비가 안 됐습니다: {why}')
            cok, _ = bot.yt.creds_ready()
            if not cok:
                print('   bot/README.md 의 2단계를 먼저 해주세요. 지금은 --live 없이 돌리면 됩니다.')
                return EX_CONFIG
            print('   ⏳ 열쇠는 멀쩡합니다. 방송이 켜지거나 조종실에서 라이브 주소를 넣으면 그때 붙습니다.', flush=True)
            bot.yt_note = str(why)[:200]
        else:
            bot.yt_note = 'ok'
        print('💬 진짜로 칩니다.')
    try:
        bot.run(once=args.once)
    except KeyboardInterrupt:
        print('\n👋 껐습니다.')
    return bot.exit_code


if __name__ == '__main__':
    sys.exit(main())
