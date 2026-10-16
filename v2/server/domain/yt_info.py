# -*- coding: utf-8 -*-
"""📺 유튜브 영상 제목 · 채널 — 조종실 BGM 재생 목록에 제목을 보여 주려고(옛 features/yt_info.py 를 v2 로, 대표님 10-07 "무한반복이랑 리스트").

GET /api/yt/info?id=<영상 번호 11자>   (로그인) → {status, id, title, author}

유튜브 **공식 oEmbed**(https://www.youtube.com/oembed)에 영상 주소로 묻는다 — 열쇠 · 로그인이 필요 없는 공개 창구다.
⚠️ 못 받으면(비공개 · 삭제 · 인터넷) 빈 제목 — 조종실은 '영상 번호' 로 두고, 재생하면 플레이어(getVideoData)가 제목을 채운다.
   받은 것만 기억한다(같은 영상은 다시 안 묻는다). 못 받은 것은 기억하지 않아 다음에 다시 묻는다.
⚠️ 바깥으로 나가는 곳은 fetch_info 하나 — 검사는 이것을 바꿔 낀다. LM2_YT_INFO_OFF=1 이면 아예 안 묻는다(시험 서버 · 화면 찍기).
⚠️ 한 번 묻기는 DEADLINE 초까지만 기다린다 — 옛 것이 IPv6 주소 여럿을 하나씩 5초씩 붙잡아 40초가 걸린 적이 있다(실측).
   묻기는 뒤에서 마저 끝나 기억에 들어간다(다음 번엔 바로 나온다).
"""
import asyncio
import json
import os
import re
import urllib.parse
import urllib.request

from fastapi.responses import JSONResponse

from .legacy import route

_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
_CACHE = {}
CACHE_MAX = 2000
TIMEOUT = 5
DEADLINE = 6.0


def fetch_info(vid):
    """oEmbed 한 번 → {title, author} 또는 None."""
    q = urllib.parse.urlencode({'url': 'https://www.youtube.com/watch?v=' + vid, 'format': 'json'})
    req = urllib.request.Request('https://www.youtube.com/oembed?' + q, headers={'User-Agent': 'livemaster-v2'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:          # noqa: S310 (고정 주소 · https 만)
        if r.status != 200:
            return None
        j = json.loads(r.read().decode('utf-8', 'replace') or '{}')
    title = str(j.get('title') or '').strip()
    if not title:
        return None
    return {'title': title[:200], 'author': str(j.get('author_name') or '').strip()[:100]}


def _off():
    return (os.environ.get('LM2_YT_INFO_OFF') or '').strip().lower() in ('1', 'on', 'true', 'yes')


def _ask(vid):
    try:
        v = fetch_info(vid)
    except Exception as e:                       # 인터넷 · 막힌 영상 — 빈 답(조종실은 영상 번호로 둔다)
        print('⚠️ [유튜브 제목] %s 못 받음: %s' % (vid, type(e).__name__), flush=True)
        return None
    if v:
        if len(_CACHE) >= CACHE_MAX:
            _CACHE.clear()
        _CACHE[vid] = v
    return v


@route('/api/yt/info', methods=('GET',))
async def yt_info(req, bus, authed, answer):
    if not authed(req):
        return JSONResponse({'status': 'error', 'message': '로그인이 필요합니다'}, status_code=401)
    vid = str(req.query_params.get('id') or '')
    if not _ID.match(vid):
        return JSONResponse({'status': 'error', 'message': '유튜브 영상 번호가 아닙니다'}, status_code=400)
    hit = _CACHE.get(vid)
    if hit is None and not _off():
        try:
            hit = await asyncio.wait_for(asyncio.to_thread(_ask, vid), DEADLINE)
        except asyncio.TimeoutError:
            hit = None
    hit = hit or {}
    return {'status': 'success', 'id': vid, 'title': hit.get('title', ''), 'author': hit.get('author', '')}
