# -*- coding: utf-8 -*-
"""☕ 조종실 휴식 모드(10-17) — 계산(restcore.js)은 node 로, 이어 붙인 자리 · 소리 없음 · 실명 없음은 글자로 지킨다.

화면(가장자리 깜빡 · 카드 · 탭 제목 · [확인])은 헤드리스 크롬으로 따로 봤다(ARCHITECTURE '10-17 안전 꾸러미 — rest').
node 가 없는 PC 에서는 node 검사만 건너뛴다.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(ROOT, 'v2', 'web', 'controller')


def read(*p):
    with open(os.path.join(WEB, *p), encoding='utf-8') as f:
        return f.read()


def code(src):
    """설명(주석)을 뺀 코드만"""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?<![:\'"])//[^\n]*', '', src)


class Core(unittest.TestCase):
    def test_node(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node 가 없다')
        tmp = tempfile.mkdtemp(prefix='lm2restjs_')
        try:
            mod = os.path.join(tmp, 'restcore.mjs')
            shutil.copy(os.path.join(WEB, 'js', 'restcore.js'), mod)
            p = subprocess.run([node, os.path.join(ROOT, 'v2', 'tests', 'js', 'rest_core_test.mjs'), mod],
                               capture_output=True, timeout=60)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        out = p.stdout.decode('utf-8', 'replace')
        bad = [ln for ln in out.splitlines() if ln.startswith('BAD ')]
        self.assertEqual(p.returncode, 0, p.stderr.decode('utf-8', 'replace')[-1500:])
        self.assertEqual(bad, [])
        m = re.search(r'^DONE (\d+)$', out, re.M)
        self.assertTrue(m and int(m.group(1)) >= 30, out[-500:])

    def test_core_has_no_dom(self):
        only = code(read('js', 'restcore.js'))
        self.assertIsNone(re.search(r'\bdocument\.|\bwindow\.|^import ', only, re.M))

    def test_core_never_reads_holder_for_display(self):
        """holder(예금주 실명)는 '이름이 실명과 같은가' 비교에만 — 글자로 내보내지 않는다."""
        only = code(read('js', 'restcore.js'))
        self.assertEqual(only.count('it.holder'), 1, '실명은 비교 한 곳에서만 읽는다')
        self.assertNotIn('holder', code(read('js', 'restmode.js')))


class Wiring(unittest.TestCase):
    def test_no_sound(self):
        for p in [('js', 'restmode.js'), ('js', 'restcore.js')]:
            src = read(*p)
            for bad in ['Audio', '.play(', 'vibrate', 'Notification', 'speechSynthesis', 'beep']:
                self.assertNotIn(bad, code(src), '/'.join(p) + ' ' + bad)

    def test_button_in_control_row(self):
        src = read('js', 'restmode.js')
        self.assertIn("id: 'ctl-rest'", src)
        self.assertIn("'aria-pressed'", src)
        self.assertIn("querySelector('#hdr .cb')", src)          # 조종 줄(둘째 줄)
        self.assertIn('cb.insertBefore(btn, moreBtn)', src)                 # PC: 조종 줄 [더보기] 앞
        self.assertIn("document.querySelector('#ctl-more .cbs-panel')", src)  # 폰: 조종 줄 [⋯ 더보기] 판 안
        self.assertIn('readRest(store())', src)                   # 기기마다 기억
        self.assertNotIn('confirm(', code(src))
        self.assertNotIn('alert(', code(src).replace('emptyAlert(', '').replace('pushAlert(', ''))

    def test_signals_hooked(self):
        src = read('js', 'restmode.js')
        self.assertIn("import { onExt } from './bankext.js'", src)                       # 계좌 띠와 같은 신호
        self.assertIn("import { heldCards } from './panels/auto/holdband.js'", src)     # 보류 띠와 같은 고르기
        self.assertIn('st.on', src)
        main = read('js', 'main.js')
        self.assertIn("import { mountRest } from './restmode.js'", main)
        self.assertIn('rest.render(slices, view)', main)

    def test_css_linked_and_reduced_motion(self):
        idx = read('index.html')
        self.assertIn('./css/rest.css', idx)
        css = read('css', 'rest.css')
        self.assertIn('@keyframes rest-pulse', css)
        m = re.search(r'@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}', css, re.S)
        self.assertTrue(m, '움직임 줄이기 규칙')
        self.assertIn('animation: none', m.group(1))
        self.assertIn('12px', m.group(1))                          # 깜빡임 대신 굵은 테두리
        self.assertIn('pointer-events: none', css)                 # 가장자리가 누르기를 막지 않는다


if __name__ == '__main__':
    unittest.main()
