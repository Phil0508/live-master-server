# -*- coding: utf-8 -*-
"""🧪 무인 방송 미리 채점 — "그때 기계가 정했다면 맞혔을까?" 를 지난 기록(donor_memory)으로 다시 돌려 본다.

하는 일
  장부의 donor_memory(후원 한 건이 누구에게 갔나)를 **시간 순서대로** 한 건씩 꺼내,
  그 **앞의 기록만** 아는 빈 기억(메모리 안 SQLite)으로 donor_memory.suggest_rules 를 돌린다 — 서버가 방송 중에 하는 것과 같은 판단.
  답을 실제로 받은 사람과 견준 뒤, 그 건을 기억에 넣고 다음 건으로 간다(방송을 거듭할수록 똑똑해지는 것까지 그대로).

  단계(tier)별로 센다 — 켬이었다면:
    자동(auto, 0.90↑)   기계가 스스로 줬을 것 → 맞힘 / **틀림(= 엉뚱한 사람에게 점수가 갔을 것)**
    추천(suggest)       배지만 떴을 것 → 맞힘 / 틀림 (사람이 누르므로 틀려도 점수는 안 샌다)
    모름(unknown)       보류 — 사람이 정했을 것

한계(숫자를 읽을 때)
  - 그때 판에 있던 선수 명단은 기록에 없다 → **같은 방송(6시간 넘게 빈 틈으로 가른다)에 점수를 받은 선수**로 어림한다.
    실제 명단은 이보다 길 수 있어(한 번도 후원을 못 받은 선수) 이름 글자 겹침이 실제보다 조금 적게 잡힌다.
  - AI 단계(④)는 부르지 않는다(돈 · 한도 · 기록 유출). 규칙으로 못 푼 건은 'AI 에게 물었을 것' 으로 따로 센다.
  - 나눠 준 후원은 기계가 고른 사람이 그 안에 있으면 맞힘(그림자 채점과 같은 규칙).

쓰는 법(장부는 **읽기만** 한다 — 켜진 서버 옆에서 돌려도 된다)
  python -m v2.tools.backtest_autopilot --db v2/data/lm2.db
  python -m v2.tools.backtest_autopilot --db v2/data/lm2.db --json      # 숫자만 JSON 으로
  ⚠️ 결과에 후원자 이름 · 금액은 찍지 않는다(알림 · 기록으로 옮겨 가도 괜찮게). --examples 를 주면 틀린 예를 몇 개 보여 준다.
"""
import argparse
import json
import sqlite3
import sys
import time
import types

from v2.server.domain import donor_memory as dm
from v2.server.domain.rules import norm_donor

GAP_SEC = 6 * 3600          # 이만큼 기록이 비면 다른 방송으로 본다
KST = 9 * 3600
OUTCOMES = ('auto_ok', 'auto_bad', 'sug_ok', 'sug_bad', 'unknown')


def _zero():
    return dict({k: 0 for k in OUTCOMES}, n=0, ai=0, src={})


def load(path):
    """donor_memory 를 읽기만 한다. [(at, donor, player, amount, message, ref)] 시간 순."""
    conn = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
    try:
        conn.execute('PRAGMA query_only = 1')
        return [tuple(r) for r in conn.execute(
            'SELECT at, donor, player, amount, message, ref FROM donor_memory ORDER BY at, id').fetchall()]
    finally:
        conn.close()


def group(rows):
    """한 후원이 여러 줄(나눠 줌)이면 한 건으로. v2 는 ref(후원 id)로, 옛 것('old:')은 후원자 · 메시지 · 같은 초로 묶는다."""
    out, idx = [], {}
    for at, donor, player, amount, message, ref in rows:
        ref = str(ref or '')
        key = ref if ref and not ref.startswith('old:') else ('old', norm_donor(donor), str(message or ''), int(float(at)))
        g = idx.get(key)
        if g is None:
            g = {'at': float(at), 'donor': donor, 'message': str(message or ''), 'players': [], 'amount': 0}
            idx[key] = g
            out.append(g)
        if player not in g['players']:
            g['players'].append(player)
        g['amount'] += int(amount or 0)
    return out


def broadcasts(groups):
    """6시간 넘게 빈 틈으로 방송을 가른다. 명단 = 그 방송에 점수를 받은 선수(어림)."""
    out = []
    for g in groups:
        if not out or g['at'] - out[-1]['last'] > GAP_SEC:
            out.append({'first': g['at'], 'last': g['at'], 'items': []})
        b = out[-1]
        b['last'] = g['at']
        b['items'].append(g)
    for b in out:
        roster = []
        for g in b['items']:
            for p in g['players']:
                if p not in roster:
                    roster.append(p)
        b['roster'] = roster
        b['label'] = time.strftime('%Y-%m-%d', time.gmtime(b['first'] + KST))
    return out


