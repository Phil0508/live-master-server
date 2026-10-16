# -*- coding: utf-8 -*-
"""조종실 시안 B 묶음 D(w2feat 10-17) — 🎵 BGM 재생 목록 · 반복 · 📥 장부 엑셀 · ⌨️ Ctrl+K · 🙈 리액션 모드 스위치.

- 순수 계산(다음 곡 셈 · 200곡 · CSV · Ctrl+K 고를 거리)은 node 로 실물 파일을 그대로 부른다(v2/tests/js/w2feat_check.mjs).
- 📺 /api/yt/info(유튜브 제목) — 바깥으로 나가는 fetch_info 를 바꿔 끼워 본다(진짜 유튜브에 안 묻는다).
- 이어 붙인 자리 · 소리 없음 · 명령 이름은 파일 글자로 지킨다. 화면은 헤드리스 크롬으로 따로 본다(ARCHITECTURE '10-17 이사 2차 — w2feat').
돌리기: python -m unittest discover -s v2/tests -t .
"""
import os
import re
import shutil
import subprocess
import unittest

from v2.tests.test_flow import Base, H

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
        p = subprocess.run([node, os.path.join(ROOT, 'v2', 'tests', 'js', 'w2feat_check.mjs')], capture_output=True, timeout=120)
        out = p.stdout.decode('utf-8', 'replace')
        self.assertEqual(p.returncode, 0, p.stderr.decode('utf-8', 'replace')[-1500:])
        self.assertEqual([ln for ln in out.splitlines() if ln.startswith('BAD ')], [])
        m = re.search(r'^DONE (\d+)$', out, re.M)
        self.assertTrue(m and int(m.group(1)) >= 35, out[-500:])


class YtInfo(Base):
    def setUp(self):
        super().setUp()
        from v2.server.domain import yt_info
        self.m = yt_info
        self.m._CACHE.clear()
        self.asked = []
        self._orig = yt_info.fetch_info
        yt_info.fetch_info = lambda vid: (self.asked.append(vid) or {'title': '비 오는 밤 로파이', 'author': '채널'})

    def tearDown(self):
        self.m.fetch_info = self._orig
        self.m._CACHE.clear()
        super().tearDown()

    def test_title_and_cache(self):
        r = self.c.get('/api/yt/info?id=dQw4w9WgXcQ', headers=H).json()
        self.assertEqual((r['status'], r['title'], r['author']), ('success', '비 오는 밤 로파이', '채널'))
        self.c.get('/api/yt/info?id=dQw4w9WgXcQ', headers=H)
        self.assertEqual(self.asked, ['dQw4w9WgXcQ'])                       # 받은 것은 기억 — 두 번 안 묻는다

    def test_login_and_bad_id(self):
        self.assertEqual(self.c.get('/api/yt/info?id=dQw4w9WgXcQ').status_code, 401)   # 로그인한 조종실만
        self.assertEqual(self.c.get('/api/yt/info?id=../../etc', headers=H).status_code, 400)
        self.assertEqual(self.asked, [])

    def test_failure_is_empty_and_not_cached(self):
        def boom(vid):
            raise OSError('인터넷 없음')
        self.m.fetch_info = boom
        r = self.c.get('/api/yt/info?id=aaaaaaaaaaa', headers=H).json()
        self.assertEqual((r['status'], r['title']), ('success', ''))         # 못 받으면 빈 제목(조종실은 영상 번호로 둔다)
        self.assertNotIn('aaaaaaaaaaa', self.m._CACHE)

    def test_off_switch(self):
        os.environ['LM2_YT_INFO_OFF'] = '1'
        try:
            r = self.c.get('/api/yt/info?id=bbbbbbbbbbb', headers=H).json()
        finally:
            del os.environ['LM2_YT_INFO_OFF']
        self.assertEqual((r['title'], self.asked), ('', []))


