# -*- coding: utf-8 -*-
"""✨ 방송판 효과 — 대결 시간 끝 · 효과 켜기/끄기 · 룰렛 당첨 · 모금함.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import copy
import show as showmod
import time
from flask import jsonify, request
from server import (
    DEFAULT_STATE, _as_int, app, broadcast_event, file_lock, load_data, now_hms,
    request_is_authed, save_data,
)


@app.route('/api/match/timeup', methods=['POST'])
def api_match_timeup():
    """대결 타이머가 0이 됐을 때 오버레이가 알린다.

    ⚠️ 예전에는 오버레이가 이 목적으로 /api/data 에 '자기가 들고 있는 상태 전체'를 POST 했다.
       두 가지가 나빴다.
       1) 그것 때문에 /api/data POST 를 무인증으로 열어둘 수밖에 없었다(누구나 점수를 지울 수 있었다).
       2) 오버레이의 상태가 조금이라도 낡아 있으면 그 낡은 점수가 서버를 덮어썼다.
       그래서 '타이머를 멈춘다'는 사실만 전달하는 좁은 엔드포인트로 분리했다.
    """
    with file_lock:
        state = load_data()
        md = state.get('match_data') or {}
        if not md.get('active'):
            return jsonify({"status": "ignored"})   # 이미 끝난 대결이면 아무것도 하지 않는다

        # ⚠️ 이 경로도 무인증이라, 진행 중인 대결을 밖에서 아무 때나 끝낼 수 있었다.
        #    '정말 시간이 다 됐는지'를 서버가 직접 확인한다. 3초는 시계 차이·전송 지연 몫이다.
        end_ms = md.get('end_time_ms')
        if md.get('is_running') and end_ms and not request_is_authed():
            now_ms = int(time.time() * 1000)
            if now_ms < int(end_ms) - 3000:
                left = (int(end_ms) - now_ms) / 1000
                print(f"⛔ [대결 종료 거부] 아직 {left:.1f}초 남았습니다 (ip={request.remote_addr})", flush=True)
                return jsonify({"status": "error", "message": "아직 시간이 남았습니다"}), 409

        md['is_running'] = False
        md['time_left_ms'] = 0
        state['match_data'] = md
        save_data(state)
        broadcast_event('update', state)
    return jsonify({"status": "success"})


@app.route('/api/effect/fire', methods=['POST'])
def api_effect_fire():
    """후원 콘솔의 '이펙트' 탭에서 조종실(사장님) 후원 연출을 쏜다.

    body: {"kinds": ["banner","flash","ticker"], "name": 후원자, "amount": 금액, "message": 문구}

    ⚠️ 기존 시그니처·목표달성 연출과 섞지 않는다. 그쪽은 큐·게이지 상태에 묶여 있어서
       끼어들면 서로를 끊는다(실제로 그런 사고가 있었다). 전용 이벤트로 따로 보낸다.
    상태를 바꾸지 않고 이벤트만 쏘므로 file_lock 을 잡지 않는다.
    """
    data = request.get_json(silent=True) or {}
    kinds = data.get('kinds') or []
    if isinstance(kinds, str):
        kinds = [kinds]
    # 오버레이가 실제로 그릴 줄 아는 연출만 받는다(오타로 아무 일도 안 일어나는 것을 막는다)
    allowed = {'banner', 'flash', 'ticker', 'card', 'shock', 'glitch', 'warn'}
    kinds = [k for k in kinds if k in allowed]
    if not kinds:
        return jsonify({"status": "error", "message": "연출을 하나 이상 골라주세요"}), 400

    name = (data.get('name') or '').strip()
    message = (data.get('message') or '').strip()
    try:
        amount = int(data.get('amount') or 0)
    except (TypeError, ValueError):
        amount = 0

    broadcast_event('operator_effect', {
        "kinds": kinds, "name": name, "amount": amount, "message": message,
        "time": int(time.time() * 1000),
    })
    return jsonify({"status": "ok", "fired": kinds})


@app.route('/api/effect/clear', methods=['POST'])
def api_effect_clear():
    """연출을 즉시 걷는다(잘못 눌렀을 때)."""
    broadcast_event('operator_effect_clear', {})
    return jsonify({"status": "ok"})


# ⚠️ 아래 둘은 오버레이가 부르므로 로그인을 요구할 수 없다. 대신 '지금 그럴 상황인가'를
#    상태로 확인해, 아무 때나 밖에서 불러 방송을 흔드는 것을 막는다.
@app.route('/api/roulette/winner', methods=['POST'])
def api_roulette_winner():
    try:
        req_data = request.get_json(silent=True) or {}
        winner_name = req_data.get('name', '익명')
        with file_lock:
            state = load_data()
            if 'roulette' not in state:
                state['roulette'] = {
                    "command": None,
                    "command_time": 0,
                    "weight_type": "equal",
                    "select_name": "",
                    "select_index": -1,
                    "winner_name": None,
                    "is_spinning": False,
                    "item_source": "bj",
                    "custom_items": ["벌칙 1", "벌칙 2", "벌칙 3", "벌칙 4", "벌칙 5"]
                }
            # ⚠️ 돌고 있지 않은데 결과가 들어오면 밖에서 부른 것이다.
            #    (오버레이는 자기가 돌린 룰렛이 멈출 때만 부른다)
            #    로그인한 요청은 그대로 통과시킨다 — 조종실 조작이나 시험용이다.
            if not state['roulette'].get('is_spinning') and not request_is_authed():
                print(f"⛔ [룰렛 결과 거부] 돌고 있지 않은데 결과가 들어왔습니다 "
                      f"(ip={request.remote_addr}, 이름={winner_name})", flush=True)
                return jsonify({"status": "error", "message": "지금은 룰렛이 돌고 있지 않습니다"}), 409

            state['roulette']['winner_name'] = winner_name
            state['roulette']['command'] = 'ended'
            state['roulette']['is_spinning'] = False
            state['roulette']['command_time'] = int(time.time() * 1000)
            showmod.end_temp(state, 'roulette')     # 📺 원래 무대로 돌아간다(화면은 방송판이 4초 더 잡고 있다)
            
            # 랭킹 로그에 기록 추가
            time_str = now_hms()
            if 'logs' not in state:
                state['logs'] = []
            state['logs'].insert(0, {
                'time': time_str,
                'name': f"🎡 룰렛 결과: {winner_name}",
                'val': 0
            })
            if len(state['logs']) > 200:
                state['logs'] = state['logs'][:200]
                
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/fundjar', methods=['POST'])
def api_fundjar():
    """🏺 모금함 켜고 끄기 · 종잣돈 · 초기화.

    ⚠️ 돈을 더하는 길은 여기가 **아니다**. /api/score/add 의 scope='jar' 로 간다 —
       후원 배정과 같은 잠금·로그·이중배정 방지를 그대로 타야 하기 때문이다.
       여기에 따로 만들면 폰과 조종실이 동시에 눌렀을 때 금액이 어긋난다.
    """
    try:
        body = request.get_json(silent=True) or {}
        with file_lock:
            state = load_data()
            j = state.get('fundjar')
            if not isinstance(j, dict):
                j = copy.deepcopy(DEFAULT_STATE['fundjar'])
                state['fundjar'] = j
            if 'on' in body:
                showmod.set_hud(state, 'fundjar', bool(body.get('on')))   # 📺 고정 자리
            if body.get('seed') is not None:
                _s = _as_int(body.get('seed'))
                if _s is None or not (0 <= _s <= 100000000):
                    return jsonify({'status': 'error',
                                    'message': '종잣돈은 0~1억 사이 숫자입니다'}), 400
                j['seed'] = _s
            if body.get('reset'):
                j['score'] = 0        # 종잣돈은 남기고 후원분만 턴다
            j.setdefault('name', '모금함')
            save_data(state)
            broadcast_event('update', state)
        print(f"  🏺 [모금함] {'켬' if j['enabled'] else '끔'} · 종잣돈 {j['seed']:,}원"
              f" · 후원 {j['score']:,}원", flush=True)
        return jsonify({'status': 'success', 'fundjar': j})
    except Exception as e:
        print(f'[모금함 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500
