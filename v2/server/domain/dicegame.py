# -*- coding: utf-8 -*-
"""🎲 주사위게임(부루마블식) — 판 · 말 · 굴리기 · 황금열쇠 · 쉴드권 · 한 바퀴 · 전용 점수판 · 기본판.

옛 것: features/dicegame.py(본문) · server.py DEFAULT_STATE['dicegame'](1384) · strip_private_state(868, 열쇠 덱 감추기)
       · reset_session_keys(2076~, 방송 1회분) · overlay.html dgRollPlan(8897) · controller.html dgc*(12085~12610, 기본판 12344~12526)
       · tests/dice_test.py · dice_fix_test.py · dice_preset_test.py · dice_timing_test.py

조각
  dicegame         (공개)  cols · rows · dice · roll_price · lap_contrib · tiles · keys_count · pieces · board · turn · action
                            pieces[{name, pos, laps, shield, choose}] · board[{name, pts}](주사위 **전용** 점수판)
  dicegame_private (비공개) keys(황금열쇠 덱 — 뽑기 전까지 비밀, 방송판은 keys_count 만) · parked(명단에서 빠진 이름의 기록)
                            · log(전용 판 기록, 최근 200) · settles(정산 되돌리기용)

명령(전부 로그인 필요)
  dice.setup  {cols?, rows?, dice?, roll_price?, lap_contrib?}  판 깔기 — 같은 번호 칸은 남기고, 말은 출발로, 무대에 올린다
  dice.preset {name:'basic22'|'draw22', tiles_only?, sigs?}      22칸 기본판 · 손그림판(옛 조종실 DGC_PRESET_22 · _DRAW)
  dice.tile   {id, type, label?, points?, sig_id?, sig?}          칸 하나
  dice.keys   {keys:[글…]}                                      황금열쇠 덱(40장 · 200자)
  dice.roll   {piece?, player?, value?(1~6), seed?}               굴리기 — 결과 · 경로 · 연출 시간표를 서버가 정한다
  dice.move   {pos, piece?}                                      손으로 옮기기('원하는 곳으로' 를 뽑은 말이면 그 칸이 일을 한다)
  dice.shield {piece, on}                                        쉴드권 표시 켜고 끄기(진행자가 쓰면 [사용함] → on:false)
  dice.reset  {}                                                말을 출발로 · 무대에서 내림(칸 · 덱 · 전용 판 점수는 남김)
  dice.board  {do:'reset'|'set'|'add', name?, pts?}              전용 판 손보기
  dice.settle {clear?}                                          전용 판 → 진짜 기여도(이 게임에서 players 를 건드리는 **유일한** 길)

옮긴 규칙(숫자 · 조건은 옛 것 그대로, 줄 번호는 features/dicegame.py)
  - 판: 테두리 고리 2×(가로+세로)−4 칸, 가로 4~10 · 세로 3~8 · 주사위 1~2개(안 보내면 1개) · 0번은 출발(못 바꾼다)
    · 한 판 값 0~1천만(안 보내면 쓰던 값) · 한 바퀴 기여도 0~1000(기본 10) · 크기를 바꿔도 같은 번호 칸은 남는다(486~548)
  - 칸 종류 10가지(30). 숫자를 쓰는 칸은 score · move(몇 칸, 음수면 뒤로) · goto(칸 번호) · giveall · steal, ±1000(551~599)
  - 말 = 점수판 선수(번외 판이 켜져 있으면 번외 명단). 순서는 있던 말 순서를 지키고 새 이름만 뒤에,
    차례는 이름으로 기억(앞사람이 빠져도 안 건너뛴다 · 차례인 사람이 빠지면 다음 사람),
    빠진 이름의 자리 · 바퀴 · 쉴드 · 선택권 · 점수는 맡아 두었다가 돌아오면 되살린다(40명까지), 명단이 비면 말은 그대로(181~263, 382~407)
  - 굴리기(673~992): 말 고르기 piece → player 가 말 이름이면 그 말 → 차례 말 · 점수 받는 사람 = player 또는 움직인 말 주인
    · 무대에 주사위판이 없으면 거절(다른 판이면 그 이름을 알린다) · 연출이 끝나기 전(gate + 300ms)의 다음 굴림은 429
    · 현실 눈(value 1~6)이면 그 눈 하나, 아니면 서버가 판의 주사위 수만큼
    · 한 바퀴 = 출발을 **지나치면**(밟지 않아도) — 끌려간 이동(블랙홀 · 싱크홀 · 열쇠)은 안 센다(776~786)
    · 점수 칸: 전용 판에만(꽝 = 0점은 아무것도 안 준다) · 시그 칸: 대기줄(금액 0 · 팝업 없음 · 집계 안 셈 · 연출 끝에)
      + 기여도 = man_won(시그 값 − 한 판 값), 0 아래면 0(829~874) · 한 바퀴: lap_contrib(879~894)
    · move/goto: 거꾸로면 역주행 표시, 끌려간 자리의 점수 · 전원 지급 · 뺏기 · 열쇠는 걸고 이동 · 시그 칸은 안 건다(902~938, 618~670)
    · giveall: 모든 말 주인에게 · steal: 착지한 사람이 나머지 각각에게서(총점 그대로, 마이너스 됨)(939~962, 452~467)
    · 굴려도 차례는 안 넘어간다 — 고른 말이 차례가 된다(대표님 09-30, 968~972)
  - 황금열쇠(63~178): 글을 읽어 효과 — N등과 바꾸기 · 뒤로 N칸 · 앞으로 N칸 · 출발(거꾸로 걸어서) · 파산 · 한 번 더
    · 쉴드 · 원하는 곳으로 · 꽝 · 기여도 N(순서 그대로 — '1등과 바꾸기' 를 '기여도 N' 보다 먼저). 모르는 글이면 글만.
    끌려온 자리에서 뽑은 이동 열쇠는 다시 옮기지 않는다(끝없는 연쇄 방지).
  - 🛡️ 쉴드권(10-03): 뽑으면 '가지고 있다' 표시만. 저절로 막지 않는다 — 마이너스 칸 · 싱크홀 · 블랙홀도 그대로 걸리고,
    진행자가 쓰면 dice.shield {on:false}(1048~1062)
  - 손 이동(995~1045): 안 고르면 차례 말 · '원하는 곳으로' 표시가 있으면 그 칸 효과를 그 말 주인에게 한 번만
  - 전용 판(1101~1187): 전원 0점 시작 · 마이너스 됨 · 순위는 점수 → 이름 순 · 정산은 0점이 아닌 사람만,
    명단에서 못 찾은 사람(맡아 둔 사람 포함)은 **옮기지 않고 판에 남기고** 알린다
  - 방송 시작 · 끝(server.py reset_session_keys 2076~): 말 자리 · 바퀴 · 쉴드 · 선택권 · 차례 · 연출 · 전용 판 점수 · 보관함을 비운다.
    칸 구성 · 덱 · 판 크기 · 한 판 값 · 한 바퀴 값은 다음 주에도 쓰는 설정이라 남긴다.
  - 기본판(controller.html 12344~12526): 22칸 기본판(시그 5 · 꽝 2 · 미션 8 · 점수 6) · 손그림판(+ 황금열쇠 10장),
    시그니처는 이름으로 찾고(띄어쓰기 · 따옴표 · 느낌표 무시, 뒤에 말이 붙어도) 못 찾은 칸은 빈칸으로 두고 알린다.

화면 약속(방송판이 굴림을 그리는 법 — 옛 _dicegame_plan == dgRollPlan 을 **서버 한 곳**에서)
  - 눈 · 경로 · 열쇠 카드 · 끌려가기까지 전부 서버가 정해 action 에 싣는다. 방송판은 그리기만 한다 → 창이 여럿이어도 같은 굴림.
  - ROLL: {type, ts, dice, manual, piece, piece_idx, from, to, path, lap, tile{id,type,label,points,image?},
           key?, key_effect?, key_kind?, scored?, score_note?, contrib?, lap_contrib?, giveall?, steal?,
           after?{kind, from, to, path, rev, label, tile, scored?, note?, giveall?, steal?, key?, key_effect?, key_kind?},
           plan{rollT, land, gate, afStart, afStep}}
    plan(ms, 방송판이 action 을 **받은 때**부터 잰다):
      0 ~ rollT 굴림(현실 눈이면 380ms 동안 눈만) → 칸마다 300ms 걸음 → land 칸에 닿음
      → 열쇠 칸이면 뽑기 1.7초 → 카드 1.5초 → gate.
      after 가 있으면 land + afStart 부터 칸마다 afStep 으로 걷는다(역주행이 8칸을 넘으면 빠르게 — 전체 2.4초 안).
      gate 전에는 가리개(리액션 모드)도 시그 재생도 열지 않는다.
    ⚠️ 서버 시각 ts 와 화면 시계를 비교해 기다리지 말 것(옛 교훈: 시계가 어긋난 만큼 늦게 나왔다).
       ts 는 '이미 그린 굴림인가' 와 '20초 넘게 묵었나(새로 연 창은 연출 없이 제자리)' 만 본다.
  - 서버도 같은 plan 으로 연타를 막는다(gate + 300ms 안의 다음 굴림 = 429).
  - 시그 칸이면 대기줄 항목이 play_after = ts + gate · skip_popup · source:'dice' · banner:'이름 · 시그 칸 도착' 으로 들어간다.
  - MOVE: 걷지 않고 그 자리에 세운다. tile 이 있으면('원하는 곳으로') 칸을 밝히고 카드(열쇠 칸이면 뽑기 먼저). plan 없음.
  - PLACE(판 깔기 · 정리): 연출 없이 pieces 자리에 세운다. · '출발 N번' 표시 = pieces 의 laps 합.

v2 에서 뺀 것(옛 '통째 저장' 구조 · 옛 저장본 때문에 있던 것)
  - enabled 스위치 → show.stage 하나 · /api/dicegame/enable → show.stage 명령
  - pos/laps 거울(말이 하나이던 시절 호환) · last_player(09-30 에 버린 기억 규칙, 거절된 명령은 원래 아무것도 안 바꾼다)
  - lap_v2(옛 저장본 한 바퀴 5 → 10 한 번 올리기) · _dicegame_state 보정 · 내보낼 때 board 채우기(server.py 1123)
  - roster 사진과 개명 짐작(_dicegame_rename 266~296) → players.rename 이 명시적이니 on_rename 고리로 받는다
  - SERVER_OWNED · PATCH_DENY(조종실이 통째로 덮던 것) · 응답의 shield_used(10-03 이후 늘 False)
  - 전용 판 기록을 공용 logs 에 kind:'dice' 로 섞던 것 → dicegame_private.log(공용 기록 200줄을 주사위가 밀어내지 않게)
"""
import random
import re
import uuid

