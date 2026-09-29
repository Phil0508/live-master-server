# -*- coding: utf-8 -*-
"""🌐 페이지 — 로그인 · 조종실/폰/방송판 등 화면 파일, 효과음 · 영상 · 정적 파일 내보내기.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import os
from flask import jsonify, redirect, request, send_from_directory, session, url_for
from server import (
    ADMIN_PASSWORD_UNSET_MSG, BASE_DIR, BUNDLE_DIR,
    admin_password_is_unset, app, login_failed, login_ok,
    login_throttle, password_matches, serve_html_file,
)


# ==========================================
# 🌐 페이지 라우팅
# ==========================================
# 🔓 /setup(OTP 등록 화면)은 걷어냈다 — 조종실 로그인은 비밀번호 하나다(2026-09-30).


@app.route('/login', methods=['GET', 'POST'])
def serve_login():
    if request.method == 'GET' and session.get('authenticated'):
        if request.query_string:
            return redirect(url_for('serve_controller') + '?' + request.query_string.decode('utf-8'))
        return redirect(url_for('serve_controller'))
        
    if request.method == 'POST':
        try:
            data = request.get_json(silent=True) or request.form or {}
            p = data.get('password', '').strip()

            # PW 검증
            if admin_password_is_unset():
                return jsonify({'status': 'error', 'message': ADMIN_PASSWORD_UNSET_MSG}), 403

            login_throttle()   # 앞서 틀린 만큼 늦춘다(찍어보기 방지) — OTP 가 없으니 이게 유일한 장치다

            # 🔓 비밀번호 하나로 들어온다. 옛 화면 · 진행봇이 'otp' 를 같이 보내도 보지 않는다.
            if password_matches(p):
                login_ok()
                session['authenticated'] = True
                return jsonify({'status': 'success'})
            login_failed('조종실 로그인')
            return jsonify({'status': 'error', 'message': '비밀번호가 달라요. 다시 넣어 주세요.'}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    return serve_html_file('login.html')

@app.route('/logout')
def serve_logout():
    session.pop('authenticated', None)
    return redirect(url_for('serve_login'))

@app.route('/')
def serve_root():
    return serve_html_file('overlay.html')

@app.route('/overlay')
@app.route('/overlay.html')
def serve_overlay():
    return serve_html_file('overlay.html')

@app.route('/slot')
@app.route('/slot.html')
def serve_slot():
    return serve_html_file('slot.html')

@app.route('/signature-display')
@app.route('/signature-display.html')
@app.route('/signature_display.html')
def serve_signature_display():
    return serve_html_file('signature_display.html')

@app.route('/alertbox')
@app.route('/alertbox.html')
def serve_alertbox():
    return serve_html_file('alertbox.html')

@app.route('/manual')
@app.route('/manual_send')
@app.route('/manual_send.html')
def serve_manual_send():
    return serve_html_file('manual_send.html')

@app.route('/streamdeck')
@app.route('/streamdeck.html')
def serve_streamdeck():
    return serve_html_file('streamdeck.html')

# 📱↔💻 기기를 보고 알아서 갈라준다.
#    폰으로 /controller 를 열면 폰 조종실로, PC 로 /mobile 을 열면 PC 조종실로 보낸다.
#    즐겨찾기가 어느 쪽이든 그 기기에 맞는 화면이 뜬다 — 주소를 두 개 외울 필요가 없다.
#    ?view=pc / ?view=mobile 을 붙이면 강제로 그 화면을 연다(태블릿에서 PC 판을 쓰고 싶을 때).
#    ⚠️ 되돌릴 때 쿼리스트링(토큰!)을 반드시 그대로 실어야 한다 — 떨어뜨리면 로그인으로 튕긴다.
def _wants_mobile():
    forced = (request.args.get('view') or '').strip().lower()
    if forced in ('pc', 'desktop'):
        return False
    if forced in ('mobile', 'phone'):
        return True
    # 'Mobi' 는 아이폰 사파리·안드로이드 크롬이 다 갖고 있는 표준 표식이다.
    # 아이패드(데스크톱 UA)는 화면이 넓으니 PC 판을 준다 — 의도된 동작.
    return 'Mobi' in (request.headers.get('User-Agent') or '')


def _redirect_keep_query(path):
    qs = request.query_string.decode('utf-8')
    return redirect(path + ('?' + qs if qs else ''))


@app.route('/controller')
def serve_controller():
    if _wants_mobile():
        return _redirect_keep_query('/mobile')
    return serve_html_file('controller.html')

# 🧪 /controller2(재구성 미리보기)는 걷었다(2026-09-29) — 조종실이 그 내용을 흡수했고,
#    옛 방식으로 화면 스위치를 보내 방송 화면 개편(show.py) 뒤로는 눌러도 서버가 거절한다.

@app.route('/mobile')
def serve_mobile():
    # 📱 아이폰 방식 폰 조종실 (앱 12개 + 상단 알림 배너)
    if not _wants_mobile():
        return _redirect_keep_query('/controller')
    return serve_html_file('mobile.html')

@app.route('/admin')
@app.route('/admin.html')
def serve_admin():
    return serve_html_file('admin.html')

@app.route('/upload')
@app.route('/노래등록')
def serve_upload():
    return serve_html_file('upload.html')

# 이 폴더에는 화면 파일만 있는 게 아니다. server.py, live_master.db,
# SUPABASE_CREDENTIALS.txt, auth_config.json, .env, 로그가 전부 같이 있다.
# 아래 catch-all 이 '있으면 준다' 였던 탓에, 주소만 대면 그것들이 그대로 내려왔다
# (관리자 키가 공개 기본값이면 로그인 없이도 통했다).
# 그래서 화면이 실제로 부르는 확장자만 통과시킨다. 목록에 없는 것은
# 로그인한 사람에게도 주지 않는다 — 조종실도 이 파일들을 주소로 꺼내 쓰지 않는다.
SERVABLE_EXTS = {
    '.html', '.htm', '.css', '.js', '.mjs', '.map', '.wasm',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.avif',
    '.woff', '.woff2', '.ttf', '.otf', '.eot',
    '.mp3', '.m4a', '.aac', '.ogg', '.wav', '.webm', '.mp4',
}


# 🔊 효과음. 오버레이에는 로그인 세션이 없으므로 이 폴더만 따로 열어준다.
#    ⚠️ sounds/ 안의 소리 파일만 나간다. 폴더를 벗어나거나 다른 확장자면 404 다.
#       (아래 catch-all 은 .mp3 를 로그인 없이 주지 않는다 — 그래서 전용 길이 필요하다)
SFX_DIR = os.path.join(BASE_DIR, 'sounds')
SFX_EXTS = {'.mp3', '.m4a', '.ogg', '.wav', '.webm'}


@app.route('/sfx/<path:filename>')
def serve_sfx(filename):
    if os.path.splitext(filename)[1].lower() not in SFX_EXTS:
        return jsonify({"error": "File not found"}), 404
    full = os.path.normpath(os.path.join(SFX_DIR, filename))
    if not full.startswith(os.path.normpath(SFX_DIR) + os.sep) or not os.path.exists(full):
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(SFX_DIR, filename)


@app.route('/sfx/list')
def api_sfx_list():
    """있는 효과음 파일 이름만 알려준다.

    ⚠️ 이게 없으면 화면이 파일이 있는지 확인하려고 하나씩 받아보게 되고,
       없는 파일마다 404 가 콘솔에 쌓인다(효과음 9개 = 404 아홉 줄).
       진짜 문제가 생겼을 때 그 사이에 묻힌다. 한 번만 물어보고 끝낸다.
    ⚠️ 로그인 없이 열어둔다 — 오버레이에는 세션이 없다(/sfx/ 와 같은 이유).
    """
    # ⚠️ 이름만 주면 화면이 확장자를 짐작해야 한다(.mp3 로 찍으면 .wav 를 넣었을 때 못 찾는다).
    #    이름 → 실제 파일 로 짝지어 준다.
    out = {}
    try:
        for root, _dirs, files in os.walk(SFX_DIR):
            for fn in sorted(files):
                stem, ext = os.path.splitext(fn)
                if ext.lower() not in SFX_EXTS:
                    continue
                rel_dir = os.path.relpath(root, SFX_DIR)
                pre = '' if rel_dir in ('.', '') else rel_dir.replace(os.sep, '/') + '/'
                out.setdefault(pre + stem, pre + fn)     # 같은 이름이면 먼저 것을 쓴다
    except Exception as e:
        print(f'[효과음 목록] 훑기 실패 — 빈 목록으로 진행: {e}')
    return jsonify({'status': 'success', 'files': out, 'names': sorted(out)})


# 🎬 고액후원 영상. 효과음(/sfx/)과 같은 이유로 전용 길을 낸다 —
#    오버레이에는 로그인 세션이 없어서, 일반 경로로 두면 영상이 로그인 화면으로 튕긴다.
#    (지금은 Supabase 에 두므로 이 길이 없어도 되지만, 서버에 직접 두고 싶어질 때를 위해
#     열어둔다. 그러면 조종실에 저장된 주소 한 줄만 바꾸면 되고 코드는 안 건드린다)
#    ⚠️ videos/ 폴더 안의 영상만 나간다. 폴더를 벗어나거나 다른 확장자면 404 다.
VIDEO_DIR = os.path.join(BASE_DIR, 'videos')
VIDEO_EXTS = {'.mp4', '.webm', '.mov', '.m4v'}


@app.route('/videos/<path:filename>')
def serve_video(filename):
    if os.path.splitext(filename)[1].lower() not in VIDEO_EXTS:
        return jsonify({"error": "File not found"}), 404
    full = os.path.normpath(os.path.join(VIDEO_DIR, filename))
    if not full.startswith(os.path.normpath(VIDEO_DIR) + os.sep) or not os.path.exists(full):
        return jsonify({"error": "File not found"}), 404
    # 영상은 커서 탐색(range 요청)이 되어야 한다. conditional=True 가 그걸 처리한다.
    return send_from_directory(VIDEO_DIR, filename, conditional=True)


@app.route('/<path:filename>')
def serve_dynamic_file(filename):
    if filename.startswith('api/'):
        return jsonify({"status": "error", "message": "API endpoint not found"}), 404
    if os.path.splitext(filename)[1].lower() not in SERVABLE_EXTS:
        return jsonify({"error": "File not found"}), 404
    for root in [BASE_DIR, BUNDLE_DIR]:
        # 상위 폴더로 빠져나가는 경로를 두 겹으로 막는다
        # (send_from_directory 도 막지만, 여기서 os.path.exists 로 존재 여부를
        #  먼저 알려주는 것 자체가 힌트가 된다)
        full = os.path.normpath(os.path.join(root, filename))
        if not full.startswith(os.path.normpath(root) + os.sep):
            continue
        if os.path.exists(full):
            return send_from_directory(root, filename)
    return jsonify({"error": "File not found"}), 404
