# -*- coding: utf-8 -*-
"""🎲 주사위 22칸 기본판 프리셋.

사장님이 정한 판:
  출발 1 · 시그 5(이꾸욧2·포카치노1·멈춘시간2) · 꽝 2 · 코끼리코 3
  · 기여도20 1 · 기여도10 2 · 5점 3 · 고수 2 · 완력기 3   = 22칸

무엇을 지키나
  · 칸 수와 종류별 개수가 정한 대로인가 (하나만 틀려도 방송에서 알게 된다)
  · 7×6 테두리가 정확히 22칸인가
  · 같은 종류가 붙어 있지 않고, 시그니처가 고르게 흩어져 있는가
  · 시그니처를 못 찾으면 조용히 넘어가지 않고 어느 칸인지 알려주는가
  · 이름 찾기가 띄어쓰기·따옴표 때문에 헛발질하지 않는가
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'C:\Users\Administrator\Desktop\새로다시시작'
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


src = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8', errors='replace').read()

print('=' * 74)
print('① 칸 구성이 정한 대로인가')
print('=' * 74)
i = src.find('const DGC_PRESET_22')
chk('프리셋이 있다', i > 0)
blk = src[i:src.find('];', i)] if i > 0 else ''

rows = []
for m in re.finditer(r"\{\s*id:\s*(\d+),\s*type:\s*'(\w+)'(?:,\s*label:\s*'([^']*)')?"
                     r"(?:,\s*points:\s*(-?\d+))?(?:,\s*sigName:\s*'([^']*)')?", blk):
    rows.append({'id': int(m.group(1)), 'type': m.group(2), 'label': m.group(3) or '',
                 'points': int(m.group(4)) if m.group(4) else None, 'sig': m.group(5) or ''})

chk('출발 말고 21칸 (합쳐서 22칸)', len(rows) == 21, len(rows))
chk('칸 번호가 1~21 로 빠짐없다', sorted(r['id'] for r in rows) == list(range(1, 22)),
    sorted(r['id'] for r in rows))

want = {
    ('sig', '이꾸욧'): 2, ('sig', '포카치노'): 1, ('sig', '멈춘시간'): 2,
    ('score', 2): 2, ('score', 5): 3, ('score', 10): 2, ('score', 20): 1,
}
got = {}
for r in rows:
    if r['type'] == 'sig':
        got[('sig', r['sig'])] = got.get(('sig', r['sig']), 0) + 1
    elif r['type'] == 'score':
        got[('score', r['points'])] = got.get(('score', r['points']), 0) + 1
for k, n in want.items():
    chk('%s %s → %d칸' % (k[0], k[1], n), got.get(k) == n, got.get(k))

miss = {}
for r in rows:
    if r['type'] == 'mission':
        key = r['label'].split('—')[0].strip()
        miss[key] = miss.get(key, 0) + 1
chk('코끼리코 3칸', miss.get('코끼리코') == 3, miss.get('코끼리코'))
chk('고수 2칸', miss.get('고수') == 2, miss.get('고수'))
chk('완력기 3칸', miss.get('완력기') == 3, miss.get('완력기'))

print()
print('=' * 74)
print('② 판 크기 — 7×6 테두리가 정확히 22칸인가')
print('=' * 74)
m = re.search(r"dgcCall\('setup',\s*\{\s*cols:\s*(\d+),\s*rows:\s*(\d+)", src[i:] if i > 0 else '')
cols, rows_n = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
chk('7×6 으로 깐다', (cols, rows_n) == (7, 6), (cols, rows_n))
chk('테두리 칸 수가 22 다 (2×(가로+세로)-4)', 2 * (cols + rows_n) - 4 == 22, 2 * (cols + rows_n) - 4)

print()
print('=' * 74)
print('③ 같은 종류가 붙어 있지 않고 시그니처가 흩어져 있는가')
print('=' * 74)
seq = [r['type'] for r in sorted(rows, key=lambda x: x['id'])]
adj = [i2 + 1 for i2 in range(len(seq) - 1) if seq[i2] == seq[i2 + 1]
       and seq[i2] in ('sig',)]
chk('시그니처 칸이 서로 붙어 있지 않다', not adj, adj)
sig_ids = sorted(r['id'] for r in rows if r['type'] == 'sig')
gaps = [sig_ids[k + 1] - sig_ids[k] for k in range(len(sig_ids) - 1)]
chk('시그니처가 고르게 흩어져 있다 (간격 3칸 이상)', gaps and min(gaps) >= 3, (sig_ids, gaps))

print()
print('=' * 74)
print('④ 못 찾은 시그니처를 조용히 넘기지 않는가')
print('=' * 74)
fn = src[src.find('async function dgcPreset22'):]
fn = fn[:fn.find('\n        function ')] if '\n        function ' in fn else fn[:4000]
chk('못 찾으면 목록에 담는다', 'missing.push' in fn)
chk('그 칸은 빈칸으로 남긴다 (엉뚱한 걸 붙이지 않는다)', 'continue;' in fn)
chk('사람에게 알린다', 'premiumAlert' in fn and 'missing' in fn)
chk('덮어쓰기 전에 물어본다', 'premiumConfirm' in fn)

print()
print('=' * 74)
print('⑤ 이름 찾기 — 띄어쓰기·따옴표에 헛발질하지 않는가')
print('=' * 74)
m = re.search(r'function dgcFindSig[\s\S]*?\n        \}', src)
chk('이름 찾기 함수가 있다', m is not None)
if m:
    js = m.group(0) + """
