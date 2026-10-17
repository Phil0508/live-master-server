# -*- coding: utf-8 -*-
"""📮 명령 줄 — 명령은 한 줄로 서서 **하나씩** 처리된다.

한 명령 = 장부 한 번(BEGIN … COMMIT). 실패하면 장부도 조각도 처음 그대로다.
⚠️ 옛 서버는 file_lock 을 쥔 채로 Supabase 왕복(최대 18초)을 해서 그동안 점수 버튼까지 멈췄다.
   여기서는 명령 안에서 바깥으로 나가지 않는다. 바깥 조회가 필요하면 명령 **전에** 해서 결과를 같이 넘긴다.

⏰ 예약(ctx.later) — 명령과 **같은 묶음**으로 장부 timers 표에 적는다(sturdy 10-17).
   ⚠️ 전에는 메모리(call_later)에만 있어서 방송 중 서버가 다시 켜지면(감시 장치 · 버전 바꾸기) 룰렛 · 슬롯이 끝나도
   무대가 안 돌아오고, 시그뒤집기 까보기가 안 덮였다. 이제 다시 켜지면(arm_timers) 남은 시간대로 다시 걸고, 지난 것은 바로 부른다.
   부른 명령이 성공하면 같은 묶음에서 지운다(두 번 안 부른다). 실패해도 지운다 — 실패한 명령은 아무것도 안 바꿨다.
🔁 명령 번호(cid) — 조종실은 명령마다 번호를 붙인다(shared/client.js). 같은 이름 · 같은 번호가 다시 오면 **다시 하지 않고**
   첫 결과를 돌려준다(dup: True). 8초 안에 답이 없어 '다시 눌러 주세요' 뒤 다시 눌러도 점수가 두 번 들어가지 않게.
   성공한 것은 장부(cmd_ids)에도 같은 묶음으로 적어, 그사이 서버가 다시 켜져도 기억한다(하루치).
   실패한 명령은 아무것도 안 바꿨으므로 기억하지 않는다 — 다시 오면 다시 해 본다.
"""
import asyncio
import collections
import time

from .state import State, Work

COMMANDS = {}        # 이름 → (처리 함수, 로그인 필요?)
PREFETCH = {}        # 이름 → fn(bus, data) → data — 명령 **전에**(잠금 밖 · 다른 갈래) 바깥 조회를 해서 data 에 붙인다
AFTER = []           # 모든 명령이 끝난 뒤 같은 작업본에서 fn(ctx) — 여러 조각을 함께 보는 규칙(대결 시계 ↔ 시그니처 재생 등)
BEFORE_COMMIT = []   # fn(ctx, type_, changed) — 바뀐 조각이 정해진 뒤 · 장부를 닫기 전(같은 묶음). ⚠️ 조각은 못 바꾼다(장부 표에 적기만)
                     # 예: ⏪ [방송 끝] 바로 전 조각을 되살리기 지점으로 적는다(domain/endundo.py)

CID_MAX = 100                 # 명령 번호 길이
CID_RECENT = 2000             # 메모리에 기억하는 번호 수
CID_KEEP_SEC = 24 * 3600      # 장부(cmd_ids)에 남기는 시간


