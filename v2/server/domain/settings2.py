# -*- coding: utf-8 -*-
"""🎚️ 옛 설정 더 옮기기 — 시그니처 보이는 모습 · 목록 개수 · 효과음 스위치 · 💾 세이브 슬롯(순서표).

옛 admin.html(편집기) · controller.html(조종실) · server.py DEFAULT_STATE · features/show_api.py 의 숫자 · 범위 · 기본값을 그대로 옮겼다.

sigview 조각(공개) — 시그니처 카드 · 'OO업' 배너(옛 reaction_* 설정)
  big_scale       처음 크게 보일 때 배율    0.5~2.0  기본 1.0   (옛 reaction_big_scale)
  small_scale     줄어든 뒤 배율            0.3~1.5  기본 0.6   (옛 reaction_small_scale)
  min_x · min_y   줄어든 뒤 자리(카드 가운데, 캔버스 px)  기본 180 · 600 (옛 reaction_min_x · _y)
                  ⚠️ 옛 칸은 범위가 없었다 — 화면 밖으로 사라지지 않게 캔버스(1080×1920) 안으로만 막는다
  shrink_delay    크게 보였다가 줄어들기까지(ms) 500~6000 기본 2500 (옛 reaction_shrink_delay)
  title_size      'OO업' 글자 크기(px)       60~300   기본 150   (옛 reaction_title_size)
  title_duration  'OO업' 노출 시간(ms)       1000~8000 기본 3500 (옛 reaction_title_duration)
  title_suffix    이름 뒤에 붙는 말(6자까지, 비워도 된다 · 앞 띄어쓰기도 그대로 — ' 최고' → '홍길동 최고') 기본 '업' (옛 reaction_title_suffix)
  ※ 'OO업' 켜고 끄기(옛 reaction_title_enabled)는 원래 있던 알림 스위치 show.alerts.reaction_title 이다.

look 조각(공개)에 더한 칸 — 없으면 기본값으로 읽는다(옛 상태처럼 '값이 없으면 켜짐/기본')
  sig_tally_limit   시그 집계 몇 개   3~12 기본 6  (옛 sig_tally_limit — 방송판 widgets/sig-tally.js 가 읽는다)
  donor_rank_limit  후원 순위 몇 명   3~10 기본 5  (옛 donor_rank_limit)
  sfx               효과음(주사위 · 목표 · 모금함 · 시그뒤집기 · 대결 삑 …) 끄면 False. 시그니처 · 노래방 · 영상 소리는 그대로.

presets 조각(비공개 — 방송판은 몰라도 된다) {list: [{id, name, layout, hud, stage, saved_at}]}  옛 layout_presets
  한 칸 = 위젯 자리 · 크기(layout 조각의 widgets 통째) + 고정 자리(hud) + 무대(stage, 잠깐 판이면 돌아갈 무대).
  ⚠️ 안 담는 것: 게임 속 내용(룰렛 칸 · 핀볼 명단) · 점수 · 테마 · 알림 스위치 — 누르는 순간의 것을 그대로 쓴다.
  ⚠️ 지옥탈출 · 퇴근빵 · 대결의 '진행'(기록 · 점수 · 시계)은 건드리지 않는다 — 무대에 올리고 내리기만(show.stage 와 같다).
  60칸까지 · 이름 30자. 방송이 바뀌어도 남는다.
show.cue_at — 순서표의 '지금 몇 번째'(-1 = 아직 없음). 방송 시작 · 끝에 -1. 옮기기 · 지우기 뒤에도 같은 단계를 가리킨다(옛 _keep_cue).
"""
import copy
import re
import uuid

from ..bus import CommandError, command
from ..state import slice_
from . import session as ses
from . import show as sh

# ── 시그니처 보이는 모습 ──
SIGVIEW_DEFAULT = {'big_scale': 1.0, 'small_scale': 0.6, 'min_x': 180, 'min_y': 600, 'shrink_delay': 2500,
                   'title_size': 150, 'title_duration': 3500, 'title_suffix': '업'}