class Wiring(unittest.TestCase):
    def test_main_mounts_d(self):
        src = read('js', 'main.js')
        self.assertIn("import { mountCmdk } from './cmdk.js';", src)
        self.assertIn("import { mountRxSwitch } from './rxswitch.js';", src)
        self.assertIn("safe(() => mountCmdk(ctx));", src)
        self.assertIn("safe(() => mountRxSwitch($('ctl-rx'), ctx));", src)
        self.assertIn("safe(() => bindBgm(ctx));", src)
        self.assertIn('prepare: id =>', read('js', 'tabs.js'))              # 조종 줄 ▶ 가 BGM 탭을 숨긴 채 미리 그린다

    def test_commands_shared_not_copied(self):
        chat = read('js', 'panels', 'ai', 'chat.js')
        cmdk = read('js', 'cmdk.js')
        self.assertIn("import { runCommand } from './commands.js';", chat)
        self.assertIn("import { runCommand, COMMAND_HINTS } from './panels/ai/commands.js';", cmdk)
        for frag in ("'score.add'", "'roulette.spin'", "'reaction.skip'", "'sig.allclear'"):
            self.assertNotIn(frag, chat, '규칙은 commands.js 한 곳에만: ' + frag)
            self.assertNotIn(frag, cmdk)

    def test_commands_are_known(self):
        from v2.server import domain  # noqa: F401
        from v2.server.bus import COMMANDS
        for p in [('js', 'panels', 'ai', 'commands.js'), ('js', 'rxswitch.js'), ('js', 'cmdk.js')]:
            for name in re.findall(r"""ctx\.run\(\s*(?:want === 'start' \? )?'([a-z_]+\.[a-z_]+)'""", read(*p)):
                self.assertIn(name, COMMANDS, '/'.join(p) + ' → ' + name)
        self.assertIn("ctx.run('lights.manual', { on })", read('js', 'rxswitch.js'))

    def test_no_sound_no_outside_text_html(self):
        for p in [('js', 'cmdk.js'), ('js', 'rxswitch.js'), ('js', 'panels', 'ai', 'commands.js'), ('js', 'panels', 'records', 'csv.js')]:
            only = code(read(*p))
            for bad in ['new Audio', 'AudioContext', '.play()', 'navigator.vibrate', 'Notification', 'innerHTML']:
                self.assertNotIn(bad, only, '/'.join(p) + ' ' + bad)
        bgm = code(read('js', 'panels', 'records', 'bgm.js'))
        self.assertNotIn('new Audio', bgm)
        self.assertNotIn('i.ytimg.com', bgm)                                # 바깥 그림 서버는 안 부른다(IFrame API 하나만)
        self.assertEqual(re.findall(r'https?://[^\'"\s]+', bgm), ['https://www.youtube.com/iframe_api'])
        # innerHTML 은 고정 아이콘에만(곡 제목 · 채널은 textContent)
        for m in re.finditer(r'\.innerHTML\s*=\s*([^;]+);', bgm):
            self.assertRegex(m.group(1), r'^\(?\s*(ICON\.|playing \?|B\.muted \?|icon\b)', m.group(0))

    def test_bgm_rules(self):
        bgm = read('js', 'panels', 'records', 'bgm.js')
        self.assertIn('if (ev.data === ENDED) onEnded();', bgm)              # 끝나면 다음 곡(예전엔 '끝남' 에서 멈췄다)
        self.assertIn('export const LIST_MAX = 200;', bgm)
        self.assertIn("listType: 'playlist'", bgm)                         # 재생목록 주소 통째 넣기
        self.assertIn('getPlaylist()', bgm)
        self.assertIn("'/api/yt/info?id='", bgm)
        # 페이지를 열 때 유튜브 API 를 안 부른다 — loadApi 는 openVideo · importPlaylist 안에서만
        calls = [m.start() for m in re.finditer(r'await loadApi\(\)', bgm)]
        self.assertEqual(len(calls), 2)

    def test_ledger_csv(self):
        led = read('js', 'panels', 'records', 'ledger.js')
        csv = read('js', 'panels', 'records', 'csv.js')
        self.assertIn("import { csvCell } from '../more/monthly.js';", csv)  # 수식 막기 규칙은 한 곳
        self.assertIn("export const BOM = '\\ufeff';", csv)
        self.assertIn('getUTCHours', csv)                                   # 한국 시각은 PC 시계와 상관없이
        for frag in ("['이번 방송 후원', 'don', 'current']", "['이번 방송 점수 기록', 'score', 'current']",
                     "['전체 후원(모든 회차)', 'all', '']", "['이 회차 후원', 'don', sid]", "['이 회차 점수 기록', 'score', sid]"):
            self.assertIn(frag, led)

    def test_cmdk_under_confirm_box(self):
        """Ctrl+K 상자가 확인 상자(올클리어 · 룰렛 돌려가 묻는 것)를 가리면 [확인] 을 누를 수 없다 — 상자는 확인 상자보다 아래(검토 10-17)"""
        with open(os.path.join(CTL, 'controller.css'), encoding='utf-8') as f:
            base = f.read()
        modal = int(re.search(r'\.modal-wrap\s*\{[^}]*z-index:\s*(\d+)', base).group(1))
        more = int(re.search(r'#ctl-more\s*\{[^}]*z-index:\s*(\d+)', base).group(1))
        cmdk = int(re.search(r'\.cmdk\s*\{[^}]*z-index:\s*(\d+)', read('css', 'tools_records.css')).group(1))
        self.assertLess(cmdk, modal)
        self.assertGreater(cmdk, more)

    def test_overlay_honors_manual(self):
        with open(os.path.join(ROOT, 'v2', 'web', 'overlay', 'widgets', 'signature.js'), encoding='utf-8') as f:
            sig = f.read()
        self.assertIn("opts.stage.setMode('reaction', sigOn || manualOn())", sig)
        self.assertIn("lm.on('lights', () => setReaction(sigOn));", sig)


if __name__ == '__main__':
    unittest.main()
