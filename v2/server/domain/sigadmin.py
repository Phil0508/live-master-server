# -*- coding: utf-8 -*-
"""🎵 시그니처 관리 — 등록 · 고치기 · 지우기 (옛 features/signatures.py · upload.html · 후원 콘솔 '시그니처 관리').

주소 (옛 주소는 같은 모양 — form 으로 받고 {status, message, signature} 로 답한다)
  GET  /api/sigadmin/list                  (로그인) 목록을 보관소에서 새로 받아 준다 · 최저선 · 보관소 설정 여부
  POST /api/signatures/add                 (로그인) form: title, amount, duration, image?, sound?, allow_dup?
  POST /api/signatures/update/{id}         (로그인) form: title?, amount?, duration?, image?, sound?, allow_dup?
  POST /api/signatures/delete/{id}         (로그인) 행만 지운다 — 파일은 남기고 지운 행은 sig_admin.log 에 보관
  POST /api/sigadmin/restore {lid}         (로그인) 지운 것 되살리기(되도록 같은 번호로)
  POST /api/sigadmin/revert  {lid}         (로그인) 고친 것 되돌리기(고치기 전 값으로)
조각
  sig_admin (비공개) ver — 목록이 바뀔 때마다 +1(다른 기기의 조종실이 보고 목록을 다시 받는다) · log[최근 바뀐 것, 새것이 앞]
    log 한 줄: {lid, at, act(add|edit|delete|restore|revert), id, title, amount, before?, after?, row?, of?, restored?, reverted?}

옛 규칙 그대로
  - 금액은 0보다 커야 한다. 제목이 비면 '10,000원 시그니처'. 재생 시간 기본 10초(음원이 없을 때 사진을 보여 줄 시간).
  - 새로 등록할 때는 사진이나 음원 중 하나는 있어야 한다.
  - 사진은 WebP 로 줄여(긴 변 1280) 올린다 — Pillow 가 없거나 못 읽으면 원본 그대로.
  - 음원 형식은 파일 이름(확장자)으로 정한다 — 브라우저가 보낸 형식은 믿지 않는다(octet-stream 이면 재생 못 하는 브라우저가 있다).
  - 파일 주소 끝에 ?v=시각 — 보관소 앞단(CDN)이 옛 파일을 계속 내주지 않게. 캐시는 1년(전송량 아끼기).
  - 요청 하나 80MB 까지(옛 서버 MAX_CONTENT_LENGTH).

v2 에서 더한 안전장치 — 08-13 시그니처 105번(60만 원)이 DB · 보관소 양쪽에서 사라졌다. 지금도 로컬 백업으로만 살릴 수 있다.
  ⚠️ 시그니처 보관소는 개발 · 방송이 **같이** 쓴다. 여기서 지우면 방송에서도 바로 사라진다.
  - 지우기는 '행만' 지운다. 사진 · 음원 파일은 보관소에 남기고, 지운 행 전체를 sig_admin.log 에 적어 둔다 → [되살리기].
    적어 두기가 먼저다 — 적지 못하면 지우지 않는다.
  - 파일을 바꿀 때 옛 파일을 지우지 않는다. 새 파일은 새 이름(…_v시각)으로 올려 옛 파일이 덮이지 않게 → [되돌리기].
  - 같은 금액이 이미 있으면 한 번 묻는다(409 · code:'dup') — 자동 매칭은 같은 금액 중 하나만 고른다.
  - 움짤(여러 장짜리 GIF · WebP · PNG)은 줄이지 않고 그대로 올린다 — 옛 서버는 첫 장만 남겨 멈춘 사진이 됐다.
  - 폰 사진은 돌려 찍은 방향(EXIF)을 반영해 줄인다 — 안 그러면 옆으로 누운 사진이 된다.
  - 등록 중 파일 올리기가 실패하면 방금 만든 행을 지운다 — 옛 서버는 사진 · 음원 없는 행이 남아 후원에 빈 시그니처가 걸렸다.
  - 바뀐 뒤에는 서버의 시그니처 목록(bus.sigs)을 바로 새로 받는다 — 다음 후원부터 새 목록으로 매칭한다(전에는 10분 기억).

⚠️ Supabase 왕복은 전부 명령 밖(asyncio.to_thread)에서 한다. 바깥 일은 아래 sb_* · storage_upload 만 한다 —
   검사(test_sigadmin.py)는 이 함수들을 가짜로 바꾼다. 다른 곳에서 requests 를 부르지 말 것.
"""
import asyncio
import io
import time