# 칸 → (낮은 끝, 높은 끝, 정수?) — 옛 편집기 막대의 min · max 그대로
SIGVIEW_RANGE = {'big_scale': (0.5, 2.0, False), 'small_scale': (0.3, 1.5, False),
                 'min_x': (0, 1080, True), 'min_y': (0, 1920, True), 'shrink_delay': (500, 6000, True),
                 'title_size': (60, 300, True), 'title_duration': (1000, 8000, True)}
SUFFIX_MAX = 6


def _suffix(v):
    """옛 칸처럼 적은 그대로(6자) — 줄바꿈 · 탭 같은 제어 글자만 뺀다."""
    return re.sub(r'[\x00-\x1f\x7f]', '', str(v if v is not None else ''))[:SUFFIX_MAX]


slice_('sigview', True, lambda: dict(SIGVIEW_DEFAULT))

# ── 목록 개수 (look 조각 안) ──
LIMITS = {'sig_tally_limit': (3, 12, 6), 'donor_rank_limit': (3, 10, 5)}

# ── 세이브 슬롯 ──
PRESET_MAX = 60                  # 옛 것과 같다 — 제한 없이, 다만 끝없이 쌓이지 않게 넉넉한 뚜껑만
PRESET_NAME_MAX = 30
slice_('presets', False, lambda: {'list': []})
# 옛 슬롯의 옛 스위치 이름 → v2 고정 자리(옛 show.py HUD_LEGACY. 전광판 ticker 는 10-03 에 지웠다)
HUD_LEGACY = {'notice_enabled': 'notice', 'donor_rank_enabled': 'donor_rank', 'sig_tally_enabled': 'sig_tally',
              'best_enabled': 'best', 'fundjar': 'fundjar'}


def _num(data, k, lo, hi, as_int):
    try:
        v = float(data[k])
    except (TypeError, ValueError):
        raise CommandError('%s 는 숫자여야 합니다' % k)
    if v != v:                                          # NaN
        raise CommandError('%s 가 숫자가 아닙니다' % k)
    v = max(lo, min(hi, v))
    return int(round(v)) if as_int else round(v, 2)


@command('sigview.set')
def sigview_set(ctx, data):
    """시그니처 보이는 모습 — 보낸 칸만 바꾼다. {big_scale?, small_scale?, min_x?, min_y?, shrink_delay?,
       title_size?, title_duration?, title_suffix?} 숫자는 옛 범위 안으로 맞춘다."""
    keys = [k for k in data if k in SIGVIEW_DEFAULT]
    if not keys:
        raise CommandError('바꿀 칸이 없습니다')
    v = ctx.edit('sigview')
    for k in keys:
        if k == 'title_suffix':
            v[k] = _suffix(data.get(k))
        else:
            lo, hi, as_int = SIGVIEW_RANGE[k]
            v[k] = _num(data, k, lo, hi, as_int)


@command('look.limits')
def look_limits(ctx, data):
    """방송판 목록 개수 — {sig_tally_limit?: 3~12, donor_rank_limit?: 3~10}"""
    keys = [k for k in data if k in LIMITS]
    if not keys:
        raise CommandError('바꿀 칸이 없습니다(sig_tally_limit · donor_rank_limit)')
    look = ctx.edit('look')
    for k in keys:
        lo, hi, _ = LIMITS[k]
        look[k] = _num(data, k, lo, hi, True)


@command('look.donor')
def look_donor(ctx, data):
    """🏅 후원 순위 판 — {amount?: 금액도 보여주기(기본 켬), anon?: 익명 후원도 순위에 넣기(기본 끔)} (옛 donor_rank_amount · donor_rank_anon)"""
    keys = [k for k in ('amount', 'anon') if k in data]
    if not keys:
        raise CommandError('바꿀 칸이 없습니다(amount · anon)')
    look = ctx.edit('look')
    for k in keys:
        look['donor_' + k] = bool(data.get(k))


@command('look.sfx')
def look_sfx(ctx, data):
    """🔊 효과음 켜고 끄기 — {on}. 방송 중에 거슬리면 바로 끈다(옛 sfx_enabled)."""
    if 'on' not in data:
        raise CommandError('켤지 끌지(on) 적어 주세요')
    ctx.edit('look')['sfx'] = bool(data.get('on'))


