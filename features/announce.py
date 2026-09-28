# -*- coding: utf-8 -*-
"""📢 안내 봇 — 채팅방에 안내 문구 보내기(유튜브 영상 주소 읽기 포함).

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import copy
import re
from flask import jsonify, request
from server import (
    DEFAULT_STATE, _as_int, app, broadcast_event, file_lock, load_data, save_data,
)


_YT_ID_RE = re.compile(r'(?:v=|/live/|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})')


def _yt_video_id(text):
    """붙여넣은 라이브 주소에서 영상 번호(11글자)를 뽑는다.

    유튜브 주소는 모양이 여럿이다 — watch?v= · youtu.be/ · /live/ · /shorts/ · /embed/.
    사장님이 어느 걸 복사해 오든 받아야 한다. 번호만 그냥 붙여넣어도 받는다.

    ⚠️ 돌려주는 값이 셋이다. '' 는 **비우라는 뜻**(채널에서 알아서 찾기)이고,
       None 은 **못 읽었다**는 뜻이다. 둘을 같게 다루면, 오타를 조용히 '비움'으로
       받아들여 봇이 엉뚱한 데를 쳐다본다.
    """
    t = (text or '').strip()
    if not t:
        return ''
    m = _YT_ID_RE.search(t)
    if m:
        return m.group(1)
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', t):
        return t
    return None


@app.route('/api/announcebot', methods=['POST'])
def api_announce_bot():
    """🤖 진행봇 설정 — 조종실에서 켜고 끄고 간격을 바꾼다.

    ⚠️ 봇은 **다른 프로그램**이다(bot/announce.py). 서버는 이 값을 상태에 적어 SSE 로
       뿌릴 뿐이고, 봇이 그걸 보고 스스로 입을 다문다. 봇이 안 떠 있으면 아무 일도 안 난다.
    ⚠️ /api/data 로는 못 바꾼다(SERVER_OWNED). 조종실이 낡은 사본을 통째로 보낼 때
       방금 바꾼 설정이 되돌아가면 안 되기 때문이다 — 모금함과 같은 이유다.
    """
    try:
        body = request.get_json(silent=True) or {}
        _D = DEFAULT_STATE['announce_bot']
        with file_lock:
            state = load_data()
            b = state.get('announce_bot')
            if not isinstance(b, dict):
                b = copy.deepcopy(_D)
                state['announce_bot'] = b
            for _sub in ('say', 'notices'):
                if not isinstance(b.get(_sub), dict):
                    b[_sub] = copy.deepcopy(_D[_sub])

            if 'enabled' in body:
                b['enabled'] = bool(body.get('enabled'))
            if body.get('min_interval_sec') is not None:
                _iv = _as_int(body.get('min_interval_sec'))
                if _iv is None or not (5 <= _iv <= 600):
                    return jsonify({'status': 'error',
                                    'message': '간격은 5~600초 사이입니다'}), 400
                b['min_interval_sec'] = _iv
            if 'live_url' in body:
                _raw = str(body.get('live_url') or '').strip()
                _vid = _yt_video_id(_raw)
                if _vid is None:
                    return jsonify({'status': 'error',
                                    'message': '라이브 주소를 못 읽었습니다. 유튜브 주소를 '
                                               '그대로 붙여넣어 주세요'}), 400
                b['live_url'] = _raw
                b['live_video_id'] = _vid

            # ⚠️ 모르는 이름은 조용히 버린다. 오타로 상태에 쓰레기 칸이 생기면
            #    봇은 그걸 안 보는데 조종실에는 켜진 것처럼 남는다.
            for _k, _v in (body.get('say') or {}).items():
                if _k in _D['say']:
                    b['say'][_k] = bool(_v)
            for _k, _v in (body.get('notices') or {}).items():
                if _k not in _D['notices']:
                    continue
                _m = _as_int(_v)
                if _m is None or not (0 <= _m <= 120):
                    return jsonify({'status': 'error',
                                    'message': '안내 간격은 0~120분 사이입니다 (0 이면 끔)'}), 400
                b['notices'][_k] = _m

            save_data(state)
            broadcast_event('update', state)
        _on = [k for k, v in b['say'].items() if v]
        print(f"  🤖 [진행봇] {'켬' if b['enabled'] else '끔'} · {b['min_interval_sec']}초"
              f" · 말하는 것 {','.join(_on) or '없음'}", flush=True)
        return jsonify({'status': 'success', 'announce_bot': b})
    except Exception as e:
        print(f'[진행봇 설정 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500
