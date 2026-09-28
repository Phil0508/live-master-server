# -*- coding: utf-8 -*-
"""➕ 점수 넣기 — 후원판 점수를 선수 · 팀에 올리고, 대결 점수로 잇는다.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import time
from flask import jsonify, request
from server import (
    LOG_MAX, app, broadcast_event, file_lock, load_data, now_hms, remember_assignment,
    save_data,
)


def _match_team_of(state, member_name):
    """그 사람이 속한 대결 팀을 돌려준다. 팀전이 꺼져 있거나 소속이 없으면 None.

    ⚠️ 이름 비교는 양쪽 모두 공백을 떼고 한다. 팀원 이름은 점수판에서 골라 넣지만,
       나중에 점수판에서 이름을 고치면 팀원 목록에는 옛 이름이 남는다.
       그때는 조용히 합산이 멈춘다 — 조종실이 그 사실을 보여준다(팀원 칸에 회색 표시).
    """
    md = state.get('match_data') or {}
    if not md.get('active') or not md.get('team_mode'):
        return None
    want = str(member_name or '').strip()
    if not want:
        return None
    for team in (md.get('players') or []):
        for m in (team.get('members') or []):
            if str(m or '').strip() == want:
                return team
    return None


def _find_score_target(state, scope, name):
    """점수를 더할 대상 하나를 찾는다. 언제나 '이름'으로 찾는다 —
       랭킹은 기여도순으로 계속 재정렬되므로 위치 인덱스로 찾으면 엉뚱한 사람에게 돈이 들어간다.

    ⚠️ 이름을 비교할 때 양쪽 모두 앞뒤 공백을 뗀다.
       들어온 이름은 위에서 이미 strip 되는데 저장된 이름은 안 됐다. 그래서 이름 칸에
       공백을 하나만 더 눌러도('밍밍 ') 그 사람은 그때부터 점수를 받을 수 없었다.
       화면에는 '밍밍' 으로 멀쩡히 보이니 원인을 찾을 수도 없다.
       대결·점수판 양쪽 모두에서 재현된다.
    """
    want = str(name or '').strip()

    def same(v):
        return str(v or '').strip() == want

    if scope == 'bot':
        return state.get('bottom_fixed')
    if scope == 'jar':
        return state.get('fundjar')
    if scope == 'match':
        md = state.get('match_data') or {}
        return next((p for p in (md.get('players') or []) if same(p.get('name'))), None)
    src = 'extra_bjs' if state.get('extra_game_active') else 'bjs'
    return next((b for b in (state.get(src) or []) if same(b.get('name'))), None)


@app.route('/api/score/add', methods=['POST'])
def api_score_add():
    """점수는 '더할 값'만 받아서 서버가 읽고-더하고-쓴다.

    ⚠️ 이 엔드포인트가 생긴 이유:
       폰(mobile.html)과 조종실은 둘 다 '상태 전체'를 POST 했고, /api/data 는 필드를 통째로
       교체한다(state.update). 그래서 같은 스냅샷을 들고 각자 점수를 더해 보내면 나중에 도착한
       쪽이 앞선 점수를 덮어썼다. 부하 테스트에서 동시 배정 12건 중 6건이 사라졌다.
       위험 구간은 SSE 전파 지연만큼인데 Render 실측이 약 0.5초라 사람이 충분히 부딪힌다.
       (자리 비운 사이 폰으로 배정하는데 PC 에서 오토파일럿이 돌고 있으면 정확히 그 조건이다)
       여기서는 스냅샷을 주고받지 않으므로 두 조작이 겹쳐도 둘 다 남는다.

    pending_id 를 함께 주면 '점수 지급'과 '대기함에서 제거'가 같은 잠금 안에서 끝난다.
    예전에는 왕복 두 번이라 그 사이에 실패하면 후원이 어디에도 없는 상태가 될 수 있었다.
    그 후원이 대기함에 이미 없으면 누군가 먼저 처리한 것이므로 점수를 더하지 않고
    already=True 로 답한다 — 폰과 PC 에서 같은 후원을 동시에 눌러도 두 번 들어가지 않는다.

    items 로 여러 명을 한 번에 줄 수 있다(반반·N분할). 한 명이라도 못 찾으면 아무것도 반영하지 않는다.
    """
    try:
        body = request.get_json(silent=True) or {}
        # scope 가 숫자로 오면 .strip() 에서 터진다 — 무엇이 와도 글자로 본다
        scope = str(body.get('scope') or 'rank').strip()
        if scope not in ('rank', 'bot', 'match', 'jar'):
            return jsonify({"status": "error", "message": f"알 수 없는 scope: {scope}"}), 400

        raw = body.get('items') or [{"name": body.get('name'), "delta": body.get('delta'),
                                     "contribution": body.get('contribution')}]
        # 값 검증을 먼저 다 끝낸다 — 절반만 반영되는 일이 없게
        wanted = []
        for it in raw:
            name = str(it.get('name') or '').strip()
            # 운영비·모금함은 통이 하나뿐이라 이름이 필요 없다
            if not name and scope not in ('bot', 'jar'):
                return jsonify({"status": "error", "message": "name 이 비어 있다"}), 400
            try:
                delta = int(it.get('delta') or 0)
                contrib = delta if it.get('contribution') is None else int(it.get('contribution'))
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "delta/contribution 이 숫자가 아니다"}), 400
            wanted.append((name, delta, contrib))

        # 🧠 이 후원이 누구에게 갔는지 기억해 둔다(다음 판단의 재료).
        #    조종실·폰이 배정할 때 donor 를 같이 보낸다. 없으면 그냥 기억하지 않는다.
        donor_name = (body.get('donor') or '').strip()
        donor_msg = (body.get('donor_message') or '').strip()
        want_log = bool(body.get('log', True))
        want_popup = bool(body.get('popup', False))
        want_takeover = bool(body.get('takeover', False))
        pending_id = body.get('pending_id')
        undo_log = body.get('undo_log')

        with file_lock:
            state = load_data()
            # 🛡️ 같은 후원을 두 곳에서 동시에 배정하면 점수가 두 번 들어간다.
            #    조종실도 '이미 처리됐나' 를 보지만 그건 각자 화면의 사본이라, 폰과 PC 가
            #    서로를 못 본다. 대기함에 그 후원이 남아 있는지는 서버만 확실히 안다.
            #    이미 없으면 '누군가 먼저 처리했다' 는 뜻이므로 점수를 더하지 않는다.
            if pending_id:
                _pend = state.get('pending_donations') or []
                if not any(d.get('id') == pending_id for d in _pend):
                    print(f'  ↩️ [이중 배정 방지] 이미 처리된 후원입니다 ({pending_id})', flush=True)
                    return jsonify({'status': 'success', 'already': True,
                                    'message': '이미 다른 기기에서 처리된 후원입니다'})
            src = 'extra_bjs' if state.get('extra_game_active') else 'bjs'
            prev_first = None
            if scope == 'rank':
                lst = state.get(src) or []
                prev_first = (lst[0].get('name') if lst else None)

            # ⚠️ 대상을 '전부 찾은 뒤에' 더한다. load_data() 는 살아 있는 메모리 상태를 돌려주므로,
            #    더하다가 중간에 빠져나가면 저장을 건너뛰어도 앞사람 점수는 이미 올라가 있다.
            #    (반반 지급에서 두 번째 이름이 오타일 때 첫 사람만 점수를 받는 사고가 난다)
            targets = []
            for name, delta, contrib in wanted:
                t = _find_score_target(state, scope, name)
                if t is None:
                    return jsonify({"status": "error",
                                    "message": f"'{name}' 을(를) 찾을 수 없습니다"}), 404
                targets.append((t, delta, contrib, t.get('name') or name))

            applied = []
            team_hits = []
            for t, delta, contrib, tname in targets:
                t['score'] = (t.get('score') or 0) + delta
                if scope == 'rank':
                    t['contribution'] = (t.get('contribution') or 0) + contrib
                    # ⚔️ 팀전: 이 사람이 어느 팀 소속이면 그 팀 점수도 같이 올린다.
                    #    대결판이 후원을 따라 실시간으로 움직여야 보는 재미가 있다.
                    team = _match_team_of(state, tname) if delta else None
                    if team is not None:
                        team['score'] = (team.get('score') or 0) + delta
                        team_hits.append((team.get('name'), tname, delta))
                applied.append({"name": tname, "delta": delta, "contrib": contrib,
                                "score": t.get('score'), "contribution": t.get('contribution')})
            for tn, mn, dv in team_hits:
                print(f"  ⚔️ [팀전] {mn} 의 {dv:+d} 점이 '{tn}' 팀 점수에도 반영됐습니다", flush=True)

            time_str = now_hms()
            log_key = 'match_logs' if scope == 'match' else 'logs'
            logs = state.get(log_key)
            if not isinstance(logs, list):
                logs = []
            state[log_key] = logs
            if want_log:
                _reason = str(body.get('reason') or '')[:80]
                for a in applied:
                    # 🧾 기여도만 움직인 것은 기여도로 적는다.
                    #    ⚠️ 예전에는 delta 만 적어서, 기여도를 손으로 고치면 '0점' 이라는
                    #       쓸모없는 줄이 남았다(그나마도 log:false 라 아예 안 남겼다).
                    #       그래서 나중에 "이 사람 기여도가 왜 이렇지" 를 되짚을 수 없었다.
                    if not a['delta'] and a.get('contrib'):
                        logs.insert(0, {"time": time_str, "name": a['name'],
                                        "val": a['contrib'], "kind": "contrib",
                                        "why": _reason or '조종실에서'})
                    else:
                        logs.insert(0, {"time": time_str, "name": a['name'], "val": a['delta']})
            # 되돌리기: '-3점' 줄을 새로 남기는 대신 원래 줄을 지운다(장부가 깔끔하게 남는다).
            # 반반·N분할을 되돌릴 때는 지울 줄이 여러 개라 목록도 받는다.
            for u in ([undo_log] if isinstance(undo_log, dict) else (undo_log or [])):
                for i, l in enumerate(logs):
                    if (l.get('time') == u.get('time') and l.get('name') == u.get('name')
                            and l.get('val') == u.get('val')):
                        del logs[i]
                        break
            del logs[LOG_MAX:]

            if want_popup:
                top = max(applied, key=lambda a: a['delta'])
                if top['delta'] > 0:
                    state['latest_popup'] = {"time": int(time.time() * 1000),
                                             "name": top['name'], "diff": top['delta']}

            if scope == 'rank':
                lst = state.get(src) or []
                lst.sort(key=lambda b: -(b.get('contribution') or 0))
                state[src] = lst
                if want_takeover and prev_first and lst:
                    curr = lst[0].get('name')
                    gained = {a['name'] for a in applied if a['delta'] > 0}
                    if curr and curr != prev_first and curr in gained:
                        state['latest_takeover'] = {"time": int(time.time() * 1000), "name": curr}

            if pending_id:
                # 💥 배정한 후원이 '한 방 최고 후원' 이면 **받은 멤버**를 붙인다
                #    (XL 방송판처럼 '누가 · 누구에게 · 얼마' 가 한 번에 보이게)
                try:
                    _bs = state.get('best_single') or {}
                    if _bs.get('id') and _bs.get('id') == pending_id:
                        _who = [a.get('name') for a in applied if a.get('name')]
                        _label = {'jar': '🏺 기여도 상금', 'bot': '운영비'}.get(scope)
                        _bs = dict(_bs)
                        _bs['member'] = _label or ' · '.join(_who[:3])
                        state['best_single'] = _bs
                except Exception as _e:
                    print(f"⚠️ [한 방 최고 후원 멤버 붙이기 실패] {_e}")
                pend = state.get('pending_donations') or []
                state['pending_donations'] = [d for d in pend if d.get('id') != pending_id]

            save_data(state)
            broadcast_event('update', state)

        # ⚠️ 기억은 락 밖에서 적는다. DB 왕복이라 락 안에서 하면 그동안 후원 접수가 멈춘다.
        #    되돌리기(delta<0)는 기억하지 않는다 — 취소한 것을 배운 것으로 쌓으면 오히려 나빠진다.
        if donor_name and scope == 'rank':
            for a in applied:
                if (a.get('delta') or 0) > 0:
                    remember_assignment(donor_name, a['name'], a.get('delta'), donor_msg)
        return jsonify({"status": "success", "applied": applied, "time": time_str})
    except Exception as e:
        print(f"Error in api_score_add: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
