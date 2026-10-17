# -*- coding: utf-8 -*-
"""🧪 시험 이름 후보 목록 — 장부에서 시험용 같은 후원자 · 선수 이름과 건수를 보여 준다(**지우지 않는다** · 읽기만).

무엇을 보나
  후원자   장부(donations.name)와 기억(donor_memory.donor)의 이름 중 donor_clean.test_name_reason 에 걸리는 것
           (숫자만 · Player N · 테스트/test). 장부 건수(진짜 후원 / 전체) · 기억 건수 · 장부 금액 합(진짜 후원만).
  선수     기억(donor_memory.player)과 장부(donations.player)의 선수 칸 중 donor_clean.test_player_reason 에 걸리는 것
           — 글자로 걸리거나 지금 선수 명단(players 조각)에 없는 이름.
           ⚠️ 방송이 끝나면 명단이 비어 있다 → 그때는 명단으로 판단하지 않고, 선수 칸 전체를 건수 적은 순으로 보여 준다
              (고수달 · 한명 같은 시험 이름은 건수가 적어 맨 위에 모인다). --roster 밍밍,앙앙,… 으로 명단을 직접 줄 수 있다.
  조종실에서 뺀 이름  donor_rules 조각의 excluded(대표님이 순위에서 뺀 이름 — 엔젤컴퍼니 · 수동송출 …)도 건수와 함께 따로 보여 준다.
  대표님이 보고 '시험' 이라고 정하면 후원자 장부(donor_person.test)에서 표시한다 — 이 도구는 아무것도 안 바꾼다.

쓰는 법
  python -m v2.tools.report_test_names --db v2/data/lm2.db
  python -m v2.tools.report_test_names --db v2/data/lm2.db --json
  python -m v2.tools.report_test_names --db v2/data/lm2.db --roster 밍밍,앙앙,예지랑
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from urllib.request import pathname2url

from v2.server.domain.donor_clean import is_real_donation, test_name_reason, test_player_reason
from v2.server.domain.rules import norm_donor


def open_ro(path):
    if not os.path.isfile(path):
        raise SystemExit('장부 파일이 없습니다: %s' % path)
    conn = sqlite3.connect('file:%s?mode=ro' % pathname2url(os.path.abspath(path)), uri=True)
    conn.execute('PRAGMA query_only = 1')
    conn.row_factory = sqlite3.Row
    return conn


def _has(conn, table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def roster_of(conn):
    """지금 선수 명단 — players 조각의 list + extra 이름. 없거나 비었으면 []."""
    if not _has(conn, 'slices'):
        return []
    row = conn.execute("SELECT value FROM slices WHERE name = 'players'").fetchone()
    if not row:
        return []
    try:
        p = json.loads(row[0])
    except ValueError:
        return []
    if not isinstance(p, dict):
        return []
    out = []
    for key in ('list', 'extra'):
        for r in p.get(key) or []:
            n = str((r.get('name') if isinstance(r, dict) else r) or '').strip()
            if n and n not in out:
                out.append(n)
    return out


def excluded_of(conn):
    """조종실에서 순위 · 합계에서 뺀 이름(donor_rules.excluded). 없으면 []."""
    if not _has(conn, 'slices'):
        return []
    row = conn.execute("SELECT value FROM slices WHERE name = 'donor_rules'").fetchone()
    try:
        return [norm_donor(x) for x in (json.loads(row[0]).get('excluded') or [])] if row else []
    except (ValueError, AttributeError):
        return []


def collect(conn, roster=None):
    """돌려받는 값: {donors: [...], players: [...], roster: [...], roster_used: bool, all_players: [...]}"""
    roster = list(roster) if roster else roster_of(conn)
    dons = [dict(r) for r in conn.execute('SELECT * FROM donations').fetchall()] if _has(conn, 'donations') else []
    mem = ([dict(r) for r in conn.execute('SELECT donor, player FROM donor_memory').fetchall()]
           if _has(conn, 'donor_memory') else [])

    donors = defaultdict(lambda: {'ledger': 0, 'ledger_real': 0, 'won': 0, 'memory': 0})
    for d in dons:
        n = norm_donor(d.get('name'))
        if not test_name_reason(n):
            continue
        r = donors[n]
        r['ledger'] += 1
        if is_real_donation(d):
            r['ledger_real'] += 1
            r['won'] += int(d.get('amount') or 0)
    for m in mem:
        n = norm_donor(m.get('donor'))
        if test_name_reason(n):
            donors[n]['memory'] += 1
    donor_list = [dict(name=n, why=test_name_reason(n), **v) for n, v in donors.items()]
    donor_list.sort(key=lambda r: (-(r['ledger'] + r['memory']), r['name']))

    counts = defaultdict(lambda: {'memory': 0, 'ledger': 0})
    for m in mem:
        p = str(m.get('player') or '').strip()
        if p:
            counts[p]['memory'] += 1
    for d in dons:
        p = str(d.get('player') or '').strip()
        if p:
            counts[p]['ledger'] += 1
    players = []
    for p, v in counts.items():
        why = test_player_reason(p, roster)
        if why:
            players.append(dict(name=p, why=why, **v))
    players.sort(key=lambda r: (r['memory'] + r['ledger'], r['name']))
    all_players = sorted((dict(name=p, **v) for p, v in counts.items()),
                         key=lambda r: (r['memory'] + r['ledger'], r['name']))
    ex = []
    for n in excluded_of(conn):
        rows = [d for d in dons if norm_donor(d.get('name')) == n]
        ex.append({'name': n, 'why': test_name_reason(n), 'ledger': len(rows),
                   'won': sum(int(d.get('amount') or 0) for d in rows if is_real_donation(d))})
    return {'donors': donor_list, 'players': players, 'excluded': ex, 'roster': roster, 'roster_used': bool(roster),
            'all_players': all_players}


def report(res):
    lines = ['🧪 시험 이름 후보 — 지우지 않음 · 대표님 확인용', '',
             '후원자 %d명 (이름 · 이유 · 장부 진짜/전체 · 장부 금액 · 기억 건수):' % len(res['donors'])]
    for r in res['donors']:
        lines.append('  - %s · %s · 장부 %d/%d건 · %s원 · 기억 %d건'
                     % (r['name'], r['why'], r['ledger_real'], r['ledger'], format(r['won'], ','), r['memory']))
    if res.get('excluded'):
        lines.append('')
        lines.append('조종실에서 뺀 이름(donor_rules) %d개:' % len(res['excluded']))
        for r in res['excluded']:
            lines.append('  - %s%s · 장부 %d건 · %s원' % (r['name'], (' · ' + r['why']) if r['why'] else '',
                                                    r['ledger'], format(r['won'], ',')))
    lines.append('')
    if res['roster_used']:
        lines.append('선수 칸 %d명 (지금 명단: %s):' % (len(res['players']), ' · '.join(res['roster'])))
        for r in res['players']:
            lines.append('  - %s · %s · 기억 %d건 · 장부 %d건' % (r['name'], r['why'], r['memory'], r['ledger']))
    else:
        lines.append('선수 칸 — 지금 명단이 비어 있어(방송 끝) 명단으로는 판단 못 함. 글자로 걸린 것 %d명:' % len(res['players']))
        for r in res['players']:
            lines.append('  - %s · %s · 기억 %d건 · 장부 %d건' % (r['name'], r['why'], r['memory'], r['ledger']))
        lines.append('선수 칸 전체(건수 적은 순 — 위쪽이 시험 이름일 수 있음, --roster 로 명단을 주면 가려 준다):')
        for r in res['all_players']:
            lines.append('  - %s · 기억 %d건 · 장부 %d건' % (r['name'], r['memory'], r['ledger']))
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description='시험 이름 후보 목록(읽기만)')
    ap.add_argument('--db', required=True)
    ap.add_argument('--roster', default='', help='선수 명단(쉼표로) — 없으면 players 조각')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    roster = [x.strip() for x in a.roster.split(',') if x.strip()]
    conn = open_ro(a.db)
    try:
        res = collect(conn, roster or None)
    finally:
        conn.close()
    print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else report(res))
    return 0


if __name__ == '__main__':
    sys.exit(main())
