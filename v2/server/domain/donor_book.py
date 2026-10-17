# -*- coding: utf-8 -*-
"""📒 후원자 장부(donor book) — 후원자 한 명 = 카드 한 장(person). 카드에 '누구 팬인지' 딱지가 붙고, 방송마다 저절로 쌓인다.

대표님 10-17 "데이터는 한번 모아서 구분하고 쌓아보자". 이번 판은 **보이기 · 쌓기까지** —
⚠️ 자동 배정(autopilot · donor_memory 판단)은 이 모듈을 안 본다(바꾸지 않는다, 6단계는 나중).

표(이 모듈이 만든다 — store.py 는 안 건드린다. donor_memory 처럼 CREATE TABLE IF NOT EXISTS 를 한 줄씩, executescript 금지)
  donor_person   카드 — pid('p_'+10자) · label(가장 최근에 쓴 닉네임) · pin(📌 고정 선수) · test(1=시험 이름) · note
  donor_alias    닉네임 → 카드. name = norm_donor(닉네임) — 한 닉네임은 한 카드에만. first_at · last_at · n(후원 수)
  donor_suggest  '같은 사람 같아요' 제안 — a<b(pid 둘) · why('key' 번호표 같음 · 'name' 이름 비슷 · 'bank' 계좌 짝) · status(open · merged · rejected)
                 ⚠️ **제안만** 한다(대표님): 번호표가 같아도 자동으로 안 묶는다 — [묶기](donor.merge)를 눌러야 묶인다. [풀기](donor.split) 가능.
                 풀면 그 짝을 'split' · rejected 로 적어 둔다 → 다시 채우기(donor.rebuild)가 같은 제안을 또 올리지 않는다.
  answer_log     정답지 — 후원 한 건 = 한 줄(ref = 장부 id). 기계 추천(guess) · 실제로 받은 선수(final) · 사람/자동(how) · 바꿨나(changed) · 되돌림(undone)
                 갈래 '가'(옛 기억 잇기, how='relink')도 같은 표에 쓴다 — SCHEMA 는 설계서 그대로.

딱지(tag) — 카드 기준, 그 카드의 모든 닉네임 donor_memory 를 합친다
  n = 기억 건수(시험 선수 · 명단에 없는 선수 빼고) · top = 가장 많이 받은 선수 · share = top/n
  📌 pin(PIN_ON 일 때만) → n<3 'new' → share≥0.90 · n≥5 'main'(💛 전담팬) → share≥0.60 'lean'(🧡 주력팬) → 'multi'(🌈 여러 멤버)
  club = 닉네임에 **확정된** 팬클럽 말(donor_clubs confirmed)이 들어 있으면 그 선수(딱지와 별도 칸). 추정(confirmed=false)은 안 쓴다.
  부가: total_won(장부 진짜 후원 합 — donor_clean.is_real_donation) · last_at · dormant(30일 넘음) · big(누적 상위 10%)
  선수 명단(roster): 지금 players 조각의 이름 + donor_memory 에 ROSTER_MIN_MEMORY 번 이상 받은 이름(시험 이름 빼고).
  ⚠️ 방송이 꺼져 있으면 players 조각이 비어서, 지금 조각만 보면 딱지가 전부 'new' 가 된다 — 그래서 기록으로 채운다(하드코딩 아님).

조각(비공개 — 조종실만. 방송판으로 안 샌다)
  donor_tags   {norm_name: {pid, tag, player, n, share, club}} — 대기 후원 카드 딱지용. 배정 · 되돌리기 · 새 카드 때 그 사람만 고치고,
               방송 시작 · 끝 · 카드 명령(묶기 · 풀기 …) · donor.rebuild 때 통째로 다시.
  donor_clubs  {word: {player, confirmed, n?, share?, names?}} — 밍플단 → 밍밍 · 앙플단 → 앙앙 은 확정. 나머지는 기록으로 만든 추정 후보.
길(로그인) GET /api/donors/book · /api/donors/person/{pid} · /api/donors/suggest
명령 donor.merge {a, b} · donor.split {name} · donor.suggest_reject {id} · donor.pin {pid, player|null} · donor.mark_test {pid, test}
     donor.note {pid, note} · donor.club_set {word, player|null, confirmed} · donor.rebuild {}
고리(쓰기 실패해도 후원 · 배정은 그대로 — SAVEPOINT, donor_memory._after_score 와 같다)
  donation.AFTER_DONATION  새 닉네임이면 카드 · 번호표가 다른 카드에 있으면 'key' 제안 · 계좌 입금이면 'bank' 제안
  players.AFTER_SCORE      answer_log 한 줄(기계 추천은 대기 카드의 auto — autopilot 이 붙인 것)
  donation.ON_ASSIGN       조종실 🚗 오토파일럿(via 'ap')이 준 것 → how 'auto'
  bus.AFTER                autopilot 의 🤖 AI 배정(notes.by 'autopilot-ai') → how 'ai'
  players.ON_UNDO          answer_log.undone = 1 (다시 주면 그 줄을 새로 덮어쓴다)
개인정보: 입금자 실명(bank_inbox.holder)은 메모리에서 지문(bank_learn.holder_key)으로만 쓰고 표 · 조각 · 답 어디에도 안 넣는다.
"""
import json
import math
import re
import time
import uuid

from fastapi.responses import JSONResponse

from .. import bus as busmod
from ..bus import CommandError, command
from ..state import slice_
from . import bank_learn as bl
from . import donation as dn
from . import donor_clean as dc
from . import donor_extras as dx
from . import donor_memory as dm
from . import players as pl
from . import session as ses
from .legacy import route
from .rules import norm_donor

# 📌 고정(대표님이 "이 사람은 밍밍" 하고 못박기) — **대표님 답 대기**. 켜려면 이 한 줄을 True 로.
#    끄면: donor.pin 이 409 로 이유를 말하고 막고, 딱지 계산이 pin 을 안 본다(적어 둔 pin 값은 지우지 않는다).
PIN_ON = False

