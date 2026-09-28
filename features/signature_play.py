# -*- coding: utf-8 -*-
"""🎵 시그니처 목록(공개) · 조종실에서 시그니처 바로 틀기.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
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
        return jsonify({'status': 'success', 'signatures': sigs, 'count': len(sigs)})
    except Exception as e:
        print(f"[시그니처 목록 조회 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e), 'signatures': []}), 500

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

        if sig_id:
            sig = server.supabase_get_signature(sig_id)
            if sig and not amount:
                amount = sig.get('amount') or 0
        else:
            if amount <= 0:
                return jsonify({'status': 'error', 'message': '후원 금액을 입력해주세요.'}), 400
            sig = server.supabase_match_signature(amount)

        if not sig:
            return jsonify({'status': 'error', 'message': '재생할 시그니처를 찾지 못했습니다.'}), 404

        with file_lock:
            state = load_data()
            # 재생 전용 수동 송출은 실제 후원이 아니므로 시그니처 순위 집계에서 제외한다.
            enqueue_signature(state, sig, amount, donator, message, count_tally=False)
            save_data(state)
            broadcast_event('update', state)

        print(f"  ▶️ [수동 송출] {amount}원 → '{sig.get('title')}' (#{sig.get('id')})")
        return jsonify({'status': 'success', 'message': '송출했습니다.', 'signature': sig})
    except Exception as e:
        print(f"[수동 송출 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
