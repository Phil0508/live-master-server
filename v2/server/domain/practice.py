# -*- coding: utf-8 -*-
"""🧪 화면 테스트 · 🎓 연습 모드 — 대표님 10-19 "후원 신호를 테스트로 불러오는것도" · 용도 둘 다 · "따로 페이지"(/practice/).

🧪 화면 테스트  POST /api/donation/test {mode:'screen', name, amount, message, title?, level?, via?, count?}
   방송판에 진짜와 똑같이(후원 카드 · 시그니처 · 소액 띠) — donation.add 의 '화면에만' 길(page_test).
   대기함 · 점수 · 장부 합계 · 후원 순위 · 한 방 최고 · 시그 집계 · 기억 · 후원자 장부 · 정답지 · 월별 → 아무것도 안 바뀐다.
   장부엔 status 'display' · source 'test_page' 줄만(합계 밖).

🎓 연습 모드
   practice.start {names}  방송 중이면 409. 지금 판 전체(조각들)를 되살리기 지점(restore_points 'practice')에 적고 연습 회차를 연다.
                           session.start 의 시작 고리를 그대로 돈다(점수판 · 대기함 비우기 등) — 판은 연습 끝에 통째로 되돌린다.
                           ⚠️ session.end 는 부르지 않는다(백업 · 크레딧 · [방송 끝] 되살리기 지점 같은 끝 고리가 돌면 안 된다).
   POST /api/donation/test {mode:'practice', … , expect?}  연습 후원 → 대기함 카드(practice) · 팝업 · 시그니처, 장부 source 'practice'.
                           주기 · 나눠 주기 · 무시 · 되돌리기 · 모금함 · 오토파일럿 다 평소처럼.
   practice.end            연습 전 판으로 통째로 되돌리고 연습 줄(장부 · 점수 기록)을 지운다. 채점 요약을 돌려준다.
   - 연습은 아무것도 배우지 않는다: 장부 source 'practice'/'test_page' 는 donor_clean.is_real_donation 이 '후원 아님' 으로 보고
     후원자 장부 · 정답지가 건너뛰고, donor_memory 도 건너뛴다. 오토파일럿 채점 · 집계 · 등급은 조각이라 판과 같이 되돌아간다.
   - 연습 중 들어온 진짜 후원(리스너 toon_ · 계좌 송출 manual_bank_)은 잃지 않는다 — 연습 중엔 손대지 못하게 막고(donation.practice_guard)
     연습 끝에 되돌린 판의 대기함 · 시그니처 대기줄 · 후원 순위에 다시 얹는다. 장부 줄은 그대로(회차 번호만 연습 전 것으로).
   - 연습 중엔 session.live 라 배포 잠금(/api/deploy/ok 409)이 그대로 걸린다. 재시작해도 되살리기 지점은 장부에 있다.
   GET /api/practice/info  연습 시작 칸에 넣을 멤버(기억에 5번 이상) · 시그 목록 · 지금 상태
   GET /api/practice/sample?n=1  그럴듯한 가짜 후원 — 실제 후원자 닉네임 · 그 사람이 자주 준 멤버 이름 든 메시지 · 실제 금액, expect(기록상 정답)
"""
import asyncio
import collections
import copy
import random
import time
import uuid

from fastapi.responses import JSONResponse

from ..bus import CommandError, command
from ..state import SLICES
from . import donation as dn
from . import session as ses
from .legacy import route
from .rules import norm_donor

KIND = 'practice'
SKIP = ('popup', 'practice')            # 되돌리지 않는 조각 — 지난 알림이 다시 뜨지 않게 · 연습 상태는 따로
FAKE_SOURCES = ('practice', 'test_page')
TEST_PER_MIN = 30
_recent = collections.deque()


def _err(msg, code):
    return JSONResponse({'status': 'error', 'message': msg}, status_code=code)


# ── 시작 · 끝 ─────────────────────────────────────────────
@command('practice.start')
def practice_start(ctx, data):
    if ctx.read('session').get('live'):
        raise CommandError('방송 중에는 연습을 시작할 수 없어요 — 방송을 끝낸 뒤에 해 주세요', 409)
    if dn.practice_on(ctx):
        raise CommandError('이미 연습 중이에요', 409)
    names = [str(n).strip() for n in (data.get('names') or []) if str(n).strip()]
    prev_sid = ctx.read('session').get('id') or ''
    pre = {k: copy.deepcopy(v) for k, v in ctx.bus.state.slices.items() if k not in SKIP}
    rid = ctx.store.add_restore_point(KIND, prev_sid, pre, {}, keep=5)
    ses.start(ctx, {'names': names})                      # 이름이 틀리면 여기서 거절 — 되살리기 지점도 같은 묶음이라 안 남는다
    ctx.put('practice', {'on': True, 'started_at': ctx.now, 'rp': rid, 'sid': ctx.read('session')['id'], 'prev_sid': prev_sid,
                         'cards': [], 'real': 0, 'tests': 0})
    ctx.notes.update({'sid': ctx.read('session')['id']})


