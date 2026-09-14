# -*- coding: utf-8 -*-
"""🤖 진행봇 — 방송에서 일어난 일을 유튜브 라이브 채팅에 알린다.

    방송 서버 ──SSE(/api/stream)──> 이 프로그램 ──> 유튜브 라이브 채팅

⚠️ server.py 안에 넣지 않는다. 유튜브 쪽이 느려지거나 토큰이 만료돼도 방송은 멀쩡해야
   하고, 봇만 껐다 켤 수 있어야 한다. 봇은 방송판과 똑같이 그냥 '또 하나의 손님' 이다.
⚠️ AI 를 쓰지 않는다. 할 말이 전부 서버가 이미 아는 사실이라 문구표 빈칸에 끼워 넣으면
   된다(사장님: "안내봇은 말 그대로 안내만 하면 되는 거잖아"). 그 편이 사고도 없고,
   자주 죽는 AI 모델에 봇이 매달리지도 않는다.
⚠️ 표준 라이브러리만 쓴다. 새 의존성 없음.

사용:
    python bot/announce.py             # 입 막고 돌리기 — dryrun.log 에만 남긴다 (기본)
    python bot/announce.py --live      # 진짜로 유튜브에 친다
    python bot/announce.py --once      # 붙어서 한 번 받고 바로 끝 (연결 확인용)
"""
import argparse
import http.cookiejar
import io
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))

# ── 우선순위. 작을수록 먼저 나간다. 밀리면 큰 숫자부터 버린다 ──
P_DONATION = 0     # 돈이 들어온 것 — 절대 안 버린다
P_DICE_BIG = 1     # 한 바퀴·황금열쇠·뺏기·블랙홀
P_RANK     = 2     # 1위가 바뀜
P_DICE     = 3     # 그냥 굴림
P_GOAL     = 4     # 목표 진행
P_IDLE     = 9     # 조용할 때 던지는 질문
# ⚠️ 1위가 바뀌는 건 그냥 굴림보다 위다. 주사위를 연달아 굴리면 큐가 밀리는데,
#    그때 '1위가 바뀌었다' 가 버려지고 '2번 칸으로 갔다' 가 남으면 순서가 거꾸로다.

TILE_NAME = {'start': '출발', 'blank': '빈칸', 'mission': '미션', 'sig': '시그니처',
             'score': '점수', 'key': '황금열쇠', 'move': '싱크홀', 'goto': '블랙홀',
             'giveall': '전원 지급', 'steal': '뺏어오기'}


def load_json(path, default=None):
    try:
        with io.open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        if default is None:
            raise
        print(f'⚠️ {os.path.basename(path)} 를 못 읽었습니다 ({e}) — 기본값으로 갑니다')
        return default


def won(n):
    return format(int(n or 0), ',')


class Templates:
    """문구표. 같은 칸에 여러 개면 돌아가며 쓴다 — 같은 말이 연달아 나오면 봇 티가 난다."""

    def __init__(self, path):
        self.path = path
        self.data = load_json(path, {})
        self._turn = {}

    def reload(self):
        self.data = load_json(self.path, self.data)

    def _list(self, key):
        cur = self.data
        for part in key.split('.'):
            cur = (cur or {}).get(part)
        return [s for s in (cur or []) if isinstance(s, str) and s.strip()]

    def render(self, key, fields):
        """빈칸을 채운 문장. 칸이 비어 있거나 채울 값이 없으면 None(= 안 친다)."""
        opts = self._list(key)
        if not opts:
            return None
        i = self._turn.get(key, random.randrange(len(opts)))
        self._turn[key] = (i + 1) % len(opts)
        try:
            return opts[i % len(opts)].format(**fields)
        except (KeyError, IndexError) as e:
            # ⚠️ 사장님이 문구를 고치다 없는 이름을 쓸 수 있다. 그때 봇이 죽으면 안 된다.
            print(f'⚠️ 문구 "{key}" 에 채울 수 없는 값이 있습니다 ({e}) — 건너뜁니다')
            return None


class Event:
    __slots__ = ('prio', 'key', 'fields', 'at')

    def __init__(self, prio, key, fields):
        self.prio, self.key, self.fields = prio, key, fields
        self.at = time.time()


