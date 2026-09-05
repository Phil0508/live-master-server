# -*- coding: utf-8 -*-
"""🔊 효과음 · 걷어낸 것들.

사장님 말
  "효과음들을 더 추가해주고 라이브모드는 없애줘 차피 안 써
   그리고 방송 제어 센터 라는 글자는 없애도 상관없어 굳이 안 필요해"

여기서 지키는 것
  ① 소리는 이름으로 부른다. 파일(sounds/<이름>.mp3)이 있으면 파일, 없으면 만든 소리.
     → 파일이 하나도 없는 지금도 소리가 나야 한다.
  ② 파일이 있는지 하나씩 받아보면 안 된다. 없는 것마다 404 가 콘솔에 쌓여
     (효과음 9개 + 시그뒤집기 5개 = 열네 줄) 진짜 오류가 그 사이에 묻힌다.
     /sfx/list 로 한 번만 묻는다.
  ③ 목록은 **이름 → 실제 파일** 로 준다. 이름만 주면 화면이 확장자를 짐작해야 해서
     .wav 를 넣었을 때 못 찾는다.
  ④ 방송 중에 끌 수 있어야 한다(sfx_enabled). 거슬리는데 못 끄면 그게 사고다.
  ⑤ 라이브 모드와 제목 글자는 흔적 없이 사라져야 한다.
     ⚠️ 라이브 모드는 단축 명령 목록에도 있었다 — 안 지웠으면 누르는 순간 터진다.

⚠️ 실제로 소리가 나는지는 여기서 못 듣는다. 2026-09-04 에 오버레이를 띄워
   확인했다 — 스위치 끄면 0번, 켜면 음 개수대로, 파일이 있으면 파일로.
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

PROJ = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
rd = lambda f: io.open(os.path.join(PROJ, f), encoding='utf-8', errors='replace').read()
OV, CT, SV = rd('overlay.html'), rd('controller.html'), rd('server.py')

OK, BAD = [], []


def chk(n, c, d=''):
    (OK if c else BAD).append(n)
    print(('  [OK] ' if c else '  [!!] ') + n + (('  -- ' + str(d)[:110]) if d else ''))


print('=' * 74)
print('① 소리를 이름으로 부른다 — 파일이 없어도 난다')
print('=' * 74)
chk('playSfx 가 있다', 'function playSfx(' in OV)
chk('소리표가 있다', 'const SFX_TUNE = {' in OV)
tune = OV.split('const SFX_TUNE = {')[1].split('\n        };')[0]
want = ['dice-roll', 'dice-score', 'dice-sig', 'dice-key', 'dice-miss',
        'dice-start', 'donation', 'goal', 'takeover']
missing = [w for w in want if ("'%s'" % w) not in tune]
chk('필요한 소리가 다 있다 (%d종)' % len(want), not missing, missing)
body = OV.split('function playSfx(')[1].split('\n        }')[0]
chk('파일이 있으면 파일을 튼다', '_sfxFile[name]' in body)
chk('없으면 만들어 낸다', 'SFX_TUNE[name]' in body and 'sgBlip' in body)
chk('겹쳐 나게 복제한다', 'cloneNode()' in body)
chk('오버레이가 여러 개면 한 곳만 낸다', 'isAudioLeader' in body)

print()
print('=' * 74)
print('② 파일이 있는지 하나씩 받아보지 않는다 — 404 가 콘솔을 덮는다')
print('=' * 74)
chk('서버가 목록을 준다', "@app.route('/sfx/list')" in SV)
chk('로그인 없이 열려 있다 (오버레이엔 세션이 없다)', "'/sfx/list'," in SV)
lst = SV.split('def api_sfx_list():')[1].split('\n@app.route')[0]
chk('이름 → 실제 파일 로 준다', "'files': out" in lst and 'pre + fn' in lst)
chk('허용 확장자만 센다', 'SFX_EXTS' in lst)
chk('훑기가 실패해도 안 터진다', 'except Exception' in lst)
chk('화면은 한 번만 묻는다', 'let _sfxListPromise' in OV and OV.count("fetch('/sfx/list')") == 1)
chk('준 파일 이름 그대로 받는다 (.wav 도 된다)', "new Audio('/sfx/' + files[name])" in OV)
# ⚠️ let 은 선언 줄을 지나기 전엔 못 읽는다. 쓰는 곳보다 위에 있어야 한다(실제로 터졌다).
chk('선언이 쓰는 곳보다 위에 있다',
    OV.index('let _sfxListPromise') < OV.index('function sfxLoadFiles')
    and OV.index('let _sfxListPromise') < OV.index('function sgLoadSounds'))
chk('시그뒤집기도 같은 길을 쓴다', 'const files = await sfxList();' in OV)
chk("clear1~5 를 그냥 받아보던 코드가 없다", "'/sfx/siggame/clear' + i" not in OV)

print()
print('=' * 74)
print('③ 방송 중에 끌 수 있다')
print('=' * 74)
chk('서버 상태에 스위치가 있다', '"sfx_enabled": True,' in SV)
chk('오버레이가 스위치를 따른다', 'window.sfxEnabled = (d.sfx_enabled !== false);' in OV)
chk('꺼져 있으면 아무 소리도 안 낸다', 'if (!window.sfxEnabled) return;' in body)
chk('조종실에 스위치가 있다', 'id="chk-sfx"' in CT and "toggleOption('sfx_enabled')" in CT)
# ⚠️ 값이 없는 옛 상태를 '꺼짐'으로 읽으면 안 된다 — 아무도 안 껐는데 소리가 사라진다
chk('옛 상태는 켜진 것으로 본다', "setChk('chk-sfx', gd.sfx_enabled !== false);" in CT)

print()
print('=' * 74)
print('④ 소리가 실제로 붙어 있는 자리')
print('=' * 74)
for call, what in (("playSfx('dice-roll')", '주사위 굴림'),
                   ("playSfx('dice-start')", '출발 칸 도착'),
                   ("playSfx('donation')", '후원 알림'),
                   ("playSfx('goal')", '목표 달성'),
                   ("playSfx('takeover')", '1등 탈환')):
    chk('%s 에 소리가 붙어 있다' % what, call in OV)
chk('도착한 칸 종류에 따라 갈린다', "_tt === 'sig' ? 'dice-sig'" in OV)
# ⚠️ 꽝은 '점수 칸인데 0점' 이다. 점수 칸과 같은 소리가 나면 안 된다.
chk('꽝은 다른 소리', "(_tt === 'score') ? 'dice-miss'" in OV)

print()
print('=' * 74)
print('⑤ 라이브 모드와 제목 글자는 흔적 없이 사라졌다')
print('=' * 74)
for bad in ('live-mode', 'liveMode', 'live-toggle', 'live-hint',
            'applyLiveMode', 'toggleLiveMode'):
    chk("'%s' 가 안 남아 있다" % bad, bad not in CT)
chk('제목 글자가 없다', '방송 제어 센터' not in CT)
# 아이콘과 연결 표시는 남아야 한다 — 서버가 살아 있는지 보는 유일한 곳이다
chk('아이콘은 남아 있다', 'fa-layer-group' in CT)
chk('연결 표시는 남아 있다', 'connection-status-badge' in CT)

print()
print('=' * 74)
print('⑥ 라이브 모드를 지울 때 옆에 붙어 있던 것까지 지우지 않았다')
print('=' * 74)
# ⚠️ 2026-09-05 실제 사고. 라이브 모드 CSS 를 통째로 잘라낼 때 바로 뒤의 오토파일럿 배너
#    CSS 가 같이 사라져, 배너가 상태와 무관하게 항상 보였다(운영에 그대로 올라갔다).
chk('오토파일럿 배너는 기본으로 숨긴다', '#autopilot-banner { display:none' in CT)
chk('켜졌을 때만 보인다', 'body.autopilot-on #autopilot-banner { display:flex; }' in CT)
chk('배너 깜빡임 정의가 있다', '@keyframes apBlink' in CT)
chk('켜기 버튼 켜짐 색이 있다', '#ai-autopilot-toggle.on' in CT)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
