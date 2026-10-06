# -*- coding: utf-8 -*-
"""📦 옛 프로그램 장부(DB) → v2 장부(SQLite) — 갈아탈 때 **한 번** 돌린다.

옮기는 것(옛 표 → v2)
  donation_archive · donation_history → donations   지난 방송 후원 기록. status 'archived'(누구에게 갔는지는 옛 장부에 없다),
                                                    session 'old-<회차 이름>'(아직 보관 안 된 이번 방송분은 'old-current')
  donor_memory                         → donor_memory  후원자가 누구에게 줬나 — AI 배정 제안의 '이력' (ref 'old:<id>')
  alias_memory                         → alias_memory  별명 → 선수 (같은 줄이 있으면 hits 를 더한다)
  donor_excluded                       → donor_rules.excluded · names   순위에서 뺀 이름
  vip_donators                         → donor_rules.manual             직접 준 등급
안 옮기는 것: 점수 · 대기함 · 설정(설정은 조종실 [옛 설정 옮기기] — admin.import_old) · 클릭 기록 · 은행 원장(bank_ledger).

쓰는 법(운영 서버에서 — v2 서버를 **멈춘 채로**)
  DATABASE_URL=... python -m v2.tools.import_old_db --v2-db v2/data/lm2.db            # 먼저 무엇을 옮길지 세어 보기만
  DATABASE_URL=... python -m v2.tools.import_old_db --v2-db v2/data/lm2.db --write    # 진짜로 옮긴다
  python -m v2.tools.import_old_db --sqlite <옛 sqlite 파일> --db-tz kst ...          # 옛 것을 이 PC(SQLite)에서 돌렸을 때

규칙
  - 옛 장부는 **읽기만** 한다(SELECT 만). 옛 서버는 그대로 돈다.
  - 여러 번 돌려도 두 번 들어가지 않는다 — 후원은 id(old_a<번호> · old_h<번호>)와 tx_id 로, 기억은 ref 로 거른다.
  - 옛 장부의 시각은 **서버 지역시**로 적혀 있다(운영 서버는 UTC — 옛 ts_kst 주석). --db-tz utc|kst 로 맞춘다(기본 utc).
  - v2 서버가 켜져 있으면 멈춘다(켜진 서버는 조각을 메모리에 쥐고 있어서, 여기서 고친 donor_rules 를 덮어쓴다). --force 로 무시.
"""
import argparse
import calendar
import json
import os
import sqlite3
import sys
import time
import urllib.request

from v2.server.domain.rules import norm_donor

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.dirname(HERE)
GRADES = {'VVIP': ('#f6c453', '🏆'), 'VIP': ('#c8d4e3', '👑'), 'DIAMOND': ('#5ac8fa', '💎'),
          'BRONZE': ('#c97f3d', '🥉'), 'GOLD': ('#ffd700', '⭐')}


# ── 옛 장부 열기(읽기만) ──
class Old:
    def __init__(self, sqlite_path=None, url=None):
        self.pg = bool(url)
        if self.pg:
            import psycopg2          # 운영 서버 venv 에 이미 있다(옛 server.py 가 쓴다)
            self.conn = psycopg2.connect(url)
            self.conn.set_session(readonly=True)
        else:
            self.conn = sqlite3.connect('file:%s?mode=ro' % sqlite_path, uri=True)

    def rows(self, sql):
        cur = self.conn.cursor()
        try:
            cur.execute(sql)
        except Exception as e:
            if self.pg:
                self.conn.rollback()
            print('  (건너뜀: %s — %s)' % (sql.split('FROM')[-1].split()[0], str(e).splitlines()[0][:80]))
            return []
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def to_epoch(text, tz):
    """'2026-10-01 21:33:12' (서버 지역시) → 초. 못 읽으면 None."""
    s = str(text or '').strip().replace('T', ' ')
    for fmt, n in (('%Y-%m-%d %H:%M:%S', 19), ('%Y-%m-%d %H:%M', 16)):
        try:
            t = time.strptime(s[:n], fmt)
        except ValueError:
            continue
        return float(calendar.timegm(t) - (9 * 3600 if tz == 'kst' else 0))
    return None


def server_running(url):
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


