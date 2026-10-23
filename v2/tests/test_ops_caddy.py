# -*- coding: utf-8 -*-
"""🔀 Caddy 큰 주소 갈아타기 조각(v2/deploy/Caddyfile.switch · .unswitch) · 도구(caddy_switch.py).

caddy 를 이 PC 에서 돌릴 수 없어서 파일을 읽어 맞대 본다(진짜 확인은 서버에서 caddy validate — README '갈아타는 날').
  - 되돌리기 조각의 덩어리 = 옛 deploy/Caddyfile 의 덩어리(한 글자도 같다)
  - 갈아타기 조각: 기계가 부르는 주소(은행 · 폰 앱 · 크루 사이트 · 개인정보 · 약관 · 스트림덱 · 비상 후원) → 5300,
    옛 운영자 화면 → :8443 의 같은 화면(302), 나머지 → 8080, 기록 파일은 옛 것과 같다(새 기록 파일 없음 — root 함정)
  - 도구: 큰 주소 덩어리만 바꾸고 :8443 · angelcompany.me 홈페이지 · crew · 전역 설정은 한 글자도 안 바꾼다,
    apply → revert 하면 원래 파일과 같다, 두 번 apply · 안 갈아탄 것 revert · 원래 파일 덮어쓰기는 거절
  - 보내는 v2 화면 주소가 v2 에 정말 있다(app.py · 화면 폴더)
"""
import io
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from v2.deploy import caddy_switch as cs

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEP = os.path.join(REPO, 'v2', 'deploy')


