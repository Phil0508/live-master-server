# -*- coding: utf-8 -*-
"""🎨 방송판 생김새 토큰 — 제각각으로 되돌아가지 않는가.

사장님 말
  "그냥 오버레이 퀄리티를 높히고싶어서" → "싹해보자"

무엇이 문제였나 (2026-09-07 실측)
  그림자 72가지 · 둥글기 22가지 · 전환 속도 19가지 · 글자로 박은 색 132가지.
  위젯 하나하나는 멀쩡한데 서로 남남처럼 생겨서 '아마추어 같다' 는 인상을 줬다.
  엑셀판과 후원 순위판이 서로 다른 은·동을 쓰고, 퇴근빵만 틀이 파랑이었다.

여기서 지키는 것
  ① :root 에 단계 토큰이 있고, 편집기(admin.html)에도 같은 값으로 있다
  ② 금색 위 글자색·금색 반투명은 토큰으로만 쓴다 (글자로 박지 않는다)
  ③ 둥글기·전환 속도는 단계 밖의 값을 새로 만들지 않는다 (예외 목록만 허용)
  ④ 안 쓰는 글꼴(Chakra Petch)을 내려받지 않는다 · 숫자는 어디서나 같은 폭
  ⑤ 시그 집계 머리글은 28px(폰 10px 바닥선)을 지키면서 한 줄이다
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

PROJ = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
rd = lambda f: io.open(os.path.join(PROJ, f), encoding='utf-8', errors='replace').read()
OV, AD = rd('overlay.html'), rd('admin.html')
CSS = OV[:OV.index('</style>')]
ROOT_END = CSS.index('body.theme-pink {')
ROOT, BODY = CSS[:ROOT_END], CSS[ROOT_END:]

OK, BAD = [], []


def chk(n, c, d=''):
    (OK if c else BAD).append(n)
    print(('  [OK] ' if c else '  [!!] ') + n + (('  -- ' + str(d)[:110]) if d else ''))


def tokens(src):
    t = {}
    for blk in re.findall(r':root\s*\{([^}]*)\}', src, re.S):
        for d in re.sub(r'/\*.*?\*/', ' ', blk, flags=re.S).split(';'):
            if ':' in d and d.strip().startswith('--'):
                k, v = d.split(':', 1)
                t[k.strip()] = ' '.join(v.split())
    return t


print('=' * 74)
print('① 단계 토큰이 있고 편집기와 같다')
print('=' * 74)
TO, TA = tokens(OV), tokens(AD)
NEED = ['--gold-rgb', '--on-gold', '--gold-light', '--silver', '--bronze', '--ok', '--ok-rgb',
        '--race', '--race-rgb', '--row-bg', '--row-border',
        '--sh-1', '--sh-2', '--sh-3', '--sh-4', '--glow-s', '--glow-m', '--glow-l',
        '--ts-1', '--ts-2', '--r-s', '--r-m', '--r-l', '--t-fast', '--t-base', '--t-slow', '--ease', '--ease-pop']
miss = [k for k in NEED if k not in TO]
chk('방송판에 토큰이 다 있다 (%d개)' % len(NEED), not miss, miss)
miss = [k for k in NEED if k not in TA]
chk('편집기에도 다 있다', not miss, miss)
diff = [k for k in NEED if k in TO and k in TA and TO[k] != TA[k]]
chk('값이 같다', not diff, diff)
chk('그림자 4단은 크기 순이다',
    [int(re.search(r'0 (\d+)px', TO.get(k, '0 0px')).group(1)) for k in ('--sh-1', '--sh-2', '--sh-3', '--sh-4')]
    == sorted(int(re.search(r'0 (\d+)px', TO.get(k, '0 0px')).group(1)) for k in ('--sh-1', '--sh-2', '--sh-3', '--sh-4')))
chk('둥글기 3단은 8 · 14 · 22', (TO.get('--r-s'), TO.get('--r-m'), TO.get('--r-l')) == ('8px', '14px', '22px'))

print()
print('=' * 74)
print('② 색을 글자로 박지 않는다 — 토큰이 있는 것은 토큰으로')
print('=' * 74)
chk('금색 위 글자색(#241a05)이 :root 밖에 없다', '#241a05' not in BODY and '#241a05' not in OV[OV.index('</style>'):])
chk('금색 반투명 rgba(246,196,83…) 이 :root 밖에 없다',
    not re.search(r'rgba\(246,\s?196,\s?83', OV[ROOT_END:]))
chk('초록 rgba(46,204,113…) 이 남아 있지 않다', not re.search(r'rgba\(46,\s?204,\s?113', BODY))
chk('엑셀판·후원 순위판이 같은 은·동을 쓴다',
    'background: var(--silver); color: var(--on-silver)' in BODY and 'var(--silver), var(--silver-2)' in BODY
    and 'background: var(--bronze); color: var(--on-bronze)' in BODY and 'var(--bronze), var(--bronze-2)' in BODY)
chk('퇴근빵 틀이 유리판이다',
    re.search(r'\.home-race-box \{[^}]*background: var\(--glass-bg\)', BODY, re.S) is not None
    and re.search(r'\.home-race-box \{[^}]*box-shadow: var\(--glass-shadow\)', BODY, re.S) is not None)
chk('UP!·당첨 글자가 테마 색을 따른다', '0 0 20px #ff0055' not in BODY and 'var(--theme-neon), 0 0 50px var(--theme-neon)' in BODY)

print()
print('=' * 74)
print('③ 둥글기·속도는 단계 밖 값을 새로 만들지 않는다')
print('=' * 74)
# 허용: 토큰 · 알약 · 원 · inherit · 칸 비례(calc) · LED(6px) · 0
# ⚠️ 모서리를 따로 주는 표기도 허용한다 — 자리마다 전부 허용값이면 단계를 벗어난 게
#    아니다. (예: 위만 둥근 등급 머리띠 'var(--glass-radius) var(--glass-radius) 0 0')
#    막으려는 건 '28px' 같은 **새 숫자**를 지어내는 것이지, 모서리를 나눠 주는 게 아니다.
_R1 = r'(?:var\(--r-[sml]\)|var\(--glass-radius\)|999px|50%|inherit|6px|0)'
RADIUS_OK = re.compile(r'^(?:calc\(.*\)|%s(?:\s+%s){0,3})$' % (_R1, _R1))
bad = [v.strip() for v in re.findall(r'border-radius:\s*([^;]+);', BODY) if not RADIUS_OK.match(v.strip())]
chk('CSS 둥글기가 단계 안에 있다', not bad, bad[:5])
# 전환: var(--t-…) 아니면 안 된다. 예외 셋 — 릴(0.1s, 멈추는 좌표와 묶여 있다),
# 카드 뒤집기(.6s)·주사위 굴림(.9s)은 3D 연출이라 일부러 제 속도를 둔다
EXEMPT = ('transform 0.1s linear', 'transform .6s cubic-bezier(.4,0,.2,1)',
          'transform .9s cubic-bezier(.2, 1.1, .35, 1)')
bad = []
for v in re.findall(r'transition:\s*([^;]+);', OV):
    v = v.strip()
    if 'var(--t-' in v or v == 'none' or v in EXEMPT:
        continue
    if re.search(r'\d(?:\.\d+)?m?s', v):
        bad.append(v)
chk('전환 속도가 전부 토큰이다 (릴·뒤집기·주사위만 예외)', not bad, bad[:4])
chk('묶여 있는 릴 속도는 그대로', OV.count('transition: transform 0.1s linear') == 3)

print()
print('=' * 74)
print('④ 글꼴')
print('=' * 74)
chk('안 쓰는 Chakra Petch 를 내려받지 않는다', 'Chakra' not in OV)
chk('Pretendard 를 받는다 (없으면 Malgun Gothic 가짜 굵기)', 'pretendard' in OV.lower() and '@import' in OV)
chk('숫자 폭이 어디서나 같다 (body)', re.search(r'body, html \{[^}]*font-variant-numeric: tabular-nums', CSS) is not None)

print()
print('=' * 74)
print('⑤ 시그 집계 머리글 — 폰 바닥선(27px)을 지키면서 한 줄')
print('=' * 74)
hdr = re.search(r'\.sig-tally-header \{([^}]*)\}', BODY, re.S)
chk('28px 이다', bool(hdr) and 'font-size: 28px' in hdr.group(1))
chk('한 줄로 못 박았다', bool(hdr) and 'white-space: nowrap' in hdr.group(1))
chk('글자 수를 줄였다 (206px 판에 들어간다)', '>🎵 시그 집계<' in OV and '>🎵 시그 집계<' in AD)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