from .. import bus as _bus
from ..bus import CommandError, command
from ..state import slice_
from . import players as pl
from . import reaction as rx
from . import session as ses
from . import show as sh
from .rules import LOG_MAX, man_won

TILE_TYPES = ('start', 'blank', 'mission', 'sig', 'score', 'key', 'move', 'goto', 'giveall', 'steal')
NUM_TYPES = ('score', 'move', 'goto', 'giveall', 'steal')       # 숫자를 쓰는 칸 — 뜻은 종류마다 다르다
SIG_FIELDS = ('id', 'amount', 'title', 'image_url', 'sound_url', 'duration')
STAGE_LABEL = {'match': '대결', 'pinball': '핀볼', 'dicegame': '주사위', 'siggame': '시그뒤집기', 'roulette': '룰렛',
               'slot': '슬롯', 'home_race': '퇴근빵', 'hell': '지옥탈출', 'quiz': '퀴즈'}
PARKED_MAX = 40          # 🅿️ 맡아 두는 이름 수 — 넘으면 오래된 것부터
KEYS_MAX, KEY_LEN = 40, 200
SETTLES_MAX = 10
ROLL_GAP = 300           # 연타 막기 여유(연출 끝 + 0.3초)

# ⏱️ 연출 시간표의 박자 — 옛 DG_SIG_BEAT · DG_CARD_BEAT · DG_KEY_DRAW(37~40)
DG_SIG_BEAT = 1500       # 🎵 "시그니처 재생!" 카드를 읽을 틈 — 그 뒤에 가리개 + 시그
DG_CARD_BEAT = 1500      # 다른 칸 카드를 읽을 틈
DG_KEY_DRAW = 1700       # 🔑 황금열쇠 뽑기 연출

slice_('dicegame', True, lambda: {'cols': 7, 'rows': 5, 'dice': 1, 'roll_price': 20000, 'lap_contrib': 10, 'tiles': [],
                                  'keys_count': 0, 'pieces': [], 'board': [], 'turn': 0, 'action': {}})
slice_('dicegame_private', False, lambda: {'keys': [], 'parked': {}, 'log': [], 'settles': {}})


# ── 작은 도구 ──
def _int(v, default=None):
    """숫자로 — 못 바꾸면 default. 참/거짓 · 목록 · 글자는 숫자가 아니다(옛 _as_int)."""
    if isinstance(v, bool) or v is None:
        return default
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _brief(t):
    return {k: t.get(k) for k in ('id', 'type', 'label', 'points')}


def _clean_sig(sig):
    if not isinstance(sig, dict) or sig.get('id') is None:
        return None
    return {k: sig.get(k) for k in SIG_FIELDS}


def _piece(name, src=None):
    s = src or {}
    return {'name': name, 'pos': max(0, _int(s.get('pos'), 0) or 0), 'laps': max(0, _int(s.get('laps'), 0) or 0),
            'shield': bool(s.get('shield')), 'choose': bool(s.get('choose'))}


def plan(action):
    """⏱️ 굴림 한 번의 연출 시간표(ms, 방송판이 굴림을 받은 때부터) — 옛 _dicegame_plan(43~60) == dgRollPlan.
       land: 말이 칸에 닿는 때 · gate: 연출이 다 끝나 가리개 · 시그를 열어도 되는 때(연타 막기도 이것을 본다)."""
    a = action or {}
    roll_t = 380 if a.get('manual') else 250 + 1300 * len(a.get('dice') or [])
    land = roll_t + 300 * len(a.get('path') or []) + 120
    tt = (a.get('tile') or {}).get('type')
    gate = land + (DG_KEY_DRAW if tt == 'key' else 0) + (DG_SIG_BEAT if tt == 'sig' else DG_CARD_BEAT)
    af_start = af_step = 0
    af = a.get('after')
    if isinstance(af, dict):
        p2 = af.get('path') or []
        af_start = 3200 if tt == 'key' else 1500       # 카드 읽을 틈(열쇠 칸은 뽑기 1.7초가 더 있다)
        # 🕳️ 역주행이 길면 빨리 밟는다 — 전체 2.4초 안. ⚠️ Math.round 와 같게(파이썬 round 는 .5 를 짝수로 보낸다)
        af_step = max(90, int(2400 / len(p2) + 0.5)) if af.get('rev') and len(p2) > 8 else 220
        after_end = land + af_start + af_step * len(p2) + 120
        t2 = (af.get('tile') or {}).get('type')
        gate = max(gate, after_end + (DG_KEY_DRAW if t2 == 'key' else 0) + DG_CARD_BEAT)
    return {'rollT': roll_t, 'land': land, 'gate': gate, 'afStart': af_start, 'afStep': af_step}


_KEY_RULES = (
    # ⚠️ 순서가 중요하다 — '기여도 1등과 바꾸기' 는 '기여도 N' 보다 먼저 '바꾸기' 로 잡아야 한다
    (r'(\d+)\s*등\s*(?:이|과|와|이랑|랑)?\s*바꾸', 'swap'),
    (r'뒤\s*로\s*(\d+)\s*칸', 'back'),
    (r'앞\s*으로\s*(\d+)\s*칸', 'fwd'),
    (r'출발', 'start'),
    (r'파산', 'bankrupt'),
    (r'한\s*번\s*더', 'again'),
    (r'[실쉴]드', 'shield'),          # 옛 덱은 '실드권' — '쉴드권' 으로 적어도 알아듣는다
    (r'원하는', 'choose'),
    (r'꽝', 'nothing'),
    (r'기여도\s*(-?\d+)', 'contrib'),
)