def _note_card(ctx, did, data):
    """연습 카드 하나를 practice 조각에 — 채점에 쓴다(정답 · 들어온 때)."""
    p = ctx.edit('practice')
    p.setdefault('cards', []).append({'id': did, 'at': ctx.now, 'expect': str(data.get('expect') or '')[:40] or None})
    del p['cards'][:-300]


def _summary(ctx, p):
    cards = p.get('cards') or []
    db = ctx.store.db
    out = {'cards': len(cards), 'given': 0, 'ignored': 0, 'left': 0, 'jar': 0, 'checked': 0, 'correct': 0, 'avg_sec': None,
           'minutes': round((ctx.now - float(p.get('started_at') or ctx.now)) / 60.0, 1), 'misses': []}
    secs = []
    for c in cards:
        r = db.execute('SELECT status, player FROM donations WHERE id = ?', (c['id'],)).fetchone()
        st = r['status'] if r else 'pending'
        if st == 'assigned':
            rows = [x for x in ctx.store.score_rows(c['id']) if x['field'] == 'score' and int(x['delta']) > 0]
            got = [x['player'] for x in rows]
            if rows and rows[0]['list'] == 'jar':
                out['jar'] += 1
            else:
                out['given'] += 1
            if rows:
                secs.append(max(0.0, float(rows[0]['at']) - float(c['at'])))
            if c.get('expect'):
                out['checked'] += 1
                if c['expect'] in got:
                    out['correct'] += 1
                elif len(out['misses']) < 8:
                    r2 = db.execute('SELECT name, amount FROM donations WHERE id = ?', (c['id'],)).fetchone()
                    out['misses'].append({'name': r2['name'] if r2 else '', 'amount': int(r2['amount']) if r2 else 0,
                                          'expect': c['expect'], 'got': got})
        elif st == 'ignored':
            out['ignored'] += 1
        else:
            out['left'] += 1
    if secs:
        out['avg_sec'] = round(sum(secs) / len(secs), 1)
    return out


def _retally(ctx, rows):
    """연습 중 들어온 진짜 후원 — 되돌린 판의 후원 순위 · 한 방 최고에 다시 더한다(donation.add 와 같은 셈)."""
    t = ctx.edit('tallies')
    for d in rows:
        if d['status'] == 'display' or int(d['amount'] or 0) <= 0:
            continue
        key = norm_donor(d['name'])
        dt = t['donors'].setdefault(key, {'name': d['name'], 'total': 0, 'count': 0})
        dt['total'] += int(d['amount'])
        dt['count'] += 1
        if not t['best'] or int(d['amount']) > int(t['best']['amount']):
            t['best'] = {'name': d['name'], 'amount': int(d['amount']), 'at': int(float(d['at']) * 1000), 'id': d['id'], 'member': ''}


@command('practice.end')
def practice_end(ctx, data):
    p = ctx.read('practice')
    if not p.get('on'):
        raise CommandError('연습 중이 아니에요', 409)
    rp = ctx.store.last_restore_point(KIND)
    if not rp or rp['id'] != p.get('rp'):
        raise CommandError('연습 전 판을 찾지 못했어요 — 조종실에서 [방송 끝]으로 정리해 주세요', 409)
    psid, prev_sid = p.get('sid') or '', p.get('prev_sid') or ''
    summary = _summary(ctx, p)
    db = ctx.store.db
    rows = [dict(r) for r in db.execute('SELECT * FROM donations WHERE session = ? ORDER BY at', (psid,))] if psid else []
    fake = {r['id'] for r in rows if r['source'] in FAKE_SOURCES}
    real = [r for r in rows if r['id'] not in fake]
    real_ids = {r['id'] for r in real}
    keep_pending = [x for x in ctx.read('pending') if not x.get('practice') and x.get('id') in real_ids]
    keep_queue = [x for x in (ctx.read('queue').get('items') or [])
                  if x.get('don_ids') and all(i in real_ids for i in x['don_ids'] if i)]
    # 연습 전 판으로 — 조각마다 통째로
    restored = []
    for name, val in rp['pre'].items():
        if name in SKIP or name not in SLICES:
            continue
        ctx.put(name, copy.deepcopy(val))
        restored.append(name)
    if keep_pending:
        ctx.edit('pending').extend(keep_pending)
    if keep_queue:
        ctx.edit('queue')['items'].extend(keep_queue)
    if real:
        _retally(ctx, real)
    # 장부 — 연습 줄 · 연습 회차 점수 기록은 지운다(가짜다). 진짜 줄은 그대로 두고 회차만 연습 전 것으로.
    if psid:
        for did in fake:
            db.execute('DELETE FROM donations WHERE id = ?', (did,))
        db.execute('DELETE FROM score_log WHERE session = ?', (psid,))
        db.execute('UPDATE donations SET session = ? WHERE session = ?', (prev_sid, psid))
    ctx.put('practice', {'on': False, 'ended_at': ctx.now, 'last': summary})
    ctx.notes.update({'summary': summary, 'kept_real': len(real), 'restored': len(restored)})


