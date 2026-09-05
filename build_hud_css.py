# -*- coding: utf-8 -*-
"""🧱 방송판 HUD 의 생김새를 한 곳으로 모은다 — hud.css 를 만들고 편집기에 끼워 넣는다.

■ 왜 만들었나
  편집기(admin.html)는 방송판(overlay.html)의 CSS 를 '손으로 베껴' 갖고 있었다.
  그래서 방송판을 고칠 때마다 두 곳을 같이 고쳐야 했고, 안 고치면 편집기가
  거짓말을 한다. 2026-08-31 에 재 보니 같은 이름의 규칙 18개 중 56곳이 달랐고,
  엑셀판이 편집기에서는 698×130, 실제 방송에서는 990×399 였다.

■ 원본은 overlay.html 이다 (hud.css 가 아니라)
  ⚠️ 방송판을 쪼개서 외부 CSS 를 불러쓰게 만들면, OBS 가 그 파일을 못 읽는 순간
     방송이 민무늬가 된다. 그래서 방송판은 한 글자도 안 건드린다.
     hud.css 는 방송판에서 '뽑아낸 사본' 이고, 그것을 편집기에 끼워 넣는다.
     고칠 곳은 언제나 overlay.html 한 곳뿐이다.

■ 무엇을 뽑나
  편집기가 그림자로 흉내내는 HUD 요소의 규칙만 뽑는다 (아래 PREFIX).
  편집기 자체 UI 는 클래스 이름이 겹치지 않으므로 섞이지 않는다.
  ⚠️ :root 토큰은 안 뽑는다 — 편집기 자체 UI 도 :root 를 쓰기 때문에 덮어쓰면
     편집기 색이 같이 물든다. 대신 tests/editor_sync_test.py 가 '편집기 토큰이
     방송판과 같은 값인가' 를 따로 검사한다.

■ 쓰는 법
    python build_hud_css.py          만들고 끼워 넣는다
    python build_hud_css.py --check  다르면 1 로 끝난다 (검사가 쓴다)
"""
import io
import os
import re
import sys

# ⚠️ 윈도우 콘솔 기본이 cp949 라 '—' 하나에 스크립트가 죽는다. 파일은 이미 쓰인
#    뒤라 더 헷갈린다 — 먼저 UTF-8 로 돌려놓는다.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.')))
OVERLAY = ROOT + r'\overlay.html'
ADMIN = ROOT + r'\admin.html'
HUD = ROOT + r'\hud.css'

BEGIN = '/* ===== hud.css 시작 — build_hud_css.py 가 넣는다. 손으로 고치지 말 것 ===== */'
END = '/* ===== hud.css 끝 ===== */'

# 편집기가 흉내내는 HUD 요소들. 여기 없는 것은 편집기에 안 들어간다.
PREFIX = (
    'excel-', 'r-rank', 'r-name', 'r-score', 'r-contrib', 'row-bottom', 'b-name', 'b-score',
    'rank-1', 'rank-2', 'rank-3',
    'acc-', 'notice', 'goal-rail', 'ticker-',
    'dr-', 'donor-rank', 'sig-tally',
    'dg-', 'm-', 'hr-', 'home-race', 'sg-',
    'center-popup', 'takeover-popup', 'vip-badge',
    'slot-',
)


def hud_rule(sel):
    """이 선택자가 HUD 요소의 것인가."""
    # 한 규칙에 선택자가 여럿일 수 있다 (a, b { }). 하나라도 HUD 면 가져온다.
    for one in sel.split(','):
        for cls in re.findall(r'[.#]([\w-]+)', one):
            if any(cls.startswith(p) for p in PREFIX):
                return True
    return False


