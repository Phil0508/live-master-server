# -*- coding: utf-8 -*-
"""🛡️ 큰 금액은 한 번 더 확인(10-17 bigok).

- 서버: 기준 조각 bigok(비공개 · 기본 20만 원 · 20점) · 명령 bigok.set(검사 · 0 = 끔) · 방송판엔 안 간다.
- 조종실 순수 계산(묻나 · 제목 · [취소]면 안 감 · [주기]면 감)은 node 로 실물 js/bigok.js 를 부른다(js/bigok_check.mjs).
- 모든 사람 손 길이 ctx.run 한 곳을 지나는지 · 이미 물어본 길만 bigOk 인지는 파일 글자로 지킨다.
  화면(대기함 · 나눠 주기 · 폰 서랍 · AI 카드 · 손 점수 · Ctrl+K)은 헤드리스 크롬으로 따로 눌러 봤다(ARCHITECTURE '10-17 안전 꾸러미 — bigok').
돌리기: python -m unittest discover -s v2/tests -t .
"""
import os
import re
import shutil
import subprocess
import unittest

from v2.tests.test_flow import Base

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JS = os.path.join(ROOT, 'v2', 'web', 'controller', 'js')


def read(*p):
    with open(os.path.join(JS, *p), encoding='utf-8') as f:
        return f.read()


def slurp(path):
    with open(path, encoding='utf-8') as f:
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
        p = subprocess.run([node, os.path.join(ROOT, 'v2', 'tests', 'js', 'bigok_check.mjs')], capture_output=True, timeout=120)
        out = p.stdout.decode('utf-8', 'replace')
        self.assertEqual(p.returncode, 0, p.stderr.decode('utf-8', 'replace')[-1500:])
        self.assertEqual([ln for ln in out.splitlines() if ln.startswith('BAD ')], [])
        m = re.search(r'^DONE (\d+)$', out, re.M)
        self.assertTrue(m and int(m.group(1)) >= 38, out[-500:])


class Server(Base):
    def test_default_private(self):
        self.assertEqual(self.st()['bigok'], {'won': 200000, 'pts': 20})
        self.assertNotIn('bigok', self.st(auth=False))               # 방송판(로그인 없음)엔 안 간다

    def test_set_and_keep(self):
        c, r = self.cmd('bigok.set', won='300,000', pts=30)
        self.assertEqual((c, r['ok']), (200, True), r)
        self.assertEqual(r['bigok'], {'won': 300000, 'pts': 30})
        self.assertEqual(self.st()['bigok'], {'won': 300000, 'pts': 30})
        c, r = self.cmd('bigok.set', pts=0)                          # 하나만 — 다른 하나는 그대로
        self.assertTrue(r['ok'], r)
        self.assertEqual(self.st()['bigok'], {'won': 300000, 'pts': 0})
        c, r = self.cmd('session.end')
        self.assertEqual(self.st()['bigok'], {'won': 300000, 'pts': 0})  # 방송을 끝내도 기준은 남는다

    def test_reject(self):
        for bad in ({'won': -1}, {'won': 'abc'}, {'pts': True}, {'pts': 100001}, {'won': 100000001}, {}):
            c, r = self.cmd('bigok.set', **bad)
            self.assertFalse(r['ok'], bad)
        self.assertEqual(self.st()['bigok'], {'won': 200000, 'pts': 20})

    def test_needs_login(self):
        r = self.c.post('/api/cmd', json={'type': 'bigok.set', 'data': {'won': 0}})
        self.assertFalse(r.json().get('ok'))
        self.assertEqual(self.st()['bigok']['won'], 200000)

    def test_assign_not_blocked_by_server(self):
        """확인은 조종실 화면에서만 — 서버는 큰 후원도 그대로 받는다(자동 진행 · 옛 길이 막히지 않게)"""
        self.don('영원', 500000, 'toon_big1')
        pid = self.st()['pending'][0]['id']
        c, r = self.cmd('pending.assign', id=pid, name='하율')
        self.assertTrue(r['ok'], r)
        self.assertEqual(self.player('하율')['score'], 50)


class Wiring(unittest.TestCase):
    def test_main_wraps_run_once(self):
        m = code(read('main.js'))
        self.assertIn("import { guardRun, askBig } from './bigok.js'", m)
        self.assertRegex(m, r'ctx\.run = guardRun\(ctx\.run, \(\) => slices, needs => askBig\(ctx, needs\)')
        # 화면들을 붙이기 **전에** 감싼다(붙일 때 ctx.run 을 붙잡아 두는 화면이 있어도 감싼 것을 쓰게)
        self.assertLess(m.index('ctx.run = guardRun'), m.index('const views = {'))

    def test_score_paths_go_through_ctx_run(self):
        """점수가 들어가는 명령을 lm.cmd 로 바로 보내는 조종실 파일이 없다(모두 ctx.run → 거름망)"""
        for dp, _, fs in os.walk(JS):
            for f in fs:
                if not f.endswith('.js'):
                    continue
                src = code(slurp(os.path.join(dp, f)))
                self.assertNotRegex(src, r"lm\.cmd\(\s*'(score\.add|pending\.assign)'", f)
                self.assertNotRegex(src, r"/api/cmd", f)

    def test_bigok_only_after_asking(self):
        """{bigOk: true}(묻지 않고 보내기)는 이미 물어본 두 곳에서만"""
        users = []
        for dp, _, fs in os.walk(JS):
            for f in fs:
                if f.endswith('.js') and f != 'bigok.js' and 'bigOk: true' in code(slurp(os.path.join(dp, f))):
                    users.append(f)
        self.assertEqual(sorted(users), ['cards.js', 'pending.js'])
        p = code(read('pending.js'))
        self.assertLess(p.index('askBig(ctx, [big])'), p.index("ctx.run('pending.assign', data, { bigOk: true })"))
        self.assertLess(p.index('askBig(ctx, [big])'), p.index('busy.add(it.id)'))      # '보내는 중' 전에 묻는다
        c = code(read('panels', 'ai', 'cards.js'))
        self.assertLess(c.index('askBig(ctx, bigs)'), c.index('runCard(ctx, c, { bigOk: true })'))

    def test_client_autopilot_gone(self):
        # 10-22 🚗 조종실 오토파일럿은 ☕ 휴식(서버 자동 진행)으로 합쳐 뺐다 — 기계 쪽은 상한 이상을 이미 보류한다
        with self.assertRaises(OSError):
            read('panels', 'ai', 'autopilot.js')

    def test_settings_block(self):
        s = code(read('panels', 'settings_menu.js'))
        self.assertIn('mountBigokSettings(ctx)', s)
        b = code(read('bigok.js'))
        self.assertIn("ctx.run('bigok.set'", b)
        for tag in ('id: \'bigok-won\'', 'id: \'bigok-pts\'', 'id: \'bigok-save\''):
            self.assertIn(tag, b)

    def test_css_linked_thumb_size(self):
        with open(os.path.join(ROOT, 'v2', 'web', 'controller', 'index.html'), encoding='utf-8') as f:
            self.assertIn('href="./css/bigok.css"', f.read())
        with open(os.path.join(ROOT, 'v2', 'web', 'controller', 'css', 'bigok.css'), encoding='utf-8') as f:
            css = f.read()
        self.assertRegex(css, r'\.modal\.bigok \.modal-btns \.btn \{ min-height: 5[2-9]px')


if __name__ == '__main__':
    unittest.main()
