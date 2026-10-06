# -*- coding: utf-8 -*-
"""🔁 옛 주소 호환 — 리스너(toon_listener.py) · 후원 콘솔이 쓰는 주소를 v2 명령으로 바꿔 준다.

리스너를 안 고치고 v2 로 갈아탈 수 있게 같은 모양으로 받는다. 채우는 것은 donation 모듈이 맡는다.
"""

import os

MOUNTS = []      # (경로, 함수) — 각 모듈이 더한다

# 🧪 시험판(LM2_TRIAL=1) — 옛 프로그램과 **같이 쓰는 것**을 바꾸는 주소는 잠근다(옛 서버가 방송하는 동안 v2 를 옆에서 만져 볼 때).
#    시그니처 보관소(Supabase) · 리스너가 읽는 테스트 계정 파일 · 서버 코드 버전(git · 서비스 재시작).
#    읽기(목록 · 상태)는 그대로 된다. 갈아탄 뒤에는 LM2_TRIAL 을 빼고 다시 켠다.
TRIAL_BLOCK = {
    ('/api/version/switch', 'POST'): '서버 버전 바꾸기', ('/api/version/latest', 'POST'): '서버 버전 바꾸기',
    ('/api/toon/accounts', 'POST'): '투네이션 테스트 계정 바꾸기',
    ('/api/signatures/add', 'POST'): '시그니처 등록', ('/api/signatures/update/{sig_id}', 'POST'): '시그니처 고치기',
    ('/api/signatures/delete/{sig_id}', 'POST'): '시그니처 지우기', ('/api/signatures/delete/{sig_id}', 'DELETE'): '시그니처 지우기',
    ('/api/sigadmin/restore', 'POST'): '시그니처 되살리기', ('/api/sigadmin/revert', 'POST'): '시그니처 되돌리기',
}


def trial_on():
    return (os.environ.get('LM2_TRIAL') or '').strip().lower() in ('1', 'on', 'true', 'yes')


def route(path, methods=('POST',)):
    def deco(fn):
        MOUNTS.append((path, methods, fn))
        return fn
    return deco


def mount(app, bus, authed, answer):
    from fastapi import Request
    for path, methods, fn in MOUNTS:
        def make(_fn, _path):
            async def handler(req: Request):        # ⚠️ 타입을 적어야 FastAPI 가 요청으로 안다(안 적으면 422)
                what = TRIAL_BLOCK.get((_path, req.method)) if trial_on() else None
                if what:
                    from fastapi.responses import JSONResponse
                    return JSONResponse({'status': 'error', 'trial': True,
                                         'message': '🧪 시험판이라 「%s」 는 잠가 뒀어요 — 지금 방송 중인 옛 프로그램과 같이 쓰는 것을 바꿔서요. 갈아탄 뒤에 열려요.' % what},
                                        status_code=403)
                return await _fn(req, bus, authed, answer)
            return handler
        handler = make(fn, path)
        handler.__name__ = 'legacy_' + path.strip('/').replace('/', '_')
        app.add_api_route(path, handler, methods=list(methods))
