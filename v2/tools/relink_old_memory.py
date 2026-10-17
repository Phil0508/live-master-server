# -*- coding: utf-8 -*-
"""🔗 옛 기억 잇기 — 옛 프로그램의 '누구에게 갔나' 기억(donor_memory)을 옮겨 온 장부(donations, archived)의 후원 한 건과 잇는다.

왜
  옛 장부에서 옮긴 후원은 player 가 비어 있다(누구에게 갔는지 모른다). 그런데 옛 기억(donor_memory, ref 'old:N')에는
  후원자 · 받은 선수 · 점수 · 메시지 · 시각이 있다. 둘을 이어 정답지(answer_log, how='relink')를 만들면
  지난 방송도 '이 후원 → 이 선수' 로 세고 배울 수 있다.

어떻게 잇나 — **하나만 딱 맞을 때만** 잇는다(애매하면 버리고 센다)
  같은 사람   norm_donor(장부 이름) == 기억의 donor
  시각       기억 시각 − 장부 시각 이 LAG_MIN ~ LAG_MAX 초(배정은 후원이 들어온 뒤에 한다)
             ↳ 10-17 운영 장부 사본으로 잰 값: 하나만 맞는 656쌍의 차이가 0~383초(중간 9초 · 99% 241초 · 음수 0건)
               → 넉넉히 10분(600초). 더 넓히면 같은 사람의 다른 후원과 헷갈린다.
  메시지     기억 메시지 == 장부 메시지 앞 300자(기억은 300자에서 자른다) — 잰 값: 기억 1,113줄 모두 같은 글이 있었다.
  금액       만 원 반올림 (원+4000)//10000 == 기억 점수.
             나눠 준 한 건(기억 여러 줄 · 같은 사람 · 같은 메시지 · SPLIT_SEC 안)은 점수 합이 맞으면 한 건으로 본다.
             ↳ 잰 값: 옛 나눠 줌은 같은 초(차이 0초)에 적혔다 → 2초.
  짝 찾기     ① 후원 하나에만 맞고 그 후원도 이 기억 하나에만 맞으면 잇는다. 이은 후원은 빼고 다시(풀릴 때까지).
             ② 남은 것 중 '똑같은 후원 여러 건 ↔ 똑같은 기억 여러 줄'(같은 선수 · 같은 점수 · 같은 수)은 시각 순으로 잇는다 —
                어느 짝으로 이어도 정답지 내용이 같다(예: 같은 시그를 세 번 연달아 · 셋 다 밍밍).
             ③ 그래도 둘 이상이 맞으면 '애매해서 버림'.
  빼는 것     진짜 후원이 아닌 장부 줄(donor_clean.is_real_donation — 손 점수 · 투네이션 테스트 · 0원) · 시험 이름 후원자(test_name_reason).
  v2 기억     ref 가 이미 장부 id('don_…')인 줄은 찾을 것 없이 바로 잇는다('바로 이어짐').

쓰는 곳
  answer_log(정답지 — 후원 한 건 = 한 줄)에 how='relink' 로. 여러 번 돌려도 같다(멱등).
  이미 사람/기계가 적은 줄(how 가 relink 가 아닌 것)은 건드리지 않는다. donor_memory · donations 는 읽기만 한다.

쓰는 법(기본은 보기만 — 몇 건 잇는지 · 못 잇는 이유별 수)
  python -m v2.tools.relink_old_memory --db v2/data/lm2.db
  python -m v2.tools.relink_old_memory --db v2/data/lm2.db --json
  python -m v2.tools.relink_old_memory --db v2/data/lm2.db --write      # 정답지에 쓴다
  ⚠️ 결과에 후원자 이름 · 메시지는 찍지 않는다(숫자만).
"""
import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict

from v2.server.domain.donor_clean import is_real_donation, test_name_reason
from v2.server.domain.rules import man_won, norm_donor

LAG_MIN = -2       # 초 — 기억 시각이 장부보다 앞설 수 있는 한도(잰 값은 0, 시계 오차만 둔다)
LAG_MAX = 600      # 초 — 잰 값 최대 383초 → 10분
SPLIT_SEC = 2      # 초 — 나눠 준 한 건의 기억 줄들이 적힌 간격(잰 값 0초)
MSG_CUT = 300      # 기억은 메시지를 300자에서 자른다(donor_memory.remember_assignment)

