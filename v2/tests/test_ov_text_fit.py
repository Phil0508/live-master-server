# -*- coding: utf-8 -*-
"""✂️ 방송판 글자 자르기 (ovconn 10-17) — 이름이 '…' 없이 잘리던 것 · 시그 메시지가 낱말 중간에서 끊기던 것.

③ 점수판 이름 칸: .excel-row > div 가 flex 라 text-overflow: ellipsis 가 안 그려졌다 → 이름 칸만 block.
⑤ 시그 카드(방송판 · 출연진 전광판) 메시지: break-all → keep-all + overflow-wrap:anywhere, 3줄에서 … .
   후원 카드 메시지는 4줄. 출연진 전광판 사진은 창 높이 기준(55vh) — 1280x720 에서 아래가 잘리지 않게.
   줄 제한(-webkit-line-clamp)은 높이만 줄이고 다음 줄도 그린다 → 위아래 padding 이 있으면 다음 줄 윗동이 비친다.
   그래서 위아래 여백은 투명 테두리로(overflow 는 padding 바깥을 자른다). 출연진 전광판은 글자 빛(18px)이 잘리지 않게
   3줄이 넘을 때만 .clamp 를 붙인다(sigdisp.js fitMsg).
화면 실측은 사진으로 했고, 여기선 규칙이 다시 빠지지 않게 CSS 글을 본다.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OV = os.path.join(ROOT, 'v2', 'web', 'overlay')


def _read(*p):
    with open(os.path.join(OV, *p), encoding='utf-8') as f:
        return f.read()


def rule(css, selector):
    """선택자가 정확히 그것인 규칙 몸통(여러 개면 이어 붙임) — 주석은 뺀다"""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        sels = [s.strip() for s in m.group(1).split(',')]
        if selector in sels:
            out.append(m.group(2))
    return ' '.join(out)


def decls(body):
    d = {}
    for part in body.split(';'):
        if ':' in part:
            k, v = part.split(':', 1)
            d[k.strip()] = v.strip()
    return d


class TextFit(unittest.TestCase):
    def setUp(self):
        self.ov = _read('overlay.css')
        self.sig = _read('css', 'sigfx.css')

    def test_rank_name_block_for_ellipsis(self):
        d = decls(rule(self.ov, '.excel-row > .r-name'))
        self.assertEqual(d.get('display'), 'block')          # .excel-row > div(flex) 보다 셀 것(선택자 무게 0,2,0)
        n = decls(rule(self.ov, '.r-name'))
        self.assertEqual(n.get('text-overflow'), 'ellipsis')
        self.assertEqual(n.get('white-space'), 'nowrap')
        self.assertEqual(n.get('overflow'), 'hidden')
        self.assertEqual(decls(rule(self.ov, '.excel-row > div')).get('min-width'), '0')   # 칸이 줄어들 수 있어야 … 가 나온다
        js = _read('widgets', 'ranking.js')
        self.assertIn('<div class="r-name">', js)

    def _clamped(self, d, lines):
        self.assertEqual(d.get('word-break'), 'keep-all')
        self.assertEqual(d.get('overflow-wrap'), 'anywhere')
        self.assertEqual(d.get('display'), '-webkit-box')
        self.assertEqual(d.get('-webkit-box-orient'), 'vertical')
        self.assertEqual(d.get('-webkit-line-clamp'), str(lines))
        self.assertEqual(d.get('overflow'), 'hidden')

    def _no_vpad(self, d):
        self.assertTrue(d.get('padding', '').startswith('0 '), d.get('padding'))      # 위아래 padding 0
        self.assertIn('transparent', d.get('border', ''))                              # 여백은 투명 테두리

    def test_sig_card_message(self):
        d = decls(rule(self.ov, '.reaction-text-message'))
        self.assertNotIn('break-all', rule(self.ov, '.reaction-text-message'))
        self._clamped(d, 3)
        self._no_vpad(d)
        self.assertEqual(d.get('background-origin'), 'border-box')        # 유리 그러데이션이 테두리 밑에서 되풀이되지 않게
        self.assertIn('var(--glass-border)', d.get('box-shadow', ''))      # 테두리 선은 고리로
        self.assertEqual(decls(rule(self.ov, '.reaction-text-message:empty')).get('display'), 'none')
        self.assertEqual(decls(rule(self.ov, '.reaction-text-donator')).get('overflow-wrap'), 'anywhere')

    def test_donation_message_lines(self):
        d = decls(rule(self.ov, '.donation-message'))
        self._clamped(d, 4)
        self._no_vpad(d)

    def test_sigdisp(self):
        self.assertNotIn('break-all', self.sig)
        base = decls(rule(self.sig, '.sigdisp-msg'))
        self.assertEqual(base.get('word-break'), 'keep-all')
        self.assertEqual(base.get('overflow-wrap'), 'anywhere')
        self.assertNotIn('overflow', base)                                  # 평소엔 안 자른다(글자 빛)
        self._clamped(dict(base, **decls(rule(self.sig, '.sigdisp-msg.clamp'))), 3)
        self.assertEqual(decls(rule(self.sig, '.sigdisp-donator')).get('overflow-wrap'), 'anywhere')
        self.assertEqual(decls(rule(self.sig, '.sigdisp-img')).get('max-height'), '55vh')
        # JS 가 display:block 을 박으면 3줄 제한(-webkit-box)이 풀린다
        js = _read('widgets', 'sigfx', 'sigdisp.js')
        self.assertNotIn("? 'block' : 'none'", js)
        self.assertEqual(js.count('fitMsg();'), 2)                          # 메시지를 바꾸는 두 곳 모두 다시 잰다
        self.assertIn("classList.add('clamp')", js)

    def test_no_theme_overrides_display(self):
        th = re.sub(r'/\*.*?\*/', '', _read('css', 'themes.css'), flags=re.S)
        for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', th):
            if re.search(r'\.(r-name|reaction-text-message|donation-message|sigdisp-msg)\b', m.group(1)):
                self.assertNotIn('display', decls(m.group(2)), m.group(1).strip())


if __name__ == '__main__':
    unittest.main()
