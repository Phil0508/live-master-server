# -*- coding: utf-8 -*-
"""📺 유튜브 영상 제목 · 채널 — 조종실 유튜브 재생 목록에 제목을 보여 주려고(대표님 2026-10-07 "무한반복이랑 리스트").

유튜브 **공식 oEmbed**(https://www.youtube.com/oembed)에 영상 주소로 묻는다 — 열쇠 · 로그인이 필요 없는 공개 창구다.
로그인한 조종실만 부른다(require_login 예외 목록에 없다).
⚠️ 못 받으면(비공개 · 삭제 · 네트워크) 빈 답 — 화면은 '영상 번호' 로 두고, 재생하면 플레이어가 제목을 채운다.
   받은 것만 기억한다(같은 영상은 다시 안 묻는다). 못 받은 것은 기억하지 않아 다음에 다시 묻는다.
"""
import re
import threading

from flask import jsonify, request
from server import app

_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
_CACHE = {}
_LOCK = threading.Lock()
CACHE_MAX = 2000
TIMEOUT = 5


def fetch_info(vid):
    """oEmbed 한 번. 돌려받는 값: {title, author} 또는 None. ⚠️ 바깥으로 나가는 곳 — 검사는 이것을 바꿔 낀다."""
    import requests
    r = requests.get('https://www.youtube.com/oembed',
                     params={'url': 'https://www.youtube.com/watch?v=' + vid, 'format': 'json'}, timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    j = r.json()
    title = str(j.get('title') or '').strip()
    if not title:
        return None
    return {'title': title[:200], 'author': str(j.get('author_name') or '').strip()[:100]}


DEADLINE = 6.0     # 이 이상은 안 기다리고 빈 답(묻기는 뒤에서 마저 끝나 기억에 들어간다)
_INFLIGHT = set()


def _lookup(vid):
    """⚠️ requests 의 timeout 은 주소 하나당이다 — 이 PC 처럼 IPv6 주소 8개가 하나씩 5초씩 걸리면 40초를 붙잡는다(실측).
       그래서 다른 갈래에서 묻고 DEADLINE 만 기다린다. 같은 영상을 동시에 두 번 묻지 않는다."""
    def run():
        try:
            v = fetch_info(vid)
        except Exception as e:
            print(f'⚠️ [유튜브 제목] {vid} 못 받음: {type(e).__name__}', flush=True)
            v = None
        with _LOCK:
            _INFLIGHT.discard(vid)
            if v:
                if len(_CACHE) >= CACHE_MAX:
                    _CACHE.clear()
                _CACHE[vid] = v
    with _LOCK:
        if vid in _INFLIGHT:
            return None
        _INFLIGHT.add(vid)
    t = threading.Thread(target=run, daemon=True, name='yt-info')
    t.start()
    t.join(DEADLINE)
    with _LOCK:
        return _CACHE.get(vid)


@app.route('/api/yt/info', methods=['GET'])
def api_yt_info():
    vid = str(request.args.get('id') or '')
    if not _ID.match(vid):
        return jsonify({'status': 'error', 'message': '유튜브 영상 번호가 아닙니다'}), 400
    with _LOCK:
        hit = _CACHE.get(vid)
    if hit is None:
        hit = _lookup(vid)
    if not hit:
        return jsonify({'status': 'success', 'id': vid, 'title': '', 'author': ''})
    return jsonify({'status': 'success', 'id': vid, 'title': hit['title'], 'author': hit['author']})