MAIN_SHARE, MAIN_MIN = 0.90, 5        # 💛 전담팬 — 한 멤버에게 90% 이상 · 5번 이상(대표님)
LEAN_SHARE = 0.60                     # 🧡 주력팬
NEW_MIN = 3                           # 이보다 적으면 'new'
DORMANT_SEC = 30 * 86400              # 마지막 후원이 30일 넘음
BIG_TOP = 0.10                        # 누적 상위 10%
ROSTER_MIN_MEMORY = 5                 # 기억에 이만큼 받은 이름은 꺼진 방송에도 선수로 본다
RECENT_MAX = 20
NOTE_MAX = 300
WORD_MAX = 12
TAGS = ('pin', 'new', 'main', 'lean', 'multi')
WHYS = ('key', 'name', 'bank')
# 🎌 팬클럽 사전 — 대표님이 확정한 것(10-17). 나머지는 기록으로 추정 후보만(confirmed=false — 딱지에 안 쓴다).
CONFIRMED_CLUBS = {'밍플단': '밍밍', '앙플단': '앙앙'}
CLUB_SEEDS = ('7싸단', '제이7싸단', '제이설싸단', '원플단', '다림단', '야다림단', '잔단')     # 대표님이 말한 말 — 누구 팬클럽인지는 기록으로 어림
CLUB_RE = re.compile(r'([0-9A-Za-z가-힣]{1,3}(?:플단|싸단))')                            # 닉네임에서 더 찾기
CLUB_GUESS_MIN, CLUB_GUESS_SHARE = 3, 0.60
NAME_SUG_MIN, NAME_SUG_RATIO, NAME_SUG_COMMON = 3, 0.60, 3     # 이름 비슷 — 보수적으로(아래 _name_pairs)
GUESS_HOW = {'이름': 'rule', '별명': 'alias', '이력': 'history', 'AI': 'ai'}

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS donor_person ("
    " pid TEXT PRIMARY KEY, label TEXT NOT NULL, pin TEXT, test INTEGER NOT NULL DEFAULT 0,"
    " note TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL)",
    "CREATE TABLE IF NOT EXISTS donor_alias ("
    " name TEXT PRIMARY KEY, pid TEXT NOT NULL, first_at REAL, last_at REAL, n INTEGER NOT NULL DEFAULT 0)",
    "CREATE INDEX IF NOT EXISTS donor_alias_pid ON donor_alias(pid)",
    "CREATE TABLE IF NOT EXISTS donor_suggest ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, a TEXT NOT NULL, b TEXT NOT NULL, why TEXT NOT NULL,"
    " detail TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open', at REAL NOT NULL, UNIQUE(a, b))",
    "CREATE TABLE IF NOT EXISTS answer_log ("
    " ref TEXT PRIMARY KEY, at REAL NOT NULL, session TEXT NOT NULL DEFAULT '', name TEXT NOT NULL,"
    " amount INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '', guess TEXT, guess_conf REAL, guess_how TEXT,"
    " final TEXT NOT NULL DEFAULT '[]', how TEXT NOT NULL DEFAULT '', changed INTEGER, undone INTEGER NOT NULL DEFAULT 0)",
    "CREATE INDEX IF NOT EXISTS answer_log_name ON answer_log(name)",
)


def _default_clubs():
    return {w: {'player': p, 'confirmed': True} for w, p in CONFIRMED_CLUBS.items()}


slice_('donor_tags', False, lambda: {})
slice_('donor_clubs', False, _default_clubs)


def ensure(db):
    """표가 없으면 만든다(기억 · 번호표 · 계좌 짝 표도 — 읽을 때 없으면 넘어지지 않게). 한 줄씩(열린 BEGIN 을 몰래 끝내지 않는다)."""
    for q in SCHEMA + dm._SCHEMA + dx._SCHEMA + (bl.SCHEMA,):
        db.execute(q)


