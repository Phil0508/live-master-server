# -*- coding: utf-8 -*-
"""🧩 상태 = 이름 붙은 조각(slice)들.

조각마다 (기본값, 공개 여부)가 있다. 방송판(로그인 없음)은 **공개 조각만** 받는다.
⚠️ 옛 서버는 상태 하나를 통째로 보내고 strip_private_state 로 비밀 칸을 걸러 냈다 —
   새 칸을 만들 때 거르기를 잊으면 그대로 샜다. v2 는 조각을 만들 때 공개 여부를 **반드시** 정한다.
"""
import copy

SLICES = {}          # 이름 → (기본값 만드는 함수, 공개?, 숨김?)
# 🙈 보여 주는 사본(view) — 장부 · 조각은 원문 그대로 두고, **내보낼 때만** 화면에 맞게 고친 사본을 만든다(mask 10-17).
#    fn(name, value, slices, on_air) → 고친 사본 또는 None(그대로). on_air = 방송판(로그인 없음 · 방송판 종류 화면)이 받는 것.
#    ⚠️ value 를 직접 고치지 말 것(장부에 적힌 원본이다) — 고칠 때는 사본을 만들어 돌려준다.
VIEWS = []
# 이 조각이 바뀌면 같이 다시 보낼 조각 — 원문은 그대로인데 보여 주는 사본이 바뀌는 경우(금칙어 · 가리기 → 팝업 · 대기줄)
DEPENDS = {}


def slice_(name, public, default, hidden=False):
    """hidden=True — 어떤 화면에도 안 간다(조종실에도). 서버 안에서만 쓰는 진짜 답(시그뒤집기 카드 앞면 등)."""
    SLICES[name] = (default, public and not hidden, hidden)


def default(name):
    return copy.deepcopy(SLICES[name][0]())


def is_public(name):
    return bool(SLICES.get(name, (None, False, False))[1])


def is_hidden(name):
    return bool(SLICES.get(name, (None, False, False))[2])


def view(name, value, slices, on_air):
    """내보낼 사본 — VIEWS 를 차례로. 고칠 게 없으면 원본 그대로(복사 안 함)."""
    for fn in VIEWS:
        try:
            got = fn(name, value, slices, on_air)
        except Exception as e:          # 보여 주기 실패로 방송이 멈추면 안 된다 — 방송판이면 안전하게 비운다
            print('⚠️ [보여 주기 실패] %s: %s' % (name, type(e).__name__), flush=True)
            got = None
            if on_air:
                return None
        if got is not None:
            value = got
    return value


class State:
    """지금 상태. 조각은 dict/list 로 담는다. 바꿀 때는 Work(작업본)로만 바꾼다."""

    def __init__(self, saved=None):
        saved = saved or {}
        self.slices = {}
        for name in SLICES:
            v = saved.get(name)
            self.slices[name] = v if v is not None else default(name)
        self.seq = 0

    def snapshot(self, authed, on_air=None):
        """authed — 비공개 조각까지. on_air — 방송판이 받는 사본(금칙어 가린 글). 기본은 로그인 안 했으면 방송판."""
        on_air = (not authed) if on_air is None else on_air
        return {k: view(k, v, self.slices, on_air) for k, v in self.slices.items()
                if not is_hidden(k) and (authed or is_public(k))}

    def get(self, name):
        return self.slices[name]


class Work:
    """명령 하나의 작업본 — 고친 조각만 복사해 두었다가, 다 끝나면 한꺼번에 바꾼다(실패하면 버린다)."""

    def __init__(self, state):
        self.state = state
        self.copies = {}

    def read(self, name):
        """읽기만 — 작업본이 있으면 작업본(같은 명령 안에서 고친 것이 보이게)."""
        return self.copies[name] if name in self.copies else self.state.slices[name]

    def edit(self, name):
        if name not in self.copies:
            self.copies[name] = copy.deepcopy(self.state.slices[name])
        return self.copies[name]

    def put(self, name, value):
        self.copies[name] = value

    def changed(self):
        return {k: v for k, v in self.copies.items() if v != self.state.slices.get(k)}
