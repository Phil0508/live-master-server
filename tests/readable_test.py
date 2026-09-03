# -*- coding: utf-8 -*-
"""📱 시청자 폰에서 읽히는가.

왜 만들었나
  방송은 1080 폭인데 시청자 폰에서는 402px 로 줄어든다 — 2.687 배 축소.
  그래서 방송 27px 이라야 폰에서 겨우 10px 이다. 그 아래는 '있는지도 모르는' 글씨다.

  2026-08-31 에 전부 훑어보니 규칙 43개가 그 아래였다. 최악은 후원 순위판으로
  12~15px — 폰에서 4.5~5.6px 라 그냥 흐릿한 띠였다.

여기서 지키는 것
  · 고친 판들이 다시 작아지지 않는가        (바닥선 27px)
  · 엑셀판이 '왜 그렇게 했는지' 가 살아 있는가 (숫자만 키우고 되돌리면 소용없다)
  · 글씨를 키우느라 칸이 자리를 넘지 않는가   (후원 순위판)

⚠️ CSS 를 읽어서 재는 것이라 '그 규칙이 실제로 걸리는가' 까지는 모른다.
   자리(픽셀) 는 화면에서 직접 재서 아래 숫자로 박아 뒀다.
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
# ⚠️ runall 은 검사를 스크래치패드로 복사해서 돌린다. 거기서는 부모 폴더에
#    overlay.html 이 없다 — 처음에 그것 때문에 이 검사만 통째로 터졌다.
#    위로 올라가며 찾고, 못 찾으면 저장소 자리를 쓴다.
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
    # 2026-08-31 안 A 적용 — 이름·점수 31px, 순위·기여도·머리 27px
    '엑셀판': (r'\.excel-', r'\.r-rank', r'\.r-name', r'\.r-score', r'\.r-contrib',
             r'\.row-bottom', r'\.b-name', r'\.b-score'),
    # 2026-08-31 유리 카드로 — 당첨 글씨가 23px(폰 8.6px)이라 못 읽었다
    '슬롯': (r'\.slot-ttl', r'\.slot-win'),
}


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
print('② 엑셀판 — 안 A 가 들어갔는가')
print('=' * 74)
"""⚠️ 글씨 크기는 ① 이 이미 지킨다. 여기서는 '왜 그렇게 했는지' 가 살아 있는지 본다.
   숫자만 키우고 아래 넷을 되돌리면 읽히기는 해도 예전 문제가 그대로 남는다."""
# ⚠️ 점수와 기여도가 '823,00025.6%' 로 붙어 읽히던 것 — 오른쪽 정렬로 자릿수를 맞춘다
chk('점수·기여도를 오른쪽으로 붙인다 (자릿수가 맞아야 비교된다)',
    '.excel-row > div:nth-child(3), .excel-row > div:nth-child(4) { justify-content: flex-end; }' in css)
# ⚠️ 한 번 읽고 마는 머리줄이 가장 밝은 금색 알약이라 위계가 뒤집혀 있었다
chk('머리줄의 금색 알약을 걷어냈다 (밑줄만 남긴다)',
    re.search(r'\.excel-header\s*\{[^}]*background:\s*linear-gradient', css) is None)
# ⚠️ 1등만 배경, 2·3등은 왼쪽 선 — 규칙이 제각각이었다
chk('순위를 1·2·3 같은 규칙(색 배지)으로 통일했다',
    all(('.rank-%d .r-rank { background:' % k) in css for k in (1, 2, 3)))
# ⚠️ 기여도가 점수보다 강조(금색+글로우)돼 있었다
chk('기여도에서 글로우를 뺐다 (점수가 주인공)',
    re.search(r'\.r-contrib\s*\{[^}]*text-shadow', css) is None)
# ⚠️ 번외 점수판이 같은 .excel-row 를 쓰면서 인라인 style 로 색만 덮는다
chk('칸 개수·순서가 그대로다 (번외 점수판이 같은 줄을 쓴다)',
    css.count('grid-template-columns: 60px 1fr 148px 92px') == 2)

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
print('④ 퇴근빵 — 글씨를 키운 만큼 칸도 넓어졌는가')
print('=' * 74)
# ⚠️ 글씨만 27~32px 로 키우고 칸은 540px 그대로 뒀더니, 숫자칸 96px 에
#    '1,234,000'(161px) 이 안 들어가 65px 잘렸다. 엑셀판이 698→990 으로
#    넓어져야 했던 것과 같은 병이다. 화면에서 직접 잰 값으로 못 박는다.
_hr = re.search(r'\.home-race-box \{[^}]*width:\s*(\d+)px', css, re.S)
chk('판이 900px 이다 (540 이면 숫자가 잘린다)', _hr and int(_hr.group(1)) >= 900,
    (_hr.group(1) + 'px') if _hr else '못 찾음')
_nm = re.search(r'\.home-race-name \{[^}]*width:\s*(\d+)px', css, re.S)
chk('이름칸이 200px 이다 (120 이면 네 글자에서 꽉 찬다)', _nm and int(_nm.group(1)) >= 200,
    (_nm.group(1) + 'px') if _nm else '못 찾음')
_nu = re.search(r'\.home-race-nums \{[^}]*width:\s*(\d+)px', css, re.S)
chk("숫자칸이 196px 이다 ('1,234,000' 이 161px 다)", _nu and int(_nu.group(1)) >= 176,
    (_nu.group(1) + 'px') if _nu else '못 찾음')
chk('숫자를 오른쪽으로 맞춘다 (자릿수가 맞아야 비교된다)',
    re.search(r'\.home-race-nums \{[^}]*text-align:\s*right', css, re.S) is not None)

print()
print('=' * 74)
print('⑤ 슬롯머신 — 우리 테마(둥근 유리 카드)인가')
print('=' * 74)
# ⚠️ 슬롯만 비스듬히 잘린 각진 상자였다. 엑셀판·계좌·후원순위는 전부 둥근 유리
#    카드라 슬롯 혼자 다른 물건처럼 보였다. 사장님이 안 A(유리 카드)를 골랐다.
chk('유리 카드를 두른다 (엑셀판과 같은 언어)',
    re.search(r'\.slot-card \{[^}]*background: var\(--glass-bg\)', css, re.S) is not None)
chk('모서리를 같은 값으로 둥글린다',
    re.search(r'\.slot-card \{[^}]*border-radius: var\(--glass-radius\)', css, re.S) is not None)
chk('위쪽 하이라이트 한 줄이 있다', '.slot-card::before' in css)
# 머리글은 한 번 읽고 마는 것 — 금색 알약을 걷어내고 밑줄만 (엑셀판과 같은 규칙)
chk('머리글의 금색 알약을 걷어냈다',
    re.search(r'\.slot-ttl \{[^}]*background:', css, re.S) is None)
chk('금색은 밑줄로만 남긴다',
    re.search(r'\.slot-ttl \{[^}]*border-bottom: 2px solid rgba\(246,196,83', css, re.S) is not None)
# ⚠️ 비스듬히 자르던 clip-path 가 남아 있으면 되돌아간 것이다
chk('릴을 비스듬히 자르지 않는다', 'clip-path: polygon(7px 0' not in ov)
chk('릴을 둥글린다', re.search(r'\.slot-reel \{[^}]*border-radius: 16px', css, re.S) is not None)
# ⚠️ 릴 창 170×120 은 릴이 멈추는 좌표(cardHeight = 120)와 묶여 있다.
#    바꾸면 당첨 칸이 어긋난다 — 모양을 바꾸면서도 이 숫자는 지켜야 한다.
chk('릴 창이 170×120 그대로다 (멈추는 좌표와 묶여 있다)',
    re.search(r'\.slot-reel \{[^}]*width: 170px; height: 120px', css, re.S) is not None)
chk('멈추는 좌표도 그대로다', 'const cardHeight = 120;' in ov)
# 겉 상자는 편집기 그림자·검사가 아는 크기다
chk('겉 상자 660×360 은 안 건드렸다', 'width: 660px; height: 360px' in ov)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (ok, bad))
print('=' * 74)
sys.exit(1 if bad else 0)