def _memory():
    conn = sqlite3.connect(':memory:', isolation_level=None)
    conn.row_factory = sqlite3.Row
    store = types.SimpleNamespace(db=conn)
    dm.ensure(store)
    return store


def judge(res, actual):
    tgt, tier = res.get('target'), res.get('tier') or 'unknown'
    if not tgt or tier == 'unknown':
        return 'unknown'
    ok = tgt in actual
    if tier == 'auto':
        return 'auto_ok' if ok else 'auto_bad'
    return 'sug_ok' if ok else 'sug_bad'


def run(rows, examples=0):
    store = _memory()
    bcs = broadcasts(group(rows))
    total, per, bad = _zero(), [], []
    for b in bcs:
        s = _zero()
        for g in b['items']:
            res, pre = dm.suggest_rules(store, g['donor'], g['message'], b['roster'])
            asked_ai = res is None
            if asked_ai:
                res = dm.suggest_after_ai(pre, {'target': None, 'confidence': 0.0, 'skipped': True})
            out = judge(res, g['players'])
            for t in (s, total):
                t['n'] += 1
                t[out] += 1
                t['ai'] += int(asked_ai)
                if out != 'unknown':
                    k = '%s:%s' % (res.get('source') or '?', 'ok' if out.endswith('ok') else 'bad')
                    t['src'][k] = t['src'].get(k, 0) + 1
            if out == 'auto_bad' and len(bad) < examples:
                bad.append({'date': b['label'], 'source': res.get('source'), 'why': res.get('why'),
                            'conf': res.get('confidence'), 'split': len(g['players']) > 1})
            # 그 건을 기억에 넣는다(서버와 같다 — 받은 사람마다 한 줄)
            share = max(1, len(g['players']))
            for p in g['players']:
                dm.remember_assignment(store, g['donor'], p, g['amount'] // share, g['message'], ref='bt', at=g['at'])
        per.append(dict(s, date=b['label'], roster=len(b['roster'])))
    return {'total': total, 'broadcasts': per, 'bad_examples': bad}


def _pct(a, b):
    return '%.1f%%' % (100.0 * a / b) if b else '-'


def report(r):
    t = r['total']
    auto = t['auto_ok'] + t['auto_bad']
    sug = t['sug_ok'] + t['sug_bad']
    lines = [
        '🧪 무인 방송 미리 채점 — 지난 후원 %d건 · 방송 %d번' % (t['n'], len(r['broadcasts'])),
        '',
        '켬이었다면',
        '  자동으로 줬을 것  %4d건 (%s) — 맞힘 %d · 틀림 %d  → 자동 정확도 %s'
        % (auto, _pct(auto, t['n']), t['auto_ok'], t['auto_bad'], _pct(t['auto_ok'], auto)),
        '  추천만 떴을 것    %4d건 (%s) — 맞힘 %d · 틀림 %d'
        % (sug, _pct(sug, t['n']), t['sug_ok'], t['sug_bad']),
        '  모름(사람이 정함) %4d건 (%s) — 그중 AI 에게 물었을 것 %d건'
        % (t['unknown'], _pct(t['unknown'], t['n']), t['ai']),
        '',
        '단서별(맞힘/틀림): ' + ' · '.join('%s %d' % (k, v) for k, v in sorted(t['src'].items())),
        '',
        '방송별 (날짜 · 건수 · 선수 수 · 자동 맞힘/틀림 · 추천 맞힘/틀림 · 모름)',
    ]
    for b in r['broadcasts']:
        lines.append('  %s  %3d건  선수 %2d  자동 %3d/%-2d  추천 %3d/%-2d  모름 %3d'
                     % (b['date'], b['n'], b['roster'], b['auto_ok'], b['auto_bad'], b['sug_ok'], b['sug_bad'], b['unknown']))
    if r['bad_examples']:
        lines += ['', '자동으로 틀렸을 예(이름 · 금액 없이)']
        for x in r['bad_examples']:
            lines.append('  %s  %s %.2f%s — %s' % (x['date'], x['source'], x['conf'] or 0, ' (나눠 줌)' if x['split'] else '', x['why']))
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description='무인 방송 미리 채점(지난 기록 · 읽기만)')
    ap.add_argument('--db', required=True, help='v2 장부(lm2.db) — 읽기만 한다')
    ap.add_argument('--json', action='store_true', help='숫자만 JSON 으로')
    ap.add_argument('--examples', type=int, default=0, help='자동으로 틀렸을 예를 몇 개 보여 줄지(기본 0)')
    a = ap.parse_args(argv)
    rows = load(a.db)
    if not rows:
        print('후원자 기억(donor_memory)이 비어 있어요 — 채점할 것이 없습니다')
        return 1
    r = run(rows, a.examples)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(report(r))
    return 0


if __name__ == '__main__':
    sys.exit(main())
