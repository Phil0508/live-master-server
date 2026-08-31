# -*- coding: utf-8 -*-
"""📱 시청자 폰에서 읽히는가.

왜 만들었나
  방송은 1080 폭인데 시청자 폰에서는 402px 로 줄어든다 — 2.687 배 축소.
  그래서 방송 27px 이라야 폰에서 겨우 10px 이다. 그 아래는 '있는지도 모르는' 글씨다.

  2026-08-31 에 전부 훑어보니 규칙 43개가 그 아래였다. 최악은 후원 순위판으로
  12~15px — 폰에서 4.5~5.6px 라 그냥 흐릿한 띠였다.

여기서 지키는 것
  · 고친 판들이 다시 작아지지 않는가        (바닥선 27px)
  · 아직 안 고친 것을 '통과' 로 숨기지 않는가 (빚 목록으로 드러낸다)
  · 글씨를 키우느라 칸이 자리를 넘지 않는가   (후원 순위판)

⚠️ CSS 를 읽어서 재는 것이라 '그 규칙이 실제로 걸리는가' 까지는 모른다.
   자리(픽셀) 는 화면에서 직접 재서 아래 숫자로 박아 뒀다.
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)

ov = io.open(os.path.join(PROJ, 'overlay.html'), 'rb').read().replace(b'\x00', b'').decode('utf-8')
css = '\n'.join(re.findall(r'<style[^>]*>(.*?)</style>', ov, re.S))

SHRINK = 2.687      # 1080 → 402
FLOOR = 27          # 방송 px. 폰에서 10.0px

ok = bad = 0


def chk(name, cond, extra=''):
    global ok, bad
    if cond:
        ok += 1
        print('  [OK] %s%s' % (name, ('  -- ' + str(extra)) if extra else ''))
    else:
        bad += 1
        print('  [!!] %s  -- %s' % (name, extra))


# 고쳐 놓은 판들 — 여기 글씨가 바닥선 아래로 내려가면 잡는다
FIXED = {
    '후원 순위': (r'\.dr-', r'donor-rank'),
    '시그 집계': (r'sig-tally',),
    '시그뒤집기': (r'\.sg-header-title', r'\.sg-timer'),
    '퇴근빵': (r'\.hr-goal-', r'\.home-race-'),
    '대결': (r'\.m-crown', r'\.m-card-', r'\.m-name-box', r'\.m-front-num', r'\.m-vs'),
    '계좌': (r'\.acc-',),
    '안내': (r'\.notice-ico',),
    '기타': (r'\.vip-badge-tag', r'\.donation-message', r'\.reaction-text-message',
             r'\.score-pop', r'\.op-card-label'),
}

# ⚠️ 아직 안 고친 것 — 엑셀판은 어떤 모양으로 갈지 안 정했다. 정하면 여기서 뺀다.
#    통과시키려고 예외를 두는 게 아니라, 남은 빚을 눈에 보이게 두는 것이다.
DEBT = (r'\.excel-', r'\.r-rank', r'\.r-name', r'\.r-score', r'\.r-contrib',
        r'\.row-bottom', r'\.b-name', r'\.b-score')


def rules():
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        sel, body = m.group(1).strip(), m.group(2)
        if sel.startswith('@') or not sel:
            continue
        fs = re.search(r'(?:^|[;\s])font-size:\s*(\d+(?:\.\d+)?)px', body)
        if fs:
            yield ' '.join(sel.split())[:70], float(fs.group(1))


ALL = list(rules())

print('=' * 74)
print('① 고친 판들 — 바닥선 %dpx (폰 %.1fpx) 아래로 안 내려가는가' % (FLOOR, FLOOR / SHRINK))
print('=' * 74)
for name, pats in FIXED.items():
    small = [(s, px) for s, px in ALL
             if any(re.search(p, s) for p in pats) and px < FLOOR]
    chk('%s 의 글씨가 전부 %dpx 이상' % (name, FLOOR), not small,
        ' · '.join('%s %.0fpx→폰%.1f' % (s[:40], px, px / SHRINK) for s, px in small[:4]))

print()
print('=' * 74)
print('② 아직 안 고친 빚 — 엑셀판')
print('=' * 74)
"""⚠️ 이건 '통과' 가 아니라 '아직 남았다' 는 표시다. 엑셀판 모양을 정하고 나서
   글씨를 키우면, 아래 개수가 0 이 되고 그때 이 구간을 지운다."""
debt = [(s, px) for s, px in ALL if any(re.search(p, s) for p in DEBT) and px < FLOOR]
print('  ※ 엑셀판에 아직 %d개 남아 있다 (모양을 정하고 한꺼번에 고친다)' % len(debt))
for s, px in sorted(debt, key=lambda r: r[1])[:12]:
    print('       %5.0fpx → 폰 %4.1fpx   %s' % (px, px / SHRINK, s))
chk('엑셀판 빚이 늘지는 않았다 (9개 이하)', len(debt) <= 9, '%d개' % len(debt))

print()
print('=' * 74)
print('③ 글씨를 키우느라 칸이 자리를 넘지 않는가 — 후원 순위판')
print('=' * 74)
"""화면에서 직접 잰 값 (2026-08-31):
     가로 658~1038  · 목표 막대는 1046 부터라 안 닿는다
     세로 387~904 (7줄) · 안전지대 아래끝 954 안"""
# ⚠️ box-sizing 이 없으면 380 이 '안쪽 폭' 이라 겉이 408 이 되고, 오른쪽 끝이
#    1066 이 되어 목표 막대(1046) 를 파고든다. 실제로 한 번 그랬다.
chk('폭을 겉폭으로 잡는다 (없으면 여백 때문에 막대를 파고든다)',
    re.search(r'\.donor-rank-board\s*\{[^}]*box-sizing:\s*border-box[^}]*width:\s*380px', css) is not None)
m = re.search(r'id="donor-rank-container"[^>]*left:\s*(\d+)px', ov)
chk('왼쪽 자리를 옮겼다 (766 이면 오른쪽이 화면 밖)', m and int(m.group(1)) == 658,
    m.group(1) + 'px' if m else '못 찾음')
chk('오른쪽 끝이 목표 막대(1046) 앞이다', m and int(m.group(1)) + 380 <= 1046,
    '%d' % (int(m.group(1)) + 380) if m else '')
# ⚠️ 줄 높이가 63px 이라 8줄이면 966 — 안전지대(954) 를 넘는다
chk('줄 상한을 7 로 조였다 (예전 20)',
    'Math.min(7, parseInt(d.donor_rank_limit)' in ov)
chk('상한을 우회해도 안 넘게 못을 박았다', 'max-height:466px; overflow:hidden' in ov)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (ok, bad))
print('=' * 74)
sys.exit(1 if bad else 0)
