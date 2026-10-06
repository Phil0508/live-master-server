# -*- coding: utf-8 -*-
"""💰 후원 — 받기 · 대기함 · 선수에게 주기 · 무시 · 집계.

조각
  pending (비공개) 대기함 [{id, name, orig_name, amount, message, at, kind?, contrib?, test?}]
  tallies (공개)  donors{정규화 이름: {name, total, count}} · best(한 방 최고) · notice_donors(소액 띠) · sigs(오늘의 시그니처)

받기(donation.add) 순서 — 옛 것과 같다
  1) 같은 tx_id 가 장부에 있으면 한 번으로(장부 표의 UNIQUE 가 지킨다 — 옛 것은 메모리 목록이라 재시작하면 잊었다)
  2) 리스너(toon_)가 아니면 12초 안의 같은 이름 · 금액 · 메시지는 한 번으로
  3) 화면에만(display_only · 리스너 · 1만 원 미만) → 팝업만, 대기함 · 점수 · 집계 없음
  4) 이름 보정(이름이 없을 때만 '닉네임: 내용') → 대기함 · 장부 · 팝업 · 집계
  5) 시그니처 — 최저선 미만이면 안 틀고 소액 띠로, 아니면 대기줄(reaction)
"""
import time
import uuid

from ..bus import CommandError, command
from ..state import slice_
from . import players as pl
from . import session as ses
from .rules import DEDUPE_WINDOW, NOTICE_DONORS_MAX, SMALL_DISPLAY_MAX, derive_name, man_won, norm_donor, split_points

slice_('pending', False, lambda: [])
slice_('tallies', True, lambda: {'donors': {}, 'best': None, 'notice_donors': [], 'sigs': {}})

ENQUEUE = []        # 시그니처 대기줄에 넣는 함수(reaction 모듈이 건다)
AFTER_DONATION = []  # 후원 하나가 장부에 들어간 뒤(특별 후원자 등급 다시 매기기 등)
ON_ASSIGN = []       # 🤖 대기함 카드를 준 뒤 fn(ctx, 그 카드, 받은 items, 보낸 data) — 무인 방송 그림자 채점(autopilot.py)
ON_IGNORE = []       # 🤖 대기함 카드를 무시한 뒤 fn(ctx, 그 카드) — 같은 곳


def _did(now):
    return 'don_%d_%s' % (int(now * 1000), uuid.uuid4().hex[:6])


@command('donation.add')
def donation_add(ctx, data):
    """옛 주소(/api/donation)가 부른다 — 시그니처 매칭(sig) · 최저선(floor)은 명령 밖에서 미리 구해 온다."""
    tx = str(data.get('tx_id') or '').strip()
    try:
        amount = int(data.get('amount'))
    except (TypeError, ValueError):
        raise CommandError('금액이 숫자가 아닙니다')
    if amount < 0:
        raise CommandError('금액이 음수입니다')
    name_in, msg_in = str(data.get('name') or ''), str(data.get('message') or '')
    if tx and ctx.store.donation_by_tx(tx):
        ctx.notes.update({'duplicate': True})
        return
    from_listener = tx.startswith('toon_')
    if not from_listener and not (tx.startswith('manual_') and data.get('trusted')):
        since = ctx.now - DEDUPE_WINDOW
        for d in ctx.store.donations(limit=30):
            if d['at'] >= since and d['name'] == derive_name(name_in, msg_in, tx)[0] and d['amount'] == amount \
                    and d['message'] == derive_name(name_in, msg_in, tx)[2]:
                ctx.notes.update({'duplicate': True})
                return
    sid = ses.session_id(ctx)
    did = _did(ctx.now)
    # 화면에만 — 1만 원 미만(리스너가 표시해 보낸 것)
    if data.get('display_only') and from_listener and 0 < amount < SMALL_DISPLAY_MAX:
        nm = ' '.join(name_in.split()) or '익명'
        ctx.store.add_donation({'id': did, 'tx_id': tx or None, 'at': ctx.now, 'name': nm, 'amount': amount,
                                'message': msg_in.strip(), 'source': 'display', 'status': 'display', 'player': None, 'session': sid})
        ctx.edit('popup')['donation'] = {'id': did, 'name': nm, 'amount': amount, 'message': msg_in.strip(),
                                         'at': int(ctx.now * 1000), 'display_only': True}
        ctx.notes.update({'id': did, 'display_only': True})
        return
    name, orig, msg = derive_name(name_in, msg_in, tx)
    test = tx.startswith('toon_t2_')
    item = {'id': did, 'name': name, 'orig_name': orig, 'amount': amount, 'message': msg, 'at': int(ctx.now * 1000)}
    if test:
        item['test'] = True
    ctx.edit('pending').append(item)
    ctx.store.add_donation({'id': did, 'tx_id': tx or None, 'at': ctx.now, 'name': name, 'amount': amount, 'message': msg,
                            'source': 'toonation_test' if test else ('toonation' if from_listener else 'manual'),
                            'status': 'pending', 'player': None, 'session': sid})
    ctx.edit('popup')['donation'] = {'id': did, 'name': name, 'amount': amount, 'message': msg, 'at': int(ctx.now * 1000)}
    t = ctx.edit('tallies')
    key = norm_donor(name)
    dt = t['donors'].setdefault(key, {'name': name, 'total': 0, 'count': 0})
    dt['total'] += max(0, amount)
    dt['count'] += 1
    dt['name'] = name
    if amount > 0 and (not t['best'] or amount > t['best']['amount']):
        t['best'] = {'name': name, 'amount': amount, 'at': int(ctx.now * 1000), 'id': did, 'member': ''}
    floor = int(data.get('floor') or 0)
    sig = data.get('sig')
    if amount > 0 and floor and amount < floor:
        t['notice_donors'].append({'name': name.replace('*', '')[:16], 'amount': amount, 'ts': int(ctx.now * 1000)})
        del t['notice_donors'][:-NOTICE_DONORS_MAX]
    elif sig and amount > 0:
        for fn in ENQUEUE:
            fn(ctx, sig, amount=amount, donator=name, message=msg)
    ctx.notes.update({'id': did})
    for fn in AFTER_DONATION:
        fn(ctx, name, amount)