def _has(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def _new_pid():
    return 'p_' + uuid.uuid4().hex[:10]


def skip_name(name):
    """새 카드를 안 만드는 이름 — 익명 · 시험 이름(숫자만 · Player N · 테스트)."""
    n = norm_donor(name)
    return n == '익명' or bool(dc.test_name_reason(n))


# ── 카드 · 닉네임 ─────────────────────────────────────────────
def pid_of(db, name):
    r = db.execute('SELECT pid FROM donor_alias WHERE name = ?', (norm_donor(name),)).fetchone()
    return r['pid'] if r else None


def person(db, pid):
    r = db.execute('SELECT * FROM donor_person WHERE pid = ?', (str(pid or ''),)).fetchone()
    return dict(r) if r else None


def names_of(db, pid):
    return [dict(r) for r in db.execute('SELECT * FROM donor_alias WHERE pid = ? ORDER BY COALESCE(last_at, 0) DESC, name',
                                        (pid,))]


def _relabel(db, pid, now):
    """보이는 이름 = 가장 최근에 쓴 닉네임. 바뀔 때만 고친다(다시 채우기를 여러 번 돌려도 같게)."""
    r = db.execute('SELECT name FROM donor_alias WHERE pid = ? ORDER BY COALESCE(last_at, 0) DESC, n DESC, name LIMIT 1',
                   (pid,)).fetchone()
    if r:
        db.execute('UPDATE donor_person SET label = ?, updated = ? WHERE pid = ? AND label != ?', (r['name'], now, pid, r['name']))


def _create(db, name, first_at, last_at, n, now):
    pid = _new_pid()
    db.execute('INSERT INTO donor_person(pid, label, created, updated) VALUES(?, ?, ?, ?)', (pid, name, now, now))
    db.execute('INSERT INTO donor_alias(name, pid, first_at, last_at, n) VALUES(?, ?, ?, ?, ?)', (name, pid, first_at, last_at, n))
    return pid


def ensure_card(db, name, at, n_add=1):
    """닉네임 → 카드(없으면 새 카드). 후원 하나가 들어올 때 — n 을 하나 올리고 마지막 시각을 고친다. 돌려받는 값: (pid, 새 카드인가)"""
    nm = norm_donor(name)
    at = float(at)
    pid = pid_of(db, nm)
    if pid:
        db.execute('UPDATE donor_alias SET n = n + ?, last_at = MAX(COALESCE(last_at, 0), ?),'
                   ' first_at = MIN(COALESCE(first_at, ?), ?) WHERE name = ?', (int(n_add), at, at, at, nm))
        _relabel(db, pid, at)
        return pid, False
    return _create(db, nm, at, at, int(n_add), at), True


def open_suggest(db, a, b, why, detail, at):
    """제안 하나 — 같은 짝은 한 줄(UNIQUE). 이미 있으면(열림 · 거절 · 묶음 · 풀기) 그대로 둔다. 새로 열었으면 True."""
    if not a or not b or a == b:
        return False
    a, b = sorted((a, b))
    cur = db.execute("INSERT OR IGNORE INTO donor_suggest(a, b, why, detail, status, at) VALUES(?, ?, ?, ?, 'open', ?)",
                     (a, b, why, str(detail or '')[:200], float(at)))
    return cur.rowcount > 0


def _star(db, pids, why, detail, at):
    """여러 카드가 같은 사람 같을 때 — 가장 많이 쓴 카드 하나에 나머지를 잇는 제안(짝마다 다 열면 너무 많다). 연 수."""
    pids = sorted(set(p for p in pids if p))
    if len(pids) < 2:
        return 0
    use = {p: int(db.execute('SELECT COALESCE(SUM(n), 0) FROM donor_alias WHERE pid = ?', (p,)).fetchone()[0]) for p in pids}
    hub = max(pids, key=lambda p: (use[p], p))
    return sum(1 for p in pids if p != hub and open_suggest(db, hub, p, why, detail, at))


def merge(db, a, b, now):
    """b 카드를 a 로 — 닉네임들을 옮기고 b 를 지운다. a · b 사이 제안은 merged, b 의 다른 제안은 a 로 옮긴다."""
    pa, pb = person(db, a), person(db, b)
    if not pa or not pb:
        raise LookupError('없는 카드')
    if a == b:
        raise ValueError('같은 카드')
    db.execute('UPDATE donor_alias SET pid = ? WHERE pid = ?', (a, b))
    pin = pa['pin'] or pb['pin']
    note = ' / '.join(x for x in (pa['note'], pb['note']) if x)[:NOTE_MAX]
    db.execute('UPDATE donor_person SET pin = ?, note = ?, updated = ? WHERE pid = ?', (pin, note, now, a))
    db.execute('DELETE FROM donor_person WHERE pid = ?', (b,))
    x, y = sorted((a, b))
    db.execute("UPDATE donor_suggest SET status = 'merged', at = ? WHERE a = ? AND b = ?", (now, x, y))
    rows = db.execute('SELECT * FROM donor_suggest WHERE (a = ? OR b = ?) AND NOT (a = ? AND b = ?)', (b, b, x, y)).fetchall()
    for r in rows:
        other = r['b'] if r['a'] == b else r['a']
        db.execute('DELETE FROM donor_suggest WHERE id = ?', (r['id'],))
        if other == a:
            continue
        na, nb = sorted((a, other))
        db.execute('INSERT OR IGNORE INTO donor_suggest(a, b, why, detail, status, at) VALUES(?, ?, ?, ?, ?, ?)',
                   (na, nb, r['why'], r['detail'], r['status'], r['at']))
    _relabel(db, a, now)


def split(db, name, now):
    """그 닉네임 하나를 새 카드로 뗀다(묶은 것 풀기). 돌려받는 값: 새 pid"""
    nm = norm_donor(name)
    pid = pid_of(db, nm)
    if not pid:
        raise LookupError('없는 닉네임')
    if len(names_of(db, pid)) <= 1:
        raise ValueError('이미 혼자인 카드')
    old = person(db, pid)
    new = _new_pid()
    db.execute('INSERT INTO donor_person(pid, label, test, created, updated) VALUES(?, ?, ?, ?, ?)',
               (new, nm, int(old['test'] or 0), now, now))
    db.execute('UPDATE donor_alias SET pid = ? WHERE name = ?', (new, nm))
    _relabel(db, pid, now)
    x, y = sorted((pid, new))       # 대표님이 '다른 사람' 이라 했다 — 다시 채우기가 이 짝을 또 제안하지 않게
    db.execute("INSERT OR REPLACE INTO donor_suggest(a, b, why, detail, status, at) VALUES(?, ?, 'split', ?, 'rejected', ?)",
               (x, y, '풀기: ' + nm, now))
    return new


# ── 선수 명단 · 딱지 ────────────────────────────────────────────
def roster(db, players=None):
    """딱지에 셀 선수 — 지금 판 이름 + 기억에 ROSTER_MIN_MEMORY 번 이상 받은 이름(시험 이름은 빼고). 맨 위 설명."""
    out = set()
    p = players if isinstance(players, dict) else {}
    for key in ('list', 'extra'):
        for r in p.get(key) or []:
            if isinstance(r, dict) and r.get('name'):
                out.add(str(r['name']))
    if _has(db, 'donor_memory'):
        for r in db.execute('SELECT player, COUNT(*) AS c FROM donor_memory GROUP BY player HAVING c >= ?', (ROSTER_MIN_MEMORY,)):
            out.add(str(r['player']))
    return {n for n in out if n and not dc.test_name_reason(n)}


def club_words(clubs):
    """확정된 팬클럽 말 → 선수(긴 말 먼저 — '제이7싸단' 이 '7싸단' 보다 먼저 맞게)."""
    got = {w: c.get('player') for w, c in (clubs or {}).items() if isinstance(c, dict) and c.get('confirmed') and c.get('player')}
    return sorted(got.items(), key=lambda kv: (-len(kv[0]), kv[0]))


def club_of(names, words):
    """닉네임들(이름, 쓴 수) 중 확정된 팬클럽 말이 든 것 → 그 선수(여럿이면 많이 쓴 닉네임 쪽)."""
    score = {}
    for nm, n in names:
        for w, p in words:
            if w in nm:
                score[p] = score.get(p, 0) + max(1, int(n or 0))
                break
    if not score:
        return None
    return max(score.items(), key=lambda kv: (kv[1], kv[0]))[0]


def tag_of(players_n, pin=None):
    """{선수: 건수} → (tag, player, n, share). 우선순위는 맨 위 설명."""
    n = sum(players_n.values())
    top, c = (max(players_n.items(), key=lambda kv: (kv[1], kv[0])) if players_n else (None, 0))
    share = (c / n) if n else 0.0
    if PIN_ON and pin:
        return 'pin', pin, n, round(share, 2)
    if n < NEW_MIN:
        tag = 'new'
    elif share >= MAIN_SHARE and n >= MAIN_MIN:
        tag = 'main'
    elif share >= LEAN_SHARE:
        tag = 'lean'
    else:
        tag = 'multi'
    return tag, top, n, round(share, 2)


def _totals(db):
    """장부 진짜 후원 — 정규화 이름 → (합, 마지막 시각, 건수). 화면에만 줄(display)은 뺀다."""
    out = {}
    for r in db.execute("SELECT name, amount, message, source, status, at FROM donations WHERE status != 'display'"):
        if not dc.is_real_donation(dict(r)):
            continue
        k = norm_donor(r['name'])
        t = out.setdefault(k, [0, 0.0, 0])
        t[0] += int(r['amount'] or 0)
        t[1] = max(t[1], float(r['at'] or 0))
        t[2] += 1
    return out


def compute(db, roster_names, clubs, now=None, pids=None, totals=None):
    """카드들의 딱지 · 부가 정보. pids 를 주면 그 카드만(배정 · 되돌리기 때). 돌려받는 값: {pid: info}"""
    ensure(db)
    now = time.time() if now is None else now
    words = club_words(clubs)
    if pids is not None:
        pids = [p for p in pids if p]
        if not pids:
            return {}
        ph = ', '.join('?' * len(pids))
        persons = [dict(r) for r in db.execute('SELECT * FROM donor_person WHERE pid IN (%s)' % ph, tuple(pids))]
        aliases = [dict(r) for r in db.execute('SELECT * FROM donor_alias WHERE pid IN (%s)' % ph, tuple(pids))]
    else:
        persons = [dict(r) for r in db.execute('SELECT * FROM donor_person')]
        aliases = [dict(r) for r in db.execute('SELECT * FROM donor_alias')]
    by_pid = {}
    for a in aliases:
        by_pid.setdefault(a['pid'], []).append(a)
    names = [a['name'] for a in aliases]
    mem = {}
    for i in range(0, len(names), 500):
        chunk = names[i:i + 500]
        q = 'SELECT donor, player, COUNT(*) AS c, MAX(at) AS last FROM donor_memory WHERE donor IN (%s) GROUP BY donor, player'
        for r in db.execute(q % ', '.join('?' * len(chunk)), tuple(chunk)):
            mem.setdefault(r['donor'], []).append((r['player'], int(r['c']), float(r['last'] or 0)))
    tot = totals if totals is not None else _totals(db)
    sugg = {}
    for r in db.execute("SELECT a, b FROM donor_suggest WHERE status = 'open'"):
        sugg[r['a']] = sugg.get(r['a'], 0) + 1
        sugg[r['b']] = sugg.get(r['b'], 0) + 1
    out = {}
    for p in persons:
        al = sorted(by_pid.get(p['pid'], []), key=lambda a: (-(a['last_at'] or 0), a['name']))
        cnt, other, last = {}, 0, 0.0
        total = 0
        for a in al:
            for pl_, c, lt in mem.get(a['name'], []):
                last = max(last, lt)
                if pl_ in roster_names:
                    cnt[pl_] = cnt.get(pl_, 0) + c
                else:
                    other += c
            t = tot.get(a['name'])
            if t:
                total += t[0]
                last = max(last, t[1])
            last = max(last, float(a['last_at'] or 0))
        tag, player, n, share = tag_of(cnt, p['pin'])
        out[p['pid']] = {
            'pid': p['pid'], 'label': p['label'], 'tag': tag, 'player': player, 'share': share, 'n': n,
            'club': club_of([(a['name'], a['n']) for a in al], words),
            'players': dict(sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))), 'excluded': other,
            'total_won': total, 'last_at': last or None, 'dormant': bool(last) and (now - last) > DORMANT_SEC,
            'names': [a['name'] for a in al], 'pin': p['pin'], 'test': int(p['test'] or 0), 'note': p['note'],
            'suspect': dc.test_name_reason(p['label']), 'sugg': sugg.get(p['pid'], 0)}
    _mark_big(db, out, tot, whole=pids is None)
    return out


