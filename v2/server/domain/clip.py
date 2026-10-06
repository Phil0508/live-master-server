# -*- coding: utf-8 -*-
"""✂️ 쇼츠 클립 — OBS 리플레이 버퍼로 '그 순간 앞 90초 + 뒤 90초' 저장(옛 features/clip.py 를 옮겼다).

대표님 09-28 "9시간 방송으로 쇼츠를 몇 개 만들 수 있게" · 09-30 "누르는 순간 기준 전 90초 ~ 후 90초".
OBS 는 다른 컴퓨터(회사)에 있다. 조종실은 OBS 에 직접 못 붙는다 → OBS 안에 이미 들어가 있는 **방송판(브라우저 소스)** 이
window.obsstudio.saveReplayBuffer() 로 대신 말한다(OBS 에서 그 소스에 '고급 접근 권한' 을 줬을 때만 먹는다).
언제 저장할지(순간 90초 뒤 · 30초 안에 붙은 순간은 파일 하나)는 방송판이 정한다 — web/overlay/widgets/more/clip.js.
서버는 목록(무엇이 언제)과 설정만 적는다.

조각
  clip      (공개)   auto(큰 시그 · 올클리어 때 저절로) · auto_min(기준 금액, 기본 10만 원) ·
                     ask{id, at(ms), label, delay_ms} — 조종실 [✂ 클립]. 방송판은 id 가 바뀌면 한 번 예약한다
  clip_log  (비공개) name_fmt(파일 이름 규칙) · log[{id, ts(ms), kind(manual|auto), label, ref, name, saved_at(ms)}] 최근 60
  clip_key  (숨김)   feed — 회사 PC 도우미가 목록을 읽는 읽기 전용 열쇠(도우미를 받을 때 만든다)
순간은 셋(옛 것과 같다)
  ① 조종실 [✂ 클립](clip.now) ② 기준 금액 이상 시그니처가 **실제로 재생될 때** ③ 시그뒤집기 올클리어
  ②③ 은 방송판이 재생 · 연출 시각을 보고 스스로 건다. 서버는 목록에 '이런 순간이 곧 나온다' 를 적어 둔다 —
  시그는 대기줄에 새 줄로 들어갈 때(×N 으로 묶인 후원은 이미 적힌 한 줄로 충분), 올클리어는 그 순간.
OBS 쪽 '저장 담당' 상태는 메모리에만 둔다(장부 · 조각에 안 쓴다 — 1분마다 오는 알림이 쪽지를 만들지 않게).

주소
  GET  /api/clip            (로그인) 설정 · 목록 · OBS 상태(조종실이 20초마다 읽는다)
  POST /api/clip/hello      (로그인 없이) 방송판이 '권한 · 리플레이 버퍼 · 저장됨' 을 알린다 — 좁게 받는다(아래)
  GET  /api/clip/helper.zip (로그인) 회사 PC 도우미(v2/tools/clip_helper) — 서버 주소 · 읽기 열쇠를 박아 준다
  GET  /api/clip/feed?k=    (읽기 열쇠 또는 로그인) 도우미가 3초마다 읽는 것 — 이름 규칙 · 목록 · 서버 시각
명령: clip.now{label?, delay_ms?} · clip.settings{auto?, auto_min?, name_fmt?, clear?} · clip.rename{id, name} ·
      clip.saved{refs}(hello 가 부른다) · clip.feed_key{renew?}(도우미 받을 때)
⚠️ 옛 도우미는 무인증 /api/data(상태 통째)를 읽었다. v2 는 목록만 · 열쇠를 박은 도우미만 읽는다.
"""
import hmac
import io
import os
import secrets
import time
import uuid
import zipfile

from fastapi.responses import JSONResponse, Response

from .. import bus as busmod
from ..bus import CommandError, command
from ..state import slice_
from . import siggame as sg
from .legacy import route

CLIP_LOG_MAX = 60
CLIP_AUTO_DEFAULT = 100000
CLIP_AUTO_MAX = 100000000
# 📁 파일 이름 규칙 — 회사 PC 도우미가 리플레이 파일을 모을 폴더로 옮기며 이 규칙대로 이름을 붙인다.
#    {날짜} 2026-10-01 · {시각} 21-14-50 · {제목} 클립 제목(조종실에서 고친 것, 없으면 이유) · {번호} 그날 몇 번째
CLIP_NAME_FMT_DEFAULT = '{날짜} {시각} {제목}'
OBS_FRESH_SEC = 90               # 방송판은 1분마다 알린다 — 90초 넘게 소식이 없으면 '안 보임'
HELLO_REFS_MAX = 10
HELPER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tools', 'clip_helper')

