# -*- coding: utf-8 -*-
"""🔑 로그인 — 비밀번호 하나(대표님 혼자 쓰는 도구 · 옛 서버와 같다).

- 로그인하면 서명한 쿠키(lm2)를 준다. 서명 열쇠는 SESSION_SECRET.
- 도구 · 검사는 `Authorization: Bearer <SESSION_SECRET>` 로도 된다(옛 서버와 같은 약속).
- 방송판(OBS)은 로그인 없이 공개 조각만 본다.
"""
import base64
import hashlib
import hmac
import time

COOKIE = 'lm2'
MAX_AGE = 60 * 60 * 24 * 30      # 30일


def _sig(secret, body):
    return hmac.new(secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).hexdigest()[:32]


def make_cookie(secret):
    body = base64.urlsafe_b64encode(str(int(time.time())).encode()).decode()
    return body + '.' + _sig(secret, body)


def check_cookie(secret, value):
    try:
        body, sig = str(value or '').rsplit('.', 1)
        if not hmac.compare_digest(sig, _sig(secret, body)):
            return False
        at = int(base64.urlsafe_b64decode(body.encode()).decode())
        return time.time() - at < MAX_AGE
    except Exception:
        return False


def is_authed(secret, cookies, headers, query=None):
    if check_cookie(secret, (cookies or {}).get(COOKIE)):
        return True
    h = (headers or {}).get('authorization') or ''
    if h.startswith('Bearer ') and hmac.compare_digest(h[7:].strip(), secret):
        return True
    t = (query or {}).get('token')
    return bool(t) and hmac.compare_digest(str(t), secret)