# 정답지 — 공통 설계서의 CREATE 문 그대로(합칠 때 donor_book.SCHEMA 하나로 모은다). executescript 금지 — 한 줄씩.
ANSWER_LOG_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS answer_log ("
    " ref TEXT PRIMARY KEY, at REAL NOT NULL, session TEXT NOT NULL DEFAULT '', name TEXT NOT NULL,"
    " amount INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT '', guess TEXT, guess_conf REAL, guess_how TEXT,"
    " final TEXT NOT NULL DEFAULT '[]', how TEXT NOT NULL DEFAULT '', changed INTEGER, undone INTEGER NOT NULL DEFAULT 0)",
    "CREATE INDEX IF NOT EXISTS answer_log_name ON answer_log(name)",
)

# 못 이은 이유(보고서 순서)
REASONS = (
    ('test_name', '시험 이름 후원자'),
    ('no_name', '같은 이름 후원이 장부에 없음'),
    ('no_time', '시각이 맞는 후원 없음'),
    ('no_message', '메시지가 맞는 후원 없음'),
    ('no_amount', '금액이 맞는 후원 없음'),
    ('not_real', '맞는 것이 손 점수 · 테스트 · 0원뿐'),
    ('taken', '맞는 후원을 다른 기억이 먼저 가짐'),
    ('ambiguous', '애매해서 버림(둘 이상 맞음)'),
)


# ── 읽기 ───────────────────────────────────────────────
def open_db(path, write=False):
    if write:
        conn = sqlite3.connect(path)
    else:
        conn = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
        conn.execute('PRAGMA query_only = 1')
    conn.row_factory = sqlite3.Row
    return conn


def load(conn):
    """(기억 줄들, 장부 줄들) — dict 목록. 기억은 시각 · id 순."""
    mem = [dict(r) for r in conn.execute(
        'SELECT id, at, donor, player, amount, message, ref FROM donor_memory ORDER BY at, id').fetchall()]
    dons = [dict(r) for r in conn.execute('SELECT * FROM donations').fetchall()]
    return mem, dons


def _msg(s):
    return str(s or '')[:MSG_CUT].strip()


# ── 짝 찾기 ────────────────────────────────────────────
def _units(mem_old, by_name):
    """기억 줄들을 '후원 한 건' 단위로 묶고, 각 단위에 맞는 장부 후원(후보)을 붙인다.
       돌려받는 값: [{mem: [줄…], at, donor, players, points, cands: [장부 id…], why}]"""
    def cands(donor, msg, at, points):
        out, stage = [], 'no_name'
        rows = by_name.get(donor) or []
        if rows:
            stage = 'no_time'
        rows = [d for d in rows if LAG_MIN <= at - d['at'] <= LAG_MAX]
        if rows:
            stage = 'no_message'
        rows = [d for d in rows if _msg(d.get('message')) == msg]
        if rows:
            stage = 'no_amount'
        rows = [d for d in rows if man_won(d.get('amount')) == points]
        if rows:
            stage = 'not_real'
        out = [d['id'] for d in rows if is_real_donation(d)]
        return out, ('' if out else stage)

    units, used = [], set()
    for i, m in enumerate(mem_old):
        if m['id'] in used:
            continue
        msg = _msg(m['message'])
        c1, why1 = cands(m['donor'], msg, m['at'], int(m['amount'] or 0))
        if not c1:
            # 나눠 준 한 건인가 — 같은 사람 · 같은 메시지 · SPLIT_SEC 안의 줄들(아직 안 쓴 것)의 점수 합으로 다시 본다
            grp = [m]
            for n in mem_old[i + 1:]:
                if n['at'] - m['at'] > SPLIT_SEC:
                    break
                if n['id'] not in used and n['donor'] == m['donor'] and _msg(n['message']) == msg:
                    grp.append(n)
            if len(grp) > 1:
                cs, _ = cands(m['donor'], msg, m['at'], sum(int(g['amount'] or 0) for g in grp))
                if cs:
                    used.update(g['id'] for g in grp)
                    units.append({'mem': grp, 'at': m['at'], 'donor': m['donor'],
                                  'players': [g['player'] for g in grp],
                                  'points': [int(g['amount'] or 0) for g in grp], 'cands': cs, 'why': ''})
                    continue
        used.add(m['id'])
        units.append({'mem': [m], 'at': m['at'], 'donor': m['donor'], 'players': [m['player']],
                      'points': [int(m['amount'] or 0)], 'cands': c1, 'why': why1})
    return units


