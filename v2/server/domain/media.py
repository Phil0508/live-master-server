# -*- coding: utf-8 -*-
"""🎞️ 계좌 고액후원 영상 · 🎤 노래방 — 방송판에 영상을 띄우는 것들.

조각
  acct_video (공개) tiers[{min, label, video}] (옛 금액대 그대로) · now{video, label, at} | None
  karaoke    (공개) on · video(유튜브 id 또는 주소) · at · volume(영상 음량 0~100, 기본 70 — 옛 karaoke_volume)
옛 규칙 그대로
  - 계좌 영상은 운영자가 구간을 **골라서** 튼다(자동 매칭 없음 — 배정 · 시그니처와 순서가 뒤엉켰다).
  - 영상 파일은 Supabase 보관소(media 버킷)에 올린다 — 60MB · mp4/webm/mov/m4v. 올리기는 명령 **밖**에서(바깥 왕복).
  - 방송판은 영상이 떠 있는 동안 계좌 줄을 영상 뒤로 보낸다(10-05 고친 것 — 방송판 쪽 일).
"""
import asyncio
import time

from fastapi.responses import JSONResponse

from ..bus import CommandError, command
from ..state import slice_
from .legacy import route
from .signatures import _supabase_config

TIERS = [(200000, '20만'), (300000, '30만'), (400000, '40만'), (500000, '50만'), (600000, '60~70만'),
         (800000, '80~90만'), (1000000, '100만'), (2000000, '200만'), (3000000, '300만'), (5000000, '500만')]
VIDEO_TYPES = {'mp4': 'video/mp4', 'webm': 'video/webm', 'mov': 'video/quicktime', 'm4v': 'video/x-m4v'}
VIDEO_MAX_MB = 60
BUCKET = 'media'

slice_('acct_video', True, lambda: {'tiers': [{'min': m, 'label': l, 'video': ''} for m, l in TIERS], 'now': None})
slice_('karaoke', True, lambda: {'on': False, 'video': '', 'at': 0, 'volume': 70})


@command('acctvid.play')
def acctvid_play(ctx, data):
    tiers = ctx.read('acct_video')['tiers']
    try:
        i = int(data.get('tier'))
    except (TypeError, ValueError):
        raise CommandError('구간 번호가 필요합니다')
    if not 0 <= i < len(tiers):
        raise CommandError('없는 구간입니다')
    t = tiers[i]
    if not t.get('video'):
        ctx.notes.update({'played': False, 'reason': 'no_video', 'label': t['label']})
        return
    ctx.edit('acct_video')['now'] = {'video': t['video'], 'label': t['label'], 'at': int(ctx.now * 1000)}
    ctx.notes.update({'played': True, 'label': t['label']})


@command('acctvid.stop')
def acctvid_stop(ctx, data):
    ctx.edit('acct_video')['now'] = None


@command('acctvid.ended', auth=False)
def acctvid_ended(ctx, data):
    """방송판이 영상을 다 틀었다 — 지금 틀고 있는 그 영상(at)일 때만 내린다."""
    now = ctx.read('acct_video')['now']
    if now and int(data.get('at') or 0) == now['at']:
        ctx.edit('acct_video')['now'] = None
    else:
        ctx.notes['ignored'] = True


@command('acctvid.set')
def acctvid_set(ctx, data):
    av = ctx.edit('acct_video')
    try:
        i = int(data.get('tier'))
    except (TypeError, ValueError):
        raise CommandError('구간 번호가 필요합니다')
    if not 0 <= i < len(av['tiers']):
        raise CommandError('없는 구간입니다')
    t = av['tiers'][i]
    if 'video' in data:
        t['video'] = str(data.get('video') or '').strip()[:500]
    if 'label' in data:
        t['label'] = ' '.join(str(data.get('label') or '').split())[:20] or t['label']