slice_('clip', True, lambda: {'auto': True, 'auto_min': CLIP_AUTO_DEFAULT, 'ask': None})
slice_('clip_log', False, lambda: {'name_fmt': CLIP_NAME_FMT_DEFAULT, 'log': []})
slice_('clip_key', False, lambda: {'feed': ''}, hidden=True)


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _one_line(v, n):
    return ' '.join(str(v or '').replace('\n', ' ').split())[:n]


def _log(ctx, kind, label, ref=None):
    """목록에 한 줄. 방송이 끝나면 '어느 파일이 뭐였나' 를 이 시각으로 맞춘다.
       ref — 방송판이 '이것을 저장했다' 고 알려 올 때 쓰는 열쇠(직접 = 이 줄 id · 큰 시그 = 대기줄 id · 올클리어 = allclear:시각)."""
    cid = uuid.uuid4().hex[:10]
    log = ctx.edit('clip_log')['log']
    log.append({'id': cid, 'ts': int(ctx.now * 1000), 'kind': kind, 'label': str(label or '')[:60],
                'ref': str(ref or cid)[:40], 'name': '', 'saved_at': 0})
    del log[:-CLIP_LOG_MAX]
    return cid


# ── 방송판(OBS) '저장 담당' 상태 — 서버 메모리에만(bus 에 붙여 둔다. 검사마다 서버가 따로라 섞이지 않게) ──
def _obs(bus):
    o = getattr(bus, 'clip_obs', None)
    if o is None:
        o = {'seen': 0.0, 'level': -1, 'rb': None, 'saved': 0.0, 'err': ''}
        bus.clip_obs = o
    return o


def obs_view(bus):
    o = dict(_obs(bus))
    now = time.time()
    o['alive'] = bool(o['seen']) and (now - o['seen'] < OBS_FRESH_SEC)
    o['seen_ago'] = int(now - o['seen']) if o['seen'] else None
    o['saved_ago'] = int(now - o['saved']) if o['saved'] else None
    return o


# ── 명령 ──
@command('clip.now')
def clip_now(ctx, data):
    """조종실 [✂ 클립] · 스트림덱 — 목록에 적고, 방송판에게 '지금 순간' 을 알린다(ask). 저장은 방송판이 90초 뒤에."""
    label = _one_line(data.get('label'), 60) or '✂ 직접 누름'
    delay = max(0, min(60000, _int(data.get('delay_ms'), 0)))
    cid = _log(ctx, 'manual', label)
    ctx.edit('clip')['ask'] = {'id': cid, 'at': int(ctx.now * 1000), 'label': label, 'delay_ms': delay}
    ctx.notes.update({'id': cid, 'obs': obs_view(ctx.bus)})


@command('clip.settings')
def clip_settings(ctx, data):
    if 'auto' in data:
        ctx.edit('clip')['auto'] = bool(data.get('auto'))
    if 'auto_min' in data:
        ctx.edit('clip')['auto_min'] = max(0, min(CLIP_AUTO_MAX, _int(data.get('auto_min'), CLIP_AUTO_DEFAULT)))
    if 'name_fmt' in data:
        f = str(data.get('name_fmt') or '').replace('\n', ' ').strip()[:80]
        ctx.edit('clip_log')['name_fmt'] = f or CLIP_NAME_FMT_DEFAULT
    if data.get('clear'):
        ctx.edit('clip_log')['log'] = []


@command('clip.rename')
def clip_rename(ctx, data):
    """클립 제목 고치기 — 도우미가 모은 폴더의 파일 이름도 따라 바뀐다(도우미가 3초마다 읽는다)."""
    cid = str(data.get('id') or '')
    log = ctx.read('clip_log')['log']
    i = next((k for k, x in enumerate(log) if x.get('id') == cid), None)
    if i is None:
        raise CommandError('없는 클립입니다', 404)
    ctx.edit('clip_log')['log'][i]['name'] = _one_line(data.get('name'), 60)