def extract(src):
    """overlay.html 의 <style> 에서 HUD 규칙만 순서대로 뽑는다.

    ⚠️ CSS 는 순서가 곧 우선순위다. 뽑을 때 순서를 흐트러뜨리면 나중에 덮어쓰는
       규칙(.r-score 를 두 번 적어 두 번째가 이기는 식)이 뒤집힌다. 그래서
       원문에 나온 차례 그대로 이어 붙인다.
    """
    css = '\n'.join(re.findall(r'<style[^>]*>(.*?)</style>', src, re.S))
    out = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        sel = m.group(1)
        # 앞에 붙은 주석은 떼고 선택자만 본다
        clean = re.sub(r'/\*.*?\*/', ' ', sel, flags=re.S).strip()
        if not clean or clean.startswith('@'):
            continue
        if hud_rule(clean):
            body = ' '.join(m.group(2).split())
            out.append('%s { %s }' % (' '.join(clean.split()), body))
    return out


def build():
    ov = io.open(OVERLAY, 'rb').read().replace(b'\x00', b'').decode('utf-8')
    rules = extract(ov)
    head = (
        '/* 🧱 방송판 HUD 의 생김새 — overlay.html 에서 뽑아낸 사본이다.\n'
        '   ⚠️ 이 파일을 고치지 말 것. 원본은 overlay.html 이고, 고친 뒤\n'
        '      python build_hud_css.py 를 돌리면 여기와 admin.html 이 따라온다.\n'
        '   ⚠️ 편집기가 방송판을 손으로 베끼던 것을 없애려고 만들었다 —\n'
        '      2026-08-31 에 둘이 56곳 어긋나 있었고 엑셀판 폭이 292px 달랐다. */\n'
    )
    return head + '\n'.join(rules) + '\n'


def inject(css_text):
    """편집기 안의 표시 구간을 새 내용으로 갈아끼운다."""
    ad = io.open(ADMIN, 'rb').read().decode('utf-8')
    # ⚠️ 줄바꿈을 못 박으면 안 된다. 저장소에 담긴 바이트는 LF 인데, 윈도우는 받을 때
    #    CRLF 로 바뀌고 맥(core.autocrlf input)은 LF 그대로 놓인다. CRLF 를 박아 뒀더니
    #    맥에서 --check 가 '통째로 어긋났다' 고 했다 — 이 파일이 쓰는 줄바꿈을 따라간다.
    nl = '\r\n' if '\r\n' in ad else '\n'
    block = (BEGIN + '\n' + css_text + END).replace('\n', nl)
    if BEGIN in ad:
        a = ad.index(BEGIN)
        b = ad.index(END) + len(END)
        return ad[:a] + block + ad[b:], ad
    raise SystemExit('admin.html 에 표시 구간이 없다. 먼저 %s / %s 를 넣어라.' % (BEGIN, END))


def main():
    check = '--check' in sys.argv
    css_text = build()

    old_hud = ''
    try:
        old_hud = io.open(HUD, encoding='utf-8', newline='').read()
    except FileNotFoundError:
        pass
    new_admin, old_admin = inject(css_text)

    if check:
        bad = []
        # ⚠️ 줄끝 차이로는 트집 잡지 않는다. 여기서 보려는 건 '방송판을 고치고
        #    build 를 안 돌렸나' 이지, 받는 쪽 줄바꿈 설정이 아니다.
        if old_hud.replace('\r\n', '\n') != css_text:
            bad.append('hud.css')
        if new_admin != old_admin:
            bad.append('admin.html')
        if bad:
            print('[!!] %s 가 overlay.html 과 어긋났다. python build_hud_css.py 를 돌려라.'
                  % ' · '.join(bad))
            return 1
        print('[OK] hud.css · admin.html 이 overlay.html 과 같다 (규칙 %d개)'
              % css_text.count('{'))
        return 0

    io.open(HUD, 'w', encoding='utf-8', newline='\n').write(css_text)
    out = new_admin.encode('utf-8')
    # ⚠️ 줄끝이 섞이면 다음 사람이 통째 diff 를 보게 된다. 원래 쓰던 줄바꿈으로만 되게 한다.
    if b'\r\n' in out:
        assert b'\n' not in out.replace(b'\r\n', b''), 'CRLF 파일에 LF 가 섞였다'
    else:
        assert b'\r' not in out, 'LF 파일에 CR 이 섞였다'
    io.open(ADMIN, 'wb').write(out)
    print('hud.css 를 만들고 admin.html 에 끼워 넣었다 — 규칙 %d개' % css_text.count('{'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
