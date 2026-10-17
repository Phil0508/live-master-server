# -*- coding: utf-8 -*-
"""🎬 엔딩 크레딧 — 방송 끝에 오늘 후원해 준 사람 **전원**을 영화 엔딩처럼 아래에서 위로(대표님 10-17 '3순위').

끝 화면(screen end)은 후원자 8명까지만 보인다. 크레딧은 전원 — 멤버별로 묶는다.

조각
  credits      (공개)  방송판이 그린다 — 이름(닉네임)과, '금액 보이기' 를 켰을 때만 금액. 실명 · 계좌 · 메시지 · 장부 번호 없음.
      on · paused · speed(slow · normal · fast) · at(ms, 서버 시각) · offset(px — at 때 흐른 거리) · run(처음부터 누를 때마다 +1)
      title(맨 위 제목) · outro(맨 끝 마무리 글) · show_amount · built_at(ms) · count(이름 수) · anon(이름 없는 후원 수)
      groups[{kind: member|all|etc, title, names[{name, total?}]}]
  credits_ops  (비공개) 조종실 미리보기 — built(만든 적 있나) · session · built_at · stale(만든 뒤 후원 · 배정이 바뀜)
      groups(금액 늘 포함) · skipped{anon, excluded, test, replay}

셈(build — 장부 · 점수 기록에서 서버가 센다. 방송판은 그리기만)
  - 이번 회차(session.id — 방송을 끝내도 같은 번호) 장부 줄만.
  - 빼는 것: 🧪 테스트(source toonation_test) · 🔁 다시 보기 · 대시보드 테스트 · ↻ 다시 송출(장부 status display 중 소액 띠가 아닌 것) ·
    순위에서 뺀 이름(donor_rules.excluded) · 0원 이하. 익명은 이름 대신 마무리 글 위 '이름 없이 함께해 주신 N분' 으로만 센다.
  - 넣는 것: 대기함 · 배정 · 무시 · 옛 장부(archived) 줄 + 1만 원 미만 '화면에만' 소액(source display — 진짜 후원자다).
  - 묶음: 점수 기록(score_log, 되돌린 것 빼고)에서 그 후원(ref = 후원 id)이 점수 · 기여도를 준 멤버(list · extra).
      나눠 주기면 각 멤버 묶음에 다 들어가고, 금액은 준 점수 비율로 나눠 센다.
      모금함으로 간 후원(list jar) · 그때 판의 멤버 **전원**에게 나눈 후원 → '모두에게'.
      그 밖(대기함에 남음 · 무시 · 소액 · 옛 장부)은 '기타' — 단, 다른 묶음에 이미 이름이 있는 사람은 '기타' 에 또 쓰지 않는다.
  - 순서: 멤버 순위(players.list 순서 = 점수 순) → 번외 판 멤버 → 명단에서 빠진 멤버(받은 금액 큰 순) → 모두에게 → 기타.
      묶음 안은 후원 합계 큰 순(같으면 먼저 온 사람). 같은 사람(norm_donor — '님' · 띄어쓰기)은 한 줄로, 이름은 처음 쓴 것.
  - **얼린다**: 만든 순간의 명단을 credits 에 넣고 그대로 쓴다. 그 뒤 후원 · 배정이 바뀌면 credits_ops.stale 만 켠다
    → 조종실이 '그 뒤 바뀐 것이 있어요 — [다시 만들기]' 를 보여 준다. 띄우기(credits.show)는 만든 적이 없을 때만 새로 만든다.

흐름(방송판) — 서버가 '언제 몇 px 흘렀나' 만 적고, 방송판이 서버 시계로 지금 자리를 센다(OBS 가 다시 붙어도 같은 자리).
  지금 자리 = offset + (멈춤이 아니면 (서버 지금 − at) × 속도). 끝까지 가면 마무리 글이 안전지대 가운데에서 멈춘다(방송판이 자른다).

명령(로그인): credits.build{title?, outro?} · credits.show{rebuild?} · credits.pause{paused?} · credits.restart · credits.hide ·
  credits.set{title?, outro?, show_amount?, speed?}
순서표: 단계를 저장할 때 크레딧이 떠 있었는지(credits: true/false)를 같이 적고, 불러오면 그대로 띄우거나 내린다(settings2 SNAP_EXTRA · APPLY_EXTRA).
"""
from ..bus import AFTER, CommandError, command
from ..state import slice_
from . import session as ses
from . import settings2
from .rules import name_is_missing, norm_donor