@command('karaoke.play')
def karaoke_play(ctx, data):
    v = str(data.get('video') or '').strip()
    if not v:
        raise CommandError('유튜브 링크를 넣어 주세요')
    # ⚠️ 통째로 갈지 않는다 — 음량(volume)은 켜고 끌 때마다 남아야 한다(옛 karaoke_volume 처럼 방송이 바뀌어도)
    ctx.edit('karaoke').update({'on': True, 'video': v[:300], 'at': int(ctx.now * 1000)})


@command('karaoke.stop')
def karaoke_stop(ctx, data):
    ctx.edit('karaoke')['on'] = False


@command('karaoke.volume')
def karaoke_volume(ctx, data):
    """🎤 노래방 영상 음량 0~100(유튜브 척도, 옛 기본 70) — 부르는 사람 목소리와 균형을 잡는 값."""
    try:
        v = float(data.get('volume'))
    except (TypeError, ValueError):
        raise CommandError('음량은 0~100 숫자입니다')
    if v != v:
        raise CommandError('음량이 숫자가 아닙니다')
    ctx.edit('karaoke')['volume'] = int(max(0, min(100, round(v))))


def _upload(path, raw, ctype):
    import requests
    url, key = _supabase_config()
    if not url or not key:
        raise RuntimeError('영상 보관소(Supabase)가 설정되지 않았습니다')
    r = requests.post('%s/storage/v1/object/%s/%s' % (url, BUCKET, path), data=raw, timeout=120,
                      headers={'apikey': key, 'Authorization': 'Bearer ' + key, 'Content-Type': ctype,
                               'Cache-Control': 'public, max-age=31536000, immutable', 'x-upsert': 'true'})
    if r.status_code not in (200, 201):
        raise RuntimeError('보관소 올리기 실패 %s: %s' % (r.status_code, r.text[:200]))
    return '%s/storage/v1/object/public/%s/%s' % (url, BUCKET, path)


@route('/api/account/video/upload')
async def upload(req, bus, authed, answer):
    """금액대 한 칸에 영상 파일 — form: tier, file. 올리기(바깥)는 명령 밖, 주소 적기만 명령으로."""
    if not authed(req):
        return JSONResponse({'status': 'error', 'message': '로그인이 필요합니다'}, status_code=401)
    form = await req.form()
    try:
        i = int(form.get('tier'))
    except (TypeError, ValueError):
        return JSONResponse({'status': 'error', 'message': '구간 번호가 필요합니다'}, status_code=400)
    f = form.get('file')
    if f is None or not getattr(f, 'filename', ''):
        return JSONResponse({'status': 'error', 'message': '영상 파일을 골라 주세요'}, status_code=400)
    ext = (f.filename.rsplit('.', 1)[-1] or '').lower()
    if ext not in VIDEO_TYPES:
        return JSONResponse({'status': 'error', 'message': '%s 형식은 쓸 수 없습니다 (mp4 · webm · mov · m4v)' % (ext or '?')}, status_code=400)
    raw = await f.read()
    mb = len(raw) / 1024 / 1024
    if not raw or mb > VIDEO_MAX_MB:
        return JSONResponse({'status': 'error', 'message': '빈 파일이거나 %dMB 를 넘습니다' % VIDEO_MAX_MB}, status_code=400)
    tiers = bus.state.get('acct_video')['tiers']
    if not 0 <= i < len(tiers):
        return JSONResponse({'status': 'error', 'message': '없는 구간입니다'}, status_code=400)
    try:
        url = await asyncio.to_thread(_upload, 'videos/acct_%s.%s' % (tiers[i]['min'], ext), raw, VIDEO_TYPES[ext])
    except Exception as e:
        return JSONResponse({'status': 'error', 'message': str(e)}, status_code=503)
    url += '?v=%d' % int(time.time())
    res = await bus.run('acctvid.set', {'tier': i, 'video': url}, by='upload', authed=True)
    return answer(dict(res, url=url, size_mb=round(mb, 1), status='success' if res.get('ok') else 'error'))