def _mark_big(db, out, tot, whole):
    """누적 상위 10%(시험 카드 · 0원 빼고). 일부만 계산할 때도 기준선은 전체로 잡는다."""
    if whole:
        totals = sorted((x['total_won'] for x in out.values() if not x['test'] and x['total_won'] > 0), reverse=True)
    else:
        per = {}
        for r in db.execute('SELECT a.pid, a.name FROM donor_alias a JOIN donor_person p ON p.pid = a.pid WHERE p.test = 0'):
            t = tot.get(r['name'])
            if t:
                per[r['pid']] = per.get(r['pid'], 0) + t[0]
        totals = sorted((v for v in per.values() if v > 0), reverse=True)
    cut = totals[max(0, math.ceil(len(totals) * BIG_TOP) - 1)] if totals else None
    for x in out.values():
        x['big'] = bool(cut) and not x['test'] and x['total_won'] >= cut and x['total_won'] > 0


def tag_entry(info):
    return {'pid': info['pid'], 'tag': info['tag'], 'player': info['player'], 'n': info['n'], 'share': info['share'],
            'club': info['club']}


def tags_slice(infos):
    """donor_tags 조각 — 시험 카드는 뺀다(목록 · 딱지에서 뺀다)."""
    out = {}
    for info in infos.values():
        if info['test']:
            continue
        e = tag_entry(info)
        for nm in info['names']:
            out[nm] = e
    return out


# ── 처음 채우기(다시 채우기) — 이미 있는 데이터로 · 여러 번 돌려도 같은 결과 ─────────
def _canon(n):
    return re.sub(r'[^0-9a-z가-힣ㄱ-ㅎ]', '', str(n or '').lower())


def _club_like(c):
    return bool(CLUB_RE.fullmatch(c)) or c in CLUB_SEEDS or c in CONFIRMED_CLUBS


def _name_pairs(names):
    """이름 비슷 — 보수적으로. ① 띄어쓰기 · 기호 · 대소문자만 다름 ② 긴 이름 안에 짧은 이름(3자 이상 · 긴 이름의 60% 이상)이
       통째로 들어 있고, 그 짧은 이름이 흔하지 않음(NAME_SUG_COMMON 개 넘는 이름에 들어 있으면 낱말이라 본다) · 팬클럽 말 자체가 아님.
       돌려받는 값: [(이름1, 이름2, 까닭)]"""
    canon = {n: _canon(n) for n in names}
    out = []
    by = {}
    for n, c in canon.items():
        if c:
            by.setdefault(c, []).append(n)
    for c, lst in by.items():
        lst = sorted(lst)
        for other in lst[1:]:
            out.append((lst[0], other, "'%s' · '%s' 띄어쓰기 · 기호만 다름" % (lst[0], other)))
    uniq = sorted({c: n for n, c in canon.items() if c}.items())
    for i, (cs, ns) in enumerate(uniq):
        if len(cs) < NAME_SUG_MIN or _club_like(cs):
            continue                 # 팬클럽 말('밍플단' · '7싸단')만 닉네임으로 쓴 것은 다른 사람이 여럿 붙여 쓴다 — 같은 사람 근거가 아니다
        holders = [(cl, nl) for cl, nl in uniq if cl != cs and cs in cl]
        if not holders or len(holders) > NAME_SUG_COMMON:
            continue
        for cl, nl in holders:
            if len(cs) / len(cl) >= NAME_SUG_RATIO:
                out.append((ns, nl, "'%s' 가 '%s' 안에 그대로 있음" % (ns, nl)))
    return out


