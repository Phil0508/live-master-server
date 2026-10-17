# -*- coding: utf-8 -*-
"""↩ 기록에서 골라 되돌리기(undopick 10-17).

대표님: 마지막 것만이 아니라 점수 기록(로그 탭 · 장부 탭 점수 줄 · 폰)의 줄마다 [↩ 되돌리기] → 그 줄만.
서버 규칙(그대로 따른다): score.undo {ref} 는 **묶음(ref) 단위** — 한 후원을 나눠 준 줄들은 같이 되돌아간다.

① 세 개 전 줄을 골라 되돌리면 그 줄만 · 점수 · 대기함 복귀 · 두 번 눌러도 한 번
② 나눠 준 후원은 묶음으로(줄 하나를 골라도 두 사람 다) · 대기함엔 한 번만
③ 되돌린 줄은 logs 에서 빠지고 logs_undone(비공개)에 남는다 — 회색 '되돌림' · 방송 시작/끝이면 비운다
④ 지난 방송 줄은 못 되돌린다(409 — 지금 판 같은 이름에서 빠지면 안 된다)
⑤ 기록 줄에 후원자 · 금액(don) — 확인 상자 '21:03 밍밍 +5점(영원 50,000원)'
⑥ 조종실: 화면 안 확인 상자(confirm() 없음) · 소리 없음 · 로그 탭 · 장부 탭이 같은 함수(askUndo) · 확인 상자 글(node 로 실물)
"""
import os
import re
import shutil
import subprocess
import unittest

from v2.tests.test_flow import Base

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CTL = os.path.join(ROOT, 'v2', 'web', 'controller')


def read(*p):
    with open(os.path.join(CTL, *p), encoding='utf-8') as f:
        return f.read()