from fastapi.responses import JSONResponse

from ..bus import CommandError, command
from ..state import slice_
from .legacy import route
from .signatures import FIELDS, _supabase_config

BUCKET = 'media'
CACHE_CONTROL = 'public, max-age=31536000, immutable'
MAX_REQUEST_MB = 80
IMAGE_MAX_DIM, IMAGE_QUALITY = 1280, 82
TITLE_MAX = 60
DUR_DEFAULT, DUR_MIN, DUR_MAX = 10, 1, 600
AMOUNT_MAX = 100_000_000
LOG_KEEP = 40            # 최근 바뀐 것 — 이만큼은 다 남긴다
TRASH_KEEP = 200         # 그보다 오래된 것 중 '아직 안 되살린 지우기' 는 여기까지 남긴다(되살릴 길)
ROW_KEYS = ('id', 'amount', 'title', 'image_url', 'sound_url', 'duration')
EDIT_KEYS = ('amount', 'title', 'duration', 'image_url', 'sound_url')
ACTS = ('add', 'edit', 'delete', 'restore', 'revert')

AUDIO_TYPES = {'mp3': 'audio/mpeg', 'm4a': 'audio/mp4', 'aac': 'audio/aac', 'ogg': 'audio/ogg', 'oga': 'audio/ogg',
               'wav': 'audio/wav', 'webm': 'audio/webm', 'mp4': 'video/mp4', 'flac': 'audio/flac', 'opus': 'audio/ogg'}
IMAGE_TYPES = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'webp': 'image/webp',
               'bmp': 'image/bmp', 'avif': 'image/avif'}

slice_('sig_admin', False, lambda: {'ver': 0, 'log': []})


class BadInput(Exception):
    """사람에게 보여 줄 입력 오류(400)."""


# ══════════════════════════════════════════════════════════════
# 바깥(Supabase) — 이 함수들만 바깥으로 나간다. 검사는 전부 가짜로 바꾼다.
# ══════════════════════════════════════════════════════════════
def sb_ready():
    url, key = _supabase_config()
    return bool(url and key)


def _sb():
    url, key = _supabase_config()
    if not url or not key:
        raise RuntimeError('시그니처 보관소(Supabase)가 설정되지 않았습니다')
    return url, {'apikey': key, 'Authorization': 'Bearer ' + key}


def sb_get(sig_id):
    import requests
    url, hd = _sb()
    r = requests.get('%s/rest/v1/signatures?id=eq.%d&limit=1&select=%s' % (url, int(sig_id), FIELDS), headers=hd, timeout=8)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def sb_insert(fields):
    import requests
    url, hd = _sb()
    r = requests.post('%s/rest/v1/signatures' % url, json=fields, timeout=15,
                      headers=dict(hd, **{'Content-Type': 'application/json', 'Prefer': 'return=representation'}))
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def sb_update(sig_id, fields):
    import requests
    url, hd = _sb()
    r = requests.patch('%s/rest/v1/signatures?id=eq.%d' % (url, int(sig_id)), json=fields, timeout=15,
                       headers=dict(hd, **{'Content-Type': 'application/json', 'Prefer': 'return=representation'}))
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def sb_delete(sig_id):
    import requests
    url, hd = _sb()
    r = requests.delete('%s/rest/v1/signatures?id=eq.%d' % (url, int(sig_id)), headers=hd, timeout=15)
    r.raise_for_status()
    return True


