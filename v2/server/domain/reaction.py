# -*- coding: utf-8 -*-
"""🎵 시그니처 재생 대기줄.

queue 조각(공개): items[{id, sig_id, title, sig_amount, audio_url, image_url, duration, amount, donator, message,
                        count, play_all, skip_popup, play_after}] · paused · volume
- 맨 앞(items[0])이 방송판에서 재생 중인 것이다.
- play_after = 이 시각(ms, epoch) 전에는 틀지 않는다(슬롯 당첨은 릴이 다 선 뒤에 나온다). 0 이면 바로.
- 같은 시그니처를 같은 사람이 연달아 보내면 마지막 줄에 ×N 으로 묶는다(옛 것과 같다).
- 방송판이 다 틀면 reaction.done {id} — **로그인 없이** 부른다. 맨 앞 id 가 맞을 때만 뺀다(늦게 온 보고 · 두 화면 보고는 무시).
- 📺 방송판이 실제로 틀기 시작하면 reaction.started {id, replay} — **로그인 없이**(done 과 같은 방송판이 보낸다).
  맨 앞 id · 회차(replay)가 맞을 때만 맨 앞에 started {replay, at(서버 ms)} 를 한 번 적는다(두 화면이 보내도 처음 것만).
  출연진 전광판(?only=sig)이 이것을 보고 방송판과 같이 뜬다(10-17 — 옛 것은 맨 앞이 되자마자 그려 2~3초 먼저 떴다).
  바꾸는 것은 그 칸 하나뿐 — 순서 · 재생 · 점수에는 아무 영향이 없다.
- 대기줄은 40줄까지. 넘치면 재생 중인 것 다음(가장 오래 기다린 것)부터 뺀다.
- 💬 묶일 때 메시지는 후원마다 msgs 에 차례대로 모은다(빈 메시지도 자리를 지킨다, 30개까지 — 옛 10-11 5d179b0).
  혼자인 줄은 message 하나. 방송판이 [N번 다 틀기]면 틀 때마다 그 차례 메시지, 한 번만 틀면 다 같이 보여 준다.
- 🏷️💙 extra — 첫 줄을 만들 때만 실린다(옛 것과 같다): donor_title · donor_level(칭호 · Lv) · via:'toon'(투네 딱지).
- 🔁 끝난 묶음 기억(reaction_done_recent — 비공개 조각, 옛 features/reaction.py _RECENT_DONE): 다 틀고 빠진(또는 건너뛴)
  줄 중 ×N(전체 2번 이상)만 30개까지. [N번 다 틀기]를 이미 빠진 줄에 누르면 남은 만큼을 '지금 나오는 것 바로 다음'에
  이어 틀기 줄(again_of · seq_base(이미 튼 수) · seq_total · skip_popup)로 세운다. 방송 시작 · 끝에 비운다.
  이어 틀기 줄 필드: 옛 줄을 그대로 베끼고 id 새로 · count = 남은 수 · play_all · seq_base · seq_total · again_of.
"""
import uuid

from ..bus import CommandError, command
from ..state import slice_
from . import cast
from . import donation as dn
from . import session as ses
from .rules import QUEUE_MAX, norm_donor

REACTION_MSGS_MAX = 30       # 묶음 한 줄에 모아 둘 메시지 수(옛 server.py 와 같다) — 큐 전체가 쪽지마다 모든 화면에 나간다
RECENT_DONE_MAX = 30         # 끝난 묶음 기억 수(옛 _RECENT_DONE maxlen)

slice_('queue', True, lambda: {'items': [], 'paused': False, 'volume': 0.5})
slice_('reaction_done_recent', False, lambda: {'items': []})


