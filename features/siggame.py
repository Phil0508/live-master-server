# -*- coding: utf-8 -*-
"""🃏 시그 뒤집기 게임.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import copy
import math
import random
import show as showmod
import time
from flask import jsonify, request
import server  # 연습 서버가 가짜로 바꿔 끼우는 시그니처 조회는 부를 때마다 server 에서 찾는다
from server import (
    DEFAULT_STATE, _clip_log, _clip_state, _stage_log, app, broadcast_event, file_lock,
    load_data, save_data,
)


# ==========================================
# 🃏 시그 뒤집기 게임
# ==========================================
# 규칙: 시그니처를 덮어 깔고, 그중 몇 장(기본 5장)을 뒤집는다.
#       뒤집힌 것이 이번 판의 '목표'이고, 제한 시간 안에 그 시그니처를 후원으로 받아내면 달성이다.
#
# ⚠️ 달성 표시는 전부 사람이 누른다. 후원이 들어올 때 자동으로 찍지 않는다 —
#    후원은 즉시 접수되지만 시그니처는 대기열에 쌓였다가 나중에 재생되기 때문에,
#    자동으로 찍으면 아직 화면에 나오지도 않은 시그니처가 이미 달성된 것처럼 보인다.
#    타이밍은 진행자가 잡아야 연출이 산다.
#
# 상태는 전부 서버가 들고 SSE 로 뿌린다. 원본 프로그램은 창끼리 localStorage 로 맞췄는데,
# OBS 브라우저 소스는 조종실 크롬과 저장소를 공유하지 않아 애초에 동기화가 되지 않았다.
SIGGAME_MAX_CARDS = 36   # 6x6. 이보다 크면 상태가 무거워지고 OBS 가 버벅인다.


def _siggame_state(state):
    """항상 온전한 모양의 게임 상태를 돌려준다(예전 저장본에 없던 키 보정)."""
    g = state.get('siggame')
    if not isinstance(g, dict):
        g = copy.deepcopy(DEFAULT_STATE['siggame'])
        state['siggame'] = g
    for k, v in DEFAULT_STATE['siggame'].items():
        g.setdefault(k, copy.deepcopy(v))
    if not isinstance(g.get('timer'), dict):
        g['timer'] = copy.deepcopy(DEFAULT_STATE['siggame']['timer'])
    for k in ('cards', 'picks'):
        if not isinstance(g.get(k), list):
            g[k] = []
    return g


def _siggame_save(state, g):
    state['siggame'] = g
    save_data(state)
    broadcast_event('update', state)


@app.route('/api/siggame/picks', methods=['POST'])
def api_siggame_picks():
    """이번 판에 깔 시그니처를 고른다.

    body: {"picks": [12345, 12346, ...]}   (시그니처 id 목록)
    ⚠️ 여기에는 감출 것이 없다. 어느 카드가 무엇인지는 '깔고 나서' 감춰진다(mask_siggame).
    """
    data = request.get_json(silent=True) or {}
    ids = data.get('picks')
    if not isinstance(ids, list) or not ids:
        return jsonify({"status": "error", "message": "시그니처를 하나 이상 골라주세요"}), 400
    if len(ids) > SIGGAME_MAX_CARDS:
        return jsonify({"status": "error",
                        "message": "카드는 최대 %d장까지입니다 (지금 %d장)"
                                   % (SIGGAME_MAX_CARDS, len(ids))}), 400

    by_id = {int(s['id']): s for s in (server.supabase_list_signatures() or []) if s.get('id') is not None}
    picks, missing = [], []
    for raw_id in ids:
        try:
            sid = int(raw_id)
        except (TypeError, ValueError):
            continue
        s = by_id.get(sid)
        if not s:
            missing.append(sid)
            continue
        picks.append({"sig_id": sid, "title": s.get('title') or '',
                      "image": s.get('image_url') or '', "amount": s.get('amount')})
    if not picks:
        return jsonify({"status": "error", "message": "고른 시그니처를 찾을 수 없습니다"}), 400

    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        g['picks'] = picks
        _siggame_save(state, g)
    if missing:
        print("⚠️ [시그게임] 고른 시그니처 %d장을 찾을 수 없어 뺐습니다: %s" % (len(missing), missing), flush=True)
    print("🃏 [시그게임] 시그니처 %d장 선택" % len(picks), flush=True)
    return jsonify({"status": "success", "count": len(picks), "missing": missing,
                    "requested": len(ids)})


@app.route('/api/siggame/deal', methods=['POST'])
def api_siggame_deal():
    """고른 시그니처를 무작위 자리에 깔고 전부 덮는다."""
    data = request.get_json(silent=True) or {}
    try:
        minutes = max(0, min(180, int(data.get('minutes', 10))))
    except (TypeError, ValueError):
        minutes = 10

    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        picks = list(g.get('picks') or [])
        if not picks:
            return jsonify({"status": "error",
                            "message": "먼저 시그니처를 골라주세요 (아래 목록에서 선택)"}), 400
        try:
            target = int(data.get('target', g.get('target') or 5))
        except (TypeError, ValueError):
            target = 5
        target = max(1, min(len(picks), target))

        random.shuffle(picks)   # 자리를 섞는다 — 번호만 보고는 무엇인지 알 수 없어야 한다
        n = len(picks)
        cols = int(math.ceil(math.sqrt(n)))
        rows = int(math.ceil(n / cols))
        g['cards'] = [{"id": i + 1, "sig_id": p.get('sig_id'), "image": p.get('image'),
                       "title": p.get('title'), "amount": p.get('amount'),
                       "state": "HIDDEN", "doneAt": None, "flippedAt": None}
                      for i, p in enumerate(picks)]
        _prev = showmod.ensure(state)['stage']
        showmod.set_stage(state, 'siggame')      # 📺 카드를 깔면 무대를 차지한다
        _stage_log(_prev, 'siggame')
        g.update({"cols": cols, "rows": rows, "enabled": True, "target": target,
                  "compact": False,     # 새 판이면 올린 상태를 푼다
                  "timer": {"status": "STOPPED", "timeLeft": minutes * 60, "expiresAt": None},
                  "action": {"type": "PLACE", "ts": int(time.time() * 1000)}})
        _siggame_save(state, g)
    print("🃏 [시그게임] %d장 배치 (%dx%d, 목표 %d장, %d분)" % (n, cols, rows, target, minutes), flush=True)
    return jsonify({"status": "success", "count": n, "target": target, "cols": cols, "rows": rows})


@app.route('/api/siggame/shuffle', methods=['POST'])
def api_siggame_shuffle():
    """자리를 다시 섞고 전부 덮는다(달성 기록도 초기화된다 — 새 판이나 마찬가지다)."""
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        cards = g.get('cards') or []
        if not cards:
            return jsonify({"status": "error", "message": "먼저 카드를 깔아주세요"}), 400
        faces = [{"sig_id": c.get('sig_id'), "image": c.get('image'),
                  "title": c.get('title'), "amount": c.get('amount')} for c in cards]
        random.shuffle(faces)
        g['cards'] = [{"id": c["id"], "sig_id": f["sig_id"], "image": f["image"],
                       "title": f["title"], "amount": f["amount"],
                       "state": "HIDDEN", "doneAt": None, "flippedAt": None}
                      for c, f in zip(cards, faces)]
        g['compact'] = False        # 섞으면 목표가 사라지므로 올린 상태도 푼다
        g['action'] = {"type": "SHUFFLE", "ts": int(time.time() * 1000),
                       "animIndex": random.randint(1, 4)}
        n = len(cards)
        _siggame_save(state, g)
    print("🃏 [시그게임] 카드 %d장 다시 섞음" % n, flush=True)
    return jsonify({"status": "success"})


@app.route('/api/siggame/flip', methods=['POST'])
def api_siggame_flip():
    """카드 한 장을 뒤집는다. 뒤집힌 카드가 이번 판의 '목표'가 된다.

    ⚠️ 목표 장수(target)를 넘겨 뒤집지 못하게 막는다. 실수로 하나 더 뒤집으면
       참가자가 받아야 할 금액이 늘어난다 — 돈이 걸린 문제라 되돌리기보다 막는 쪽이 낫다.
    ⚠️ '크게 보이는 2초'는 서버 상태로 두지 않는다. 요청이 실패하거나 조종실이 닫혔을 때
       카드가 확대된 채 방송에 박히기 때문이다. 뒤집은 시각만 남기고 연출은 화면이 판단한다.
    """
    data = request.get_json(silent=True) or {}
    try:
        cid = int(data.get('id'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "카드 번호가 필요합니다"}), 400
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        cards = g.get('cards') or []
        found = next((c for c in cards if c.get('id') == cid), None)
        if not found:
            return jsonify({"status": "error", "message": "%d번 카드가 없습니다" % cid}), 404
        if found.get('state') == 'REVEALED':
            return jsonify({"status": "success", "id": cid, "already": True,
                            "title": found.get('title') or ''})
        opened = sum(1 for c in cards if c.get('state') == 'REVEALED')
        target = int(g.get('target') or 5)
        if opened >= target:
            return jsonify({"status": "error",
                            "message": "이미 %d장을 뒤집었습니다 (목표 %d장)" % (opened, target)}), 400
        found['state'] = 'REVEALED'
        found['flippedAt'] = now_ms
        g['action'] = {"type": "FLIP", "ts": now_ms, "id": cid}
        title = found.get('title') or ''
        amount = found.get('amount')
        left = target - (opened + 1)
        _siggame_save(state, g)
    # ⚠️ 여기서 예외가 나면 이미 저장·전파가 끝난 뒤라, 카드는 뒤집혔는데 조종실엔 500 이 뜬다.
    #    금액이 숫자가 아니어도 로그 한 줄 때문에 요청이 실패하면 안 된다.
    try:
        amount_txt = format(int(amount or 0), ',')
    except (TypeError, ValueError):
        amount_txt = str(amount)
    print("🃏 [시그게임] %d번 뒤집음 → '%s' (%s원) / 더 뒤집을 수 있는 카드 %d장"
          % (cid, title, amount_txt, left), flush=True)
    return jsonify({"status": "success", "id": cid, "title": title,
                    "amount": amount, "remaining_flips": left})


@app.route('/api/siggame/done', methods=['POST'])
def api_siggame_done():
    """목표 카드를 손으로 달성/취소 처리한다.

    ⚠️ 달성은 전부 이 경로로만 찍힌다. 후원이 들어올 때 자동으로 찍지 않는다 —
       후원은 즉시 접수되지만 시그니처는 대기열에 쌓였다가 나중에 재생되므로,
       자동으로 찍으면 아직 화면에 안 나온 시그니처가 이미 달성된 것처럼 보인다.
    """
    data = request.get_json(silent=True) or {}
    try:
        cid = int(data.get('id'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "카드 번호가 필요합니다"}), 400
    want = data.get('done')
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        found = next((c for c in (g.get('cards') or []) if c.get('id') == cid), None)
        if not found:
            return jsonify({"status": "error", "message": "%d번 카드가 없습니다" % cid}), 404
        if found.get('state') != 'REVEALED':
            return jsonify({"status": "error", "message": "아직 뒤집지 않은 카드입니다"}), 400
        done = (not found.get('doneAt')) if want is None else bool(want)
        found['doneAt'] = now_ms if done else None
        g['action'] = {"type": "DONE", "ts": now_ms, "id": cid} if done else None
        _siggame_save(state, g)
    return jsonify({"status": "success", "id": cid, "done": done})


@app.route('/api/siggame/allclear', methods=['POST'])
def api_siggame_allclear():
    """남은 목표를 전부 달성 처리하고 올클리어 연출을 터뜨린다 — '한 방' 버튼.

    ⚠️ 다 채웠다고 자동으로 터지지는 않는다. 언제 터뜨릴지는 진행자가 정한다.
       그리고 하나씩 채우다 누르는 게 아니라, '한 번에 몰아서 쏜' 후원이 들어왔을 때
       목표를 일일이 찍을 겨를이 없으니 버튼 하나로 남은 것까지 전부 채우면서 터뜨린다.
       (예전에는 다 채워야만 눌렸는데, 정작 이 연출이 필요한 순간은 한 방에 다 채운
        순간이라 진행자가 5장을 급하게 하나씩 찍고 있어야 했다)
    """
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        goals = [c for c in (g.get('cards') or []) if c.get('flippedAt')]
        if not goals:
            return jsonify({"status": "error", "message": "뒤집은 카드가 없습니다"}), 400
        now_ms = int(time.time() * 1000)
        left = [c for c in goals if not c.get('doneAt')]
        for c in left:
            c['doneAt'] = now_ms
        g['action'] = {"type": "ALLCLEAR", "ts": now_ms, "count": len(goals)}
        n, filled = len(goals), len(left)
        try:
            if _clip_state(state).get('auto'):
                _clip_log(state, 'auto', '시그뒤집기 올클리어 (%d장)' % n, ref='allclear:%d' % now_ms)
        except Exception as e:
            print(f"⚠️ [클립 목록 실패] {e}")
        _siggame_save(state, g)
    print("🎉 [시그게임] 올클리어! (%d장, 이번에 채운 %d장)" % (n, filled), flush=True)
    return jsonify({"status": "success", "count": n, "filled": filled})


# 한 줄에 나란히 세워도 카드가 알아볼 만한 최대 장수.
# 6칸부터는 폭이 6등분이라 그림도 금액도 작아져서 올리는 의미가 없다.
SIGGAME_LIFT_MAX = 5



@app.route('/api/siggame/lift', methods=['POST'])
def api_siggame_lift():
    """목표만 한 줄로 올리거나(on) 판 전체로 되돌린다(off).

       ⚠️ 예전에는 목표를 다 뒤집는 순간 화면이 저 혼자 올렸다. 진행자가
          멘트를 칠 새도 없이 판이 바뀌고, 되돌릴 방법도 없었다.
          이제 언제 올릴지는 진행자가 정한다.
    """
    data = request.get_json(silent=True) or {}
    want = data.get('on')
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        goals = [c for c in (g.get('cards') or []) if c.get('flippedAt')]
        on = (not g.get('compact')) if want is None else bool(want)
        if on:
            if not goals:
                return jsonify({'status': 'error', 'message': '뒤집은 목표가 없습니다'}), 400
            if len(goals) > SIGGAME_LIFT_MAX:
                return jsonify({'status': 'error',
                                'message': '목표가 %d장이라 올리지 않습니다. 한 줄에 %d장까지만 알아볼 만합니다'
                                           % (len(goals), SIGGAME_LIFT_MAX)}), 400
        g['compact'] = on
        g['action'] = {'type': 'LIFT', 'ts': int(time.time() * 1000), 'on': on}
        _siggame_save(state, g)
    print('🃏 [시그게임] 목표만 올리기 %s (목표 %d장)' % ('켬' if on else '끔', len(goals)), flush=True)
    return jsonify({'status': 'success', 'compact': on, 'goals': len(goals)})


@app.route('/api/siggame/peek', methods=['POST'])
def api_siggame_peek():
    """안 뽑힌 카드가 뭐였는지 잠깐 까본다(목표만 올려둔 상태에서도).

       ⚠️ reveal 과 다르다. reveal 은 판을 영영 열어두는 '게임 끝' 동작이고,
          이건 '나머지 궁금하죠?' 하고 잠깐 보여주는 것이다. 목표 달성 판정과
          무관하도록 flippedAt 은 건드리지 않는다.
    """
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        cards = g.get('cards') or []
        if not cards:
            return jsonify({'status': 'error', 'message': '깔린 카드가 없습니다'}), 400
        rest = [c for c in cards if not c.get('flippedAt')]
        if not rest:
            return jsonify({'status': 'error', 'message': '안 뽑힌 카드가 없습니다'}), 400
        g['action'] = {'type': 'PEEK', 'ts': now_ms, 'count': len(rest)}
        _siggame_save(state, g)
    print('🃏 [시그게임] 나머지 %d장 까보기' % len(rest), flush=True)
    return jsonify({'status': 'success', 'count': len(rest)})


@app.route('/api/siggame/reveal', methods=['POST'])
def api_siggame_reveal():
    """남은 카드를 전부 공개한다(게임이 끝난 뒤 무엇이 있었는지 보여줄 때).

    ⚠️ 이건 '목표 추가'가 아니다. 공개만 하고 달성 판정에는 넣지 않기 위해
       flippedAt 을 남기지 않는다.
    """
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        if not (g.get('cards') or []):
            return jsonify({"status": "error", "message": "깔린 카드가 없습니다"}), 400
        for c in g['cards']:
            if c.get('state') != 'REVEALED':
                c['state'] = 'REVEALED'
                c['flippedAt'] = None   # 목표가 아니라 '구경용 공개'
        g['action'] = {"type": "REVEAL", "ts": now_ms}
        _siggame_save(state, g)
    print("🃏 [시그게임] 남은 카드 전체 공개", flush=True)
    return jsonify({"status": "success"})


@app.route('/api/siggame/timer', methods=['POST'])
def api_siggame_timer():
    """타이머 시작·일시정지·초기화.

    ⚠️ 남은 시간을 서버가 1초씩 세지 않는다. '끝나는 시각'만 두고 화면이 계산한다.
       그래야 오버레이를 새로 띄우거나 늦게 붙어도 시간이 어긋나지 않는다.
    """
    data = request.get_json(silent=True) or {}
    action = str(data.get('action') or '').upper()
    if action not in ('START', 'PAUSE', 'STOP'):
        return jsonify({"status": "error", "message": "action 은 START/PAUSE/STOP"}), 400
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        t = g['timer']
        if action == 'START' and t.get('status') != 'PLAYING':
            left = max(0, int(t.get('timeLeft') or 0))
            if left <= 0:
                return jsonify({"status": "error", "message": "남은 시간이 없습니다"}), 400
            t.update({"status": "PLAYING", "expiresAt": now_ms + left * 1000})
        elif action == 'PAUSE' and t.get('status') == 'PLAYING':
            left = max(0, int(((t.get('expiresAt') or now_ms) - now_ms) / 1000))
            t.update({"status": "PAUSED", "timeLeft": left, "expiresAt": None})
        elif action == 'STOP':
            try:
                minutes = int(data.get('minutes'))
            except (TypeError, ValueError):
                minutes = None
            left = minutes * 60 if minutes is not None else int(t.get('timeLeft') or 0)
            t.update({"status": "STOPPED", "timeLeft": max(0, left), "expiresAt": None})
        timer_out = dict(t)
        _siggame_save(state, g)
    return jsonify({"status": "success", "timer": timer_out})


@app.route('/api/siggame/set', methods=['POST'])
def api_siggame_set():
    """켜기/끄기, 투명도, 목표 장수 같은 설정."""
    data = request.get_json(silent=True) or {}
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        if 'enabled' in data:
            _prev = showmod.ensure(state)['stage']
            if data['enabled']:
                showmod.set_stage(state, 'siggame')
            else:
                showmod.clear_stage(state, 'siggame')
            _stage_log(_prev, state['show']['stage'])
        if 'opacity' in data:
            try:
                g['opacity'] = max(0.1, min(1.0, float(data['opacity'])))
            except (TypeError, ValueError):
                pass
        if 'target' in data:
            try:
                # 깔린 카드보다 많이 뒤집을 수는 없다. 넘겨두면 '③ 카드를 뒤집으세요 (5/10)'
                # 에서 영원히 멈추고, 오버레이도 목표만 남기는 화면으로 넘어가지 않는다.
                cap = len(g.get('cards') or []) or SIGGAME_MAX_CARDS
                g['target'] = max(1, min(cap, int(data['target'])))
            except (TypeError, ValueError):
                pass
        out = {"enabled": g['enabled'], "opacity": g['opacity'], "target": g['target']}
        _siggame_save(state, g)
    return jsonify({"status": "success", **out})


@app.route('/api/siggame/clear', methods=['POST'])
def api_siggame_clear():
    """판을 치운다. 고른 시그니처 목록은 남겨 다음 판에 그대로 다시 쓴다."""
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        g.update({"cards": [], "action": None,
                  "timer": copy.deepcopy(DEFAULT_STATE['siggame']['timer'])})
        showmod.clear_stage(state, 'siggame')
        _siggame_save(state, g)
    print("🃏 [시그게임] 판을 치웠습니다 (고른 시그니처는 유지)", flush=True)
    return jsonify({"status": "success"})
