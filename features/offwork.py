# -*- coding: utf-8 -*-
"""🏠 퇴근빵 — 퇴근 알림 보내기 · 목표 달성 승인 · 대기 중인 퇴근 목록.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import time
import uuid
from flask import jsonify, request
from server import (
    _hell_state, app, broadcast_event, file_lock, load_data, now_hms, save_data,
)


@app.route('/api/offwork/broadcast', methods=['POST'])
def broadcast_offwork():
    """🏃 퇴근 성공 연출 송출. 운영자가 승인대기함에서 [송출하기]를 누를 때 호출된다."""
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '선수').strip()
        kind = 'hell' if data.get('kind') == 'hell' else 'home'
        broadcast_event('off_work_event', {'name': name, 'kind': kind})
        print(f"  🏃 [퇴근 송출] {name}")
        return jsonify({"status": "success", "message": f"{name}님 퇴근 이벤트를 송출했습니다."})
    except Exception as e:
        print(f"[퇴근 송출 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/goal/approve_event', methods=['POST'])
def approve_goal_event():
    """🎯 목표 100% 달성 연출 송출 승인. 운영자가 눌러야 오버레이에 연출이 나간다."""
    try:
        with file_lock:
            state = load_data()
            state['goal_event_pending'] = False
            state['goal_event_approved'] = True
            save_data(state)
            broadcast_event('goal_celebration', {
                'timestamp': time.time(),
                'target_goal': state.get('target_goal', 50000)
            })
            broadcast_event('update', state)
        print("  🎯 [목표 달성 연출 송출]")
        return jsonify({"status": "success", "message": "목표 달성 연출을 방송 화면에 송출했습니다!"})
    except Exception as e:
        print(f"[목표 연출 송출 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/offwork/pending', methods=['POST'])
def api_offwork_pending():
    """퇴근전쟁 목표를 넘긴 플레이어의 '퇴근 성공' 카드를 서버에 만든다.

    ⚠️ 예전에는 컨트롤러가 자기 pending_donations 에 카드를 직접 넣고 /api/data 로 밀어넣었다.
       그런데 pending_donations 는 SERVER_OWNED 라 그 POST 에서 통째로 버려진다.
       카드는 다음 update 가 오는 순간 화면에서 사라지는데, '이미 알렸다'는 표시
       (home_race_notified)는 서버 소유가 아니라 그대로 저장됐다.
       결과적으로 그 플레이어는 두 번 다시 퇴근 카드를 받지 못했다 = 퇴근 연출을 영영 못 보냄.
       카드 생성과 '알림 표시'를 서버 한 곳에서 같이 처리해 어긋날 수 없게 한다.
    """
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    # 🔥 kind='hell' 이면 지옥탈출 성공 카드. '이미 알렸다' 기록도 퇴근빵과 따로 쓴다
    #    (같은 사람이 퇴근빵으로 이미 카드를 받았어도 지옥탈출 카드는 따로 받아야 한다).
    kind = 'hell' if body.get('kind') == 'hell' else 'home'
    if not name:
        return jsonify({"status": "error", "message": "name required"}), 400
    with file_lock:
        state = load_data()
        pend = state.setdefault('pending_donations', [])
        if kind == 'hell':
            h = _hell_state(state)
            if not h.get('on') or name not in (h.get('goals') or {}):
                return jsonify({"status": "error", "message": "지옥탈출 중이 아닙니다"}), 409
            notified = h['escaped']
        else:
            notified = state.setdefault('home_race_notified', [])
        if name in notified or any(d.get('type') == 'off_work' and d.get('name') == name
                                   and (d.get('kind') or 'home') == kind for d in pend):
            return jsonify({"status": "success", "message": "already"})
        notified.append(name)
        pend.insert(0, {
            'id': f"off_{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}",
            'type': 'off_work',
            'kind': kind,
            'name': name,
            'amount': 0,
            'message': '🔥 지옥 탈출 성공!' if kind == 'hell' else '퇴근전쟁 목표 달성!',
            'time': now_hms(),
        })
        save_data(state)
        broadcast_event('update', state)
    print(f"  {'🔥 [지옥탈출]' if kind == 'hell' else '🏃 [퇴근전쟁]'} '{name}' 성공 카드 생성")
    return jsonify({"status": "success"})
