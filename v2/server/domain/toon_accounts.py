# -*- coding: utf-8 -*-
"""🧪 투네이션 두 번째(테스트) 계정 — 리스너가 10초마다 읽는 toon_accounts.json 을 고친다(옛 features/toon_accounts.py 그대로).

GET  /api/toon/accounts  (로그인) 테스트 계정 주소(끝 네 글자만) · 켜짐 · 오늘 쉬는 날(수 · 목) · 리스너 상태
POST /api/toon/accounts  (로그인) {test_url?, enabled?}
⚠️ 알림창 주소 끝의 키는 비밀번호 같은 접속 열쇠다. 화면에 그대로 돌려주지 않는다(끝 네 글자만).
⚠️ 상태가 아니라 파일이다 — 리스너(다른 프로그램)가 읽는다. 그래서 명령 줄(bus)을 안 거친다.
"""
import json
import os
import re
import time

from fastapi.responses import JSONResponse

from .legacy import route
from .preflight import REPO, STATUS_FILE

ACCOUNTS_FILE = os.environ.get('TOON_ACCOUNTS_FILE') or os.path.join(REPO, 'toon_accounts.json')
REST_WEEKDAYS = (2, 3)            # 수 · 목 — 리스너(TEST_REST_WEEKDAYS)와 같게
_ALERTBOX_RE = re.compile(r'^https://toon\.at/widget/alertbox/([A-Za-z0-9_\-]{6,})/?$')


def _read(path):
    try:
        with open(path, encoding='utf-8') as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _key_of(url):
    m = _ALERTBOX_RE.match(str(url or '').strip().split('?')[0].split('#')[0])
    return m.group(1) if m else ''


def _mask(url):
    k = _key_of(url)
    return ('toon.at/widget/alertbox/••••' + k[-4:]) if k else ''


def view():
    cfg, st = _read(ACCOUNTS_FILE), _read(STATUS_FILE)
    url = str(cfg.get('test_url') or '')
    accs = st.get('accounts') if isinstance(st.get('accounts'), dict) else {}
    try:
        age = time.time() - float(st.get('updated') or 0)
    except (TypeError, ValueError):
        age = None
    return {'status': 'success',
            'test': {'set': bool(url), 'masked': _mask(url), 'enabled': cfg.get('enabled', True) is not False,
                     'resting_today': time.gmtime(time.time() + 9 * 3600).tm_wday in REST_WEEKDAYS},
            'listener': {'alive': bool(st) and age is not None and age < 60,
                         'age_sec': int(age) if (st and age is not None) else None,
                         'main': accs.get('main'), 'test': accs.get('test')}}


def _err(msg, code):
    return JSONResponse({'status': 'error', 'message': msg}, status_code=code)


@route('/api/toon/accounts', methods=('GET',))
async def get_accounts(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    return view()


@route('/api/toon/accounts', methods=('POST',))
async def set_accounts(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    try:
        body = await req.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return _err('JSON 객체가 필요합니다', 400)
    cfg = _read(ACCOUNTS_FILE)
    if 'test_url' in body:
        raw = str(body.get('test_url') or '').strip()
        if raw:
            key = _key_of(raw)
            if not key:
                return _err('투네이션 알림창 주소(https://toon.at/widget/alertbox/…)를 그대로 붙여 주세요', 400)
            if key == _key_of(os.environ.get('ALERTBOX_URL', '')):
                return _err('본 계정과 같은 주소예요 — 두 번째 계정의 알림창 주소를 넣어 주세요', 400)
            cfg['test_url'] = 'https://toon.at/widget/alertbox/' + key
            cfg['enabled'] = True
        else:
            cfg['test_url'] = ''
    if 'enabled' in body:
        cfg['enabled'] = bool(body.get('enabled'))
    cfg['updated'] = int(time.time())
    tmp = ACCOUNTS_FILE + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, ACCOUNTS_FILE)
    except Exception as e:
        return _err('설정을 저장하지 못했습니다: %s' % e, 500)
    return view()