def key_effect(text):
    """황금열쇠 글 → {'kind', 'n'} · 모르는 글이면 None(화면에 글만, 진행자가 처리)."""
    t = str(text or '')
    for rx_, kind in _KEY_RULES:
        m = re.search(rx_, t)
        if m:
            return {'kind': kind, 'n': int(m.group(1)) if m.groups() else None}
    return None


# ── 명단 맞추기 ──
def _roster(ctx):
    """말이 될 이름 — 번외 판이 켜져 있으면 번외 명단(기여도가 그리로 가니 말도 따라간다)."""
    p = ctx.read('players')
    names = []
    for r in (p['extra'] if p.get('extra_active') else p['list']):
        nm = str(r.get('name') or '').strip()
        if nm and nm not in names:
            names.append(nm)
    return names


def _prune(parked):
    """맡아 둘 게 없는 이름(출발 칸 · 0점)은 버리고, 40명을 넘으면 오래된 것부터."""
    for nm in list(parked):
        v = parked[nm] if isinstance(parked[nm], dict) else {}
        if not (v.get('pos') or v.get('laps') or v.get('shield') or v.get('choose') or v.get('pts')):
            parked.pop(nm)
    while len(parked) > PARKED_MAX:
        parked.pop(next(iter(parked)))


def _sync(ctx, g, pv):
    """말 · 전용 판을 지금 점수판 명단에 맞춘다(옛 _dicegame_sync_pieces 181 · _dicegame_sync_board 385).
    ⚠️ 명단이 비면 있던 말을 그대로 둔다 — 명단을 잠깐 비웠다고 판 위의 말이 사라지면 방송 중에 사고로 보인다.
    ⚠️ 순서는 있던 말 순서를 지킨다(새 이름만 뒤에). 차례는 자리 번호라 판을 따라 다시 서면 남의 차례를 먹는다."""
    names = _roster(ctx)
    old_ps = g['pieces']
    parked = pv['parked']
    if not names:
        if not old_ps:
            g['pieces'] = [_piece('말')]        # 명단이 비어도 말은 하나 — 판을 미리 깔아 두려면 굴리기 · 옮기기가 돼야 한다
    else:
        old = {p['name']: p for p in old_ps}
        kept = [p['name'] for p in old_ps if p['name'] in names]
        order = kept + [nm for nm in names if nm not in kept]
        # 차례는 이름으로 — 차례보다 앞사람이 빠져도 건너뛰지 않고, 차례인 사람이 빠지면 그다음 남은 사람
        ti = max(0, min(len(old_ps) - 1, _int(g.get('turn'), 0) or 0)) if old_ps else 0
        nxt = next((p['name'] for p in old_ps[ti:] + old_ps[:ti] if p['name'] in order), None)
        g['turn'] = order.index(nxt) if nxt in order else 0
        # 🅿️ 빠진 이름의 기록은 맡아 둔다 — 같은 이름이 돌아오면 그대로 되살린다
        for p in old_ps:
            if p['name'] not in order:
                parked.setdefault(p['name'], {}).update({'pos': p['pos'], 'laps': p['laps'],
                                                        'shield': bool(p['shield']), 'choose': bool(p['choose'])})
        g['pieces'] = [_piece(nm, old.get(nm) or parked.get(nm)) for nm in order]
    # 🏆 전용 판 — 점수는 이름으로 지킨다. 빠진 이름의 점수는 보관함에, 돌아오면 되살린다
    pts = {r['name']: int(r.get('pts') or 0) for r in g['board']}
    on = [p['name'] for p in g['pieces']]
    for nm, v in pts.items():
        if nm not in on:
            parked.setdefault(nm, {})['pts'] = v
    g['board'] = [{'name': nm, 'pts': pts[nm] if nm in pts else int((parked.get(nm) or {}).get('pts') or 0)} for nm in on]
    for nm in on:
        parked.pop(nm, None)
    _prune(parked)
    g['turn'] = max(0, min(len(g['pieces']) - 1, _int(g.get('turn'), 0) or 0))


def _edit(ctx):
    """작업본 둘(공개 · 비공개)을 꺼내 명단에 맞춘다 — 주사위 명령은 전부 여기서 시작한다."""
    g, pv = ctx.edit('dicegame'), ctx.edit('dicegame_private')
    _sync(ctx, g, pv)
    return g, pv


def on_roster(ctx, *_):
    """명단이 바뀐 그 자리에서 말을 맞춘다(players 의 ON_ROSTER 고리). 안 걸려 있으면 다음 주사위 명령 때 맞춘다."""
    _edit(ctx)


def on_rename(ctx, old, new):
    """✏️ 개명 — 옛 이름의 말(자리 · 바퀴 · 쉴드 · 선택권)과 전용 판 점수를 새 이름이 물려받는다(players 의 ON_RENAME 고리).
    ⚠️ 새 이름이 보관함에 있으면 '맡아 둔 사람이 돌아온 것' 이다 — 되살리기가 먼저(옛 _dicegame_rename 284).
       그때 옛 이름의 기록은 보관함으로 간다(잃지 않는다)."""
    old, new = str(old or '').strip(), str(new or '').strip()
    g, pv = ctx.edit('dicegame'), ctx.edit('dicegame_private')
    if old and new and old != new and new not in pv['parked'] and not any(p['name'] == new for p in g['pieces']):
        for p in g['pieces']:
            if p['name'] == old:
                p['name'] = new
        for r in g['board']:
            if r['name'] == old:
                r['name'] = new
        if old in pv['parked']:
            pv['parked'][new] = pv['parked'].pop(old)
    _sync(ctx, g, pv)


# ── 전용 점수판 ──
def _row(g, name):
    want = str(name or '').strip()
    return next((r for r in g['board'] if r['name'] == want), None)


def _log(ctx, pv, name, val, why):
    """🧮 '몇에 몇을 더해 몇' — 부르는 곳은 전부 점수를 **바꾼 뒤에** 부른다."""
    row = _row(ctx.read('dicegame'), name)
    e = {'at': ctx.now, 'name': name, 'val': int(val), 'why': str(why)[:80]}
    if row is not None:
        e.update({'before': row['pts'] - int(val), 'after': row['pts']})
    pv['log'].insert(0, e)
    del pv['log'][LOG_MAX:]


def _add(ctx, g, pv, name, pts, why):
    """전용 판 점수를 더한다(마이너스 됨). 판에 없는 이름이면 None."""
    r = _row(g, name)
    if r is None:
        return None
    r['pts'] += int(pts)
    _log(ctx, pv, r['name'], int(pts), why)
    return r['name']


def _ranked(g):
    """점수 높은 차례, 같으면 이름 차례 — 굴릴 때마다 순위가 흔들리면 안 된다."""
    return sorted(g['board'], key=lambda r: (-int(r.get('pts') or 0), r['name']))


def _steal(ctx, g, pv, taker, per):
    """💰 착지한 사람이 다른 말들에게서 per 점씩 — 판의 총점은 그대로(대표님: '다른 플레이어들에게서 뺏어오는 거')."""
    me = _row(g, taker)
    if me is None or not per:
        return None
    victims = [r for r in g['board'] if r is not me]
    if not victims:
        return None
    for v in victims:
        v['pts'] -= per
        _log(ctx, pv, v['name'], -per, '%s 에게 빼앗김' % me['name'])
    gain = per * len(victims)
    me['pts'] += gain
    _log(ctx, pv, me['name'], gain, '%d명에게서 %d점씩 빼앗음' % (len(victims), per))
    return {'taker': me['name'], 'per': per, 'gain': gain, 'from': [v['name'] for v in victims]}