TITLE_MAX, OUTRO_MAX, NAME_MAX = 40, 60, 20
NAMES_MAX = 1500                       # 한 번에 싣는 이름 수 끝(조각이 너무 커지지 않게) — 넘으면 큰 금액 순으로 자른다
SPEEDS = {'slow': 45, 'normal': 75, 'fast': 130}       # px/초 — 1080×1920 방송판 기준(방송판 widgets/credits/credits.js 와 같은 값)
DEFAULT_TITLE = '오늘 함께해 주셔서 감사합니다'
DEFAULT_OUTRO = '다음 방송에서 또 만나요 ♥'
TEST_SOURCES = ('toonation_test',)
SMALL_SOURCE = 'display'               # 1만 원 미만 '화면에만' 소액 — 진짜 후원(장부 합계 밖일 뿐)
MEMBER_LISTS = ('list', 'extra')
JAR_LIST = 'jar'
TITLE_ALL, TITLE_ETC = '모두에게', '그리고 함께해 주신 분'


def _default_pub():
    return {'on': False, 'paused': False, 'speed': 'normal', 'at': 0, 'offset': 0, 'run': 0,
            'title': DEFAULT_TITLE, 'outro': DEFAULT_OUTRO, 'show_amount': False,
            'built_at': 0, 'count': 0, 'anon': 0, 'groups': []}


def _default_ops():
    return {'built': False, 'session': '', 'built_at': 0, 'stale': False, 'groups': [],
            'count': 0, 'anon': 0, 'skipped': {'anon': 0, 'excluded': 0, 'test': 0, 'replay': 0}}


slice_('credits', True, _default_pub)
slice_('credits_ops', False, _default_ops)


def _clean(s, n):
    return ' '.join(str(s or '').split())[:n]