def match(units, don_by_id):
    """단위 ↔ 장부 후원 짝. 돌려받는 값: ({단위 번호: 장부 id}, {단위 번호: 이유}, {똑같은 묶음으로 이은 단위 번호})"""
    linked, reason = {}, {}
    for k, u in enumerate(units):
        if not u['cands']:
            reason[k] = u['why'] or 'no_name'
    open_units = {k for k, u in enumerate(units) if u['cands']}
    claimed = set()

    def live(k):
        return [d for d in units[k]['cands'] if d not in claimed]

    # ① 서로 하나뿐인 짝 — 이은 후원을 빼고 다시(풀릴 때까지)
    changed = True
    while changed:
        changed = False
        by_don = defaultdict(list)
        for k in open_units:
            for d in live(k):
                by_don[d].append(k)
        for k in sorted(open_units, key=lambda x: units[x]['at']):
            c = live(k)
            if len(c) == 1 and len(by_don[c[0]]) == 1:
                linked[k] = c[0]
                claimed.add(c[0])
                open_units.discard(k)
                changed = True
        for k in list(open_units):
            if not live(k):
                reason[k] = 'taken'
                open_units.discard(k)

    # ② 똑같은 후원 여러 건 ↔ 똑같은 기억 여러 줄 — 어느 짝이든 정답지가 같으면 시각 순으로 잇는다
    same = set()
    seen = set()
    for k0 in sorted(open_units, key=lambda x: units[x]['at']):
        if k0 in seen:
            continue
        comp_u, comp_d, stack = {k0}, set(), [k0]       # 이어진 덩어리(단위 · 후원)
        while stack:
            k = stack.pop()
            for d in live(k):
                if d in comp_d:
                    continue
                comp_d.add(d)
                for k2 in open_units:
                    if k2 not in comp_u and d in live(k2):
                        comp_u.add(k2)
                        stack.append(k2)
        seen |= comp_u
        keys_u = {(tuple(units[k]['players']), tuple(units[k]['points'])) for k in comp_u}
        keys_d = {(_msg(don_by_id[d].get('message')), man_won(don_by_id[d].get('amount'))) for d in comp_d}
        us = sorted(comp_u, key=lambda x: (units[x]['at'], units[x]['mem'][0]['id']))
        ds = sorted(comp_d, key=lambda d: (don_by_id[d]['at'], d))
        ok = (len(keys_u) == 1 and len(keys_d) == 1 and len(us) == len(ds)
              and all(d in live(k) for k, d in zip(us, ds)))
        for k, d in (zip(us, ds) if ok else ()):
            linked[k] = d
            claimed.add(d)
            open_units.discard(k)
            same.add(k)
        if not ok:
            for k in comp_u:
                reason[k] = 'ambiguous'
                open_units.discard(k)
    return linked, reason, same


def plan(mem, dons):
    """무엇을 잇는지 정한다(쓰지 않는다). 돌려받는 값: {links: [정답지 줄…], counts: {...}, reasons: {이유: 기억 줄 수}}"""
    don_by_id = {d['id']: d for d in dons}
    by_name = defaultdict(list)
    for d in dons:
        if d.get('status') == 'archived':
            by_name[norm_donor(d.get('name'))].append(d)

    direct, mem_old = defaultdict(list), []
    reasons = Counter()
    for m in mem:
        if test_name_reason(m['donor']):
            reasons['test_name'] += 1
            continue
        if m['ref'] in don_by_id:                       # v2 기억 — ref 가 장부 id
            direct[m['ref']].append(m)
        else:
            mem_old.append(m)

    links = []

    def add(d, rows, kind):
        links.append({'ref': d['id'], 'at': float(d['at']), 'session': str(d.get('session') or ''),
                      'name': norm_donor(d.get('name')), 'amount': int(d.get('amount') or 0),
                      'source': str(d.get('source') or ''),
                      'final': [r['player'] for r in rows], 'kind': kind, 'mem_ids': [r['id'] for r in rows]})

    n_direct = 0
    for ref, rows in direct.items():
        d = don_by_id[ref]
        if not is_real_donation(d):
            reasons['not_real'] += len(rows)
            continue
        add(d, rows, 'direct')
        n_direct += 1

    units = _units(mem_old, by_name)
    linked, why, same = match(units, don_by_id)
    for k, u in enumerate(units):
        if k in linked:
            add(don_by_id[linked[k]], u['mem'], 'same' if k in same else 'unique')
        else:
            reasons[why.get(k, 'ambiguous')] += len(u['mem'])
    links.sort(key=lambda r: (r['at'], r['ref']))
    n_mem_linked = sum(len(r['mem_ids']) for r in links)
    counts = {
        'memory': len(mem), 'memory_old': len(mem_old), 'memory_linked': n_mem_linked,
        'links': len(links), 'direct': n_direct, 'same_cluster': len(same),
        'split': sum(1 for r in links if len(r['mem_ids']) > 1 and r['kind'] != 'direct'),
        'archived_real': sum(1 for d in dons if d.get('status') == 'archived' and is_real_donation(d)),
    }
    return {'links': links, 'counts': counts, 'reasons': dict(reasons)}


