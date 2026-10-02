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


# 🏺 모금함 깃발 자리 — 점수판 왼쪽 / 오른쪽 (2026-10-03 대표님 "모금함은 왼쪽 오른쪽 고를 수 있게")
#    깃발(108×262)은 점수판(878×262 — 늘 두 칸이라 폭이 안 바뀐다)과 키가 같게 그렸다.
#    둘을 한 줄로 나란히 세우고 순서만 바꾼다. 깃발 배율 = 점수판 배율(키가 같게).
#    ⚠️ 왼쪽을 고르면 **점수판이 깃발 폭만큼 오른쪽으로 비킨다** — 운영 배치는 점수판이 왼쪽 끝(10)에
#       붙어 있어서, 안 비키면 깃발이 들어갈 데가 없다. 오른쪽으로 돌아오면 점수판도 제자리로 온다.
#    ⚠️ 배치 파일(layout.json)에 바로 적는다 — 편집기에서 끈 것과 같은 길이라 편집기 · 방송판이 같이 따른다.
#       편집기에서 손으로 다시 옮기면 그게 이긴다(그때 자리는 'free').
_RANK_W, _FLAG_W, _CANVAS_W, _EDGE = 878, 108, 1080, 6


def _fj_rank(ly):
    """점수판 자리(x, y, 배율). 편집기에서 안 잡았으면 방송판 기본 자리(오른쪽 42 · 위 167 · 배율 1)."""
    r = ly.get('ranking') if isinstance(ly.get('ranking'), dict) else None
    if r and r.get('x_px') is not None:
        return float(r.get('x_px') or 0), float(r.get('y_px') or 0), float(r.get('scale') or 1)
    return float(_CANVAS_W - 42 - _RANK_W), 167.0, 1.0


def _fj_side_now(ly):
    """지금 깃발이 점수판 어느 쪽에 붙어 있나 — 'left' · 'right' · 'free'(따로 놓임)."""
    rx, ry, rs = _fj_rank(ly)
    f = ly.get('fundjar') if isinstance(ly.get('fundjar'), dict) else None
    if not f or f.get('x_px') is None:
        return 'free'
    fx, fy, fs = float(f.get('x_px') or 0), float(f.get('y_px') or 0), float(f.get('scale') or 1)
    if abs(fy - ry) > 40:
        return 'free'
    if 0 <= rx - (fx + _FLAG_W * fs) <= 60:
        return 'left'
    if 0 <= fx - (rx + _RANK_W * rs) <= 60:
        return 'right'
    return 'free'


@app.route('/api/fundjar/side', methods=['GET', 'POST'])
def api_fundjar_side():
    if request.method == 'GET':
        return jsonify({'side': _fj_side_now(_layout_read())})
    body = request.get_json(silent=True) or {}
    side = body.get('side')
    if side not in ('left', 'right'):
        return jsonify({'status': 'error', 'message': "side 는 'left' 나 'right' 여야 합니다"}), 400
    ly = _layout_read()
    # 옛 배치 파일(판 번호 2 미만)은 방송판이 통째로 무시한다 — 여기서 판 번호만 올리면 옛 자리들이 살아난다
    if any(not str(k).startswith('__') for k in ly) and (ly.get('__v') or 0) < 2:
        return jsonify({'status': 'error',
                        'message': '옛 배치 파일입니다 — 편집기를 한 번 열어 저장한 뒤 다시 눌러 주세요'}), 409
    rx, ry, rs = _fj_rank(ly)
    rank_w, flag_w, gap = _RANK_W * rs, _FLAG_W * rs, round(10 * rs)
    # 둘이 차지하는 줄의 왼쪽 끝 — 깃발이 이미 왼쪽에 붙어 있으면 깃발 자리, 아니면 점수판 자리
    origin = float(ly['fundjar']['x_px']) if _fj_side_now(ly) == 'left' else rx
    origin = max(0.0, min(origin, _CANVAS_W - _EDGE - (rank_w + gap + flag_w)))   # 화면 밖으로 안 나가게
    if side == 'right':
        rank_x, flag_x = origin, origin + rank_w + gap
    else:
        flag_x, rank_x = origin, origin + flag_w + gap
    rk = dict(ly['ranking']) if isinstance(ly.get('ranking'), dict) else {}
    rk.update({'x_px': round(rank_x), 'y_px': round(ry), 'scale': rs})
    ly['ranking'] = rk
    ly['fundjar'] = {'x_px': round(flag_x), 'y_px': round(ry), 'scale': rs}
    ly['__v'] = max(2, ly.get('__v') or 0)
    _layout_write(ly)
    return jsonify({'status': 'success', 'side': side, 'ranking': rk, 'fundjar': ly['fundjar']})