# ── 셈(순수 함수 — 검사가 바로 부른다) ──
def compute(donations, scores, roster, extra=(), excluded=()):
    """donations = 장부 줄[{id, at, name, amount, source, status}] · scores = 점수 기록 줄[{ref, player, field, list, delta}](되돌린 것 뺀 것)
       roster = 본 명단 이름(순위 순서) · extra = 번외 판 이름 · excluded = 순위에서 뺀 정규화 이름.
       돌려받는 값: {groups:[{kind, title, names:[{name, total}]}], count, anon, skipped}"""
    roster = [str(n) for n in roster or []]
    extra = [str(n) for n in extra or [] if str(n) not in roster]
    excluded = set(excluded or [])
    skipped = {'anon': 0, 'excluded': 0, 'test': 0, 'replay': 0}

    # 후원 하나 → {멤버: 몫(점수)} / 모금함
    gave = {}
    for r in scores:
        ref = str(r.get('ref') or '')
        if not ref.startswith('don_'):
            continue
        try:
            d = int(r.get('delta') or 0)
        except (TypeError, ValueError):
            continue
        if d <= 0:
            continue
        g = gave.setdefault(ref, {'score': {}, 'contrib': {}, 'jar': False})
        lst = str(r.get('list') or 'list')
        if lst == JAR_LIST:
            g['jar'] = True
        elif lst in MEMBER_LISTS:
            key = 'contrib' if r.get('field') == 'contribution' else 'score'
            g[key][str(r.get('player'))] = g[key].get(str(r.get('player')), 0) + d

    buckets = {}            # (kind, member) → {donor_key: {name, total, first}}
    first_member_total = {}

    def put(kind, member, key, name, amount, at):
        b = buckets.setdefault((kind, member), {})
        row = b.get(key)
        if row is None:
            row = b[key] = {'name': name, 'total': 0, 'first': at}
        row['total'] += amount
        row['first'] = min(row['first'], at)

    anon = 0
    for d in sorted(donations, key=lambda x: (float(x.get('at') or 0), str(x.get('id') or ''))):
        src, status = str(d.get('source') or ''), str(d.get('status') or '')
        if src in TEST_SOURCES:
            skipped['test'] += 1
            continue
        if status == 'display' and src != SMALL_SOURCE:
            skipped['replay'] += 1           # 다시 보기 · 대시보드 테스트 · 다시 송출 — 화면에만 한 번 더 띄운 것
            continue
        try:
            amount = int(d.get('amount') or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        raw = _clean(d.get('name'), 60)
        key = norm_donor(raw)
        if key == '익명' or name_is_missing(key):
            anon += 1
            skipped['anon'] += 1
            continue
        if key in excluded:
            skipped['excluded'] += 1
            continue
        name = raw[:-1].strip() if raw.endswith('님') and len(raw) > 1 else raw
        name = name[:NAME_MAX] or key[:NAME_MAX]
        at = float(d.get('at') or 0)
        g = gave.get(str(d.get('id') or ''))
        shares = (g['score'] or g['contrib']) if g else {}
        if g and g['jar'] and not shares:
            put('all', '', key, name, amount, at)
        elif shares:
            members = set(shares)
            if len(roster) >= 2 and members >= set(roster) and members <= set(roster) | set(extra):
                put('all', '', key, name, amount, at)        # 그때 판의 멤버 전원에게 나눴다 = 모두에게
            else:
                tot = sum(shares.values()) or 1
                left = amount
                items = sorted(shares.items(), key=lambda kv: -kv[1])
                for i, (m, v) in enumerate(items):
                    part = left if i == len(items) - 1 else amount * v // tot
                    left -= part
                    put('member', m, key, name, part, at)
                    first_member_total[m] = first_member_total.get(m, 0) + part
        else:
            put('etc', '', key, name, amount, at)

    def rows(kind, member):
        b = buckets.get((kind, member)) or {}
        out = sorted(b.values(), key=lambda r: (-r['total'], r['first'], r['name']))
        return [{'name': r['name'], 'total': int(r['total'])} for r in out], set(b)

    groups, seen = [], set()
    members_known = roster + extra
    others = sorted((m for (k, m) in buckets if k == 'member' and m not in members_known),
                    key=lambda m: (-first_member_total.get(m, 0), m))
    for m in members_known + others:
        names, keys = rows('member', m)
        if names:
            groups.append({'kind': 'member', 'title': m, 'names': names})
            seen |= keys
    names, keys = rows('all', '')
    if names:
        groups.append({'kind': 'all', 'title': TITLE_ALL, 'names': names})
        seen |= keys
    b = buckets.get(('etc', '')) or {}
    etc = sorted((r for k, r in b.items() if k not in seen), key=lambda r: (-r['total'], r['first'], r['name']))
    if etc:
        groups.append({'kind': 'etc', 'title': TITLE_ETC, 'names': [{'name': r['name'], 'total': int(r['total'])} for r in etc]})
    # 이름 수 끝 — 넘으면 각 묶음 뒤쪽(작은 금액)부터 덜어 낸다
    total_names = sum(len(g['names']) for g in groups)
    if total_names > NAMES_MAX:
        cut = total_names - NAMES_MAX
        for g in reversed(groups):
            take = min(cut, max(0, len(g['names']) - 1))
            if take:
                del g['names'][-take:]
                cut -= take
            if not cut:
                break
    people = set()
    for (k, m), b in buckets.items():
        people |= set(b)
    return {'groups': groups, 'count': len(people), 'anon': anon, 'skipped': skipped}


def public_groups(groups, show_amount):
    """방송판에 보낼 모양 — 이름(닉네임)과, 금액 보이기를 켰을 때만 금액."""
    out = []
    for g in groups:
        out.append({'kind': g['kind'], 'title': g['title'],
                    'names': [({'name': r['name'], 'total': r['total']} if show_amount else {'name': r['name']}) for r in g['names']]})
    return out


def _ledger_rows(ctx, sid):
    db = ctx.store.db
    dons = [dict(r) for r in db.execute(
        'SELECT id, at, name, amount, source, status FROM donations WHERE session = ? ORDER BY at, id', (sid,))]
    scs = [dict(r) for r in db.execute(
        "SELECT ref, player, field, list, delta FROM score_log WHERE session = ? AND undone = 0 AND ref LIKE 'don\\_%' ESCAPE '\\' "
        'ORDER BY id', (sid,))]
    return dons, scs


def build(ctx):
    sid = ses.session_id(ctx)
    dons, scs = _ledger_rows(ctx, sid)
    p = ctx.read('players')
    roster = [r['name'] for r in p.get('list') or []]
    extra = [r['name'] for r in p.get('extra') or []]
    excluded = (ctx.read('donor_rules') or {}).get('excluded') or []
    res = compute(dons, scs, roster, extra, excluded)
    now = int(ctx.now * 1000)
    ops = ctx.edit('credits_ops')
    ops.update({'built': True, 'session': sid, 'built_at': now, 'stale': False, 'groups': res['groups'],
                'count': res['count'], 'anon': res['anon'], 'skipped': res['skipped']})
    pub = ctx.edit('credits')
    pub.update({'built_at': now, 'count': res['count'], 'anon': res['anon'],
                'groups': public_groups(res['groups'], pub.get('show_amount'))})
    ctx.notes.update({'count': res['count'], 'groups': len(res['groups']), 'anon': res['anon']})


def _pos(c, now_ms):
    """지금 흐른 거리(px) — 방송판과 같은 셈(끝에서 자르는 것은 방송판 몫)."""
    off = float(c.get('offset') or 0)
    if c.get('on') and not c.get('paused'):
        off += max(0.0, (now_ms - float(c.get('at') or 0)) / 1000.0) * SPEEDS.get(c.get('speed'), SPEEDS['normal'])
    return off


def _apply_text(pub, data):
    if 'title' in data:
        pub['title'] = _clean(data.get('title'), TITLE_MAX) or DEFAULT_TITLE
    if 'outro' in data:
        pub['outro'] = _clean(data.get('outro'), OUTRO_MAX) or DEFAULT_OUTRO


def _start(ctx):
    pub = ctx.edit('credits')
    pub.update({'on': True, 'paused': False, 'at': int(ctx.now * 1000), 'offset': 0, 'run': int(pub.get('run') or 0) + 1})


def _need_build(ctx):
    ops = ctx.read('credits_ops')
    return not ops.get('built') or ops.get('session') != ses.session_id(ctx)


# ── 명령 ──
@command('credits.build')
def credits_build(ctx, data):
    """명단을 (다시) 만든다 — 지금 장부 · 점수 기록으로. 띄우지는 않는다(떠 있으면 새 명단으로 바뀐다)."""
    _apply_text(ctx.edit('credits'), data)
    build(ctx)


@command('credits.show')
def credits_show(ctx, data):
    """방송판에 띄운다 — 처음부터. 만든 적이 없으면(또는 rebuild) 지금 만든다. 만들어 둔 명단은 그대로(얼린 것)."""
    _apply_text(ctx.edit('credits'), data)
    if data.get('rebuild') or _need_build(ctx):
        build(ctx)
    _start(ctx)


@command('credits.pause')
def credits_pause(ctx, data):
    pub = ctx.edit('credits')
    if not pub.get('on'):
        raise CommandError('크레딧이 떠 있지 않아요 — 먼저 띄워 주세요', 409)
    want = (not pub.get('paused')) if 'paused' not in data else bool(data.get('paused'))
    if want == bool(pub.get('paused')):
        return
    now = int(ctx.now * 1000)
    pub['offset'] = int(_pos(pub, now))
    pub['at'] = now
    pub['paused'] = want
    ctx.notes['paused'] = want


@command('credits.restart')
def credits_restart(ctx, data):
    if _need_build(ctx):
        build(ctx)
    _start(ctx)


@command('credits.hide')
def credits_hide(ctx, data):
    pub = ctx.edit('credits')
    pub.update({'on': False, 'paused': False})


@command('credits.set')
def credits_set(ctx, data):
    pub = ctx.edit('credits')
    _apply_text(pub, data)
    if 'show_amount' in data:
        pub['show_amount'] = bool(data.get('show_amount'))
        pub['groups'] = public_groups(ctx.read('credits_ops').get('groups') or [], pub['show_amount'])
    if 'speed' in data:
        sp = str(data.get('speed') or '')
        if sp not in SPEEDS:
            raise CommandError('속도는 느림(slow) · 보통(normal) · 빠름(fast) 중 하나예요')
        if sp != pub.get('speed'):
            now = int(ctx.now * 1000)
            pub['offset'] = int(_pos(pub, now))       # 지금 자리에서 이어서 — 속도만 바뀐다
            pub['at'] = now
            pub['speed'] = sp


# ── 만든 뒤 바뀐 것 알리기(조종실 '다시 만들기') ──
def _mark_stale(ctx):
    ops = ctx.read('credits_ops')
    if not ops.get('built') or ops.get('stale'):
        return
    w = ctx.work
    pend_changed = 'pending' in w.copies and w.copies['pending'] != w.state.slices.get('pending')
    if pend_changed or ctx.notes.get('display_only'):
        ctx.edit('credits_ops')['stale'] = True


AFTER.append(_mark_stale)


# ── 방송 시작: 지난 방송 크레딧을 내리고 비운다(제목 · 마무리 글 · 속도 · 금액 보이기는 남긴다) ──
def _on_start(ctx, data):
    pub = ctx.edit('credits')
    keep = {k: pub.get(k) for k in ('title', 'outro', 'speed', 'show_amount', 'run')}
    ctx.put('credits', dict(_default_pub(), **keep))
    ctx.put('credits_ops', _default_ops())


ses.ON_START.append(_on_start)


# ── 순서표 단계 — 저장할 때 크레딧이 떠 있었는지 적고, 불러오면 그대로 ──
def _snap(ctx, snap):
    snap['credits'] = bool(ctx.read('credits').get('on'))


def _apply(ctx, hit):
    if 'credits' not in hit:
        return                                      # 이 기능 전에 저장한 단계 — 크레딧은 그대로
    on = bool(hit.get('credits'))
    cur = bool(ctx.read('credits').get('on'))
    if on and not cur:
        if _need_build(ctx):
            build(ctx)
        _start(ctx)
    elif not on and cur:
        ctx.edit('credits').update({'on': False, 'paused': False})


settings2.SNAP_EXTRA.append(_snap)
settings2.APPLY_EXTRA.append(_apply)
