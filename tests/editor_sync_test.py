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
  ⑦ 위젯이 무대 안에서 제 깊이로 닫히는가 (밖으로 나가면 클릭을 삼킨다)
  ⑧ 겹쳐 있어도 손이 닿는가 · 무대 배율이 뒤집히지 않는가

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
REPO = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))


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
   ⚠️ 아래 것들은 방송판 자체가 JS/인라인/canvas 로 그려 클래스가 없다 — 어쩔 수 없다.
      나머지가 인라인으로 돌아가면 그건 되돌아간 것이다.
   🎱 핀볼은 판 전체가 canvas 한 장이라 흉내낼 마크업이 아예 없다(편집기는 크기만 잡는다)."""
INLINE_OK = {'roulette', 'slot', 'siggame', 'karaoke', 'acct_video', 'dicegame', 'sig-tally',
             'pinball'}
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
    'pinball':    (50,  300, '🎱 구슬 핀볼 — 게임 자리'),
    'donor-rank': (658, 387, '오른쪽 끝 1038 · 폭 380'),
    'sig-tally':  (800, 315, ''),
    'home-race':  (92,  167, '오른쪽 42 기준 · 폭 946 (판을 540→900 으로 넓혔다)'),
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
print('⑥ 옛 배치 파일 막기 · 안전지대를 걷어낸 것이 양쪽에 반영됐는가')
print('=' * 74)
"""⚠️ 저장소에 있던 layout.json 에는 게이지 y=1598(폰에서 안 보이는 구역),
   엑셀판 362,178(옛 크기 기준) 이 남아 있었다. 방송판이 전부 읽게 바꾼 뒤로는
   그 파일 하나가 방송을 통째로 옛 자리로 되돌릴 수 있다. 판 번호로 막는다."""
chk('방송판이 판 번호를 본다', "(ly.__v || 0) >= 2" in ov)
chk('편집기가 판 번호를 적는다', 'layout.__v = 2' in ad)
# 🔓 안전지대는 2026-09-15 에 걷어냈다. 사장님: "안전지대라는거 없애 자꾸 뜨네".
#    (그전 이력: 룰렛이 댓글창을 39px, 슬롯이 80px 침범해 폰에서 잘려 잠갔었고,
#     그 뒤 잠그는 대신 붙잡기로 바꿨었다. 이제 아무것도 안 막는다 — 잘리는지는 사람이 본다.)
#    여기서 지키는 것은 '없앤 상태가 양쪽에 똑같이 반영됐는가' 다.
#    ⚠️ 편집기만 풀면 안 된다. 방송판 applyLayout 의 fit() 이 세로를 115～954 로 도로
#       끌어당겨, 편집기에서 밖에 둔 것이 방송에서는 안으로 튀어 들어온다(또 어긋난다).
chk('편집기가 안 붙잡는다 (붙잡기가 통과다)',
    'function holdInSafe(' in ad and re.search(r'function holdInSafe\([^)]*\)\s*\{[^}]*?return \[x, y\];\s*\}', ad, re.S) is not None)
chk('빨간 딱지·구역 색칠이 없다',
    'out-of-safe' not in ad and 'zone-safe' not in ad and 'markOutOfSafe' not in ad)
chk("'안전지대 무시' 스위치도 없앴다 (늘 자유라 뜻이 없다)",
    'id="free-on"' not in ad and 'reholdAll' not in ad)
chk('편집기가 방송판에도 붙잡지 말라고 적는다 (저장 · 무대 양쪽)',
    ad.count('__free: true') + ad.count('__free = true') >= 2)
chk('방송판이 그 표시를 따른다', 'ly.__free' in ov)
# ⚠️ 화면 밖으로 빠뜨린 것을 되찾는 길은 남아 있어야 한다(이건 안전지대가 아니라 화면 전체 기준).
chk("'화면 안으로' 로 되찾을 수 있다", "tidy('inside')" in ad and '1080 - b.w' in ad)
# ⚠️ layout.json 이 git 에 있으면 자동배포(git reset --hard)가 사장님이 방금 잡은
#    자리를 통째로 되돌린다. 서버가 쓰는 파일이니 저장소가 들고 있으면 안 된다.
gi = io.open(os.path.join(PROJ, '.gitignore'), encoding='utf-8').read()
chk('layout.json 을 저장소가 안 들고 있다 (배포가 자리를 안 지운다)',
    'layout.json' in gi)

print()
print('=' * 74)
print('⑦ 위젯이 무대(canvas-board) 안에서 제 깊이로 닫히는가')
print('=' * 74)
# ⚠️ 2026-08-31 에 내가 이걸 깨뜨려 방송에 올렸다. 그림자 마크업을 바꿀 때
#   '여는 태그 + 아무거나(게으르게) + 첫 </div>' 로 잡는 정규식을 썼는데, 위젯 속이
#   여러 겹이면 그 첫 </div> 는 안쪽 것이다. 바깥 닫는 태그가 그대로 남아 위젯이
#   제 깊이보다 일찍 닫혔고, 뒤 일곱 개가 무대 밖 <body> 직속이 됐다.
#
#   무대는 0.43배로 줄여 보여주는데 튀어나간 것들은 안 줄어들어 화면을 덮었다.
#   그 밑의 위젯이 안 잡혔고, 창 크기에 따라 덮이는 자리가 달라져 '작게 하면 잡히고
#   크게 하면 안 잡히는' 것처럼 보였다. 시그뒤집기는 아예 못 잡았다.
_board = ad.index('<div class="canvas-board" id="canvas-board">')
_last = ad.rindex('<div class="widget" id="')
# ⚠️ 줄바꿈을 못 박으면 안 된다 — 맥에서는 admin.html 이 LF 라 못 찾고,
#    _end 가 파일 끝이 되어 마지막 위젯이 남은 </div> 를 다 삼킨다(home-race -4).
_nl = '\r\n' if '\r\n' in ad else '\n'
_after = ad.find('</div>' + _nl + ' ' * 12 + '</div>', _last)
_end = _after if _after > 0 else len(ad)
_starts = [m.start() for m in re.finditer(r'<div class="widget" id="', ad)
           if _board < m.start() < _end]
chk('무대 안에서 위젯을 찾았다', len(_starts) == 20, '%d개' % len(_starts))   # 🏺 모금함이 늘었다


def _depth(seg):
    d = 0
    # ⚠️ 닫는 태그를 먼저 본다 — 그래야 '<div[^>]*>' 가 여는 것만 잡는다.
    for m in re.finditer(r'<!--[\s\S]*?-->|</div>|<div[^>]*>', seg):
        t = m.group(0)
        if t.startswith('<!--'):
            continue
        d += -1 if t.startswith('</') else 1
    return d


_bad = []
for _i, _st in enumerate(_starts):
    _en = _starts[_i + 1] if _i + 1 < len(_starts) else _end
    _d = _depth(ad[_st:_en])
    if _d != 0:
        _bad.append('%s(%+d)' % (re.match(r'<div class="widget" id="([\w-]+)"', ad[_st:_st + 80]).group(1), _d))
chk('위젯마다 열고 닫은 수가 맞는다 (안 맞으면 뒤 위젯이 무대 밖으로 나간다)',
    not _bad, ' · '.join(_bad))

print()
print('=' * 74)
print('⑧ 겹쳐 있어도 손이 닿는가 · 무대 배율이 뒤집히지 않는가')
print('=' * 74)
# ⚠️ 고액후원 영상(1286×726)과 노래방(1006×569)이 캔버스 거의 전체를 덮는다.
#    '맨 위' 를 고르는 기본 규칙이면 어디를 눌러도 그 둘만 잡혀서, 사장님이
#    "아무것도 안 움직여져" 라고 했다. 겹친 것 중 작은 것부터 고르게 했다.
chk('겹친 위젯 중 작은 것을 고른다', 'function pickUnder(' in ad and 'elementsFromPoint' in ad)
chk('끌기가 그 고르기를 쓴다', 'pickUnder(_p.clientX, _p.clientY' in ad)
chk('같은 자리를 다시 누르면 다음 것으로 넘어간다',
    'list.indexOf(activeWidget)' in ad and '(i + 1) % list.length' in ad)
# ⚠️ 창이 좁으면 (폭-80) 이 음수라 배율이 음수가 된다. 무대가 뒤집혀 아주 작게
#    그려지고 클릭 자리가 통째로 어긋난다 — 실제로 scale(-0.0185) 를 봤다.
chk('무대 배율이 0 이하로 안 내려간다', 'Math.max(0.08, Math.min(availableW / 1080' in ad)

print()
print('=' * 74)
print('📏 손잡이가 샐어난 부분까지 덮는가')
print('=' * 74)
"""대표님: "게이지는 잘 움직이는데 옆에 숲자가 안따라가는다" (2026-09-16)
   목표 게이지의 금액 딱지는 position:absolute 로 막대 **왼쪽 107px 밖**에 떠 있다.
   offsetWidth 는 그런 자식을 안 센다 — 손잡이가 막대(30px)만 덮어 숲자를 못 잡았다."""
chk('실제 네모를 재는 함수가 있다', 'function stageBox(' in ad)
chk('손잡이 크기를 그걸로 정한다', 'const bx = stageBox(real, d);' in ad)
# ⚠️ 자리(style.left/top)는 곧 배치 값이다. 샐어난 만큼을 left 로 밀면 저장값이 동값이 된다.
chk('샐어난 만큼은 margin 으로만 밀린다', 'el.style.marginLeft = ml;' in ad and 'el.style.marginTop = mt;' in ad)
chk('자리 값은 안 건드린다', 'bx.dx' in ad and 'el.style.left = bx' not in ad)
# ⚠️ 화면에 고정된 팝업·안 보이는 것은 네모에서 빼야 한다.
chk('안 보이는 것은 뺀다', "c.position === 'fixed'" in ad and "c.visibility === 'hidden'" in ad)

print()
print('=' * 74)
print('👁️ 무대 강제표시가 깜빡이지 않는가')
print('=' * 74)
"""⚠️ 한 번 display:block 을 박아 두면 다음번엔 '이미 block 이네' 하고 규칙을 빼버려
   도로 숨고, 그 다음번엔 다시 박는다 — 0.7초마다 깜빡였다(목표 게이지 실측).
   재기 전에 규칙을 비워 항상 본모습을 기준으로 재게 한다."""
chk('재기 전에 규칙을 비운다', "if (st && st.textContent) { st.textContent = ''; void root.offsetWidth; }" in ad)

print()
print('=' * 74)
print('🔒 코드가 자리를 정하는 위젯을 정직하게 보여주는가')
print('=' * 74)
# ⚠️ 전광판은 머리 줄에 맞춰 설계돼 방송이 배치 파일을 안 읽는다(사장님 2026-09-09).
#    그런데 편집기는 끌리는 척하고 저장까지 돼서 "옷겼는데 왜 그대로지" 로 헤매게 됐다.
#    방송 동작은 그대로 두고 편집기에서 그 사실만 보여준다.
chk('방송판이 목록을 내놓는다', 'window.LAY_CODE_OWNED = LAY_CODE_OWNED;' in ov)
# ⚠️ applyLayout **밖**에 있어야 한다 — 안에 두면 한 번 그려진 뒤에야 생겨 표시가 안 붙는다.
chk('목록이 applyLayout 밖에 있다',
    ov.find('const LAY_CODE_OWNED =') < ov.find('function applyLayout('))
chk('편집기가 목록을 방송판에서 읽는다', 'stageWin().LAY_CODE_OWNED' in ad)
# ⚠️ 편집기에 같은 목록을 또 적으면 언젠가 한쪽만 고치고 어긋난다.
chk('편집기가 목록을 따로 적어 두지 않는다', "['notice']" not in ad)
chk('표시를 붙인다', "el.classList.toggle('code-owned'" in ad and '.widget.code-owned' in ad)
chk('끌기는 막되 고르기는 된다',
    "if (widgetEl.classList.contains('code-owned')) { selectWidget(widgetEl); return; }" in ad)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (ok, bad))
print('=' * 74)
sys.exit(1 if bad else 0)
