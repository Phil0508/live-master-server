# -*- coding: utf-8 -*-
"""📚 지난 방송 후원내역과 🗓️ 월별 후원 순위(수요일 방송 시간만).

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import datetime
import time
from flask import jsonify, request
from server import (
    BC_END_H, BC_START_H, _bc_shift_hours, _bc_window, _norm_donor, app, db_query,
    get_db_connection, is_excluded, request_is_authed, ts_kst,
)


# ==========================================
# 📚 지난 방송 후원내역 (donation_archive) — 로그인 필요
#   방송 종료 때마다 그 회차 장부가 여기로 옮겨진다(지우지 않는다).
#   넣기만 하고 읽는 길이 없어서 그동안 꺼내 볼 수가 없었다.
# ==========================================
ARCHIVE_ROWS_MAX = 5000      # 한 회차가 이보다 많으면 잘라 보낸다(화면이 감당 못 한다)


def _csv_cell(v):
    """엑셀에서 열 때 안전한 한 칸으로 만든다.

       ⚠️ = + - @ 로 시작하는 값은 엑셀이 '수식'으로 읽는다. 후원 메시지는
          후원자가 적는 글이라 그런 글자로 시작할 수 있고, 그대로 두면 정산 파일을
          여는 순간 엑셀이 계산을 시도한다(수식 주입). 앞에 따옴표를 붙여 글로 못박는다.
    """
    t = '' if v is None else str(v)
    if t[:1] in ('=', '+', '-', '@'):
        t = "'" + t
    return '"' + t.replace('"', '""') + '"'


@app.route('/api/ranking/monthly')
def api_ranking_monthly():
    """월별 후원 순위. ?month=YYYY-MM (없으면 이번 달).

       ⚠️ 수요일 17:00~목요일 03:00 에 들어온 것만 센다. 그 밖의 후원은 뺀다.
    """
    if not request_is_authed():
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    shift = _bc_shift_hours()
    want = (request.args.get('month') or '').strip()
    try:
        rows = []
        with get_db_connection() as conn:
            cur = conn.cursor()
            # 지난 방송분과 이번 방송분을 같이 본다 — 이번 주 것도 순위에 들어가야 한다
            for tbl in ('donation_archive', 'donation_history'):
                try:
                    cur.execute(db_query(
                        "SELECT timestamp, name, amount FROM %s" % tbl))
                    rows.extend(cur.fetchall())
                except Exception as e:
                    print(f'[월별 순위] {tbl} 조회 실패(건너뜀): {e}')

        months, tally = {}, {}
        for ts, name, amount in rows:
            day = _bc_window(ts, shift)
            if not day:
                continue                      # 방송 시간 밖 — 안 센다
            mon = '%04d-%02d' % (day.year, day.month)
            months[mon] = months.get(mon, 0) + 1
            if want and mon != want:
                continue
            who = _norm_donor(name)
            # ⚠️ 익명은 사람이 아니다. 그런데 여기만 안 빼고 있어서, 익명 후원 여러
            #    건이 한 덩어리로 묶여 순위 위쪽에 사람처럼 앉아 있었다.
            if is_excluded(name):
                continue
            row = tally.setdefault(who, {'name': name or who, 'total': 0,
                                         'count': 0, 'days': set()})
            row['total'] += int(amount or 0)
            row['count'] += 1
            row['days'].add(str(day))

        # 달을 안 골랐으면 자료가 있는 가장 최근 달
        if not want:
            want = max(months) if months else time.strftime('%Y-%m')
            tally = {}
            for ts, name, amount in rows:
                day = _bc_window(ts, shift)
                if not day or '%04d-%02d' % (day.year, day.month) != want:
                    continue
                who = _norm_donor(name)
                if is_excluded(name):
                    continue
                row = tally.setdefault(who, {'name': name or who, 'total': 0,
                                             'count': 0, 'days': set()})
                row['total'] += int(amount or 0)
                row['count'] += 1
                row['days'].add(str(day))

        out = sorted(tally.values(), key=lambda r: -r['total'])
        for r in out:
            r['days'] = len(r['days'])        # 몇 번의 방송에 왔나
        now = datetime.datetime.now()
        return jsonify({
            'status': 'success',
            'month': want,
            'rows': out,
            'total': sum(r['total'] for r in out),
            'months': sorted(months, reverse=True),
            # ⚠️ 시간대가 어긋나면 한 건도 안 잡힌다. 눈으로 바로 확인되게 같이 보낸다.
            'clock': {
                'server': now.strftime('%Y-%m-%d %H:%M:%S'),
                'shifted': (now + datetime.timedelta(hours=shift)).strftime('%Y-%m-%d %H:%M:%S'),
                'shift': shift,
            },
            'window': '수요일 %02d:00 ~ 목요일 %02d:00' % (BC_START_H, BC_END_H),
        })
    except Exception as e:
        print(f'[월별 순위 조회 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e), 'rows': []}), 500


@app.route('/api/archive/sessions')
def api_archive_sessions():
    """회차 목록. 언제 방송분이 몇 건이고 얼마인지."""
    try:
        out = []
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("""
                SELECT session_label, COUNT(*), SUM(amount), MIN(timestamp), MAX(timestamp)
                FROM donation_archive
                GROUP BY session_label
                ORDER BY MAX(archived_at) DESC, session_label DESC
            """))
            for r in cur.fetchall():
                # ⚠️ label 은 회차를 고르는 열쇠라 그대로 둔다. 시각만 한국 시각으로 옮긴다.
                out.append({'label': r[0] or '(이름 없음)', 'count': int(r[1] or 0),
                            'total': int(r[2] or 0),
                            'first': ts_kst(r[3]), 'last': ts_kst(r[4])})
        return jsonify({'status': 'success', 'sessions': out, 'count': len(out)})
    except Exception as e:
        print(f'[지난 방송 목록 조회 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e), 'sessions': []}), 500


@app.route('/api/archive/rows')
def api_archive_rows():
    """한 회차의 후원내역. ?label=... 로 회차를 고른다."""
    label = (request.args.get('label') or '').strip()
    if not label:
        return jsonify({'status': 'error', 'message': '회차를 골라주세요'}), 400
    try:
        rows = []
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("""
                SELECT timestamp, name, amount, message, source
                FROM donation_archive WHERE session_label = ?
                ORDER BY id ASC
            """), (label,))
            for r in cur.fetchall():
                rows.append({'time': ts_kst(r[0]), 'name': r[1], 'amount': int(r[2] or 0),
                             'message': r[3] or '', 'source': r[4] or ''})
        total = sum(r['amount'] for r in rows)
        cut = len(rows) > ARCHIVE_ROWS_MAX
        if cut:
            rows = rows[:ARCHIVE_ROWS_MAX]
        # ⚠️ 잘랐으면 반드시 알려준다. 말없이 자르면 '이게 전부' 로 읽혀 정산이 틀어진다.
        return jsonify({'status': 'success', 'label': label, 'rows': rows,
                        'total': total, 'truncated': cut, 'max': ARCHIVE_ROWS_MAX})
    except Exception as e:
        print(f'[지난 방송 내역 조회 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e), 'rows': []}), 500


@app.route('/api/archive/csv')
def api_archive_csv():
    """엑셀로 내려받기. ?label=... 없으면 전체."""
    from flask import Response
    label = (request.args.get('label') or '').strip()
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            if label:
                cur.execute(db_query("""
                    SELECT session_label, timestamp, name, amount, message, source
                    FROM donation_archive WHERE session_label = ? ORDER BY id ASC
                """), (label,))
            else:
                cur.execute(db_query("""
                    SELECT session_label, timestamp, name, amount, message, source
                    FROM donation_archive ORDER BY id ASC
                """))
            data = cur.fetchall()
        lines = ['회차,시각,후원자,금액,메시지,경로']
        for r in data:
            # ⚠️ 두 번째 칸이 시각이다. 한국 시각으로 옮겨 내보낸다 — 엑셀을 열어
            #    정산할 때 9시간 뒤처진 시각이 나오면 어느 방송분인지 헷갈린다.
            #    (첫 칸 session_label 은 회차 이름이라 그대로 둔다)
            _r = list(r); _r[1] = ts_kst(_r[1])
            lines.append(','.join(_csv_cell(x) for x in _r))
        # ⚠️ 앞에 BOM 을 붙인다. 없으면 엑셀이 UTF-8 을 못 알아채고 한글이 전부 깨진다.
        body = '\ufeff' + '\r\n'.join(lines) + '\r\n'
        stamp = time.strftime('%Y%m%d_%H%M%S',
                              time.localtime(time.time() + _bc_shift_hours() * 3600))
        fname = f'donations_{stamp}.csv'
        # ⚠️ mimetype 에 charset 을 적으면 Flask 가 뒤에 또 붙여 두 번 들어간다.
        #    content_type 으로 통째로 지정한다.
        return Response(body.encode('utf-8'), content_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename="{fname}"'})
    except Exception as e:
        print(f'[지난 방송 내려받기 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500
