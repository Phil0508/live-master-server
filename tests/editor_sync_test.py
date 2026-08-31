# -*- coding: utf-8 -*-
"""🪞 편집기가 방송판과 같은 것을 보여주는가.

왜 만들었나
  편집기(admin.html)는 방송판(overlay.html)의 CSS 와 마크업을 '손으로 베껴'
  갖고 있었다. 그래서 방송판을 고칠 때마다 두 곳을 같이 고쳐야 했고, 안 고치면
  편집기가 거짓말을 한다.

  2026-08-31 실측 — 어긋난 것들
    · 같은 이름의 규칙 18개 중 56곳의 값이 달랐다
    · 엑셀판이 편집기 698×130, 실제 방송 990×399 (폭이 292px 차이)
    · 후원 순위판이 편집기 262×188, 실제 380×393
    · 위젯 자리 5곳이 달랐다 (그날 방송판만 658 로 옮기고 편집기를 안 고쳤다)
    · 끌 수 있는 위젯이 6개인데 방송이 읽는 것은 4개였다 —
      주사위판·퇴근빵은 끌어서 저장해도 방송이 무시했다

여기서 지키는 것
  ① 편집기에 끼운 hud.css 가 방송판에서 뽑은 것과 같은가
  ② 편집기 디자인 토큰이 방송판과 같은 값인가
  ③ 끌 수 있는 것 = 방송이 읽는 것 인가
  ④ 그림자가 인라인으로 크기를 손으로 박고 있지 않은가
  ⑤ 기본 자리가 방송판과 같은가 (사장님이 안 옮겼을 때 서는 자리)
  ⑥ 옛 배치 파일이 방송을 되돌리지 못하는가 · 안전지대 붙잡기가 양쪽에 있는가

⚠️ 여기서 잡지 못하는 것: 룰렛·슬롯·시그뒤집기·노래방·계좌영상·주사위판의
   그림자는 방송판 자체가 JS/인라인으로 그려 클래스가 없다. 그건 ⑤ 에서
   자리만 보고, 크기는 사람이 봐야 한다.
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = r'C:\Users\Administrator\Desktop\새로다시시작'


def _find_proj():
    d = HERE
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.exists(os.path.join(d, 'overlay.html')):
            return d
    return REPO


PROJ = _find_proj()
ov = io.open(os.path.join(PROJ, 'overlay.html'), 'rb').read().replace(b'\x00', b'').decode('utf-8')
ad = io.open(os.path.join(PROJ, 'admin.html'), 'rb').read().decode('utf-8')

ok = bad = 0


def chk(name, cond, extra=''):
    global ok, bad
    if cond:
        ok += 1
        print('  [OK] %s%s' % (name, ('  -- ' + str(extra)[:90]) if extra else ''))
    else:
        bad += 1
        print('  [!!] %s  -- %s' % (name, extra))


print('=' * 74)
print('① 끼워 넣은 hud.css 가 방송판에서 뽑은 것과 같은가')
print('=' * 74)
"""⚠️ build_hud_css.py 를 안 돌리고 방송판만 고치면 여기서 걸린다.
   '고치는 곳은 overlay.html 한 곳' 이라는 약속을 지키게 하는 검사다."""
build = os.path.join(PROJ, 'build_hud_css.py')
chk('만드는 대본이 있다', os.path.exists(build))
if os.path.exists(build):
    r = subprocess.run([sys.executable, build, '--check'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', cwd=PROJ)
    chk('hud.css · admin.html 이 overlay.html 과 같다', r.returncode == 0,
        (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else '')
chk('편집기에 끼운 자리가 있다', 'hud.css 시작' in ad and 'hud.css 끝' in ad)
# ⚠️ 끼운 구간 밖에 HUD 규칙이 또 있으면 그게 나중에 이겨서 다시 어긋난다
before = ad.split('hud.css 시작')[0]
strays = re.findall(r'(?:^|[;\s{])(\.(?:excel-|r-name|r-score|r-contrib|r-rank|acc-|dr-|'
                    r'donor-rank|sig-tally|notice-|goal-rail|ticker-|hr-goal|home-race)[\w-]*)\s*[,{]',
                    before)
chk('베낀 옛 규칙이 안 남아 있다', not strays, ', '.join(sorted(set(strays))[:6]))

print()
print('=' * 74)
print('② 디자인 토큰이 같은 값인가')
print('=' * 74)
"""⚠️ 편집기에 --glass-shadow · --tx-2 등 5개가 아예 없어서, 미리보기가 색과
   그림자를 잃고 있었다. 사람이 rgba 값을 손으로 적어 넣는 일까지 벌어졌다."""


def tokens(src):
    t = {}
    for blk in re.findall(r':root\s*\{([^}]*)\}', src, re.S):
        for d in re.sub(r'/\*.*?\*/', ' ', blk, flags=re.S).split(';'):
            if ':' in d and d.strip().startswith('--'):
                k, v = d.split(':', 1)
                t[k.strip()] = ' '.join(v.split())
    return t


TO, TA = tokens(ov), tokens(ad)
hud = io.open(os.path.join(PROJ, 'hud.css'), encoding='utf-8').read() if \
    os.path.exists(os.path.join(PROJ, 'hud.css')) else ''
need = sorted({v for v in re.findall(r'var\(\s*(--[\w-]+)', hud) if v in TO})
miss = [v for v in need if v not in TA]
diff = [v for v in need if v in TA and TA[v] != TO[v]]
chk('hud.css 가 쓰는 토큰이 편집기에 다 있다 (%d개)' % len(need), not miss, ', '.join(miss))
chk('그 값이 방송판과 같다', not diff,
    ' · '.join('%s 방송판 %s / 편집기 %s' % (v, TO[v][:18], TA[v][:18]) for v in diff))

print()
print('=' * 74)
print('③ 끌 수 있는 것 = 방송이 읽는 것 인가')
print('=' * 74)
"""⚠️ 편집기에서 끌어 저장해도 방송이 안 읽으면 그건 거짓말이다.
   주사위판·퇴근빵이 실제로 그랬다."""
# ⚠️ 예전에는 넷만 읽는 배열을 찾았다. 지금은 LAY_IDS 하나가 목록이다.
#    아무 배열이나 잡으면 엉뚱한 것(전광판 둘)이 걸려 검사가 거짓으로 통과한다.
m = re.search(r'const LAY_IDS = \[([\s\S]*?)\];', ov)
honored = set(re.findall(r"'([\w-]+)'", m.group(1))) if m else set()
# ⚠️ 못 박은 것(data-pinned)은 빼고 센다. 여는 태그를 통째로 잡아야 한다 —
#    data-id 뒤에 style 이 오는 것이 대부분이라 '>' 로 끝난다고 보면 하나도 안 잡힌다.
drag = {t.group(1) for t in re.finditer(r'<div class="widget" id="([\w-]+)"[^>]*>', ad)
        if 'data-pinned' not in t.group(0)}
chk('방송이 읽는 목록을 찾았다', honored, ' · '.join(sorted(honored)))
chk('둘이 같다', drag == honored,
    '끌 수 있음 %s / 방송이 읽음 %s' % (sorted(drag), sorted(honored)))

print()
print('=' * 74)
print('④ 그림자가 크기를 손으로 박고 있지 않은가')
print('=' * 74)
"""hud.css 가 아무리 정확해도, 그림자가 인라인으로 크기를 박아 두면 안 걸린다.
   ⚠️ 아래 여섯은 방송판 자체가 JS/인라인으로 그려 클래스가 없다 — 어쩔 수 없다.
      나머지가 인라인으로 돌아가면 그건 되돌아간 것이다."""
INLINE_OK = {'roulette', 'slot', 'siggame', 'karaoke', 'acct_video', 'dicegame', 'sig-tally'}
parts = re.split(r'(?=<div class="widget" id=")', ad)
for p in parts[1:]:
    w = re.match(r'<div class="widget" id="([\w-]+)"', p)
    if not w:
        continue
    wid = w.group(1)
    if wid in INLINE_OK:
        continue
    hard = re.findall(r'(?:font-size|height|border-radius):\s*[\d.]+px', p)
    chk('%s 그림자가 클래스로 그려진다' % wid, not hard, ', '.join(sorted(set(hard))[:4]))

print()
print('=' * 74)
print('⑤ 기본 자리가 방송판과 같은가')
print('=' * 74)
"""사장님이 아직 안 옮긴 위젯이 서는 자리다 (배치 파일에 없으면 여기에 선다).
   화면에서 직접 잰 폭으로 계산한다 (오른쪽 기준인 것은 1038 - 폭).
   ⚠️ 엑셀판·퇴근빵은 right 기준이라 폭이 바뀌면 left 도 같이 바뀐다. 안 바꾸면
      편집기가 엉뚱한 데를 가리킨다 — 엑셀판을 990 으로 넓힌 날 실제로 그랬다."""
WANT = {                       # 위젯: (왼쪽, 위, 왜)
    'ranking':    (48,  167, '오른쪽 42 기준 · 폭 990'),
    'gauge':      (1046, 115, '화면 오른쪽 끝'),
    'account':    (6,   115, '머리 줄 왼쪽 끝'),
    'notice':     (654, 115, '머리 줄에서 계좌(640) + gap 8 다음'),
    'ticker_top': (0,   115, '안전지대 위 끝'),
    'ticker_bottom': (0, 882, '안전지대 아래 끝'),
    'dicegame':   (6,   307, '게임 자리'),
    'donor-rank': (658, 387, '오른쪽 끝 1038 · 폭 380'),
    'sig-tally':  (800, 315, ''),
    'home-race':  (452, 167, '엑셀판 자리(오른쪽 42, 위 167) · 폭 586'),
    'match':      (288, 795, ''),
    'roulette':   (234, 311, ''),
    'slot':       (191, 452, ''),
    'siggame':    (171, 340, ''),
}
for wid, (wl, wt, why) in WANT.items():
    m = re.search(r'id="%s" data-id="[\w-]+"[^>]*style="left:(-?\d+)px; top:(-?\d+)px' % re.escape(wid), ad)
    if not m:
        chk('%s 자리를 찾았다' % wid, False, '못 찾음')
        continue
    got = (int(m.group(1)), int(m.group(2)))
    chk('%s 자리 %s' % (wid, why or ''), got == (wl, wt),
        '편집기 %s / 있어야 할 곳 %s' % (got, (wl, wt)))

print()
print('=' * 74)
print('⑥ 옛 배치 파일 막기 · 안전지대 붙잡기')
print('=' * 74)
"""⚠️ 저장소에 있던 layout.json 에는 게이지 y=1598(폰에서 안 보이는 구역),
   엑셀판 362,178(옛 크기 기준) 이 남아 있었다. 방송판이 전부 읽게 바꾼 뒤로는
   그 파일 하나가 방송을 통째로 옛 자리로 되돌릴 수 있다. 판 번호로 막는다."""
chk('방송판이 판 번호를 본다', "(ly.__v || 0) >= 2" in ov)
chk('편집기가 판 번호를 적는다', 'layout.__v = 2' in ad)
# ⚠️ 예전에 룰렛이 채팅창을 39px, 슬롯이 80px 침범해 폰에서 잘렸다. 그래서 잠갔었다.
#    이제 잠그는 대신 붙잡는다 — 붙잡기가 사라지면 그 사고가 그대로 돌아온다.
chk('편집기에 안전지대 붙잡기가 있다', 'function holdInSafe(' in ad)
chk('끌기와 크기조절 양쪽에서 붙잡는다', ad.count('holdInSafe(activeWidget') >= 2)
chk("'안전지대 무시' 스위치가 있다", 'id="free-on"' in ad)
chk('무시를 끄면 나가 있던 것을 불러들인다', 'window.reholdAll' in ad and 'onchange="reholdAll()"' in ad)
chk('방송판도 무시 표시를 따른다', 'ly.__free' in ov)
# ⚠️ layout.json 이 git 에 있으면 자동배포(git reset --hard)가 사장님이 방금 잡은
#    자리를 통째로 되돌린다. 서버가 쓰는 파일이니 저장소가 들고 있으면 안 된다.
gi = io.open(os.path.join(PROJ, '.gitignore'), encoding='utf-8').read()
chk('layout.json 을 저장소가 안 들고 있다 (배포가 자리를 안 지운다)',
    'layout.json' in gi)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (ok, bad))
print('=' * 74)
sys.exit(1 if bad else 0)
