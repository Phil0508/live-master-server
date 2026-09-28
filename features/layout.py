# -*- coding: utf-8 -*-
"""📐 위젯 자리(layout.json) 읽기 · 쓰기.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import json
import os
from flask import jsonify, request
from server import (
    LAYOUT_FILE, app, broadcast_event,
)


@app.route('/api/layout', methods=['GET', 'POST'])
def api_layout():
    if request.method == 'POST':
        # ⚠️ 여기 담기는 것은 '방송 화면의 모든 위젯 위치'다. 잘못 쓰면 오버레이가
        #    통째로 흐트러지고, 되돌릴 방법이 없다.
        #    ① 본문이 깨졌거나 사전이 아니면 아예 손대지 않는다
        #      (예전에는 request.json 이 그 자리에서 터져 500 이 났고, null 을 보내면
        #       파일에 'null' 이 적혀 배치가 날아갔다)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error",
                            "message": "레이아웃 내용(JSON 사전)이 필요합니다"}), 400
        data.pop('__scenes', None)          # 옛 '모드별 배치' 칸 — 세이브 슬롯으로 옮겼다
        _layout_write(data)
        return jsonify({"status": "success"})
    return jsonify(_layout_read())


def _layout_read():
    """배치 파일을 읽는다. 없거나 깨졌으면 빈 사전."""
    try:
        if os.path.exists(LAYOUT_FILE):
            with open(LAYOUT_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception as e:
        print(f'[배치 읽기 오류] {e}', flush=True)
    return {}


def _layout_write(data):
    # ② 임시 파일에 다 쓴 뒤 갈아끼운다. 쓰는 도중에 서버가 죽어도
    #    예전 배치가 그대로 남는다(반쯤 쓰인 파일은 읽을 수 없다).
    tmp = LAYOUT_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, LAYOUT_FILE)
    broadcast_event('layout', data)
