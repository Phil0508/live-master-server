# -*- coding: utf-8 -*-
"""🎵 시그니처 재생 대기줄.

queue 조각(공개): items[{id, sig_id, title, sig_amount, audio_url, image_url, duration, amount, donator, message,
                        count, play_all, skip_popup, play_after}] · paused · volume
- 맨 앞(items[0])이 방송판에서 재생 중인 것이다.
- play_after = 이 시각(ms, epoch) 전에는 틀지 않는다(슬롯 당첨은 릴이 다 선 뒤에 나온다). 0 이면 바로.
- 같은 시그니처를 같은 사람이 연달아 보내면 마지막 줄에 ×N 으로 묶는다(옛 것과 같다).
- 방송판이 다 틀면 reaction.done {id} — **로그인 없이** 부른다. 맨 앞 id 가 맞을 때만 뺀다(늦게 온 보고 · 두 화면 보고는 무시).
- 대기줄은 40줄까지. 넘치면 재생 중인 것 다음(가장 오래 기다린 것)부터 뺀다.
"""
import uuid

from ..bus import CommandError, command
from ..state import slice_
from . import donation as dn
from . import session as ses
from .rules import QUEUE_MAX, norm_donor

slice_('queue', True, lambda: {'items': [], 'paused': False, 'volume': 0.5})


def enqueue(ctx, sig, amount=0, donator='', message='', skip_popup=False, play_after=0, count_tally=True):
    q = ctx.edit('queue')
    items = q['items']
    last = items[-1] if items else None
    if (count_tally and not skip_popup and not play_after and last and not last.get('skip_popup') and not last.get('play_after')
            and str(last.get('sig_id')) == str(sig.get('id')) and norm_donor(last.get('donator')) == norm_donor(donator)):
        last['count'] += 1
    else:
        items.append({'id': 'rq_' + uuid.uuid4().hex, 'sig_id': sig.get('id'), 'title': sig.get('title') or '시그니처',
                      'sig_amount': int(sig.get('amount') or 0), 'audio_url': sig.get('sound_url') or '',
                      'image_url': sig.get('image_url') or '', 'duration': float(sig.get('duration') or 10),
                      'amount': int(amount or 0), 'donator': donator, 'message': message, 'count': 1, 'play_all': False,
                      'skip_popup': bool(skip_popup), 'play_after': int(play_after or 0)})
        while len(items) > QUEUE_MAX:
            items.pop(1)
    if count_tally:
        t = ctx.edit('tallies')
        st = t['sigs'].setdefault(str(sig.get('id')), {'title': sig.get('title') or '', 'image_url': sig.get('image_url') or '',
                                                      'amount': int(sig.get('amount') or 0), 'count': 0, 'donors': {}})
        st['count'] += 1
        k = norm_donor(donator)
        st['donors'][k] = st['donors'].get(k, 0) + 1


dn.ENQUEUE.append(enqueue)


@command('reaction.done', auth=False)
def done(ctx, data):
    """방송판이 다 틀었다 — 맨 앞이 그 id 일 때만. ×N 을 '다 틀기' 로 해 뒀으면 하나 줄이고 다시 튼다."""
    items = ctx.read('queue')['items']
    if not items or items[0]['id'] != data.get('id'):
        ctx.notes['ignored'] = True
        return
    head0 = items[0]
    if head0.get('play_all') and head0['count'] > 1 and data.get('replay') is not None             and int(data.get('replay')) != int(head0.get('replay') or 0):
        ctx.notes['ignored'] = True          # 다른 화면이 이미 이 회차를 끝냈다(두 화면이 두 번 깎지 않게)
        return
    q = ctx.edit('queue')
    head = q['items'][0]
    if head.get('play_all') and head['count'] > 1:
        head['count'] -= 1
        head['replay'] = int(head.get('replay') or 0) + 1      # 방송판이 '같은 것을 한 번 더' 로 알아보게
    else:
        q['items'].pop(0)


@command('reaction.skip')
def skip(ctx, data):
    q = ctx.edit('queue')
    if not q['items']:
        raise CommandError('재생 중인 시그니처가 없습니다', 404)
    q['items'].pop(0)


@command('reaction.stop')
def stop(ctx, data):
    ctx.edit('queue')['items'] = []


@command('reaction.pause')
def pause(ctx, data):
    q = ctx.edit('queue')
    q['paused'] = bool(data['paused']) if 'paused' in data else not q['paused']


@command('reaction.remove')
def remove(ctx, data):
    q = ctx.edit('queue')
    before = len(q['items'])
    q['items'] = [x for x in q['items'] if x['id'] != data.get('id')]
    if len(q['items']) == before:
        raise CommandError('대기줄에 없습니다', 404)


@command('reaction.playall')
def playall(ctx, data):
    q = ctx.edit('queue')
    it = next((x for x in q['items'] if x['id'] == data.get('id')), None)
    if it is None:
        raise CommandError('대기줄에 없습니다', 404)
    it['play_all'] = bool(data.get('on', True))


@command('reaction.volume')
def volume(ctx, data):
    try:
        v = float(data.get('volume'))
    except (TypeError, ValueError):
        raise CommandError('볼륨은 0~1 숫자입니다')
    ctx.edit('queue')['volume'] = max(0.0, min(1.0, v))


def _reset(ctx, data):
    q = ctx.edit('queue')
    q['items'], q['paused'] = [], False


ses.ON_START.append(_reset)
ses.ON_END.append(_reset)


@command('signature.play')
def signature_play(ctx, data):
    """후원 콘솔 '바로 틀기'(장부 없음) — 옛 /api/signature/play 와 같다.
       sig 는 명령 밖에서 미리 찾아 온다. 최저선 미만이면(시그니처를 고르지 않았을 때) 화면에만 띄운다.
       재생 전용이라 '오늘의 시그니처' 집계에는 안 넣는다(count_tally=False). ×N 은 한 줄에 count=N."""
    name = ' '.join(str(data.get('name') or '').split())[:20] or '수동송출'
    msg = str(data.get('message') or '').strip()[:120]
    amount = int(data.get('amount') or 0)
    try:
        count = max(1, min(30, int(data.get('count') or 1)))
    except (TypeError, ValueError):
        count = 1
    if data.get('display'):
        ctx.edit('popup')['donation'] = {'id': 'man_%d' % int(ctx.now * 1000), 'name': name, 'amount': amount, 'message': msg,
                                         'at': int(ctx.now * 1000), 'display_only': True}
        ctx.notes['display_only'] = True
        return
    sig = data.get('sig')
    if not sig:
        raise CommandError('재생할 시그니처를 찾지 못했습니다', 404)
    enqueue(ctx, sig, amount=amount or int(sig.get('amount') or 0), donator=name, message=msg, count_tally=False)
    ctx.edit('queue')['items'][-1]['count'] = count
    ctx.notes.update({'title': sig.get('title'), 'count': count})