# ── 💾 세이브 슬롯 · 순서표 ──
def _list(ctx, edit=False):
    p = ctx.edit('presets') if edit else ctx.read('presets')
    if not isinstance(p.get('list'), list):
        p = ctx.edit('presets')
        p['list'] = []
    return p['list']


def _find(ps, pid):
    pid = str(pid or '')
    return next((i for i, x in enumerate(ps) if x.get('id') == pid), -1) if pid else -1


def _name(v):
    return ' '.join(str(v or '').split())[:PRESET_NAME_MAX]


def cue_at(show):
    try:
        return int(show.get('cue_at', -1))
    except (TypeError, ValueError):
        return -1


def snap_now(ctx):
    """지금 화면 한 장 — 자리 · 크기(layout.widgets 통째) · 고정 자리 · 무대(잠깐 판이면 돌아갈 무대 — 옛 cue_from_state)."""
    s = ctx.read('show')
    stage = s.get('ret') if s.get('stage') in sh.TEMP_STAGES else s.get('stage')
    return {'layout': copy.deepcopy(ctx.read('layout').get('widgets') or {}),
            'hud': {k: bool(v) for k, v in (s.get('hud') or {}).items()},
            'stage': stage if stage in sh.STAGES else None,
            'saved_at': int(ctx.now)}


def cue_hud(cue):
    """단계에 담긴 고정 자리. 새 모양은 hud, 옛 슬롯은 switches(옛 스위치 이름)에서 옮긴다. 없는 칸은 안 건드린다."""
    if isinstance(cue.get('hud'), dict):
        return {k: bool(v) for k, v in cue['hud'].items() if k in sh.HUD_DEFAULT}
    sw = cue.get('switches') if isinstance(cue.get('switches'), dict) else {}
    return {HUD_LEGACY[k]: bool(v) for k, v in sw.items() if k in HUD_LEGACY}


def cue_stage(cue):
    st = cue.get('stage') if 'stage' in cue else (cue.get('board') or None)
    return st if st in sh.STAGES else None


def _keep_cue(ctx, before_ids):
    """옮기거나 지운 뒤에도 '지금 단계' 가 같은 단계를 가리키게. 지금 단계를 지웠으면 그 바로 앞을 가리킨다
       — 그래야 [다음 ▶] 이 지운 단계 다음 것으로 간다(옛 _keep_cue 그대로)."""
    at = cue_at(ctx.read('show'))
    if not 0 <= at < len(before_ids):
        return
    ids = [x.get('id') for x in _list(ctx)]
    cur = before_ids[at]
    ctx.edit('show')['cue_at'] = ids.index(cur) if cur in ids else min(at, len(ids)) - 1


def apply_cue(ctx, hit, idx):
    """한 단계를 불러온다 — 자리 · 고정 자리 · 무대. 게임 속 내용 · 점수 · 테마는 그대로."""
    if isinstance(hit.get('layout'), dict):
        # v2 슬롯은 layout.widgets 통째다(기본 자리에 있던 위젯은 안 들어 있다) → 통째로 바꿔야 저장한 그대로가 된다.
        # ⚠️ 옛 프로그램에서 옮겨 온 슬롯은 layout 이 없다(옛 좌표는 기준점이 달라 옮기지 않았다) → 자리는 안 건드린다
        ctx.edit('layout')['widgets'] = {str(k): dict(v) for k, v in hit['layout'].items() if isinstance(v, dict)}
    s = ctx.edit('show')
    for k, v in cue_hud(hit).items():
        s['hud'][k] = v
        if k == 'fundjar' and 'fundjar' in ctx.bus.state.slices:
            ctx.edit('fundjar')['enabled'] = v          # 모금함 켜기와 같은 스위치(show.hud 와 같게)
    st = cue_stage(hit)
    # ⚠️ 옛 슬롯(board 만 있는 것)은 게임판 다섯만 다뤘다 — 판이 없으면 대결 · 지옥탈출 · 퇴근빵 무대는 그대로 둔다(옛 apply_cue)
    if not ('stage' not in hit and st is None and s.get('stage') in ('match', 'hell', 'home_race')):
        sh.set_stage(ctx, st)
    ctx.edit('show')['cue_at'] = idx
    ctx.notes.update({'at': idx, 'name': hit.get('name') or '', 'stage': ctx.read('show').get('stage')})