@command('clip.saved')
def clip_saved(ctx, data):
    """방송판이 OBS 저장을 확인했다 — 열쇠가 맞는 줄에 저장 시각을 적는다(이미 적힌 줄은 그대로).
       /api/clip/hello 가 좁게 걸러서 부른다(권한 있는 방송판 · 열쇠 10개 · 40자)."""
    refs = {str(r)[:40] for r in (data.get('refs') or [])[:HELLO_REFS_MAX] if isinstance(r, (str, int))}
    log = ctx.read('clip_log')['log']
    hit = [k for k, x in enumerate(log) if (x.get('ref') in refs or x.get('id') in refs) and not x.get('saved_at')]
    if hit:
        at = int(ctx.now * 1000)
        rows = ctx.edit('clip_log')['log']
        for k in hit:
            rows[k]['saved_at'] = at
    ctx.notes['hit'] = len(hit)


@command('clip.feed_key')
def clip_feed_key(ctx, data):
    """도우미가 목록을 읽을 열쇠 — 없으면 만든다. renew 면 새로(옛 도우미는 못 읽게 된다)."""
    k = ctx.read('clip_key').get('feed') or ''
    if not k or data.get('renew'):
        k = secrets.token_urlsafe(18)
        ctx.put('clip_key', {'feed': k})
    ctx.notes['key'] = k


# ── 저절로 적기: ② 큰 시그(대기줄에 새로 들어온 줄) · ③ 올클리어 ──
def _follow_queue(ctx):
    """명령 하나가 끝난 뒤(bus.AFTER) — 대기줄에 기준 금액 이상의 **새 줄** 이 생겼으면 '곧 나올 순간' 으로 적는다.
       ⚠️ 실제 저장은 방송판이 재생을 시작한 뒤 건다(대기줄이 밀리면 재생은 한참 뒤다)."""
    q = ctx.read('queue')
    before = ctx.bus.state.get('queue')
    if q is before:                      # 이 명령은 대기줄을 안 건드렸다
        return
    c = ctx.read('clip')
    floor = _int(c.get('auto_min'), 0)
    if not c.get('auto') or floor <= 0:
        return
    old = {x.get('id') for x in (before.get('items') or [])}
    for it in q.get('items') or []:
        amt = _int(it.get('amount'), 0)
        if it.get('id') in old or amt < floor:
            continue
        label = '%s %s원 %s' % (it.get('donator') or '익명', format(amt, ','), it.get('title') or '')
        _log(ctx, 'auto', label.strip(), ref=it.get('id'))


def _on_allclear(ctx, n):
    if not ctx.read('clip').get('auto'):
        return
    act = ctx.read('siggame').get('action') or {}
    ts = _int(act.get('ts'), int(ctx.now * 1000))
    _log(ctx, 'auto', '시그뒤집기 올클리어 (%d장)' % n, ref='allclear:%d' % ts)


busmod.AFTER.append(_follow_queue)
sg.ON_ALLCLEAR.append(_on_allclear)


# ── 주소 ──
def _err(msg, code):
    return JSONResponse({'status': 'error', 'message': msg}, status_code=code)


def _view(bus):
    c, cl = bus.state.get('clip'), bus.state.get('clip_log')
    return {'auto': c.get('auto', True), 'auto_min': c.get('auto_min', CLIP_AUTO_DEFAULT),
            'name_fmt': cl.get('name_fmt') or CLIP_NAME_FMT_DEFAULT, 'log': cl.get('log') or []}