def _take_pending(ctx, pid):
    pend = ctx.edit('pending')
    it = next((x for x in pend if x['id'] == pid), None)
    if it is None:
        return None
    pend.remove(it)
    return it


@command('pending.assign')
def pending_assign(ctx, data):
    """대기함 후원을 선수에게. {id, name} · {id, names:[…]}(나눠 주기) · {id, items:[{name, delta, contrib}]}.
       기본: 점수 = 기여도 = 만 원 단위(man_won). 기여도 카드(kind:'contrib')는 점수 0 · 기여도 = 카드 값."""
    pid = data.get('id')
    it = next((x for x in ctx.read('pending') if x['id'] == pid), None)
    if it is None:
        ctx.notes['already'] = True            # 이미 처리된 것 — 두 번 눌러도 한 번
        return
    if data.get('items'):
        items = [{'name': x.get('name'), 'delta': int(x.get('delta') or 0),
                  'contrib': int(x['contrib']) if x.get('contrib') is not None else None} for x in data['items']]
    else:
        names = data.get('names') or ([data.get('name')] if data.get('name') else [])
        if not names:
            raise CommandError('누구에게 줄지 골라 주세요')
        if it.get('kind') == 'contrib':
            parts = split_points(int(it.get('contrib') or 0), len(names))
            items = [{'name': n, 'delta': 0, 'contrib': v} for n, v in zip(names, parts)]
        else:
            parts = split_points(man_won(it['amount']), len(names))
            items = [{'name': n, 'delta': v, 'contrib': v} for n, v in zip(names, parts)]
    pl.apply_scores(ctx, items, reason='후원 %s' % it['name'], ref=pid, popup=data.get('popup', True) is not False,
                    takeover=True, want_list=data.get('list'))
    _take_pending(ctx, pid)
    who = ' · '.join(x['name'] for x in items)[:60]
    if ctx.store.donation(pid):
        ctx.store.set_donation(pid, status='assigned', player=who)
    t = ctx.read('tallies')
    if t.get('best') and t['best'].get('id') == pid:
        ctx.edit('tallies')['best']['member'] = ' · '.join(x['name'] for x in items[:3])
    for fn in ON_ASSIGN:
        fn(ctx, it, items, data)


@command('pending.ignore')
def pending_ignore(ctx, data):
    it = _take_pending(ctx, data.get('id'))
    if it is None:
        ctx.notes['already'] = True
        return
    if ctx.store.donation(it['id']):
        ctx.store.set_donation(it['id'], status='ignored')
    for fn in ON_IGNORE:
        fn(ctx, it)


def _undo_back_to_pending(ctx, ref):
    """후원 배정을 되돌리면 그 후원이 대기함 맨 앞으로 돌아온다(옛 것은 사라졌다)."""
    if not str(ref).startswith('don_'):
        return
    d = ctx.store.donation(ref)
    if not d or d['status'] != 'assigned':
        return
    ctx.store.set_donation(ref, status='pending', player=None)
    if not any(x['id'] == ref for x in ctx.read('pending')):
        ctx.edit('pending').insert(0, {'id': ref, 'name': d['name'], 'orig_name': d['name'], 'amount': d['amount'],
                                       'message': d['message'], 'at': int(d['at'] * 1000), 'returned': True})
    t = ctx.read('tallies')
    if t.get('best') and t['best'].get('id') == ref:
        ctx.edit('tallies')['best']['member'] = ''


pl.ON_UNDO.append(_undo_back_to_pending)


def _reset(ctx, data):
    ctx.put('pending', [])
    ctx.put('tallies', {'donors': {}, 'best': None, 'notice_donors': [], 'sigs': {}})


ses.ON_START.append(_reset)
ses.ON_END.append(_reset)


def add_pending_card(ctx, name, contrib, message='', kind='contrib', front=False, **extra):
    """게임 결과(주사위 · 슬롯 카드 등)를 대기함에 '기여도 카드' 로 올린다 — 조종실이 받을 선수를 고른다.
       옛 것과 같다: 점수 0 · 기여도 = contrib. 배정은 pending.assign 이 한다(kind:'contrib' 이면 기여도만).
       돌려받는 값: 카드 id"""
    cid = '%s_%d_%s' % ('dg' if kind == 'contrib' else kind, int(ctx.now * 1000), uuid.uuid4().hex[:6])
    item = dict({'id': cid, 'name': str(name or ''), 'orig_name': str(name or ''), 'amount': 0, 'message': str(message or ''),
                 'at': int(ctx.now * 1000), 'kind': kind, 'contrib': int(contrib or 0)}, **extra)
    pend = ctx.edit('pending')
    if front:
        pend.insert(0, item)
    else:
        pend.append(item)
    return cid
