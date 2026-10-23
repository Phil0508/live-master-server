# -*- coding: utf-8 -*-
"""🔁 옛 주소 — 리스너(toon_listener.py)가 그대로 쓴다.

POST /api/donation {name, amount, message, tx_id, display_only, title?, level?, vip?, donor_key?, replay?, test?}
  받아 주는 상대(옛 것과 같다): 이 서버 안(127.0.0.1, 앞단 프록시를 거치지 않은 것) · 로그인 · X-Donation-Key
  답(옛 모양): {status:'success', id} · {status:'success', message:'Duplicate donation ignored.'} · {status:'success', display_only:true}
              · {status:'success', show_only:'replay'|'test'}(다시 보기 · 후원 테스트 — 화면에만)
              로그인한 조종실의 손 송출(tx manual_)이면 장부 줄 번호 no 를 더한다(후원 콘솔 토스트 '#12 로 들어갔어요')
POST /api/donation/replay {id} — ↻ 장부 줄 하나를 방송 화면에만 한 번 더(로그인, donation.replay)
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
    cmd = {'name': body.get('name'), 'amount': amount, 'message': body.get('message'),
           'tx_id': tx, 'display_only': display, 'sig': sig, 'floor': floor, 'trusted': a}
    # 🏷️🔁 리스너가 붙여 보내는 칸(10-08 ~) — 칭호 · 레벨 · 투네이션 VIP · 번호표 · 다시 보기 · 후원 테스트.
    #    ⚠️ 예전(10-17 전 v2)엔 여기서 버려서 다시 보기가 진짜 후원으로 장부에 들어갔다. 믿을지는 명령이 정한다(리스너 toon_ 만).
    for k in ('title', 'level', 'vip', 'donor_key', 'replay', 'test'):
        if k in body:
            cmd[k] = body[k]
    if a and 'bank_total' in body:
        cmd['bank_total'] = body['bank_total']          # 🏦🐉 계좌 입금 대형 연출 — 로그인한 후원 콘솔만(donation.add 가 manual_bank_ 인지 본다)
    res = await bus.run('donation.add', cmd, by='listener' if tx.startswith('toon_') else 'http', authed=True)
    if not res.get('ok'):
        return _err(res.get('error') or '실패', int(res.get('code') or 400))
    if res.get('duplicate'):
        return {'status': 'success', 'message': 'Duplicate donation ignored.'}
    # 🏷️ 장부 줄 번호 — 로그인한 조종실의 손 송출(manual_ — 후원 콘솔 토스트)에만 알려 준다. 리스너 답 모양은 옛 것 그대로
    no = {'no': res['no']} if a and tx.startswith('manual_') and res.get('no') else {}
    if res.get('display_only'):
        return dict({'status': 'success', 'display_only': True}, **no)
    if res.get('show_only'):
        return dict({'status': 'success', 'show_only': res['show_only']}, **no)          # 옛 답 모양 그대로(화면에만)
    # 📚 계좌 카드 [채우기] → [송출](tx_id manual_bank_<카드id>[_N]) — 그 카드의 입금자명 = 보낸 이름을 배운다(로그인한 조종실만).
    #    같은 카드는 첫 이름만(×N · 나눠 보내기). 실패해도 후원은 그대로 — 기록엔 이름 · 실명을 안 남긴다.
    if a and tx.startswith('manual_bank_'):
        from . import bank, bank_learn
        bank.learn_card(bus.store, bank_learn.card_of_tx(tx), body.get('name'))
    return dict({'status': 'success', 'id': res.get('id')}, **no)


@route('/api/donation/replay')
async def donation_replay(req, bus, authed, answer):
    """↻ 다시 송출 — 로그인 필요. {id}(장부 줄 id). 시그니처는 명령 밖에서 금액으로 다시 맞춘다(바로 틀기와 같은 셈 —
       최저선 미만이면 시그니처 없이). 시그니처 목록을 못 받으면 팝업만 띄운다(화면에만이라 실패로 막지 않는다)."""
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    try:
        body = await req.json()
    except Exception:
        body = None
    if not isinstance(body, dict) or not body.get('id'):
        return _err('어느 후원인지(id) 필요합니다', 400)
    d = bus.store.donation(str(body.get('id')))
    sig, floor = None, 0
    sigs = getattr(bus, 'sigs', None)
    amount = int((d or {}).get('amount') or 0)
    if d and sigs is not None and amount > 0:
        try:
            floor = await asyncio.to_thread(sigs.floor)
            if not (floor and amount < floor):
                sig = await asyncio.to_thread(sigs.match, amount)
        except Exception as e:
            print('⚠️ [다시 송출] 시그니처 찾기 실패 — 팝업만: %s' % type(e).__name__, flush=True)
            sig, floor = None, 0
    res = await bus.run('donation.replay', {'id': str(body.get('id')), 'sig': sig, 'floor': floor}, by='console', authed=True)
    if not res.get('ok'):
        return _err(res.get('error') or '실패', int(res.get('code') or 400))
    return {'status': 'success', 'id': res.get('id'), 'no': res.get('no'), 'of_no': res.get('of_no'), 'title': res.get('title') or ''}


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
                                           'count': body.get('count'), 'display': display,
                                           'bank_total': body.get('bank_total') if body.get('bank') else None}, by='console', authed=True)
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