# ── 옮기기 ──
def plan(old, tz):
    """옛 장부를 읽어 v2 에 넣을 줄들을 만든다(아직 안 쓴다)."""
    out = {'donations': [], 'memory': [], 'alias': [], 'excluded': [], 'vip': [], 'skipped': 0}
    seen_tx = set()
    for r in old.rows('SELECT id, session_label, timestamp, name, amount, message, source, tx_id FROM donation_archive ORDER BY id'):
        at = to_epoch(r['timestamp'], tz)
        if at is None or r['amount'] is None:
            out['skipped'] += 1
            continue
        tx = str(r['tx_id'] or '') or 'old_a%s' % r['id']
        if tx in seen_tx:
            continue
        seen_tx.add(tx)
        out['donations'].append({'id': 'old_a%s' % r['id'], 'tx_id': tx, 'at': at, 'name': str(r['name'] or '익명')[:60],
                                 'amount': int(r['amount']), 'message': str(r['message'] or '')[:500],
                                 'source': str(r['source'] or 'old'), 'session': 'old-' + str(r['session_label'] or '?')[:40]})
    # 아직 보관되지 않은 '이번 방송' 분(옛 서버가 방송을 끝내지 않은 채 갈아탈 때)
    for r in old.rows('SELECT id, timestamp, name, amount, message, source, tx_id FROM donation_history ORDER BY id'):
        at = to_epoch(r['timestamp'], tz)
        tx = str(r['tx_id'] or '') or 'old_h%s' % r['id']
        if at is None or r['amount'] is None or tx in seen_tx:
            continue
        seen_tx.add(tx)
        out['donations'].append({'id': 'old_h%s' % r['id'], 'tx_id': tx, 'at': at, 'name': str(r['name'] or '익명')[:60],
                                 'amount': int(r['amount']), 'message': str(r['message'] or '')[:500],
                                 'source': str(r['source'] or 'old'), 'session': 'old-current'})
    for r in old.rows('SELECT id, timestamp, donor, player, amount, message FROM donor_memory ORDER BY id'):
        d, p = norm_donor(r['donor']), str(r['player'] or '').strip()
        if d == '익명' or not p:
            continue
        out['memory'].append({'at': to_epoch(r['timestamp'], tz) or 0.0, 'donor': d, 'player': p,
                              'amount': int(r['amount'] or 0), 'message': str(r['message'] or '')[:300], 'ref': 'old:%s' % r['id']})
    agg = {}
    for r in old.rows('SELECT token, player, hits, updated FROM alias_memory'):
        k = (str(r['token'] or '').strip(), str(r['player'] or '').strip())
        if k[0] and k[1]:
            a = agg.setdefault(k, {'hits': 0, 'updated': 0.0})
            a['hits'] += int(r['hits'] or 1)
            a['updated'] = max(a['updated'], to_epoch(r['updated'], tz) or 0.0)
    out['alias'] = [{'token': t, 'player': p, **v} for (t, p), v in agg.items()]
    for r in old.rows('SELECT name FROM donor_excluded'):
        n = ' '.join(str(r['name'] or '').split())
        if n:
            out['excluded'].append(n)
    for r in old.rows('SELECT name, grade, custom_color, badge FROM vip_donators'):
        n, g = ' '.join(str(r['name'] or '').split())[:30], str(r['grade'] or '').strip().upper()
        if n and g in GRADES:
            c = str(r['custom_color'] or '')
            out['vip'].append({'name': n, 'grade': g, 'color': c if len(c) == 7 and c.startswith('#') else GRADES[g][0],
                               'badge': str(r['badge'] or '')[:4] or GRADES[g][1]})
    return out