@command('preset.save')
def preset_save(ctx, data):
    """지금 화면을 슬롯에 적는다. id 가 있으면 그 칸을 덮고(이름 · 순서는 그대로, name 을 주면 이름도), 없으면 새 칸."""
    ps = _list(ctx, edit=True)
    name = _name(data.get('name'))
    i = _find(ps, data.get('id'))
    snap = snap_now(ctx)
    if i >= 0:
        ps[i].update(snap)
        ps[i].pop('switches', None)                     # 옛 슬롯을 덮으면 새 모양만 남긴다
        ps[i].pop('board', None)
        if name:
            ps[i]['name'] = name
        hit = ps[i]
    else:
        if len(ps) >= PRESET_MAX:
            raise CommandError('슬롯이 너무 많습니다(%d개). 안 쓰는 걸 지워 주세요' % PRESET_MAX)
        hit = dict(snap, id='p' + uuid.uuid4().hex[:10], name=name or ('슬롯 %d' % (len(ps) + 1)))
        ps.append(hit)
    ctx.notes.update({'id': hit['id'], 'name': hit['name']})


@command('preset.rename')
def preset_rename(ctx, data):
    name = _name(data.get('name'))
    if not name:
        raise CommandError('이름을 적어 주세요')
    ps = _list(ctx, edit=True)
    i = _find(ps, data.get('id'))
    if i < 0:
        raise CommandError('없는 슬롯입니다', 404)
    ps[i]['name'] = name


@command('preset.move')
def preset_move(ctx, data):
    """순서 바꾸기 — dir -1 이면 앞으로, +1 이면 뒤로. 끝에서 더 가면 그대로."""
    try:
        d = -1 if int(data.get('dir')) < 0 else 1
    except (TypeError, ValueError):
        d = 1
    ps = _list(ctx)
    i = _find(ps, data.get('id'))
    if i < 0:
        raise CommandError('없는 슬롯입니다', 404)
    j = i + d
    if not 0 <= j < len(ps):
        return
    before = [x.get('id') for x in ps]
    ps = _list(ctx, edit=True)
    ps[i], ps[j] = ps[j], ps[i]
    _keep_cue(ctx, before)


@command('preset.delete')
def preset_delete(ctx, data):
    ps = _list(ctx)
    i = _find(ps, data.get('id'))
    if i < 0:
        raise CommandError('없는 슬롯입니다', 404)
    before = [x.get('id') for x in ps]
    _list(ctx, edit=True).pop(i)
    _keep_cue(ctx, before)


@command('preset.apply')
def preset_apply(ctx, data):
    """슬롯을 불러온다 — 자리 · 켜기/끄기 · 무대를 저장한 그대로."""
    ps = _list(ctx)
    i = _find(ps, data.get('id'))
    if i < 0:
        raise CommandError('없는 슬롯입니다', 404)
    apply_cue(ctx, ps[i], i)


@command('show.cue')
def show_cue(ctx, data):
    """순서표 넘기기 — {dir: 'next' | 'prev' | 'go', id?}. 끝에서 더 가면 409(옛 /api/show cue 와 같다)."""
    ps = _list(ctx)
    at = cue_at(ctx.read('show'))
    d = data.get('dir')
    if d == 'next':
        idx = at + 1
    elif d == 'prev':
        idx = at - 1
    elif d == 'go':
        idx = _find(ps, data.get('id'))
    else:
        raise CommandError('모르는 순서표 명령입니다')
    if not 0 <= idx < len(ps):
        raise CommandError('순서표 끝이에요' if ps else '순서표가 비어 있어요 — 지금 화면을 단계로 저장해 주세요', 409)
    apply_cue(ctx, ps[idx], idx)


