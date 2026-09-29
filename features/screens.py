# -*- coding: utf-8 -*-
"""🎬 방송 시작 · 끝 화면(대기 화면 · 엔딩 화면).

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import copy
import time
from flask import jsonify, request
from server import (
    DEFAULT_STATE, _norm_donor, app, broadcast_event, excluded_names, file_lock, load_data, save_data,
)


def _really_excluded(name):
    """사장님이 [순위에서 빼기] 로 뺀 이름인가(빈 이름도 뺀다).
    ⚠️ is_excluded() 를 쓰면 안 된다 — 그건 '익명' 을 언제나 빼서, 조종실에서 '익명 포함' 을
       켜도 끝 화면에만 익명이 안 나왔다(후원 순위판엔 나온다). 익명은 donor_rank_anon 이 정한다."""
    who = _norm_donor(name)
    return (not who) or who in excluded_names()


# ==========================================
# 🎬 방송 시작·끝 화면
#   방송 들어가기 전 '곧 시작합니다 + 카운트다운', 끝날 때 '오늘도 고마워요 + 오늘의 기록' 을
#   방송판 전체에 깐다. 조종실 [시작 전 화면]·[끝 화면]·[끄기] 로만 바뀐다(SERVER_OWNED · PATCH_DENY).
#   ⚠️ 끝 화면의 '오늘의 기록' 은 두 군데서 온다 —
#      방송 중이면 state_for_client 가 **지금 상태로 매번** 만들어 싣고(stage_live),
#      방송을 끝낸 뒤면 종료가 지우기 직전에 떠 둔 last_snap 을 쓴다.
#      누르는 순간에 한 장만 떠 두면, 끝 화면을 띄운 뒤 들어온 마지막 후원이 안 나온다.
STAGE_MODES = ('off', 'start', 'end')
STAGE_TITLE_MAX = 40        # 한 줄 문구 — 방송판 한 줄에 들어가는 만큼
STAGE_MINUTES_MAX = 180     # 카운트다운 — 세 시간이면 충분하다
STAGE_DONORS = 8            # 끝 화면 '후원해 주신 분' — 두 줄씩 네 칸(안전지대 안에 들어가는 만큼)


def _stage_state(state):
    """옛 저장본엔 칸이 없다 — 쓸 때마다 여기서 채운다."""
    ss = state.get('stage_screen')
    if not isinstance(ss, dict):
        ss = {}
        state['stage_screen'] = ss
    for k, v in DEFAULT_STATE['stage_screen'].items():
        ss.setdefault(k, copy.deepcopy(v))
    if ss.get('mode') not in STAGE_MODES:
        ss['mode'] = 'off'
    return ss


def _stage_snapshot(st):
    """끝 화면에 띄울 '오늘의 기록' 한 장.
    ⚠️ 후원 순위판이 보여주는 만큼만 담는다 — 익명 넣기·금액 보이기 설정을 그대로 따른다."""
    st = st or {}

    def _n(v):
        try:
            return int(float(v or 0))
        except (TypeError, ValueError):
            return 0

    # 🏆 오늘의 1등 — 랭킹판과 같은 순서(기여도 높은 순)
    bjs = [b for b in (st.get('bjs') or []) if isinstance(b, dict) and str(b.get('name') or '').strip()]
    bjs.sort(key=lambda b: -_n(b.get('contribution')))
    members = [{'name': str(b.get('name')).strip(), 'score': _n(b.get('score')),
                'contribution': _n(b.get('contribution'))} for b in bjs[:3]]

    with_anon = bool(st.get('donor_rank_anon'))
    show_amt = st.get('donor_rank_amount') is not False
    rows = []
    for who, row in (st.get('donor_tally') or {}).items():
        if not isinstance(row, dict) or _really_excluded(who):
            continue
        if not with_anon and who == '익명':
            continue
        total = _n(row.get('total'))
        if total > 0:
            rows.append({'name': ' '.join(str(row.get('name') or who).split()) or who, 'total': total})
    rows.sort(key=lambda r: (-r['total'], r['name']))

    b = st.get('best_single') or {}
    best = None
    # ⚠️ 한 방 최고도 뺀 이름이면 안 띄운다 — 기록된 뒤에 [순위에서 빼기] 를 눌러도 best_single 은
    #    그대로 남아 있어, 끝 화면에 테스트 후원 이름이 '오늘의 한 방' 으로 나갈 수 있었다.
    #    익명 한 방은 그대로 둔다(한 방 위젯도 익명을 띄운다).
    if (isinstance(b, dict) and _n(b.get('amount')) > 0
            and not (str(b.get('name') or '').strip() and _really_excluded(b.get('name')))):
        best = {'name': str(b.get('name') or ''), 'amount': _n(b.get('amount')),
                'member': str(b.get('member') or '')}
    return {
        'at': int(time.time() * 1000),
        'members': members,
        'donors': [{'name': r['name'], 'total': r['total'] if show_amt else None} for r in rows[:STAGE_DONORS]],
        'donor_count': len(rows),
        'show_amount': show_amt,
        'best': best,
    }


@app.route('/api/screen', methods=['POST'])
def api_stage_screen():
    """🎬 시작 전 화면 · 끝 화면 · 끄기."""
    try:
        body = request.get_json(silent=True) or {}
        mode = str(body.get('mode') or 'off')
        if mode not in STAGE_MODES:
            return jsonify({'status': 'error', 'message': '화면은 off · start · end 중 하나입니다.'}), 400
        with file_lock:
            state = load_data()
            ss = _stage_state(state)
            now = int(time.time() * 1000)
            if mode != 'off':
                ss['title'] = ' '.join(str(body.get('title') or '').split())[:STAGE_TITLE_MAX]
                ss['shown_at'] = now
            if mode == 'start':
                try:
                    minutes = int(float(body.get('minutes') or 0))
                except (TypeError, ValueError):
                    minutes = 0
                minutes = max(0, min(STAGE_MINUTES_MAX, minutes))
                # 0 분이면 카운트다운 없이 문구만 띄운다
                ss['start_at'] = (now + minutes * 60000) if minutes else 0
                # 방송 시작 전에는 선수 명단(bjs)이 비어 있다 — 조종실 준비 칸에 적어 둔 이름을 받아 둔다
                names = []
                raw = body.get('names')
                for nm in (raw if isinstance(raw, list) else [])[:10]:
                    nm = ' '.join(str(nm or '').split())[:20]
                    if nm and nm not in names:
                        names.append(nm)
                ss['names'] = names
            ss['mode'] = mode
            save_data(state)
            broadcast_event('update', state)
        return jsonify({'status': 'success', 'stage_screen': ss})
    except Exception as e:
        print(f'[시작·끝 화면 오류] {e}', flush=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500
