# -*- coding: utf-8 -*-
"""🚫 순위에서 뺄 이름.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import time
from flask import jsonify, request
from server import (
    IS_POSTGRES, NOTICE_DONOR_NAME_MAX, _norm_donor, app, broadcast_event, db_query, file_lock,
    get_db_connection, load_data, request_is_authed, save_data,
)


# ==========================================
# 🚫 순위에서 뺄 이름
#    익명·테스트처럼 명단에 넣으면 안 되는 이름을 사장님이 직접 고른다.
#    ⚠️ 후원 기록은 안 지운다. 돈은 장부에 그대로 있고 순위에서만 안 보인다.
# ==========================================
# ⚠️ 후원이 들어올 때마다 이 표를 뒤지면 안 된다. 후원 경로는 제일 바쁜 길이고
#    Postgres 왕복이 40ms 다. 한 번 읽어 기억해 두고, 바뀔 때만 버린다.
_excluded_cache = {'set': None, 'retry_at': 0.0}
# ⚠️ 못 읽었을 때 빈 집합을 **잠깐만** 기억한다. 예전에는 한 번 실패하면 빈 집합을 영원히 들고 있어서
#    (다시 뺄 때까지) 뺀 이름이 조용히 순위 · 한 방 최고 · 전광판에 다시 올라갔다.
#    Supabase 는 유휴 커넥션을 끊어 조용한 구간 뒤 첫 조회가 실패하는 일이 실제로 있다.
#    그렇다고 매번 다시 묻으면 DB 가 죽었을 때 후원마다 왕복을 기다린다 — 그래서 몇 초 간격으로만 다시 본다.
_EXCLUDED_RETRY_SEC = 5.0


def _excluded_invalidate():
    _excluded_cache['set'] = None
    _excluded_cache['retry_at'] = 0.0


def excluded_names():
    """순위에서 뺄 이름들(다듬은 형태).

    ⚠️ 못 읽으면 빈 집합으로 넘어간다. 명단이 조금 지저분해질 뿐이지, 여기서
       터져서 후원 받는 길이 막히면 그게 훨씬 큰 사고다. (실패는 잠깐만 기억한다 — 위 설명)
    """
    if _excluded_cache['set'] is not None:
        if not _excluded_cache['retry_at'] or time.time() < _excluded_cache['retry_at']:
            return _excluded_cache['set']
    out = set()
    failed = False
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("SELECT name FROM donor_excluded"))
            out = {str(r[0] or '') for r in cur.fetchall() if r and r[0]}
    except Exception as e:
        failed = True
        print(f'[제외 명단 조회 실패 — 빈 목록으로 진행, {_EXCLUDED_RETRY_SEC:.0f}초 뒤 다시 읽습니다] {e}')
    _excluded_cache['set'] = out
    _excluded_cache['retry_at'] = (time.time() + _EXCLUDED_RETRY_SEC) if failed else 0.0
    return out


def is_excluded(name):
    """이 이름은 명단에서 빼야 하는가. '익명' 은 언제나 뺀다 — 사람이 아니다."""
    who = _norm_donor(name)
    return (not who) or who == '익명' or who in excluded_names()


def _ledger_rows():
    """이번 방송 장부의 (이름, 금액) — 들어온 순서대로. ⚠️ 읽기만 한다."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(db_query("SELECT name, amount FROM donation_history ORDER BY id"))
        return [(nm, int(amt or 0)) for nm, amt in cur.fetchall()]


def _best_from_rows(state, rows):
    """장부로 '한 방 최고 후원' 을 다시 고른다. 없으면 None.
    ⚠️ 규칙은 후원 접수(features/donation.py)와 똑같다 — 빼둔 이름은 안 치고(익명은 친다),
       같은 금액이면 **먼저 보낸 분**(장부 id 가 작은 쪽)이 지킨다."""
    ex = excluded_names()
    top = None
    for nm, amt in rows:
        if amt > 0 and _norm_donor(nm) not in ex and (top is None or amt > top[1]):
            top = (nm, amt)
    if top is None:
        return None
    shown = ' '.join(str(top[0] or '').split()) or '익명'
    # 아직 대기함에 있으면 그 줄 번호를 붙인다 — 조종실이 배정할 때 '받은 멤버' 가 붙게(features/score.py)
    pid = None
    for p in (state.get('pending_donations') or []):
        if (isinstance(p, dict) and _norm_donor(p.get('name')) == _norm_donor(top[0])
                and int(p.get('amount') or 0) == top[1]):
            pid = p.get('id')
            break
    # ⚠️ at 은 0 으로 둔다. 방송판은 at 이 바뀌면 '최고 기록 갱신!' 을 터뜨리는데(overlay renderBest),
    #    이건 갱신이 아니라 **뺀 사람을 내린 것**이라 연출이 나가면 거짓말이 된다. at 이 0 이면 연출을 안 한다.
    #    다음 진짜 갱신(후원 접수)은 새 at 을 적으므로 그때는 정상으로 터진다.
    return {'name': shown, 'amount': top[1], 'at': 0, 'id': pid, 'member': ''}


