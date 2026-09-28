# -*- coding: utf-8 -*-
"""🎬 시그 리액션 대기줄 — 다음 · 멈춤 · 중단, 슬롯 돌리기, 대기줄에서 빼기.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import random
import show as showmod
import threading
from flask import jsonify, request
import server  # 연습 서버가 가짜로 바꿔 끼우는 시그니처 조회는 부를 때마다 server 에서 찾는다
from server import (
    SLOT_RESULT_DELAY_SEC, _slot_finish, _stage_log, app, broadcast_event, file_lock,
    load_data, request_is_authed, save_data, state_for_client,
)


@app.route('/api/reaction/next', methods=['POST'])
def next_reaction():
    try:
        data = request.get_json(silent=True) or {}
        pop_id = data.get('id')
        
        with file_lock:
            state = load_data()
            queue = state.get('reaction_queue', [])
            
            # ⚠️ 이 경로는 무인증으로 열려 있다(오버레이가 재생을 끝내고 스스로 넘겨야 하므로).
            #    그래서 '번호 없이 무조건 pop' 은 허용하면 안 된다 — 주소만 알면 누구나
            #    빈 POST 를 반복해 대기 중인 시그니처를 하나씩 지울 수 있다.
            #    돈을 낸 후원의 시그니처가 재생도 없이 사라지는데 흔적도 안 남는다.
            #    번호를 대면(오버레이가 하는 일) 큐 머리와 일치할 때만 지운다.
            #    번호 없이 넘기는 건 조종실·후원 콘솔의 '건너뛰기' 뿐이라 로그인을 요구한다.
            if not pop_id and not request_is_authed():
                return jsonify({"status": "error",
                                "message": "넘길 항목의 번호(id)가 필요합니다"}), 400

            if queue:
                if not pop_id or queue[0].get('id') == pop_id:
                    queue.pop(0)
                
            if not queue:
                state['reaction_mode'] = False
                
            save_data(state)
            broadcast_event('update', state)
        # 오버레이가 이 응답의 state 를 그대로 써서 다음 시그니처를 즉시 재생한다
        # (예전엔 pop 후 /api/data 를 한 번 더 불러 왕복이 2회였고, 그 사이 SSE 와 겹쳐
        #  대기열이 깊을 때 재생이 불안정했다. 이제 왕복 1회로 줄여 겹침/지연을 낮춘다.)
        # ⚠️ 여기도 반드시 state_for_client 를 거쳐야 한다.
        #    예전에는 strip_private_state 만 불러서 시그게임 마스킹이 빠져 있었고,
        #    시그니처가 재생될 때마다 덮인 카드 16장의 정체가 통째로 나갔다.
        out_state = state_for_client(state, request_is_authed())
        return jsonify({"status": "success", "message": "Popped reaction", "state": out_state})
    except Exception as e:
        print(f"Error in next_reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/reaction/pause', methods=['POST'])
def api_reaction_pause():
    """알림(시그니처) 재생을 잠시 멈추거나 다시 내보낸다.

    ⚠️ 큐는 건드리지 않는다. 멈춘 동안 들어온 후원은 그대로 쌓였다가 풀면 순서대로 나간다.
       큐를 지우는 '전체 비우기'(/api/reaction/stop)와 혼동하면 안 된다.
    ⚠️ 재생 중인 시그니처는 끊지 않는다. 오버레이가 '다음 것을 시작하지 않는' 방식으로 멈추므로,
       지금 나가고 있는 것은 끝까지 나가고 그 다음부터 멈춘다.
       (중간에 끊으면 돈 낸 후원자의 시그니처가 잘려나간다)

    body 에 paused 가 있으면 그 값으로, 없으면 현재값을 뒤집는다(버튼 한 개로 토글).
    """
    # ⚠️ request.json 은 Content-Type 이 application/json 이 아니면 415 를 던진다.
    #    이 엔드포인트는 '본문 없이 눌러서 토글'하는 쓰임이 정상이므로 그걸로 실패하면 안 된다.
    #    (실제로 콘솔 버튼이 헤더 없이 보내 415 로 막혔다)
    data = request.get_json(silent=True) or {}
    with file_lock:
        state = load_data()
        paused = bool(data['paused']) if 'paused' in data else not bool(state.get('reaction_paused'))
        state['reaction_paused'] = paused
        queued = len(state.get('reaction_queue') or [])
        save_data(state)
        broadcast_event('update', state)
    print(f"{'⏸️ 알림 일시정지' if paused else '▶️ 알림 재개'} (대기 {queued}건)", flush=True)
    return jsonify({"status": "success", "paused": paused, "queued": queued})

@app.route('/api/reaction/stop', methods=['POST'])
def stop_reaction():
    try:
        with file_lock:
            state = load_data()
            state['reaction_queue'] = []
            state['reaction_mode'] = False
            save_data(state)
            broadcast_event('update', state)
            broadcast_event('reaction_stop', {})
        return jsonify({"status": "success", "message": "All reactions stopped"})
    except Exception as e:
        print(f"Error in stop_reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/slot/spin', methods=['POST'])
def api_slot_spin():
    try:
        data = request.get_json(silent=True) or {}
        winner = data.get('winner')
        candidates = data.get('candidates', [])

        if not winner:
            # winner 미지정 시: 서버가 무작위 선택.
            # 이번 방송용으로 고른 후보(slot_pool)가 있으면 그 안에서만 뽑는다.
            try:
                sigs = server.supabase_list_signatures()
            except Exception as e:
                return jsonify({"status": "error", "message": f"시그니처 조회 실패: {e}"}), 500
            if not sigs:
                return jsonify({"status": "error", "message": "등록된 시그니처가 없습니다."}), 400

            pool_ids = load_data().get('slot_pool') or []
            if pool_ids:
                pool_set = {int(i) for i in pool_ids}
                filtered = [s for s in sigs if s.get('id') in pool_set]
                if filtered:
                    sigs = filtered
                else:
                    print("⚠️ [슬롯] 선택된 후보가 목록에 없어 전체에서 뽑습니다.")

            winner = random.choice(sigs)
            candidates = sigs

        # 릴이 도는 동안 슬롯 위젯이 확실히 보이도록 켠다.
        # (오버레이는 매 업데이트마다 slot_enabled로 표시를 다시 칠하므로 상태로 켜야 한다)
        with file_lock:
            state = load_data()
            _prev = showmod.ensure(state)['stage']
            showmod.set_stage(state, 'slot', temp=True)   # 📺 잠깐 — 당첨 뒤 원래 무대로 돌아간다
            _stage_log(_prev, 'slot')
            save_data(state)
            broadcast_event('update', state)

        broadcast_event('slot_spin', {
            "type": "slot_spin",
            "event": "slot_spin",
            "winner": winner,
            "candidates": candidates
        })

        # 당첨 발표(약 3.3초) 뒤에 슬롯을 끄고 시그니처를 리액션 큐에 넣는다.
        # 큐를 태우면 reaction_mode가 켜지고, 재생이 끝나면 큐가 비면서 자동으로 꺼진다.
        # 오버레이는 비인증이라 스스로 재생 API를 부를 수 없으므로 서버가 예약한다.
        threading.Timer(SLOT_RESULT_DELAY_SEC, _slot_finish, args=(winner,)).start()

        return jsonify({"status": "success", "winner": winner})
    except Exception as e:
        print(f"Error spinning slot: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/queue/remove/<string:rq_id>', methods=['POST'])
def remove_from_queue(rq_id):
    try:
        with file_lock:
            state = load_data()
            queue = state.get('reaction_queue', [])
            if queue:
                is_currently_playing = (queue[0]['id'] == rq_id)
                state['reaction_queue'] = [item for item in queue if item['id'] != rq_id]
                
                if is_currently_playing:
                    broadcast_event('reaction_stop', {'id': rq_id})
                    
                if not state['reaction_queue']:
                    state['reaction_mode'] = False
                    
                save_data(state)
                broadcast_event('update', state)
        return jsonify({"status": "success", "message": "Removed from queue"})
    except Exception as e:
        print(f"Error in remove_from_queue: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
