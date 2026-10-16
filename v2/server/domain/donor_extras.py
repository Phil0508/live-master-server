# -*- coding: utf-8 -*-
"""🏷️ 투네이션이 후원에 같이 보내는 것 — 칭호 · 레벨 · 투네이션 VIP · 후원자 번호표 · 다시 보기/테스트 표시.

옛 features/donation.py _donor_extras · _show_only(10-08 커밋 176db46 · 27ee92a) 를 그대로 옮겼다.
리스너(toon_listener.py donor_extras)가 이미 한 번 거른 값을 서버가 **한 번 더** 거른다 — 바깥에서 온 값이다.

  clean(data) → (pub, priv)
    pub  = 화면에 실어도 되는 것 {donor_title: {name, color?}, donor_level}
           칭호는 투네이션 **공식** 칭호만(type 101~300, 비어 오면 이름으로) — 크리에이터 칭호(type 301~)는 버린다
           (대표님 2026-10-08 "개인방 칭호 말고 공식만"). 색은 이름으로 정한다(블랙 다이아 = 검정 …), 칭호 그림은 안 쓴다.
    priv = 대기함(조종실) · 장부에만 둘 것 {toon_vip, donor_key} — ⚠️ 방송판(공개 조각)에는 절대 싣지 않는다.
           donor_key = 투네이션 계정(이메일형)을 리스너가 HMAC 으로 바꾼 16자. 이메일 원문은 서버에 오지도 않는다.
  show_only_kind(data) → 'replay' · 'test' · ''
    대시보드 '다시 보기'(replay=1) · '후원 테스트'(test) — 방송 화면(팝업 · 시그니처)에만 띄우고 장부(정산) · 대기함 ·
    후원 순위 · 시그 집계 · 월별 순위 · AI 기억에는 넣지 않는다(10-08 실측: 다시 보기 두 번이 80만 원 · 1만2천 원
    진짜 후원으로 장부에 들어갔다). ⚠️ 투네이션 신호에는 고유 번호가 없어 리스너가 tx_id 를 매번 새로 만든다 —
    tx_id 중복 거르기로는 못 막는다(v2/tests/test_donate_mig.py 가 보여 준다).

표(이 모듈이 만든다 — store.py 는 안 건드린다. 처음 쓸 때 CREATE TABLE IF NOT EXISTS · donor_memory 와 같은 방식)
  donor_keys  후원 한 건(tx_id)마다 한 줄 — tx_id · donor_key · level · title · vip · at(초)
              닉네임을 바꿔도 · 익명이어도 같은 사람을 알아보는 데 쓴다(옛 donor_keys 표 그대로, 옛 장부 옮기기가 이어 붙인다).
              ⚠️ 적기 실패는 후원을 막지 않는다 — 부가 정보다(옛 것과 같다).
"""
import re
import sqlite3

_HEX6 = re.compile(r'^#[0-9A-Fa-f]{6}$')
_HEX16 = re.compile(r'^[0-9a-f]{16}$')
# 🏷️ 투네이션 공식 칭호 색 — 이름에 든 낱말로 고른다(먼저 맞는 것). 옛 _OFFICIAL_TITLE_COLORS 그대로.
OFFICIAL_TITLE_COLORS = (('블랙', '#3A3A44'), ('블루', '#4DA3FF'), ('그린', '#34D399'), ('레드', '#FF5A5A'),
                         ('골드', '#F5C542'), ('금수저', '#F5C542'), ('노블레스', '#C9A7FF'), ('다이아', '#9EE7FF'))
OFFICIAL_TITLE_WORDS = ('다이아', '노블레스', '금수저', '투네이션', '후원왕')

_SCHEMA = (
    'CREATE TABLE IF NOT EXISTS donor_keys ('
    ' tx_id TEXT PRIMARY KEY, donor_key TEXT NOT NULL, level INTEGER, title TEXT, vip TEXT, at REAL)',
    'CREATE INDEX IF NOT EXISTS donor_keys_key ON donor_keys(donor_key)',
)


def official_title_color(name):
    n = str(name or '').replace(' ', '')
    for w, c in OFFICIAL_TITLE_COLORS:
        if w in n:
            return c
    return None


def clean(data):
    """리스너가 붙여 보낸 칭호 · 레벨 · VIP · 번호표를 다시 다듬는다. 돌려받는 값: (pub, priv) — 위 설명."""
    pub, priv = {}, {}
    t = data.get('title')
    if isinstance(t, dict):
        nm = ' '.join(str(t.get('name') or '').split())[:24]
        try:
            ttype = int(t.get('type') or 0)
        except (TypeError, ValueError):
            ttype = 0
        official = ttype < 301 and (101 <= ttype <= 300 or any(w in nm.replace(' ', '') for w in OFFICIAL_TITLE_WORDS))
        if nm and official:
            tt = {'name': nm}
            col = official_title_color(nm) or str(t.get('color') or '').strip()
            if _HEX6.match(col):
                tt['color'] = col.upper()
            pub['donor_title'] = tt
    try:
        lv = int(data.get('level'))
        if 0 < lv < 1000:
            pub['donor_level'] = lv
    except (TypeError, ValueError):
        pass
    vip = ' '.join(str(data.get('vip') or '').split())[:12]
    if vip:
        priv['toon_vip'] = vip
    key = str(data.get('donor_key') or '')
    if _HEX16.match(key):
        priv['donor_key'] = key
    return pub, priv


def show_only_kind(data):
    """'다시 보기'(replay) · '후원 테스트'(test) 표시 — 옛 것처럼 정확히 True 일 때만(문자 '1' 같은 것은 리스너가 이미 True 로 바꿔 보낸다)."""
    if data.get('replay') is True:
        return 'replay'
    if data.get('test') is True:
        return 'test'
    return ''


def ensure(store):
    """표가 없으면 만든다. ⚠️ executescript 는 열린 장부(BEGIN)를 몰래 COMMIT 하므로 쓰지 않는다 — 한 줄씩.
       명령 안(장부가 열려 있을 때)에서 만들면 그 명령이 되감길 때 표도 사라지므로 '만들었다' 고 기억하지 않는다."""
    if getattr(store, '_lm_donor_keys', False):
        return
    for q in _SCHEMA:
        store.db.execute(q)
    if not store.db.in_transaction:
        store._lm_donor_keys = True


def record_key(store, tx, priv, pub, at):
    """번호표 한 줄(tx_id 로 장부와 잇는다). 실패해도 후원은 그대로 간다 — 부가 정보다. 적었으면 True."""
    key = priv.get('donor_key')
    if not key or not tx:
        return False
    try:
        ensure(store)
        store.db.execute('INSERT OR IGNORE INTO donor_keys (tx_id, donor_key, level, title, vip, at) VALUES (?, ?, ?, ?, ?, ?)',
                         (str(tx), key, pub.get('donor_level'), (pub.get('donor_title') or {}).get('name'), priv.get('toon_vip'), float(at)))
        return True
    except sqlite3.Error as e:       # SQLite 는 문장 하나만 되감는다 — 후원(같은 명령)은 그대로 들어간다
        print('⚠️ [번호표 기록 실패 — 후원은 정상] %s' % type(e).__name__, flush=True)
        return False


def keys_for(store, donor_key, limit=200):
    """이 번호표로 들어온 후원 tx_id 들(최근 것부터) — 같은 사람을 알아볼 때(지금은 검사 · 점검용)."""
    ensure(store)
    return [r[0] for r in store.db.execute('SELECT tx_id FROM donor_keys WHERE donor_key = ? ORDER BY at DESC LIMIT ?',
                                           (donor_key, int(limit)))]