def _bank_groups(db):
    """계좌 짝 — 같은 입금 통장(입금자 지문)에서 보낸 닉네임들. ⚠️ 실명은 메모리에서 지문으로만 바꾸고 버린다.
       돌려받는 값: [set(정규화 닉네임)] (둘 이상인 것만)"""
    groups = {}
    if _has(db, 'bank_inbox'):
        holder = {r['id']: r['holder'] for r in db.execute("SELECT id, holder FROM bank_inbox WHERE holder != ''")}
        for r in db.execute("SELECT tx_id, name, amount, message, source, status FROM donations WHERE tx_id LIKE 'manual\\_bank\\_%' ESCAPE '\\'"):
            if r['status'] == 'display' or not dc.is_real_donation(dict(r)):
                continue
            hk = bl.holder_key(holder.get(bl.card_of_tx(r['tx_id']), ''))
            if hk and not skip_name(r['name']):
                groups.setdefault(hk, set()).add(norm_donor(r['name']))
    if _has(db, 'bank_learn'):
        for r in db.execute('SELECT hk, name FROM bank_learn'):
            if r['hk'] in groups and not skip_name(r['name']):
                groups[r['hk']].add(norm_donor(r['name']))
    return [g for g in groups.values() if len(g) > 1]


def club_candidates(db, clubs, roster_names):
    """팬클럽 추정 후보 — 확정 안 된 말마다, 그 말이 든 닉네임들의 기억으로 누구 팬클럽 같은지(근거 n · share · 이름 수)."""
    ensure(db)
    words = set(CLUB_SEEDS)
    all_names = set(r['name'] for r in db.execute('SELECT name FROM donor_alias'))
    all_names |= set(r['donor'] for r in db.execute('SELECT DISTINCT donor FROM donor_memory'))
    confirmed = [w for w, c in (clubs or {}).items() if isinstance(c, dict) and c.get('confirmed') and c.get('player')]
    for nm in all_names:
        for w in CLUB_RE.findall(nm):
            if not any(cw in w for cw in confirmed):
                words.add(w)
    out = {}
    for w in sorted(words):
        c = (clubs or {}).get(w)
        if isinstance(c, dict) and c.get('confirmed'):
            continue
        hit = sorted(n for n in all_names if w in n)
        cnt = {}
        for i in range(0, len(hit), 500):
            chunk = hit[i:i + 500]
            for r in db.execute('SELECT player, COUNT(*) AS c FROM donor_memory WHERE donor IN (%s) GROUP BY player'
                                % ', '.join('?' * len(chunk)), tuple(chunk)):
                if r['player'] in roster_names:
                    cnt[r['player']] = cnt.get(r['player'], 0) + int(r['c'])
        n = sum(cnt.values())
        top, tc = max(cnt.items(), key=lambda kv: (kv[1], kv[0])) if cnt else (None, 0)
        share = (tc / n) if n else 0.0
        out[w] = {'player': top if n >= CLUB_GUESS_MIN and share >= CLUB_GUESS_SHARE else None, 'confirmed': False,
                  'n': n, 'share': round(share, 2), 'names': len(hit),
                  'players': dict(sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[:3])}
    return out


def merge_clubs(clubs, cands):
    """확정(대표님이 정한 것)은 그대로, 추정은 새 후보로 바꾼다."""
    out = {w: dict(c) for w, c in (clubs or {}).items() if isinstance(c, dict) and c.get('confirmed')}
    for w, c in cands.items():
        if w not in out:
            out[w] = c
    return out


def build(db, now=None, players=None, clubs=None):
    """장부(진짜 후원만) · donor_memory · donor_keys · bank_learn 에서 카드 · 닉네임 · 제안을 만든다(멱등 — 있는 카드는 그대로,
       묶은 것 · 거절한 제안 · 푼 짝은 다시 안 만든다). 돌려받는 값: {'tags', 'clubs', 'stats'}"""
    ensure(db)
    now = time.time() if now is None else float(now)
    seen = {}            # 정규화 이름 → [first, last, 장부 건수, 기억 건수]
    for r in db.execute("SELECT name, amount, message, source, status, at FROM donations WHERE status != 'display' ORDER BY at"):
        if not dc.is_real_donation(dict(r)):
            continue
        nm = norm_donor(r['name'])
        if nm == '익명':
            continue
        s = seen.setdefault(nm, [float(r['at']), float(r['at']), 0, 0])
        s[0], s[1] = min(s[0], float(r['at'])), max(s[1], float(r['at']))
        s[2] += 1
    for r in db.execute('SELECT donor, COUNT(*) AS c, MIN(at) AS f, MAX(at) AS l FROM donor_memory GROUP BY donor'):
        nm = norm_donor(r['donor'])
        if nm == '익명':
            continue
        s = seen.setdefault(nm, [float(r['f']), float(r['l']), 0, 0])
        s[0], s[1] = min(s[0], float(r['f'])), max(s[1], float(r['l']))
        s[3] += int(r['c'])
    made = 0
    for nm, (f, l, nl, nmem) in sorted(seen.items(), key=lambda kv: (kv[1][0], kv[0])):
        n = max(nl, nmem)
        cur = db.execute('SELECT * FROM donor_alias WHERE name = ?', (nm,)).fetchone()
        if cur is None:
            _create(db, nm, f, l, n, now)
            made += 1
        elif (cur['first_at'], cur['last_at'], cur['n']) != (f, l, n):
            db.execute('UPDATE donor_alias SET first_at = ?, last_at = ?, n = ? WHERE name = ?', (f, l, n, nm))
    for r in db.execute('SELECT pid FROM donor_person').fetchall():
        _relabel(db, r['pid'], now)
    opened = {'key': 0, 'name': 0, 'bank': 0}
    # 번호표 같음 — 같은 투네이션 계정(리스너가 HMAC 으로 바꾼 번호표)
    keyed = {}
    for r in db.execute('SELECT k.donor_key, d.name FROM donor_keys k JOIN donations d ON d.tx_id = k.tx_id'):
        if not skip_name(r['name']):
            keyed.setdefault(r['donor_key'], set()).add(norm_donor(r['name']))
    for k, nms in sorted(keyed.items()):
        pids = {pid_of(db, n) for n in nms}
        if len(pids - {None}) > 1:
            shown = ' · '.join("'%s'" % n for n in sorted(nms)[:6])
            opened['key'] += _star(db, pids, 'key', '같은 투네이션 번호표: ' + shown, now)
    # 이름 비슷(보수적)
    alias = {r['name']: r['pid'] for r in db.execute('SELECT name, pid FROM donor_alias')}
    plain = [n for n in alias if not skip_name(n)]
    for a, b, why in _name_pairs(plain):
        if alias[a] != alias[b] and open_suggest(db, alias[a], alias[b], 'name', why, now):
            opened['name'] += 1
    # 계좌 짝
    for g in _bank_groups(db):
        pids = {alias.get(n) for n in g}
        if len(pids - {None}) > 1:
            opened['bank'] += _star(db, pids, 'bank', '같은 통장에서 보낸 이름: ' + ' · '.join("'%s'" % n for n in sorted(g)[:6]), now)
    ros = roster(db, players)
    cl = merge_clubs(clubs if clubs is not None else _default_clubs(), club_candidates(db, clubs or _default_clubs(), ros))
    infos = compute(db, ros, cl, now=now)
    return {'tags': tags_slice(infos), 'clubs': cl, 'stats': stats(db, infos, made=made, opened=opened)}


