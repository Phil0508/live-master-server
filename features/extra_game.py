# -*- coding: utf-8 -*-
"""🎮 번외 게임 모드.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
from flask import jsonify
from server import (
    app, broadcast_event, file_lock, load_data, save_data,
)


# ==========================================
# 🎮 번외 게임 모드 제어 API
# ==========================================
@app.route('/api/extra_game/start', methods=['POST'])
def extra_game_start():
    try:
        with file_lock:
            state = load_data()
            state["extra_game_active"] = True
            
            # Initialize extra_bjs with all players from bjs, reset scores to 0
            state["extra_bjs"] = []
            for bj in state.get("bjs", []):
                state["extra_bjs"].append({
                    "name": bj["name"],
                    "score": 0,
                    "contribution": 0
                })
                
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/extra_game/end', methods=['POST'])
def extra_game_end():
    try:
        with file_lock:
            state = load_data()
            if not state.get("extra_game_active", False) or "extra_bjs" not in state:
                return jsonify({"status": "error", "message": "진행 중인 번외 게임이 없습니다."}), 400
                
            extra_scores = {bj["name"]: bj for bj in state.get("extra_bjs", [])}
            
            for bj in state.get("bjs", []):
                bj_name = bj["name"]
                if bj_name in extra_scores:
                    bj["score"] += extra_scores[bj_name]["score"]
                    bj["contribution"] = bj.get("contribution", 0) + extra_scores[bj_name].get("contribution", 0)
                    
            state["extra_game_active"] = False
            state["extra_bjs"] = []
            
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/extra_game/cancel', methods=['POST'])
def extra_game_cancel():
    try:
        with file_lock:
            state = load_data()
            state["extra_game_active"] = False
            state["extra_bjs"] = []
            
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