# ── 칸 · 열쇠 효과 ──
def _apply_key(ctx, g, pv, piece, who, text, cur, allow_move):
    """뽑힌 황금열쇠의 효과(옛 89~178). 돌려받는 값: {note, after(두 번째 이동), again, kind}
    ⚠️ 말은 여기서 옮기지 않는다 — 부르는 쪽이 착지 처리를 끝낸 뒤 after 를 적용한다.
    ⚠️ allow_move=False 는 끌려온 자리에서 뽑은 경우 — 다시 옮기면 끝없이 튕길 수 있다.
    ⚠️ 바꾸기 · 파산 · 점수는 전부 **전용 판** 안에서(대표님: '전용 기여도판 안에서 해당하는 미션임')."""
    out = {'note': '', 'after': None, 'again': False, 'kind': None}
    eff = key_effect(text)
    if not eff:
        return out
    k, n = eff['kind'], eff['n']
    out['kind'] = k
    if k == 'contrib' and n:
        got = _add(ctx, g, pv, who, n, '황금열쇠: ' + str(text)) if who else None
        out['note'] = ('%s %+d점' % (got, n)) if got else '누구 차례인지 몰라 점수는 손으로'
    elif k == 'bankrupt':
        t = _row(g, who) if who else None
        if t is None:
            out['note'] = '판에서 못 찾아 파산은 손으로'
        else:
            before = t['pts']
            t['pts'] = 0
            _log(ctx, pv, t['name'], -before, '황금열쇠: 파산')
            out['note'] = '%s %d점 → 0' % (t['name'], before)
    elif k == 'swap' and n:
        me = _row(g, who) if who else None
        ranked = _ranked(g)
        tgt = ranked[n - 1] if 0 < n <= len(ranked) else None
        if me is None or tgt is None:
            out['note'] = '%d등을 못 찾아 바꾸기는 손으로' % n
        elif tgt is me:
            out['note'] = '본인이 %d등이라 바꿀 상대가 없음' % n
        else:
            a, b = me['pts'], tgt['pts']
            me['pts'], tgt['pts'] = b, a
            _log(ctx, pv, me['name'], b - a, '황금열쇠: %d등과 바꾸기' % n)
            _log(ctx, pv, tgt['name'], a - b, '황금열쇠: %d등과 바꾸기(상대)' % n)
            out['note'] = '%s %d ↔ %s %d' % (me['name'], a, tgt['name'], b)
    elif k == 'again':
        out['again'] = True
        out['note'] = '한 번 더 — 차례가 넘어가지 않는다'
    elif k == 'shield':
        # 🛡️ 10-03 대표님: "쉴드권 획득! 이라고만 뜨고 사용은 우리가 알아서 할게" — 저절로 쓰지 않는다
        piece['shield'] = True
        out['note'] = '쉴드권 획득!'
    elif k == 'choose':
        # 표시가 없으면 '기여도 10' 칸을 골라 가도 아무것도 못 받는다 — dice.move 가 이 표시를 본다
        piece['choose'] = True
        out['note'] = '원하는 칸으로 — 조종실에서 옮기면 그 칸 효과가 걸린다'
    elif k == 'nothing':
        out['note'] = '꽝'
    elif k in ('back', 'fwd', 'start'):
        if not allow_move:
            out['note'] = '끌려온 자리에서는 다시 옮기지 않는다 — 손으로'
        else:
            tiles = g['tiles']
            nt = len(tiles)
            if k == 'start':
                # 🏁 출발지로 — 블랙홀처럼 거꾸로 걸어서(예전엔 경로가 비어 순간이동했다)
                dest, kind = 0, 'goto'
                path = [(cur - i) % nt for i in range(1, cur + 1)]
            elif k == 'back':
                dest, kind = (cur - n) % nt, 'move'
                path = [(cur - i) % nt for i in range(1, n + 1)]
            else:
                dest, kind = (cur + n) % nt, 'move'
                path = [(cur + i) % nt for i in range(1, n + 1)]
            t2 = tiles[dest]
            after = {'kind': kind, 'from': cur, 'to': dest, 'path': path, 'label': str(text),
                     'rev': k in ('back', 'start'), 'tile': _brief(t2)}
            # 도착한 칸이 점수 칸이면 그 점수도 — 열쇠 · 이동 칸은 다시 걸지 않는다(끝없는 연쇄 방지)
            if t2.get('type') == 'score' and t2.get('points') and who:
                p2 = int(t2['points'])
                got = _add(ctx, g, pv, who, p2, (t2.get('label') or '점수 칸') + ' (열쇠로 이동)')
                if got:
                    after['scored'] = {'name': got, 'points': p2}
            out['after'] = after
            out['note'] = '%d번으로' % dest
    return out


def _dest_effects(ctx, g, pv, rng, piece, who, dest, tag):
    """끌려가거나 손으로 옮겨진 자리의 칸이 제 일을 한다 — 점수 · 전원 지급 · 뺏기 · 황금열쇠(옛 618~670).
    ⚠️ 다시 옮기는 칸(move · goto)에는 걸지 않는다 — 싱크홀에서 싱크홀로 끝없이 튕길 수 있다.
    ⚠️ 시그니처 칸도 안 건다 — 굴림 한 번에 두 곡이 걸릴 수 있다. 그 자리에 서면 진행자가 직접 튼다."""
    tiles = g['tiles']
    t2 = tiles[dest] if 0 <= dest < len(tiles) else {'id': dest, 'type': 'blank'}
    parts, again = {}, False
    d2 = t2.get('type')
    p2 = _int(t2.get('points'), 0) or 0
    if d2 == 'score' and p2:
        if who:
            got = _add(ctx, g, pv, who, p2, (t2.get('label') or '점수 칸') + tag)
            if got:
                parts['scored'] = {'name': got, 'points': p2}
            else:
                parts['note'] = "'%s' 을(를) 명단에서 못 찾아 기여도는 안 넣었습니다" % who
        else:
            parts['note'] = '누구 차례인지 몰라 기여도는 손으로 주세요'
    elif d2 == 'giveall':
        names = []
        if p2:
            why = (t2.get('label') or '전원 지급') + ' 칸' + tag
            names = [nm for nm in (p['name'] for p in g['pieces']) if _add(ctx, g, pv, nm, p2, why)]
        parts['giveall'] = {'points': p2, 'names': names}
    elif d2 == 'steal':
        st = _steal(ctx, g, pv, who or piece['name'], p2)
        if st:
            parts['steal'] = st
    elif d2 == 'key':
        keys = pv['keys']
        parts['key'] = rng.choice(keys) if keys else '(황금열쇠 덱이 비어 있습니다)'
        if keys:
            ke = _apply_key(ctx, g, pv, piece, who, parts['key'], dest, allow_move=False)
            if ke['note']:
                parts['key_effect'] = ke['note']
            if ke['kind']:
                parts['key_kind'] = ke['kind']
            again = ke['again']
    return {'parts': parts, 'again': again, 'tile': _brief(t2)}


def _pick(g, want):
    """어느 말인가 — 이름 · 번호 둘 다 받는다. 안 주면 차례 말. 줬는데 없으면 None(부르는 쪽이 알린다)."""
    ps = g['pieces']
    if not ps:
        return None
    want = '' if want is None else str(want).strip()
    if want:
        for i, p in enumerate(ps):
            if p['name'] == want:
                return i
        i = _int(want)
        return i if i is not None and 0 <= i < len(ps) else None
    return max(0, min(len(ps) - 1, _int(g.get('turn'), 0) or 0))


def _no_piece(g, want):
    return CommandError("'%s' 말이 없습니다. 있는 말: %s" % (want, ' · '.join(p['name'] for p in g['pieces'])))


def _rng(data):
    """🎲 운은 서버가 — seed 를 주면 같은 굴림이 나온다(검사용). 안 주면 매번 새로."""
    seed = data.get('seed')
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, (int, str))):
        raise CommandError('seed 는 숫자나 글자입니다')
    return random.Random(seed)


def _clear_stage(ctx):
    """주사위판이 지금 무대면 내린다(다른 판이 올라와 있으면 그대로 — 옛 show.clear_stage)."""
    if ctx.read('show')['stage'] == 'dicegame':
        sh.set_stage(ctx, None)