def stats(db, infos, made=0, opened=None):
    tags = {t: 0 for t in TAGS}
    for x in infos.values():
        if not x['test']:
            tags[x['tag']] = tags.get(x['tag'], 0) + 1
    op = {w: 0 for w in WHYS}
    for r in db.execute("SELECT why, COUNT(*) AS c FROM donor_suggest WHERE status = 'open' GROUP BY why"):
        op[r['why']] = int(r['c'])
    return {'persons': len(infos), 'aliases': int(db.execute('SELECT COUNT(*) FROM donor_alias').fetchone()[0]),
            'test': sum(1 for x in infos.values() if x['test']),
            'suspect': sum(1 for x in infos.values() if x['suspect'] and not x['test']),
            'big': sum(1 for x in infos.values() if x['big']), 'dormant': sum(1 for x in infos.values() if x['dormant']),
            'club': sum(1 for x in infos.values() if x['club'] and not x['test']),
            'tags': tags, 'open_suggest': op, 'made': made, 'opened': dict(opened or {})}


# ── 조각 고치기(명령 안) ─────────────────────────────────────────
def _roster_ctx(ctx):
    return roster(ctx.store.db, ctx.read('players'))


def refresh_all(ctx):
    """donor_tags 통째로 다시. 실패해도 그 명령은 그대로 간다(조각만 안 바뀐다)."""
    try:
        infos = compute(ctx.store.db, _roster_ctx(ctx), ctx.read('donor_clubs'), now=ctx.now)
    except Exception as e:
        print('⚠️ [후원자 장부] 딱지 다시 계산 실패 — 그대로 둡니다: %s' % type(e).__name__, flush=True)
        return
    ctx.put('donor_tags', tags_slice(infos))


def refresh_names(ctx, names):
    """그 닉네임들의 카드만 다시(배정 · 되돌리기 · 새 카드). 그 카드의 모든 닉네임 줄을 새로 쓰고, 떠난 닉네임은 뺀다."""
    try:
        db = ctx.store.db
        pids = {pid_of(db, n) for n in names} - {None}
        if not pids:
            return
        infos = compute(db, _roster_ctx(ctx), ctx.read('donor_clubs'), now=ctx.now, pids=pids)
    except Exception as e:
        print('⚠️ [후원자 장부] 딱지 고치기 실패 — 그대로 둡니다: %s' % type(e).__name__, flush=True)
        return
    cur = ctx.read('donor_tags') or {}
    new = {nm: tag_entry(i) for i in infos.values() if not i['test'] for nm in i['names']}
    stale = [k for k, v in cur.items() if isinstance(v, dict) and v.get('pid') in pids and k not in new]
    if all(cur.get(k) == v for k, v in new.items()) and not stale:
        return                                   # 안 바뀌었으면 조각을 안 건드린다(쪽지가 안 나간다)
    t = ctx.edit('donor_tags')
    for k in stale:
        t.pop(k, None)
    t.update(new)


def _savepoint(db, name, fn):
    """fn 을 SAVEPOINT 안에서 — 넘어지면 그 부분만 되돌리고 False(배정 · 후원은 그대로 간다)."""
    try:
        db.execute('SAVEPOINT %s' % name)
    except Exception:
        return False
    try:
        fn()
        db.execute('RELEASE %s' % name)
        return True
    except Exception as e:
        print('⚠️ [후원자 장부] 기록 실패 — 후원 · 점수는 그대로: %s' % type(e).__name__, flush=True)
        try:
            db.execute('ROLLBACK TO %s' % name)
            db.execute('RELEASE %s' % name)
        except Exception:
            pass
        return False


# ── 고리 1: 새 후원 → 카드 · 번호표/계좌 제안 ──────────────────────
def _on_donation(ctx, name, amount):
    did = ctx.notes.get('id')
    d = ctx.store.donation(did) if did else None
    if not d or d.get('status') == 'display' or not dc.is_real_donation(d) or skip_name(d.get('name')):
        return
    db = ctx.store.db

    def work():
        ensure(db)
        pid, _new = ensure_card(db, d['name'], d['at'])
        tx = str(d.get('tx_id') or '')
        if tx:
            r = db.execute('SELECT donor_key FROM donor_keys WHERE tx_id = ?', (tx,)).fetchone()
            if r:
                others = set()
                for o in db.execute('SELECT d.name FROM donor_keys k JOIN donations d ON d.tx_id = k.tx_id '
                                    'WHERE k.donor_key = ? AND k.tx_id != ?', (r['donor_key'], tx)):
                    if not skip_name(o['name']):
                        others.add(norm_donor(o['name']))
                for nm in sorted(others):
                    op = pid_of(db, nm)
                    if op and op != pid:
                        open_suggest(db, pid, op, 'key', "같은 투네이션 번호표: '%s' · '%s'" % (norm_donor(d['name']), nm), ctx.now)
        if tx.startswith('manual_bank_') and _has(db, 'bank_inbox'):
            h = db.execute('SELECT holder FROM bank_inbox WHERE id = ?', (bl.card_of_tx(tx),)).fetchone()
            if h and h['holder']:
                prev = bl.lookup(db, h['holder'])          # 이 통장에서 전에 보낸 이름(이번 것은 명령이 끝난 뒤에 배운다)
                op = pid_of(db, prev) if prev and not skip_name(prev) else None
                if op and op != pid:
                    open_suggest(db, pid, op, 'bank', "같은 통장에서 보낸 이름: '%s' · '%s'" % (norm_donor(d['name']), norm_donor(prev)), ctx.now)

    if _savepoint(db, 'lm_donor_book_don', work):
        refresh_names(ctx, [d['name']])


dn.AFTER_DONATION.append(_on_donation)


# ── 고리 2: 배정 → 정답지 ──────────────────────────────────────
def _final(ctx, ref):
    out = []
    for r in ctx.store.score_rows(ref):
        if r['field'] == 'score' and int(r['delta']) > 0 and r['list'] in ('list', 'main', 'extra', 'jar') and r['player'] not in out:
            out.append(r['player'])
    return out


