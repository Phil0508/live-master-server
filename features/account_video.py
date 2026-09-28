# -*- coding: utf-8 -*-
"""🎞️ 계좌 고액후원 영상 — 금액대별 영상 올리기 · 틀기 · 멈추기.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import time
from flask import jsonify, request
from werkzeug.exceptions import HTTPException
import server  # 연습 서버가 가짜로 바꿔 끼우는 시그니처 조회는 부를 때마다 server 에서 찾는다
from server import (
    app, broadcast_event, file_lock, load_data, save_data, storage_delete_by_url,
    storage_upload,
)


@app.route('/api/account/play', methods=['POST'])
def api_account_play_video():
    """후원 콘솔에서 금액대 버튼을 눌렀을 때 그 구간의 유튜브 영상을 오버레이에 재생한다.

    ⚠️ 예전에는 후원 금액을 받아 '알아서' 구간을 골라 자동 재생했다. 그런데 계좌 버튼이
       점수 배정 자리(대기함 카드)에 붙어 있어서, 배정·시그니처 재생과 순서가 뒤엉켰다.
       지금은 운영자가 '어느 영상을' 트는지 직접 고른다. 자동 매칭은 없앴다.

    body: {"tier": 구간 번호(0부터)}

    상태를 바꾸지 않고 이벤트만 쏘므로 file_lock 을 잡지 않는다(후원 처리를 막지 않는다).
    """
    data = request.get_json(silent=True) or {}
    tiers = load_data().get('account_video_tiers') or []

    try:
        idx = int(data.get('tier'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "tier 번호가 필요합니다"}), 400
    if not (0 <= idx < len(tiers)):
        return jsonify({"status": "error", "message": "없는 구간입니다"}), 400

    t = tiers[idx]
    video = (t.get('video') or '').strip()
    label = t.get('label') or ''
    if not video:
        return jsonify({"status": "ok", "played": False, "reason": "no_video", "label": label})

    broadcast_event('account_video', {"videoId": video, "label": label})
    return jsonify({"status": "ok", "played": True, "label": label})


# 🎬 고액후원 영상 — 유튜브 대신 mp4 파일을 쓸 수 있게 한다.
#
# ⚠️ 유튜브 임베드는 방송에 쓰기엔 약점이 있다: 재생 전 광고가 붙을 수 있고, 끝나면
#    추천 영상 썸네일이 뜨고, 로고와 제목이 화면에 남는다. 고액 후원 연출 끝에 남의
#    영상 썸네일이 뜨는 셈이다. 게다가 '끝났다'를 postMessage 로 물어보는 구조라
#    놓치면 20분 안전장치가 돌 때까지 화면을 점유한다.
#    파일은 <video> 의 onended 로 확실히 끝나고, 광고도 로고도 없다.
#
# ⚠️ 파일은 Supabase Storage 에 둔다. 서버 디스크에 두면 서버를 다시 세팅할 때
#    통째로 사라지는데, 시그니처는 이미 Supabase 라 영상만 취약해진다.
#    저장 위치가 바뀌어도 화면은 손댈 필요가 없다 — 오버레이는 '주소'만 보고
#    유튜브인지 파일인지 알아서 판단한다.
ACCT_VIDEO_TYPES = {'mp4': 'video/mp4', 'webm': 'video/webm',
                    'mov': 'video/quicktime', 'm4v': 'video/x-m4v'}
ACCT_VIDEO_MAX_MB = 60


@app.route('/api/account/video/upload', methods=['POST'])
def api_account_video_upload():
    """금액대 한 칸에 영상 파일을 올린다. form: tier(번호), file"""
    try:
        # ⚠️ 파일 검사를 먼저 한다. exe 를 거부하는 일이 저장소 설정 여부에 달려 있으면,
        #    저장소가 잠깐 어긋난 사이에는 무엇을 올려도 같은 오류만 돌아와
        #    무엇이 잘못됐는지 알 수 없다. 저장소는 실제로 올리기 직전에 확인한다.
        try:
            idx = int(request.form.get('tier'))
        except (TypeError, ValueError):
            return jsonify({'status': 'error', 'message': '구간 번호가 필요합니다'}), 400
        f = request.files.get('file')
        if not f or not f.filename:
            return jsonify({'status': 'error', 'message': '영상 파일을 골라주세요'}), 400
        ext = (f.filename.rsplit('.', 1)[-1] or '').lower()
        if ext not in ACCT_VIDEO_TYPES:
            return jsonify({'status': 'error',
                            'message': f"{ext or '?'} 형식은 쓸 수 없습니다 (mp4 · webm · mov · m4v)"}), 400

        data = f.read()
        mb = len(data) / 1024 / 1024
        if mb > ACCT_VIDEO_MAX_MB:
            return jsonify({'status': 'error',
                            'message': f'파일이 {mb:.0f}MB 입니다. {ACCT_VIDEO_MAX_MB}MB 이하로 줄여주세요'}), 400
        if not data:
            return jsonify({'status': 'error', 'message': '빈 파일입니다'}), 400

        with file_lock:
            state = load_data()
            tiers = state.get('account_video_tiers') or []
            if not (0 <= idx < len(tiers)):
                return jsonify({'status': 'error', 'message': '없는 구간입니다'}), 400
            tier = tiers[idx]
            old = (tier.get('video') or '').strip()

        if not server._supabase_ready():
            return jsonify({'status': 'error',
                            'message': '영상 보관소(Supabase)가 설정되지 않아 올릴 수 없습니다'}), 503

        # ⚠️ 올리기는 락 밖에서 한다. 60MB 를 서울까지 보내는 동안 락을 쥐고 있으면
        #    그동안 후원 접수·점수 지급이 통째로 멈춘다.
        ver = int(time.time())
        path = f"videos/acct_{tier.get('min')}.{ext}"
        url = storage_upload(path, data, ACCT_VIDEO_TYPES[ext]) + f'?v={ver}'

        with file_lock:
            state = load_data()
            tiers = state.get('account_video_tiers') or []
            if 0 <= idx < len(tiers):
                tiers[idx]['video'] = url
                state['account_video_tiers'] = tiers
                save_data(state, sync=True)
                broadcast_event('update', state)

        # 확장자가 바뀌면 옛 파일이 남는다(acct_200000.mov 를 mp4 로 갈아끼운 경우).
        # 실패해도 새 영상은 이미 걸렸으므로 조용히 넘어간다.
        if old.startswith('http') and '/storage/v1/object/public/' in old and old.split('?')[0] != url.split('?')[0]:
            storage_delete_by_url(old)

        print(f"  🎬 [고액후원 영상] {tier.get('label')} 구간에 {ext} {mb:.1f}MB 올림")
        return jsonify({'status': 'success', 'url': url, 'label': tier.get('label'),
                        'size_mb': round(mb, 1)})
    except HTTPException:
        # ⚠️ 본문이 상한(80MB)을 넘으면 파일을 읽는 순간 Flask 가 413 을 던진다.
        #    아래 except 가 그걸 삼키면 운영자에게 "서버 오류" 로 보여서,
        #    파일을 줄이면 된다는 걸 알 방법이 없다. 그대로 올려보낸다.
        raise
    except Exception as e:
        print(f'[고액후원 영상 업로드 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/account/stop', methods=['POST'])
def api_account_stop_video():
    """재생 중인 영상을 즉시 끈다. 잘못 눌렀거나 길 때 손으로 멈출 수 있어야 한다."""
    broadcast_event('account_video_stop', {})
    return jsonify({"status": "ok"})
