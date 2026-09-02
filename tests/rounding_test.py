# -*- coding: utf-8 -*-
"""💴 만원 반올림 — 5,000원대는 내리고 6,000원부터 올린다.

사장님 말
  "반올림 방식을 5000원은 내리고 6000원부터 올리기로 했어"

■ 왜 검사가 필요한가
  예전에는 세 곳이 셋 다 달랐다. 조종실·폰은 Math.round(5,000 을 올림), 서버 기여도는
  파이썬 round(짝수 쪽 — 15,000 → 2, 25,000 → 2). 같은 후원이 어디서 배정하느냐에 따라
  점수가 달라졌다. 이제 한 식이다: floor((금액 + 4,000) / 10,000).

여기서 지키는 것
  ① 경계표 — 5,000·5,999 는 내리고 6,000 은 올린다 (15,000·25,000 도 내린다)
  ② 세 곳(서버·조종실·폰)이 같은 답을 낸다 — 실제 코드를 꺼내 돌린다
  ③ 옛 셈(Math.round(… / 10000), round(… / 10000))이 한 줄도 안 남았다
"""
import io, json, os, re, subprocess, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
def _find_proj():
    d = HERE
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.exists(os.path.join(d, 'server.py')): return d
    return r'C:\Users\Administrator\Desktop\새로다시시작'
PROJ = _find_proj(); OK, BAD = [], []
def chk(n, c, d=''):
    (OK if c else BAD).append(n); print(('  [OK] ' if c else '  [!!] ') + n + (('  -- ' + str(d)[:110]) if d else ''))
def read(f): return io.open(os.path.join(PROJ, f), encoding='utf-8', errors='replace').read()

# 사장님 규칙을 표로 — 이게 정답이다
TABLE = [(0, 0), (4999, 0), (5000, 0), (5999, 0), (6000, 1), (9999, 1), (10000, 1),
         (14999, 1), (15000, 1), (15999, 1), (16000, 2), (25000, 2), (26000, 3),
         (35000, 3), (36000, 4), (100000, 10), (105000, 10), (106000, 11), (333000, 33)]

print('=' * 74); print('① 서버 man_won — 실제 코드를 꺼내 돌린다'); print('=' * 74)
src = read('server.py')
m = re.search(r'def man_won\(amount\):.*?\n(?=\n\ndef |\n\n\n)', src, re.S)
chk('서버에 man_won 이 있다', bool(m))
ns = {}
if m:
    exec(m.group(0), ns)
    bad = [(a, ns['man_won'](a), w) for a, w in TABLE if ns['man_won'](a) != w]
    chk('경계표 %d칸 전부 맞음' % len(TABLE), not bad, bad[:4])
    chk('5,000 은 내린다', ns['man_won'](5000) == 0)
    chk('6,000 은 올린다', ns['man_won'](6000) == 1)
    chk('15,000 도 내린다 (옛 round 는 2 였다)', ns['man_won'](15000) == 1)
    chk('쓰레기 값은 0', ns['man_won'](None) == 0 and ns['man_won']('x') == 0)

print(); print('=' * 74); print('② 조종실·폰 manWon — 실제 코드를 꺼내 node 로 돌린다'); print('=' * 74)
def grab_js(f):
    lines = read(f).splitlines()
    k = next((n for n, l in enumerate(lines) if l.strip().startswith('function manWon(')), None)
    if k is None: return None
    blk, depth = [], 0
    for l in lines[k:]:
        blk.append(l.strip()); depth += l.count('{') - l.count('}')
        if depth == 0: break
    return '\n'.join(blk)
for f in ('controller.html', 'mobile.html'):
    js = grab_js(f)
    chk('%s 에 manWon 이 있다' % f, js is not None)
    if not js: continue
    prog = js + '\nconsole.log(JSON.stringify(%s.map(a => manWon(a))));' % json.dumps([a for a, _ in TABLE])
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as t:
        t.write(prog); path = t.name
    try:
        out = subprocess.run(['node', path], capture_output=True, text=True, timeout=20).stdout.strip()
        got = json.loads(out or '[]')
        bad = [(a, g, w) for (a, w), g in zip(TABLE, got) if g != w]
        chk('%s 경계표 전부 맞음' % f, len(got) == len(TABLE) and not bad, bad[:4])
    finally:
        os.remove(path)
c_js, m_js = grab_js('controller.html'), grab_js('mobile.html')
chk('조종실과 폰의 manWon 이 글자까지 같다', c_js is not None and c_js == m_js)

print(); print('=' * 74); print('③ 옛 셈이 한 줄도 안 남았다'); print('=' * 74)
old_js = re.compile(r'Math\.round\([^;]*/\s*10000\)')
for f in ('controller.html', 'mobile.html', 'overlay.html'):
    hits = [l.strip()[:80] for l in read(f).splitlines() if old_js.search(l)]
    chk('%s 에 Math.round(…/10000) 없음' % f, not hits, hits[:2])
old_py = re.compile(r'\bround\([^)]*/\s*10000\)')
hits = [l.strip()[:80] for l in src.splitlines() if old_py.search(l) and not l.strip().startswith('#')]
chk('server.py 에 round(…/10000) 없음', not hits, hits[:2])
chk('서버 기여도 두 곳이 man_won 을 쓴다', src.count('man_won(_amt - _price)') == 1 and src.count('man_won(_sig_amt - _price)') == 1)
chk('조종실 배정이 manWon 을 쓴다', read('controller.html').count('manWon(') >= 5)
chk('폰 배정이 manWon 을 쓴다', read('mobile.html').count('manWon(') >= 2)

print(); print('=' * 74); print('통과 %d · 실패 %d' % (len(OK), len(BAD))); print('=' * 74)
sys.exit(1 if BAD else 0)