def goal_total(st):
    """목표 막대와 **같은 셈**. server.py 의 _goal_waiting 과 같아야 한다 —
    기여도 합을 쓰면 막대가 다 차기 전에 '넘었다' 고 한다."""
    total = int((st.get('bottom_fixed') or {}).get('score') or 0)
    total += sum(int(b.get('score') or 0) for b in (st.get('bjs') or []))
    total += int(st.get('goal_offset') or 0)
    return total


def top_name(st):
    """기여도 1위 이름. 동점이면 이름순 — 서버 순위표와 같은 규칙."""
    rows = [(int(b.get('contribution') or 0), str(b.get('name') or '')) for b in (st.get('bjs') or [])]
    rows = [r for r in rows if r[1]]
    if not rows:
        return None
    rows.sort(key=lambda r: (-r[0], r[1]))
    return rows[0][1] if rows[0][0] > 0 else None


GOAL_MARKS = (25, 50, 75, 90)


def detect(prev, cur):
    """이전 상태와 견줘 '알릴 만한 일' 을 뽑는다. 순수 함수 — 검사에서 그대로 부른다."""
    out = []

    # ── 💝 후원 ──
    ld, pld = cur.get('latest_donation') or {}, prev.get('latest_donation') or {}
    if ld.get('time') and ld.get('time') != pld.get('time') and int(ld.get('amount') or 0) > 0:
        out.append(Event(P_DONATION, 'donation',
                         {'name': ld.get('name') or '익명', 'amount': won(ld.get('amount'))}))

    # ── 🎲 주사위. 한 번 굴림에 한 줄만 낸다 — 사건마다 한 줄이면 채팅이 도배된다 ──
    a = (cur.get('dicegame') or {}).get('action') or {}
    pa = (prev.get('dicegame') or {}).get('action') or {}
    # ⚠️ 'ROLL' 만 본다. 'MOVE' 는 조종실에서 말을 손으로 옮긴 것이라 게임 사건이 아니다.
    #    예전에 넣었더니 판을 정리할 때마다 "예지랑님 ? → 0번 칸" 을 떠들었다(눈으로 잡았다).
    if a.get('ts') and a.get('ts') != pa.get('ts') and a.get('type') == 'ROLL':
        piece = a.get('piece') or '말'
        tile = a.get('tile') or {}
        f = {'piece': piece,
             'dice': '+'.join(str(x) for x in (a.get('dice') or [])) or '?',
             'to': a.get('to'),
             'tile': tile.get('label') or TILE_NAME.get(tile.get('type'), '빈칸')}
        after = a.get('after') or {}
        key = None
        if after.get('kind') == 'goto':
            key, prio = 'dice_blackhole', P_DICE_BIG
        elif a.get('key_effect') or a.get('key'):
            key, prio = 'dice_key', P_DICE_BIG
            f['effect'] = a.get('key_effect') or a.get('key') or ''
        elif a.get('steal'):
            key, prio = 'dice_steal', P_DICE_BIG
            f['per'] = (a.get('steal') or {}).get('per', '')
        elif a.get('giveall'):
            key, prio = 'dice_giveall', P_DICE_BIG
            f['points'] = (a.get('giveall') or {}).get('points', '')
        elif a.get('lap_contrib'):
            key, prio = 'dice_lap', P_DICE_BIG
            f['points'] = (a.get('lap_contrib') or {}).get('points', '')
        elif a.get('scored') or tile.get('type') == 'score':
            key, prio = 'dice_score', P_DICE
            f['points'] = tile.get('points', '')
        else:
            key, prio = 'dice_roll', P_DICE
        out.append(Event(prio, key, f))

    # ── 👑 1위가 바뀜 ──
    t, pt = top_name(cur), top_name(prev)
    if t and t != pt:
        out.append(Event(P_RANK, 'rank_top', {'name': t}))

    # ── 🎯 목표. 25·50·75·90% 를 **지나는 순간**만. 매번 떠들면 시끄럽다 ──
    tgt = int(cur.get('target_goal') or 0)
    if tgt > 0:
        now_p = goal_total(cur) * 100 // tgt
        was_p = (goal_total(prev) * 100 // tgt) if int(prev.get('target_goal') or 0) > 0 else now_p
        if now_p >= 100 > was_p:
            out.append(Event(P_GOAL, 'goal_done', {}))
        else:
            for m in GOAL_MARKS:
                if was_p < m <= now_p:
                    out.append(Event(P_GOAL, 'goal',
                                     {'percent': m, 'remain': won(max(0, tgt - goal_total(cur)))}))
                    break
    return out


class Bot:
    def __init__(self, cfg, tpl, live=False):
        self.cfg, self.tpl, self.live = cfg, tpl, live
        self.q = deque()
        self.lock = threading.Lock()
        self.state = {}
        self.prev = None
        self.last_sent = 0.0
        self.last_event = time.time()
        self.sent_today, self.today = 0, time.strftime('%Y-%m-%d')
        self.interval = float(cfg.get('min_interval_sec', 25))
        self.stop = False
        self.yt = None
        self.dry_path = os.path.join(HERE, 'dryrun.log')

    # ── 서버에 붙기 ──
    def _opener(self):
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        pw = os.environ.get('ADMIN_PASSWORD')
        if pw:
            # ⚠️ 로그인해야 logs 가 온다. 무인증 손님에게는 서버가 빼고 보낸다.
            body = json.dumps({'password': pw, 'otp': os.environ.get('ADMIN_OTP', '')}).encode()
            req = urllib.request.Request(self.cfg['server'] + '/login', data=body,
                                         headers={'Content-Type': 'application/json'})
            try:
                op.open(req, timeout=15).read()
            except Exception as e:
                print(f'⚠️ 로그인 실패 — 공개 정보만 보고 갑니다 ({e})')
        else:
            print('ℹ️ ADMIN_PASSWORD 가 없습니다 — 공개 정보만 보고 갑니다')
        return op

    def run(self, once=False):
        threading.Thread(target=self._sender, daemon=True).start()
        while not self.stop:
            try:
                self._listen(once)
                if once:
                    return
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f'⚠️ 연결이 끊겼습니다 — 5초 뒤 다시 붙습니다 ({e})')
                time.sleep(5)

    def _listen(self, once=False):
        op = self._opener()
        url = self.cfg['server'] + '/api/stream'
        print(f'📡 {url} 에 붙는 중…')
        res = op.open(urllib.request.Request(url, headers={'Accept': 'text/event-stream'}),
                      timeout=60)
        print('📡 붙었습니다.' + ('' if self.live else '  (입 막음 — dryrun.log 에만 남깁니다)'))
        ev, buf = None, []
        for raw in res:
            line = raw.decode('utf-8', 'replace').rstrip('\n').rstrip('\r')
            if line.startswith('event:'):
                ev = line[6:].strip()
            elif line.startswith('data:'):
                buf.append(line[5:].strip())
            elif line == '':
                if ev in ('init', 'update') and buf:
                    try:
                        self._on_state(json.loads(''.join(buf)))
                    except Exception as e:
                        print(f'⚠️ 상태를 읽다 넘어갔습니다 ({e})')
                    if once:
                        return
                ev, buf = None, []

    def _on_state(self, st):
        self.state = st
        if self.prev is None:
            # ⚠️ 붙자마자 받는 첫 상태로는 아무 말도 안 한다. 안 그러면 봇을 켤 때마다
            #    이미 지나간 후원·굴림을 뒤늦게 떠든다.
            self.prev = st
            print('📌 기준 상태를 잡았습니다. 지금부터 새로 생기는 일만 알립니다.')
            return
        try:
            evs = detect(self.prev, st)
        except Exception as e:
            print(f'⚠️ 사건을 찾다 넘어갔습니다 ({e})')
            evs = []
        self.prev = st
        if not evs:
            return
        self.last_event = time.time()
        with self.lock:
            for e in evs:
                self.q.append(e)
            # 밀리면 낮은 것부터 버린다 — 30초 지난 소식을 뒤늦게 치면 더 이상하다
            if len(self.q) > 6:
                keep = sorted(self.q, key=lambda x: (x.prio, x.at))[:6]
                self.q = deque(sorted(keep, key=lambda x: x.at))

    # ── 말하기 ──
    def _sender(self):
        while not self.stop:
            time.sleep(1)
            try:
                self._tick()
            except Exception as e:
                print(f'⚠️ 보내다 넘어갔습니다 ({e})')

    def _tick(self):
        now = time.time()
        if now - self.last_sent < self.interval:
            return
        if self.cfg.get('only_when_broadcasting', True) and not self.state.get('broadcast_active'):
            return
        if time.strftime('%Y-%m-%d') != self.today:
            self.today, self.sent_today = time.strftime('%Y-%m-%d'), 0
        with self.lock:
            self.q = deque(sorted(self.q, key=lambda x: (x.prio, x.at)))
            e = self.q.popleft() if self.q else None
        if e is None:
            e = self._idle(now)
            if e is None:
                return
        # 하루 예산을 넘으면 후원 감사만 남긴다 — 돈 낸 사람에게 인사는 해야 한다
        if self.sent_today >= int(self.cfg.get('daily_budget', 180)) and e.prio != P_DONATION:
            return
        text = self.tpl.render(e.key, e.fields)
        if not text:
            return
        self._say(text)
        self.last_sent, self.sent_today = now, self.sent_today + 1

    def _idle(self, now):
        """아무 일도 없을 때만 질문을 던진다. 상황을 보고 고를 뿐 생각하지는 않는다."""
        if now - self.last_event < float(self.cfg.get('idle_after_sec', 90)):
            return None
        self.last_event = now
        st = self.state
        kind = 'any'
        if (st.get('dicegame') or {}).get('enabled'):
            kind = 'dice'
        else:
            tgt = int(st.get('target_goal') or 0)
            if tgt > 0 and goal_total(st) * 100 // tgt >= 60:
                kind = 'goal'
        return Event(P_IDLE, 'idle.' + kind, {})

    def _say(self, text):
        line = f'[{time.strftime("%H:%M:%S")}] {text}'
        print(('💬 ' if self.live else '📝 ') + line, flush=True)
        if not self.live:
            with io.open(self.dry_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
            return
        ok, err = self.yt.post(text)
        if not ok:
            print(f'⚠️ 유튜브에 못 올렸습니다 ({err})')
            # 너무 빨리 쳐서 막힌 것이면 스스로 느려진다
            if 'rateLimit' in str(err):
                self.interval = min(self.interval * 2, 300)
                print(f'⏳ 간격을 {self.interval:.0f}초로 늘립니다')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--live', action='store_true', help='진짜로 유튜브에 친다 (기본은 입 막음)')
    ap.add_argument('--once', action='store_true', help='한 번 받고 끝 — 연결 확인용')
    args = ap.parse_args()

    cfg = load_json(os.path.join(HERE, 'config.json'))
    # 파일을 안 고치고 그때그때 바꿀 수 있게 — 오늘만 조용히 시키거나, 검사할 때 빨리 돌린다
    cfg['server'] = os.environ.get('BOT_SERVER') or cfg.get('server') or 'http://127.0.0.1:5000'
    cfg['min_interval_sec'] = float(os.environ.get('BOT_INTERVAL') or cfg.get('min_interval_sec', 25))
    cfg['idle_after_sec'] = float(os.environ.get('BOT_IDLE') or cfg.get('idle_after_sec', 90))
    tpl = Templates(os.path.join(HERE, 'messages.json'))
    bot = Bot(cfg, tpl, live=args.live)

    if args.live:
        from youtube import YouTube          # 입 막고 돌릴 때는 아예 안 불러온다
        bot.yt = YouTube(cfg.get('youtube') or {})
        ok, why = bot.yt.ready()
        if not ok:
            print(f'❌ 유튜브 준비가 안 됐습니다: {why}')
            print('   README.md 의 2단계를 먼저 해주세요. 지금은 --live 없이 돌리면 됩니다.')
            return 1
        print('💬 진짜로 칩니다.')
    try:
        bot.run(once=args.once)
    except KeyboardInterrupt:
        print('\n👋 껐습니다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
