# -*- coding: utf-8 -*-
"""🧱 방송판 짜임 — 여는 태그 · 닫는 태그가 맞는가 (2026-10-06 점검에서 찾은 사고)

무슨 일이 있었나
  모금함을 깃발로 바꾸면서(04ac1e1) 옛 병 모양의 닫는 </div> 하나가 남았다.
  그 하나 때문에 #master-container 가 일찍 닫혀서, 그 뒤의 주사위판 · 핀볼 · 순위판들이
  바깥 상자(#scale-wrapper)로 빠져나갔다. #master-container 는 그 자체가 한 층(쌓임 맥락)이라
  빠져나간 판(z-index 100000)이 **후원 팝업 · 시그니처 연출 · 계엄 화면보다 위에** 그려졌다.
  → 주사위 게임 중에 후원이 오면 팝업이 판 뒤에 가려진다. 화면 흔들기도 그 판들만 안 흔들린다.

여기서 지키는 것
  ① 방송판 · 조종실 · 폰 · 후원 콘솔 · 시그니처 화면 — 태그가 다 맞게 닫힌다
  ② 방송판의 판 · 위젯 · 팝업이 전부 #master-container 안에 있다
"""
import os
import sys
from html.parser import HTMLParser

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(HERE, '..'))
OK, BAD = [], []
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:300]) if detail else ''))


class Tree(HTMLParser):
    """태그를 쌓았다 내리며 (1) 안 맞는 닫힘 (2) id 마다 바로 위 id 를 적는다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # [(태그, id)]
        self.parent = {}         # id → 가장 가까운 위쪽 id
        self.bad = []

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        i = dict(attrs).get('id') or ''
        if i:
            up = [x for _, x in self.stack if x]
            self.parent[i] = up[-1] if up else None
        self.stack.append((tag, i))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.bad.append('닫는 </%s> 가 남는다 (줄 %d)' % (tag, self.getpos()[0]))
            return
        if self.stack[-1][0] != tag:
            self.bad.append('<%s> 자리에 </%s> (줄 %d)' % (self.stack[-1][0], tag, self.getpos()[0]))
            if any(t == tag for t, _ in self.stack):
                while self.stack and self.stack[-1][0] != tag:
                    self.stack.pop()
        if self.stack:
            self.stack.pop()


def parse(name):
    t = Tree()
    with open(os.path.join(ROOT, name), encoding='utf-8') as f:
        t.feed(f.read())
    t.close()
    return t


print('=' * 74)
print('① 태그가 맞게 닫히는가')
print('=' * 74)
# ⚠️ admin.html(편집기)은 예전부터 </div> 하나가 남는다 — 방송에 안 나가는 화면이라 여기선 안 본다
for page in ('overlay.html', 'controller.html', 'mobile.html', 'manual_send.html', 'signature_display.html'):
    if not os.path.exists(os.path.join(ROOT, page)):
        continue
    t = parse(page)
    chk('%s — 여닫는 태그가 맞다' % page, not t.bad and not [x for x in t.stack if x[0] not in ('html', 'body')], t.bad[:3])

print()
print('=' * 74)
print('② 방송판의 판 · 위젯 · 팝업이 #master-container 안에 있다')
print('=' * 74)
t = parse('overlay.html')
chk('#master-container 는 #scale-wrapper 안', t.parent.get('master-container') == 'scale-wrapper', t.parent.get('master-container'))
MUST = ('headrow', 'fundjar-container', 'quiz-container', 'pinball-container', 'dicegame-container',
        'dgscore-container', 'best-container', 'donor-rank-container', 'sig-tally-container', 'toon-popup-container')
for i in MUST:
    if i not in t.parent:
        chk('#%s 가 방송판에 있다' % i, False)
        continue
    # 바로 위가 아니어도 된다 — 올라가다 #master-container 를 만나면 안에 있는 것
    p, seen = t.parent.get(i), 0
    while p and p != 'master-container' and seen < 50:
        p, seen = t.parent.get(p), seen + 1
    chk('⭐ #%s 는 #master-container 안 (후원 팝업 · 연출보다 아래 층)' % i, p == 'master-container', t.parent.get(i))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
