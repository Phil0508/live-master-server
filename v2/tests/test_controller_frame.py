# -*- coding: utf-8 -*-
"""조종실 틀(시안 B 10-17 · 묶음 A w2frame) — 칸 id 약속 · 다음 작업자 자리 · 소리 없음 · 설정 타일이 있는 탭을 가리키는가.

화면은 헤드리스 크롬으로 따로 본다(ARCHITECTURE '10-17 이사 2차 — w2frame'). 여기서는 파일만 읽어 틀이 깨지지 않았는지 지킨다.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CTL = os.path.join(ROOT, 'v2', 'web', 'controller')


def read(*p):
    with open(os.path.join(CTL, *p), encoding='utf-8') as f:
        return f.read()


def panel_ids():
    """탭 목록 파일들에서 { id: '…' } 를 모은다"""
    ids = []
    for name in ['games.js', 'tools_ops.js', 'tools_records.js', 'tools_more.js', 'tools_sig.js', 'tools_fx.js',
                 'tools_ai.js', 'tools_auto.js', 'frame.js', 'settings_menu.js']:
        src = read('js', 'panels', name)
        ids += re.findall(r"\{\s*id:\s*'([a-z0-9-]+)'", src)
    return ids


class ControllerFrame(unittest.TestCase):
    def test_index_has_frame_ids(self):
        idx = read('index.html')
        # 옛 id(클릭 기록 구역 · 다른 파일이 찾는 칸)는 그대로
        for i in ['hdr', 'down-banner', 'v-splash', 'v-login', 'v-setup', 'undo', 'scores', 'goal', 'logs', 'pending', 'queue', 'splash-msg']:
            self.assertIn('id="%s"' % i, idx, i)
        # 새 틀 칸(다른 작업자가 채운다)
        for i in ['v-shell', 'rail', 'center', 'side', 'drawer', 'stagebar', 'goal-win-slot', 'home', 'kpis', 'basic',
                  'tabbody', 'say-slot', 'con-mini', 'queue-fold']:
            self.assertIn('id="%s"' % i, idx, i)
        self.assertIn('class="tabbar rail"', idx)          # uistats areaOf 가 .tabbar 로 '탭 줄' 을 센다
        self.assertIn('v-live', idx)                        # 옛 css 셀렉터 이름
        self.assertIn('./css/home.css', idx)
        self.assertIn('./css/side.css', idx)

    def test_main_leaves_slots_for_b_c_d(self):
        src = read('js', 'main.js')
        for s in ['// [B] import { mountKpis }', '// [B] import { mountStagebar }', '// [C] import { mountDrawer }',
                  '// [D] import { mountCmdk }', '// [D] import { mountRxSwitch }', "// [D] safe(() => mountCmdk(ctx));"]:
            self.assertIn(s, src)
        # 방송 전에도 탭을 그린다
        self.assertIn("if (view === 'setup' || view === 'live') safe(() => views.tabs.render(slices, view));", src)

    def test_header_has_control_slots(self):
        src = read('js', 'header.js')
        for i in ['ctl-bgm', 'ctl-sig', 'ctl-rx', 'ctl-misc', 'ctl-more', 'ctl-more-sig', 'sb-dots', 'sb-band']:
            self.assertIn("id: '%s'" % i, src, i)
        self.assertIn("class: 'btn xs dgr end-btn'", src)    # [방송 끝] class 그대로
        self.assertIn('/controller/editor/', src)
        self.assertNotIn('mountTodayPill', src)              # 💰 알약은 숫자 카드 ①로 간다

    def test_no_sound_in_frame(self):
        for p in [('js', 'alarm.js'), ('js', 'header.js'), ('js', 'tabs.js'), ('js', 'bankext.js'), ('js', 'icons.js'),
                  ('js', 'panels', 'frame.js'), ('js', 'panels', 'settings_menu.js')]:
            src = read(*p)
            for bad in ['new Audio', 'AudioContext', '.play()', 'navigator.vibrate', 'Notification.requestPermission']:
                self.assertNotIn(bad, src, '/'.join(p) + ' ' + bad)

    def test_band_api_and_bank_uses_it(self):
        alarm = read('js', 'alarm.js')
        self.assertIn('export function bandAdd(', alarm)
        self.assertIn('export function bandRemove(', alarm)
        ext = read('js', 'bankext.js')
        self.assertIn("bandAdd('bank-dead'", ext)
        self.assertIn("bandAdd('bank-new'", ext)

    def test_panel_ids_unique_and_tiles_exist(self):
        ids = panel_ids()
        self.assertEqual(len(ids), len(set(ids)), [i for i in ids if ids.count(i) > 1])
        tabs = read('js', 'tabs.js')
        order = re.search(r'RAIL_ORDER = \[([^\]]*)\]', tabs).group(1)
        for i in re.findall(r"'([a-z0-9-]+)'", order):
            self.assertIn(i, ids, '왼쪽 줄 순서표에 없는 탭: ' + i)
        menu = read('js', 'panels', 'settings_menu.js')
        groups = re.search(r'const GROUPS = \[(.*?)\n\];', menu, re.S).group(1)
        for i in re.findall(r"'([a-z0-9-]+)'", groups):
            self.assertIn(i, ids, '설정 타일이 가리키는 탭이 없다: ' + i)

    def test_logout_calls_existing_route_only(self):
        menu = read('js', 'panels', 'settings_menu.js')
        self.assertIn("fetch('/logout', { method: 'POST'", menu)


if __name__ == '__main__':
    unittest.main()