def storage_upload(path, raw, ctype):
    """보관소(media 버킷)에 올리고 공개 주소를 돌려준다."""
    import requests
    url, hd = _sb()
    r = requests.post('%s/storage/v1/object/%s/%s' % (url, BUCKET, path), data=raw, timeout=120,
                      headers=dict(hd, **{'Content-Type': ctype, 'Cache-Control': CACHE_CONTROL, 'x-upsert': 'true'}))
    if r.status_code not in (200, 201):
        raise RuntimeError('보관소에 파일을 올리지 못했습니다 (%s): %s' % (r.status_code, r.text[:160]))
    return '%s/storage/v1/object/public/%s/%s' % (url, BUCKET, path)


# ══════════════════════════════════════════════════════════════
# 입력 손보기 — 바깥에 나가기 **전에** 다 검사한다(행을 만든 뒤 거절하면 빈 행이 남는다)
# ══════════════════════════════════════════════════════════════
def _ext(filename):
    n = str(filename or '')
    return n.rsplit('.', 1)[-1].lower().strip() if '.' in n else ''


def _int(v, what):
    s = str(v if v is not None else '').strip().replace(',', '').replace('원', '').replace(' ', '')
    try:
        return int(s)
    except ValueError:
        raise BadInput('%s 숫자로 넣어 주세요' % what)


def _amount(v):
    a = _int(v, '후원 금액은')
    if a <= 0:
        raise BadInput('후원 금액을 입력해주세요.')
    if a > AMOUNT_MAX:
        raise BadInput('후원 금액이 너무 큽니다')
    return a


def _duration(v):
    d = _int(v, '재생 시간은')
    if not DUR_MIN <= d <= DUR_MAX:
        raise BadInput('재생 시간은 %d~%d초로 넣어 주세요' % (DUR_MIN, DUR_MAX))
    return d


def _title(v):
    return ' '.join(str(v or '').split())[:TITLE_MAX]


def _given(v):
    return v is not None and str(v).strip() != ''


def _truthy(v):
    return str(v or '').strip().lower() in ('1', 'true', 'yes', 'on')


async def _file(f):
    """form 의 파일 칸 → (바이트, 파일 이름, 브라우저가 보낸 형식) · 비었으면 None"""
    if f is None or isinstance(f, str) or not getattr(f, 'filename', ''):
        return None
    raw = await f.read()
    if not raw:
        raise BadInput('빈 파일입니다: %s' % f.filename)
    return raw, f.filename, getattr(f, 'content_type', '') or ''


def prep_image(raw, filename, ctype):
    """사진 → (바이트, 확장자, 형식). 한 장짜리는 WebP 로 줄이고, 움짤은 그대로."""
    ext = _ext(filename)
    try:
        from PIL import Image, ImageOps
    except ImportError:
        Image = None
    if Image is not None:
        try:
            im = Image.open(io.BytesIO(raw))
            fmt = (im.format or '').lower()
            if getattr(im, 'is_animated', False) and int(getattr(im, 'n_frames', 1) or 1) > 1:
                e = {'gif': 'gif', 'webp': 'webp', 'png': 'png'}.get(fmt, ext)
                if e not in IMAGE_TYPES:
                    raise BadInput('이 움짤 형식은 쓸 수 없습니다 (gif · webp)')
                return raw, e, IMAGE_TYPES[e]
            try:
                im = ImageOps.exif_transpose(im)        # 폰으로 돌려 찍은 사진
            except Exception:
                pass
            if im.mode in ('P', 'LA'):
                im = im.convert('RGBA')
            elif im.mode not in ('RGB', 'RGBA'):
                im = im.convert('RGB')
            w, h = im.size
            scale = min(1.0, IMAGE_MAX_DIM / float(max(w, h) or 1))
            if scale < 1.0:
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format='WEBP', quality=IMAGE_QUALITY, method=6)
            return buf.getvalue(), 'webp', 'image/webp'
        except BadInput:
            raise
        except Exception:
            pass                                       # 못 읽는 사진 — 아래에서 확장자로 판단
    if ext not in IMAGE_TYPES:
        raise BadInput('사진 파일이 아닙니다 (png · jpg · gif · webp): %s' % (filename or '?'))
    return raw, ext, IMAGE_TYPES[ext]


