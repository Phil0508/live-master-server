# -*- coding: utf-8 -*-
"""📮 명령 줄 — 명령은 한 줄로 서서 **하나씩** 처리된다.

한 명령 = 장부 한 번(BEGIN … COMMIT). 실패하면 장부도 조각도 처음 그대로다.
⚠️ 옛 서버는 file_lock 을 쥔 채로 Supabase 왕복(최대 18초)을 해서 그동안 점수 버튼까지 멈췄다.
   여기서는 명령 안에서 바깥으로 나가지 않는다. 바깥 조회가 필요하면 명령 **전에** 해서 결과를 같이 넘긴다.
"""
import asyncio
import time

from .state import State, Work

COMMANDS = {}        # 이름 → (처리 함수, 로그인 필요?)
PREFETCH = {}        # 이름 → fn(bus, data) → data — 명령 **전에**(잠금 밖 · 다른 갈래) 바깥 조회를 해서 data 에 붙인다
AFTER = []           # 모든 명령이 끝난 뒤 같은 작업본에서 fn(ctx) — 여러 조각을 함께 보는 규칙(대결 시계 ↔ 시그니처 재생 등)


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
           ⚠️ 그때 다시 조건을 보는 것은 그 명령의 몫이다 — 그 사이 상황이 바뀌었을 수 있다."""
        self.timers.append((float(sec), type_, dict(data or {})))


class Bus:
    def __init__(self, store, hub=None):
        self.store = store
        self.hub = hub
        self.state = State(store.load_slices())
        self.state.seq = store.last_seq()
        self.lock = asyncio.Lock()

    async def run(self, type_, data=None, by='', authed=True):
        """명령 하나. 돌려받는 값: {'ok': True, 'seq': N, ...notes} 또는 {'ok': False, 'error': …, 'code': …}"""
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
            res, changed, timers = self._apply(fn, type_, data, by)
        # ⚠️ 바뀐 게 없어도 번호(seq)는 보낸다 — 화면은 번호가 하나 건너뛰면 '빠진 쪽지' 로 보고 통째를 다시 받는다
        if res.get('ok') and self.hub is not None:
            await self.hub.publish(res['seq'], changed)
        if res.get('ok'):
            loop = asyncio.get_running_loop()
            for sec, t, d in timers:
                loop.call_later(sec, lambda t=t, d=d: asyncio.ensure_future(self.run(t, d, by='timer', authed=True)))
        return res

    def run_sync(self, type_, data=None, by=''):
        """검사 · 시작할 때 — 잠금 없이(같은 갈래에서만 부른다)."""
        fn, _ = COMMANDS[type_]
        res, _, _ = self._apply(fn, type_, data or {}, by)
        return res

    def _apply(self, fn, type_, data, by):
        work = Work(self.state)
        ctx = Ctx(self, work, by)
        self.store.begin()
        try:
            fn(ctx, data)
            for h in AFTER:
                h(ctx)
            changed = work.changed()
            if changed:
                self.store.put_slices(changed)
            seq = self.store.add_event(type_, by, data)
            self.store.commit()
        except CommandError as e:
            self.store.rollback()
            return dict({'ok': False, 'error': str(e), 'code': e.code}, **e.extra), {}, []
        except Exception:
            self.store.rollback()
            raise
        self.state.slices.update(changed)
        self.state.seq = seq
        return dict({'ok': True, 'seq': seq}, **ctx.notes), changed, ctx.timers
