# -*- coding: utf-8 -*-
"""🎲 주사위게임(부루마블식)과 그 전용 점수판.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import copy
import random
import show as showmod
import time
import uuid
from flask import jsonify, request
import server  # 연습 서버가 가짜로 바꿔 끼우는 시그니처 조회는 부를 때마다 server 에서 찾는다
from server import (
    DEFAULT_STATE, LOG_MAX, _as_int, _find_score_target, _stage_log, app, broadcast_event,
    enqueue_signature, file_lock, load_data, man_won, now_hms, save_data,
)


# ==========================================
# 🎲 주사위게임 (부루마블식) — 로그인 필요 (exempt 목록에 없음)
#   시그뒤집기와 같은 원칙: 서버가 유일한 진실, 화면은 action 신호로 연출만.
# ==========================================
#    move    : 말을 points 칸만큼 옮긴다(음수면 뒤로). 싱크홀 = -5
#    goto    : points 번 칸으로 보낸다. 블랙홀 = 0(출발점)
#    giveall : 모든 말 주인에게 points 만큼 준다 (전원 지급 — 판의 총점이 늘어난다)
#    steal   : 착지한 사람이 **다른 말들에게서** points 만큼씩 뺏는다 (총점은 그대로)
#              사장님: "각 플레이어 5점씩 받는건 다른 플레이어들에게서 뺏어오는거였음"
#    ⚠️ 옮겨 간 칸의 효과는 **다시 걸지 않는다**. 걸면 싱크홀→싱크홀 로
#       끝없이 튕길 수 있고, 방송 중에 그게 터지면 손쓸 수가 없다.
DICE_TILE_TYPES = ('start', 'blank', 'mission', 'sig', 'score', 'key',
                   'move', 'goto', 'giveall', 'steal')

# ⏱️ 굴림 한 번의 연출 시간표 — 방송판 dgRollPlan(overlay.html)과 **같은 식**이어야 한다.
#    tests/dice_timing_test.py 가 두 식에 같은 굴림을 넣어 맞춰 본다.
#    ⚠️ 예전엔 연타 막기(429)가 '걸어가는 시간'까지만 셌다. 끌려가기 · 열쇠 뽑기 · 카드 읽을 틈을
#       안 세서 블랙홀이 거꾸로 걷는 중에 다음 굴림이 끼어들었다(시험 서버 실측 3.2초).
DG_SIG_BEAT = 1500    # 🎵 시그 칸 — "시그니처 재생!" 카드를 읽을 틈. 그 뒤에 가리개 + 시그 재생
                      #    대표님: "주사위 굴리고 이동하고 시그니처 걸린 게 뜨고 리액션모드로 들어가서 재생"
DG_CARD_BEAT = 1500   # 다른 칸 — 카드를 읽을 틈(다른 후원 시그가 판을 덮기 전)
DG_KEY_DRAW = 1700    # 🔑 황금열쇠 뽑기 연출(dgKeyDraw)


def _dicegame_plan(action):
    """굴림 신호를 받은 때부터 잰 연출 시각(ms).
    land: 말이 칸에 닿는 때 · gate: 연출이 다 끝나 시그를 틀어도 되는 때(연타 막기도 이걸 본다)."""
    a = action or {}
    roll_t = 380 if a.get('manual') else 250 + 1300 * len(a.get('dice') or [])
    land = roll_t + 300 * len(a.get('path') or []) + 120
    tt = (a.get('tile') or {}).get('type')
    gate = land + (DG_KEY_DRAW if tt == 'key' else 0) + (DG_SIG_BEAT if tt == 'sig' else DG_CARD_BEAT)
    af = a.get('after')
    if isinstance(af, dict):
        p2 = af.get('path') or []
        start = 3200 if tt == 'key' else 1500
        # ⚠️ Math.round 와 같게 반올림한다(파이썬 round 는 .5 를 짝수로 보낸다)
        step = max(90, int(2400 / len(p2) + 0.5)) if af.get('rev') and len(p2) > 8 else 220
        after_end = land + start + step * len(p2) + 120
        t2 = (af.get('tile') or {}).get('type')
        gate = max(gate, after_end + (DG_KEY_DRAW if t2 == 'key' else 0) + DG_CARD_BEAT)
    return {'land': land, 'gate': gate}


def _dicegame_key_effect(text):
    """황금열쇠 글을 읽어 어떤 효과인지 알아낸다. 덱은 글자로 저장돼 있으므로
    (조종실이 그렇게 만들어져 있다) 글을 그대로 두고 여기서 뜻만 읽는다.
    ⚠️ 순서가 중요하다 — '기여도 1등과 바꾸기' 는 '기여도 N' 보다 먼저 '바꾸기' 로 잡아야 한다.
    모르는 글이면 None — 예전처럼 화면에 글만 뜨고 진행자가 처리한다."""
    import re
    t = str(text or '')
    for rx, kind in (
        (r'(\d+)\s*등\s*(?:이|과|와|이랑|랑)?\s*바꾸', 'swap'),
        (r'뒤\s*로\s*(\d+)\s*칸', 'back'),
        (r'앞\s*으로\s*(\d+)\s*칸', 'fwd'),
        (r'출발', 'start'),
        (r'파산', 'bankrupt'),
        (r'한\s*번\s*더', 'again'),
        (r'실드', 'shield'),
        (r'원하는', 'choose'),
        (r'꽝', 'nothing'),
        (r'기여도\s*(-?\d+)', 'contrib'),
    ):
        m = re.search(rx, t)
        if m:
            n = int(m.group(1)) if m.groups() else None
            return {'kind': kind, 'n': n}
    return None


def _dicegame_apply_key(state, g, piece, who, text, cur_pos, allow_move):
    """뽑힌 황금열쇠의 효과를 건다.
    돌려주는 값: {'note': 화면·조종실에 보일 한 줄, 'after': 이동이면 두 번째 이동 신호, 'again': 한 번 더}
    ⚠️ 말은 여기서 옮기지 않는다 — 부르는 쪽이 착지 처리를 끝낸 뒤 'after' 를 적용한다.
       (착지 처리가 뒤에서 piece['pos'] 를 덮어쓰므로 여기서 옮기면 되돌아간다)
    ⚠️ allow_move=False 는 끌려온 자리에서 뽑은 경우 — 다시 옮기면 끝없이 튕길 수 있다."""
    out = {'note': '', 'after': None, 'again': False}
    eff = _dicegame_key_effect(text)
    if not eff:
        return out
    k, n = eff['kind'], eff['n']
    # ⚠️ 바꾸기·파산·점수는 전부 **주사위 전용 판** 안에서 돈다. 엑셀판(진짜 기여도)은
    #    안 건드린다 — 사장님: "전용 기여도판안에서 해당하는 미션임".

    if k == 'contrib' and n:
        got = _dicegame_add_pts(state, g, who, n, '황금열쇠: ' + str(text)) if who else None
        out['note'] = ('%s %+d점' % (got, n)) if got else '누구 차례인지 몰라 점수는 손으로'
    elif k == 'bankrupt':
        t = _dicegame_row(g, who) if who else None
        if t is None:
            out['note'] = '판에서 못 찾아 파산은 손으로'
        else:
            before = _as_int(t.get('pts'), 0) or 0
            t['pts'] = 0
            _dicegame_log(state, t['name'], -before, '황금열쇠: 파산')
            out['note'] = '%s %d점 → 0' % (t['name'], before)
    elif k == 'swap' and n:
        me = _dicegame_row(g, who) if who else None
        ranked = _dicegame_ranked(g)
        tgt = ranked[n - 1] if 0 < n <= len(ranked) else None
        if me is None or tgt is None:
            out['note'] = '%d등을 못 찾아 바꾸기는 손으로' % n
        elif tgt is me:
            out['note'] = '본인이 %d등이라 바꿀 상대가 없음' % n
        else:
            a = _as_int(me.get('pts'), 0) or 0
            b = _as_int(tgt.get('pts'), 0) or 0
            me['pts'], tgt['pts'] = b, a
            _dicegame_log(state, me['name'], b - a, '황금열쇠: %d등과 바꾸기' % n)
            _dicegame_log(state, tgt['name'], a - b, '황금열쇠: %d등과 바꾸기(상대)' % n)
            out['note'] = '%s %d ↔ %s %d' % (me['name'], a, tgt['name'], b)
    elif k == 'again':
        out['again'] = True
        out['note'] = '한 번 더 — 차례가 넘어가지 않는다'
    elif k == 'shield':
        piece['shield'] = True
        out['note'] = '실드 획득 — 다음 벌칙 한 번을 막는다'
    elif k == 'choose':
        # 조종실이 이 말을 손으로 옮기면 그 칸이 제 일을 한다(/api/dicegame/move).
        # 표시가 없으면 '기여도 10' 칸을 골라 가도 아무것도 못 받는다 — 열쇠가 헛것이 된다.
        piece['choose'] = True
        out['note'] = '원하는 칸으로 — 조종실에서 옮기면 그 칸 효과가 걸린다'
    elif k == 'nothing':
        out['note'] = '꽝'
    elif k in ('back', 'fwd', 'start'):
        if not allow_move:
            out['note'] = '끌려온 자리에서는 다시 옮기지 않는다 — 손으로'
        else:
            tiles = g.get('tiles') or []
            nt = len(tiles)
            if k == 'start':
                # 🏁 출발지로 — 블랙홀처럼 거꾸로 걸어 출발까지. 예전엔 경로가 비어 혼자 순간이동했다
                dest, kind = 0, 'goto'
                path = [(cur_pos - i) % nt for i in range(1, cur_pos + 1)]
            elif k == 'back':
                dest = (cur_pos - n) % nt
                path = [(cur_pos - i) % nt for i in range(1, n + 1)]
                kind = 'move'
            else:
                dest = (cur_pos + n) % nt
                path = [(cur_pos + i) % nt for i in range(1, n + 1)]
                kind = 'move'
            t2 = tiles[dest] if isinstance(tiles[dest], dict) else {'id': dest, 'type': 'blank'}
            after = {'kind': kind, 'from': cur_pos, 'to': dest, 'path': path, 'label': str(text),
                     # 뒤로 · 출발지로는 벌칙처럼 거꾸로 밟는다(길면 빠르게) — 블랙홀과 같은 표시
                     'rev': k in ('back', 'start'),
                     'tile': {kk: t2.get(kk) for kk in ('id', 'type', 'label', 'points')}}
            # 도착한 칸이 점수 칸이면 그 점수도 준다. 열쇠·이동 칸은 다시 걸지 않는다(끝없는 연쇄 방지).
            if t2.get('type') == 'score' and t2.get('points') and who:
                p2 = _as_int(t2.get('points'), 0) or 0
                got = _dicegame_add_pts(state, g, who, p2, (t2.get('label') or '점수 칸') + ' (열쇠로 이동)')
                if got:
                    after['scored'] = {'name': got, 'points': p2}
            out['after'] = after
            out['note'] = '%d번으로' % dest
    return out


def _dicegame_sync_pieces(state, g):
    """말 목록을 지금 쓰는 점수판 명단에 맞춘다.

    이름을 코드에 박아두면 방송마다 고쳐야 한다 — 엑셀판에 있는 사람이 곧 말이다.
    ⚠️ 번외 게임 중에는 명단이 extra_bjs 로 바뀐다. 기여도가 그쪽으로 들어가므로
       말도 같이 따라가야 한다(_find_score_target 과 같은 규칙을 쓴다).
    ⚠️ 명단이 비면 있던 말을 그대로 둔다 — 명단을 잠깐 비웠다고 판 위의 말이
       사라지면 방송 중에 사고로 보인다.
    """
    src = 'extra_bjs' if state.get('extra_game_active') else 'bjs'
    names = []
    for b in (state.get(src) or []):
        if isinstance(b, dict):
            nm = str(b.get('name') or '').strip()
            if nm and nm not in names:
                names.append(nm)
    if not names:
        # 명단이 비어도 말은 하나 있어야 한다. 없으면 굴리기·옮기기가 통째로 막혀
        # 판을 미리 깔아두는 것조차 못 한다(명단은 방송 직전에 채우기도 한다).
        if not g.get('pieces'):
            g['pieces'] = [{'name': '말', 'pos': 0, 'laps': 0}]
        return
    old = {p['name']: p for p in g.get('pieces') or []}
    _old_ps = g.get('pieces') or []
    parked = g.get('parked') if isinstance(g.get('parked'), dict) else {}
    # ✏️ 개명이면 옛 이름의 말(자리 · 바퀴 · 실드 · 선택권)과 전용 판 점수를 새 이름이 물려받는다.
    #    ⚠️ 예전엔 개명도 '빠짐 + 새로 들어옴' 으로 보고 옛 이름을 보관함(parked)에 맡겼다.
    #       그런데 [엑셀판으로 옮기기] · 방송 종료 확인은 판(board)만 보고, 방송을 끝내면
    #       보관함이 비워져서 **이름을 고친 사람의 주사위 점수가 소리 없이 사라졌다.**
    #    엑셀판(server.py /api/data)과 같은 규칙으로만 개명이라 본다 — 확신할 수 없으면
    #    예전처럼 맡겨 둔다(잘못 물려주면 그건 남의 점수를 주는 것이다).
    _ren = _dicegame_rename(g, src, names, _old_ps, parked)
    if _ren:
        _gone, _new = _ren
        old[_new] = dict(old.get(_gone) or {}, name=_new)
        for _r in (g.get('board') or []):         # 점수판 줄도 이름만 바꿔 _dicegame_sync_board 가 이어받게
            if isinstance(_r, dict) and str(_r.get('name') or '').strip() == _gone:
                _r['name'] = _new
        _o = old[_new]
        print("  ✏️ [주사위게임] 이름 변경 %s → %s (%s번 칸 · 점수 그대로)"
              % (_gone, _new, _o.get('pos', 0)), flush=True)
    _swap = (lambda nm: _ren[1] if nm == _ren[0] else nm) if _ren else (lambda nm: nm)
    # 이름이 남아 있으면 자리도 그대로 — 명단을 고쳤다고 판이 초기화되면 안 된다
    # ⚠️ 순서는 **있던 말 순서를 지킨다**(새 이름만 뒤에 붙인다). 판은 기여도순으로 계속
    #    다시 서는데, 차례(turn)는 이 목록의 자리 번호다. 목록이 판을 따라 다시 서면
    #    점수를 받아 1등으로 뛴 사람이 곧바로 또 굴리고(자리 0번이 그 사람이 된다)
    #    누군가는 한 차례를 건너뛴다 — 남의 차례에 남의 말이 가고 기여도도 그리로 간다.
    # ⚠️ 개명한 말은 **제자리**에 둔다(뒤로 붙이면 차례 순서가 바뀐다).
    kept = [_swap(p['name']) for p in _old_ps if _swap(p.get('name')) in names]
    order = kept + [nm for nm in names if nm not in kept]
    # 차례는 자리 번호라서, 차례보다 앞에 있던 사람이 명단에서 빠지면 번호가 한 칸
    # 당겨져 다음 사람이 건너뛰어진다. 차례였던 이름을 기억해 새 목록에서 다시 찾는다.
    # 그 사람이 빠졌으면 그 다음 남은 사람.
    _ti = max(0, min(len(_old_ps) - 1, _as_int(g.get('turn'), 0) or 0)) if _old_ps else 0
    _next_name = None
    for _p in _old_ps[_ti:] + _old_ps[:_ti]:
        if _swap(_p.get('name')) in order:
            _next_name = _swap(_p['name'])
            break
    g['turn'] = order.index(_next_name) if _next_name in order else 0
    # 🅿️ 명단에서 빠진 이름의 기록은 버리지 않고 맡아 둔다(자리 · 바퀴 · 실드 · 선택권).
    #    같은 이름이 돌아오면 그대로 되살린다 — 오타를 고쳤다 되돌리거나 번외 게임으로 명단이
    #    잠깐 바뀌어도 판이 안 날아간다. 예전엔 곧바로 버려서 '0번 칸 · 0점' 으로 돌아왔다.
    #    점수(board)는 _dicegame_sync_board 가 같은 자리에 맡기고, 되살린 뒤 비운다.
    for _p in _old_ps:
        _nm = _p.get('name')
        if _nm and _swap(_nm) not in order:      # 개명한 이름은 물려줬으니 맡기지 않는다
            parked.setdefault(_nm, {}).update({'pos': _p.get('pos', 0), 'laps': _p.get('laps', 0),
                                               'shield': bool(_p.get('shield')),
                                               'choose': bool(_p.get('choose'))})
    g['parked'] = parked

    def _was(nm):
        return old.get(nm) or parked.get(nm) or {}
    g['pieces'] = [{'name': nm,
                    'pos': _was(nm).get('pos', 0),
                    'laps': _was(nm).get('laps', 0),
                    'shield': bool(_was(nm).get('shield')),
                    # '원하는 곳으로' 를 뽑아 손 이동을 기다리는 중인가
                    'choose': bool(_was(nm).get('choose'))} for nm in order]
    # 📸 이번 명단(순서 그대로)을 적어 둔다 — 다음 번에 '같은 자리의 이름만 바뀌었나'(개명)를 본다.
    #    ⚠️ 말 목록 순서로는 못 본다. 말은 있던 순서를 지키고 새 이름을 뒤에 붙이므로 명단 순서와 다를 수 있다.
    g['roster'] = {'src': src, 'names': list(names)}


def _dicegame_rename(g, src, names, old_ps, parked):
    """명단 변경이 '한 사람 개명' 인가. 맞으면 (옛 이름, 새 이름), 아니면 None.

    엑셀판(server.py /api/data 의 개명 처리)과 같은 규칙이다:
      사라진 이름 하나 · 새 이름 하나 · 사람 수 그대로 · **명단에서 같은 자리**.
    ⚠️ 한 번에 여럿을 고치거나 추가·삭제가 섞이면 확신할 수 없으니 개명으로 안 본다
       (그땐 예전처럼 보관함에 맡긴다 — 잃지는 않는다).
    ⚠️ 번외 게임으로 명단이 bjs ↔ extra_bjs 로 바뀐 것은 개명이 아니다.
    ⚠️ 새 이름이 보관함에 있으면 '맡아 둔 사람이 돌아온 것' 이다 — 되살리기가 먼저다.
    """
    old_names = [p.get('name') for p in old_ps if p.get('name')]
    if len(old_names) != len(names):
        return None
    gone = [nm for nm in old_names if nm not in names]
    new = [nm for nm in names if nm not in old_names]
    if len(gone) != 1 or len(new) != 1:
        return None
    gone, new = gone[0], new[0]
    if new in parked:
        return None
    prev = g.get('roster') if isinstance(g.get('roster'), dict) else None
    pn = prev.get('names') if prev else None
    if isinstance(pn, list) and set(pn) == set(old_names):
        if prev.get('src') != src:
            return None
        return (gone, new) if pn.index(gone) == names.index(new) else None
    # 명단 사진이 없다(고치기 전 저장본) — 말 순서로 대신 본다.
    # ⚠️ 명단이 비었을 때 까는 자리표 말('말' 하나)은 사람이 아니다. 그 기록을 물려주지 않는다.
    if old_names == ['말']:
        return None
    return (gone, new) if old_names.index(gone) == names.index(new) else None


def _dicegame_state(state):
    """항상 온전한 모양의 게임 상태를 돌려준다(예전 저장본에 없던 키 보정)."""
    g = state.get('dicegame')
    if not isinstance(g, dict):
        g = copy.deepcopy(DEFAULT_STATE['dicegame'])
        state['dicegame'] = g
    for k, v in DEFAULT_STATE['dicegame'].items():
        g.setdefault(k, copy.deepcopy(v))
    for k in ('tiles', 'keys'):
        if not isinstance(g.get(k), list):
            g[k] = []
    # 🧩 말 목록 보정 — 옛 저장본에는 말이 아예 없다. 그때는 기본 넷을 깔고,
    #    예전 말 위치(pos)를 첫 말에게 물려준다(판 위의 말이 갑자기 출발점으로
    #    돌아가면 방송 중에 사고로 보인다).
    if not isinstance(g.get('pieces'), list):
        g['pieces'] = []
    _fixed = []
    for _p in g['pieces']:
        if not isinstance(_p, dict):
            continue
        _nm = str(_p.get('name') or '').strip()
        if not _nm:
            continue
        _fixed.append({'name': _nm,
                       'pos': max(0, _as_int(_p.get('pos'), 0) or 0),
                       'laps': max(0, _as_int(_p.get('laps'), 0) or 0),
                       'shield': bool(_p.get('shield')),
                       'choose': bool(_p.get('choose'))})
    g['pieces'] = _fixed
    _dicegame_sync_pieces(state, g)
    if not isinstance(g.get('board'), list):
        g['board'] = []
    _dicegame_sync_board(g)
    # 🏁 한 바퀴 보상을 5 → 10 으로 **한 번만** 올린다.
    #    조종실에는 이 값을 고치는 칸이 없고 setup 은 쓰던 값을 그대로 이어받는다 —
    #    여기서 안 올리면 이미 깔려 있는 판은 영영 5점으로 남는다.
    # ⚠️ 표시(lap_v2)를 **DEFAULT_STATE 에 넣지 말 것.** 위 setdefault 반복이 먼저
    #    돌아서 옛 저장본까지 '이미 올렸다' 로 찍어 버린다 — 그러면 영영 안 올라간다.
    # ⚠️ 한 번 올린 뒤 사장님이 일부러 다른 값으로 바꾸면 그 값을 그대로 둔다.
    if not g.get('lap_v2'):
        g['lap_v2'] = True
        if _as_int(g.get('lap_contrib'), 0) == 5:      # 옛 기본값 그대로인 판만
            g['lap_contrib'] = 10
    g['turn'] = max(0, min(max(0, len(g['pieces']) - 1), _as_int(g.get('turn'), 0) or 0))
    return g


def _dicegame_pick(g, want):
    """어느 말을 움직일지 고른다. 이름·번호 둘 다 받는다.

    아무것도 안 주면 '다음 차례'(turn) 말이 움직인다. 조종실이 말을 안 고르고
    굴렸을 때 엉뚱한 말이 가는 것을 막으려고, 고른 결과를 항상 돌려준다.
    """
    ps = g['pieces']
    if not ps:
        return None          # 명단이 비었다 — 부르는 쪽이 알아서 알린다
    want = '' if want is None else str(want).strip()
    if want:
        for i, p in enumerate(ps):
            if p['name'] == want:
                return i
        _i = _as_int(want)
        if _i is not None and 0 <= _i < len(ps):
            return _i
        return None          # 이름을 줬는데 없다 — 부르는 쪽이 알아야 한다
    return max(0, min(len(ps) - 1, _as_int(g.get('turn'), 0) or 0))


def _dicegame_save(state, g):
    state['dicegame'] = g
    save_data(state)
    broadcast_event('update', state)


# ══════════════════════════════════════════════════════════════
# 🎲 주사위게임 **전용** 점수판
#   사장님(2026-09-13): "평소에 쓰는 엑셀판 말고 주사위게임 전용 기여도판이 필요함"
#   · 전원 0점에서 시작 · 마이너스도 된다
#   · 엑셀판(진짜 기여도)은 절대 안 건드린다 — 조종실에서 [옮기기] 를 눌러야 넘어간다
#   ⚠️ 예전에는 주사위 칸·열쇠가 곧바로 엑셀판 기여도를 올렸다. 그래서 '기여도 1등과
#      바꾸기' 가 진짜 후원 순위를 뒤바꿔 버렸다 — 이제 전부 이 판 안에서만 돈다.
# ══════════════════════════════════════════════════════════════

DG_PARKED_MAX = 40   # 🅿️ 맡아 두는 이름 수 상한 — 넘으면 오래된 것부터 버린다


def _dicegame_sync_board(g):
    """전용 점수판을 말 명단에 맞춘다. 있던 점수는 이름으로 지킨다.
    빠진 이름의 점수는 보관함(parked)에 맡기고, 돌아오면 되살린다."""
    old = {}
    for r in (g.get('board') or []):
        if isinstance(r, dict) and str(r.get('name') or '').strip():
            old[str(r['name']).strip()] = _as_int(r.get('pts'), 0) or 0
    names = [p['name'] for p in (g.get('pieces') or [])]
    parked = g.get('parked') if isinstance(g.get('parked'), dict) else {}
    for nm, pts in old.items():
        if nm not in names:
            parked.setdefault(nm, {})['pts'] = pts
    g['board'] = [{'name': nm, 'pts': old[nm] if nm in old else (_as_int((parked.get(nm) or {}).get('pts'), 0) or 0)}
                  for nm in names]
    for nm in names:              # 돌아온 이름은 판에 올렸으니 보관함에서 뺀다
        parked.pop(nm, None)
    for nm in list(parked):       # 맡아 둘 게 없는 이름(출발 칸 · 0점)은 버린다
        v = parked[nm] if isinstance(parked[nm], dict) else {}
        if not (v.get('pos') or v.get('laps') or v.get('shield') or v.get('choose') or v.get('pts')):
            parked.pop(nm)
    while len(parked) > DG_PARKED_MAX:
        parked.pop(next(iter(parked)))
    g['parked'] = parked


def _dicegame_row(g, name):
    want = str(name or '').strip()
    for r in (g.get('board') or []):
        if str(r.get('name') or '').strip() == want:
            return r
    return None


def _dicegame_log(state, name, val, why):
    """⚠️ kind 는 'dice' 다 — 'contrib' 로 남기면 조종실 장부에서 진짜 기여도와 섞인다."""
    logs = state.get('logs')
    if not isinstance(logs, list):
        logs = []
        state['logs'] = logs
    logs.insert(0, {'time': now_hms(), 'name': name, 'val': int(val),
                    'kind': 'dice', 'why': why})
    del logs[LOG_MAX:]


def _dicegame_add_pts(state, g, player, pts, why):
    """전용 판 점수를 더한다(마이너스도 된다). 그 이름이 판에 없으면 None."""
    r = _dicegame_row(g, player)
    if r is None:
        return None
    r['pts'] = (_as_int(r.get('pts'), 0) or 0) + int(pts)
    _dicegame_log(state, r['name'], int(pts), why)
    return r['name']


def _dicegame_ranked(g):
    """점수 높은 차례. 같으면 이름 차례 — 굴릴 때마다 순위가 흔들리면 안 된다."""
    rows = [r for r in (g.get('board') or []) if isinstance(r, dict)]
    return sorted(rows, key=lambda r: (-(_as_int(r.get('pts'), 0) or 0),
                                       str(r.get('name') or '')))


def _dicegame_steal(state, g, taker, per):
    """착지한 사람이 다른 말들에게서 per 점씩 뺏는다. 판의 총점은 그대로다."""
    me = _dicegame_row(g, taker)
    if me is None or not per:
        return None
    victims = [r for r in (g.get('board') or []) if r is not me]
    if not victims:
        return None
    for v in victims:
        v['pts'] = (_as_int(v.get('pts'), 0) or 0) - per
        _dicegame_log(state, v['name'], -per, '%s 에게 빼앗김' % me['name'])
    gain = per * len(victims)
    me['pts'] = (_as_int(me.get('pts'), 0) or 0) + gain
    _dicegame_log(state, me['name'], gain, '%d명에게서 %d점씩 빼앗음' % (len(victims), per))
    return {'taker': me['name'], 'per': per, 'gain': gain,
            'from': [v['name'] for v in victims]}


def _contrib_alert(state, title, contrib, why):
    """기여도만 주는 알림을 대기함에 남긴다 — 조종실이 누구에게 줄지 고른다."""
    # ⚠️ 주사위(차례를 모를 때)와 슬롯(굴린 사람이 아예 없다)이 같이 쓴다.
    #    이름에 dicegame 이 붙어 있었는데, 슬롯도 쓰게 되면서 거짓말이 됐다.
    state.setdefault('pending_donations', []).append({
        'id': f"dg_{uuid.uuid4().hex[:12]}",
        'name': title,
        'orig_name': '주사위게임',
        'amount': 0,
        'message': why,
        'time': now_hms(),
        'kind': 'contrib',
        'contrib': contrib,
    })


@app.route('/api/dicegame/setup', methods=['POST'])
def api_dicegame_setup():
    """판을 깐다. 같은 번호 칸의 내용은 남긴다 — 크기만 바꿔도 적어둔 게 안 날아가게."""
    body = request.get_json(silent=True) or {}
    # ⚠️ '안 보낸 것'(기본값으로 간다)과 '보냈는데 숫자가 아닌 것'(400)을 구분한다.
    #    _as_int 에 기본값을 주면 쓰레기도 조용히 기본값이 되어, 잘못 보낸 쪽이
    #    자기 실수를 영영 모른다.
    def _opt(key, default):
        return default if body.get(key) is None else _as_int(body.get(key))
    cols = _opt('cols', 7)
    rows = _opt('rows', 5)
    dice = _opt('dice', 1)
    # 💰 한 판 값 · 🏁 한 바퀴 보너스. 안 보내면 지금 쓰던 값을 그대로 이어받는다
    #    — 크기만 바꿨다고 단가가 기본값으로 되돌아가면 그게 사고다.
    with file_lock:
        _cur = _dicegame_state(load_data())
        _cur_price = _as_int(_cur.get('roll_price'), 20000) or 20000
        _cur_lapc = _as_int(_cur.get('lap_contrib'), 10)
        if _cur_lapc is None:
            _cur_lapc = 10
    roll_price = _opt('roll_price', _cur_price)
    lap_contrib = _opt('lap_contrib', _cur_lapc)
    if cols is None or rows is None or dice is None or roll_price is None or lap_contrib is None:
        return jsonify({'status': 'error', 'message': '숫자가 아닙니다'}), 400
    cols = max(4, min(10, cols))
    rows = max(3, min(8, rows))
    dice = max(1, min(2, dice))
    roll_price = max(0, min(10000000, roll_price))
    lap_contrib = max(0, min(1000, lap_contrib))
    n = 2 * (cols + rows) - 4
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        old = {t.get('id'): t for t in (g.get('tiles') or []) if isinstance(t, dict)}
        tiles = []
        for i in range(n):
            prev = old.get(i)
            if i == 0:
                tiles.append({'id': 0, 'type': 'start', 'label': '출발'})
            elif prev and prev.get('type') in DICE_TILE_TYPES and prev.get('type') != 'start':
                tiles.append(prev)
            else:
                tiles.append({'id': i, 'type': 'blank', 'label': ''})
        g.update({'cols': cols, 'rows': rows, 'dice': dice, 'tiles': tiles,
                  'roll_price': roll_price, 'lap_contrib': lap_contrib,
                  'pos': 0, 'laps': 0,
                  # 새 판이면 말 넷 전부 출발점으로. 이름은 그대로 둔다.
                  'pieces': [{'name': _p['name'], 'pos': 0, 'laps': 0}
                             for _p in g['pieces']], 'turn': 0,
                  'action': {'type': 'PLACE', 'ts': int(time.time() * 1000)}})
        # 🅿️ 맡아 둔 이름도 새 판에선 출발부터(점수는 판 크기와 상관없으니 그대로)
        for _v in (g.get('parked') or {}).values():
            if isinstance(_v, dict):
                _v.update({'pos': 0, 'laps': 0, 'shield': False, 'choose': False})
        # 📺 판을 깔면 무대에 올린다. ⚠️ 예전엔 enabled 만 켜서 다른 게임판과 겹쳐 떴다
        _prev = showmod.ensure(state)['stage']
        showmod.set_stage(state, 'dicegame')
        _stage_log(_prev, 'dicegame')
        _dicegame_save(state, g)
    print(f"🎲 [주사위게임] 판 깔림 — {cols}×{rows} 테두리 {n}칸, 주사위 {dice}개, "
          f"한 판 {roll_price:,}원, 한 바퀴 기여도 {lap_contrib}")
    return jsonify({'status': 'success', 'tiles': n,
                    'roll_price': roll_price, 'lap_contrib': lap_contrib})


@app.route('/api/dicegame/tile', methods=['POST'])
def api_dicegame_tile():
    """칸 하나를 고친다. body: {id, type, label?, points?, sig_id?}"""
    body = request.get_json(silent=True) or {}
    tid = _as_int(body.get('id'))
    ttype = str(body.get('type') or '').strip()
    if tid is None:
        return jsonify({'status': 'error', 'message': '칸 번호가 없습니다'}), 400
    if ttype not in DICE_TILE_TYPES:
        return jsonify({'status': 'error', 'message': f'모르는 칸 종류: {ttype}'}), 400
    if tid == 0 or ttype == 'start':
        return jsonify({'status': 'error', 'message': '출발 칸은 바꿀 수 없습니다'}), 400
    label = str(body.get('label') or '').strip()[:60]
    points = _as_int(body.get('points'), 0) or 0
    points = max(-1000, min(1000, points))
    # ⚠️ 시그니처 정보는 잠금 밖(여기)에서 미리 받아 칸에 붙여 둔다.
    #    굴리는 순간 받으러 가면 잠금 안에서 네트워크를 기다린다.
    sig = None
    if ttype == 'sig':
        sig_id = _as_int(body.get('sig_id'))
        if sig_id is None:
            return jsonify({'status': 'error', 'message': '시그니처를 골라주세요'}), 400
        try:
            sig = server.supabase_get_signature(sig_id)
        except Exception as e:
            print(f'[주사위게임] 시그니처 조회 실패: {e}')
            sig = None
        if not sig:
            return jsonify({'status': 'error', 'message': '그 시그니처를 찾지 못했습니다'}), 404
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        tiles = g.get('tiles') or []
        if not (0 <= tid < len(tiles)):
            return jsonify({'status': 'error', 'message': '없는 칸입니다'}), 400
        tile = {'id': tid, 'type': ttype, 'label': label}
        # 숫자를 쓰는 칸은 넷이다. 뜻은 종류마다 다르다 —
        #   score 점수 · move 몇 칸(음수면 뒤로) · goto 칸 번호 · giveall/steal 점수
        # ⚠️ 예전에는 score 만 저장했다. 그래서 싱크홀(-5)·전원지급(5)이 0 으로
        #    저장돼 밟아도 아무 일이 없었다(블랙홀만 목표가 0 이라 우연히 맞았다).
        if ttype in ('score', 'move', 'goto', 'giveall', 'steal'):
            tile['points'] = points
        if ttype == 'sig' and sig:
            tile['sig'] = sig
            if not label:
                tile['label'] = str(sig.get('title') or '')[:60]
        tiles[tid] = tile
        _dicegame_save(state, g)
    return jsonify({'status': 'success', 'tile': tile})


@app.route('/api/dicegame/keys', methods=['POST'])
def api_dicegame_keys():
    """황금열쇠 덱을 통째로 저장한다. body: {keys: [글, ...]}"""
    body = request.get_json(silent=True) or {}
    raw = body.get('keys')
    if not isinstance(raw, list):
        return jsonify({'status': 'error', 'message': '목록이 아닙니다'}), 400
    keys = [str(k).strip()[:200] for k in raw if str(k or '').strip()][:40]
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        g['keys'] = keys
        _dicegame_save(state, g)
    return jsonify({'status': 'success', 'count': len(keys)})


def _dicegame_dest_effects(state, g, piece, who, dest, tag):
    """끌려가거나 손으로 옮겨진 자리의 칸이 제 일을 한다 — 점수·전원 지급·황금열쇠.
    돌려주는 값: {'parts': action 에 합칠 조각(scored/note/giveall/key/key_effect),
                  'again': 한 번 더, 'tile': 그 칸 요약}
    ⚠️ 다시 옮기는 칸(move·goto)에는 걸지 않는다 — 싱크홀에서 싱크홀로 끝없이 튕길 수 있고,
       방송 중에 그게 터지면 손쓸 수가 없다.
    ⚠️ 시그니처 칸도 뺐다. 재생 큐가 얽혀 있어 한 번에 두 곡이 걸릴 수 있다. 그 자리에 서면
       진행자가 직접 틀어준다.
    """
    tiles = g.get('tiles') or []
    t2 = tiles[dest] if 0 <= dest < len(tiles) and isinstance(tiles[dest], dict) else {'id': dest, 'type': 'blank'}
    parts, again = {}, False
    d2 = t2.get('type')
    if d2 == 'score' and t2.get('points'):
        p2 = _as_int(t2.get('points'), 0) or 0
        if who:
            got = _dicegame_add_pts(state, g, who, p2, (t2.get('label') or '점수 칸') + tag)
            if got:
                parts['scored'] = {'name': got, 'points': p2}
                print(f"🎯 [주사위게임] {dest}번{tag} → {got} 기여도 {p2}", flush=True)
            else:
                parts['note'] = "'%s' 을(를) 명단에서 못 찾아 기여도는 안 넣었습니다" % who
        else:
            parts['note'] = '누구 차례인지 몰라 기여도는 손으로 주세요'
    elif d2 == 'giveall':
        p2 = _as_int(t2.get('points'), 0) or 0
        names = []
        if p2:
            why2 = (t2.get('label') or '전원 지급') + ' 칸' + tag
            for pc in g['pieces']:
                try:
                    if _dicegame_add_pts(state, g, pc['name'], p2, why2):
                        names.append(pc['name'])
                except Exception as e:
                    print(f'⚠️ [주사위게임] 전원 지급 실패{tag} — 계속합니다: {e}')
        parts['giveall'] = {'points': p2, 'names': names}
    elif d2 == 'steal':
        p2 = _as_int(t2.get('points'), 0) or 0
        st = _dicegame_steal(state, g, who or (piece or {}).get('name'), p2)
        if st:
            parts['steal'] = st
    elif d2 == 'key':
        keys2 = [str(x) for x in (g.get('keys') or []) if str(x).strip()]
        parts['key'] = random.choice(keys2) if keys2 else '(황금열쇠 덱이 비어 있습니다)'
        if keys2:
            ke2 = _dicegame_apply_key(state, g, piece, who, parts['key'], dest, allow_move=False)
            if ke2['note']:
                parts['key_effect'] = ke2['note']
            again = bool(ke2['again'])
    return {'parts': parts, 'again': again,
            'tile': {k: t2.get(k) for k in ('id', 'type', 'label', 'points')}}


@app.route('/api/dicegame/roll', methods=['POST'])
def api_dicegame_roll():
    """주사위를 굴린다.

       body: {player?: 이 굴림이 누구 것인지(점수 칸 자동 반영용),
              value?:  현실에서 굴린 눈(1~6). 넣으면 그 눈으로 간다.}

       🎲 사장님이 주사위를 현실에서 굴리기로 정했다(화면 주사위는 타격감이 없다).
          value 를 넣으면 그 눈을 쓰고, 안 넣으면 예전처럼 서버가 무작위로 정한다
          — 주사위를 놓고 왔을 때를 위해 무작위도 남긴다.

       ⚠️ 눈·경로·황금열쇠까지 전부 여기서 정해 action 에 싣는다.
          화면마다 따로 정하면 오버레이 두 개가 서로 다른 결과를 보여준다.
    """
    body = request.get_json(silent=True) or {}
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        player = str(body.get('player') or '').strip()
        contrib_player = player
        # 🧩 어느 말이 가는가.
        #    ① piece 를 줬으면 그 말  ② 안 줬는데 사람 이름이 말 이름이면 그 말
        #    ③ 둘 다 아니면 '다음 차례' 말
        #    ⚠️ ②가 있어야 옛 호출(piece 없이 player 만)이 그대로 돈다. 사람 이름이
        #       말 이름이 아닐 수도 있다(시청자·게스트) — 그때는 말만 차례대로 가고
        #       기여도는 그 사람에게 간다. 예전과 똑같은 결과다.
        _piece_want = body.get('piece')
        _idx = None
        if _piece_want not in (None, ''):
            _idx = _dicegame_pick(g, _piece_want)
            if _idx is None:
                _names = ' · '.join(x['name'] for x in g['pieces'])
                return jsonify({'status': 'error',
                                "message": "'%s' 말이 없습니다. 있는 말: %s"
                                           % (_piece_want, _names)}), 400
        #    ⚠️ 여기서 contrib_player(= 기억해 둔 사람)를 쓰면 안 된다. 한 번
        #       말 이름이 기억되는 순간 그 뒤로는 손으로 옮겨 놔도 계속 그 말만
        #       움직인다(실제로 그렇게 만들었다가 잡았다). 기억은 '점수 받을
        #       사람' 에만 쓰고, 말 고르기에는 이번 요청에 온 값만 쓴다.
        if _idx is None and player:
            _idx = _dicegame_pick(g, player)
        if _idx is None:
            _idx = _dicegame_pick(g, None)
        if _idx is None:
            # 말은 점수판 명단에서 나온다 — 명단이 비면 굴릴 말이 없다
            return jsonify({'status': 'error',
                            'message': '점수판에 사람이 없습니다. 엑셀판에 선수를 넣어주세요'}), 400
        piece = g['pieces'][_idx]
        tiles = g.get('tiles') or []
        if not tiles:
            return jsonify({'status': 'error', 'message': '먼저 판을 깔아주세요'}), 400
        if not g.get('enabled'):
            # 판은 있는데 무대에 없다 — '판을 깔아 주세요' 는 틀린 안내였다(깔려 있다)
            _st = (state.get('show') or {}).get('stage')
            if _st and _st != 'dicegame':
                _lb = showmod.STAGE_LABEL.get(_st, _st)
                _msg = "지금 무대에 '%s' 판이 올라가 있어요 — 주사위판을 먼저 올려 주세요" % _lb
            else:
                _msg = '주사위판이 방송에 안 떠 있어요 — 먼저 띄워 주세요'
            return jsonify({'status': 'error', 'message': _msg}), 400
        # 연타 방지 — 앞 연출이 끝나기 전의 굴림은 겹쳐 보인다.
        #   ⚠️ 연출 길이는 _dicegame_plan 한 곳에서 잰다(방송판 dgRollPlan 과 같은 식).
        #      예전 식은 걸어가는 시간까지만 세서 블랙홀 · 열쇠 연출 중간에 다음 굴림이 끼어들었다.
        prev = g.get('action') or {}
        if prev.get('type') == 'ROLL':
            hold = _dicegame_plan(prev)['gate'] + 300
            left = hold - (now_ms - (prev.get('ts') or 0))
            if left > 0:
                return jsonify({'status': 'error', 'wait_ms': left,
                                'message': '앞 연출이 아직 안 끝났어요 — %.1f초 뒤에 다시 눌러 주세요' % (left / 1000.0)}), 429
        n = len(tiles)
        # 🎲 현실에서 굴린 눈이 왔으면 그것을 쓴다.
        #    ⚠️ 값 검사를 여기서 확실히 한다 — 7 이나 글자가 들어오면 말이 엉뚱한 데로 간다.
        _raw_v = body.get('value')
        manual = _raw_v is not None
        if manual:
            _v = _as_int(_raw_v)
            if _v is None or not (1 <= _v <= 6):
                return jsonify({'status': 'error',
                                'message': '주사위 눈은 1~6 입니다'}), 400
            dice = [_v]
        else:
            dice = [random.randint(1, 6) for _ in range(max(1, min(2, _as_int(g.get('dice'), 1) or 1)))]
        # ── ⚠️ 여기까지는 거절될 수 있는 검사뿐이다. 상태는 아래부터 바꾼다 ──
        #    예전엔 검사 앞에서 선택권을 지웠다 — 연출 중에 한 번 더 눌러 429 로 거절돼도
        #    '원하는 곳으로' 가 사라져, 원하는 칸으로 옮겨도 점수가 안 들어갔다.
        # 🙋 기여도 받을 사람 — 골랐으면 그 사람, 아니면 **움직인 말의 주인**.
        #    ⚠️ 예전에는 '마지막으로 굴린 사람' 을 기억해 줬다 — 말이 하나뿐일 때 규칙이다.
        #       말이 선수마다 하나씩 생긴 뒤로는 그 기억이 거짓이 된다: 폰은 말만 골라
        #       보내므로(piece) 첫 사람이 한 번 굴리면 그 뒤 모두의 기여도가 첫 사람에게
        #       갔다(사장님: '기여도 올라가는 게 안 보이네' — 다른 줄이 오르고 있었다).
        if player:
            g['last_player'] = player
        # '원하는 곳으로' 를 뽑고 옮기지 않은 채 다시 굴렸으면 그 선택권은 사라진다
        piece.pop('choose', None)
        # 사람을 안 골랐으면 움직인 말의 주인이 받는다 (말 = 점수판 선수)
        if not contrib_player:
            contrib_player = piece['name']
            g['last_player'] = piece['name']
        steps = sum(dice)
        frm = piece['pos'] % n
        to = (frm + steps) % n
        # 🏁 **한 바퀴 돌 때마다** 준다 — 출발 칸을 지나치면 되고, 밟지 않아도 된다.
        #    ⚠️ 이 규칙은 두 번 뒤집혔다. 되돌리기 전에 이걸 읽을 것:
        #       ① 처음엔 지나가기만 해도 줬다 — (frm + steps) >= n
        #       ② 사장님: "1바퀴 될 때가 아니라 시작지점 오면 5점" → 정확히 밟을 때만
        #       ③ 사장님: "출발칸을 밟을 때 말고 한 바퀴 돌 때마다로" → ①로 되돌림
        #       지금은 ③ 이다. ②로 되돌리는 고침은 사장님 뜻이 아니다.
        #    ⚠️ 벌칙으로 끌려간 이동(블랙홀·싱크홀)은 여기를 안 탄다. 아래 두 번째
        #       이동에서 lap 을 다시 세지 않으므로, 블랙홀로 출발에 닿아도 한 바퀴가
        #       아니다 — 사장님: "블랙홀 그거는 한 바퀴 돌 때의 점수를 안 줘".
        lap = (frm + steps) >= n
        path = [(frm + i) % n for i in range(1, steps + 1)]
        tile = tiles[to] if isinstance(tiles[to], dict) else {'id': to, 'type': 'blank'}
        action = {'type': 'ROLL', 'ts': now_ms, 'dice': dice, 'from': frm, 'to': to,
                  # 🧩 넷 중 어느 말이 가는가. 없으면 화면이 아무 말이나 움직인다.
                  'piece': piece['name'], 'piece_idx': _idx,
                  # 현실에서 굴린 것이면 화면은 굴리는 연출을 건너뛰고 눈만 보여준다
                  'manual': manual,
                  'path': path, 'lap': bool(lap),
                  'tile': {k: tile.get(k) for k in ('id', 'type', 'label', 'points')}}
        if tile.get('type') == 'sig' and isinstance(tile.get('sig'), dict):
            action['tile']['image'] = tile['sig'].get('image_url')
        # 🔑 황금열쇠 — 뽑기도 서버가 한다. 화면마다 다른 카드가 나오면 안 된다.
        _ke_after, _key_again = None, False   # 열쇠가 만든 두 번째 이동 · 한 번 더
        if tile.get('type') == 'key':
            keys = g.get('keys') or []
            action['key'] = random.choice(keys) if keys else '(황금열쇠 덱이 비어 있습니다)'
            # 뽑힌 글을 읽어 효과를 건다. 이동은 착지 처리가 끝난 뒤에 적용한다(아래).
            if keys:
                _ke = _dicegame_apply_key(state, g, piece, contrib_player, action['key'], to, allow_move=True)
                if _ke['note']:
                    action['key_effect'] = _ke['note']
                _ke_after, _key_again = _ke['after'], _ke['again']
                print('[주사위게임] 황금열쇠 %r -> %s' % (action['key'], _ke['note'] or '효과 없음(글만)'), flush=True)
        # 💯 점수 칸 — 칸에는 '점수' 라고 적혀 있지만 올리는 것은 기여도뿐이다.
        #    사장님: "점수 칸은 점수라고만 써있지 기여도 5점만 올라가는거야"
        #    ⚠️ 예전에는 점수(그날 일당)도 같이 올렸다. 게임에서 5만원어치가 가짜로 붙었다.
        #    기여도라서 시그·한 바퀴와 같이 차례를 기억해 저절로 준다(contrib_player).
        # 실드권 — 음수 점수 칸을 한 번 막는다. 카드에는 '실드로 막았다' 만 남긴다.
        if tile.get('type') == 'score' and (_as_int(tile.get('points'), 0) or 0) < 0 and piece.get('shield'):
            piece['shield'] = False
            action['shield_used'] = True
            action['score_note'] = '실드로 막았다 — 기여도 차감 없음'
            action['tile']['points'] = 0
            tile = dict(tile)
            tile['points'] = 0   # 아래 점수 분기가 안 걸리게
        if tile.get('type') == 'score' and tile.get('points'):
            _pts = int(tile['points'])
            if contrib_player:
                applied_to = _dicegame_add_pts(state, g, contrib_player, _pts,
                                               '🎲 점수 칸 %+d' % _pts)
                if applied_to:
                    action['scored'] = {'name': applied_to, 'points': _pts}
                else:
                    action['score_note'] = f"'{contrib_player}' 을(를) 판에서 못 찾아 점수를 넣지 않았습니다"
            else:
                action['score_note'] = '누구 차례인지 몰라 점수는 손으로 주세요'
        # 🎵 시그니처 칸 — 기존 재생 경로 그대로(재생 전용이라 집계에는 안 센다)
        if tile.get('type') == 'sig' and isinstance(tile.get('sig'), dict):
            try:
                # ⏳ 말이 다 간 뒤에 나오게 한다. 곧바로 넣으면 reaction_mode 가 켜지면서
                #    body.reaction-mode 가 주사위판을 숨겨, 말이 가는 것을 볼 수가 없다.
                #    ⚠️ 큐에는 지금 넣는다 — 서버가 그 사이 재시작해도 시그니처를 안 잃는다.
                #    ⚠️ 시간은 _dicegame_plan 한 곳에서 잰다(방송판 dgRollPlan 과 같은 식):
                #       말이 닿고(land) "시그니처 재생!" 카드를 읽을 틈(DG_SIG_BEAT)까지.
                #    (방송판은 이 시각을 안 본다 — 제 시계로 같은 식을 잰다. 조종실 · 기록용)
                _anim_ms = _dicegame_plan(action)['gate']
                # 🎲 후원이 아니다 — 금액 0 · 팝업 없음 · '업' 배너 없음 · 클립 저장 없음.
                #    예전엔 '주사위게임' 님이 시그 값만큼 후원한 것처럼 떴고, 10만 원 이상이면
                #    '주사위게임업' 배너와 클립 자동 저장까지 돌았다. 누가 밟았는지만 제목으로 띄운다.
                _who = contrib_player or piece['name']
                enqueue_signature(state, tile['sig'], 0, _who, '🎲 주사위로 뽑은 시그',
                                  skip_popup=True, count_tally=False, play_after_ms=_anim_ms,
                                  extra={'source': 'dice', 'banner': '%s · 시그 칸 도착' % _who})
            except Exception as e:
                print(f'⚠️ [주사위게임] 시그니처 재생 실패 — 게임은 계속됩니다: {e}')
            # 🎯 기여도만 준다. 점수는 그날 일당이라 게임으로 오르면 안 된다.
            #    ⚠️ 시그니처 값에서 '한 판 값' 을 뺀다. 주사위 한 판은 2만원 후원으로
            #       사는데, 그 후원이 들어올 때 이미 2점이 올라갔다. 시그니처 값을
            #       통째로 또 주면 그 2점이 두 번 셈된다.
            #         10만원짜리 시그 = 10점, 한 판 2만원 = 2점 → 기여도 8점
            #    ⚠️ 한 판 값보다 싼 시그니처면 0 으로 둔다. 이미 받은 것이 더 크므로
            #       더 줄 것이 없다 — 빼앗지는 않는다.
            try:
                _sig_amt = int(tile['sig'].get('amount') or 0)
                _price = max(0, _as_int(g.get('roll_price'), 20000) or 0)
                _contrib = max(0, man_won(_sig_amt - _price))
                _why = '%s (%s원 − 한 판 %s원)' % (
                    str(tile['sig'].get('title') or '')[:40],
                    format(_sig_amt, ','), format(_price, ','))
                if _contrib <= 0:
                    print(f"🎯 [주사위게임] 시그니처 '{tile['sig'].get('title')}' 는 한 판 값"
                          f"({_price:,}원) 이하라 더 줄 기여도가 없습니다")
                elif contrib_player:
                    _to = _dicegame_add_pts(state, g, contrib_player, _contrib, _why)
                    if _to:
                        action['contrib'] = {'name': _to, 'points': _contrib, 'why': _why}
                        print(f"🎯 [주사위게임] {_to} 에게 {_contrib}점 (시그니처)")
                    else:
                        print(f"🎯 [주사위게임] 시그니처 {_contrib}점 — 받을 말이 판에 없습니다")
                else:
                    print(f"🎯 [주사위게임] 시그니처 {_contrib}점 — 누구 차례인지 몰라 손으로")
            except Exception as e:
                print(f'⚠️ [주사위게임] 기여도 실패 — 게임은 계속됩니다: {e}')

        # 🏁 출발 칸을 지나쳤다 — 한 바퀴 돈 사람에게 기여도를 준다.
        #    ⚠️ 시그니처와 같은 판에서 둘 다 일어날 수 있다(시그 칸을 밟으며 한 바퀴).
        #       그때는 둘 다 준다 — 각각 다른 이유로 받는 것이다.
        if lap:
            try:
                _lap_c = max(0, _as_int(g.get('lap_contrib'), 10) or 0)
                if _lap_c:
                    _why = '한 바퀴 돌았습니다 (%d번째)' % (piece['laps'] + 1)
                    if contrib_player:
                        _to = _dicegame_add_pts(state, g, contrib_player, _lap_c, _why)
                        if _to:
                            action['lap_contrib'] = {'name': _to, 'points': _lap_c}
                            print(f"🏁 [주사위게임] {_to} 에게 {_lap_c}점 (한 바퀴)")
                        else:
                            print(f"🏁 [주사위게임] 한 바퀴 {_lap_c}점 — 받을 말이 판에 없습니다")
                    else:
                        print(f"🏁 [주사위게임] 한 바퀴 {_lap_c}점 — 누구 차례인지 몰라 손으로")
            except Exception as e:
                print(f'⚠️ [주사위게임] 한 바퀴 기여도 실패 — 게임은 계속됩니다: {e}')
        piece['pos'] = to
        if lap:
            piece['laps'] += 1
        # 🕳️ 말을 다시 옮기는 칸(싱크홀·블랙홀)과 전원 지급 칸.
        #    화면이 두 번째 이동을 이어서 그리도록 action 에 실어 보낸다.
        _tt = tile.get('type')
        if _tt in ('move', 'goto') and piece.get('shield'):
            piece['shield'] = False
            action['shield_used'] = True
            action['key_effect'] = '실드로 막았다 — 옮겨지지 않는다'
            _tt = 'shielded'   # 아래 이동 분기가 안 걸리게
        if _tt in ('move', 'goto'):
            _pts = _as_int(tile.get('points'), 0) or 0
            _dest = (to + _pts) % n if _tt == 'move' else (_pts % n)
            # 두 번째 이동에는 한 바퀴 보상을 주지 않는다 — 벌칙으로 끌려간 것이지
            # 제 힘으로 돈 게 아니다.
            # 경로: move 는 한 칸씩 걸어간다(뒤로 가면 뒤로 밟는다).
            # 🕳️ goto(블랙홀)도 이제 걸어간다 — 사장님: "출발점으로 돌아가는 애니메이션이
            #    필요함, 근데 원래 가던 방향말고 반대방향으로 돌아야함".
            #    그래서 뒤로 몇 칸인지 재서 거꾸로 밟는다(21번 → 0번이면 21칸 역주행).
            #    ⚠️ 앞으로 한 칸처럼 그리면 벌칙이 아니라 보너스로 보인다 — 반드시 역방향.
            if _tt == 'goto':
                _back = (to - _dest) % n
                _path2 = [(to - i) % n for i in range(1, _back + 1)]
            elif _pts < 0:
                _path2 = [(to - i) % n for i in range(1, (-_pts) + 1)]
            else:
                _path2 = [(to + i) % n for i in range(1, _pts + 1)]
            piece['pos'] = _dest
            _t2 = tiles[_dest] if isinstance(tiles[_dest], dict) else {'id': _dest, 'type': 'blank'}
            action['after'] = {'kind': _tt, 'from': to, 'to': _dest, 'path': _path2,
                               'label': tile.get('label') or '',
                               # 🕳️ 역주행이다 — 화면은 이 표시를 보고 빠르게(110ms/칸) 밟는다.
                               #    21칸을 걸을 때(220ms)처럼 가면 4.6초라 늘어진다.
                               'rev': bool(_tt == 'goto' or (_as_int(tile.get('points'), 0) or 0) < 0),
                               'tile': {k: _t2.get(k) for k in ('id', 'type', 'label', 'points')}}
            # 🎯 끌려간 자리의 칸도 제 일을 해야 한다. 뒤로 5칸 밀렸는데 그 자리가
            #    기여도 칸이면 그 기여도를 받아야 말이 된다.
            #    ⚠️ 다시 옮기는 칸(move·goto)에는 걸지 않는다 — 싱크홀에서 싱크홀로
            #       끝없이 튕길 수 있고, 방송 중에 그게 터지면 손쓸 수가 없다.
            #    ⚠️ 시그니처 칸도 뺐다. 재생 큐가 얽혀 있어 굴림 한 번에 두 곡이
            #       걸릴 수 있다. 그 자리에 서면 진행자가 직접 틀어준다.
            _fx = _dicegame_dest_effects(state, g, piece, contrib_player, _dest, ' (끌려간 자리)')
            action['after'].update(_fx['parts'])
            if _fx['again']:
                _key_again = True
            print(f"🕳️ [주사위게임] {tile.get('label') or _tt} → {to}번에서 {_dest}번으로", flush=True)
            to = _dest
        elif _tt == 'giveall':
            _pts = _as_int(tile.get('points'), 0) or 0
            _got = []
            if _pts:
                _why = (tile.get('label') or '전원 지급') + ' 칸'
                for _pc in g['pieces']:
                    try:
                        if _dicegame_add_pts(state, g, _pc['name'], _pts, _why):
                            _got.append(_pc['name'])
                    except Exception as e:
                        print(f'⚠️ [주사위게임] 전원 지급 실패({_pc["name"]}) — 계속합니다: {e}')
            action['giveall'] = {'points': _pts, 'names': _got}
            print(f"🎁 [주사위게임] 전원 {_pts}점 → {', '.join(_got) or '아무도 못 받음'}", flush=True)
        elif _tt == 'steal':
            # 💰 뺏어오기 — 착지한 사람이 나머지 전원에게서 points 점씩 가져온다.
            #    판의 총점은 변하지 않는다(주고받기만 한다).
            _pts = _as_int(tile.get('points'), 0) or 0
            _st = _dicegame_steal(state, g, contrib_player or piece['name'], _pts)
            if _st:
                action['steal'] = _st
                print(f"💰 [주사위게임] {_st['taker']} 가 {len(_st['from'])}명에게서"
                      f" {_pts}점씩 (+{_st['gain']})", flush=True)
            else:
                action['score_note'] = '뺏을 상대가 없습니다'
        # 열쇠가 만든 두 번째 이동(뒤로 N칸·출발지로). 칸이 만든 이동(싱크홀)이 이미 있으면 그쪽이 우선.
        if _ke_after and not action.get('after'):
            action['after'] = _ke_after
            piece['pos'] = _ke_after['to']
            to = _ke_after['to']
        # 🙋 차례는 **그대로 둔다** — 방금 굴린 말이 다음에도 굴린다. 바뀌는 것은 조종실 · 폰에서 사람을 고를 때뿐.
        #    대표님(2026-09-30): "한 명 굴리면 다른 사람으로 굴리는 게 바뀌던데 내가 바꾸기 전까진 그대로 냅두게 해줘"
        #    ⚠️ 예전엔 굴릴 때마다 다음 말로 넘겼다(넷이 돌아가며 굴리는 규칙). 되돌리려면 (_idx + 1) % len(...).
        #       '한 번 더' 열쇠는 원래 '차례를 안 넘긴다' 였으므로 이제 따로 할 일이 없다.
        g['turn'] = _idx
        # 옛 저장본·옛 화면 호환 — 위치는 마지막으로 움직인 말,
        # 바퀴 수는 **넷을 합한 값**. 말마다 따로 세면 다른 말이 움직인 순간
        # 숫자가 거꾸로 줄어든다(화면의 '출발 N번' 이 깜빡 내려간다).
        g['pos'] = to
        g['laps'] = sum(x['laps'] for x in g['pieces'])
        g['action'] = action
        _dicegame_save(state, g)
    print(f"🎲 [주사위게임] {'+'.join(map(str, dice))} → {frm}→{to} 칸"
          f" ({tile.get('type')}{' 출발칸!' if lap else ''})", flush=True)
    return jsonify({'status': 'success', 'dice': dice, 'to': to,
                    'tile': action['tile'], 'lap': bool(lap),
                    'piece': piece['name'],
                    'scored': action.get('scored'), 'note': action.get('score_note'),
                    'steal': action.get('steal'), 'giveall': action.get('giveall'),
                    'contrib': action.get('contrib'),
                    'lap_contrib': action.get('lap_contrib'),
                    'key': action.get('key'),
                    'key_effect': action.get('key_effect'),
                    'shield_used': bool(action.get('shield_used')),
                    'again': bool(_key_again)})


@app.route('/api/dicegame/move', methods=['POST'])
def api_dicegame_move():
    """말 위치를 손으로 맞춘다(연출이 어긋났을 때의 비상 손잡이)."""
    body = request.get_json(silent=True) or {}
    pos = _as_int(body.get('pos'))
    if pos is None:
        return jsonify({'status': 'error', 'message': '칸 번호가 숫자가 아닙니다'}), 400
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        n = len(g.get('tiles') or [])
        if not n:
            return jsonify({'status': 'error', 'message': '먼저 판을 깔아주세요'}), 400
        if not (0 <= pos < n):
            return jsonify({'status': 'error', 'message': f'칸 번호는 0~{n - 1} 입니다'}), 400
        # 🧩 어느 말을 옮기는가. 안 주면 '다음 차례' 말 — 굴리기와 **같은 규칙**이어야 한다.
        #    (마지막으로 움직인 말을 잡게 했다가 되돌렸다: 옮긴 말과 이어서 굴리는 말이
        #     달라져 '19번으로 옮기고 1' 이 출발 칸에 안 닿았다.) 조종실 첫 줄에
        #    '(다음 차례: 누구)' 라고 적혀 있으니 비워 두면 그 말이다.
        #    엉뚱한 말을 옮기면 더 큰 사고가 되므로 고른 말을 응답에 실어 보낸다.
        _idx = _dicegame_pick(g, body.get('piece'))
        if _idx is None and not g['pieces']:
            return jsonify({'status': 'error',
                            'message': '점수판에 사람이 없습니다. 엑셀판에 선수를 넣어주세요'}), 400
        if _idx is None:
            _names = ' · '.join(x['name'] for x in g['pieces'])
            return jsonify({'status': 'error',
                            'message': "'%s' 말이 없습니다. 있는 말: %s"
                                       % (body.get('piece'), _names)}), 400
        piece = g['pieces'][_idx]
        piece['pos'] = pos
        g['pos'] = pos
        action = {'type': 'MOVE', 'ts': int(time.time() * 1000), 'to': pos,
                  'piece': piece['name'], 'piece_idx': _idx}
        # 🎯 '원하는 곳으로' 열쇠를 뽑은 말은 옮겨진 자리의 칸이 제 일을 한다 —
        #    고른 자리가 기여도 칸이면 그 기여도를 받아야 열쇠가 뜻이 있다. 한 번만.
        #    받는 사람은 그 말의 주인. 기억해 둔 남이 아니다.
        if piece.pop('choose', None):
            _fx = _dicegame_dest_effects(state, g, piece, piece['name'], pos, ' (원하는 곳으로)')
            action['tile'] = _fx['tile']
            action['choose'] = True
            action.update(_fx['parts'])
            if _fx['again']:
                g['turn'] = _idx
        g['action'] = action
        _dicegame_save(state, g)
    out = {'status': 'success', 'pos': pos, 'piece': piece['name']}
    for k in ('tile', 'scored', 'note', 'giveall', 'steal', 'key', 'key_effect', 'choose'):
        if k in action:
            out[k] = action[k]
    return jsonify(out)


@app.route('/api/dicegame/enable', methods=['POST'])
def api_dicegame_enable():
    """방송 화면에 보일지만 켜고 끈다(판 내용은 그대로)."""
    body = request.get_json(silent=True) or {}
    on = bool(body.get('on'))
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        _prev = showmod.ensure(state)['stage']
        if on:
            showmod.set_stage(state, 'dicegame')
        else:
            showmod.clear_stage(state, 'dicegame')
        _stage_log(_prev, state['show']['stage'])
        _dicegame_save(state, g)
    return jsonify({'status': 'success', 'enabled': on})


@app.route('/api/dicegame/reset', methods=['POST'])
def api_dicegame_reset():
    """말을 출발로 되돌린다. 칸 구성과 황금열쇠 덱은 남긴다 — 적는 데 든 손이 아깝다."""
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        for _p in g['pieces']:
            _p['pos'] = 0; _p['laps'] = 0
        for _v in (g.get('parked') or {}).values():   # 🅿️ 맡아 둔 이름도 출발로
            if isinstance(_v, dict):
                _v['pos'] = 0; _v['laps'] = 0
        g.update({'pos': 0, 'laps': 0, 'turn': 0,
                  'action': {'type': 'PLACE', 'ts': int(time.time() * 1000)}})
        showmod.clear_stage(state, 'dicegame')
        _dicegame_save(state, g)
    return jsonify({'status': 'success'})


@app.route('/api/dicegame/board', methods=['POST'])
def api_dicegame_board():
    """🏆 주사위 전용 점수판을 조종한다.

       body: {do: 'reset'}              전원 0점
             {do: 'set', name, pts}     한 사람 점수를 그 값으로
             {do: 'add', name, pts}     한 사람 점수를 그만큼 더한다(음수 가능)
             {do: 'apply', clear?}      **엑셀판 기여도로 옮긴다** (기본은 옮기고 판을 비운다)

    ⚠️ 'apply' 가 이 게임에서 유일하게 진짜 기여도를 건드리는 곳이다.
       사장님이 버튼을 눌러야만 넘어간다 — 게임 중에 저절로 넘어가면 되돌릴 수가 없다.
    """
    body = request.get_json(silent=True) or {}
    do = str(body.get('do') or '').strip().lower()
    if do not in ('reset', 'set', 'add', 'apply'):
        return jsonify({'status': 'error',
                        'message': "do 는 reset·set·add·apply 중 하나입니다"}), 400
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        moved, skipped = [], []
        if do == 'reset':
            for r in g['board']:
                r['pts'] = 0
            print('🏆 [주사위 판] 전원 0점으로 되돌렸습니다', flush=True)
        elif do in ('set', 'add'):
            nm = str(body.get('name') or '').strip()
            pts = _as_int(body.get('pts'))
            if pts is None:
                return jsonify({'status': 'error', 'message': '점수가 숫자가 아닙니다'}), 400
            r = _dicegame_row(g, nm)
            if r is None:
                _names = ' · '.join(x['name'] for x in g['board'])
                return jsonify({'status': 'error',
                                'message': "'%s' 가 판에 없습니다. 있는 사람: %s"
                                           % (nm, _names)}), 400
            before = _as_int(r.get('pts'), 0) or 0
            r['pts'] = pts if do == 'set' else before + pts
            _dicegame_log(state, r['name'], r['pts'] - before, '손으로 고침')
        else:   # apply
            # 🎯 전용 판 점수를 엑셀판 기여도에 더한다. 0점인 사람은 건너뛴다.
            #    ⚠️ 여기서만 _find_score_target(엑셀판)을 쓴다.
            _done = set()   # 실제로 옮긴 줄 — 이 줄만 비운다
            for r in g['board']:
                pts = _as_int(r.get('pts'), 0) or 0
                if not pts:
                    continue
                t = _find_score_target(state, 'rank', r['name'])
                if t is None:
                    # ⚠️ 못 찾은 사람의 점수는 **남긴다**. 예전엔 옮기지도 않고 아래에서 0 으로
                    #    비워 점수가 그냥 사라졌다. 조종실이 '못 옮긴 사람' 을 알린다.
                    print(f"⚠️ [주사위 판] '{r['name']}' 을(를) 엑셀판에서 못 찾아 건너뜁니다", flush=True)
                    skipped.append({'name': r['name'], 'points': pts})
                    continue
                _done.add(r['name'])
                t['contribution'] = (t.get('contribution') or 0) + pts
                logs = state.get('logs')
                if not isinstance(logs, list):
                    logs = []
                    state['logs'] = logs
                logs.insert(0, {'time': now_hms(), 'name': t.get('name') or r['name'],
                                'val': pts, 'kind': 'contrib', 'why': '🎲 주사위게임 정산'})
                del logs[LOG_MAX:]
                moved.append({'name': t.get('name') or r['name'], 'points': pts})
            # 🅿️ 명단에서 빠져 보관함에 맡겨 둔 사람의 점수도 **알린다**(옮기지는 않는다 — 엑셀판에 없는 이름이다).
            #    ⚠️ 예전엔 판만 봐서 보관함 점수는 아무 말 없이 지나갔고, 방송을 끝내면 보관함째 비워져 사라졌다.
            #       이름을 되돌리면 되살아나니, 사장님이 보고 고를 수 있게 '못 옮김' 에 같이 올린다.
            _on_board = {r['name'] for r in g['board']}
            for _nm, _v in (g.get('parked') or {}).items():
                _pp = _as_int((_v or {}).get('pts'), 0) if isinstance(_v, dict) else 0
                if _pp and _nm not in _on_board:
                    print(f"⚠️ [주사위 판] '{_nm}' 은(는) 명단에서 빠져 보관함에 {_pp}점이 있습니다 — 옮기지 않았습니다", flush=True)
                    skipped.append({'name': _nm, 'points': _pp, 'parked': True})
            if moved:
                src = 'extra_bjs' if state.get('extra_game_active') else 'bjs'
                lst = state.get(src) or []
                lst.sort(key=lambda b: -(b.get('contribution') or 0))
                state[src] = lst
            if body.get('clear', True):
                for r in g['board']:
                    if r['name'] in _done:
                        r['pts'] = 0
            print(f"🎯 [주사위 판] 기여도로 옮겼습니다 — {len(moved)}명"
                  + (f" · 못 옮김 {len(skipped)}명" if skipped else ''), flush=True)
        _dicegame_save(state, g)
    return jsonify({'status': 'success', 'board': g['board'], 'moved': moved, 'skipped': skipped})