def prep_sound(raw, filename, ctype):
    """음원 → (바이트, 확장자, 형식). 형식은 확장자로 — 모르는 확장자는 브라우저가 audio/… 라고 할 때만."""
    ext = _ext(filename)
    if ext in AUDIO_TYPES:
        return raw, ext, AUDIO_TYPES[ext]
    c = str(ctype or '').split(';')[0].strip().lower()
    if c.startswith('audio/'):
        sub = ''.join(ch for ch in c.split('/', 1)[1] if ch.isalnum())[:8] or 'audio'
        return raw, (ext if ext.isascii() and ext.isalnum() and len(ext) <= 8 else '') or sub, c
    raise BadInput('음원 파일이 아닙니다 (mp3 · m4a · wav · ogg · aac): %s' % (filename or '?'))


def _row(r):
    if not isinstance(r, dict):
        return None
    return {k: r.get(k) for k in ROW_KEYS}


def _dups(rows, amount, skip_id=None):
    return [{'id': r.get('id'), 'title': r.get('title'), 'amount': r.get('amount')} for r in (rows or [])
            if int(r.get('amount') or 0) == int(amount) and str(r.get('id')) != str(skip_id)]


def _why(e):
    """바깥 실패 → 사람 말. requests 오류 글자에는 주소가 섞이므로 종류만 말한다."""
    if isinstance(e, RuntimeError):
        return str(e)
    resp = getattr(e, 'response', None)
    if resp is not None and getattr(resp, 'status_code', None):
        return '보관소가 거절했습니다 (HTTP %s)' % resp.status_code
    return '보관소에 닿지 않습니다 (%s)' % type(e).__name__


def _err(msg, http, **extra):
    return JSONResponse(dict({'ok': False, 'status': 'error', 'message': msg, 'error': msg}, **extra), status_code=http)


def _ok(**kw):
    return dict({'ok': True, 'status': 'success'}, **kw)


def _too_big(req):
    try:
        return int(req.headers.get('content-length') or 0) > MAX_REQUEST_MB * 1024 * 1024
    except ValueError:
        return False