class CommandError(Exception):
    """사람에게 보여 줄 거절 — 장부는 손대지 않는다. extra 는 답에 같이 실린다(예: wait_ms)."""

    def __init__(self, message, code=400, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


def command(name, auth=True):
    def deco(fn):
        COMMANDS[name] = (fn, auth)
        return fn
    return deco


def cid_key(type_, cid):
    """명령 번호 → 기억 열쇠('이름|번호'). 번호가 없거나 이상하면 None(번호 없이 — 옛 화면 · 리스너 · 예약)."""
    if isinstance(cid, bool) or not isinstance(cid, (str, int)):
        return None
    cid = str(cid).strip()
    if not 4 <= len(cid) <= CID_MAX or not cid.isprintable():
        return None
    return '%s|%s' % (type_, cid)


class Ctx:
    """처리 함수가 받는 것 — 조각 작업본 · 장부 · 누가 · 지금 시각."""

    def __init__(self, bus, work, by):
        self.bus = bus
        self.work = work
        self.store = bus.store
        self.by = by
        self.now = time.time()
        self.notes = {}           # 처리 함수가 돌려줄 덧붙임(예: 만든 후원 id)
        self.timers = []          # 잠시 뒤 서버가 스스로 할 명령 [(초, 이름, data)] — 명령이 성공했을 때만 건다

    def read(self, name):
        return self.work.read(name)

    def edit(self, name):
        return self.work.edit(name)

    def put(self, name, value):
        self.work.put(name, value)

    def later(self, sec, type_, data=None):
        """sec 초 뒤에 서버가 이 명령을 스스로 부른다(예: 까보기 6초 뒤 덮기 · 시간이 다 된 판 닫기).
           장부(timers)에 같은 묶음으로 적으므로 서버가 그사이 다시 켜져도 부른다(지났으면 켜지자마자).
           ⚠️ 그때 다시 조건을 보는 것은 그 명령의 몫이다 — 그 사이 상황이 바뀌었을 수 있다.
           ⚠️ data 는 JSON 으로 적힐 수 있는 것만(글자 · 숫자 · 목록 · 사전)."""
        self.timers.append((float(sec), type_, dict(data or {})))


class Bus:
    def __init__(self, store, hub=None):
        self.store = store
        self.hub = hub
        self.state = State(store.load_slices())
        self.state.seq = store.last_seq()
        self.lock = asyncio.Lock()
        self._armed = set()                           # 이 프로세스에서 이미 걸어 둔 예약 번호
        self._recent = collections.OrderedDict()      # 명령 번호 열쇠 → 첫 결과(성공한 것)
        self._inflight = {}                           # 명령 번호 열쇠 → 아직 처리 중인 첫 명령(Future)
        self._cid_writes = 0
        try:
            store.prune_cmd_ids(time.time() - CID_KEEP_SEC)
        except Exception:
            pass

    async def run(self, type_, data=None, by='', authed=True, cid=None, _timer=None):
        """명령 하나. 돌려받는 값: {'ok': True, 'seq': N, ...notes} 또는 {'ok': False, 'error': …, 'code': …}
           cid — 조종실이 붙인 명령 번호(같은 번호면 첫 결과 + dup). _timer — 예약으로 부른 것이면 그 예약 번호."""
        ent = COMMANDS.get(type_)
        if ent and ent[1] and not authed:
            return {'ok': False, 'error': '로그인이 필요합니다', 'code': 401}
        key = cid_key(type_, cid) if cid is not None else None
        if key is None:
            return await self._run(type_, data, by, authed, None, _timer)
        hit = self._recent.get(key)
        if hit is None:
            hit = self.store.cmd_result(key)          # 서버가 다시 켜지기 전에 들어간 것
        if hit is not None:
            return dict(hit, dup=True)
        fut = self._inflight.get(key)
        if fut is not None:                           # 첫 명령이 아직 처리 중(바깥 조회 · 잠금 기다림) — 그 결과를 같이 받는다
            return dict(await asyncio.shield(fut), dup=True)
        fut = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            res = await self._run(type_, data, by, authed, key, _timer)
        except BaseException:
            if not fut.done():
                fut.set_result({'ok': False, 'error': '서버 오류 — 다시 눌러 주세요', 'code': 500})
            raise
        finally:
            self._inflight.pop(key, None)
        if not fut.done():
            fut.set_result(res)
        if res.get('ok'):
            self._recent[key] = res
            while len(self._recent) > CID_RECENT:
                self._recent.popitem(last=False)
        return res

    async def _run(self, type_, data, by, authed, key, timer):
        ent = COMMANDS.get(type_)
        if not ent:
            return {'ok': False, 'error': '모르는 명령: %s' % type_, 'code': 404}
        fn, need_auth = ent
        if need_auth and not authed:
            return {'ok': False, 'error': '로그인이 필요합니다', 'code': 401}
        data = data if isinstance(data, dict) else {}
        pre = PREFETCH.get(type_)
        if pre is not None:
            try:
                data = await asyncio.to_thread(pre, self, data)
            except Exception as e:
                return {'ok': False, 'error': '미리 받아 오기 실패: %s' % type(e).__name__, 'code': 503}
        async with self.lock:
            res, changed, timers = self._apply(fn, type_, data, by, key=key, timer=timer)
        # ⚠️ 바뀐 게 없어도 번호(seq)는 보낸다 — 화면은 번호가 하나 건너뛰면 '빠진 쪽지' 로 보고 통째를 다시 받는다
        if res.get('ok') and self.hub is not None:
            await self.hub.publish(res['seq'], changed, self.state.slices)
        if res.get('ok'):
            for tid, due, t, d in timers:
                self._arm(tid, due, t, d)
        return res

    def run_sync(self, type_, data=None, by=''):
        """검사 · 시작할 때 — 잠금 없이(같은 갈래에서만 부른다). 예약은 장부에만 적히고 걸리지 않는다(다음에 켜질 때 건다)."""
        fn, _ = COMMANDS[type_]
        res, _, _ = self._apply(fn, type_, data or {}, by)
        return res

    # ── ⏰ 예약 ──
    def _arm(self, tid, due, type_, data):
        if tid in self._armed:
            return
        self._armed.add(tid)
        loop = asyncio.get_running_loop()
        loop.call_later(max(0.0, due - time.time()), lambda: asyncio.ensure_future(self._fire(tid, type_, data)))

    async def _fire(self, tid, type_, data):
        try:
            await self.run(type_, data, by='timer', authed=True, _timer=tid)
        except Exception as e:
            print('⚠️ [예약 명령 실패] %s: %s' % (type_, type(e).__name__), flush=True)
        finally:
            self._armed.discard(tid)
            try:
                async with self.lock:
                    self.store.drop_timer(tid)        # 성공했으면 이미 같은 묶음에서 지웠다 — 실패 · 넘어짐도 여기서 치운다
            except Exception:
                pass

    async def _fire_all(self, rows):
        for r in rows:
            await self._fire(r['id'], r['type'], r['data'])

    def arm_timers(self):
        """서버가 켜질 때(app lifespan) — 장부에 남은 예약을 다시 건다. 시간이 지난 것은 적힌 순서대로 바로 부른다.
           ⚠️ 돌고 있는 이벤트 루프 안에서 부른다. 돌려받는 값: {'due': 바로 부른 수, 'later': 다시 건 수}"""
        now = time.time()
        due, later = [], 0
        for r in self.store.timers():
            if r['id'] in self._armed:
                continue
            if r['due'] <= now:
                self._armed.add(r['id'])
                due.append(r)
            else:
                self._arm(r['id'], r['due'], r['type'], r['data'])
                later += 1
        if due:
            asyncio.ensure_future(self._fire_all(due))
        return {'due': len(due), 'later': later}

    def _apply(self, fn, type_, data, by, key=None, timer=None):
        work = Work(self.state)
        ctx = Ctx(self, work, by)
        self.store.begin()
        try:
            fn(ctx, data)
            for h in AFTER:
                h(ctx)
            changed = work.changed()
            for h in BEFORE_COMMIT:
                h(ctx, type_, changed)
            if changed:
                self.store.put_slices(changed)
            seq = self.store.add_event(type_, by, data)
            now = time.time()
            timers = [(self.store.add_timer(now + sec, t, d), now + sec, t, d) for sec, t, d in ctx.timers]
            if timer is not None:
                self.store.drop_timer(timer)          # 예약으로 부른 것 — 명령과 같은 묶음에서 지운다(다시 켜져도 두 번 안 부른다)
            res = dict({'ok': True, 'seq': seq}, **ctx.notes)
            if key:
                self.store.put_cmd_result(key, res)
                self._cid_writes += 1
                if self._cid_writes % 500 == 0:
                    self.store.prune_cmd_ids(now - CID_KEEP_SEC)
            self.store.commit()
        except CommandError as e:
            self.store.rollback()
            return dict({'ok': False, 'error': str(e), 'code': e.code}, **e.extra), {}, []
        except Exception:
            self.store.rollback()
            raise
        self.state.slices.update(changed)
        self.state.seq = seq
        return res, changed, timers
