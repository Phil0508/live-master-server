# -*- coding: utf-8 -*-
"""💬 화면에 한마디 — 조종실 오른쪽 칸에 쓰고 Enter 치면 방송판 한가운데 1초 떴다가 사라진다(대표님 2026-10-07).

글씨: 궁서체 · 흰 글씨 · 검은 테두리 · 배경 없음(방송판 overlay.html 의 #say-layer).
상태 · 장부는 안 바꾸고 이벤트('say')만 쏜다 — 그래서 file_lock 을 잡지 않는다(operator_effect 와 같다).
로그인 필요(require_login 의 예외 목록에 없다) — 주소만 아는 사람이 방송에 아무 글이나 띄울 수 없다.
"""
import time

from flask import jsonify, request
from server import app, broadcast_event

SAY_MAX = 60      # 1초에 읽을 수 있는 만큼만 — 넘치면 자른다


@app.route('/api/say', methods=['POST'])
def api_say():
    """body: {text} → 방송판에 'say' 이벤트 {text, id, time}. 줄바꿈 · 겹친 띄어쓰기는 한 칸으로."""
    data = request.get_json(silent=True) or {}
    text = ' '.join(str(data.get('text') or '').split())[:SAY_MAX]
    if not text:
        return jsonify({"status": "error", "message": "띄울 글을 써 주세요"}), 400
    now = int(time.time() * 1000)
    broadcast_event('say', {"text": text, "id": now, "time": now})
    print(f'💬 [화면에 한마디] "{text[:30]}"', flush=True)
    return jsonify({"status": "ok", "text": text})
