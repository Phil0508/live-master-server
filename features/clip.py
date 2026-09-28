# -*- coding: utf-8 -*-
"""✂️ 쇼츠 클립 — OBS 리플레이 버퍼로 '방금 90초' 저장, 회사 PC 클립 도우미와 주고받기.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import os
import threading
import time
import uuid
from flask import jsonify, request
from server import (
    BASE_DIR, _as_int, app, broadcast_event, file_lock, load_data, save_data,
)


# ==========================================
# ✂️ 쇼츠 클립 — OBS 리플레이 버퍼로 '방금 90초' 저장 (2026-09-28)
# ==========================================
# 대표님: "9시간 방송으로 쇼츠를 몇 개 만들 수 있게". 녹화본을 나중에 처음부터 뒤지지 않도록,
# 명장면이 터질 때마다 OBS 가 '방금 90초' 를 파일로 떨구게 한다(자동차 블랙박스와 같다).
# ⚠️ OBS 는 다른 컴퓨터(회사)에 있다. 조종실은 https 라서 다른 컴퓨터의 OBS 에 직접 못 붙는다.
#    그래서 OBS 안에 이미 들어가 있는 **방송판(브라우저 소스)** 이 대신 말한다:
#    window.obsstudio.saveReplayBuffer(). 이 말은 OBS 에서 그 소스에 '고급 접근 권한' 을 줬을 때만 먹는다.
#    → 방송판을 여러 장면에 넣어 뒀어도 권한 준 하나만 저장한다(같은 클립이 여러 개 안 생긴다).
# 순간은 셋: ① 조종실 [✂ 클립] ② 기준 금액 이상 시그가 **실제로 재생될 때** ③ 시그뒤집기 올클리어.
#    ②③ 은 방송판이 재생·연출 시각을 알아서 스스로 건다 — 서버는 목록(무엇이 언제)만 적는다.
CLIP_LOG_MAX = 60
CLIP_AUTO_DEFAULT = 100000
# 📁 파일 이름 규칙 — 회사 PC 도우미가 리플레이 파일을 모을 폴더로 옮기며 이 규칙대로 이름을 붙인다.
#    {날짜} 2026-10-01 · {시각} 21-14-50 · {제목} 클립 제목(조종실에서 고친 것, 없으면 이유) · {번호} 그날 몇 번째
CLIP_NAME_FMT_DEFAULT = '{날짜} {시각} {제목}'
CLIP_HELPER_DIR = os.path.join(BASE_DIR, 'tools', 'clip_helper')  # (옮기기 전엔 server.py 옆 = BASE_DIR)
# 방송판(OBS)이 알려 오는 '저장 담당' 상태 — 메모리에만 둔다(DB·상태에 안 쓴다, 조종실 표시용).
_clip_obs = {'seen': 0.0, 'level': -1, 'rb': None, 'saved': 0.0, 'err': ''}
_clip_obs_lock = threading.Lock()


def _clip_state(state):
    c = state.get('clip')
    if not isinstance(c, dict):
        c = {}
        state['clip'] = c
    c.setdefault('auto', True)
    c['auto_min'] = max(0, _as_int(c.get('auto_min'), CLIP_AUTO_DEFAULT) or 0)
    if not isinstance(c.get('name_fmt'), str) or not c.get('name_fmt').strip():
        c['name_fmt'] = CLIP_NAME_FMT_DEFAULT
    if not isinstance(c.get('log'), list):
        c['log'] = []
    return c


def _clip_log(state, kind, label, ref=None):
    """클립 목록에 한 줄. 방송이 끝나면 '어느 파일이 뭐였나' 를 이 시각으로 맞춘다.
    ref — 방송판이 '이것을 저장했다' 고 알려 올 때 쓰는 열쇠(직접=이 줄 id, 큰 시그=대기열 id, 올클리어=allclear:시각).
    saved_at — 방송판이 OBS 저장을 확인한 서버 시각. 회사 PC 도우미가 파일 시각과 맞춰 이름을 붙인다."""
    c = _clip_state(state)
    cid = uuid.uuid4().hex[:10]
    c['log'].append({'id': cid, 'ts': int(time.time() * 1000), 'kind': kind, 'label': str(label or '')[:60],
                     'ref': str(ref or cid)[:40], 'name': '', 'saved_at': 0})
    if len(c['log']) > CLIP_LOG_MAX:
        del c['log'][:len(c['log']) - CLIP_LOG_MAX]
    return cid


def _clip_obs_view():
    with _clip_obs_lock:
        o = dict(_clip_obs)
    o['alive'] = bool(o['seen']) and (time.time() - o['seen'] < 90)
    o['seen_ago'] = int(time.time() - o['seen']) if o['seen'] else None
    o['saved_ago'] = int(time.time() - o['saved']) if o['saved'] else None
    return o


@app.route('/api/clip', methods=['GET'])
def api_clip_get():
    state = load_data()
    return jsonify({'status': 'success', 'clip': _clip_state(state), 'obs': _clip_obs_view()})


@app.route('/api/clip', methods=['POST'])
def api_clip_now():
    """조종실 [✂ 클립] — 방송판에게 '지금 저장' 을 보낸다."""
    body = request.get_json(silent=True) or {}
    label = str(body.get('label') or '').strip()[:60] or '✂ 직접 누름'
    delay = max(0, min(60000, _as_int(body.get('delay_ms'), 0) or 0))
    with file_lock:
        state = load_data()
        cid = _clip_log(state, 'manual', label)
        save_data(state)
        broadcast_event('update', state)
    broadcast_event('clip', {'id': cid, 'label': label, 'delay_ms': delay})
    return jsonify({'status': 'success', 'id': cid, 'obs': _clip_obs_view()})


@app.route('/api/clip/settings', methods=['POST'])
def api_clip_settings():
    body = request.get_json(silent=True) or {}
    with file_lock:
        state = load_data()
        c = _clip_state(state)
        if 'auto' in body:
            c['auto'] = bool(body.get('auto'))
        if 'auto_min' in body:
            c['auto_min'] = max(0, min(100000000, _as_int(body.get('auto_min'), CLIP_AUTO_DEFAULT) or 0))
        if 'name_fmt' in body:
            f = str(body.get('name_fmt') or '').replace('\n', ' ').strip()[:80]
            c['name_fmt'] = f or CLIP_NAME_FMT_DEFAULT
        if body.get('clear'):
            c['log'] = []
        save_data(state)
        broadcast_event('update', state)
    return jsonify({'status': 'success', 'clip': c})


@app.route('/api/clip/rename', methods=['POST'])
def api_clip_rename():
    """클립 제목 고치기 — 도우미가 모은 폴더의 파일 이름도 따라 바뀐다."""
    body = request.get_json(silent=True) or {}
    cid = str(body.get('id') or '')
    name = str(body.get('name') or '').replace('\n', ' ').strip()[:60]
    with file_lock:
        state = load_data()
        c = _clip_state(state)
        hit = next((x for x in c['log'] if x.get('id') == cid), None)
        if not hit:
            return jsonify({'status': 'error', 'message': '없는 클립입니다'}), 404
        hit['name'] = name
        save_data(state)
        broadcast_event('update', state)
    return jsonify({'status': 'success', 'clip': hit})


@app.route('/api/clip/helper.zip', methods=['GET'])
def api_clip_helper_zip():
    """회사 PC(OBS 있는 곳)에서 켜 둘 도우미 — 리플레이 파일을 고른 폴더로 옮기며 이름을 붙인다.
    ⚠️ 윈도우 기본 PowerShell 로 돈다(설치 없음). 서버 주소는 받는 순간의 주소로 박아 준다."""
    import io as _io, zipfile as _zip
    from flask import Response
    host = request.headers.get('X-Forwarded-Host') or request.host
    scheme = request.headers.get('X-Forwarded-Proto') or request.scheme
    if not host.startswith(('127.0.0.1', 'localhost')):
        scheme = 'https'
    server = '%s://%s' % (scheme, host)
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, 'w', _zip.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(CLIP_HELPER_DIR)):
            p = os.path.join(CLIP_HELPER_DIR, fn)
            if not os.path.isfile(p):
                continue
            data = open(p, 'rb').read()
            if fn.endswith('.ps1'):
                txt = data.decode('utf-8-sig').replace('__SERVER__', server)
                data = b'\xef\xbb\xbf' + txt.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')   # PowerShell 5.1 은 BOM 이 있어야 한글을 읽는다
            elif fn.endswith(('.bat', '.txt')):
                data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            z.writestr('shorts_clip_helper/' + fn, data)
    return Response(buf.getvalue(), mimetype='application/zip',
                    headers={'Content-Disposition': 'attachment; filename=shorts_clip_helper.zip'})


@app.route('/api/clip/hello', methods=['POST'])
def api_clip_hello():
    """방송판(OBS 브라우저 소스)이 '저장 담당' 상태를 알린다 — 무인증(방송판은 세션이 없다).
    ⚠️ 받는 것은 숫자·참거짓 몇 개뿐이고 메모리에만 적는다. 상태·DB 는 안 건드린다.
       여러 방송판이 알려 오면 권한이 가장 높은 쪽을 믿는다(권한 없는 쪽이 덮어써 깜빡이지 않게)."""
    b = request.get_json(silent=True) or {}
    lv = _as_int(b.get('level'), -1)
    lv = -1 if lv is None else max(-1, min(5, lv))
    now = time.time()
    with _clip_obs_lock:
        fresh = _clip_obs['seen'] and now - _clip_obs['seen'] < 90
        if fresh and lv < _clip_obs['level']:
            return jsonify({'status': 'success', 'kept': True})
        _clip_obs['seen'] = now
        _clip_obs['level'] = lv
        _clip_obs['rb'] = b.get('rb') if isinstance(b.get('rb'), bool) else None
        _clip_obs['err'] = str(b.get('err') or '')[:80]
        if b.get('saved') is True:
            _clip_obs['saved'] = now
    # 💾 어느 순간이 저장됐나 — 목록 줄에 저장 시각을 적는다(도우미가 파일 시각과 맞춘다).
    #    ⚠️ 무인증 길이라 좁게 받는다: 저장 알림 + 권한 있는 방송판 + 열쇠 10개(각 40자)까지,
    #       이미 있는 줄의 saved_at 한 칸만 바꾼다. 없는 열쇠는 무시한다.
    refs = b.get('refs') if isinstance(b.get('refs'), list) else []
    refs = [str(r)[:40] for r in refs[:10] if isinstance(r, (str, int))]
    if b.get('saved') is True and refs and lv >= 4:
        with file_lock:
            state = load_data()
            c = _clip_state(state)
            hit = False
            for x in c['log']:
                if (x.get('ref') in refs or x.get('id') in refs) and not x.get('saved_at'):
                    x['saved_at'] = int(now * 1000)
                    hit = True
            if hit:
                save_data(state)
                broadcast_event('update', state)
    return jsonify({'status': 'success'})