def _layout(ctx, g, pv, cols, rows, dice, roll_price, lap_contrib):
    """판을 새로 깐다 — 같은 번호 칸 내용은 남기고(크기만 바꿔도 적어 둔 게 안 날아가게), 말은 전부 출발로."""
    n = 2 * (cols + rows) - 4
    old = {t.get('id'): t for t in g['tiles']}
    tiles = []
    for i in range(n):
        prev = old.get(i)
        if i == 0:
            tiles.append({'id': 0, 'type': 'start', 'label': '출발'})
        elif prev and prev.get('type') in TILE_TYPES and prev.get('type') != 'start':
            tiles.append(prev)
        else:
            tiles.append({'id': i, 'type': 'blank', 'label': ''})
    g.update({'cols': cols, 'rows': rows, 'dice': dice, 'tiles': tiles, 'roll_price': roll_price, 'lap_contrib': lap_contrib,
              'pieces': [_piece(p['name']) for p in g['pieces']], 'turn': 0,
              'action': {'type': 'PLACE', 'ts': int(ctx.now * 1000)}})
    # 🅿️ 맡아 둔 이름도 새 판에선 출발부터(점수는 판 크기와 상관없으니 그대로)
    for v in pv['parked'].values():
        v.update({'pos': 0, 'laps': 0, 'shield': False, 'choose': False})
    _prune(pv['parked'])
    sh.set_stage(ctx, 'dicegame')       # 📺 판을 깔면 무대에 올린다
    return n


# ── 명령 ──
@command('dice.setup')
def setup(ctx, data):
    """판을 깐다. ⚠️ '안 보낸 것'(기본값)과 '보냈는데 숫자가 아닌 것'(거절)을 가른다 — 쓰레기를 조용히 기본값으로 바꾸면
       잘못 보낸 쪽이 영영 모른다. 한 판 값 · 한 바퀴 값은 안 보내면 쓰던 값(크기만 바꿨는데 단가가 돌아가면 사고)."""
    g, pv = _edit(ctx)

    def opt(key, default):
        if data.get(key) is None:
            return default
        v = _int(data.get(key))
        if v is None:
            raise CommandError('숫자가 아닙니다: %s' % key)
        return v
    cols = max(4, min(10, opt('cols', 7)))
    rows = max(3, min(8, opt('rows', 5)))
    dice = max(1, min(2, opt('dice', 1)))          # 🎲 한 개로 굴린다 — 대표님이 정함(두 개 기능은 남긴다)
    roll_price = max(0, min(10000000, opt('roll_price', _int(g.get('roll_price'), 20000))))
    lap_contrib = max(0, min(1000, opt('lap_contrib', _int(g.get('lap_contrib'), 10))))
    n = _layout(ctx, g, pv, cols, rows, dice, roll_price, lap_contrib)
    ctx.notes.update({'tiles': n, 'roll_price': roll_price, 'lap_contrib': lap_contrib})


@command('dice.tile')
def tile(ctx, data):
    """칸 하나. 시그 칸은 시그니처 정보를 **명령 밖에서** 미리 받아(sig) 칸에 붙여 둔다 — 굴리는 순간 받으러 가지 않게."""
    g, pv = _edit(ctx)
    tid = _int(data.get('id'))
    ttype = str(data.get('type') or '').strip()
    if tid is None:
        raise CommandError('칸 번호가 없습니다')
    if ttype not in TILE_TYPES:
        raise CommandError('모르는 칸 종류: %s' % ttype)
    if tid == 0 or ttype == 'start':
        raise CommandError('출발 칸은 바꿀 수 없습니다')
    label = str(data.get('label') or '').strip()[:60]
    points = max(-1000, min(1000, _int(data.get('points'), 0) or 0))
    sig = None
    if ttype == 'sig':
        sid = _int(data.get('sig_id'))
        if sid is None:
            raise CommandError('시그니처를 골라 주세요')
        sig = _clean_sig(data.get('sig'))
        if not sig or str(sig['id']) != str(sid):
            raise CommandError('그 시그니처를 찾지 못했습니다', 404)
    if not 0 <= tid < len(g['tiles']):
        raise CommandError('없는 칸입니다')
    t = {'id': tid, 'type': ttype, 'label': label}
    # ⚠️ 예전엔 score 만 숫자를 저장해 싱크홀(−5) · 전원 지급(5)이 0 으로 저장됐다(밟아도 아무 일 없음)
    if ttype in NUM_TYPES:
        t['points'] = points
    if sig:
        t['sig'] = sig
        if not label:
            t['label'] = str(sig.get('title') or '')[:60]
    g['tiles'][tid] = t
    ctx.notes['tile'] = t


@command('dice.keys')
def keys(ctx, data):
    """황금열쇠 덱을 통째로. 덱은 비공개 조각에 — 방송판은 장수(keys_count)만 안다."""
    raw = data.get('keys')
    if not isinstance(raw, list):
        raise CommandError('목록이 아닙니다')
    ks = [str(k).strip()[:KEY_LEN] for k in raw if str(k or '').strip()][:KEYS_MAX]
    g, pv = _edit(ctx)
    pv['keys'] = ks
    g['keys_count'] = len(ks)
    ctx.notes['count'] = len(ks)