def _reset_cue(ctx, data):
    """방송 시작 · 끝 — 순서표는 처음부터(옛 reset_session 의 cue_at = -1)."""
    if cue_at(ctx.read('show')) != -1:
        ctx.edit('show')['cue_at'] = -1


ses.ON_START.append(_reset_cue)
ses.ON_END.append(_reset_cue)


# ── 옛 상태 옮기기(admin.import_old 가 부른다) ──
_OLD_SIGVIEW = {'reaction_big_scale': 'big_scale', 'reaction_small_scale': 'small_scale', 'reaction_min_x': 'min_x',
                'reaction_min_y': 'min_y', 'reaction_shrink_delay': 'shrink_delay', 'reaction_title_size': 'title_size',
                'reaction_title_duration': 'title_duration', 'reaction_title_suffix': 'title_suffix'}


def import_old(ctx, old):
    """옛 백업 파일의 설정 → v2. 옮긴 것 이름들을 돌려준다. 숫자가 이상한 칸은 건너뛴다(하나 때문에 전부 막지 않게)."""
    done = []
    sv = {}
    for ok, nk in _OLD_SIGVIEW.items():
        if ok in old:
            sv[nk] = old[ok]
    if sv:
        v = ctx.edit('sigview')
        for k, val in sv.items():
            try:
                if k == 'title_suffix':
                    v[k] = _suffix(val)
                else:
                    lo, hi, as_int = SIGVIEW_RANGE[k]
                    v[k] = _num({k: val}, k, lo, hi, as_int)
            except CommandError:
                pass
        done.append('시그니처 보이는 모습')
    if 'reaction_title_enabled' in old:
        ctx.edit('show')['alerts']['reaction_title'] = old.get('reaction_title_enabled') is not False
    lim = [k for k in LIMITS if k in old]
    for k in lim:
        lo, hi, dflt = LIMITS[k]
        try:
            ctx.edit('look')[k] = _num(old, k, lo, hi, True)
        except CommandError:
            ctx.edit('look')[k] = dflt
    if lim:
        done.append('목록 개수')
    if 'sfx_enabled' in old:
        ctx.edit('look')['sfx'] = old.get('sfx_enabled') is not False      # 값이 없거나 이상하면 켜짐(옛 규칙)
        done.append('효과음 스위치')
    if 'karaoke_volume' in old:
        try:
            ctx.edit('karaoke')['volume'] = int(max(0, min(100, round(float(old['karaoke_volume'])))))
            done.append('노래방 음량')
        except (TypeError, ValueError):
            pass
    ops = old.get('layout_presets')
    if isinstance(ops, list) and ops:
        ps = _list(ctx, edit=True)
        have = {x.get('id') for x in ps}
        n = 0
        for p in ops:
            if not isinstance(p, dict) or len(ps) >= PRESET_MAX:
                continue
            pid = str(p.get('id') or '')[:20] or ('p' + uuid.uuid4().hex[:10])
            if pid in have:
                continue                                # 두 번 옮겨도 겹치지 않게
            try:
                at = int(float(p.get('saved_at') or 0))
            except (TypeError, ValueError):
                at = 0
            row = {'id': pid, 'name': _name(p.get('name')) or ('슬롯 %d' % (len(ps) + 1)),
                   'hud': cue_hud(p), 'saved_at': at, 'old': True}
            # ⚠️ 무대가 없는 옛 슬롯(board 만)은 board 로 남긴다 — 불러올 때 대결 · 지옥탈출 · 퇴근빵 무대를 안 건드리는 옛 규칙
            if 'stage' in p:
                row['stage'] = cue_stage(p)
            else:
                row['board'] = cue_stage(p)
            # ⚠️ 위젯 자리(layout)는 안 옮긴다 — 옛 좌표(x_px · y_px)는 기준점이 v2(layers.js anchor)와 달라 엉뚱한 데로 간다.
            #    편집기 · 조종실에서 [지금 화면으로 바꾸기] 로 다시 담으면 된다.
            ps.append(row)
            have.add(pid)
            n += 1
        if n:
            done.append('세이브 슬롯 %d개(자리 빼고)' % n)
    return done
