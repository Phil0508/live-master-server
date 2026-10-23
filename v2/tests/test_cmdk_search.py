# -*- coding: utf-8 -*-
"""⌨️ Ctrl+K 찾기 — 대표님 10-24 "컨트롤 케이로 검색기능에 모든걸 검색할 수 있게".

- 맞추기 · 줄 세우기 · 색인은 node 로 실물 파일을 그대로 부른다(v2/tests/js/cmdk_check.mjs).
  초성 · 치는 중인 글자 · 금액 꼴 · 묶음 머리 · 명령은 예전 그대로('룰렛' → 탭, '스킵' → 바로 하기) · 6,000명 빠르기
  · 색인(cmdkindex.js)의 찾을 글자가 실제 코드에 있는지 · 블록 제목이 다 색인에 있는지.
- 여기서는 이어 붙인 자리(🔍 단추 → 'lm:cmdk' → 상자) · 소리 없음 · 바깥 글자 textContent · 순수 파일은 화면을 안 만지는지를 파일 글자로 지킨다.
돌리기: python -m unittest discover -s v2/tests -t .
"""
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CTL = os.path.join(ROOT, 'v2', 'web', 'controller')


def read(*p):
    with open(os.path.join(CTL, *p), encoding='utf-8') as f:
        return f.read()


def code(src):
    """설명(주석)을 뺀 코드만"""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?<![:\'"])//[^\n]*', '', src)


class PureJs(unittest.TestCase):
    def test_node(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node 가 없다')
        p = subprocess.run([node, os.path.join(ROOT, 'v2', 'tests', 'js', 'cmdk_check.mjs')], capture_output=True, timeout=120)
        out = p.stdout.decode('utf-8', 'replace')
        self.assertEqual(p.returncode, 0, p.stderr.decode('utf-8', 'replace')[-1500:])
        self.assertEqual([ln for ln in out.splitlines() if ln.startswith('BAD ')], [])
        m = re.search(r'^DONE (\d+)$', out, re.M)
        self.assertTrue(m and int(m.group(1)) >= 60, out[-500:])


class Wiring(unittest.TestCase):
    def test_find_button_opens_box(self):
        hdr = read('js', 'header.js')
        self.assertIn("document.dispatchEvent(new CustomEvent('lm:cmdk'))", hdr)       # 🔍 단추 → 상자(폰은 단축키가 없다)
        self.assertIn("class: 'btn sm cb-find'", hdr)
        self.assertIn('findBtn, moreBtn);', hdr)                                       # 폰에서도 조종 줄(⋯ 판으로 안 옮긴다)
        self.assertNotIn('sheetMisc.append(findBtn', hdr)
        cmdk = read('js', 'cmdk.js')
        self.assertIn("document.addEventListener('lm:cmdk', () => open());", cmdk)
        self.assertIn("if (!authed() || isOpen()) return;", cmdk)                      # 로그인 전에는 안 열린다
        self.assertIn("search:", read('js', 'icons.js'))

    def test_settings_menu_shares_lists(self):
        menu = read('js', 'panels', 'settings_menu.js')
        for name in ('export const GROUPS = [', 'export const DESC = {', 'export const ACTS = {'):
            self.assertIn(name, menu)
        cmdk = read('js', 'cmdk.js')
        self.assertIn("import { GROUPS as TILE_GROUPS, DESC as TILE_DESC, ACTS } from './panels/settings_menu.js';", cmdk)

    def test_command_rules_stay_in_one_place(self):
        cmds = read('js', 'panels', 'ai', 'commands.js')
        self.assertIn('export function isCommandForm(q, names)', cmds)
        for re_name in ('SLOT_RE', 'ROUL_RE', 'MATCH_RE', 'SKIP_RE', 'ALLCLEAR_RE', 'CLIP_RE', 'CUE_RE'):
            self.assertEqual(code(cmds).count(re_name), 3, re_name)      # 정의 1 · isCommandForm 1 · runCommand 1
        self.assertNotIn('건너뛰|스킵', read('js', 'cmdk.js'))           # 말 모양은 cmdk 에 베끼지 않는다

    def test_pure_files_have_no_dom(self):
        for p in [('js', 'cmdkcore.js'), ('js', 'cmdkindex.js')]:
            only = code(read(*p))
            for bad in ['document', 'window', 'innerHTML', 'fetch(', 'localStorage']:
                self.assertNotIn(bad, only, '/'.join(p) + ' ' + bad)

    def test_no_sound_no_inner_html(self):
        for p in [('js', 'cmdk.js'), ('js', 'cmdkcore.js'), ('js', 'cmdkindex.js'), ('js', 'header.js')]:
            only = code(read(*p))
            for bad in ['new Audio', 'AudioContext', '.play()', 'navigator.vibrate', 'Notification', 'innerHTML', 'insertAdjacentHTML']:
                self.assertNotIn(bad, only, '/'.join(p) + ' ' + bad)

    def test_css(self):
        css = read('css', 'tools_records.css')
        for sel in ('.cmdk-gh', '.cmdk-sub', '.cmdk-flash', '@keyframes cmdk-flash', '#hdr .cb .cb-find'):
            self.assertIn(sel, css)
        # 상자는 확인 상자(.modal-wrap 100) 아래 — '올클리어' 확인을 가리지 않게(test_w2feat 와 같은 약속)
        self.assertLess(int(re.search(r'\.cmdk\s*\{[^}]*z-index:\s*(\d+)', css).group(1)), 100)


if __name__ == '__main__':
    unittest.main()