def enqueue(ctx, sig, amount=0, donator='', message='', skip_popup=False, play_after=0, count_tally=True, extra=None, don_id=''):
    """don_id — 이 줄을 만든 후원(장부 id). 묶이면 don_ids 가 msgs 와 같은 차례로 쌓인다(🙈 [가리기]가 그 차례만 숨긴다 — mask.py)."""
    q = ctx.edit('queue')
    items = q['items']
    last = items[-1] if items else None
    fx_new = isinstance(extra, dict) and bool(extra.get('fx_video'))     # 🏦🐉 대형 연출이 붙은 후원은 앞줄에 안 묶는다(연출이 사라지지 않게)
    if (count_tally and not skip_popup and not play_after and not fx_new and last and not last.get('skip_popup') and not last.get('play_after')
            and str(last.get('sig_id')) == str(sig.get('id')) and norm_donor(last.get('donator')) == norm_donor(donator)):
        last['count'] += 1
        # 💬 메시지는 후원마다 따로 모은다 — 예전엔 첫 메시지만 남아 '아버지' 다음 '어머니' 가 화면 어디에도 안 떴다(대표님 10-11)
        msgs = last.get('msgs')
        if not isinstance(msgs, list):
            msgs = [str(last.get('message') or '')]
        if len(msgs) < REACTION_MSGS_MAX:
            msgs.append(str(message or ''))
            ids = last.get('don_ids') if isinstance(last.get('don_ids'), list) else [''] * (len(msgs) - 1)
            ids = (ids + [''] * len(msgs))[:len(msgs) - 1] + [str(don_id or '')]
            last['don_ids'] = ids
        last['msgs'] = msgs
    else:
        items.append({'id': 'rq_' + uuid.uuid4().hex, 'sig_id': sig.get('id'), 'title': sig.get('title') or '시그니처',
                      'sig_amount': int(sig.get('amount') or 0), 'audio_url': sig.get('sound_url') or '',
                      'image_url': sig.get('image_url') or '', 'duration': float(sig.get('duration') or 10),
                      'amount': int(amount or 0), 'donator': donator, 'message': message, 'count': 1, 'play_all': False,
                      'skip_popup': bool(skip_popup), 'play_after': int(play_after or 0)})
        if don_id:
            items[-1]['don_ids'] = [str(don_id)]
        if isinstance(extra, dict):
            new = items[-1]
            new.update({k: v for k, v in extra.items() if k not in new})      # 정해진 칸은 못 덮는다
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
        _remember_done(ctx, q['items'].pop(0))


@command('reaction.started', auth=False)
def started(ctx, data):
    """📺 방송판이 맨 앞을 실제로 틀기 시작했다 — 출연진 전광판이 따라 뜬다. 맨 앞 · 회차가 맞을 때 한 번만."""
    items = ctx.read('queue')['items']
    try:
        rep = int(data.get('replay') or 0)
    except (TypeError, ValueError):
        ctx.notes['ignored'] = True
        return
    if not items or items[0]['id'] != data.get('id') or int(items[0].get('replay') or 0) != rep:
        ctx.notes['ignored'] = True
        return
    st = items[0].get('started')
    if isinstance(st, dict) and int(st.get('replay') or 0) == rep:
        ctx.notes['ignored'] = True             # 이미 적었다(두 화면 · 다시 보냄) — 쪽지를 또 안 낸다
        return
    ctx.edit('queue')['items'][0]['started'] = {'replay': rep, 'at': int(ctx.now * 1000)}


def played_total(it):
    """이 줄이 빠지는 순간 — (지금까지 튼 수, 모두 몇 번). 이어 틀기 줄은 앞에서 튼 만큼(seq_base)을 더한다.
       v2 는 '다 틀기' 때 count 를 하나씩 줄이고 replay 를 올리므로: 튼 수 = seq_base + replay + 1, 모두 = seq_base + replay + count."""
    base, rep, cnt = int(it.get('seq_base') or 0), int(it.get('replay') or 0), max(1, int(it.get('count') or 1))
    return base + rep + 1, base + rep + cnt


def _remember_done(ctx, it):
    """🔁 방금 끝난 묶음(×N) — 조종실이 '이미 한 번 나갔는데 N번 다 틀어야 했다' 할 때 남은 만큼 이어 틀려고(옛 _RECENT_DONE)."""
    played, total = played_total(it)
    if total <= 1:
        return
    r = ctx.edit('reaction_done_recent')
    r['items'] = (r.get('items') or []) + [dict(it, played=played, total=total, ended_at=int(ctx.now * 1000))]
    del r['items'][:-RECENT_DONE_MAX]


