# -*- coding: utf-8 -*-
"""🏦 조종실 계좌 입금 화면 — 순수 계산(bankcore.js)은 node 로, 이어 붙인 자리는 글자로 확인한다.

옛 tests/bank_inbox_test.py 의 화면 글자 검사 자리를 v2 로 옮겼다:
  · [채우기] 뒤 '장부 기록' 체크를 원래대로(옛 50878d1) — makePick 을 node 로 직접 돌린다
  · 채운 송출은 tx_id manual_bank_<입금번호> · 이름을 비우면 '익명' · 끝나면 그 입금에 '씀' 표시
  · 추천 칸은 스스로 송출하지 않는다(/api/donation 을 안 부른다)
  · 조종실 계좌 알림은 화면만 — 소리를 안 낸다(대표님 10-16)
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
    with open(os.path.join(*p), encoding='utf-8') as f:
        return f.read()


def code(src):
    """설명(주석)을 뺀 코드만 — '이 파일은 /api/donation 을 부르지 않는다' 같은 설명 글이 검사에 걸리지 않게."""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?<![:\'"])//[^\n]*', '', src)


class Core(unittest.TestCase):
    def test_node(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node 가 없다')
        tmp = tempfile.mkdtemp(prefix='lm2bankjs_')
        try:
            mod = os.path.join(tmp, 'bankcore.mjs')            # .mjs 로 복사 — 어느 node 판에서나 ES 모듈로 읽게
            shutil.copy(os.path.join(WEB, 'js', 'bankcore.js'), mod)
            p = subprocess.run([node, os.path.join(ROOT, 'v2', 'tests', 'js', 'bank_core_test.mjs'), mod],
                               capture_output=True, timeout=60)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        out = p.stdout.decode('utf-8', 'replace')
        bad = [ln for ln in out.splitlines() if ln.startswith('BAD ')]
        self.assertEqual(p.returncode, 0, p.stderr.decode('utf-8', 'replace')[-1500:])
        self.assertEqual(bad, [])
        m = re.search(r'^DONE (\d+)$', out, re.M)
        self.assertTrue(m and int(m.group(1)) >= 40, out[-500:])

    def test_core_has_no_dom(self):
        """bankcore.js 는 화면을 만지지 않는다 — node 로 그대로 부르기 위해."""
        only = code(read(WEB, 'js', 'bankcore.js'))
        self.assertIsNone(re.search(r'\bdocument\.|\bwindow\.|^import ', only, re.M))


class Wiring(unittest.TestCase):
    def test_console(self):
        con = read(WEB, 'js', 'panels', 'ops', 'console.js')
        self.assertIn("import { mountBankBox } from './bank.js';", con)
        self.assertIn('const base = txBase(pick, stamp);', con)                               # manual_bank_<입금번호>
        self.assertIn("tx_id: base + (cnt > 1 ? '_' + (i + 1) : '')", con)
        self.assertIn('const name = sendName(nameIn.value, pick);', con)                     # 비우면 '익명'
        self.assertIn('if (pick) bank.used(pick, name);', con)                               # 송출 끝 → 씀 표시 · 장부 체크 되돌리기
        self.assertIn('bank.note,', con)                                                     # '계좌 입금에서 채움' 알림 + [비우기]
        self.assertLess(con.find('bank.el, h('), con.find("h('div', { class: 'con-grid' }"))  # 추천 칸이 맨 위

    def test_bank_box_never_sends(self):
        src = read(WEB, 'js', 'panels', 'ops', 'bank.js')
        only = code(src)
        self.assertFalse('/api/donation' in only, '추천 칸이 스스로 송출하면 안 된다')               # 스스로 송출하는 길이 없다
        self.assertFalse('/api/signature/play' in only)
        self.assertFalse('innerHTML' in only, '실명 · 메모는 글자로만')
        # 장부 체크를 되돌리는 자리 — 송출 · 비우기 · 숨기기 · 다른 화면 처리
        for frag in ('setLedger(P.release());', 'setLedger(P.releaseIf(id));', 'setLedger(P.releaseIfGone('):
            self.assertIn(frag, src)
        self.assertEqual(src.count('setLedger(P.release());'), 2)                            # 송출 끝(used) · [비우기]
        self.assertIn("JSON.stringify([BANK.items, BANK.hidden, P.get() && P.get().id])", src)   # 내용이 바뀔 때만 다시 그린다
        self.assertIn('ctx.confirm(', src)                                                    # 새 열쇠는 화면 안 확인 상자로(confirm() 금지)
        self.assertIsNone(re.search(r'(?<![\w.])confirm\(', only))

    def test_no_sound(self):
        for p in (('js', 'bankext.js'), ('js', 'bankcore.js'), ('js', 'panels', 'ops', 'bankmirror.js'), ('js', 'panels', 'ops', 'bank.js')):
            only = code(read(WEB, *p))
            with self.subTest(p=p):
                self.assertFalse('Audio(' in only, '소리 금지')                                  # 조종실 계좌 알림은 화면만(대표님 10-16)
                self.assertFalse('.play(' in only, '소리 금지')
                self.assertFalse('innerHTML' in only, 'innerHTML 금지')

    def test_header_tabs_system(self):
        hdr = read(WEB, 'js', 'header.js')
        self.assertIn("import { mountBankAlarm } from './bankext.js';", hdr)
        self.assertIn('bankAlarm.render(slices, status, view)', hdr)
        ext = read(WEB, 'js', 'bankext.js')
        self.assertIn("fetch('/api/bank/ext'", ext)
        self.assertIn("'/api/bank/ext/cmd'", ext)
        self.assertIn("hdrRoot.querySelector('.pf-chips')", ext)                             # alarm.js 의 점 묶음 옆
        tabs = read(WEB, 'js', 'tabs.js')
        self.assertIn('paintBadges(slices);', tabs)
        ops = read(WEB, 'js', 'panels', 'tools_ops.js')
        self.assertIn("mount: mountConsole, badge: bankBadge", ops)
        sysjs = read(WEB, 'js', 'panels', 'ops', 'system.js')
        self.assertIn('bankMirror.el,', sysjs)
        self.assertIn('bankApp.el,', sysjs)
        mir = read(WEB, 'js', 'panels', 'ops', 'bankmirror.js')
        self.assertIn("'/vendor/qrious.min.js'", mir)                                         # QR 은 우리 서버에서(바깥 CDN 안 씀)
        self.assertIn("'/download/bankphone.apk'", mir)
        self.assertTrue(os.path.exists(os.path.join(ROOT, 'vendor', 'qrious.min.js')))
        idx = read(WEB, 'index.html')
        self.assertIn('href="./css/tools_bank.css"', idx)
        self.assertNotIn('://', read(WEB, 'css', 'tools_bank.css'))                         # 바깥에서 불러오는 것 없음


if __name__ == '__main__':
    unittest.main()