# ── 연습 · 테스트 후원 보내기 ──────────────────────────────
async def _sig_for(bus, amount):
    sigs = getattr(bus, 'sigs', None)
    if sigs is None or amount <= 0:
        return None, 0
    try:
        floor = await asyncio.to_thread(sigs.floor)
        if floor and amount < floor:
            return None, floor
        return await asyncio.to_thread(sigs.match, amount), floor
    except Exception as e:
        print('⚠️ [테스트 후원] 시그니처 찾기 실패 — 팝업만: %s' % type(e).__name__, flush=True)
        return None, 0


@route('/api/donation/test')
async def donation_test(req, bus, authed, answer):
    """🧪 화면 테스트 · 🎓 연습 후원 — 로그인 필요. {mode:'screen'|'practice', name, amount, message, title?, level?, via?, count?, expect?}"""
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    try:
        body = await req.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return _err('JSON 객체가 필요합니다', 400)
    try:
        amount = int(body.get('amount'))
    except (TypeError, ValueError):
        return _err('금액이 숫자가 아니에요', 400)
    if not 0 < amount <= 100000000:
        return _err('금액은 1원 ~ 1억 원이에요', 400)
    now = time.time()
    while _recent and now - _recent[0] > 60:
        _recent.popleft()
    count = max(1, min(5, int(body.get('count') or 1)))
    if len(_recent) + count > TEST_PER_MIN:
        return _err('1분에 %d건까지예요 — 잠깐 쉬었다가 보내 주세요' % TEST_PER_MIN, 429)
    mode = 'practice' if body.get('mode') == 'practice' else 'screen'
    if mode == 'practice' and not (bus.state.slices.get('practice') or {}).get('on'):
        return _err('연습 중이 아니에요 — 먼저 [연습 시작]을 눌러 주세요', 409)
    sig, floor = await _sig_for(bus, amount)
    out = []
    for i in range(count):
        _recent.append(now)
        cmd = {'name': str(body.get('name') or '')[:40], 'amount': amount, 'message': str(body.get('message') or '')[:300],
               'sig': sig, 'floor': floor, 'via': 'toon' if body.get('via') == 'toon' else ''}
        for k in ('title', 'level'):
            if body.get(k) not in (None, ''):
                cmd[k] = body[k]
        if mode == 'practice':
            cmd.update({'practice': True, 'tx_id': 'practice_%d_%s' % (int(now * 1000), uuid.uuid4().hex[:6]),
                        'expect': body.get('expect') or ''})
        else:
            cmd.update({'page_test': True, 'test': True, 'tx_id': 'pagetest_%d_%s' % (int(now * 1000), uuid.uuid4().hex[:6])})
        res = await bus.run('practice.donate', cmd, by='practice', authed=True)
        if not res.get('ok'):
            return _err(res.get('error') or '실패', int(res.get('code') or 400))
        out.append(res.get('id'))
    return {'status': 'success', 'mode': mode, 'ids': out, 'sig': (sig or {}).get('title') or ''}


@command('practice.donate')
def practice_donate(ctx, data):
    """/api/donation/test 가 부른다 — donation.add 를 그대로(연습 카드면 practice 조각에 채점용 한 줄)."""
    dn.donation_add(ctx, data)
    did = ctx.notes.get('id')
    if data.get('practice') and did:
        _note_card(ctx, did, data)
    elif data.get('page_test') and dn.practice_on(ctx):
        ctx.edit('practice')['tests'] = int(ctx.read('practice').get('tests') or 0) + 1


