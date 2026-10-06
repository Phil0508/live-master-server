# -*- coding: utf-8 -*-
"""🔁 옛 주소 — 리스너(toon_listener.py)가 그대로 쓴다.

POST /api/donation {name, amount, message, tx_id, display_only}
  받아 주는 상대(옛 것과 같다): 이 서버 안(127.0.0.1, 앞단 프록시를 거치지 않은 것) · 로그인 · X-Donation-Key
  답(옛 모양): {status:'success', id} · {status:'success', message:'Duplicate donation ignored.'} · {status:'success', display_only:true}
⚠️ 시그니처 조회(바깥 왕복)는 여기서 — 명령 밖에서 — 하고 결과를 명령에 넘긴다.
"""
import asyncio
import hmac
import os

from fastapi.responses import JSONResponse

from .legacy import route

LOCAL_HOSTS = ('127.0.0.1', '::1', 'localhost')


def _local(req):
    host = req.client.host if req.client else ''
    return host in LOCAL_HOSTS and not req.headers.get('x-forwarded-for') and not req.headers.get('x-real-ip')


def _key_ok(req):
    want = os.environ.get('DONATION_KEY') or ''
    got = req.headers.get('x-donation-key') or ''
    return bool(want) and hmac.compare_digest(got, want)


def _err(msg, code):
    return JSONResponse({'status': 'error', 'message': msg}, status_code=code)


@route('/api/donation')
async def donation(req, bus, authed, answer):
    a = authed(req)
    if not (a or _local(req) or _key_ok(req)):
        return _err('후원 접수 권한이 없습니다', 401)
    try:
        body = await req.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return _err('JSON 객체가 필요합니다', 400)
    try:
        amount = int(body.get('amount'))
    except (TypeError, ValueError):
        return _err('금액이 숫자가 아닙니다', 400)
    if amount < 0:
        return _err('금액이 음수입니다', 400)
    tx = str(body.get('tx_id') or '')
    display = bool(body.get('display_only'))
    sig, floor = None, 0
    sigs = getattr(bus, 'sigs', None)
    if sigs is not None and amount > 0 and not display:
        floor = await asyncio.to_thread(sigs.floor)
        if not (floor and amount < floor):
            sig = await asyncio.to_thread(sigs.match, amount)
    res = await bus.run('donation.add', {'name': body.get('name'), 'amount': amount, 'message': body.get('message'),
                                         'tx_id': tx, 'display_only': display, 'sig': sig, 'floor': floor, 'trusted': a},
                        by='listener' if tx.startswith('toon_') else 'http', authed=True)
    if not res.get('ok'):
        return _err(res.get('error') or '실패', int(res.get('code') or 400))
    if res.get('duplicate'):
        return {'status': 'success', 'message': 'Duplicate donation ignored.'}
    if res.get('display_only'):
        return {'status': 'success', 'display_only': True}
    return {'status': 'success', 'id': res.get('id')}


@route('/api/signature/play')
async def signature_play(req, bus, authed, answer):
    """후원 콘솔 '바로 틀기' — 로그인 필요. {amount, name, message, count, sig_id?}"""
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    try:
        body = await req.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return _err('JSON 객체가 필요합니다', 400)
    try:
        amount = int(body.get('amount') or 0)
    except (TypeError, ValueError):
        return _err('금액이 숫자가 아닙니다', 400)
    sigs = bus.sigs
    sig, display = None, False
    if body.get('sig_id'):
        sig = await asyncio.to_thread(sigs.by_id, body.get('sig_id'))
    else:
        if amount <= 0:
            return _err('후원 금액을 입력해주세요.', 400)
        floor = await asyncio.to_thread(sigs.floor)
        if floor and amount < floor:
            display = True
        else:
            sig = await asyncio.to_thread(sigs.match, amount)
    res = await bus.run('signature.play', {'sig': sig, 'amount': amount, 'name': body.get('name'), 'message': body.get('message'),
                                           'count': body.get('count'), 'display': display}, by='console', authed=True)
    if not res.get('ok'):
        return _err(res.get('error') or '실패', int(res.get('code') or 400))
    if res.get('display_only'):
        return {'status': 'success', 'display_only': True, 'message': '제일 싼 시그니처보다 적어 시그니처 없이 방송판에 띄웠습니다'}
    return {'status': 'success', 'message': '송출했습니다.', 'count': res.get('count'), 'title': res.get('title')}


@route('/api/signatures', methods=('GET',))
async def signatures(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    rows = await asyncio.to_thread(bus.sigs.rows)
    floor = await asyncio.to_thread(bus.sigs.floor)
    return {'status': 'success', 'signatures': rows, 'count': len(rows), 'floor': floor}   # floor 미만은 화면에만
