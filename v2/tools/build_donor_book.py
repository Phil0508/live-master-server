# -*- coding: utf-8 -*-
"""📒 후원자 장부 처음 채우기 — 장부(진짜 후원만) · donor_memory · donor_keys · bank_learn 에서 카드 · 닉네임 · 제안을 만든다.

쓰는 법
  python -m v2.tools.build_donor_book --db v2/data/lm2.db            # 보기만(기본) — 장부 파일을 안 바꾼다(메모리 사본에서 돌린다)
  python -m v2.tools.build_donor_book --db v2/data/lm2.db --write    # 정말 쓴다(카드 · 닉네임 · 제안 표 + donor_tags · donor_clubs 조각)
  --json      숫자만 JSON 으로
여러 번 돌려도 같은 결과다(멱등) — 이미 있는 카드는 그대로, 묶은 것 · 거절한 제안 · 푼 짝은 다시 안 만든다.
⚠️ 켜진 서버 옆에서 --write 를 돌리면 조각(donor_tags · donor_clubs)은 서버가 다음에 다시 계산할 때까지 서버 메모리 것이 이긴다
   — 서버가 켜져 있으면 조종실에서 명령 donor.rebuild 를 누르는 쪽이 낫다(같은 계산).
⚠️ 결과에 금액 · 메시지는 찍지 않는다. 팬클럽 추정 후보는 말 · 선수 · 근거 숫자만.
"""
import argparse
import json
import sqlite3
import sys
import time

from v2.server.domain import donor_book as db_


def _slices(conn):
    try:
        return {r['name']: json.loads(r['value']) for r in conn.execute('SELECT name, value FROM slices')}
    except sqlite3.Error:
        return {}


def run(path, write=False, now=None):
    """돌려받는 값: build 의 stats + clubs(팬클럽 사전 · 후보)."""
    src = sqlite3.connect(path, isolation_level=None)
    src.row_factory = sqlite3.Row
    try:
        if write:
            conn = src
        else:
            conn = sqlite3.connect(':memory:', isolation_level=None)     # 보기만 — 메모리 사본에서
            src.backup(conn)
            conn.row_factory = sqlite3.Row
        sl = _slices(conn)
        conn.execute('BEGIN IMMEDIATE')
        try:
            got = db_.build(conn, now=now or time.time(), players=sl.get('players'), clubs=sl.get('donor_clubs'))
            if write:
                t = time.time()
                for name in ('donor_tags', 'donor_clubs'):
                    conn.execute('INSERT INTO slices(name, value, at) VALUES(?, ?, ?) '
                                 'ON CONFLICT(name) DO UPDATE SET value=excluded.value, at=excluded.at',
                                 (name, json.dumps(got['tags' if name == 'donor_tags' else 'clubs'], ensure_ascii=False), t))
                conn.execute('COMMIT')
            else:
                conn.execute('ROLLBACK')
        except Exception:
            conn.execute('ROLLBACK')
            raise
        if not write:
            conn.close()
        return dict(got['stats'], clubs=got['clubs'])
    finally:
        src.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description='후원자 장부 처음 채우기(기본: 보기만)')
    ap.add_argument('--db', required=True)
    ap.add_argument('--write', action='store_true', help='정말 쓴다(기본은 보기만)')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    st = run(a.db, write=a.write)
    if a.json:
        print(json.dumps(st, ensure_ascii=False, indent=1))
        return 0
    print('📒 후원자 장부 %s' % ('— 썼습니다' if a.write else '— 보기만(안 썼습니다. 쓰려면 --write)'))
    print('  카드 %d장(새로 %d) · 닉네임 %d개 · 시험 카드 %d · 시험 의심 %d' % (st['persons'], st['made'], st['aliases'], st['test'], st['suspect']))
    print('  딱지: ' + ' · '.join('%s %d' % (k, v) for k, v in st['tags'].items()))
    print('  팬클럽 딱지 %d · 큰손(상위 10%%) %d · 쉬는 중(30일+) %d' % (st['club'], st['big'], st['dormant']))
    print('  열린 제안: ' + ' · '.join('%s %d' % (k, v) for k, v in st['open_suggest'].items()) + '  (이번에 새로: %s)' % st['opened'])
    print('  팬클럽 사전:')
    for w, c in sorted(st['clubs'].items(), key=lambda kv: (not kv[1].get('confirmed'), kv[0])):
        if c.get('confirmed'):
            print('    ✅ %s → %s' % (w, c.get('player') or '(팬클럽 아님)'))
        else:
            print('    ❔ %s → %s  (근거: 닉네임 %s개 · 기억 %s건 · 최다 %s%% · %s)' % (
                w, c.get('player') or '모름', c.get('names'), c.get('n'), int(round((c.get('share') or 0) * 100)), c.get('players')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
