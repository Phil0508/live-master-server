# -*- coding: utf-8 -*-
"""🎱 구슬 핀볼 — 먼저 바닥에 닿는 순서로 순위.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import copy
import random
import re
import show as showmod
import time
from flask import jsonify, request
from server import (
    DEFAULT_STATE, LOG_MAX, _stage_log, app, broadcast_event, file_lock, load_data, now_hms,
    save_data,
)


# ==========================================
# 🎱 구슬 핀볼
# ==========================================
#  구슬이 못·레일에 튕기며 떨어져, 먼저 바닥에 닿는 순서로 순위가 난다.
#  ⚠️ 물리는 **방송판(overlay)이 굴린다.** 서버는 심판만 본다 — 서버에서 물리를 돌리면
#     후원 접수까지 잠그게 되고, 굴러가는 그림을 실시간으로 내보낼 방법도 없다.
#  ⚠️ 그래서 화면이 여럿이면(OBS + 미리보기) 각자 굴려 **다른 우승자**가 나올 수 있다.
#     둘로 막는다:
#       ① 판마다 서버가 씨앗(seed)을 준다 — 같은 씨앗이면 같은 경기를 본다
#       ② 결과는 **먼저 온 보고 하나만** 받고 그 자리에서 문을 닫는다(running=False).
#          늦게 온 것은 409. 룰렛 /api/roulette/winner 이 쓰는 바로 그 방식이다.

PINBALL_MAX = 800     # 한 판에 들어갈 수 있는 구슬 수 (대표님 2026-09-27: 200 → 800)
#  ⚠️ 40개를 넘으면 방송판이 **구슬 밑 이름을 안 붙인다**(겹쳐서 안 읽힌다).
#     주인공 한 명만 남긴다 — overlay.html 의 PB_NAME_MAX.
#  ⚠️ overlay.html 의 PB_BALL_MAX 와 **같아야 한다.** 방송판은 그 숫자로 출발 줄 수와
#     뚜껑 높이를 정한다. 틀어지면 윗줄 구슬이 뚜껑 위에서 시작해 영영 못 내려온다.
#     검사가 둘을 맞대본다(tests/pinball_test.py).


def _pinball_state(state):
    """항상 온전한 모양의 핀볼 상태를 돌려준다(예전 저장본에 없던 키 보정)."""
    g = state.get('pinball')
    if not isinstance(g, dict):
        g = copy.deepcopy(DEFAULT_STATE['pinball'])
        state['pinball'] = g
    for k, v in DEFAULT_STATE['pinball'].items():
        g.setdefault(k, copy.deepcopy(v))
    for k in ('names', 'result'):
        if not isinstance(g.get(k), list):
            g[k] = []
    # 🚫 저장본에 막은 맵이 적혀 있으면 여기서 조용히 우리 코스로 돌린다.
    #    읽을 때마다 보정하므로 대표님이 따로 할 일이 없다.
    g['map'] = _pinball_map(g.get('map'))
    return g


def _pinball_map(raw):
    """고른 맵 번호를 다듬는다. -1(우리 코스) ～ PINBALL_MAPS-1 사이로만 받는다.

    ⚠️ 범위를 안 지키면 방송판이 없는 맵을 찾다가 빈 화면이 된다.
    ⚠️ 막아 둔 맵(PINBALL_BLOCKED)도 우리 코스로 떨궄다. 조종실 목록에서 빼는 것만으로는
       옛 저장본·손으로 보낸 요청을 못 막는다.
    """
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return -1
    if v in PINBALL_BLOCKED:
        return -1
    return v if -1 <= v < PINBALL_MAPS else -1


PINBALL_MAPS = 4      # vendor/pinball-maps.js 에 든 맵 개수
# 🚫 못 고르게 막은 맵. 2 = Pot of greed — 항아리에 구슬이 갇혀 '끝까지 남기'
#    25판 중 16판이 중간에 멈췤다(중앙값 46초). 속도 상한·되돌림을 달리 해도
#    그대로여서 조율로는 못 고친다. 대표님: "Pot of greed 맵 빼버려" (2026-09-16)
# ⚠️ 맵 데이터는 vendor/pinball-maps.js 에 그대로 둔다. 배열에서 지우면 뒤 맵의
#    **번호가 밀려**(3 Yoru → 2) 저장된 3 이 어느 날 딕 맵을 가리킨다.
#    다시 쓰려면 이 줄에서 2 만 빼면 된다.
PINBALL_BLOCKED = (2,)
PINBALL_RULES = ('first', 'last')


def _pinball_rule(raw):
    """우승 규칙을 다듬는다. 아는 값이 아니면 '먼저 골인'으로 둔다.

    ⚠️ 모르는 값을 그대로 저장하면 방송판이 'first' 로 굴리고 조종실은
       딴 글자를 보여 준다 — 두 화면이 서로 다른 말을 하게 된다.
    """
    v = str(raw or '').strip().lower()
    return v if v in PINBALL_RULES else 'first'


def _pinball_save(state, g):
    # ⚠️ 구슬 목록과 뽑는 수는 **저장할 때마다 여기서만** 다시 센다.
    #    부르는 곳마다 따로 세면 언젠가 한 군데를 빼먹어 어긋난다.
    g['balls'] = _pinball_expand(g.get('names'))
    g['picks'] = _pinball_picks(g.get('picks'), len(g['balls']))
    g['winners'] = _pinball_winners(g.get('result'), g.get('rule'), g.get('picks'))
    state['pinball'] = g
    save_data(state)
    broadcast_event('update', state)


# 한 사람이 *N 으로 넣을 수 있는 최대 — 전체 상한과 같다.
# ⚠️ 어차피 펼친 개수는 PINBALL_MAX 에서 다시 잘린다. 여기를 낮게 잡으면
#    '양양*50' 같은 정당한 쓰임까지 막힌다.
PINBALL_COUNT_MAX = PINBALL_MAX


def _pinball_expand(names):
    """양양*3 처럼 적은 것을 실제 구슬 목록으로 펼친다.

    → ['밍밍', '양양*3'] 이면 ['밍밍', '양양', '양양', '양양']

    💡 왜 필요한가: 많이 후원한 분에게 표를 더 주는 쓰임이다.
       (원본 lazygyu/roulette 도 같은 표기를 쓴다)
    ⚠️ 펼친 개수는 반드시 PINBALL_MAX 로 자른다. 안 자르면 양양*999 하나로
       구슬 천 개가 생겨 방송판이 멈춘다.
    ⚠️ 이름에서 *N 은 떼고 넣는다 — 구슬 밑에 '양양*3' 이 보이면 안 된다.
    """
    out = []
    for raw in (names or []):
        nm = str(raw).strip()
        if not nm:
            continue
        cnt = 1
        m = re.search(r'\*\s*(\d+)\s*$', nm)
        if m:
            nm = nm[:m.start()].strip()
            try:
                cnt = max(1, min(PINBALL_COUNT_MAX, int(m.group(1))))
            except ValueError:
                cnt = 1
        if not nm:
            continue
        for _ in range(cnt):
            out.append(nm[:20])
            if len(out) >= PINBALL_MAX:
                return out
    return out


def _pinball_winners(order, rule, picks):
    """도착 순서에서 **실제 당첨자**를 골라낸다.

    ⚠️ '끝까지 남기'(last) 는 **뒤에서부터**다. 제일 늦게까지 안 떨어진 사람이 1등이라
       뒤에서 picks 명을 떼어 **뒤집어서** 준다.
    ⚠️ 방송판 overlay.html 의 pbWinnersOf 와 **같은 셈**이어야 한다.
       한쪽만 고치면 화면에 뜬 이름과 기록에 남은 이름이 달라진다(검사가 맞대본다).
    """
    if not isinstance(order, list) or not order:
        return []
    try:
        k = max(1, min(int(picks or 1), len(order)))
    except (TypeError, ValueError):
        k = 1
    if rule == 'last':
        return list(reversed(order[len(order) - k:]))
    return order[:k]


def _pinball_picks(raw, total):
    """몇 명 뽑을지 다듬는다. 1명 ～ (참가 구슬 수 - 1) 사이로만 받는다.

    ⚠️ 사람 수만큼 다 뽑으면 경기가 아니다. 최소 한 명은 남겨 둔다.
    """
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return 1
    hi = max(1, int(total) - 1) if total else 1
    return max(1, min(v, hi))


def _pinball_names(raw):
    """조종실이 보낸 참가자를 목록으로 다듬는다.

    글 한 덩어리(쉼표·줄바꿈)로 와도 받고, 이미 목록이어도 받는다.
    ⚠️ 같은 이름을 여러 번 넣는 것은 막지 않는다 — 여러 번 넣어 확률을 올리는
       쓰임이 있다. 대신 빈 것만 걷고 개수와 길이를 제한한다.
    """
    if isinstance(raw, str):
        items = re.split(r'[,\n\r]+', raw)
    elif isinstance(raw, (list, tuple)):
        items = [str(x) for x in raw]
    else:
        items = []
    out = []
    for it in items:
        nm = str(it).strip()
        if nm:
            out.append(nm[:20])       # 이름이 길면 구슬 밑에 안 들어간다
    return out[:PINBALL_MAX]


@app.route('/api/pinball/setup', methods=['POST'])
def api_pinball_setup():
    """참가자 명단을 넣는다. 굴러가는 중에는 못 바꾼다."""
    try:
        body = request.get_json(silent=True) or {}
        names = _pinball_names(body.get('names'))
        with file_lock:
            state = load_data()
            g = _pinball_state(state)
            if g.get('running'):
                return jsonify({'status': 'error',
                                'message': '굴러가는 중에는 명단을 못 바꿉니다'}), 409
            g['names'] = names
            if body.get('map') is not None:
                g['map'] = _pinball_map(body.get('map'))
            if body.get('rule') is not None:
                g['rule'] = _pinball_rule(body.get('rule'))
            if body.get('picks') is not None:
                g['picks'] = body.get('picks')        # 다듬기는 _pinball_save 가 한다
            if body.get('skills') is not None:
                g['skills'] = bool(body.get('skills'))
            g['result'] = []
            _pinball_save(state, g)
        return jsonify({'status': 'success', 'pinball': g})
    except Exception as e:
        print(f'[핀볼 명단 오류] {e}', flush=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/pinball/enable', methods=['POST'])
def api_pinball_enable():
    """화면에 띄우거나 내린다. 켤 때는 다른 게임판을 내린다(같은 자리를 쓴다)."""
    try:
        body = request.get_json(silent=True) or {}
        on = bool(body.get('enabled'))
        with file_lock:
            state = load_data()
            g = _pinball_state(state)
            _prev = showmod.ensure(state)['stage']
            if on:
                showmod.set_stage(state, 'pinball')
            else:
                showmod.clear_stage(state, 'pinball')   # 내리면 굴리던 것도 멈춘다(project)
                g['running'] = False
            _stage_log(_prev, state['show']['stage'])
            _pinball_save(state, g)
        return jsonify({'status': 'success', 'pinball': g})
    except Exception as e:
        print(f'[핀볼 표시 오류] {e}', flush=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/pinball/start', methods=['POST'])
def api_pinball_start():
    """한 판 굴린다. 판 번호를 올리고 새 씨앗을 준다."""
    try:
        body = request.get_json(silent=True) or {}
        with file_lock:
            state = load_data()
            g = _pinball_state(state)
            if body.get('names') is not None:
                g['names'] = _pinball_names(body.get('names'))
            if body.get('map') is not None:
                g['map'] = _pinball_map(body.get('map'))
            if body.get('rule') is not None:
                g['rule'] = _pinball_rule(body.get('rule'))
            if body.get('picks') is not None:
                g['picks'] = body.get('picks')        # 다듬기는 _pinball_save 가 한다
            if body.get('skills') is not None:
                g['skills'] = bool(body.get('skills'))
            # ⚠️ 이름 수가 아니라 **펼친 구슬 수**로 본다.
            #    '밍밍, 양양*2' 는 이름은 둘인데 구슬은 셋이다.
            if len(_pinball_expand(g['names'])) < 2:
                return jsonify({'status': 'error',
                                'message': '구슬이 둘 이상이어야 합니다'}), 400
            _prev = showmod.ensure(state)['stage']
            showmod.set_stage(state, 'pinball')
            _stage_log(_prev, 'pinball')
            g['running'] = True
            g['result'] = []
            g['round_id'] = int(g.get('round_id') or 0) + 1
            # 🌱 씨앗 — 모든 화면이 이걸로 같은 경기를 굴린다
            g['seed'] = random.randint(1, 2000000000)
            g['started_at'] = int(time.time() * 1000)
            _pinball_save(state, g)
        print("🎱 [핀볼] %d판 시작 — 구슬 %d개(%d명) · %s %d명 뽑기"
              % (g['round_id'], len(g.get('balls') or []), len(g['names']),
                 g.get('rule'), g.get('picks')), flush=True)
        return jsonify({'status': 'success', 'pinball': g})
    except Exception as e:
        print(f'[핀볼 시작 오류] {e}', flush=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/pinball/result', methods=['POST'])
def api_pinball_result():
    """방송판이 보내는 도착 순서. **먼저 온 하나만** 받는다.

    ⚠️ 룰렛과 같은 문지기다. running 이 꺼져 있으면 거절한다 — 화면이 여럿이면
       같은 판의 결과가 여러 번 들어오는데, 나중 것이 앞선 결과를 덮으면 안 된다.
    ⚠️ 판 번호(round_id)도 본다. 늦게 도착한 **지난 판** 결과가 지금 판을 끝내면 안 된다.
    """
    try:
        body = request.get_json(silent=True) or {}
        order = _pinball_names(body.get('result'))
        rid = body.get('round_id')
        with file_lock:
            state = load_data()
            g = _pinball_state(state)
            if not g.get('running'):
                return jsonify({'status': 'error',
                                'message': '지금은 핀볼이 굴러가고 있지 않습니다'}), 409
            try:
                if rid is not None and int(rid) != int(g.get('round_id') or 0):
                    return jsonify({'status': 'error',
                                    'message': '지난 판의 결과입니다'}), 409
            except (TypeError, ValueError):
                return jsonify({'status': 'error', 'message': '판 번호가 이상합니다'}), 400
            if not order:
                return jsonify({'status': 'error', 'message': '결과가 비어 있습니다'}), 400
            g['running'] = False          # 🚪 여기서 문을 닫는다 — 다음 보고는 409
            g['result'] = order
            # 🏆 규칙에 맞는 진짜 1등. ⚠️ order[0] 이 아니다 — '끝까지 남기' 면 그건 꼴찌다.
            _win = _pinball_winners(order, g.get('rule'), g.get('picks'))
            _top = _win[0] if _win else order[0]
            took = max(0, int(time.time() * 1000) - int(g.get('started_at') or 0))
            logs = state.setdefault('logs', [])
            logs.insert(0, {'time': now_hms(),
                            'name': "🎱 핀볼 1등: %s" % _top, 'val': 0})
            del logs[LOG_MAX:]
            _pinball_save(state, g)
        print("🎱 [핀볼] %d판 끝 — 1등 %s (%.1f초)"
              % (g['round_id'], _top, took / 1000.0), flush=True)
        return jsonify({'status': 'success', 'pinball': g, 'took_ms': took})
    except Exception as e:
        print(f'[핀볼 결과 오류] {e}', flush=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/pinball/reset', methods=['POST'])
def api_pinball_reset():
    """굴리던 것을 멈추고 결과를 지운다. 명단은 남긴다(다음 판에 또 쓴다)."""
    try:
        with file_lock:
            state = load_data()
            g = _pinball_state(state)
            g.update({'running': False, 'result': [], 'started_at': 0})
            _pinball_save(state, g)
        return jsonify({'status': 'success', 'pinball': g})
    except Exception as e:
        print(f'[핀볼 초기화 오류] {e}', flush=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500
