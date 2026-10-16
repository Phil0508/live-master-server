# -*- coding: utf-8 -*-
"""조종실 랭킹 첫 화면(시안 B 묶음 B · 10-17 w2center) — 숫자 카드 · 💱 정산 차액 · 무대 줄 · 점수판 · 기본 설정.

화면은 헤드리스 크롬으로 따로 본다(ARCHITECTURE '10-17 이사 2차 — w2center'). 여기서는 파일만 읽어 약속이 깨지지 않았는지 지킨다.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CTL = os.path.join(ROOT, 'v2', 'web', 'controller')
HOME_JS = [('js', 'kpis.js'), ('js', 'stagebar.js'), ('js', 'scores.js'), ('js', 'goal.js'), ('js', 'homeicons.js'),
           ('js', 'panels', 'ai', 'today.js')]


def read(*p):
    with open(os.path.join(CTL, *p), encoding='utf-8') as f:
        return f.read()


class ControllerHome(unittest.TestCase):
    def test_main_mounts_home(self):
        src = read('js', 'main.js')
        self.assertIn("import { mountKpis } from './kpis.js';", src)
        self.assertIn("import { mountStagebar } from './stagebar.js';", src)
        self.assertIn("kpis: mountKpis($('kpis'), ctx),", src)
        self.assertIn("stagebar: mountStagebar($('stagebar'), ctx),", src)
        self.assertRegex(src, r"'kpis', 'stagebar',")

    def test_no_sound_no_raf(self):
        for p in HOME_JS:
            src = read(*p)
            for bad in ['new Audio', 'AudioContext', '.play()', 'navigator.vibrate', 'Notification.requestPermission',
                        'requestAnimationFrame']:
                self.assertNotIn(bad, src, '/'.join(p) + ' ' + bad)

    def test_new_files_do_not_use_innerhtml(self):
        # 바깥 글자(이름 · 후원자)는 h()/textContent 로만 — 새로 만든 파일엔 innerHTML 에 넣는 줄이 없다
        for p in [('js', 'kpis.js'), ('js', 'stagebar.js'), ('js', 'homeicons.js')]:
            self.assertNotRegex(read(*p), r'\.innerHTML\s*\+?=', '/'.join(p))

    def test_buttons_send_known_commands(self):
        from v2.server import domain  # noqa: F401
        from v2.server.bus import COMMANDS
        sent = {}
        for p in HOME_JS + [('js', 'panels', 'ops', 'fjside.js')]:
            for name in re.findall(r"""run\(\s*(?:[a-z.]+\s*\?\s*)?'([a-z_]+\.[a-z_]+)'(?:\s*:\s*'([a-z_]+\.[a-z_]+)')?""", read(*p)):
                for n in name:
                    if n:
                        sent.setdefault(n, '/'.join(p))
            for n in re.findall(r"handle\(\s*'([a-z_]+\.[a-z_]+)'", read(*p)):      # goal.js 달성 상자 handle('goal.celebrate', …)
                sent.setdefault(n, '/'.join(p))
        for must in ['match.start', 'match.pause', 'match.add_time', 'show.cue', 'preset.save', 'sig.allclear', 'dice.roll',
                     'score.add', 'players.remove', 'fundjar.add', 'goal.set', 'goal.celebrate', 'goal.dismiss', 'fundjar.side']:
            self.assertIn(must, sent, must + ' 를 보내는 단추가 없어졌다')
        for name, where in sent.items():
            self.assertIn(name, COMMANDS, '%s 가 보내는 %s 는 서버에 없는 명령' % (where, name))

    def test_class_names_kept(self):
        # 클릭 기록 · 다른 파일이 찾는 이름 — 그대로
        sc = read('js', 'scores.js')
        for c in ['cfix-btn', 'extra-start', 'extra-end', 'extra-cancel']:
            self.assertIn(c, sc)
        self.assertIn('goal-win', read('js', 'goal.js'))
        self.assertIn("getElementById('goal-win-slot')", read('js', 'goal.js'))     # 달성 상자는 어느 탭에서든
        self.assertIn("id: 'jar-side-slot'", sc)

    def test_values_come_from_server(self):
        k = read('js', 'kpis.js')
        self.assertIn("'/api/ledger/settle'", k)          # 💱 정산 차액은 서버가 센다(ledger.settle)
        self.assertIn("'가장_큰'", k)                      # ① 가장 큰 후원 = ai_facts.today_summary
        self.assertIn('gaugeValue', k)                     # ④ = goal.js 와 같은 식
        self.assertIn("'/api/ai/board?today=1", read('js', 'panels', 'ai', 'today.js'))

    def test_home_css_has_three_widths(self):
        css = read('css', 'home.css')
        self.assertIn('@media (min-width: 900px) and (max-width: 1279px)', css)
        self.assertIn('@media (max-width: 899px)', css)
        self.assertIn('grid-template-columns: 40px minmax(0, 1fr) 84px 84px 210px 44px', css)

    def test_cue_at_null_means_not_started(self):
        # 방송 시작 직후 show.cue_at 은 null 로 온다(헤드리스로 확인 · 10-17 검토). Number(null) = 0 이라 그대로 쓰면
        # 무대 줄 · 순서표가 '1. ○○' 를 지금 단계로 보이고 [다음] 이름이 2단계를 가리키는데, 서버(settings2.cue_at)는 -1 로 셈해 1단계로 간다.
        self.assertIn('show.cue_at != null && Number.isFinite(Number(show.cue_at))', read('js', 'stagebar.js'))
        self.assertIn('r != null && isFinite(v)', read('js', 'panels', 'ops', 'cues.js'))
        from v2.server.domain.settings2 import cue_at
        self.assertEqual(cue_at({'cue_at': None}), -1)
        self.assertEqual(cue_at({}), -1)


if __name__ == '__main__':
    unittest.main()