@command('dice.roll')
def roll(ctx, data):
    """🎲 굴린다. 눈 · 경로 · 황금열쇠 · 끌려가기 · 연출 시간표까지 전부 여기서 정해 action 에 싣는다
       (화면마다 따로 정하면 방송판 두 개가 서로 다른 결과를 보여 준다).
       {piece?: 어느 말, player?: 점수 받을 사람(말 이름이면 그 말이 간다), value?: 현실에서 굴린 눈 1~6, seed?: 검사용}"""
    g, pv = _edit(ctx)
    now_ms = int(ctx.now * 1000)
    player = str(data.get('player') or '').strip()
    want = data.get('piece')
    idx = None
    if want not in (None, ''):
        idx = _pick(g, want)
        if idx is None:
            raise _no_piece(g, want)
    # ⚠️ 말 고르기에는 이번 요청에 온 값만 — '기억해 둔 사람' 을 쓰면 손으로 옮겨 놔도 그 말만 움직였다
    if idx is None and player:
        idx = _pick(g, player)
    if idx is None:
        idx = _pick(g, None)
    tiles = g['tiles']
    if not tiles:
        raise CommandError('먼저 판을 깔아 주세요')
    stage = ctx.read('show')['stage']
    if stage != 'dicegame':
        if stage:
            raise CommandError("지금 무대에 '%s' 판이 올라가 있어요 — 주사위판을 먼저 올려 주세요" % STAGE_LABEL.get(stage, stage))
        raise CommandError('주사위판이 방송에 안 떠 있어요 — 먼저 띄워 주세요')
    # ⏱️ 연타 막기 — 앞 굴림의 연출(끌려가기 · 열쇠 뽑기 · 카드 읽을 틈까지)이 끝나기 전이면 거절
    prev = g['action']
    if prev.get('type') == 'ROLL':
        left = plan(prev)['gate'] + ROLL_GAP - (now_ms - int(prev.get('ts') or 0))
        if left > 0:
            raise CommandError('앞 연출이 아직 안 끝났어요 — %.1f초 뒤에 다시 눌러 주세요' % (left / 1000.0), 429)
    rng = _rng(data)
    manual = data.get('value') is not None
    if manual:
        v = _int(data.get('value'))
        if v is None or not 1 <= v <= 6:
            raise CommandError('주사위 눈은 1~6 입니다')         # 7 이나 글자가 들어오면 말이 엉뚱한 데로 간다
        dice = [v]
    else:
        dice = [rng.randint(1, 6) for _ in range(max(1, min(2, _int(g.get('dice'), 1) or 1)))]
    # ── 여기부터 바꾼다(위는 거절될 수 있는 검사뿐 — 거절되면 v2 는 원래 아무것도 안 바뀐다) ──
    piece = g['pieces'][idx]
    piece['choose'] = False                # '원하는 곳으로' 를 뽑고 안 옮긴 채 다시 굴렸으면 선택권은 사라진다
    who = player or piece['name']          # 🙋 고른 사람, 아니면 **움직인 말의 주인**
    n = len(tiles)
    steps = sum(dice)
    frm = piece['pos'] % n
    to = (frm + steps) % n
    # 🏁 한 바퀴 = 출발을 지나치면. ⚠️ 이 규칙은 두 번 뒤집혔다(지나침 → 밟을 때만 → 지나침). 지금은 '지나침' 이 대표님 뜻이다
    lap = frm + steps >= n
    path = [(frm + i) % n for i in range(1, steps + 1)]
    t = tiles[to]
    tt = t.get('type')
    action = {'type': 'ROLL', 'ts': now_ms, 'dice': dice, 'from': frm, 'to': to, 'piece': piece['name'], 'piece_idx': idx,
              'manual': manual, 'path': path, 'lap': lap, 'tile': _brief(t)}
    sig = t.get('sig') if tt == 'sig' and isinstance(t.get('sig'), dict) else None
    if sig:
        action['tile']['image'] = sig.get('image_url')
    # 🔑 황금열쇠 — 뽑기도 서버가(화면마다 다른 카드가 나오면 안 된다). 이동은 착지 처리 뒤에
    ke_after, again = None, False
    if tt == 'key':
        deck = pv['keys']
        action['key'] = rng.choice(deck) if deck else '(황금열쇠 덱이 비어 있습니다)'
        if deck:
            ke = _apply_key(ctx, g, pv, piece, who, action['key'], to, allow_move=True)
            if ke['note']:
                action['key_effect'] = ke['note']
            if ke['kind']:
                action['key_kind'] = ke['kind']
            ke_after, again = ke['after'], ke['again']
    # 💯 점수 칸 — 전용 판에만. 꽝(0점)은 아무것도 안 준다(대표님: '꽝에 가면 기여도 2점도 안 올라가게')
    if tt == 'score' and _int(t.get('points'), 0):
        p = int(t['points'])
        got = _add(ctx, g, pv, who, p, '🎲 점수 칸 %+d' % p)
        if got:
            action['scored'] = {'name': got, 'points': p}
        else:
            action['score_note'] = "'%s' 을(를) 판에서 못 찾아 점수를 넣지 않았습니다" % who
    # 🎵 시그 칸 — 기여도는 시그 값에서 '한 판 값' 을 뺀 만큼(한 판을 산 후원이 이미 점수를 받았다 · 0 아래면 0)
    if sig:
        amt = _int(sig.get('amount'), 0) or 0
        price = max(0, _int(g.get('roll_price'), 20000) or 0)
        c = max(0, man_won(amt - price))
        why = '%s (%s원 − 한 판 %s원)' % (str(sig.get('title') or '')[:40], format(amt, ','), format(price, ','))
        if c > 0:
            got = _add(ctx, g, pv, who, c, why)
            if got:
                action['contrib'] = {'name': got, 'points': c, 'why': why}
    # 🏁 한 바퀴 — 시그 칸을 밟으며 한 바퀴여도 둘 다(각각 다른 이유로 받는다)
    if lap:
        lc = max(0, _int(g.get('lap_contrib'), 10) or 0)
        if lc:
            got = _add(ctx, g, pv, who, lc, '한 바퀴 돌았습니다 (%d번째)' % (piece['laps'] + 1))
            if got:
                action['lap_contrib'] = {'name': got, 'points': lc}
    piece['pos'] = to
    if lap:
        piece['laps'] += 1
    # 🕳️ 다시 옮기는 칸(싱크홀 · 블랙홀) — 두 번째 이동은 한 바퀴를 안 센다(벌칙으로 끌려간 것)
    #    🛡️ 쉴드권이 저절로 막지 않는다(10-03)
    pts = _int(t.get('points'), 0) or 0
    if tt in ('move', 'goto'):
        dest = (to + pts) % n if tt == 'move' else pts % n
        if tt == 'goto':
            # 🌀 블랙홀도 걸어간다 — **반대 방향으로**(앞으로 한 칸처럼 그리면 벌칙이 보너스로 보인다)
            path2 = [(to - i) % n for i in range(1, (to - dest) % n + 1)]
        elif pts < 0:
            path2 = [(to - i) % n for i in range(1, -pts + 1)]
        else:
            path2 = [(to + i) % n for i in range(1, pts + 1)]
        piece['pos'] = dest
        action['after'] = {'kind': tt, 'from': to, 'to': dest, 'path': path2, 'label': t.get('label') or '',
                           'rev': tt == 'goto' or pts < 0, 'tile': _brief(tiles[dest])}
        fx = _dest_effects(ctx, g, pv, rng, piece, who, dest, ' (끌려간 자리)')
        action['after'].update(fx['parts'])
        again = again or fx['again']
        to = dest
    elif tt == 'giveall':
        names = []
        if pts:
            why = (t.get('label') or '전원 지급') + ' 칸'
            names = [nm for nm in (p['name'] for p in g['pieces']) if _add(ctx, g, pv, nm, pts, why)]
        action['giveall'] = {'points': pts, 'names': names}
    elif tt == 'steal':
        st = _steal(ctx, g, pv, who, pts)
        if st:
            action['steal'] = st
        else:
            action['score_note'] = '뺏을 상대가 없습니다'
    # 열쇠가 만든 두 번째 이동(뒤로 N칸 · 앞으로 N칸 · 출발지로)
    if ke_after and not action.get('after'):
        action['after'] = ke_after
        piece['pos'] = to = ke_after['to']
    # 🙋 차례는 **그대로** — 방금 굴린 말이 다음에도 굴린다(대표님 09-30: '내가 바꾸기 전까진 그대로 냅두게 해줘')
    g['turn'] = idx
    action['plan'] = plan(action)
    g['action'] = action
    if sig:
        # ⏳ 대기줄에는 지금 넣고(재시작해도 안 잃게), 재생은 연출이 끝난 뒤(play_after)
        # 🎲 후원이 아니다 — 금액 0 · 팝업 없음 · 집계 안 셈. 누가 밟았는지만 띄운다
        rx.enqueue(ctx, sig, amount=0, donator=who, message='🎲 주사위로 뽑은 시그', skip_popup=True, count_tally=False,
                   play_after=now_ms + action['plan']['gate'])
        it = ctx.edit('queue')['items'][-1]
        it.update({'source': 'dice', 'banner': '%s · 시그 칸 도착' % who})
    ctx.notes.update({'dice': dice, 'to': to, 'tile': action['tile'], 'lap': lap, 'piece': piece['name'],
                      'scored': action.get('scored'), 'note': action.get('score_note'), 'steal': action.get('steal'),
                      'giveall': action.get('giveall'), 'contrib': action.get('contrib'),
                      'lap_contrib': action.get('lap_contrib'), 'key': action.get('key'),
                      'key_effect': action.get('key_effect'), 'again': bool(again), 'plan': action['plan']})


@command('dice.move')
def move(ctx, data):
    """말을 손으로 옮긴다(연출이 어긋났을 때의 비상 손잡이). 안 고르면 차례 말 — 굴리기와 **같은 규칙**.
       '원하는 곳으로' 를 뽑은 말이면 옮겨진 칸이 그 말 주인에게 제 일을 한다(한 번만)."""
    g, pv = _edit(ctx)
    pos = _int(data.get('pos'))
    if pos is None:
        raise CommandError('칸 번호가 숫자가 아닙니다')
    n = len(g['tiles'])
    if not n:
        raise CommandError('먼저 판을 깔아 주세요')
    if not 0 <= pos < n:
        raise CommandError('칸 번호는 0~%d 입니다' % (n - 1))
    idx = _pick(g, data.get('piece'))
    if idx is None:
        raise _no_piece(g, data.get('piece'))
    piece = g['pieces'][idx]
    piece['pos'] = pos
    action = {'type': 'MOVE', 'ts': int(ctx.now * 1000), 'to': pos, 'piece': piece['name'], 'piece_idx': idx}
    if piece['choose']:
        piece['choose'] = False
        fx = _dest_effects(ctx, g, pv, _rng(data), piece, piece['name'], pos, ' (원하는 곳으로)')
        action.update({'tile': fx['tile'], 'choose': True})
        action.update(fx['parts'])
        if fx['again']:
            g['turn'] = idx
    g['action'] = action
    ctx.notes.update({'pos': pos, 'piece': piece['name']})
    ctx.notes.update({k: action[k] for k in ('tile', 'scored', 'note', 'giveall', 'steal', 'key', 'key_effect', 'key_kind', 'choose')
                      if k in action})