const L = [{id:1,title:'이꾸욧'},{id:2,title:' 포카치노 '},{id:3,title:'멈춘 시간'},
           {id:4,title:'"이꾸욧!"'},{id:5,title:'포카치노 챌린지'},{id:6,title:'전혀다른것'}];
const p = n => { const r = dgcFindSig(L, n); return r ? r.id : null; };
console.log(JSON.stringify({
  exact: p('이꾸욧'), space: p('포카치노'), inner: p('멈춘시간'),
  none: p('없는이름'),
  quoted: (() => { const r = dgcFindSig([{id:9,title:'"이꾸욧!"'}], '이꾸욧'); return r && r.id; })(),
  partial: (() => { const r = dgcFindSig([{id:8,title:'포카치노 챌린지'}], '포카치노'); return r && r.id; })(),
}));
"""
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(js)
        tmp = f.name
    try:
        out = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
        j = json.loads(out.stdout) if out.returncode == 0 else {}
    finally:
        os.unlink(tmp)
    chk('그대로 있는 이름을 찾는다', j.get('exact') == 1, j.get('exact'))
    chk('앞뒤 공백을 넘긴다', j.get('space') == 2, j.get('space'))
    chk('제목 속 띄어쓰기를 넘긴다 (멈춘 시간)', j.get('inner') == 3, j.get('inner'))
    chk('따옴표·느낌표를 넘긴다', j.get('quoted') == 9, j.get('quoted'))
    chk('뒤에 말이 붙어도 찾는다', j.get('partial') == 8, j.get('partial'))
    chk('없는 이름은 못 찾았다고 한다', j.get('none') is None, j.get('none'))

print()
print('=' * 74)
print('⑥ 글씨가 폰에서 읽히는 크기인가')
print('=' * 74)
"""방송판은 1080 폭이고 아이폰에서는 402px 로 줄어든다 — 2.7배 작아진다.
   예전에는 칸 글씨 10px(폰 3.7px) · 도착 카드 22px(폰 8px) 이라 못 읽었다."""
ov = io.open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8', errors='replace').read()
P_PHONE = 1080 / 402

m = re.search(r'const GAP = (\d+), MAXW = (\d+), MAXH = (\d+), CELL_CAP = (\d+)', ov)
chk('칸 크기를 화면에 맞춰 키운다', m is not None, m.group(0) if m else '못 찾음')
if m:
    gap, maxw, maxh, cap = (int(x) for x in m.groups())
    cell = max(40, min(cap, (maxw - gap * 6) // 7, (maxh - gap * 5) // 6))
    chk('22칸(7×6) 판의 칸이 120px 이상', cell >= 120, '%dpx' % cell)
    chk('판이 세로 안전지대(840)를 안 넘는다', 6 * cell + gap * 5 <= maxh,
        '%dpx' % (6 * cell + gap * 5))

    r = re.search(r'\.dg-tile \.dg-lbl \{[\s\S]*?font-size: calc\(var\(--dg-cell[^)]*\) \* ([\d.]+)\)', ov)
    chk('칸 글씨가 칸 크기에 비례한다 (px 로 못박지 않았다)', r is not None,
        r.group(1) if r else '못 찾음')
    if r:
        px = cell * float(r.group(1))
        chk('칸 글씨가 폰에서 10px 이상', px / P_PHONE >= 10,
            '%.0fpx → 폰 %.1fpx (예전 10px → 3.7px)' % (px, px / P_PHONE))

for name, pat, want in [
    ('도착 카드 글씨', r'\.dg-card-txt \{ font-size: (\d+)px', 50),
    ('도착 카드 아이콘', r'\.dg-card-ico \{ font-size: (\d+)px', 80),
    ('주사위 눈 합계', r'\.dg-sum \{ font-size: (\d+)px', 55),
]:
    mm = re.search(pat, ov)
    v = int(mm.group(1)) if mm else 0
    chk('%s가 폰에서 읽힌다' % name, v >= want,
        '%dpx → 폰 %.1fpx' % (v, v / P_PHONE) if mm else '못 찾음')

chk('점수 칸도 라벨이 있으면 라벨을 앞세운다 (꽝을 알 수 있게)',
    "t.label ? '<span class=\"dg-lbl\">' + dgEsc(t.label)" in ov)

long_lbl = [r['label'] for r in rows if len(r['label']) > 6]
chk('칸 라벨이 짧다 (긴 설명은 도착 카드에)', not long_lbl, long_lbl)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