def _drop_from_records(state, who):
    """순위에서 뺀 이름을 '한 방 최고' · 전광판 소액 목록에서도 내린다. 바뀌었으면 True.
    ⚠️ 예전에는 donor_tally 만 내려서, 뺀 이름(테스트 후원 등)이 '한 방 최고' 에 계속 떠 있었고
       그 금액이 기준으로 남아 **진짜 후원자의 더 작은 한 방이 기록을 못 가져갔다**.
    ⚠️ 이름 비교는 is_excluded 와 같은 _norm_donor 로 한다('별빛님' 으로 빼도 '별빛' 이 빠진다)."""
    changed = False
    bs = state.get('best_single') or {}
    if int(bs.get('amount') or 0) > 0 and _norm_donor(bs.get('name')) == who:
        try:
            new = _best_from_rows(state, _ledger_rows())
        except Exception as e:
            # 장부를 못 읽으면 비운다 — 뺀 이름을 계속 띄우는 것보다 '아직 없음' 이 낫다. 다음 후원이 다시 채운다.
            print(f'⚠️ [순위에서 빼기] 장부를 못 읽어 한 방 최고를 비웁니다: {e}')
            new = None
        state['best_single'] = new or {"name": "", "amount": 0, "at": 0, "id": None, "member": ""}
        changed = True
    nd = state.get('notice_donors')
    if isinstance(nd, list):
        # 전광판 쪽 이름은 별표를 떼고 길이를 잘라 적었다(features/donation.py) — 같은 모양으로 맞춰 비교한다
        cut = _norm_donor(who.replace('*', '')[:NOTICE_DONOR_NAME_MAX])
        keep = [e for e in nd if not (isinstance(e, dict)
                                      and _norm_donor(e.get('name')) in (who, cut))]
        if len(keep) != len(nd):
            state['notice_donors'] = keep
            changed = True
    return changed


def _tally_restore_from_ledger(who):
    """순위에서 뺐다가 되돌린 사람의 이번 방송 합계를 장부에서 다시 세어 순위판에 올린다.
    ⚠️ 장부는 읽기만 한다 — 후원 기록을 지우거나 고치는 곳이 아니다."""
    with file_lock:
        state = load_data()
        tot, cnt, shown = 0, 0, ''
        rows = _ledger_rows()
        for nm, amt in rows:
            if _norm_donor(nm) == who and amt > 0:
                tot += amt
                cnt += 1
                shown = shown or ' '.join(str(nm or '').split())
        changed = False
        if tot > 0:
            state.setdefault('donor_tally', {})[who] = {'total': tot, 'count': cnt, 'name': shown or who}
            changed = True
        # 💥 되돌린 사람의 한 방이 지금 기록보다 **크면** 기록도 돌려준다.
        #    ⚠️ '크다' 일 때만 — 장부가 비었거나 못 읽은 것을 '기록 없음' 으로 착각해 멀쩡한 기록을 지우면 안 된다.
        try:
            best = _best_from_rows(state, rows)
            if best and _norm_donor(best['name']) == who and \
                    best['amount'] > int((state.get('best_single') or {}).get('amount') or 0):
                state['best_single'] = best
                changed = True
        except Exception as _e:
            print(f'⚠️ [다시 넣기] 한 방 최고 다시 고르기 실패(계속합니다): {_e}')
        if changed:
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
        #    ⚠️ 순위판만이 아니라 '한 방 최고' · 전광판 소액 목록에서도 내린다(_drop_from_records 설명).
        with file_lock:
            state = load_data()
            _gone = (state.get('donor_tally') or {}).pop(who, None) is not None
            if _drop_from_records(state, who) or _gone:
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
