# -*- coding: utf-8 -*-
"""📣 안내 전광판.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import time
from flask import jsonify, request
from server import (
    _as_int, app, broadcast_event, file_lock, load_data, save_data,
)


# ==========================================
# 📣 안내 전광판 — 로그인 필요
#   평소에는 화면이 서버 시계로 알아서 띄운다. 여기는 "지금 띄워" 만 받는다.
# ==========================================
@app.route('/api/notice/now', methods=['POST'])
def api_notice_now():
    """진행자가 고른 문구를 지금 띄운다. body: {idx?: 몇 번째}"""
    body = request.get_json(silent=True) or {}
    idx = _as_int(body.get('idx'), 0) or 0
    with file_lock:
        state = load_data()
        msgs = state.get('notice_msgs') or []
        if not msgs:
            return jsonify({'status': 'error', 'message': '띄울 문구가 없습니다'}), 400
        idx = max(0, min(len(msgs) - 1, idx))
        state['notice_now'] = {'ts': int(time.time() * 1000), 'idx': idx}
        save_data(state)
        broadcast_event('update', state)
    print(f'📣 [안내 전광판] 지금 띄움 — "{msgs[idx][:30]}"', flush=True)
    return jsonify({'status': 'success', 'idx': idx, 'text': msgs[idx]})
