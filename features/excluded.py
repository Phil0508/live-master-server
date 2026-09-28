# -*- coding: utf-8 -*-
"""🚫 순위에서 뺄 이름.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import time
from flask import jsonify, request
from server import (
    IS_POSTGRES, _norm_donor, app, broadcast_event, db_query, file_lock, get_db_connection,
    load_data, request_is_authed, save_data,
)


# ==========================================
# 🚫 순위에서 뺄 이름
#    익명·테스트처럼 명단에 넣으면 안 되는 이름을 사장님이 직접 고른다.
#    ⚠️ 후원 기록은 안 지운다. 돈은 장부에 그대로 있고 순위에서만 안 보인다.
# ==========================================
# ⚠️ 후원이 들어올 때마다 이 표를 뒤지면 안 된다. 후원 경로는 제일 바쁜 길이고
#    Postgres 왕복이 40ms 다. 한 번 읽어 기억해 두고, 바뀔 때만 버린다.
_excluded_cache = {'set': None}


def _excluded_invalidate():
    _excluded_cache['set'] = None


def excluded_names():
    """순위에서 뺄 이름들(다듬은 형태).

    ⚠️ 못 읽으면 빈 집합으로 넘어간다. 명단이 조금 지저분해질 뿐이지, 여기서
       터져서 후원 받는 길이 막히면 그게 훨씬 큰 사고다.
    """
    if _excluded_cache['set'] is not None:
        return _excluded_cache['set']
    out = set()
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("SELECT name FROM donor_excluded"))
            out = {str(r[0] or '') for r in cur.fetchall() if r and r[0]}
    except Exception as e:
        print(f'[제외 명단 조회 실패 — 빈 목록으로 진행] {e}')
    _excluded_cache['set'] = out
    return out


def is_excluded(name):
    """이 이름은 명단에서 빼야 하는가. '익명' 은 언제나 뺀다 — 사람이 아니다."""
    who = _norm_donor(name)
    return (not who) or who == '익명' or who in excluded_names()


def _tally_restore_from_ledger(who):
    """순위에서 뺐다가 되돌린 사람의 이번 방송 합계를 장부에서 다시 세어 순위판에 올린다.
    ⚠️ 장부는 읽기만 한다 — 후원 기록을 지우거나 고치는 곳이 아니다."""
    with file_lock:
        state = load_data()
        tot, cnt, shown = 0, 0, ''
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("SELECT name, amount FROM donation_history"))
            for nm, amt in cur.fetchall():
                if _norm_donor(nm) == who and int(amt or 0) > 0:
                    tot += int(amt or 0)
                    cnt += 1
                    shown = shown or ' '.join(str(nm or '').split())
        if tot > 0:
            state.setdefault('donor_tally', {})[who] = {'total': tot, 'count': cnt, 'name': shown or who}
            save_data(state)
            broadcast_event('update', state)


@app.route('/api/donors/excluded', methods=['GET'])
def api_excluded_list():
    if not request_is_authed():
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query(
                "SELECT name, memo, added_at FROM donor_excluded ORDER BY added_at DESC"))
            rows = [{'name': r[0], 'memo': r[1] or '', 'added_at': r[2] or ''}
                    for r in cur.fetchall()]
        return jsonify({'status': 'success', 'rows': rows})
    except Exception as e:
        print(f'[제외 명단 조회 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e), 'rows': []}), 500


@app.route('/api/donors/excluded', methods=['POST'])
def api_excluded_add():
    if not request_is_authed():
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    who = _norm_donor(data.get('name'))
    if not who or who == '익명':
        return jsonify({'status': 'error', 'message': '이름이 없습니다.'}), 400
    memo = str(data.get('memo') or '')[:200]
    try:
        stamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with get_db_connection() as conn:
            cur = conn.cursor()
            if IS_POSTGRES:
                cur.execute("""
                    INSERT INTO donor_excluded (name, memo, added_at) VALUES (%s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET memo = EXCLUDED.memo
                """, (who, memo, stamp))
            else:
                cur.execute("INSERT OR REPLACE INTO donor_excluded (name, memo, added_at)"
                            " VALUES (?, ?, ?)", (who, memo, stamp))
        _excluded_invalidate()
        # ⚠️ 이번 방송 순위판에 이미 올라가 있으면 지금 내려준다. 안 그러면 [빼기] 를
        #    눌러도 방송 화면에는 그대로 남아 있어 안 된 줄 안다.
        with file_lock:
            state = load_data()
            if (state.get('donor_tally') or {}).pop(who, None) is not None:
                save_data(state)
                broadcast_event('update', state)
        print(f'  🚫 [순위에서 빼기] {who}' + (f' ({memo})' if memo else ''))
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f'[제외 명단 저장 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/donors/excluded', methods=['DELETE'])
def api_excluded_remove():
    if not request_is_authed():
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    who = _norm_donor(request.args.get('name'))
    if not who:
        return jsonify({'status': 'error', 'message': '이름이 없습니다.'}), 400
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("DELETE FROM donor_excluded WHERE name = ?"), (who,))
        _excluded_invalidate()
        # ↩️ 이번 방송 순위판에도 되돌린다 — 뺄 때 순위판에서 내렸으므로 이번 방송 장부에서
        #    다시 센다. 안 그러면 되돌려도 순위(= 등급)에 안 나온다. (읽기만 한다)
        try:
            _tally_restore_from_ledger(who)
        except Exception as _e:
            print(f'⚠️ [다시 넣기] 순위판 복구 실패(계속합니다): {_e}')
        print(f'  ↩️ [다시 넣기] {who}')
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f'[제외 명단 삭제 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500
