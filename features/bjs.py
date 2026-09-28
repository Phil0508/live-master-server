# -*- coding: utf-8 -*-
"""👥 BJ(선수) 일괄 등록.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
from flask import jsonify, request
from server import (
    app, broadcast_event, file_lock, load_data, save_data,
)


# ==========================================
# 👥 BJ 일괄 등록 API
# ==========================================
@app.route('/api/bjs/import', methods=['POST'])
def import_bjs():
    try:
        req = request.get_json(silent=True) or {}
        names = req.get('names', [])
        if not isinstance(names, list):
            return jsonify({'status': 'error', 'message': '이름 목록이 필요합니다.'}), 400
        if not names:
            return jsonify({'status': 'error', 'message': '등록할 이름이 없습니다.'}), 400
            
        with file_lock:
            state = load_data()
            overwrite = req.get('overwrite', False)
            new_bjs = []
            
            for name in names:
                name = name.strip()
                if not name:
                    continue
                new_bjs.append({"name": name, "score": 0, "contribution": 0})
                
            if overwrite:
                state['bjs'] = new_bjs
            else:
                existing_names = {bj['name'] for bj in state.get('bjs', [])}
                for new_bj in new_bjs:
                    if new_bj['name'] not in existing_names:
                        state['bjs'].append(new_bj)
                        
            save_data(state, sync=True)
            broadcast_event('update', state)
            
        return jsonify({'status': 'success', 'count': len(new_bjs)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