def write(v2db, p):
    """v2 장부에 넣는다 — 한 번에(하나라도 실패하면 아무것도 안 바뀐다)."""
    from v2.server.domain import donor_memory as dm
    from v2.server.store import Store
    st = Store(v2db)
    dm.ensure(st)
    db = st.db
    got = {'donations': 0, 'memory': 0, 'alias': 0, 'excluded': 0, 'vip': 0}
    db.execute('BEGIN IMMEDIATE')
    try:
        for d in p['donations']:
            cur = db.execute('INSERT OR IGNORE INTO donations (id, tx_id, at, name, amount, message, source, status, player, session) '
                             "VALUES (?, ?, ?, ?, ?, ?, ?, 'archived', NULL, ?)",
                             (d['id'], d['tx_id'], d['at'], d['name'], d['amount'], d['message'], d['source'], d['session']))
            got['donations'] += cur.rowcount
        have = {r[0] for r in db.execute("SELECT ref FROM donor_memory WHERE ref LIKE 'old:%'")}
        for m in p['memory']:
            if m['ref'] in have:
                continue
            db.execute('INSERT INTO donor_memory (at, donor, player, amount, message, ref) VALUES (?, ?, ?, ?, ?, ?)',
                       (m['at'], m['donor'], m['player'], m['amount'], m['message'], m['ref']))
            got['memory'] += 1
        db.execute('CREATE TABLE IF NOT EXISTS import_marks (name TEXT PRIMARY KEY, at REAL NOT NULL)')
        done = db.execute("SELECT 1 FROM import_marks WHERE name = 'old_alias'").fetchone()
        if not done:      # 별명은 hits 를 더하므로 두 번 돌리면 두 배가 된다 — 한 번만
            for a in p['alias']:
                db.execute('INSERT INTO alias_memory (token, player, hits, updated) VALUES (?, ?, ?, ?) '
                           'ON CONFLICT(token, player) DO UPDATE SET hits = hits + excluded.hits, '
                           'updated = MAX(updated, excluded.updated)', (a['token'], a['player'], a['hits'], a['updated']))
                got['alias'] += 1
            db.execute("INSERT INTO import_marks (name, at) VALUES ('old_alias', ?)", (time.time(),))
        row = db.execute("SELECT value FROM slices WHERE name = 'donor_rules'").fetchone()
        rules = json.loads(row[0]) if row else {'excluded': []}
        ex, names, manual = rules.setdefault('excluded', []), rules.setdefault('names', {}), rules.setdefault('manual', {})
        for n in p['excluded']:
            k = norm_donor(n)
            if k != '익명' and k not in ex:
                ex.append(k)
                names[k] = n
                got['excluded'] += 1
        for v in p['vip']:
            k = norm_donor(v['name'])
            if k != '익명' and k not in manual:
                manual[k] = v
                got['vip'] += 1
        db.execute('INSERT INTO slices (name, value, at) VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value, at = excluded.at',
                   ('donor_rules', json.dumps(rules, ensure_ascii=False), time.time()))
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        raise
    finally:
        st.close()
    return got


def main(argv=None):
    ap = argparse.ArgumentParser(description='옛 장부 → v2 장부 (한 번)')
    ap.add_argument('--sqlite', help='옛 장부가 SQLite 파일이면 그 경로(없으면 DATABASE_URL 의 Postgres)')
    ap.add_argument('--v2-db', default=os.path.join(V2, 'data', 'lm2.db'))
    ap.add_argument('--db-tz', choices=('utc', 'kst'), default='utc', help='옛 장부 시각의 기준(운영 서버 utc · 이 PC kst)')
    ap.add_argument('--write', action='store_true', help='진짜로 옮긴다(빼면 세어 보기만)')
    ap.add_argument('--check-url', default='http://127.0.0.1:5300/api/health')
    ap.add_argument('--force', action='store_true', help='v2 서버가 켜져 있어도 한다(권하지 않음)')
    a = ap.parse_args(argv)
    url = None if a.sqlite else os.environ.get('DATABASE_URL')
    if not a.sqlite and not url:
        print('옛 장부를 모릅니다 — --sqlite 파일을 주거나 DATABASE_URL 을 넣어 주세요')
        return 2
    old = Old(a.sqlite, url)
    p = plan(old, a.db_tz)
    sess = sorted({d['session'] for d in p['donations']})
    print('읽은 것: 후원 %d건(회차 %d개, 못 읽은 줄 %d) · 후원자 기억 %d · 별명 %d · 순위 제외 %d · 직접 준 등급 %d'
          % (len(p['donations']), len(sess), p['skipped'], len(p['memory']), len(p['alias']), len(p['excluded']), len(p['vip'])))
    if p['donations']:
        first, last = min(d['at'] for d in p['donations']), max(d['at'] for d in p['donations'])
        print('  후원 기간(한국 시각): %s ~ %s' % (time.strftime('%Y-%m-%d %H:%M', time.gmtime(first + 9 * 3600)),
                                           time.strftime('%Y-%m-%d %H:%M', time.gmtime(last + 9 * 3600))))
    if not a.write:
        print('세어 보기만 했습니다 — 옮기려면 --write 를 붙여 다시 돌리세요')
        return 0
    if server_running(a.check_url) and not a.force:
        print('v2 서버가 켜져 있습니다 — 먼저 멈추세요(sudo systemctl stop livemaster-v2). 켜진 서버가 순위 제외 · 등급을 덮어씁니다')
        return 3
    got = write(a.v2_db, p)
    print('옮긴 것: 후원 %(donations)d건 · 후원자 기억 %(memory)d · 별명 %(alias)d · 순위 제외 %(excluded)d · 직접 준 등급 %(vip)d' % got)
    return 0


if __name__ == '__main__':
    sys.exit(main())