def code(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?<![:\'"])//[^\n]*', '', src)


class Pick(Base):
    def give(self, name, amount, tx, to):
        self.don(name, amount, tx)
        pid = next(p['id'] for p in self.st()['pending'] if p['name'] == name)
        c, r = self.cmd('pending.assign', id=pid, **({'names': to} if isinstance(to, list) else {'name': to}))
        self.assertEqual(c, 200, r)
        return pid

    def scores(self, s=None):
        s = s or self.st()
        return {p['name']: (p['score'], p['contribution']) for p in s['players']['list']}

    def test_pick_third_back_only_that(self):
        a = self.give('영원', 50000, 'toon_p1', '하율')       # 세 개 전
        self.give('별빛', 30000, 'toon_p2', '서아')
        self.cmd('score.add', name='채원', delta=2)               # 손으로
        before = self.scores()
        self.assertEqual(before, {'하율': (5, 5), '서아': (3, 3), '채원': (2, 2)})
        c, r = self.cmd('score.undo', ref=a)
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertEqual(self.scores(s), {'하율': (0, 0), '서아': (3, 3), '채원': (2, 2)})     # 그 줄만
        self.assertEqual([p['id'] for p in s['pending']], [a])                                # 그 후원만 대기함으로
        self.assertTrue(s['pending'][0]['returned'])
        self.assertEqual([l['name'] for l in s['logs']], ['채원', '서아'])                     # 나머지 기록은 그대로
        self.assertEqual([(l['name'], l['ref']) for l in s['logs_undone']], [('하율', a)])
        self.assertIn('undone_at', s['logs_undone'][0])
        # 두 번 눌러도 한 번
        c, r = self.cmd('score.undo', ref=a)
        self.assertEqual(c, 404, r)
        self.assertEqual(self.scores(), {'하율': (0, 0), '서아': (3, 3), '채원': (2, 2)})
        self.assertEqual(len(self.st()['pending']), 1)
        # 다시 주면 다시 기록에(되돌린 줄은 회색으로 남는다)
        self.cmd('pending.assign', id=a, name='채원')
        s = self.st()
        self.assertEqual(self.scores(s)['채원'], (7, 7))
        self.assertEqual(s['logs'][0]['ref'], a)
        self.assertEqual(len(s['logs_undone']), 1)

    def test_middle_manual_line(self):
        self.cmd('score.add', name='하율', delta=1)
        self.cmd('score.add', name='서아', delta=4)
        mid = self.st()['logs'][0]['ref']
        self.cmd('score.add', name='채원', delta=6)
        self.cmd('score.undo', ref=mid)
        self.assertEqual(self.scores(), {'하율': (1, 1), '서아': (0, 0), '채원': (6, 6)})
        # ref 없이 누르는 큰 [↩] 는 여전히 마지막 것
        self.cmd('score.undo')
        self.assertEqual(self.scores(), {'하율': (1, 1), '서아': (0, 0), '채원': (0, 0)})

    def test_split_donation_is_one_bundle(self):
        sp = self.give('별빛', 50000, 'toon_s1', ['하율', '서아'])      # 3점 · 2점
        self.give('달빛', 10000, 'toon_s2', '채원')
        s = self.st()
        self.assertEqual(sorted(l['name'] for l in s['logs'] if l['ref'] == sp), ['서아', '하율'])
        self.cmd('score.undo', ref=sp)                                    # 줄 하나(서아)를 눌러도 같은 ref
        s = self.st()
        self.assertEqual(self.scores(s), {'하율': (0, 0), '서아': (0, 0), '채원': (1, 1)})
        self.assertEqual([p['id'] for p in s['pending']], [sp])           # 대기함엔 한 번만
        self.assertEqual(sorted(l['name'] for l in s['logs_undone']), ['서아', '하율'])

    def test_log_row_has_donor_and_amount(self):
        a = self.give('영원', 50000, 'toon_d1', '하율')
        row = self.st()['logs'][0]
        self.assertEqual((row['ref'], row['don']), (a, {'name': '영원', 'amount': 50000}))
        self.cmd('score.add', name='서아', delta=1)
        self.assertNotIn('don', self.st()['logs'][0])                     # 손으로 준 줄엔 없다

    def test_past_session_line_refused(self):
        a = self.give('영원', 50000, 'toon_o1', '하율')
        self.cmd('session.end')
        self.cmd('session.start', names=['하율', '서아'])
        self.cmd('score.add', name='하율', delta=3)
        c, r = self.cmd('score.undo', ref=a)
        self.assertEqual(c, 409, r)
        self.assertEqual(self.scores()['하율'], (3, 3))                   # 지금 판은 그대로
        self.assertEqual(self.st()['pending'], [])

    def test_undone_slice_private_and_reset(self):
        a = self.give('영원', 50000, 'toon_r1', '하율')
        self.cmd('score.undo', ref=a)
        self.assertNotIn('logs_undone', self.st(auth=False))              # 방송판(로그인 없음)엔 없다
        self.assertEqual(len(self.st()['logs_undone']), 1)
        self.cmd('session.end')
        self.assertEqual(self.st()['logs_undone'], [])
        self.cmd('session.start', names=['하율'])
        self.assertEqual(self.st()['logs_undone'], [])

    def test_extra_after_end_vs_cancel(self):
        # 확인 상자 안내의 근거 — [끝](merged)이면 본판에서 빠지고, [취소]면 점수 그대로 · 기록만 지워진다
        self.cmd('extra.start')
        self.cmd('score.add', name='하율', delta=4, list='extra')
        r1 = self.st()['logs'][0]['ref']
        self.cmd('extra.end')
        self.assertEqual(self.scores()['하율'], (4, 4))
        self.assertEqual(self.st()['players']['extra_closed'], {'하율': 'merged', '서아': 'merged', '채원': 'merged'})
        c, r = self.cmd('score.undo', ref=r1)
        self.assertEqual(c, 200, r)
        self.assertEqual(self.scores()['하율'], (0, 0))                   # 본판에서 빠졌다 — 손으로 또 빼면 두 번
        self.cmd('extra.start')
        self.cmd('score.add', name='서아', delta=3, list='extra')
        r2 = self.st()['logs'][0]['ref']
        self.cmd('extra.cancel')
        c, r = self.cmd('score.undo', ref=r2)
        self.assertEqual(c, 200, r)
        self.assertEqual(self.scores()['서아'], (0, 0))                   # 본판은 처음부터 그대로


class Controller(unittest.TestCase):
    def test_no_confirm_alert_no_sound(self):
        for p in [('js', 'undopick.js'), ('js', 'undo.js'), ('js', 'panels', 'records', 'ledger.js')]:
            src = code(read(*p))
            self.assertIsNone(re.search(r'(?<![.\w])(confirm|alert)\(', src), p)
            for bad in ['new Audio', 'AudioContext', '.play()', 'navigator.vibrate']:
                self.assertNotIn(bad, src, p)

    def test_one_path(self):
        u = code(read('js', 'undopick.js'))
        self.assertEqual(len(re.findall(r"ctx\.run\('score\.undo', \{ ref \}\)", u)), 1)
        self.assertIn('ctx.confirm(', u)
        for p in [('js', 'undo.js'), ('js', 'panels', 'records', 'ledger.js')]:
            self.assertIn('askUndo(ctx, ', code(read(*p)), p)
        # 이번 방송 · 방송 중에만 단추 — 지난 방송 회차엔 없다
        led = code(read('js', 'panels', 'records', 'ledger.js'))
        self.assertIn("session === 'current' && !!(ctx.slices.session || {}).live", led)

    def test_ledger_regiven_not_merged_with_undone(self):
        # 되돌린 뒤 같은 후원을 다시 주면 같은 ref — 장부 점수 기록에서 회색 줄과 새 줄을 합치면 안 된다('+10 · 안 되돌림')
        led = code(read('js', 'panels', 'records', 'ledger.js'))
        self.assertIn("const k = r.ref + '|' + r.player + '|' + r.list + '|' + (r.undone ? 'u' : '');", led)

    def test_outside_text_is_text(self):
        # 후원자 이름 · 선수 이름은 h()(textContent)로만 — undo.js 의 innerHTML 은 고정 글자(SHOW 숫자)뿐
        self.assertNotIn('innerHTML', code(read('js', 'undopick.js')))
        self.assertIsNone(re.search(r'innerHTML\s*=\s*`[^`]*\$\{(?!SHOW\})', code(read('js', 'undo.js'))))

    def test_node(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node 가 없다')
        p = subprocess.run([node, os.path.join(ROOT, 'v2', 'tests', 'js', 'undopick_check.mjs')], capture_output=True, timeout=120)
        out = p.stdout.decode('utf-8', 'replace')
        self.assertEqual(p.returncode, 0, out + p.stderr.decode('utf-8', 'replace'))
        bad = [l for l in out.splitlines() if l.startswith('BAD')]
        self.assertEqual(bad, [], out)
        self.assertRegex(out, r'DONE (\d+)')
        self.assertGreaterEqual(int(re.search(r'DONE (\d+)', out).group(1)), 14)


if __name__ == '__main__':
    unittest.main()