def _upload_files(sid, img, snd, versioned):
    """사진 · 음원 올리기 → {'image_url', 'sound_url'} 조각.
       versioned=True(고치기) — 새 이름(…_v시각)으로 올려 옛 파일이 덮이지 않게 한다(되돌리기용)."""
    ver = int(time.time() * 1000)
    stem = '%s_v%d' % (sid, ver) if versioned else str(sid)
    out = {}
    if img:
        data, ext, ctype = img
        out['image_url'] = storage_upload('images/%s.%s' % (stem, ext), data, ctype) + '?v=%d' % (ver // 1000)
    if snd:
        data, ext, ctype = snd
        out['sound_url'] = storage_upload('sounds/%s.%s' % (stem, ext), data, ctype) + '?v=%d' % (ver // 1000)
    return out


def _do_add(fields, img, snd):
    row = sb_insert(fields)
    if not row or row.get('id') is None:
        raise RuntimeError('시그니처 행을 만들지 못했습니다')
    sid = row['id']
    try:
        urls = _upload_files(sid, img, snd, versioned=False)
        row = sb_update(sid, urls) or dict(row, **urls)
    except Exception:
        try:
            sb_delete(sid)        # 방금 만든 빈 행 — 사진 · 음원 없는 시그니처가 후원에 걸리지 않게
        except Exception:
            pass
        raise
    return row


def _do_update(sid, fields, img, snd):
    fields = dict(fields, **_upload_files(sid, img, snd, versioned=True))
    return sb_update(sid, fields)


def _do_restore(row):
    fields = {k: row.get(k) for k in EDIT_KEYS if row.get(k) is not None}
    sid = row.get('id')
    if sid is not None:
        try:
            got = sb_insert(dict(fields, id=sid))
            if got:
                return got
        except Exception:
            try:                                   # 들어갔는데 답만 못 받았을 수도 — 두 번 넣지 않게 본다
                cur = sb_get(sid)
            except Exception:
                cur = None
            if cur and cur.get('title') == row.get('title') and int(cur.get('amount') or 0) == int(row.get('amount') or 0):
                return cur
    got = sb_insert(fields)                        # 같은 번호를 못 쓰면 새 번호로
    if not got:
        raise RuntimeError('되살리지 못했습니다')
    return got


async def _refresh(bus):
    """서버의 시그니처 목록(후원 매칭에 쓰는 것)을 지금 새로 받는다."""
    sigs = getattr(bus, 'sigs', None)
    if sigs is None:
        return []
    return await asyncio.to_thread(sigs.refresh)


async def _log(bus, **data):
    return await bus.run('sigadmin.log', data, by='sigadmin', authed=True)


def _entry(bus, lid):
    return next((e for e in (bus.state.get('sig_admin').get('log') or []) if e.get('lid') == lid), None)


# ══════════════════════════════════════════════════════════════
# 명령 — 기록만(바깥 일은 위 주소에서 끝낸 뒤 결과만 적는다)
# ══════════════════════════════════════════════════════════════
def _trim(log):
    out = []
    for i, e in enumerate(log):
        if i < LOG_KEEP or (e.get('act') == 'delete' and not e.get('restored')):
            out.append(e)
        if len(out) >= TRASH_KEEP:
            break
    return out


@command('sigadmin.log')
def sig_log(ctx, data):
    act = str(data.get('act') or '')
    if act not in ACTS:
        raise CommandError('모르는 기록입니다')
    sa = ctx.edit('sig_admin')
    sa['ver'] = int(sa.get('ver') or 0) + 1
    e = {'lid': '%d-%d' % (int(ctx.now * 1000), sa['ver']), 'at': int(ctx.now), 'act': act}
    for k in ('before', 'after', 'row'):
        r = _row(data.get(k))
        if r:
            e[k] = r
    main = e.get('after') or e.get('row') or e.get('before') or {}
    e.update({'id': main.get('id'), 'title': main.get('title'), 'amount': main.get('amount')})
    if data.get('of'):
        e['of'] = str(data.get('of'))[:40]
    sa['log'] = _trim([e] + list(sa.get('log') or []))
    ctx.notes['lid'] = e['lid']


@command('sigadmin.mark')
def sig_mark(ctx, data):
    """되살렸다(restored: 새 번호) · 되돌렸다(reverted: 되돌린 기록 lid) 표시."""
    sa = ctx.edit('sig_admin')
    e = next((x for x in sa.get('log') or [] if x.get('lid') == data.get('lid')), None)
    if not e:
        raise CommandError('기록을 찾지 못했습니다', 404)
    for k in ('restored', 'reverted'):
        if data.get(k) is not None:
            e[k] = data.get(k)
    sa['ver'] = int(sa.get('ver') or 0) + 1


@command('sigadmin.drop')
def sig_drop(ctx, data):
    """지우기가 실패했을 때 — 미리 적어 둔 '지운 것' 을 다시 뺀다."""
    sa = ctx.edit('sig_admin')
    sa['log'] = [x for x in sa.get('log') or [] if x.get('lid') != data.get('lid')]
    sa['ver'] = int(sa.get('ver') or 0) + 1


# ══════════════════════════════════════════════════════════════
# 주소
# ══════════════════════════════════════════════════════════════
@route('/api/sigadmin/list', methods=('GET',))
async def sig_list(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    ready = sb_ready()
    rows = await _refresh(bus) if ready else []
    sigs = getattr(bus, 'sigs', None)
    floor = await asyncio.to_thread(sigs.floor) if (sigs is not None and ready) else 0
    return _ok(configured=ready, signatures=rows, count=len(rows), floor=floor,
               error=(sigs.last_error if sigs is not None else ''), ver=bus.state.get('sig_admin').get('ver', 0))


async def _read_form(req):
    if _too_big(req):
        raise BadInput('파일이 너무 큽니다 — 한 번에 %dMB 까지' % MAX_REQUEST_MB)
    try:
        return await req.form()
    except Exception:
        raise BadInput('보낸 내용을 읽지 못했습니다 — 다시 골라 주세요')


async def _files(form):
    image = await _file(form.get('image'))
    sound = await _file(form.get('sound'))
    if sum(len(x[0]) for x in (image, sound) if x) > MAX_REQUEST_MB * 1024 * 1024:
        raise BadInput('파일이 너무 큽니다 — 한 번에 %dMB 까지' % MAX_REQUEST_MB)
    img = await asyncio.to_thread(prep_image, *image) if image else None
    snd = prep_sound(*sound) if sound else None
    return img, snd


def _dup_answer(dup, amount):
    names = ', '.join('#%s %s' % (d['id'], d.get('title') or '') for d in dup[:3])
    return _err('%s원 시그니처가 이미 있어요(%s) — 자동 매칭은 같은 금액 중 하나만 고릅니다' % (format(int(amount), ','), names),
                409, code='dup', dup=dup)


@route('/api/signatures/add')
async def sig_add(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    if not sb_ready():
        return _err('시그니처 보관소(Supabase)가 설정되지 않았습니다.', 503)
    form = None
    try:
        form = await _read_form(req)
        amount = _amount(form.get('amount'))
        title = _title(form.get('title')) or '%s원 시그니처' % format(amount, ',')
        duration = _duration(form.get('duration')) if _given(form.get('duration')) else DUR_DEFAULT
        img, snd = await _files(form)
    except BadInput as e:
        return _err(str(e), 413 if '너무 큽니다' in str(e) else 400)
    finally:
        if form is not None:
            await form.close()          # 올린 파일의 임시 파일 닫기(바이트는 이미 다 읽었다)
    if not img and not snd:
        return _err('사진이나 음원 중 하나는 등록해주세요.', 400)
    rows = await _refresh(bus)
    dup = _dups(rows, amount)
    if dup and not _truthy(form.get('allow_dup')):
        return _dup_answer(dup, amount)
    try:
        row = await asyncio.to_thread(_do_add, {'amount': amount, 'title': title, 'duration': duration}, img, snd)
    except Exception as e:
        return _err('등록하지 못했습니다 — ' + _why(e), 502)
    await _refresh(bus)
    res = await _log(bus, act='add', after=row)
    return _ok(message='시그니처가 등록되었습니다.', signature=row, lid=res.get('lid'))


def _sid(req):
    try:
        sid = int(req.path_params.get('sig_id'))
    except (TypeError, ValueError):
        raise BadInput('시그니처 번호가 이상합니다')
    if sid <= 0:
        raise BadInput('시그니처 번호가 이상합니다')
    return sid


@route('/api/signatures/update/{sig_id}')
async def sig_update(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    if not sb_ready():
        return _err('시그니처 보관소(Supabase)가 설정되지 않았습니다.', 503)
    form = None
    try:
        sid = _sid(req)
        form = await _read_form(req)
        fields = {}
        if _given(form.get('amount')):
            fields['amount'] = _amount(form.get('amount'))
        if _title(form.get('title')):
            fields['title'] = _title(form.get('title'))
        if _given(form.get('duration')):
            fields['duration'] = _duration(form.get('duration'))
        img, snd = await _files(form)
    except BadInput as e:
        return _err(str(e), 413 if '너무 큽니다' in str(e) else 400)
    finally:
        if form is not None:
            await form.close()          # 올린 파일의 임시 파일 닫기(바이트는 이미 다 읽었다)
    try:
        cur = await asyncio.to_thread(sb_get, sid)
    except Exception as e:
        return _err('시그니처를 읽지 못했습니다 — ' + _why(e), 502)
    if not cur:
        return _err('시그니처를 찾을 수 없습니다.', 404)
    fields = {k: v for k, v in fields.items() if v != cur.get(k)}        # 그대로인 칸은 빼고
    if not fields and not img and not snd:
        return _ok(message='변경 사항이 없습니다.', signature=cur)
    if 'amount' in fields and not _truthy(form.get('allow_dup')):
        dup = _dups(await _refresh(bus), fields['amount'], skip_id=sid)
        if dup:
            return _dup_answer(dup, fields['amount'])
    try:
        row = await asyncio.to_thread(_do_update, sid, fields, img, snd)
    except Exception as e:
        return _err('고치지 못했습니다 — ' + _why(e), 502)
    row = row or dict(cur, **fields)
    await _refresh(bus)
    res = await _log(bus, act='edit', before=cur, after=row)
    return _ok(message='시그니처가 수정되었습니다.', signature=row, lid=res.get('lid'))


@route('/api/signatures/delete/{sig_id}', methods=('POST', 'DELETE'))
async def sig_delete(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    if not sb_ready():
        return _err('시그니처 보관소(Supabase)가 설정되지 않았습니다.', 503)
    try:
        sid = _sid(req)
    except BadInput as e:
        return _err(str(e), 400)
    try:
        cur = await asyncio.to_thread(sb_get, sid)
    except Exception as e:
        return _err('시그니처를 읽지 못했습니다 — ' + _why(e), 502)
    if not cur:
        return _err('시그니처를 찾을 수 없습니다.', 404)
    # ⚠️ 적어 두기가 먼저 — 못 적으면 지우지 않는다(되살릴 길이 없는 지우기는 하지 않는다)
    res = await _log(bus, act='delete', row=cur)
    if not res.get('ok'):
        return _err('지우기 전에 보관해 두지 못해 지우지 않았습니다', 500)
    try:
        await asyncio.to_thread(sb_delete, sid)
    except Exception as e:
        await bus.run('sigadmin.drop', {'lid': res.get('lid')}, by='sigadmin', authed=True)
        return _err('지우지 못했습니다 — ' + _why(e), 502)
    await _refresh(bus)
    return _ok(message='시그니처를 지웠습니다. [최근 바뀐 것]에서 되살릴 수 있어요.', lid=res.get('lid'), signature=cur)


async def _body(req):
    try:
        b = await req.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


@route('/api/sigadmin/restore')
async def sig_restore(req, bus, authed, answer):
    """지운 것 되살리기 {lid, allow_dup?} — 파일은 남겨 두었으므로 행만 다시 넣는다."""
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    if not sb_ready():
        return _err('시그니처 보관소(Supabase)가 설정되지 않았습니다.', 503)
    body = await _body(req)
    e = _entry(bus, body.get('lid'))
    if not e or e.get('act') != 'delete' or not e.get('row'):
        return _err('되살릴 기록을 찾지 못했습니다', 404)
    if e.get('restored'):
        return _err('이미 되살렸습니다 (#%s)' % e.get('restored'), 409)
    row = e['row']
    rows = await _refresh(bus)
    if any(str(r.get('id')) == str(row.get('id')) for r in rows):
        return _err('그 번호의 시그니처가 지금 있습니다 — 이미 되살린 것 같아요', 409)
    dup = _dups(rows, row.get('amount') or 0)
    if dup and not _truthy(body.get('allow_dup')):
        return _dup_answer(dup, row.get('amount') or 0)
    try:
        got = await asyncio.to_thread(_do_restore, row)
    except Exception as ex:
        return _err('되살리지 못했습니다 — ' + _why(ex), 502)
    await _refresh(bus)
    await bus.run('sigadmin.mark', {'lid': e['lid'], 'restored': got.get('id')}, by='sigadmin', authed=True)
    await _log(bus, act='restore', after=got, of=e['lid'])
    same = str(got.get('id')) == str(row.get('id'))
    return _ok(message='되살렸습니다' + ('' if same else ' (새 번호 #%s)' % got.get('id')), signature=got)


@route('/api/sigadmin/revert')
async def sig_revert(req, bus, authed, answer):
    """고친 것 되돌리기 {lid, allow_dup?} — 고치기 전 값(파일 주소 포함)으로. 옛 파일은 지우지 않았으므로 그대로 나온다."""
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    if not sb_ready():
        return _err('시그니처 보관소(Supabase)가 설정되지 않았습니다.', 503)
    body = await _body(req)
    e = _entry(bus, body.get('lid'))
    if not e or e.get('act') not in ('edit', 'revert') or not e.get('before'):
        return _err('되돌릴 기록을 찾지 못했습니다', 404)
    if e.get('reverted'):
        return _err('이미 되돌렸습니다', 409)
    before = e['before']
    sid = before.get('id')
    try:
        cur = await asyncio.to_thread(sb_get, sid)
    except Exception as ex:
        return _err('시그니처를 읽지 못했습니다 — ' + _why(ex), 502)
    if not cur:
        return _err('그 시그니처는 지금 없습니다(지워졌어요) — 되살리기를 먼저 해 주세요', 404)
    fields = {k: before.get(k) for k in EDIT_KEYS if before.get(k) != cur.get(k)}
    if not fields:
        await bus.run('sigadmin.mark', {'lid': e['lid'], 'reverted': True}, by='sigadmin', authed=True)
        return _ok(message='이미 고치기 전 모습입니다', signature=cur)
    if 'amount' in fields and not _truthy(body.get('allow_dup')):
        dup = _dups(await _refresh(bus), fields['amount'], skip_id=sid)
        if dup:
            return _dup_answer(dup, fields['amount'])
    try:
        row = await asyncio.to_thread(sb_update, sid, fields)
    except Exception as ex:
        return _err('되돌리지 못했습니다 — ' + _why(ex), 502)
    row = row or dict(cur, **fields)
    await _refresh(bus)
    res = await _log(bus, act='revert', before=cur, after=row, of=e['lid'])
    await bus.run('sigadmin.mark', {'lid': e['lid'], 'reverted': res.get('lid') or True}, by='sigadmin', authed=True)
    return _ok(message='고치기 전으로 되돌렸습니다', signature=row)


# ══════════════════════════════════════════════════════════════
# 옛 주소 호환 — 폰 즐겨찾기 · 북마크가 그대로 열리게
#   /upload (음원 · 사진 등록 센터) → 시그니처 관리(따로 연 화면)
#   /mobile (폰 조종실)            → 조종실 — v2 조종실이 폰 화면(900px 아래)을 한 줄로 그린다(js/phone.js)
#   ⚠️ 옛 폰 주소의 ?token= 은 넘기지 않는다(주소창 · 기록에 열쇠가 남지 않게) — 처음 한 번 비밀번호로 들어가면 30일 간다.
# ══════════════════════════════════════════════════════════════
@route('/upload', methods=('GET',))
async def old_upload(req, bus, authed, answer):
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/controller/sig.html', status_code=302)


@route('/mobile', methods=('GET',))
async def old_mobile(req, bus, authed, answer):
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/controller/', status_code=302)
