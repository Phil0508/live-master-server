# -*- coding: utf-8 -*-
"""📋 수동 조작 이력 조회.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import time
from flask import jsonify, request
from server import (
    IS_POSTGRES, app, get_db_connection, ts_kst,
)


# ==========================================
# 📋 수동 조작 이력 조회 API
# ==========================================
@app.route('/api/manual_logs', methods=['GET'])
def get_manual_logs():
    try:
        source_filter = request.args.get('source', 'all')  # all, mobile, toonation
        name_filter = request.args.get('name', '').strip()
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(200, max(10, int(request.args.get('per_page', 50))))
        export_csv = request.args.get('export', '') == 'csv'
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Build WHERE clause
            conditions = []
            params = []
            if source_filter == 'mobile':
                conditions.append("source = " + ("$1" if IS_POSTGRES else "?"))
                params.append("mobile")
            elif source_filter == 'toonation':
                conditions.append("source = " + ("$1" if IS_POSTGRES else "?"))
                params.append("toonation")
            
            if name_filter:
                param_idx = len(params) + 1
                if IS_POSTGRES:
                    conditions.append(f"name LIKE ${param_idx}")
                else:
                    conditions.append("name LIKE ?")
                params.append(f"%{name_filter}%")
            
            where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            
            # Get total count
            count_q = f"SELECT COUNT(*) FROM donation_history{where_clause}"
            if IS_POSTGRES:
                # Replace $N placeholders for count query
                pg_count_q = count_q
                for i in range(len(params)):
                    pg_count_q = pg_count_q.replace(f"${i+1}", "%s", 1)
                cursor.execute(pg_count_q, params)
            else:
                cursor.execute(count_q, params)
            total_count = cursor.fetchone()[0]
            
            # CSV Export mode
            if export_csv:
                data_q = f"SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history{where_clause} ORDER BY id DESC"
                if IS_POSTGRES:
                    pg_data_q = data_q
                    for i in range(len(params)):
                        pg_data_q = pg_data_q.replace(f"${i+1}", "%s", 1)
                    cursor.execute(pg_data_q, params)
                else:
                    cursor.execute(data_q, params)
                rows = cursor.fetchall()
                
                import io, csv
                output = io.StringIO()
                output.write('\ufeff')  # BOM for Excel
                writer = csv.writer(output)
                writer.writerow(['ID', '시간', '이름', '변동량', '누적점수', '메시지', '출처'])
                for r in rows:
                    writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6]])
                
                from flask import Response
                return Response(
                    output.getvalue(),
                    mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=score_log_{time.strftime("%Y%m%d_%H%M%S")}.csv'}
                )
            
            # Paginated fetch
            offset = (page - 1) * per_page
            if IS_POSTGRES:
                param_idx_limit = len(params) + 1
                param_idx_offset = len(params) + 2
                data_q = f"SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history{where_clause} ORDER BY id DESC LIMIT ${param_idx_limit} OFFSET ${param_idx_offset}"
                pg_data_q = data_q
                all_params = params + [per_page, offset]
                for i in range(len(all_params)):
                    pg_data_q = pg_data_q.replace(f"${i+1}", "%s", 1)
                cursor.execute(pg_data_q, all_params)
            else:
                data_q = f"SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history{where_clause} ORDER BY id DESC LIMIT ? OFFSET ?"
                cursor.execute(data_q, params + [per_page, offset])
            
            rows = cursor.fetchall()
            logs = []
            for r in rows:
                # ⚠️ 장부에는 서버 지역시(운영 서버는 UTC)로 적혀 있다. 조종실 표에
                #    그대로 내보내면 9시간 뒤처진 시각이 뜬다 — 방송 중에 제일 자주 보는 표다.
                logs.append({
                    'id': r[0], 'timestamp': ts_kst(r[1]), 'name': r[2],
                    'amount': r[3], 'current_total': r[4],
                    'message': r[5], 'source': r[6]
                })
        
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        return jsonify({
            'status': 'success',
            'logs': logs,
            'page': page,
            'per_page': per_page,
            'total_count': total_count,
            'total_pages': total_pages
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
