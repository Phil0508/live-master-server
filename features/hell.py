# -*- coding: utf-8 -*-
"""🔥 지옥탈출 — 목표 금액 · 시간 안에 탈출하는 번외 판.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import copy
import show as showmod
import time
from flask import jsonify, request
from server import (
    DEFAULT_STATE, _stage_log, app, broadcast_event, file_lock, load_data, save_data,
)


# ==========================================
# 🔥 지옥탈출 (2026-09-21 추석 방송 — 퇴근빵 대신 마지막에)
#    시작 순간 등수로 목표(점=만원)를 정하고, 그 뒤 받은 점수만 센다.
#    목표를 채우면 조종실이 /api/offwork/pending(kind=hell) 로 '탈출 성공' 카드를 만든다(퇴근빵과 같은 길).
#    ⚠️ 판정·벌칙은 없다. 채우면 탈출이고 끝이다. 벌칙 룰렛은 조종실 룰렛 탭에서 따로, 원할 때마다 돌린다.
#       (2026-09-21 에 '끝내기 → 못 채운 사람 벌칙' 으로 잘못 묶었다가 걷었다 — 대표님 2026-09-22)
# ==========================================
HELL_TARGETS = (50, 40, 30, 20)


def _hell_state(state):
    """항상 온전한 모양의 지옥탈출 상태를 돌려준다(옛 저장본에 없던 키 보정)."""
    h = state.get('hell')
    if not isinstance(h, dict):
        h = copy.deepcopy(DEFAULT_STATE['hell'])
        state['hell'] = h
    for k, v in DEFAULT_STATE['hell'].items():
        h.setdefault(k, copy.deepcopy(v))
    for k in ('base', 'goals'):
        if not isinstance(h.get(k), dict):
            h[k] = {}
    if not isinstance(h.get('escaped'), list):
        h['escaped'] = []
    for k in ('ended', 'final'):      # 옛 '끝내기(판정)' 칸 — 이제 안 쓴다
        h.pop(k, None)
    return h


def _hell_got(state, h):
    """지옥탈출 시작 뒤 받은 점수 {이름: 점}. 시작 순간보다 줄었으면 0 (점수 정정 등)."""
    base = h.get('base') or {}
    out = {}
    for b in (state.get('bjs') or []):
        n = b.get('name')
        if n in (h.get('goals') or {}):
            out[n] = max(0, int(b.get('score') or 0) - int(base.get(n) or 0))
    return out


def _hell_save(state, h):
    state['hell'] = h
    save_data(state)
    broadcast_event('update', state)


@app.route('/api/hell/start', methods=['POST'])
def api_hell_start():
    """지금 등수로 목표를 정하고 센다. 다시 누르면 처음부터 다시 잰다."""
    try:
        body = request.get_json(silent=True) or {}
        raw = body.get('targets') or HELL_TARGETS
        try:
            targets = [max(0, int(float(x))) for x in raw][:12]
        except (TypeError, ValueError):
            return jsonify({'status': 'error', 'message': '목표는 숫자(만원)로 넣어주세요'}), 400
        if not targets:
            targets = list(HELL_TARGETS)
        with file_lock:
            state = load_data()
            bjs = [b for b in (state.get('bjs') or []) if str(b.get('name') or '').strip()]
            if not bjs:
                return jsonify({'status': 'error', 'message': '선수가 없습니다 — 방송 시작부터 해주세요'}), 409
            # 점수 높은 순. 같으면 지금 줄 순서(랭킹판에 보이는 순서)를 따른다
            ranked = sorted(enumerate(bjs), key=lambda t: (-int(t[1].get('score') or 0), t[0]))
            h = _hell_state(state)
            h.update({'on': True, 'started_at': int(time.time() * 1000),
                      'base': {}, 'goals': {}, 'escaped': []})
            _prev = showmod.ensure(state)['stage']
            showmod.set_stage(state, 'hell')
            _stage_log(_prev, 'hell')
            for rank, (_, b) in enumerate(ranked):
                n = b['name']
                h['base'][n] = int(b.get('score') or 0)
                h['goals'][n] = targets[min(rank, len(targets) - 1)]   # 5등부터는 마지막 목표와 같다
            # 지난 판 '탈출 성공' 카드가 대기함에 남아 있으면 헷갈린다 — 걷는다
            state['pending_donations'] = [d for d in (state.get('pending_donations') or [])
                                          if not (d.get('type') == 'off_work' and d.get('kind') == 'hell')]
            _hell_save(state, h)
        print(f"  🔥 [지옥탈출 시작] {h['goals']}", flush=True)
        return jsonify({'status': 'success', 'hell': h})
    except Exception as e:
        print(f'[지옥탈출 시작 오류] {e}', flush=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/hell/goal', methods=['POST'])
def api_hell_goal():
    """한 사람 목표만 고친다(만원). 이미 탈출한 사람도 목표를 올리면 다시 '진행 중' 이 된다."""
    try:
        body = request.get_json(silent=True) or {}
        name = str(body.get('name') or '').strip()
        try:
            goal = max(0, int(float(body.get('goal'))))
        except (TypeError, ValueError):
            return jsonify({'status': 'error', 'message': '목표는 숫자(만원)로 넣어주세요'}), 400
        with file_lock:
            state = load_data()
            h = _hell_state(state)
            if name not in h['goals']:
                return jsonify({'status': 'error', 'message': '지옥탈출 명단에 없는 이름입니다'}), 404
            h['goals'][name] = goal
            got = _hell_got(state, h).get(name, 0)
            if got < goal and name in h['escaped']:
                h['escaped'].remove(name)
            _hell_save(state, h)
        return jsonify({'status': 'success', 'hell': h})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/hell/off', methods=['POST'])
def api_hell_off():
    """화면에서 내린다(기록은 남긴다 — 다시 켜려면 시작을 누른다)."""
    with file_lock:
        state = load_data()
        h = _hell_state(state)
        h['on'] = False
        showmod.clear_stage(state, 'hell')
        _hell_save(state, h)
    return jsonify({'status': 'success', 'hell': h})