def read(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read().replace('\r\n', '\n')


# 운영 서버 Caddyfile 과 같은 모양: 전역 설정 · 옛 큰 주소 · v2(:8443) · 홈페이지 · 크루 (자리 표시 · 따옴표 · 주석 속 괄호 포함)
HOMEPAGE = '''angelcompany.me, www.angelcompany.me {
	# 홈페이지 { 주석 속 괄호 } 는 안 센다
	encode gzip
	@www host www.angelcompany.me
	redir @www https://angelcompany.me{uri} 301
	header {
		X-Frame-Options "DENY"
		Content-Security-Policy "default-src 'self'; img-src 'self' data: { }"
	}
	root * /var/www/angelcompany
	file_server
}'''
CREW = '''crew.angelcompany.me {
	reverse_proxy 127.0.0.1:5400
}'''


def server_caddyfile(nl='\n'):
    old = read(os.path.join(REPO, 'deploy', 'Caddyfile'))
    v2 = read(os.path.join(DEP, 'Caddyfile.v2'))
    text = '{\n\temail ops@example.com\n}\n\n' + old + '\n' + v2 + '\n# 홈페이지(10-08) — 맨 끝에 따로\n' + HOMEPAGE + '\n\n' + CREW + '\n'
    return text.replace('\n', nl)


def block_text(text, head_addrs):
    for b in cs.top_blocks(text):
        if b['addrs'] == head_addrs:
            return text[b['start']:b['end']]
    raise AssertionError('덩어리 없음: %r' % head_addrs)


class Fragments(unittest.TestCase):
    def test_unswitch_equals_old_block(self):
        old = read(os.path.join(REPO, 'deploy', 'Caddyfile'))
        self.assertEqual(cs.fragment(cs.UNSWITCH), block_text(old, [cs.HOST]))
        self.assertNotIn(cs.MARK, cs.fragment(cs.UNSWITCH))

    def test_switch_has_mark_and_one_block(self):
        frag = cs.fragment(cs.SWITCH)
        self.assertIn(cs.MARK, frag)
        self.assertEqual(len(cs.top_blocks(read(cs.SWITCH))), 1)
        self.assertEqual(cs.top_blocks(frag)[0]['addrs'], [cs.HOST])

    def _matcher_paths(self, frag, name):
        m = re.search(r'^\s*@%s path (.+)$' % re.escape(name), frag, re.M)
        self.assertTrue(m, name)
        return m.group(1).split()

    def test_machine_paths_go_to_v2(self):
        frag = cs.fragment(cs.SWITCH)
        paths = self._matcher_paths(frag, 'lm2_v2')
        for p in ('/api/bank/*', '/download/bankphone.apk', '/api/signatures/board', '/api/oraksil/donors', '/privacy', '/terms',
                  '/api/streamdeck/*', '/api/donation'):
            self.assertIn(p, paths)
        # handle @lm2_v2 안은 5300 으로만
        body = frag[frag.index('handle @lm2_v2'):frag.index('# ② ')]
        self.assertIn('reverse_proxy 127.0.0.1:5300', body)
        self.assertNotIn('8080', body)

    def test_machine_paths_answered_by_v2(self):
        """v2 로 넘기는 주소를 v2 가 정말 받는다(실제 앱의 길 목록) — 은행 입구만은 은행 갈래가 들어온 뒤(README ⑥ 에서 확인)."""
        import tempfile as _tf
        from v2.server.app import create_app
        d = _tf.mkdtemp(prefix='lm2ops_caddy_')
        try:
            app = create_app(db_path=os.path.join(d, 'lm2.db'), password='pw', secret='secret-test-0123456789', sig_fetch=lambda: [])
            try:
                have = {getattr(r, 'path', '') for r in app.routes}
            finally:
                app.state.store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)
        for p in self._matcher_paths(cs.fragment(cs.SWITCH), 'lm2_v2'):
            if p.startswith('/api/bank/') or p == '/download/bankphone.apk':
                continue
            if p.endswith('/*'):
                self.assertTrue([h for h in have if h.startswith(p[:-1])], p)
            else:
                self.assertIn(p, have)

    def test_operator_screens_redirect_to_8443(self):
        frag = cs.fragment(cs.SWITCH)
        redirs = re.findall(r'^\s*redir @(\S+) (\S+) (\d+)$', frag, re.M)
        targets = {name: (url, code) for name, url, code in redirs}
        for name, (url, code) in targets.items():
            self.assertTrue(url.startswith('https://{host}:8443/'), url)
            self.assertEqual(code, '302', name)                # 잠깐 옮김 — 되돌리면 바로 풀린다
        want = {'/controller': '/controller/', '/manual': '/controller/console.html', '/manual_send': '/controller/console.html',
                '/manual_send.html': '/controller/console.html', '/uistats.html': '/controller/',
                '/admin': '/controller/editor/', '/노래등록': '/controller/sig.html', '/upload': '/controller/sig.html',
                '/streamdeck': '/streamdeck/', '/mobile': '/mobile', '/health': '/health'}
        for old_path, new_path in want.items():
            hit = [n for n in targets if old_path in self._matcher_paths(frag, n)]
            self.assertEqual(len(hit), 1, old_path)
            self.assertTrue(targets[hit[0]][0].startswith('https://{host}:8443' + new_path), (old_path, targets[hit[0]]))

    def test_obs_screens_stay_on_old_server(self):
        """OBS 소스는 사람이 하나씩 바꾼다 — 큰 주소에서 v2 로 돌리면 한 장면에 두 번 그려진다."""
        frag = cs.fragment(cs.SWITCH)
        live = '\n'.join(l for l in frag.split('\n') if not l.strip().startswith('#'))
        for p in ('/overlay.html', '/alertbox', '/signature-display', '/slot', '/api/stream'):
            self.assertNotRegex(live, r'(?m)^\s*@\S+ path .*(?<!\S)%s(?!\S)' % re.escape(p), p)
        # 나머지는 8080
        rest = frag[frag.index('# ③ '):]
        self.assertIn('reverse_proxy 127.0.0.1:8080', rest)

    def test_same_log_file_as_old_block(self):
        """새 기록 파일을 만들지 않는다 — validate 를 root 로 돌려 기록 파일 주인이 root 가 되는 함정(README 2번)."""
        logs = re.findall(r'output file (\S+)', cs.fragment(cs.SWITCH))
        self.assertEqual(logs, re.findall(r'output file (\S+)', cs.fragment(cs.UNSWITCH)))

    def test_streaming_kept(self):
        frag = cs.fragment(cs.SWITCH)
        self.assertEqual(frag.count('flush_interval -1'), 2)
        self.assertEqual(frag.count('read_timeout 0'), 2)

    def test_redirect_targets_exist_in_v2(self):
        app = read(os.path.join(REPO, 'v2', 'server', 'app.py'))
        web = os.path.join(REPO, 'v2', 'web')
        self.assertTrue(os.path.isfile(os.path.join(web, 'controller', 'index.html')))
        self.assertTrue(os.path.isfile(os.path.join(web, 'controller', 'editor', 'index.html')))
        self.assertTrue(os.path.isfile(os.path.join(web, 'controller', 'sig.html')))
        self.assertTrue(os.path.isfile(os.path.join(web, 'controller', 'console.html')))
        self.assertTrue(os.path.isfile(os.path.join(web, 'streamdeck', 'index.html')))
        self.assertIn("@app.get('/health')", app)
        sigadmin = read(os.path.join(REPO, 'v2', 'server', 'domain', 'sigadmin.py'))
        self.assertIn("@route('/mobile'", sigadmin)
        pub = read(os.path.join(REPO, 'v2', 'server', 'domain', 'ops_public.py'))
        for p in ('/api/signatures/board', '/api/oraksil/donors', '/privacy', '/terms'):
            self.assertIn("@route('%s'" % p, pub)


