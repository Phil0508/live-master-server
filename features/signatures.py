# -*- coding: utf-8 -*-
"""🎵 시그니처 관리 — 등록 · 수정 · 삭제.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import time
from flask import jsonify, request
import server  # 연습 서버가 가짜로 바꿔 끼우는 시그니처 조회는 부를 때마다 server 에서 찾는다
from server import (
    app, compress_image_to_webp, storage_delete_by_url, storage_upload,
    supabase_delete_signature, supabase_insert_signature, supabase_update_signature,
)


# ==========================================
# 🎵 시그니처 관리 (등록 / 수정 / 삭제) — 로그인 필요 (exempt 목록에 없음)
# ==========================================
def _save_signature_files(sig_id, image_file, sound_file):
    """업로드된 파일을 Storage에 올리고 {image_url, sound_url} 조각 반환.

    ⚠️ 파일 경로는 id 기준으로 고정이라 교체 시 URL이 같아진다.
    그러면 Supabase CDN 캐시 때문에 방송 화면에 '옛 사진/옛 음원'이 최대 1시간 계속 나온다.
    저장하는 URL 끝에 버전(?v=타임스탬프)을 붙여 교체 즉시 반영되게 한다.
    """
    ver = int(time.time())
    out = {}
    if image_file and image_file.filename:
        data, ext, ctype = compress_image_to_webp(image_file)
        out['image_url'] = storage_upload(f"images/{sig_id}.{ext}", data, ctype) + f"?v={ver}"
    if sound_file and sound_file.filename:
        ext = (sound_file.filename.rsplit('.', 1)[-1] or 'mp3').lower()
        # 클라이언트가 보낸 content_type은 신뢰하지 않고 확장자로 결정한다.
        # (octet-stream으로 올라가면 일부 브라우저에서 오디오 재생이 실패함)
        AUDIO_TYPES = {'mp3': 'audio/mpeg', 'm4a': 'audio/mp4', 'aac': 'audio/aac',
                       'ogg': 'audio/ogg', 'wav': 'audio/wav', 'webm': 'audio/webm',
                       'mp4': 'video/mp4'}
        ctype = AUDIO_TYPES.get(ext)
        if not ctype:
            ctype = sound_file.content_type or 'application/octet-stream'
        out['sound_url'] = storage_upload(f"sounds/{sig_id}.{ext}", sound_file.read(), ctype) + f"?v={ver}"
    return out

@app.route('/api/signatures/add', methods=['POST'])
def api_signature_add():
    try:
        if not server._supabase_ready():
            return jsonify({'status': 'error', 'message': 'Supabase가 설정되지 않았습니다.'}), 500

        amount = int(request.form.get('amount') or 0)
        title = (request.form.get('title') or '').strip() or f"{amount:,}원 시그니처"
        duration = int(request.form.get('duration') or 10)
        if amount <= 0:
            return jsonify({'status': 'error', 'message': '후원 금액을 입력해주세요.'}), 400

        # 1) 행 먼저 삽입해서 id 확보 (파일 경로에 id를 쓰기 때문)
        row = supabase_insert_signature({'amount': amount, 'title': title, 'duration': duration})
        if not row:
            return jsonify({'status': 'error', 'message': '시그니처 생성에 실패했습니다.'}), 500
        sig_id = row['id']

        # 2) 파일 업로드 후 URL 반영
        urls = _save_signature_files(sig_id, request.files.get('image'), request.files.get('sound'))
        if urls:
            row = supabase_update_signature(sig_id, urls) or row

        print(f"  ✅ [시그니처 등록] #{sig_id} '{title}' {amount}원")
        return jsonify({'status': 'success', 'message': '시그니처가 등록되었습니다.', 'signature': row})
    except Exception as e:
        print(f"[시그니처 등록 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/signatures/update/<int:sig_id>', methods=['POST'])
def api_signature_update(sig_id):
    try:
        current = server.supabase_get_signature(sig_id)
        if not current:
            return jsonify({'status': 'error', 'message': '시그니처를 찾을 수 없습니다.'}), 404

        fields = {}
        if request.form.get('amount') is not None and request.form.get('amount') != '':
            fields['amount'] = int(request.form.get('amount'))
        if request.form.get('title') is not None and request.form.get('title').strip():
            fields['title'] = request.form.get('title').strip()
        if request.form.get('duration'):
            fields['duration'] = int(request.form.get('duration'))

        image_file = request.files.get('image')
        sound_file = request.files.get('sound')
        # 파일 교체 시 기존 Storage 파일 정리 (확장자가 바뀔 수 있으므로 URL 기준 삭제)
        if image_file and image_file.filename:
            storage_delete_by_url(current.get('image_url'))
        if sound_file and sound_file.filename:
            storage_delete_by_url(current.get('sound_url'))
        fields.update(_save_signature_files(sig_id, image_file, sound_file))

        if not fields:
            return jsonify({'status': 'success', 'message': '변경 사항이 없습니다.', 'signature': current})

        row = supabase_update_signature(sig_id, fields)
        print(f"  ✏️ [시그니처 수정] #{sig_id} {list(fields.keys())}")
        return jsonify({'status': 'success', 'message': '시그니처가 수정되었습니다.', 'signature': row})
    except Exception as e:
        print(f"[시그니처 수정 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/signatures/delete/<int:sig_id>', methods=['POST', 'DELETE'])
def api_signature_delete(sig_id):
    try:
        current = server.supabase_get_signature(sig_id)
        if not current:
            return jsonify({'status': 'error', 'message': '시그니처를 찾을 수 없습니다.'}), 404
        storage_delete_by_url(current.get('image_url'))
        storage_delete_by_url(current.get('sound_url'))
        supabase_delete_signature(sig_id)
        print(f"  🗑️ [시그니처 삭제] #{sig_id} '{current.get('title')}'")
        return jsonify({'status': 'success', 'message': '시그니처가 삭제되었습니다.'})
    except Exception as e:
        print(f"[시그니처 삭제 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
