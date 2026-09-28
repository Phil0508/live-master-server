# -*- coding: utf-8 -*-
"""📊 조종실에서 무엇을 많이 누르나 — 클릭 기록.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import time
from flask import jsonify, request
from server import (
    _bc_shift_hours, app, db_query, get_db_connection, load_data,
)


# ==========================================
# 📊 조종실에서 무엇을 많이 누르나 (대표님 2026-09-22)
#    조종실이 20초마다 '무엇을 몇 번' 만 묶어 보낸다 → 방송별로 더해 쌓는다.
#    추석 방송 뒤 이걸 보고 탭 정리를 확정한다(자주 누르는 건 앞으로, 안 누르는 건 접기).
#    ⚠️ 방송 흐름에 끼면 안 된다 — 실패해도 조용히 넘어가고, 한 번에 받는 양을 자른다.
# ==========================================
UI_CLICK_MAX_KEYS = 200


def _ui_session(state):
    """지금 클릭이 어느 방송 것인지. 방송 중이면 시작 시각, 아니면 '방송 밖 + 날짜'."""
    shift = _bc_shift_hours() * 3600
    started = int(state.get('broadcast_started_at') or 0)
    if state.get('broadcast_active') and started:
        return time.strftime('%Y-%m-%d %H:%M 방송', time.localtime(started / 1000 + shift))
    return time.strftime('%Y-%m-%d 방송 밖', time.localtime(time.time() + shift))


@app.route('/api/uistats', methods=['POST'])
def api_uistats_add():
    try:
        body = request.get_json(silent=True, force=True) or {}
        rows = body.get('counts') or []
        if not isinstance(rows, list):
            return jsonify({'status': 'error', 'message': 'counts'}), 400
        clean = []
        for r in rows[:UI_CLICK_MAX_KEYS]:
            if not isinstance(r, dict):
                continue
            key = str(r.get('key') or '').strip()[:80]
            try:
                n = int(r.get('n') or 0)
            except (TypeError, ValueError):
                n = 0
            if not key or n <= 0:
                continue
            clean.append((key, str(r.get('label') or '')[:60], str(r.get('tab') or '')[:30], min(n, 5000)))
        if not clean:
            return jsonify({'status': 'success', 'saved': 0})
        session = _ui_session(load_data())
        with get_db_connection() as conn:
            cur = conn.cursor()
            for key, label, tab, n in clean:
                cur.execute(db_query(
                    "INSERT INTO ui_clicks (session, key, label, tab, n) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT (session, key) DO UPDATE SET n = ui_clicks.n + excluded.n, "
                    "label = excluded.label, tab = excluded.tab"), (session, key, label, tab, n))
        return jsonify({'status': 'success', 'saved': len(clean), 'session': session})
    except Exception as e:
        print(f'[클릭 기록 오류] {e}', flush=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/uistats', methods=['GET'])
def api_uistats_get():
    """?session= 없으면 방송 목록(최근 순), 있으면 그 방송의 순위."""
    try:
        session = (request.args.get('session') or '').strip()
        with get_db_connection() as conn:
            cur = conn.cursor()
            if not session:
                cur.execute(db_query("SELECT session, SUM(n), COUNT(*) FROM ui_clicks GROUP BY session ORDER BY session DESC"))
                out = [{'session': r[0], 'total': int(r[1] or 0), 'kinds': int(r[2] or 0)} for r in cur.fetchall()]
                return jsonify({'status': 'success', 'sessions': out, 'now': _ui_session(load_data())})
            cur.execute(db_query("SELECT key, label, tab, n FROM ui_clicks WHERE session = ? ORDER BY n DESC, key"), (session,))
            rows = [{'key': r[0], 'label': r[1], 'tab': r[2], 'n': int(r[3] or 0)} for r in cur.fetchall()]
            return jsonify({'status': 'success', 'session': session, 'rows': rows})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
