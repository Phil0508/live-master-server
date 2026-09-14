# -*- coding: utf-8 -*-
"""🤖 진행봇 — 방송에서 일어난 일을 유튜브 라이브 채팅에 알린다.

    방송 서버 ──SSE(/api/stream)──> 이 프로그램 ──> 유튜브 라이브 채팅

⚠️ server.py 안에 넣지 않는다. 유튜브 쪽이 느려지거나 토큰이 만료돼도 방송은 멀쩡해야
   하고, 봇만 껐다 켤 수 있어야 한다. 봇은 방송판과 똑같이 그냥 '또 하나의 손님' 이다.
⚠️ 점수 배정(조종실에서 선수에게 주는 것)은 **한 건씩 알리지 않는다**
   (사장님: "후원이 나올 때 누가 후원했는지가 필요한 거지, 점수 들어가는 거 하나하나
   쓸 필요 없어"). 후원 인사에 이미 후원자 이름이 들어 있고, 배정은 조종실 사정이다.
⚠️ 주사위게임은 **안내하지 않는다**(사장님: "안내봇이 주사위에 관해서 안내하는건 빼").
   화면에 판이 그대로 보이는데 채팅이 굴림마다 따라 읽으면 시끄럽기만 하다.
   판단하는 코드는 그대로 두고 **문구표만 비워** 둔다 — 나중에 마음이 바뀌면 문구만 넣으면 된다.
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
sys.path.insert(0, HERE)
# 🌐 IPv4 로만 나간다. 이 컴퓨터는 나갈 수 없는 IPv6 주소를 갖고 있어서, 그대로 두면
#    구글에 한 번 붙는 데 48~168초가 걸린다(실측). IPv4 로만 붙으면 0.1초다.
from net import force_ipv4
force_ipv4()

# ── 우선순위. 작을수록 먼저 나간다. 밀리면 큰 숫자부터 버린다 ──
P_DONATION = 0     # 돈이 들어온 것 — 절대 안 버린다
P_DICE_BIG = 1     # 한 바퀴·황금열쇠·뺏기·블랙홀
P_RANK     = 2     # 1위가 바뀜
P_DICE     = 3     # 그냥 굴림
P_GOAL     = 4     # 목표 진행
P_NOTICE   = 5     # 계좌·순위·모금함 되풀이 안내 (사건이 아니라 시계로 나간다)
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

    def has(self, key):
        """이 칸에 쓸 문구가 하나라도 있나. 비어 있으면 그 사건은 아예 안 만든다."""
        return bool(self._list(key))

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


def rank_rows(st):
    """기여도 순으로 줄 세운다 — [(기여도, 이름), ...]. 동점이면 이름순.
    ⚠️ 서버 순위표(ORDER BY contribution DESC)와 **같은 규칙**이어야 한다.
       봇이 말하는 순위와 화면의 순위가 다르면 시청자가 봇을 안 믿는다.
    ⚠️ 기여도 0 은 뺀다 — 아직 아무것도 안 한 사람을 '3위' 라고 부르지 않는다."""
    rows = [(int(b.get('contribution') or 0), str(b.get('name') or '')) for b in (st.get('bjs') or [])]
    rows = [r for r in rows if r[1] and r[0] > 0]
    rows.sort(key=lambda r: (-r[0], r[1]))
    return rows


def top_name(st):
    """기여도 1위 이름. 아무도 없으면 None."""
    rows = rank_rows(st)
    return rows[0][1] if rows else None


GOAL_MARKS = (25, 50, 75, 90)

# 🎛️ 사건 → 조종실 스위치 이름. 조종실(state['announce_bot']['say'])에서 끄면 안 나간다.
# ⚠️ 여기 없는 사건은 늘 나간다. 새 사건을 만들면 여기에도 적어야 조종실에서 끌 수 있다.
SAY_OF = {
    'donation': 'donation',
    'rank_top': 'rank_top', 'rank_top_only': 'rank_top',
    'rank_close': 'rank_close',
    'goal': 'goal', 'goal_done': 'goal',
    'dice_roll': 'dice', 'dice_score': 'dice', 'dice_lap': 'dice', 'dice_key': 'dice',
    'dice_steal': 'dice', 'dice_giveall': 'dice', 'dice_blackhole': 'dice',
}
# 📣 되풀이 안내: 봇 설정 이름 ↔ 조종실 이름(분 단위)
NOTICE_MIN_OF = {'account_every_sec': 'account_min',
                 'rank_every_sec': 'rank_min',
                 'fundjar_every_sec': 'fundjar_min'}


def bot_cfg(st):
    """조종실이 정한 설정. 없으면 빈 사전 — 그때는 파일 설정대로 간다.

    ⚠️ 서버가 이 값을 상태에 실어 SSE 로 보낸다. 봇은 다른 프로그램이라 서버가 직접
       켜고 끌 수는 없고, 봇이 이걸 보고 스스로 입을 다무는 방식이다.
    """
    b = st.get('announce_bot')
    return b if isinstance(b, dict) else {}


def says(st, key):
    """이 사건을 말해도 되나 — 조종실 스위치를 본다."""
    name = SAY_OF.get(key) or ('idle' if key.startswith('idle.') else None)
    if not name:
        return True
    say = bot_cfg(st).get('say')
    if not isinstance(say, dict) or name not in say:
        return True          # 조종실이 정한 게 없으면 문구표대로 간다
    return bool(say[name])


def _queue_ids(st):
    return [str(q.get('id') or '') for q in (st.get('reaction_queue') or []) if q.get('id')]


def _head_id(st):
    """지금 화면에서 재생 중인(또는 막 시작한) 리액션의 번호."""
    q = st.get('reaction_queue') or []
    return str((q[0].get('id') if q and isinstance(q[0], dict) else '') or '')


def _reaction_for(prev, cur, name, amount):
    """이번 후원 때문에 **새로 생긴** 리액션의 번호. 없으면 None.

    ⚠️ 큐에는 후원만 들어가는 게 아니다 — 슬롯 당첨('🎰 슬롯머신'), 주사위 칸('주사위게임'),
       조종실 수동 송출도 같은 큐를 쓴다. 그래서 '큐가 늘었다' 만으로는 안 되고
       **이번에 들어온 후원과 이름·금액이 맞는가**까지 봐야 한다.
       안 그러면 주사위판이 시그니처를 하나 틀 때마다 '주사위게임님 후원 감사합니다' 가 나간다.

    ⚠️ 이름을 글자 그대로 비교해도 되는 근거: 서버가 후원을 받을 때 latest_donation 의 name 과
       큐의 donator 에 **같은 변수(parsed_name)** 를 넣는다(server.py 의 receive_donation).
       '홍길동님' → '홍길동' 같은 다듬기는 그보다 먼저 끝나 있어서 양쪽이 늘 같다.
    """
    old = set(_queue_ids(prev))
    for q in (cur.get('reaction_queue') or []):
        if not isinstance(q, dict):
            continue
        qid = str(q.get('id') or '')
        if not qid or qid in old:
            continue
        if str(q.get('donator') or '') == str(name or '')                 and int(q.get('amount') or 0) == int(amount or 0):
            return qid
    return None


DEFAULT_CLOSE_GAP = 50000   # 1·2위 격차가 이 밑으로 내려오면 '접전' 이라고 부른다


def detect(prev, cur, close_gap=DEFAULT_CLOSE_GAP, waiting=None):
    """이전 상태와 견줘 '알릴 만한 일' 을 뽑는다.

    waiting 은 '리액션이 나오기를 기다리는 후원' 을 담아두는 상자다(부르는 쪽이 들고 있는다).
    안 주면 예전처럼 후원이 도착하자마자 인사한다 — 검사에서 한 조각씩 보기 편하라고 남겨 둔다.
    """
    out = []

    # ── 💝 후원. **도착할 때가 아니라 리액션이 화면에 나올 때** 인사한다 ──
    # 사장님: "후원이 후원함에 들어오자마자 저게 나오면 스포니까 리액션 할 때 나오게 해줘".
    # 후원은 도착과 동시에 리액션 큐에 들어가지만, 앞에 밀린 게 있으면 화면에 나오기까지
    # 한참이다. 그 사이에 채팅이 먼저 '누가 얼마' 를 말하면 연출을 다 까먹는다.
    ld, pld = cur.get('latest_donation') or {}, prev.get('latest_donation') or {}
    if ld.get('time') and ld.get('time') != pld.get('time') and int(ld.get('amount') or 0) > 0:
        f = {'name': ld.get('name') or '익명', 'amount': won(ld.get('amount'))}
        rq = _reaction_for(prev, cur, ld.get('name'), ld.get('amount'))
        if rq is None or waiting is None:
            # 리액션이 안 걸린 후원(소액 등)은 화면에 나올 게 없다 — 깔 스포도 없으니 바로 인사
            out.append(Event(P_DONATION, 'donation', f))
        else:
            waiting[rq] = dict(f, _at=time.time())

    # ── ▶️ 리액션이 화면에 나오기 시작했다 = 큐 머리가 바뀌었다. 그때 인사가 나간다 ──
    if waiting is not None:
        head, phead = _head_id(cur), _head_id(prev)
        if head and head != phead and head in waiting:
            f = waiting.pop(head)
            f.pop('_at', None)
            out.append(Event(P_DONATION, 'donation', f))
        # 큐에서 사라진 것 — 진행자가 건너뛰었거나 상한을 넘겨 버려졌다.
        # ⚠️ 그래도 인사는 한다. 리액션은 이미 지나갔으니 깔 스포가 없고,
        #    돈을 낸 사람에게 인사를 빠뜨리는 게 훨씬 나쁘다.
        alive = set(_queue_ids(cur))
        for k in [k for k in waiting if k not in alive]:
            f = waiting.pop(k)
            f.pop('_at', None)
            out.append(Event(P_DONATION, 'donation', f))

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

    # ── 👑 1위가 바뀜. 2위가 있으면 '몇 점 차' 까지 싣는다 ──
    rows, prows = rank_rows(cur), rank_rows(prev)
    t = rows[0][1] if rows else None
    pt = prows[0][1] if prows else None
    if t and t != pt:
        if len(rows) >= 2:
            out.append(Event(P_RANK, 'rank_top',
                             {'name': t, 'second': rows[1][1],
                              'gap': won(rows[0][0] - rows[1][0])}))
        else:
            # ⚠️ 혼자면 '2위와 ? 차이' 라고 말할 수 없다. 빈칸이 안 채워지는 문구를
            #    쓰면 그 줄은 통째로 안 나간다 → 칸을 따로 둔다.
            out.append(Event(P_RANK, 'rank_top_only', {'name': t}))

    # ── 🔥 접전. 격차가 기준 밑으로 **내려오는 순간**에만 한 번 ──
    # ⚠️ '지금 가깝다' 로 치면 붙어 있는 내내 떠든다. '방금 가까워졌다' 여야 한다.
    if close_gap > 0 and len(rows) >= 2 and len(prows) >= 2:
        now_gap = rows[0][0] - rows[1][0]
        was_gap = prows[0][0] - prows[1][0]
        if now_gap <= close_gap < was_gap:
            out.append(Event(P_RANK, 'rank_close',
                             {'first': rows[0][1], 'second': rows[1][1], 'gap': won(now_gap)}))

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


# ══ 📣 주기 안내 ══════════════════════════════════════════════════════════
# 사건이 아니라 **시계**로 나간다. 방송 중간에 들어온 시청자는 후원하는 법도,
# 지금 판이 어떤지도 모른다. 화면에는 다 떠 있지만 폰으로 보면 작고 복사도 안 된다.
# 채팅에 한 줄 있으면 길게 눌러 복사가 된다 — 그게 이 기능이 있는 이유다.
#
# 각 함수는 (문구칸, 채울값) 을 주거나, 지금 말할 게 없으면 None 을 준다.


def notice_account(st):
    """💛 후원 계좌. 화면의 계좌판과 같은 값을 읽는다."""
    a = st.get('account') or {}
    num = str(a.get('acc_num') or '').strip()
    if not num:
        return None
    return ('notice.account', {'bank': str(a.get('bank') or '').strip(),
                               'acc_num': num,
                               'holder': str(a.get('name') or '').strip()})


def notice_rank(st):
    """📊 지금 순위. **바로 위와 몇 점 차**까지 붙인다 — 격차가 보여야 추격이 된다."""
    rows = rank_rows(st)
    if len(rows) < 2:
        return None                      # 혼자면 '순위' 가 아니다
    f = {'first': rows[0][1], 'first_score': won(rows[0][0]),
         'second': rows[1][1], 'second_score': won(rows[1][0]),
         'gap': won(rows[0][0] - rows[1][0])}
    if len(rows) < 3:
        return ('notice.rank2', f)
    f['third'] = rows[2][1]
    f['third_score'] = won(rows[2][0])
    f['gap2'] = won(rows[1][0] - rows[2][0])
    return ('notice.rank3', f)


def notice_fundjar(st):
    """🏺 모금함. 화면 금액과 같은 셈 = 종잣돈 + 시청자 후원분."""
    j = st.get('fundjar') or {}
    if not j.get('enabled'):
        return None
    seed, added = int(j.get('seed') or 0), int(j.get('score') or 0)
    if seed + added <= 0:
        return None
    return ('notice.fundjar', {'total': won(seed + added),
                               'seed': won(seed), 'added': won(added)})


# (이름, config 칸, 기본 간격(초), 만드는 함수)
NOTICES = [
    ('account', 'account_every_sec', 420, notice_account),
    ('rank',    'rank_every_sec',    480, notice_rank),
    ('fundjar', 'fundjar_every_sec', 600, notice_fundjar),
]


class Bot:
    def __init__(self, cfg, tpl, live=False):
        self.cfg, self.tpl, self.live = cfg, tpl, live
        self.q = deque()
        self.lock = threading.Lock()
        self.state = {}
        self.prev = None
        self.last_sent = 0.0
        self.last_event = time.time()
        self.notice_at = {}        # {안내이름: 마지막으로 친 때}
        self.last_notice = 0.0     # 안내끼리도 너무 붙지 않게
        # ⏳ 리액션이 화면에 나오기를 기다리는 후원들 {리액션번호: 채울값}
        self.waiting = {}
        self.wlock = threading.Lock()   # detect(받는 실) 와 훑기(보내는 실) 가 같이 만진다
        self.sent_today, self.today = 0, time.strftime('%Y-%m-%d')
        self.interval = float(cfg.get('min_interval_sec', 25))
        self.backoff = 0.0         # 유튜브가 막아서 늘려둔 만큼 (조종실이 내려도 안 지워진다)
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
            with self.wlock:
                evs = detect(self.prev, st,
                             close_gap=self._ncfg('close_gap', DEFAULT_CLOSE_GAP),
                             waiting=self.waiting)
        except Exception as e:
            print(f'⚠️ 사건을 찾다 넘어갔습니다 ({e})')
            evs = []
        self.prev = st
        # ⚠️ 문구를 [] 로 비워 둔 사건은 여기서 버린다. 큐에 넣어 두면 여섯 칸을
        #    말없이 차지하고, 정작 알릴 일을 밀어낸다.
        evs = [e for e in evs if self.tpl.has(e.key) and says(st, e.key)]
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

    def _sweep_waiting(self, now):
        """⏳ 리액션을 아무리 기다려도 안 나오면 늦게라도 인사한다.

        ⚠️ OBS 장면을 바꿔놨거나 오버레이가 닫혀 있으면 큐가 줄지 않는다. 그때 그냥 두면
           돈을 낸 사람이 **끝까지 인사를 못 받는다.** 늦은 인사가 없는 인사보다 낫다.
        ⚠️ 봇을 껐다 켜면 이 상자가 비니, 그때 기다리던 후원은 인사가 빠진다(문서에 적어 뒀다).
        """
        limit = float(self.cfg.get('reaction_wait_max_sec', 600))
        if limit <= 0:
            return
        with self.wlock:
            late = [k for k, f in self.waiting.items() if now - f.get('_at', now) > limit]
            fs = []
            for k in late:
                f = self.waiting.pop(k)
                f.pop('_at', None)
                fs.append(f)
        if not fs:
            return
        print(f'⏳ 리액션이 {limit:.0f}초 넘게 안 나와 먼저 인사합니다 ({len(fs)}건)')
        with self.lock:
            for f in fs:
                self.q.append(Event(P_DONATION, 'donation', f))

    def _tick(self):
        now = time.time()
        self._sweep_waiting(now)
        live = bot_cfg(self.state)
        # 🎛️ 조종실에서 봇을 끄면 한마디도 안 한다.
        # ⚠️ 끄는 동안 쌓인 소식 중 **후원만 남기고 버린다.** 다시 켰을 때
        #    '1위가 바뀌었습니다' 가 10분 늦게 나가면 거짓말이 된다. 반대로 후원은
        #    늦더라도 인사해야 한다 — 돈을 낸 사람이기 때문이다.
        #    (하루 예산을 넘겼을 때와 같은 규칙이다)
        if live.get('enabled') is False:
            with self.lock:
                if any(e.prio != P_DONATION for e in self.q):
                    self.q = deque(e for e in self.q if e.prio == P_DONATION)
            return
        # ⚠️ 조종실이 간격을 정하면 그게 기본이 된다. 다만 유튜브가 '너무 빠르다' 고 막아서
        #    늘려둔 값(self.interval)은 **그 위에 얹힌다** — 조종실에서 5초로 내렸다고
        #    막힌 상태에서 5초마다 두드리면 더 오래 막힌다.
        iv = live.get('min_interval_sec')
        if iv:
            self.interval = max(float(iv), self.backoff)
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
            # 알릴 일이 없을 때 비로소 안내가 나간다. 사건이 안내에 밀리지 않는다.
            e = self._notice(now) or self._idle(now)
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

    def _ncfg(self, key, default):
        """되풀이 안내 간격(초). **조종실이 정한 값이 파일 설정을 이긴다.**"""
        nm = NOTICE_MIN_OF.get(key)
        if nm:
            live = bot_cfg(self.state).get('notices')
            if isinstance(live, dict) and live.get(nm) is not None:
                return float(live[nm]) * 60      # 조종실은 분, 여기는 초
        return float((self.cfg.get('notices') or {}).get(key, default))

    def _notice(self, now):
        """📣 되풀이 안내 — 계좌·순위·모금함. 제일 오래 묵은 것 하나만 낸다."""
        if now - self.last_notice < self._ncfg('gap_sec', 120):
            return None                      # 안내끼리 붙어 나오면 광고처럼 보인다
        st = self.state
        best, best_over = None, -1.0
        for name, cfg_key, default, build in NOTICES:
            every = self._ncfg(cfg_key, default)
            if every <= 0:
                continue                     # 0 으로 두면 그 안내는 끈 것이다
            last = self.notice_at.get(name)
            if last is None:
                # ⚠️ 켜자마자 셋을 연달아 치지 않는다. 첫 차례는 간격의 절반 뒤부터.
                self.notice_at[name] = now - every / 2
                continue
            over = (now - last) - every
            if over < 0 or over < best_over:
                continue
            made = build(st)
            if made and self.tpl.has(made[0]):
                best, best_over = (name, made), over
        if not best:
            return None
        name, (key, fields) = best
        self.notice_at[name] = now
        self.last_notice = now
        self.last_event = now                # 안내도 '봇이 말한 것' — 질문 시계를 되감는다
        return Event(P_NOTICE, key, fields)

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
        # ⚠️ 그 바구니를 비워 뒀으면 보통 질문으로 간다. 안 그러면 주사위판이 켜져 있는
        #    내내 봇이 한마디도 안 한다 — 비운 건 '주사위 얘기를 말라' 지 '입 다물라' 가 아니다.
        key = 'idle.' + kind
        if not self.tpl.has(key):
            key = 'idle.any'
        return Event(P_IDLE, key, {})

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
                self.backoff = self.interval
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
