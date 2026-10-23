# -*- coding: utf-8 -*-
"""◀ 뒤로가기(10-24 대표님 '사이트에서 뒤로가기 누르면 자꾸 나가지더라') — backnav.js 가 조종실 · 후원 콘솔에 붙어 있고,
닫을 때 누르는 단추(선택자)가 실제 화면 파일에 아직 있는지(이름이 바뀌면 뒤로가기가 그 창을 못 닫는다)."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JS = os.path.join(ROOT, 'v2', 'web', 'controller', 'js')


def src(*p):
    with open(os.path.join(JS, *p), encoding='utf-8') as f:
        return f.read()


class BackNav(unittest.TestCase):
    def test_wired(self):
        self.assertIn("from './backnav.js'", src('main.js'))
        self.assertIn('initBack(', src('main.js'))
        self.assertIn("name: '조종실'", src('main.js'))
        self.assertIn('tabChanged(active, id)', src('tabs.js'))
        self.assertIn('back: id => open(id, false)', src('tabs.js'))
        c = src('consolepage.js')
        self.assertIn('initBack(', c)
        self.assertIn('tabChanged(active, id)', c)

    def test_close_buttons_exist(self):
        """뒤로가기가 대신 누르는 [취소] · [닫기] 단추 — 그 화면 파일에 그 이름이 있어야 한다."""
        need = {
            'modal-wrap': 'util.js', 'modal-btns': 'util.js',
            'dk-wrap': 'donorcard.js', 'dk-x': 'donorcard.js',
            'sg-sheet-foot': os.path.join('panels', 'sig', 'form.js'),
            'cmdk-close': 'cmdk.js',
            'ctl-more': 'header.js', 'cbs-foot': 'header.js',
            'lm:drawer': 'drawer.js',
        }
        b = src('backnav.js')
        for name, f in need.items():
            self.assertIn(name, b, name)
            self.assertIn(name, src(f), '%s 가 %s 에 없어요' % (name, f))
        # 단추 차례 — 확인 상자의 첫 단추는 [취소], 시그니처 고치기 아래 줄 첫 단추는 [닫기]
        self.assertRegex(src('util.js'), r"modal-btns' \}, noBtn, okBtn")
        self.assertRegex(src('panels', 'sig', 'form.js'), r"sg-sheet-foot' \}, cancelBtn, saveBtn")
        with open(os.path.join(ROOT, 'v2', 'web', 'controller', 'index.html'), encoding='utf-8') as f:
            self.assertIn('id="drawer"', f.read())                                  # 폰 서랍 — #drawer.open 을 본다

    def test_only_with_person(self):
        """크롬이 건너뛰지 않게 사람이 누른 직후에만 칸을 쌓는다."""
        b = src('backnav.js')
        self.assertIn('navigator.userActivation', b)
        self.assertTrue(re.search(r'function arm\(\)[\s\S]*?activated\(\)', b))
