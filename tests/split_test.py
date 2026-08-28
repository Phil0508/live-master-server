# -*- coding: utf-8 -*-
"""나눠주기 계산이 다시 갈라지지 않게 못을 박는다.

조종실과 폰에 같은 splitPoints() 가 하나씩 있다. 한쪽만 고치면 또 갈라지므로
'두 파일의 함수가 글자까지 같은가'를 검사한다. 그리고 그 함수를 실제로 돌려
어떤 금액·인원이든 합계가 '혼자 받았을 때'와 같은지 본다.

⚠️ 내가 옮겨 적은 식이 아니라 파일에서 꺼낸 진짜 코드를 node 로 돌린다.
   옮겨 적으면 그 과정에서 또 틀린다(파이썬 round 는 5 를 내리고 JS 는 올린다).
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


def grab(path):
    """파일에서 splitPoints 함수를 통째로 꺼낸다."""
    lines = io.open(os.path.join(ROOT, path), encoding='utf-8', errors='replace').read().splitlines()
    i = next((k for k, l in enumerate(lines) if l.strip().startswith('function splitPoints(')), None)
    if i is None:
        return None
    out = []
    for l in lines[i:]:
        out.append(l.strip())
        if l.strip() == '}':
            break
    return '\n'.join(out)


print('=' * 74)
print('① 조종실과 폰이 같은 식을 쓰는가')
print('=' * 74)
ctrl, mob = grab('controller.html'), grab('mobile.html')
chk('조종실에 splitPoints 가 있다', ctrl is not None)
chk('폰에 splitPoints 가 있다', mob is not None)
chk('두 파일의 식이 글자까지 같다', ctrl is not None and ctrl == mob,
    '다름' if ctrl != mob else '')

print()
print('=' * 74)
print('② 어떻게 나눠도 합계가 혼자 받았을 때와 같은가')
print('=' * 74)
if ctrl:
    js = ctrl + """
const bad = [];
const rows = [];
for (let 만 = 0; 만 <= 60; 만++) {
  for (const 잔돈 of [0, 1000, 3000, 5000, 7000, 9999]) {
    const a = 만 * 10000 + 잔돈;
    const 혼자 = Math.round(a / 10000);
    for (let n = 1; n <= 12; n++) {
      const p = splitPoints(a, n);
      const 합 = p.reduce((x, y) => x + y, 0);
      if (합 !== 혼자) bad.push({금액: a, 인원: n, 혼자, 합, 나눔: p});
      if (p.some(v => v < 0)) bad.push({금액: a, 인원: n, 사유: '음수'});
      if (p.length !== n) bad.push({금액: a, 인원: n, 사유: '인원 수가 안 맞음'});
      // 가장 많이 받는 사람과 가장 적게 받는 사람의 차이는 1점을 넘으면 안 된다
      if (Math.max(...p) - Math.min(...p) > 1) bad.push({금액: a, 인원: n, 사유: '치우침', 나눔: p});
    }
  }
}
for (const a of [10000, 30000, 50000, 70000, 333000]) {
  rows.push({금액: a, 혼자: Math.round(a/10000), 둘: splitPoints(a,2), 셋: splitPoints(a,3)});
}
console.log(JSON.stringify({bad: bad.slice(0, 8), 검사한칸: 61*6*12, 어긋난칸: bad.length, rows}));
"""
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(js)
        tmp = f.name
    try:
        out = subprocess.run(['node', tmp], capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
        if out.returncode != 0:
            chk('식을 돌려볼 수 있다', False, out.stderr[-200:])
        else:
            r = json.loads(out.stdout)
            chk('%d가지 금액·인원 조합에서 합계가 정확하다' % r['검사한칸'],
                r['어긋난칸'] == 0, r['bad'][:3])
            print('     예시 (금액 / 혼자 / 2명 / 3명):')
            for row in r['rows']:
                print('       %8s원  %2d점  %-10s %-12s' % (
                    format(row['금액'], ','), row['혼자'],
                    '+'.join(map(str, row['둘'])), '+'.join(map(str, row['셋']))))
    finally:
        os.unlink(tmp)

print()
print('=' * 74)
print("③ '반반' 이 정말 없어졌는가")
print('=' * 74)
c = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8', errors='replace').read()
m = io.open(os.path.join(ROOT, 'mobile.html'), encoding='utf-8', errors='replace').read()
chk('조종실에 assignHalf 가 없다', 'assignHalf' not in c)
chk('조종실 대기함에 반반 버튼이 없다', '🌓 반반' not in c)
chk('폰에 반반 버튼이 없다', ">반반<" not in m)
chk("폰이 'half' 모드를 안 쓴다", "'half')" not in m.replace('class="half"', ''))
chk('나눠주기 버튼은 남아 있다', '나눠주기</button>' in c and '나눠주기</button>' in m)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
