# -*- coding: utf-8 -*-
"""🎵 시그니처 목록(공개) · 조종실에서 시그니처 바로 틀기.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import random
import time
from flask import jsonify, request
import server  # 연습 서버가 가짜로 바꿔 끼우는 시그니처 조회는 부를 때마다 server 에서 찾는다
from server import (
    _as_int, app, broadcast_event, enqueue_signature, file_lock, load_data, request_is_authed,
    save_data,
)


# 🟢 시그니처 목록 (Supabase 대리 조회) — 오버레이/컨트롤러/슬롯이 공통으로 사용
# 로그인 없이 볼 수 있는 항목. 오버레이가 사진·음원을 미리 받아두는 데 필요한 것뿐이다.
# ⚠️ title 과 amount 를 빼는 이유: 시그게임에서 어느 시그니처가 판에 깔렸는지가
#    번호(sig_id)로 나가는데, 여기서 번호→이름·금액을 그대로 조회할 수 있으면
#    카드를 감춘 의미가 절반은 사라진다. 오버레이는 이 두 값을 쓰지 않는다.
_PUBLIC_SIG_FIELDS = ('id', 'image_url', 'sound_url', 'duration')


@app.route('/api/signatures')
def api_signatures():
    try:
        sigs = server.supabase_list_signatures()
        if not request_is_authed():
            sigs = [{k: s.get(k) for k in _PUBLIC_SIG_FIELDS if k in s}
                    for s in sigs if isinstance(s, dict)]
            # 순서도 섞는다 — 금액순 그대로면 아래 시그리스트(금액순 · 이름)와 줄을 맞춰 번호→이름을 알아낼 수 있다
            random.shuffle(sigs)
        return jsonify({'status': 'success', 'signatures': sigs, 'count': len(sigs)})
    except Exception as e:
        print(f"[시그니처 목록 조회 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e), 'signatures': []}), 500


# 📜 시그리스트(공개) — 크루 사이트 시그리스트(엔젤오락실, rgfamily 처럼 그림 카드)가 읽는다(2026-10-10 대표님).
#    금액 · 이름 · 그림 · 소리. 번호(id)는 안 준다.
#    그림을 같이 주는 까닭: 시그 그림에 이름 · 금액이 크게 적혀 있어서, 번호→그림(위 공개 목록)만으로도 이미 알 수 있었다.
#    그러니 여기서 그림을 빼 봐야 시그게임 카드를 더 감추지 못하고, 사이트만 휑해진다.
#    1분 동안은 같은 답 — 누가 자꾸 불러도 Supabase 를 매번 부르지 않게. 못 읽으면 지난 답을 준다.
_board = {'t': 0.0, 'rows': None}


@app.route('/api/signatures/board')
def api_signature_board():
    now = time.time()
    if _board['rows'] is None or now - _board['t'] > 60:
        try:
            rows = []
            for s in server.supabase_list_signatures():
                amt = _as_int(s.get('amount')) if isinstance(s, dict) else None
                if amt and amt > 0:
                    rows.append({'amount': amt, 'title': str(s.get('title') or '').strip(),
                                 'image_url': s.get('image_url') or '', 'sound_url': s.get('sound_url') or ''})
            rows.sort(key=lambda r: (r['amount'], r['title']))
            _board.update(t=now, rows=rows)
        except Exception as e:
            print(f"[시그리스트 조회 오류] {e}")
            if _board['rows'] is None:
                return jsonify({'status': 'error', 'message': '시그 목록을 못 읽었어요', 'rows': []}), 502
    resp = jsonify({'status': 'success', 'rows': _board['rows'], 'count': len(_board['rows'])})
    resp.headers['Cache-Control'] = 'public, max-age=60'
    return resp

@app.route('/api/signature/play', methods=['POST'])
def api_signature_play():
    """수동 송출 (정산 장부 기록 없음).
       sig_id 지정 시 해당 시그니처 그대로, 아니면 amount로 매칭."""
    try:
        data = request.get_json(silent=True) or {}
        sig_id = data.get('sig_id')
        amount = _as_int(data.get('amount') or 0)
        if amount is None:
            return jsonify({'status': 'error', 'message': '금액이 숫자가 아닙니다'}), 400
        donator = str(data.get('name') or '수동송출').strip() or '수동송출'
        message = (data.get('message') or '').strip()
        # 🔁 × 몇 번 — 계좌로 같은 시그니처를 여러 번 받았을 때(대표님 2026-09-29). 한 줄 ×N 으로 줄 선다.
        #    방송판은 한 번 틀고 ×N, 조종실 대기줄의 [N번 다 틀기]면 N번 다 튼다.
        try:
            count = max(1, min(30, int(data.get('count') or 1)))
        except (TypeError, ValueError):
            count = 1

        if sig_id:
            sig = server.supabase_get_signature(sig_id)
            if sig and not amount:
                amount = sig.get('amount') or 0
        else:
            if amount <= 0:
                return jsonify({'status': 'error', 'message': '후원 금액을 입력해주세요.'}), 400
            # 💬 제일 싼 시그니처보다 적은 금액은 시그니처를 틀지 않는다 — 투네이션 후원과 같게.
            #    대표님 2026-10-03 "후원 콘솔에서 1000~9999원 틀면 냅다 최저 시그 가격으로 올리던데 투네이션이랑 똑같이 위에 뜨게".
            #    ⚠️ 예전엔 '올림 매칭'(gte)이라 5,000원에도 제일 싼 시그니처가 걸려 재생됐다(후원 경로는 이미 막혀 있었다).
            #    방송판은 latest_donation 금액으로 정한다 — 1만 원 미만은 맨 위 띠, 그 이상은 가운데 카드(투네이션과 같은 길).
            #    재생 전용(장부 없음)이라 display_only 를 붙인다 — 정산 · 순위 · 대기함은 안 건드린다.
            _floor = server._sig_min_amount()
            if _floor and amount < _floor:
                with file_lock:
                    state = load_data()
                    _new = {'name': donator, 'amount': amount, 'message': message,
                            'time': time.time(), 'display_only': True}
                    # 📒 되살리기 판단용 tx 목록은 이어 붙인다(features/donation.py _tx_log_add 와 같은 뜻 — 끊기면 판단이 틀어진다)
                    _prev = state.get('latest_donation')
                    if isinstance(_prev, dict) and isinstance(_prev.get('tx_log'), dict):
                        _new['tx_log'] = _prev['tx_log']
                    state['latest_donation'] = _new
                    save_data(state)
                    broadcast_event('update', state)
                print(f"  💬 [수동 송출 · 화면에만] {donator} {amount:,}원 — 제일 싼 시그니처({_floor:,}원)보다 적어 시그니처 없이 띄웁니다")
                return jsonify({'status': 'success', 'display_only': True,
                                'message': '제일 싼 시그니처(%s원)보다 적어 시그니처 없이 방송판에 띄웠습니다' % format(_floor, ',')})
            sig = server.supabase_match_signature(amount)

        if not sig:
            return jsonify({'status': 'error', 'message': '재생할 시그니처를 찾지 못했습니다.'}), 404

        with file_lock:
            state = load_data()
            # 재생 전용 수동 송출은 실제 후원이 아니므로 시그니처 순위 집계에서 제외한다.
            _rid = enqueue_signature(state, sig, amount, donator, message, count_tally=False)
            if count > 1:
                _it = next((x for x in (state.get('reaction_queue') or []) if x.get('id') == _rid), None)
                if _it is not None:
                    _it['count'] = count
            save_data(state)
            broadcast_event('update', state)

        print(f"  ▶️ [수동 송출] {amount}원 → '{sig.get('title')}' (#{sig.get('id')})" + (f" ×{count}" if count > 1 else ''))
        return jsonify({'status': 'success', 'message': '송출했습니다.', 'signature': sig, 'count': count})
    except Exception as e:
        print(f"[수동 송출 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