@command('dice.shield')
def shield(ctx, data):
    """🛡️ 쉴드권 표시. 점수 · 자리는 안 건드린다 — 쓰는 내용(되돌리기 등)은 진행자가 따로 한다."""
    g, pv = _edit(ctx)
    want = str(data.get('piece') or '').strip()
    idx = _pick(g, want) if want else None
    if idx is None:
        raise CommandError("'%s' 말이 없습니다" % want)
    g['pieces'][idx]['shield'] = bool(data.get('on'))
    ctx.notes.update({'piece': g['pieces'][idx]['name'], 'shield': g['pieces'][idx]['shield']})


@command('dice.reset')
def reset(ctx, data):
    """말을 출발로 · 무대에서 내린다. 칸 구성 · 덱 · 전용 판 점수는 남긴다 — 적는 데 든 손이 아깝다."""
    g, pv = _edit(ctx)
    for p in g['pieces']:
        p.update({'pos': 0, 'laps': 0})
    for v in pv['parked'].values():
        v.update({'pos': 0, 'laps': 0})
    _prune(pv['parked'])
    g.update({'turn': 0, 'action': {'type': 'PLACE', 'ts': int(ctx.now * 1000)}})
    _clear_stage(ctx)


@command('dice.board')
def board(ctx, data):
    """🏆 전용 판 손보기 — {do:'reset'} 전원 0점 · {do:'set'|'add', name, pts}. 엑셀판(진짜 기여도)은 안 건드린다."""
    g, pv = _edit(ctx)
    do = str(data.get('do') or '').strip().lower()
    if do == 'reset':
        for r in g['board']:
            r['pts'] = 0
    elif do in ('set', 'add'):
        pts = _int(data.get('pts'))
        if pts is None:
            raise CommandError('점수가 숫자가 아닙니다')
        r = _row(g, data.get('name'))
        if r is None:
            raise CommandError("'%s' 가 판에 없습니다. 있는 사람: %s"
                               % (str(data.get('name') or '').strip(), ' · '.join(x['name'] for x in g['board'])))
        before = r['pts']
        r['pts'] = pts if do == 'set' else before + pts
        _log(ctx, pv, r['name'], r['pts'] - before, '손으로 고침')
    else:
        raise CommandError("do 는 reset · set · add 중 하나입니다 (기여도로 옮기기는 dice.settle)")
    ctx.notes['board'] = g['board']


@command('dice.settle')
def settle(ctx, data):
    """🎯 전용 판 점수를 진짜 기여도에 더한다(점수는 그대로 — 그날 일당이라 게임으로 안 오른다).
    ⚠️ 이 게임에서 진짜 기여도를 건드리는 **유일한** 곳 — 대표님이 눌러야만 넘어간다.
    ⚠️ 명단에서 못 찾은 사람(맡아 둔 사람 포함)은 옮기지 않고 판에 **남긴다**(예전엔 옮기지도 않고 지웠다).
    v2: 정산은 되돌리기 장부에 한 묶음(ref)으로 남는다 — score.undo 하면 기여도가 빠지고 전용 판 점수가 돌아온다."""
    g, pv = _edit(ctx)
    p = ctx.read('players')
    on_list = {r['name'] for r in p[pl._list_key(p)]}
    items, moved, skipped = [], [], []
    for r in g['board']:
        if not r['pts']:
            continue
        if r['name'] in on_list:
            items.append({'name': r['name'], 'delta': 0, 'contrib': r['pts']})
            moved.append({'name': r['name'], 'points': r['pts']})
        else:
            skipped.append({'name': r['name'], 'points': r['pts']})
    on_board = {r['name'] for r in g['board']}
    for nm, v in pv['parked'].items():
        if v.get('pts') and nm not in on_board:
            skipped.append({'name': nm, 'points': int(v['pts']), 'parked': True})
    ref = None
    if items:
        ref = 'dgs_%d_%s' % (int(ctx.now * 1000), uuid.uuid4().hex[:6])
        pl.apply_scores(ctx, items, reason='🎲 주사위게임 정산', ref=ref, popup=False, takeover=False)
        clear = data.get('clear', True) is not False
        if clear:
            done = {m['name'] for m in moved}
            for r in g['board']:
                if r['name'] in done:
                    r['pts'] = 0
        pv['settles'][ref] = {'pts': {m['name']: m['points'] for m in moved}, 'cleared': clear}
        while len(pv['settles']) > SETTLES_MAX:
            pv['settles'].pop(next(iter(pv['settles'])))
    ctx.notes.update({'moved': moved, 'skipped': skipped, 'ref': ref, 'board': g['board']})


def _undo_settle(ctx, ref):
    """정산을 되돌리면(score.undo) 비웠던 전용 판 점수도 돌아온다 — 안 그러면 점수가 허공으로 사라진다."""
    rec = ctx.read('dicegame_private')['settles'].get(ref)
    if not rec:
        return
    g, pv = ctx.edit('dicegame'), ctx.edit('dicegame_private')
    if rec.get('cleared'):
        for nm, v in rec['pts'].items():
            r = _row(g, nm)
            if r is not None:
                r['pts'] += int(v)
                _log(ctx, pv, nm, int(v), '정산 되돌리기')
            else:                                        # 그 사이 명단에서 빠졌다 — 보관함에 돌려 둔다
                slot = pv['parked'].setdefault(nm, {})
                slot['pts'] = int(slot.get('pts') or 0) + int(v)
    pv['settles'].pop(ref, None)


pl.ON_UNDO.append(_undo_settle)


@command('dice.preset')
def preset(ctx, data):
    """22칸 기본판 · 손그림판을 한 번에(옛 조종실이 칸 22번을 따로 보내던 것 — 이제 한 명령, 하나라도 틀리면 아무것도 안 바뀐다).
       {name:'basic22'|'draw22', tiles_only?: 판은 그대로 두고 칸 내용만(말 위치 · 점수 그대로), sigs?: 시그니처 목록(명령 밖에서)}
       시그 칸은 이름으로 찾고, 못 찾으면 빈칸으로 두고 notes.missing 으로 알린다(엉뚱한 걸 붙이지 않는다)."""
    pr = PRESETS.get(str(data.get('name') or ''))
    if pr is None:
        raise CommandError('모르는 판입니다 (basic22 · draw22)')
    g, pv = _edit(ctx)
    if data.get('tiles_only'):
        if len(g['tiles']) != 22:
            raise CommandError('22칸 판이 아닙니다 — 먼저 판을 깔아 주세요')
    else:
        _layout(ctx, g, pv, 8, 5, 1, _int(g.get('roll_price'), 20000), _int(g.get('lap_contrib'), 10))
    sigs = [s for s in (data.get('sigs') or []) if isinstance(s, dict) and s.get('id') is not None]
    missing = []
    for spec in pr['tiles']:
        t = {'id': spec['id'], 'type': spec['type'], 'label': spec.get('label', '')}
        if spec['type'] in NUM_TYPES:
            t['points'] = spec['points']
        if spec['type'] == 'sig':
            found = find_sig(sigs, spec['sig_name'])
            if not found:
                missing.append('%d번 “%s”' % (spec['id'], spec['sig_name']))
                t = {'id': spec['id'], 'type': 'blank', 'label': ''}
            else:
                t.update({'sig': _clean_sig(found), 'label': spec['sig_name']})
        g['tiles'][spec['id']] = t
    if pr.get('keys') is not None:
        pv['keys'] = list(pr['keys'])
        g['keys_count'] = len(pr['keys'])
    ctx.notes.update({'tiles': len(g['tiles']), 'missing': missing, 'keys': g['keys_count']})


