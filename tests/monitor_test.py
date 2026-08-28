# -*- coding: utf-8 -*-
"""모니터 모드(/overlay?monitor=1) — 폰으로 방송 화면을 들여다볼 때.

여기서 지켜야 하는 것은 두 가지다.
  ① 소리를 내지 않는다 (시그니처 음원 · 고액후원 영상 · 노래방 전부)
  ② 재생 대기줄을 건드리지 않는다 — 폰이 먼저 꺼내가면 그 시그니처는 방송에 안 나간다

화면 동작은 브라우저에서 따로 확인하고, 여기서는 '그렇게 짜여 있는가' 를
소스에서 확인한다. 이 조건이 조용히 사라지면 방송 사고로 이어지기 때문에,
검사로 박아둔다.
"""
import io, os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
P = r'C:\Users\Administrator\Desktop\새로다시시작\overlay.html'
M = r'C:\Users\Administrator\Desktop\새로다시시작\mobile.html'
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


ov = io.open(P, encoding='utf-8', errors='replace').read()
mo = io.open(M, encoding='utf-8', errors='replace').read()

print('=' * 74)
print('① 모니터 모드가 있는가')
print('=' * 74)
chk('주소로 켠다 (?monitor=1)', "get('monitor') === '1'" in ov)
chk('소리 리더가 되지 않는다', re.search(r'if \(IS_MONITOR\) return false;', ov) is not None)

print()
print('=' * 74)
print('② 소리를 내지 않는가')
print('=' * 74)
chk('시그니처 음원을 음소거한다', 'IS_MONITOR || !leader' in ov or 'muted = IS_MONITOR' in ov)
chk('고액후원 영상(파일)을 음소거한다', 'if (IS_MONITOR) v.muted = true;' in ov)
n_mute = ov.count("(IS_MONITOR ? '&mute=1' : '')")
chk('유튜브에 mute=1 을 붙인다 (고액후원 + 노래방)', n_mute == 2, '%d곳' % n_mute)

print()
print('=' * 74)
print('③ 재생 대기줄을 건드리지 않는가  ← 가장 중요')
print('=' * 74)
# advanceReactionQueue 안에서 IS_MONITOR 면 곧바로 빠져나가야 한다
i = ov.find('const popId = currentPlayingId;')
j = ov.find("fetch('/api/reaction/next'", i)
seg = ov[i:j] if i >= 0 and j > i else ''
chk('큐를 넘기기 전에 모니터 모드면 빠져나간다',
    'if (IS_MONITOR) {' in seg and 'return;' in seg, seg.count('IS_MONITOR'))
chk('큐 넘김 호출은 그 뒤에 있다', j > i > 0)

print()
print('=' * 74)
print('④ 폰이 모니터 모드로만 여는가')
print('=' * 74)
chk("폰 미리보기가 monitor=1 로 연다", "'/overlay?monitor=1'" in mo or '"/overlay?monitor=1"' in mo)
bad_open = re.findall(r"src=[\"']/overlay(?!\?monitor=1)", mo)
chk('monitor 없이 여는 곳이 없다', not bad_open, bad_open)
chk('새로고침도 monitor=1 을 유지한다', "'/overlay?monitor=1&t='" in mo)
chk('크게 보기도 monitor=1 이다', "window.open('/overlay?monitor=1'" in mo)

print()
print('=' * 74)
print('⑤ 폰 화면이 갱신마다 다시 켜지지 않는가')
print('=' * 74)
chk('이미 띄웠으면 다시 만들지 않는다', "if (el.querySelector('#screen-frame')) return;" in mo)
chk('앱을 닫으면 화면을 걷는다', "if (openedApp === 'screen') $('sheet-body').innerHTML = '';" in mo)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