@command('reaction.skip')
def skip(ctx, data):
    q = ctx.edit('queue')
    if not q['items']:
        raise CommandError('재생 중인 시그니처가 없습니다', 404)
    _remember_done(ctx, q['items'].pop(0))         # 옛 것도 건너뛰기(/api/reaction/next)를 '끝난 것' 으로 기억했다


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
    """🔁 묶인 시그니처(×N)를 N번 다 틀지. on=false 면 다시 '한 번 + ×N'. 지금 틀고 있는 묶음에 눌러도 된다.
       이미 대기줄에서 빠졌으면(끝난 묶음 기억에 있으면) 남은 만큼을 지금 나오는 것 바로 다음에 이어 튼다(옛 것과 같다)."""
    q = ctx.edit('queue')
    rid = data.get('id')
    on = bool(data.get('on', True))
    it = next((x for x in q['items'] if x['id'] == rid), None)
    if it is not None:
        it['play_all'] = on
        ctx.notes.update({'play_all': on, 'count': int(it.get('count') or 1)})
        return
    rec = ctx.read('reaction_done_recent').get('items') or []
    old = next((x for x in reversed(rec) if x.get('id') == rid), None)
    if old is None:
        raise CommandError('이 시그니처는 끝난 지 오래돼 이어서 틀 수 없어요 — 시그니처 송출 칸에서 × 몇 번으로 다시 보내 주세요', 404)
    if not on:
        ctx.notes.update({'play_all': False, 'count': 0})
        return
    played, total = int(old.get('played') or 1), int(old.get('total') or 1)
    remaining = total - played
    if remaining <= 0:
        raise CommandError('이미 %d번 다 틀었어요' % total, 409)
    nw = {k: v for k, v in old.items() if k not in ('played', 'total', 'ended_at', 'replay', 'started')}
    nw.update({'id': 'rq_' + uuid.uuid4().hex, 'count': remaining, 'play_all': True, 'skip_popup': True,
               'seq_base': played, 'seq_total': total, 'again_of': rid, 'play_after': 0})
    q['items'].insert(1 if q['items'] else 0, nw)
    r = ctx.edit('reaction_done_recent')
    r['items'] = [x for x in r['items'] if x.get('id') != rid]      # 두 번 눌러 두 번 이어 틀지 않게
    ctx.notes.update({'id': nw['id'], 'play_all': True, 'count': remaining, 'again': True, 'seq_base': played, 'seq_total': total})


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
    if ctx.read('reaction_done_recent').get('items'):
        ctx.put('reaction_done_recent', {'items': []})      # 지난 방송의 묶음은 이어 틀 일이 없다(옛 것은 서버를 다시 켜면 비었다)


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
        from . import players as pl
        pl.set_donation_popup(ctx, {'id': 'man_%d' % int(ctx.now * 1000), 'name': name, 'amount': amount, 'message': msg,
                                    'at': int(ctx.now * 1000), 'display_only': True})
        ctx.notes['display_only'] = True
        return
    sig = data.get('sig')
    if not sig:
        raise CommandError('재생할 시그니처를 찾지 못했습니다', 404)
    fx = cast.bank_fx(data.get('bank_total')) if data.get('bank_total') is not None else {}     # 🏦🐉 계좌 카드에서 '시그니처만' 보낼 때
    if data.get('bank_total') is not None:
        fx['via'] = 'bank'                                                                     # 💙🏦 조종실 대기열 딱지(방송판엔 안 보인다)
    enqueue(ctx, sig, amount=amount or int(sig.get('amount') or 0), donator=name, message=msg, count_tally=False, extra=fx or None)
    ctx.edit('queue')['items'][-1]['count'] = count
    if fx.get('fx_video'):
        ctx.notes['fx_video'] = fx['fx_video']
    ctx.notes.update({'title': sig.get('title'), 'count': count})
