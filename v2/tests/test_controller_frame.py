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

    def test_frame_buttons_send_known_commands(self):
        # 틀이 직접 누르는 단추가 보내는 명령 — 서버에 그 이름이 있어야 눌러도 '모르는 명령' 이 안 난다(이름은 바꾸지 않는다)
        from v2.server import domain  # noqa: F401  (조각 · 명령 등록)
        from v2.server.bus import COMMANDS
        sent = {}
        for p in [('js', 'header.js'), ('js', 'castbox.js'), ('js', 'endundo.js'), ('js', 'panels', 'frame.js'),
                  ('js', 'panels', 'settings_menu.js'), ('js', 'tabs.js'), ('js', 'alarm.js'), ('js', 'clipbtn.js')]:
            for name in re.findall(r"""(?:ctx\.)?run\(\s*'([a-z_]+\.[a-z_]+)'""", read(*p)):
                sent.setdefault(name, '/'.join(p))
        sent.update({n: 'js/castbox.js' for n in re.findall(r"'(cast\.[a-z_]+)'", read('js', 'castbox.js'))})
        for must in ['session.end', 'session.undo_end', 'cast.say', 'cast.up', 'clip.now']:
            self.assertIn(must, sent, must + ' 를 보내는 단추가 없어졌다')
        for name, where in sent.items():
            self.assertIn(name, COMMANDS, '%s 가 보내는 %s 는 서버에 없는 명령' % (where, name))

    def test_down_banner_clears_rail(self):
        # 왼쪽 줄(#rail)은 조종 줄 옆까지 올라가 있다 — '서버와 연결이 끊겼어요' 띠가 그 밑에 깔려 첫 글자가 가리지 않게 비켜 선다(10-17 검토)
        css = read('controller.css')
        self.assertRegex(css, r'@media \(min-width: 900px\) \{ \.down-banner \{ margin: 0 0 var\(--gap\) calc\(var\(--rail-w\) \+ var\(--gap\)\); \} \}')
        self.assertIn('top: calc(var(--sb-h) - var(--hdr-h))', css)     # 왼쪽 줄이 올라가는 규칙이 있는 동안은 위 비킴도 있어야 한다

    def test_logout_calls_existing_route_only(self):
        menu = read('js', 'panels', 'settings_menu.js')
        self.assertIn("fetch('/logout', { method: 'POST'", menu)


if __name__ == '__main__':
    unittest.main()
