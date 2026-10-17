# -*- coding: utf-8 -*-
"""📇 후원자 장부 — 조종실 화면(10-17 후원자 장부 5단계, 갈래 '다').

- 순수 계산(딱지 글자 · 이름 맞추기 · 목록 거르기 · 막대 · 팬클럽 사전)은 node 로 실물 js/donorcore.js 를 부른다(js/donorbook_check.mjs).
- 이어 붙인 자리(대기함 카드 · 장부 줄 · ⚙ 설정 타일 · css)와 '바깥 글자는 textContent 로만' 은 파일 글자로 지킨다.
- 보내는 명령 · 읽는 길은 설계서의 이름만 — 서버(donor_book.py)가 합쳐진 뒤에는 그 명령이 실제로 있는지도 본다.
돌리기: python -m unittest discover -s v2/tests -t .
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CTL = os.path.join(ROOT, 'v2', 'web', 'controller')

NEW = [('js', 'donorcore.js'), ('js', 'donorcard.js'), ('js', 'panels', 'records', 'donorbook.js')]
CMDS = {'donor.merge', 'donor.split', 'donor.suggest_reject', 'donor.pin', 'donor.mark_test', 'donor.note',
        'donor.club_set', 'donor.rebuild'}


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
        p = subprocess.run([node, os.path.join(ROOT, 'v2', 'tests', 'js', 'donorbook_check.mjs')], capture_output=True, timeout=120)
        out = p.stdout.decode('utf-8', 'replace')
        self.assertEqual(p.returncode, 0, p.stderr.decode('utf-8', 'replace')[-1500:])
        self.assertEqual([ln for ln in out.splitlines() if ln.startswith('BAD ')], [])
        m = re.search(r'^DONE (\d+)$', out, re.M)
        self.assertTrue(m and int(m.group(1)) >= 68, out[-500:])

    def test_node_syntax(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node 가 없다')
        # .js 그대로 --check 하면 node 가 CommonJS 로도 읽어 보고 넘어간다(따옴표 안 맨 줄바꿈을 놓쳤다 — 리뷰 10-17).
        # 브라우저처럼 모듈로 읽게 .mjs 로 복사해서 본다(test_games_js_syntax 와 같은 방법).
        tmp = tempfile.mkdtemp(prefix='lm2-donorbook-')
        try:
            for i, p in enumerate(NEW + [('js', 'pending.js'), ('js', 'panels', 'records', 'ledger.js'), ('js', 'panels', 'tools_records.js'),
                                         ('js', 'panels', 'settings_menu.js'), ('js', 'panels', 'more', 'uistats.js')]):
                m = os.path.join(tmp, 'f%d.mjs' % i)
                shutil.copyfile(os.path.join(CTL, *p), m)
                r = subprocess.run([node, '--check', m], capture_output=True, timeout=60)
                self.assertEqual(r.returncode, 0, '/'.join(p) + ' ' + r.stderr.decode('utf-8', 'replace')[-800:])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Wiring(unittest.TestCase):
    def test_core_has_no_dom(self):
        # 순수 계산 파일은 화면을 안 만진다(node 로 부를 수 있게)
        src = code(read('js', 'donorcore.js'))
        self.assertNotRegex(src, r'\b(document|window|import)\b')

    def test_outside_text_only_by_textcontent(self):
        # 이름 · 닉네임 · 메시지 · 메모 · 팬클럽 말은 바깥 글자 — innerHTML · insertAdjacentHTML 을 안 쓴다
        for p in NEW:
            src = code(read(*p))
            self.assertNotRegex(src, r'innerHTML|outerHTML|insertAdjacentHTML|document\.write', '/'.join(p))

    def test_pending_and_ledger_show_tags(self):
        pend = code(read('js', 'pending.js'))
        self.assertIn("donorName(ctx, it.name, 'pc-name')", pend)
        self.assertIn('donorChips(ctx.slices, it.name)', pend)
        self.assertIn('tagSig(slices.donor_tags, it.name)', pend)          # 딱지가 바뀌면 그 카드만 다시 그린다
        led = code(read('js', 'panels', 'records', 'ledger.js'))
        self.assertIn("donorName(ctx, r.name, 'rc-name')", led)
        self.assertIn('donorChips(ctx.slices, r.name)', led)
        self.assertIn("changed('donor_tags')", led)

    def test_settings_tile_and_css(self):
        menu = read('js', 'panels', 'settings_menu.js')
        groups = re.search(r'const GROUPS = \[(.*?)\n\];', menu, re.S).group(1)
        self.assertIn("'donorbook'", groups)
        self.assertIn('donorbook:', menu)                                   # 타일 설명 한 줄
        self.assertRegex(read('js', 'panels', 'tools_records.js'), r"\{ id: 'donorbook', label: '후원자 목록'")
        self.assertIn('./css/donorbook.css', read('index.html'))
        css = read('css', 'donorbook.css')
        self.assertIn('@media (max-width: 899px)', css)                     # 폰 — 카드는 아래 시트
        self.assertNotRegex(css, r'https?://')                              # 바깥에서 아무것도 안 불러온다
        # 카드 서랍은 확인 상자(.modal-wrap 100) 아래 — [묶기] 가 묻는 상자가 서랍 뒤에 숨지 않게
        z = int(re.search(r'\.dk-wrap \{[^}]*z-index: (\d+)', css).group(1))
        self.assertLess(z, 100)

    def test_css_does_not_leak(self):
        # 리뷰(10-17) — 이 파일은 맨 뒤에 붙는다. 맨 .btn 규칙은 다른 탭(무대 · 공지 …)의 .btn.on 까지 바꾼다 → 자기 칸 안에서만
        css = re.sub(r'/\*.*?\*/', '', read('css', 'donorbook.css'), flags=re.S)
        for sel in re.findall(r'(?:^|[{}])\s*([^{}@]+?)\s*\{', css):
            for one in sel.split(','):
                one = one.strip()
                if one.startswith('.btn'):
                    self.fail('밖으로 새는 규칙: ' + one)
        # 장부 줄 이름이 단추가 돼도 굵기 · 크기를 지킨다
        self.assertIn('.rc-name.dk-link', css)

    def test_club_no_is_confirmed_without_player(self):
        # [아니에요] · [빼기] 는 '팬클럽 말 아님'(confirmed + 선수 없음) — confirmed:false 로 보내면 다시 세기가 같은 짐작을 또 올린다
        src = code(read('js', 'panels', 'records', 'donorbook.js'))
        self.assertIn('clubSet(r.word, null, true,', src)
        self.assertNotIn('clubSet(r.word, null, false', src)
        self.assertIn("/api/donors/book?all=1", src)          # 🧪 시험 카드도 받아야 거르기에서 다시 풀 수 있다

    def test_name_buttons_not_in_click_stats(self):
        # 리뷰(10-17) — 글자가 곧 후원자 이름인 단추는 클릭 세기(📊 ui_clicks)에 이름이 안 가게 data-stat 이름표를 단다
        for p in NEW[1:]:
            src = code(read(*p))
            for m in re.finditer(r"h\('button', \{[^}]*class: '[^']*(?:dk-link|db-open)[^']*'[^}]*\}", src):
                self.assertIn("'data-stat':", m.group(0), '/'.join(p) + ' ' + m.group(0)[:120])
        self.assertIn("getAttribute('data-stat')", read('js', 'panels', 'more', 'uistats.js'))

    def test_routes_and_commands_from_spec_only(self):
        src = '\n'.join(code(read(*p)) for p in NEW)
        routes = set(re.findall(r"'(/api/[a-z/_]+)", src))
        self.assertEqual(routes, {'/api/donors/book', '/api/donors/person/', '/api/donors/suggest'})
        sent = set(re.findall(r"(?:ctx\.run\(|act\(ctx, )\s*'([a-z_]+\.[a-z_]+)'", src))
        self.assertEqual(sent, CMDS)

    def test_commands_exist_on_server_when_merged(self):
        # 서버 갈래('나' — domain/donor_book.py)가 합쳐진 뒤에는 화면이 보내는 명령이 서버에 다 있어야 한다
        from v2.server import domain  # noqa: F401  (명령 등록)
        from v2.server.bus import COMMANDS
        if 'donor.merge' not in COMMANDS:          # donor.exclude · include(순위 빼기)는 예전부터 있다 — 새 명령 하나로 본다
            self.skipTest('서버 donor_book 이 아직 안 합쳐졌다')
        missing = sorted(n for n in CMDS if n not in COMMANDS)
        self.assertEqual(missing, [], '서버에 없는 명령')


if __name__ == '__main__':
    unittest.main()