def _after_score(ctx):
    ref = str(ctx.notes.get('ref') or '')
    if not ref.startswith('don_'):
        return
    try:
        d = ctx.store.donation(ref)
        if not d or not dc.is_real_donation(d):
            return
        final = _final(ctx, ref)
        if not final:
            return
        it = next((x for x in ctx.read('pending') or [] if isinstance(x, dict) and x.get('id') == ref), None)
    except Exception:
        return
    a = (it or {}).get('auto') if isinstance((it or {}).get('auto'), dict) else {}
    by_auto = getattr(ctx, '_autopilot_assign', None) == ref
    guess, conf, ghow = None, None, None
    if a.get('target'):
        guess, conf = a['target'], a.get('confidence')
        ghow = GUESS_HOW.get(a.get('source'), a.get('source') or None)
    elif by_auto:
        guess, ghow = final[0], 'auto'                     # 기계가 바로 준 것 — 준 사람이 곧 추천
    changed = None if guess is None else (0 if guess in final else 1)
    db = ctx.store.db

    def work():
        ensure(db)
        if not pid_of(db, d['name']) and not skip_name(d['name']):
            ensure_card(db, d['name'], d['at'])           # 이 기능 전에 들어온 후원 — 지금 카드를 만든다
        db.execute('INSERT OR REPLACE INTO answer_log(ref, at, session, name, amount, source, guess, guess_conf, guess_how,'
                   ' final, how, changed, undone) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)',
                   (ref, ctx.now, d.get('session') or '', norm_donor(d['name']), int(d.get('amount') or 0), d.get('source') or '',
                    guess, conf, ghow, json.dumps(final, ensure_ascii=False), 'auto' if by_auto else 'human', changed))

    if _savepoint(db, 'lm_donor_book_ans', work):
        refresh_names(ctx, [d['name']])


def _on_assign(ctx, it, items, data):
    """조종실 🚗 오토파일럿(브라우저 쪽, via 'ap')이 준 것 — 사람 판단이 아니다."""
    if str((data or {}).get('via') or '') != 'ap' or not str((it or {}).get('id') or '').startswith('don_'):
        return
    try:
        ensure(ctx.store.db)
        ctx.store.db.execute("UPDATE answer_log SET how = 'auto' WHERE ref = ?", (it['id'],))
    except Exception:
        pass


def _after_cmd(ctx):
    """🤖 autopilot 의 AI 배정 — 준 뒤에야 notes.by 가 붙는다. 그 줄의 how 를 'ai' 로."""
    if ctx.notes.get('by') != 'autopilot-ai' or not ctx.notes.get('auto_assigned'):
        return
    ref = str(ctx.notes.get('ref') or '')
    if not ref.startswith('don_'):
        return
    try:
        ensure(ctx.store.db)
        ctx.store.db.execute("UPDATE answer_log SET how = 'ai', guess_how = 'ai' WHERE ref = ?", (ref,))
    except Exception:
        pass


def _on_undo(ctx, ref):
    ref = str(ref or '')
    if not ref.startswith('don_'):
        return
    db = ctx.store.db
    d = None

    def work():
        nonlocal d
        ensure(db)
        db.execute('UPDATE answer_log SET undone = 1 WHERE ref = ?', (ref,))
        d = ctx.store.donation(ref)

    if _savepoint(db, 'lm_donor_book_undo', work) and d:
        refresh_names(ctx, [d['name']])


pl.AFTER_SCORE.append(_after_score)
pl.ON_UNDO.append(_on_undo)
dn.ON_ASSIGN.append(_on_assign)
busmod.AFTER.append(_after_cmd)


# ── 방송 시작 · 끝 — 딱지 통째로 다시 ────────────────────────────
def _on_session(ctx, data):
    refresh_all(ctx)


ses.ON_START.append(_on_session)
ses.ON_END.append(_on_session)


# ── 명령 ────────────────────────────────────────────────────
def _need_person(db, pid):
    p = person(db, pid)
    if not p:
        raise CommandError('없는 카드입니다', 404)
    return p


@command('donor.merge')
def donor_merge(ctx, data):
    """b 카드를 a 로 묶는다(제안 [묶기] · 손으로 묶기 모두). 풀기는 donor.split {name}."""
    a, b = str(data.get('a') or ''), str(data.get('b') or '')
    db = ctx.store.db
    ensure(db)
    _need_person(db, a)
    _need_person(db, b)
    if a == b:
        raise CommandError('같은 카드입니다', 409)
    merge(db, a, b, ctx.now)
    ctx.notes['pid'] = a
    refresh_all(ctx)


@command('donor.split')
def donor_split(ctx, data):
    db = ctx.store.db
    ensure(db)
    try:
        new = split(db, data.get('name'), ctx.now)
    except LookupError:
        raise CommandError('없는 닉네임입니다', 404)
    except ValueError:
        raise CommandError('이미 혼자인 카드예요 — 뗄 닉네임이 없어요', 409)
    ctx.notes['pid'] = new
    refresh_all(ctx)


@command('donor.suggest_reject')
def donor_suggest_reject(ctx, data):
    db = ctx.store.db
    ensure(db)
    try:
        sid = int(data.get('id'))
    except (TypeError, ValueError):
        raise CommandError('어느 제안인지(id) 필요합니다')
    r = db.execute('SELECT status FROM donor_suggest WHERE id = ?', (sid,)).fetchone()
    if not r:
        raise CommandError('없는 제안입니다', 404)
    if r['status'] != 'open':
        raise CommandError('이미 처리한 제안입니다', 409)
    db.execute("UPDATE donor_suggest SET status = 'rejected', at = ? WHERE id = ?", (ctx.now, sid))


@command('donor.pin')
def donor_pin(ctx, data):
    """📌 고정 — PIN_ON 이 꺼져 있으면(대표님 답 대기) 이유를 말하고 막는다."""
    if not PIN_ON:
        raise CommandError('📌 고정은 아직 꺼져 있어요 — 대표님 결정을 기다리는 중이에요', 409)
    db = ctx.store.db
    ensure(db)
    _need_person(db, data.get('pid'))
    player = ' '.join(str(data.get('player') or '').split())[:pl.NAME_MAX] or None
    db.execute('UPDATE donor_person SET pin = ?, updated = ? WHERE pid = ?', (player, ctx.now, data.get('pid')))
    refresh_all(ctx)


@command('donor.mark_test')
def donor_mark_test(ctx, data):
    db = ctx.store.db
    ensure(db)
    _need_person(db, data.get('pid'))
    db.execute('UPDATE donor_person SET test = ?, updated = ? WHERE pid = ?', (1 if data.get('test') else 0, ctx.now, data.get('pid')))
    refresh_all(ctx)