_SIG_NORM = re.compile(r'[\s"\'`‘’“”!?.,~]')


def find_sig(sigs, name):
    """시그니처를 이름으로 — 띄어쓰기 · 따옴표 · 느낌표 · 대소문자 무시, 없으면 '이름이 들어 있는 것'(두 글자 이상). 옛 dgcFindSig."""
    def norm(v):
        return _SIG_NORM.sub('', str(v or '')).lower()
    want = norm(name)
    for s in sigs:
        if norm(s.get('title')) == want:
            return s
    if len(want) >= 2:
        for s in sigs:
            if want in norm(s.get('title')):
                return s
    return None


# ══ 22칸 판 두 벌(옛 controller.html DGC_PRESET_22 · DGC_PRESET_22_DRAW · DGC_KEYS_DRAW) — 8×5 테두리, 주사위 한 개 ══
#  기본판: 출발 1 · 시그 5(이꾸욧 2 · 포카치노 1 · 멈춘시간 2) · 꽝 2 · 코끼리코 3 · 기여도20 1 · 기여도10 2 · 5점 3 · 고수 2 · 완력기 3
#    같은 종류가 붙지 않게, 시그는 네 칸쯤 띄워 흩었다. 미션은 사람이 해 봐야 아는 것(성공하면 진행자가 준다).
#    ⚠️ 꽝은 0점 — 예전엔 2점이라 밟으면 기여도가 붙었다.
BASIC22 = [
    {'id': 1, 'type': 'score', 'label': '5점', 'points': 5},
    {'id': 2, 'type': 'sig', 'sig_name': '이꾸욧'},
    {'id': 3, 'type': 'mission', 'label': '완력기'},
    {'id': 4, 'type': 'score', 'label': '10점', 'points': 10},
    {'id': 5, 'type': 'mission', 'label': '코끼리코'},
    {'id': 6, 'type': 'sig', 'sig_name': '멈춘시간'},
    {'id': 7, 'type': 'score', 'label': '꽝!', 'points': 0},
    {'id': 8, 'type': 'mission', 'label': '고수'},
    {'id': 9, 'type': 'score', 'label': '5점', 'points': 5},
    {'id': 10, 'type': 'sig', 'sig_name': '포카치노'},
    {'id': 11, 'type': 'mission', 'label': '완력기'},
    {'id': 12, 'type': 'score', 'label': '20점!', 'points': 20},
    {'id': 13, 'type': 'mission', 'label': '코끼리코'},
    {'id': 14, 'type': 'sig', 'sig_name': '이꾸욧'},
    {'id': 15, 'type': 'score', 'label': '꽝!', 'points': 0},
    {'id': 16, 'type': 'mission', 'label': '완력기'},
    {'id': 17, 'type': 'score', 'label': '5점', 'points': 5},
    {'id': 18, 'type': 'mission', 'label': '고수'},
    {'id': 19, 'type': 'sig', 'sig_name': '멈춘시간'},
    {'id': 20, 'type': 'mission', 'label': '코끼리코'},
    {'id': 21, 'type': 'score', 'label': '10점', 'points': 10},
]
#  손그림판: 대표님이 종이에 그린 판 그대로(왼쪽 위 출발에서 시계 방향). 싱크홀 · 블랙홀 · 뺏기는 서버가 저절로 —
#    ⚠️ 진행자가 손으로 또 옮기면 벌칙이 두 번 걸린다.
DRAW22 = [
    {'id': 1, 'type': 'score', 'label': '기여도 10', 'points': 10},
    {'id': 2, 'type': 'score', 'label': '기여도 5', 'points': 5},
    {'id': 3, 'type': 'mission', 'label': '분장'},
    {'id': 4, 'type': 'score', 'label': '기여도 -10', 'points': -10},
    {'id': 5, 'type': 'score', 'label': '기여도 5', 'points': 5},
    {'id': 6, 'type': 'mission', 'label': '고팍'},
    {'id': 7, 'type': 'move', 'label': '싱크홀 · 뒤 5칸', 'points': -5},
    {'id': 8, 'type': 'key', 'label': '황금열쇠'},
    {'id': 9, 'type': 'mission', 'label': '코끼리코'},
    {'id': 10, 'type': 'score', 'label': '기여도 10', 'points': 10},
    {'id': 11, 'type': 'steal', 'label': '각 플레이어에게서 5점씩', 'points': 5},
    {'id': 12, 'type': 'mission', 'label': '분장'},
    {'id': 13, 'type': 'score', 'label': '기여도 5', 'points': 5},
    {'id': 14, 'type': 'mission', 'label': '고팍'},
    {'id': 15, 'type': 'score', 'label': '기여도 20', 'points': 20},
    {'id': 16, 'type': 'score', 'label': '기여도 -10', 'points': -10},
    {'id': 17, 'type': 'mission', 'label': '코끼리코'},
    {'id': 18, 'type': 'move', 'label': '싱크홀 · 뒤 5칸', 'points': -5},
    {'id': 19, 'type': 'key', 'label': '황금열쇠'},
    {'id': 20, 'type': 'score', 'label': '기여도 30', 'points': 30},
    {'id': 21, 'type': 'goto', 'label': '블랙홀 · 출발점으로', 'points': 0},
]
KEYS_DRAW = ['기여도 1등과 바꾸기', '뒤로 7칸', '출발지로 (뒤)', '기여도 50', '한 번 더',
             '꽝', '원하는 곳으로', '실드권', '파산', '3등과 바꾸기']
PRESETS = {'basic22': {'tiles': BASIC22, 'keys': None}, 'draw22': {'tiles': DRAW22, 'keys': KEYS_DRAW}}


# ── 명령 밖에서 미리 할 일(시그니처 조회는 바깥 왕복 — 명령 안에서 하면 그동안 모든 버튼이 멈춘다) ──
def _pre_tile(bus, data):
    if 'sig' in data:
        return data                      # 이미 실려 왔다(검사 · 다른 길)
    if str(data.get('type') or '').strip() == 'sig' and data.get('sig_id') is not None:
        return dict(data, sig=bus.sigs.by_id(data.get('sig_id')))
    return data


def _pre_preset(bus, data):
    if 'sigs' in data:
        return data
    return dict(data, sigs=bus.sigs.rows()) if data.get('name') == 'basic22' else data


PREFETCH = {'dice.tile': _pre_tile, 'dice.preset': _pre_preset}


# ── 방송 시작 · 끝 — 방송 1회분만 걷는다(칸 · 덱 · 판 크기 · 값은 다음 주에도 쓰는 설정) ──
def _reset_session(ctx, data):
    g, pv = ctx.edit('dicegame'), ctx.edit('dicegame_private')
    for p in g['pieces']:
        p.update({'pos': 0, 'laps': 0, 'shield': False, 'choose': False})   # 쉴드 · '원하는 곳으로' 도 이번 방송 것
    # ⚠️ 예전엔 말 자리만 비우고 전용 판은 남겨, 정산을 깜빡하면 지난주 점수가 이번 주 기여도에 섞였다
    for r in g['board']:
        r['pts'] = 0
    g.update({'turn': 0, 'action': {}})
    pv.update({'parked': {}, 'log': [], 'settles': {}})
    _sync(ctx, g, pv)


ses.ON_START.append(_reset_session)
ses.ON_END.append(_reset_session)

# 🔗 공용 모듈에 고리가 생기면 저절로 걸린다(없으면 다음 주사위 명령 때 명단을 맞추고, 시그 정보는 data 로 받는다)
if isinstance(getattr(pl, 'ON_ROSTER', None), list):
    pl.ON_ROSTER.append(on_roster)
if isinstance(getattr(pl, 'ON_RENAME', None), list):
    pl.ON_RENAME.append(on_rename)
if isinstance(getattr(_bus, 'PREFETCH', None), dict):
    _bus.PREFETCH.update(PREFETCH)
