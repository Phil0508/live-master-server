# -*- coding: utf-8 -*-
"""🖥️➗ 반쪽 화면(769~1024px)에서 조종실이 무너지지 않는가.

사장님 말
  "지금 보면 내가 이렇게 절반으로 갈라두고 쓰거든 좀 별로네..
   그리고 너가 보기에 너무 난잡해보이지 않아?"

무엇이 문제였나 (창 956px 에서 실측)
  ① 토글에 flex: 1 이 박혀 있었다. flex:1 은 '기본 너비 0' 이라, 브라우저가
     "0짜리 넷이니 한 줄에 다 들어가네" 하고 **줄바꿈을 영영 안 한다**.
     넷이 짜부라져 '오늘의 시그니처' 가 한 글자씩 세로로 쌓였다.
  ② 탭 10개가 가로로 107px 넘쳐 마지막 탭이 잘려 있었다.
  ③ 머리말이 153px — 제목이 한 줄을 통째로 먹었다.
  ④ 큰 화면용(1024 초과)과 폰용(768 이하) 사이에 아무 규칙이 없었다.
     반쪽 화면이 정확히 그 사이에 들어간다.

⚠️ 이 검사는 브라우저를 안 띄운다. 실제 픽셀은 2026-09-04 에 956·1440·430px
   세 폭으로 직접 열어 확인했다(탭 넘침 0, 머리말 109px, 라벨 한 줄).
   여기서는 **그 결론을 되돌리는 수정이 들어오면 걸리게** 못을 박아 둔다.
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

PROJ = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
CT = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8', errors='replace').read()

OK, BAD = [], []


def chk(n, c, d=''):
    (OK if c else BAD).append(n)
    print(('  [OK] ' if c else '  [!!] ') + n + (('  -- ' + str(d)[:110]) if d else ''))


print('=' * 74)
print('① 토글이 스스로 접힌다 — flex:1 은 줄바꿈을 막는다')
print('=' * 74)
bare = re.findall(r'class="toggle-row"[^>]*style="flex:\s*1\s*[;"]', CT)
chk('토글에 맨 flex:1 이 남아 있지 않다', not bare, bare[:2])
chk('최소 너비를 준다 (flex: 1 1 …px)',
    len(re.findall(r'class="toggle-row"[^>]*style="flex:\s*1\s+1\s+\d+px', CT)) >= 6,
    len(re.findall(r'class="toggle-row"[^>]*style="flex:\s*1\s+1\s+\d+px', CT)))
chk('한글이 글자 단위로 안 쪼개진다', '.toggle-label { word-break: keep-all; }' in CT)

print()
print('=' * 74)
print('② 기본 설정 토글은 격자로 — flex 면 끝에 홀로 남은 칸이 가로를 다 먹는다')
print('=' * 74)
chk('toggle-grid 규칙이 있다', '.toggle-grid {' in CT)
chk('칸 너비를 스스로 맞춘다', 'repeat(auto-fit, minmax(' in CT)
chk('기본 설정에 실제로 붙어 있다', 'class="control-group toggle-grid"' in CT)

print()
print('=' * 74)
print('③ 반쪽 화면 전용 규칙이 있고, **뒤에** 있어야 한다')
print('=' * 74)
half = CT.find('@media (min-width: 769px) and (max-width: 1024px)')
m1024 = CT.find('@media (max-width: 1024px)')
m768 = CT.rfind('@media (max-width: 768px) { .header-buttons')
chk('반쪽 화면 규칙이 있다', half > 0)
# ⚠️ 여기서 한 번 헛발질했다. 앞에 두면 뒤엣것이 같은 선택자를 덮어써서
#    코드만 바뀌고 화면은 그대로였다. 순서가 곧 동작이다.
chk('1024px 블록보다 뒤에 있다', half > m1024 > 0, '반쪽=%d, 1024=%d' % (half, m1024))
chk('768px 블록보다 뒤에 있다', half > m768 > 0, '반쪽=%d, 768=%d' % (half, m768))

seg = CT[half:half + 1800] if half > 0 else ''
chk('탭을 옆으로 밀지 않고 두 줄로 접는다',
    'flex-wrap: wrap' in seg and 'overflow-x: visible' in seg)
chk('머리말을 눕혀 제목 옆에 도구가 붙는다', '.header { flex-direction: row' in seg)

print()
print('=' * 74)
print('④ 미디어 패널을 억지로 좁히지 않는다')
print('=' * 74)
# ⚠️ 340px 로 조였더니 안쪽 내용(467px)이 옆 리액션 토글 위로 삐져나왔다.
mp = re.search(r'#ios-mini-media-panel \{[^}]*\}', seg)
chk('반쪽 화면에서 패널 규칙이 있다', bool(mp), mp.group(0) if mp else '')
chk('폭을 못 박지 않는다 (flex: 0 1 auto)', bool(mp) and 'flex: 0 1 auto' in mp.group(0),
    mp.group(0) if mp else '')
chk('좁은 max-width 를 다시 넣지 않았다',
    not re.search(r'#ios-mini-media-panel \{[^}]*max-width:\s*[1-3]\d{2}px', seg))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