@command('donor.note')
def donor_note(ctx, data):
    db = ctx.store.db
    ensure(db)
    _need_person(db, data.get('pid'))
    db.execute('UPDATE donor_person SET note = ?, updated = ? WHERE pid = ?',
               (str(data.get('note') or '').strip()[:NOTE_MAX], ctx.now, data.get('pid')))


@command('donor.club_set')
def donor_club_set(ctx, data):
    """팬클럽 말 하나 — {word, player|null, confirmed}. 확정(confirmed)한 것만 딱지(club)에 쓴다.
       player 없이 confirmed 면 '팬클럽 말이 아님' 으로 적어 둔다(다시 채우기가 후보로 또 안 올린다)."""
    word = ''.join(str(data.get('word') or '').split())[:WORD_MAX]
    if len(word) < 2:
        raise CommandError('팬클럽 말을 두 글자 이상 적어 주세요')
    player = ' '.join(str(data.get('player') or '').split())[:pl.NAME_MAX] or None
    c = ctx.edit('donor_clubs')
    old = c.get(word) if isinstance(c.get(word), dict) else {}
    c[word] = dict({k: v for k, v in old.items() if k in ('n', 'share', 'names', 'players')},
                   player=player, confirmed=bool(data.get('confirmed')))
    refresh_all(ctx)


@command('donor.rebuild')
def donor_rebuild(ctx, data):
    """처음 채우기 · 다시 채우기 — 장부 · 기억 · 번호표 · 계좌 짝에서 카드 · 제안을 만들고 딱지를 통째로 다시."""
    got = build(ctx.store.db, now=ctx.now, players=ctx.read('players'), clubs=ctx.read('donor_clubs'))
    ctx.put('donor_tags', got['tags'])
    ctx.put('donor_clubs', got['clubs'])
    ctx.notes['stats'] = got['stats']


# ── 길(로그인) ────────────────────────────────────────────────
def _need(req, authed):
    if not authed(req):
        return JSONResponse({'status': 'error', 'message': '로그인이 필요합니다'}, status_code=401)
    return None


def _infos(bus, pids=None):
    db = bus.store.db
    ensure(db)
    s = bus.state.slices
    return compute(db, roster(db, s.get('players')), s.get('donor_clubs'), pids=pids)


@route('/api/donors/book', methods=('GET',))
async def donors_book(req, bus, authed, answer):
    """카드 목록 — 시험 카드는 ?all=1 일 때만."""
    bad = _need(req, authed)
    if bad:
        return bad
    infos = _infos(bus)
    want_all = (req.query_params.get('all') or '') in ('1', 'true')
    persons = []
    for x in infos.values():
        if x['test'] and not want_all:
            continue
        persons.append({k: x[k] for k in ('pid', 'label', 'tag', 'player', 'share', 'n', 'club', 'total_won', 'last_at',
                                          'dormant', 'big', 'names', 'pin', 'test', 'suspect', 'sugg')})
    persons.sort(key=lambda p: (-(p['last_at'] or 0), p['label']))
    counts = {t: 0 for t in TAGS}
    for x in infos.values():
        if not x['test']:
            counts[x['tag']] += 1
    op = int(bus.store.db.execute("SELECT COUNT(*) FROM donor_suggest WHERE status = 'open'").fetchone()[0])
    return {'status': 'success', 'persons': persons, 'counts': counts, 'open_suggest': op, 'pin_on': bool(PIN_ON)}


def _suggest_rows(db, pid=None):
    q = ("SELECT s.*, pa.label AS a_label, pb.label AS b_label FROM donor_suggest s "
         "LEFT JOIN donor_person pa ON pa.pid = s.a LEFT JOIN donor_person pb ON pb.pid = s.b WHERE s.status = 'open'")
    a = ()
    if pid:
        q += ' AND (s.a = ? OR s.b = ?)'
        a = (pid, pid)
    return [dict(r) for r in db.execute(q + ' ORDER BY s.at DESC, s.id DESC', a)]


@route('/api/donors/person/{pid}', methods=('GET',))
async def donors_person(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    pid = str(req.path_params.get('pid') or '')
    db = bus.store.db
    ensure(db)
    p = person(db, pid)
    if not p:
        return JSONResponse({'status': 'error', 'message': '없는 카드입니다'}, status_code=404)
    info = _infos(bus, pids=[pid]).get(pid) or {}
    names = [{'name': a['name'], 'first_at': a['first_at'], 'last_at': a['last_at'], 'n': a['n']} for a in names_of(db, pid)]
    mine = {a['name'] for a in names}
    from . import mask as mk
    m = bus.state.slices.get('mask')
    hidden = set((m or {}).get('hidden') or [])
    recent = []
    for r in db.execute("SELECT * FROM donations WHERE status != 'display' ORDER BY at DESC"):
        if norm_donor(r['name']) not in mine or not dc.is_real_donation(dict(r)):
            continue
        al = db.execute('SELECT final, undone FROM answer_log WHERE ref = ?', (r['id'],)).fetchone()
        if al and not al['undone']:
            who = json.loads(al['final'] or '[]')
        else:
            who = [x for x in str(r['player'] or '').split(' · ') if x]
        msg = '' if r['id'] in hidden else mk.masked(r['message'] or '', m)
        recent.append({'at': r['at'], 'amount': r['amount'], 'players': who, 'message': msg, 'ref': r['id']})
        if len(recent) >= RECENT_MAX:
            break
    sug = []
    for s in _suggest_rows(db, pid):
        other = s['b'] if s['a'] == pid else s['a']
        sug.append({'id': s['id'], 'other_pid': other, 'other_label': s['b_label'] if s['a'] == pid else s['a_label'],
                    'why': s['why'], 'detail': s['detail']})
    return {'status': 'success', 'pid': pid, 'label': p['label'], 'pin': p['pin'], 'test': int(p['test'] or 0), 'note': p['note'],
            'tag': info.get('tag'), 'player': info.get('player'), 'share': info.get('share'), 'n': info.get('n'),
            'club': info.get('club'), 'suspect': info.get('suspect') or '', 'total_won': info.get('total_won'),
            'players': info.get('players') or {}, 'names': names, 'recent': recent, 'suggest': sug, 'pin_on': bool(PIN_ON)}


@route('/api/donors/suggest', methods=('GET',))
async def donors_suggest(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    db = bus.store.db
    ensure(db)
    rows = [{'id': s['id'], 'a': s['a'], 'a_label': s['a_label'], 'b': s['b'], 'b_label': s['b_label'], 'why': s['why'],
             'detail': s['detail'], 'at': s['at']} for s in _suggest_rows(db)]
    return {'status': 'success', 'rows': rows, 'count': len(rows)}