@route('/api/clip', methods=('GET',))
async def clip_get(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    return {'status': 'success', 'clip': _view(bus), 'obs': obs_view(bus)}


@route('/api/clip/hello')
async def clip_hello(req, bus, authed, answer):
    """방송판(OBS 브라우저 소스)이 '저장 담당' 상태를 알린다 — 로그인 없이(방송판은 로그인이 없다).
       ⚠️ 받는 것은 숫자 · 참거짓 몇 개뿐이고 메모리에만 적는다.
          여러 방송판이 알려 오면 권한이 가장 높은 쪽을 믿는다(권한 없는 쪽이 덮어써 깜빡이지 않게).
       💾 저장 확인(saved + refs)은 권한 있는 방송판(4 이상)일 때만 · 열쇠 10개(각 40자)까지 ·
          이미 있는 줄의 saved_at 한 칸만 바꾼다. 없는 열쇠는 무시한다."""
    try:
        b = await req.json()
    except Exception:
        b = None
    if not isinstance(b, dict):
        b = {}
    lv = max(-1, min(5, _int(b.get('level'), -1)))
    now = time.time()
    o = _obs(bus)
    fresh = o['seen'] and now - o['seen'] < OBS_FRESH_SEC
    if fresh and lv < o['level']:
        return {'status': 'success', 'kept': True}
    o.update(seen=now, level=lv, rb=b.get('rb') if isinstance(b.get('rb'), bool) else None, err=str(b.get('err') or '')[:80])
    saved = b.get('saved') is True
    if saved:
        o['saved'] = now
    refs = b.get('refs') if isinstance(b.get('refs'), list) else []
    refs = [str(r)[:40] for r in refs[:HELLO_REFS_MAX] if isinstance(r, (str, int)) and not isinstance(r, bool)]
    # 맞는 줄이 있을 때만 명령을 부른다 — 로그인 없는 길이라 헛된 알림이 장부(events)를 채우지 않게(한 줄은 한 번만 적힌다)
    log = bus.state.get('clip_log').get('log') or []
    if saved and refs and lv >= 4 and any((x.get('ref') in refs or x.get('id') in refs) and not x.get('saved_at') for x in log):
        await bus.run('clip.saved', {'refs': refs}, by='overlay', authed=True)
    return {'status': 'success'}


@route('/api/clip/feed', methods=('GET',))
async def clip_feed(req, bus, authed, answer):
    """회사 PC 도우미가 3초마다 읽는다 — 이름 규칙 · 목록 · 서버 시각(파일 시각과 맞출 때 PC 시계 어긋남을 잰다)."""
    want = bus.state.get('clip_key').get('feed') or ''
    got = req.query_params.get('k') or ''
    if not (authed(req) or (want and hmac.compare_digest(got, want))):
        return _err('도우미 열쇠가 맞지 않습니다 — 조종실 클립 탭에서 도우미를 다시 받아 주세요', 401)
    v = _view(bus)
    log = [{k: x.get(k) for k in ('id', 'ts', 'kind', 'label', 'name', 'saved_at')} for x in v['log']]
    return {'status': 'success', 'clip': {'name_fmt': v['name_fmt'], 'log': log}, 'server_time': int(time.time() * 1000)}


def _server_url(req):
    host = req.headers.get('x-forwarded-host') or req.headers.get('host') or req.url.netloc
    scheme = req.headers.get('x-forwarded-proto') or req.url.scheme
    if not host.startswith(('127.0.0.1', 'localhost')):
        scheme = 'https'
    return '%s://%s' % (scheme, host)


def build_helper_zip(server, key):
    """도우미 묶음 — .ps1 에는 서버 주소 · 읽기 열쇠를 박는다(PowerShell 5.1 은 BOM 이 있어야 한글을 읽는다)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(HELPER_DIR)):
            p = os.path.join(HELPER_DIR, fn)
            if not os.path.isfile(p):
                continue
            with open(p, 'rb') as f:
                data = f.read()
            if fn.endswith('.ps1'):
                txt = data.decode('utf-8-sig').replace('__SERVER__', server).replace('__FEEDKEY__', key)
                data = b'\xef\xbb\xbf' + txt.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8')
            elif fn.endswith(('.bat', '.txt')):
                data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            z.writestr('shorts_clip_helper/' + fn, data)
    return buf.getvalue()


@route('/api/clip/helper.zip', methods=('GET',))
async def clip_helper_zip(req, bus, authed, answer):
    """회사 PC(OBS 있는 곳)에서 켜 둘 도우미 — 리플레이 파일을 고른 폴더로 옮기며 이름을 붙인다.
       ⚠️ 윈도우 기본 PowerShell 로 돈다(설치 없음). 서버 주소는 받는 순간의 주소로 박아 준다."""
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    if not os.path.isdir(HELPER_DIR):
        return _err('도우미 파일이 없습니다(v2/tools/clip_helper)', 500)
    res = await bus.run('clip.feed_key', {}, by='http', authed=True)
    if not res.get('ok'):
        return _err(res.get('error') or '열쇠를 만들지 못했습니다', 500)
    body = build_helper_zip(_server_url(req), res['key'])
    return Response(body, media_type='application/zip',
                    headers={'Content-Disposition': 'attachment; filename=shorts_clip_helper.zip'})
