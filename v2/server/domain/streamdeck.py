# -*- coding: utf-8 -*-
"""🎛️ 스트림덱 한 번 누르기 주소 — 옛 features/streamdeck.py 를 v2 명령으로 옮겼다.

스트림덱의 'Website' 단추(또는 가상 단추판 /streamdeck/)가 GET 주소 하나를 부르면 v2 명령 하나가 돈다.
로그인(옛 것과 같다): 조종실 로그인 쿠키(lm2) · `Authorization: Bearer <SESSION_SECRET>` · `?token=<SESSION_SECRET>`
  ⚠️ 옛 서버도 /api/streamdeck/* 를 로그인 예외에 두지 않았다 — 주소만 알면 누구나 방송판을 건드릴 수 있었기 때문이다.

GET /api/streamdeck/clip[?label=]        ✂️ 쇼츠 클립(clip.now) — 90초 뒤 방송판(OBS)이 앞뒤 90초를 저장
GET /api/streamdeck/skip                 ⏭ 지금 시그니처 건너뛰기(reaction.skip)
GET /api/streamdeck/pause[?on=1|0]       ⏸ 새 시그니처 멈춤 · 다시(reaction.pause — on 이 없으면 뒤집기)
GET /api/streamdeck/neon[?color=]        💡 조명(lights.color) — color: RAINBOW(없으면 이것 · 옛 기본) · AUDI(아우디 뒤집기) · OFF(둘 다 끔)
                                         · 색 글자 FF0055 / %23FF0055(# 은 주소에서 %23 — 그냥 # 을 쓰면 뒤가 잘린다)
  ⚠️ 옛 주소는 조명과 함께 '리액션 모드' 를 켜서 시그니처 없이도 테두리가 켜졌다(점수판도 가려졌다).
     v2 에는 그 수동 모드가 없다 — 조명은 **시그니처가 나오는 동안만** 보인다(lights.py).
옮기지 않은 옛 주소(부르면 410 과 까닭을 돌려준다 — 옛 주소로 맞춰 둔 단추가 말없이 실패하지 않게)
  save  Postgres 세이브포인트 — v2 는 SQLite 장부에 명령이 모두 남아(events · slices) 따로 저장할 것이 없다
"""
from fastapi.responses import JSONResponse

from .legacy import route


def _pause_data(q):
    on = q.get('on')
    if on in ('1', 'true', 'on'):
        return {'paused': True}
    if on in ('0', 'false', 'off'):
        return {'paused': False}
    return {}


def _pause_msg(bus):
    return '⏸ 새 시그니처를 멈췄어요(지금 것은 끝까지)' if bus.state.get('queue').get('paused') else '▶ 시그니처를 다시 틀어요'


def _neon_msg(bus):
    """💡 누른 뒤 조명이 어떻게 되었는지 한 줄로(아우디는 뒤집기라 '지금 켜짐/꺼짐' 을 알려 줘야 헷갈리지 않는다)"""
    L = bus.state.get('lights')
    c = L.get('color')
    neon = '꺼짐' if c == 'OFF' else ('🌈 무지개' if c == 'RAINBOW' else '🎨 ' + str(c))
    return '💡 조명 — 네온 %s · 아우디 %s (시그니처가 나올 때 켜져요)' % (neon, '켜짐' if L.get('audi') else '꺼짐')


# 이름 → (명령, 쿼리 → data, 성공 글(문자열 또는 fn(bus)))
ACTIONS = {
    'clip': ('clip.now', lambda q: {'label': (q.get('label') or '').strip()[:60] or '🎛 스트림덱'},
             '✂️ 클립 — 90초 뒤 OBS 가 앞 90초 + 뒤 90초를 저장해요'),
    'skip': ('reaction.skip', lambda q: {}, '⏭ 지금 시그니처를 건너뛰었어요'),
    'pause': ('reaction.pause', _pause_data, _pause_msg),
    'neon': ('lights.color', lambda q: {'color': q.get('color', 'RAINBOW')}, lambda bus: _neon_msg(bus)),
}
GONE = {
    'save': 'v2 는 모든 명령이 장부(SQLite)에 남아 세이브포인트가 따로 필요 없어요',
}


def _err(msg, code):
    return JSONResponse({'status': 'error', 'message': msg}, status_code=code)


def _make(name):
    cmd, to_data, msg = ACTIONS[name]

    async def handler(req, bus, authed, answer):
        if not authed(req):
            return _err('로그인이 필요합니다 — 조종실에서 먼저 로그인하거나 주소 끝에 ?token= 을 붙여 주세요', 401)
        res = await bus.run(cmd, to_data(req.query_params), by='streamdeck', authed=True)
        if not res.get('ok'):
            return _err(res.get('error') or '실패했어요', int(res.get('code') or 400))
        return {'status': 'success', 'action': name, 'message': msg(bus) if callable(msg) else msg}
    return handler


def _gone(name):
    async def handler(req, bus, authed, answer):
        if not authed(req):
            return _err('로그인이 필요합니다', 401)
        return _err(GONE[name], 410)
    return handler


for _n in ACTIONS:
    route('/api/streamdeck/' + _n, methods=('GET',))(_make(_n))
for _n in GONE:
    route('/api/streamdeck/' + _n, methods=('GET',))(_gone(_n))