class Tool(unittest.TestCase):
    def test_apply_touches_only_big_host(self):
        for nl in ('\n', '\r\n'):
            text = server_caddyfile(nl)
            new = cs.swap(text, 'apply')
            before = cs.top_blocks(text)
            after = cs.top_blocks(new)
            self.assertEqual([b['addrs'] for b in before], [b['addrs'] for b in after])
            for b in before:
                if b['addrs'] != [cs.HOST]:
                    self.assertEqual(text[b['start']:b['end']], block_text(new, b['addrs']))
            self.assertIn(HOMEPAGE.replace('\n', nl), new)
            self.assertIn(CREW.replace('\n', nl), new)
            self.assertEqual(block_text(new, [cs.HOST]).replace('\r\n', '\n'), cs.fragment(cs.SWITCH))
            if nl == '\n':
                self.assertNotIn('\r\n', new)
            else:
                self.assertEqual(new.count('\n'), new.count('\r\n'))

    def test_apply_then_revert_is_original(self):
        text = server_caddyfile()
        self.assertEqual(cs.swap(cs.swap(text, 'apply'), 'revert'), text)

    def test_refuses_twice_and_wrong_way(self):
        text = server_caddyfile()
        with self.assertRaises(cs.SwitchError):
            cs.swap(text, 'revert')
        new = cs.swap(text, 'apply')
        with self.assertRaises(cs.SwitchError):
            cs.swap(new, 'apply')

    def test_refuses_missing_or_double_host(self):
        no_host = '{\n}\n' + HOMEPAGE + '\n'
        with self.assertRaises(cs.SwitchError):
            cs.swap(no_host, 'apply')
        old = read(os.path.join(REPO, 'deploy', 'Caddyfile'))
        with self.assertRaises(cs.SwitchError):
            cs.swap(old + '\n' + old, 'apply')

    def test_broken_braces(self):
        with self.assertRaises(cs.SwitchError):
            cs.top_blocks('a.example {\n\tfoo\n')
        with self.assertRaises(cs.SwitchError):
            cs.top_blocks('a.example {\n}\n}\n')

    def test_placeholders_quotes_comments_not_counted(self):
        blocks = cs.top_blocks(server_caddyfile())
        self.assertEqual([b['addrs'] for b in blocks],
                         [[], [cs.HOST], [cs.HOST + ':8443'], ['angelcompany.me', 'www.angelcompany.me'], ['crew.angelcompany.me']])

    def test_cli_never_overwrites_original(self):
        d = tempfile.mkdtemp(prefix='lm2-caddy-')
        try:
            src = os.path.join(d, 'Caddyfile')
            with open(src, 'w', encoding='utf-8', newline='') as f:
                f.write(server_caddyfile())
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cs.main(['apply', src, src]), 1)
            self.assertEqual(read(src), server_caddyfile())
            dst = os.path.join(d, 'Caddyfile.new')
            with redirect_stdout(out):
                self.assertEqual(cs.main(['apply', src, dst]), 0)
            self.assertEqual(read(src), server_caddyfile())
            self.assertIn(cs.MARK, read(dst))
            back = os.path.join(d, 'Caddyfile.back')
            with redirect_stdout(out):
                self.assertEqual(cs.main(['revert', dst, back]), 0)
                self.assertEqual(cs.main(['status', back]), 0)
                self.assertEqual(cs.main(['bogus']), 2)
            self.assertEqual(read(back), server_caddyfile())
            self.assertIn('caddy validate', out.getvalue())
            self.assertIn('sudo -u caddy', out.getvalue())       # root 로 validate 하지 않게 안내
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
