# -*- coding: utf-8 -*-
"""🏆 이번 방송 후원 순위(공개).

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
from flask import jsonify
from server import (
    app, get_db_connection,
)


@app.route('/api/donation/ranking')
def api_donation_ranking():
    """현재 방송의 누적 후원 순위(이름별 합계·건수).
       donation_history는 방송 시작/종료 때 초기화되므로 자연히 '이번 방송' 집계가 된다."""
    try:
        rows = []
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, SUM(amount) AS total, COUNT(*) AS cnt, MAX(id) AS last_id
                FROM donation_history
                GROUP BY name
                ORDER BY total DESC, last_id DESC
            """)
            for r in cursor.fetchall():
                rows.append({'name': r[0], 'total': int(r[1] or 0), 'count': int(r[2] or 0)})
        return jsonify({'status': 'success', 'ranking': rows, 'count': len(rows)})
    except Exception as e:
        print(f"[후원 순위 조회 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e), 'ranking': []}), 500
