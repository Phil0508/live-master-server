# -*- coding: utf-8 -*-
"""조종실 오른쪽 칸(시안 B 10-17 · 묶음 C w2side) — 대기함 한 장 · 추천 단추 · 되돌리기 자리 · 시그 조종 줄 · 콘솔 미니 · 폰 서랍.

화면은 헤드리스 크롬으로 따로 봤다(ARCHITECTURE '10-17 이사 2차 — w2side'). 여기서는 파일만 읽어 약속이 깨지지 않았는지 지킨다.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CTL = os.path.join(ROOT, 'v2', 'web', 'controller')


def read(*p):
    with open(os.path.join(CTL, *p), encoding='utf-8') as f:
        return f.read()


def code(src):
    """주석을 뺀 코드(설명 글에 남은 옛 이름은 세지 않는다)"""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(^|[^:])//[^\n]*', r'\1', src)


class OneCardPerDonation(unittest.TestCase):
    def test_no_ask_row(self):
        # 같은 후원이 '🤖 지급할까요?' 줄과 카드로 두 번 보이던 것 — 줄을 없앴다
        self.assertNotIn('mountAsks', code(read('js', 'pending.js')))
        assist = code(read('js', 'panels', 'ai', 'assist.js'))
        self.assertNotIn('mountAsks', assist)
        self.assertNotIn('ai-ask', assist)
        self.assertNotIn('.ai-ask', read('css', 'tools_ai.css').replace("(.ai-asks)", ''))
        self.assertIn('export function pick(', assist)
        self.assertIn('export function attach(', assist)
        self.assertIn('ai.attach(ctx);', read('js', 'pending.js'))     # 연결 묶음(setCtx)은 여전히 대기함이 넣는다

    def test_recommend_button_same_path(self):
        src = read('js', 'pending.js')
        # 추천은 선수 단추 하나에 class 만 — 누르면 다른 단추와 같은 assign(it, [n])
        self.assertIn("class: 'pbtn' + (n === rec ? ' rec' : '')", src)
        self.assertEqual(code(src).count('onclick: () => assign(it, [n])'), 1)
        self.assertIn("REC_LEVELS = new Set(['sure', 'maybe'])", src)
        self.assertIn('order.includes(p.target)', src)                   # 지금 판 선수일 때만
        css = read('css', 'side.css')
        self.assertIn('#pending .pbtn.rec {', css)
        self.assertIn('#pending .rec-tag {', css)
        self.assertRegex(css, r'#drawer #pending \.pbtn \{ min-height: 36px; height: 36px;')   # 폰 선수 단추 36px

    def test_freeze_kept(self):
        src = read('js', 'pending.js')
        for frag in ["root.addEventListener('pointerenter'", "root.addEventListener('touchend'", 'toGhost(id, c)', 'mergeOrder(frozenOrder, names)']:
            self.assertIn(frag, src)
        self.assertIn("document.getElementById('pending')", read('js', 'panels', 'ai', 'assist.js'))   # 얼림은 대기함 칸에서 본다


class Placement(unittest.TestCase):
    def test_main_mounts_drawer(self):
        src = read('js', 'main.js')
        self.assertIn("import { mountDrawer } from './drawer.js';", src)
        self.assertIn('drawer: mountDrawer(ctx),', src)
        self.assertLess(src.find('undo: mountUndo('), src.find('drawer: mountDrawer('))       # 옮길 칸이 먼저 있어야 한다
        self.assertIn("'drawer',", src)

    def test_drawer_moves_nodes_only(self):
        src = code(read('js', 'drawer.js'))
        for i in ['pending', 'undo', 'con-mini', 'say-slot', 'queue-fold', 'side', 'drawer']:
            self.assertIn("$('%s')" % i, src, i)
        self.assertNotIn('innerHTML', src)
        self.assertIn('mountConsole(box, ctx, { mini: true })', src)
        self.assertIn("'data-panel': 'con-mini'", src)                                         # 클릭 기록 구역
        self.assertIn("'lm:drawer'", src)
        self.assertIn("classList.contains('has-drawer')", read('js', 'phone.js'))             # 서랍이 있으면 📥 띠 안 띄움

    def test_queue_controls_in_header(self):
        src = read('js', 'queue.js')
        self.assertIn("document.getElementById('ctl-sig')", src)
        self.assertIn("document.getElementById('ctl-more-sig')", src)
        for cls in ['skip-btn', 'pause-btn', 'stop-btn', 'ctl-stop']:
            self.assertIn(cls, src)
        self.assertIn('if (n >= 2) {', src)                                                    # [중단] 2개 이상이면 묻기

    def test_console_mini_shares_send(self):
        src = read('js', 'panels', 'ops', 'console.js')
        self.assertIn('export function mountConsole(el, ctx, opts = {})', src)
        self.assertEqual(code(src).count('async function send()'), 1)                          # 보내는 길은 하나(복사 금지)
        self.assertIn("ctx.tabs.open('ops-console')", src)

    def test_commands_exist(self):
        from v2.server import domain  # noqa: F401
        from v2.server.bus import COMMANDS
        sent = set()
        for p in [('js', 'pending.js'), ('js', 'queue.js'), ('js', 'undo.js'), ('js', 'drawer.js')]:
            sent |= set(re.findall(r"""ctx\.run\(\s*'([a-z_]+\.[a-z_]+)'""", read(*p)))
        for must in ['pending.assign', 'pending.ignore', 'pending.to_jar', 'reaction.skip', 'reaction.stop', 'reaction.volume', 'score.undo']:
            self.assertIn(must, sent)
        for name in sent:
            self.assertIn(name, COMMANDS, name)

    def test_no_sound(self):
        for p in [('js', 'pending.js'), ('js', 'drawer.js'), ('js', 'queue.js'), ('js', 'undo.js'), ('js', 'panels', 'ai', 'assist.js'),
                  ('js', 'panels', 'ops', 'console.js'), ('js', 'phone.js')]:
            src = read(*p)
            for bad in ['new Audio', 'AudioContext', '.play()', 'navigator.vibrate', 'Notification.requestPermission']:
                self.assertNotIn(bad, src, '/'.join(p) + ' ' + bad)

    def test_outside_text_is_text(self):
        # 후원자 이름 · 메시지 · AI 까닭은 h()/textContent 로만
        for p in [('js', 'pending.js'), ('js', 'drawer.js'), ('js', 'panels', 'ai', 'assist.js')]:
            src = code(read(*p))
            self.assertIsNone(re.search(r'innerHTML\s*=\s*`[^`]*\$\{', src), p)


if __name__ == '__main__':
    unittest.main()