# ── 쓰기 ───────────────────────────────────────────────
def ensure(conn):
    for q in ANSWER_LOG_SCHEMA:
        conn.execute(q)


def write(conn, links):
    """정답지에 쓴다. 이미 있는 relink 줄은 새 값으로 덮고(멱등), 사람 · 기계가 적은 줄은 그대로 둔다.
       돌려받는 값: {'written': n, 'kept': n}"""
    ensure(conn)
    written = kept = 0
    with conn:
        for r in links:
            row = conn.execute('SELECT how FROM answer_log WHERE ref = ?', (r['ref'],)).fetchone()
            if row is not None and row[0] != 'relink':
                kept += 1
                continue
            conn.execute(
                'INSERT INTO answer_log(ref, at, session, name, amount, source, guess, guess_conf, guess_how, final, how,'
                ' changed, undone) VALUES(?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, \'relink\', NULL, 0) '
                'ON CONFLICT(ref) DO UPDATE SET at = excluded.at, session = excluded.session, name = excluded.name,'
                ' amount = excluded.amount, source = excluded.source, final = excluded.final',
                (r['ref'], r['at'], r['session'], r['name'], r['amount'], r['source'],
                 json.dumps(r['final'], ensure_ascii=False)))
            written += 1
    return {'written': written, 'kept': kept}


# ── 보고 ───────────────────────────────────────────────
def lag_histogram(links, mem):
    """이은 짝의 시각 차(기억 − 장부) 분포 — 문턱이 맞는지 다시 볼 때."""
    at_of = {m['id']: m['at'] for m in mem}
    bins = [(0, 5), (5, 10), (10, 30), (30, 60), (60, 120), (120, 300), (300, 600)]
    out = Counter()
    for r in links:
        if r['kind'] == 'direct':
            continue
        lag = at_of[r['mem_ids'][0]] - r['at']
        for lo, hi in bins:
            if lo <= lag < hi or (lag < 0 and lo == 0):
                out['%d~%d초' % (lo, hi)] += 1
                break
        else:
            out['600초~'] += 1
    return [(k, out[k]) for k in ['%d~%d초' % b for b in bins] + ['600초~'] if out[k]]


def report(res, mem=None):
    c, rs = res['counts'], res['reasons']
    pct = (100.0 * c['memory_linked'] / c['memory']) if c['memory'] else 0.0
    lines = [
        '🔗 옛 기억 잇기 — 기억 %d줄 중 %d줄(%.1f%%)을 장부 후원 %d건에 이음' % (c['memory'], c['memory_linked'], pct, c['links']),
        '  · 바로 이어짐(v2 기억, ref=장부 id) %d건 · 나눠 준 한 건 %d건 · 똑같은 묶음 시각 순 %d건'
        % (c['direct'], c['split'], c['same_cluster']),
        '  · 장부의 옛 진짜 후원 %d건 중 %d건이 선수를 알게 됨'
        % (c['archived_real'], sum(1 for r in res['links'] if r['kind'] != 'direct')),
        '못 이은 기억 줄(이유별):',
    ]
    for key, label in REASONS:
        if rs.get(key):
            lines.append('  - %s: %d' % (label, rs[key]))
    if mem is not None:
        lines.append('이은 짝의 시각 차(기억 − 장부): ' + ' · '.join('%s %d' % kv for kv in lag_histogram(res['links'], mem)))
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description='옛 기억(donor_memory) ↔ 장부(donations) 잇기 → answer_log')
    ap.add_argument('--db', required=True)
    ap.add_argument('--write', action='store_true', help='정답지(answer_log)에 쓴다(없으면 보기만)')
    ap.add_argument('--json', action='store_true', help='숫자만 JSON 으로')
    a = ap.parse_args(argv)
    conn = open_db(a.db, write=a.write)
    try:
        mem, dons = load(conn)
        res = plan(mem, dons)
        out = {'counts': res['counts'], 'reasons': res['reasons']}
        if a.write:
            out['write'] = write(conn, res['links'])
    finally:
        conn.close()
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print(report(res, mem))
        if a.write:
            print('정답지에 씀: %(written)d줄 · 사람/기계가 적은 줄이라 그대로 둠: %(kept)d줄' % out['write'])
        else:
            print('(보기만 — 쓰려면 --write)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