def _note_real(ctx, name, amount):
    """연습 중 진짜 후원이 들어왔다 — 조종실 빨간 띠용 숫자."""
    if dn.practice_on(ctx):
        did = ctx.notes.get('id')
        d = ctx.store.donation(did) if did else None
        if d and d.get('source') not in FAKE_SOURCES:
            p = ctx.edit('practice')
            p['real'] = int(p.get('real') or 0) + 1


dn.AFTER_DONATION.append(_note_real)


# ── 연습 시작 칸 · 그럴듯한 가짜 후원 ────────────────────────
GENERIC_MSGS = ['', '', '', '오늘도 화이팅!', '다들 고생 많아요', '재밌어요 ㅋㅋ', '첫 후원이에요', '응원합니다', '굿굿', '방송 너무 좋아요']
NAME_MSGS = ['{p} 화이팅!', '{p} 사랑해요', '오늘은 {p}!', '{p}님께', '{p} 가즈아', '{p} 응원합니다 ㅎㅎ', '{p}한테 주세요']
NEW_NAMES = ['처음왔어요', '지나가던행인', '귤까는중', '밤샘요정', '퇴근한직장인', '야식배달부', '구독자1호', '조용한팬']


def _members(db, min_rows=5):
    try:
        return [r['player'] for r in db.execute(
            'SELECT player, COUNT(*) AS c FROM donor_memory GROUP BY player HAVING c >= ? ORDER BY c DESC', (min_rows,))]
    except Exception:
        return []


def make_samples(db, n=1, members=None, rng=None):
    """그럴듯한 가짜 후원 n개 — [{name, amount, message, expect}]. expect = 기록상 정답(그 사람이 60% 넘게 준 멤버, 아니면 메시지 속 멤버)."""
    rng = rng or random.Random()
    members = [m for m in (members or _members(db)) if m]
    try:
        hist = collections.defaultdict(collections.Counter)
        for r in db.execute('SELECT donor, player FROM donor_memory'):
            hist[r['donor']][r['player']] += 1
        amts = [int(r['amount']) for r in db.execute(
            "SELECT amount FROM donations WHERE status != 'display' AND amount > 0 AND source NOT IN ('mobile', 'practice', 'test_page') "
            'ORDER BY at DESC LIMIT 400')]
    except Exception:
        hist, amts = {}, []
    amts = amts or [1000, 5000, 10000, 10000, 20000, 30000, 50000, 100000]
    donors = [d for d, c in hist.items() if members and any(p in members for p in c)]
    out = []
    for _ in range(max(1, min(20, int(n or 1)))):
        if donors and rng.random() < 0.8:
            name = rng.choice(donors)
            c = hist[name]
            top, cnt = c.most_common(1)[0]
            share = cnt / float(sum(c.values()))
            expect = top if share >= 0.6 and top in members else None
            p_in_msg = (expect or top) if rng.random() < 0.4 else None
        else:
            name = rng.choice(NEW_NAMES)
            expect, p_in_msg = None, (rng.choice(members) if members and rng.random() < 0.6 else None)
        if p_in_msg and p_in_msg in members:
            msg = rng.choice(NAME_MSGS).format(p=p_in_msg)
            expect = expect or p_in_msg
            if expect != p_in_msg:
                expect = p_in_msg                       # 메시지에 적힌 멤버가 정답 — 사람도 그렇게 준다
        else:
            msg = rng.choice(GENERIC_MSGS)
        out.append({'name': name, 'amount': rng.choice(amts), 'message': msg, 'expect': expect})
    return out


@route('/api/practice/info', methods=('GET',))
async def practice_info(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    sl = bus.state.slices
    names = [r.get('name') for r in ((sl.get('players') or {}).get('list') or []) if r.get('name')]
    return {'status': 'success', 'members': names or _members(bus.store.db)[:10],
            'live': bool((sl.get('session') or {}).get('live')), 'practice': sl.get('practice') or {'on': False}}


@route('/api/practice/sample', methods=('GET',))
async def practice_sample(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    try:
        n = int(req.query_params.get('n') or 1)
    except ValueError:
        n = 1
    sl = bus.state.slices
    members = [r.get('name') for r in ((sl.get('players') or {}).get('list') or []) if r.get('name')]
    return {'status': 'success', 'items': make_samples(bus.store.db, n, members or None)}
