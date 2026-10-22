# -*- coding: utf-8 -*-
"""💬 조종 연출 — 화면에 한마디 · UP 자막 · 👑 조종실 후원 연출(이펙트 탭). 방송판에 '한 번 쏘는' 신호만 담는다.

cast 조각(공개 — 방송판이 그린다) — 쏠 때마다 그 칸의 id 가 하나 오른다(방송판은 id 가 바뀐 칸만 그린다):
  say       {id, text, at}   💬 화면에 한마디 — 옛 features/say.py /api/say(10-07). 가운데 궁서 · 흰 글씨 · 검은 테두리 1초.
                             60자까지 · 줄바꿈 · 겹친 띄어쓰기는 한 칸(옛 것 그대로). 방송 전에도 뜬다(옛 것은 신호만 쐈다).
  up        {id, text, at}   ⬆ UP 자막 — 옛 조종실 랭킹 탭 칸 · 폰 '📢 전광판'(gd.up_trigger). 가운데 금색 큰 글씨 2초.
                             옛 방송판은 방송 중일 때만 그렸다('방송 꺼짐 return' 뒤) — v2 칸도 liveOnly.
  fx        {id, kinds, name, amount, message, at}
                             👑 조종실 후원 연출 — 옛 features/effects.py /api/effect/fire · 후원 콘솔 '이펙트' 탭.
                             kinds: banner(큰 배너) · flash(번쩍 + 테두리 빛) · ticker(전광판 문구) · card(화면 전체 카드) ·
                                    shock(충격파 + 흔들림) · glitch(네온 글리치) · warn(비상 경보) — 방송판이 그릴 줄 아는 것만 받는다.
  fx_clear  {id, at}         🧹 [걷기] — 쏜 연출을 바로 걷는다(옛 /api/effect/clear).
⚠️ 시그니처 · 목표 달성 연출과 섞지 않는다(옛 것도 따로 쐈다 — 끼어들면 서로를 끊었다). 상태(점수 · 대기줄)는 안 바꾼다.
⚠️ 방송판이 다시 붙을 때 지난 신호가 다시 터지지 않게, 방송판은 '지금 막 온 것'(또는 그 연출 시간 안의 것)만 그린다.
"""
from ..bus import CommandError, command
from ..state import slice_

SAY_MAX = 60          # 1초에 읽을 수 있는 만큼(옛 SAY_MAX)
UP_MAX = 60
FX_KINDS = ('banner', 'flash', 'ticker', 'card', 'shock', 'glitch', 'warn')
FX_NAME_MAX, FX_MSG_MAX = 40, 120

slice_('cast', True, lambda: {'say': None, 'up': None, 'fx': None, 'fx_clear': None, 'video': None, 'n': 0})

# 🐉 대형 연출 영상(10-23 대표님 — 드리미나로 만든 영상, 검은 배경을 뺀 투명 webm) — 방송판 widgets/cast/video.js 가 /overlay/fxvideos/<이름>.webm 을 튼다
VIDEO_FX = {'dragon': '🐉 용 연출'}


def _one_line(v, n):
    return ' '.join(str(v or '').split())[:n]


def _fire(ctx, key, row):
    c = ctx.edit('cast')
    c['n'] = int(c.get('n') or 0) + 1
    row.update({'id': c['n'], 'at': int(ctx.now * 1000)})
    c[key] = row
    ctx.notes[key] = row


@command('cast.say')
def say(ctx, data):
    text = _one_line(data.get('text'), SAY_MAX)
    if not text:
        raise CommandError('띄울 글을 써 주세요')
    _fire(ctx, 'say', {'text': text})
    print('💬 [화면에 한마디] "%s"' % text[:30], flush=True)


@command('cast.up')
def up(ctx, data):
    text = _one_line(data.get('text'), UP_MAX)
    if not text:
        raise CommandError('화면에 띄울 문구를 먼저 입력해 주세요')
    _fire(ctx, 'up', {'text': text})


@command('cast.fx')
def fx(ctx, data):
    kinds = data.get('kinds') or []
    if isinstance(kinds, str):
        kinds = [kinds]
    if not isinstance(kinds, (list, tuple)):
        kinds = []
    # 방송판이 그릴 줄 아는 연출만 — 오타로 아무 일도 안 일어나는 것을 막는다(옛 allowed). 순서는 표 순서, 겹친 것은 하나로
    kinds = [k for k in FX_KINDS if k in [str(x) for x in kinds]]
    if not kinds:
        raise CommandError('연출을 하나 이상 골라 주세요')
    try:
        amount = max(0, int(float(data.get('amount') or 0)))
    except (TypeError, ValueError):
        amount = 0
    _fire(ctx, 'fx', {'kinds': kinds, 'name': _one_line(data.get('name'), FX_NAME_MAX), 'amount': amount,
                      'message': _one_line(data.get('message'), FX_MSG_MAX)})


@command('cast.fx_clear')
def fx_clear(ctx, data):
    _fire(ctx, 'fx_clear', {})


@command('cast.video')
def video(ctx, data):
    """🐉 대형 연출 영상 틀기 {name} — 방송 화면 위에 투명 영상(용 연출 등)을 한 번."""
    name = str(data.get('name') or '')
    if name not in VIDEO_FX:
        raise CommandError('모르는 연출 영상입니다: %s' % name[:20])
    _fire(ctx, 'video', {'name': name})


@command('cast.video_stop')
def video_stop(ctx, data):
    """틀고 있는 연출 영상을 바로 걷는다."""
    _fire(ctx, 'video', {'name': '', 'stop': True})
