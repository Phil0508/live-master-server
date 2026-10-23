# -*- coding: utf-8 -*-
"""💸 후원 콘솔 따로 열기(controller/console.html · js/consolepage.js) — 옛 manual_send.html(/manual)을 v2 로(대표님 10-24).

지키는 것
  - 옛 주소 /manual · /manual_send · /manual_send.html → /controller/console.html (302) · 그 화면이 실제로 열린다
  - 옛 탭 여섯이 **같은 순서 · 같은 이름**으로 있다(옛 파일에서 읽어 맞대 본다)
  - 각 탭 속은 조종실 탭을 그대로 얹는다(새로 만든 사본이 아니다) — 부르는 파일 · 이름이 정말 있다
  - 탭들이 보내는 명령이 서버에 정말 있다 · 옛 페이지가 부르던 주소가 v2 에도 있다
  - 바깥(CDN) 없음 · alert()/confirm() 없음 · 소리 없음 · 바깥 글자를 innerHTML 로 안 넣는다
화면은 헤드리스 크롬으로 따로 본다(보고서). 여기서는 서버 길 · 파일만 본다.
"""
import os
import re
import unittest

from v2.tests.test_flow import Base

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CTL = os.path.join(ROOT, 'v2', 'web', 'controller')
WEB = os.path.join(ROOT, 'v2', 'web')

OLD_TABS = ['수동 송출', '대기열', '후원 순위', '이펙트', '고액 영상', '시그니처 관리']


def read(*p):
    with open(os.path.join(*p), encoding='utf-8') as f:
        return f.read()


def code(src):
    """주석을 뺀 글(// 줄 · /* */ 묶음) — 설명 글에 든 낱말에 속지 않게"""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', src)


def imports(src):
    """import { a, b as c } from './x.js' → [('./x.js', ['a', 'b'])]"""
    out = []
    for names, spec in re.findall(r"""^import\s*\{([^}]*)\}\s*from\s*'([^']+)'""", src, re.M):
        out.append((spec, [n.strip().split(' as ')[0].strip() for n in names.split(',') if n.strip()]))
    return out


def exported(path):
    src = read(path)
    names = set(re.findall(r'^export\s+(?:async\s+)?(?:function|const|let|class)\s+([A-Za-z_$][\w$]*)', src, re.M))
    for grp in re.findall(r'^export\s*\{([^}]*)\}', src, re.M):
        for n in grp.split(','):
            n = n.strip()
            if n:
                names.add(n.split(' as ')[-1].strip())
    return names


class OldAddresses(Base):
    def test_manual_redirects(self):
        for p in ('/manual', '/manual_send', '/manual_send.html'):
            r = self.c.get(p, follow_redirects=False)
            self.assertEqual((r.status_code, r.headers['location']), (302, '/controller/console.html'), p)
        # 열쇠(?token=)는 주소에 실어 보내지 않는다(옛 /upload · /mobile 과 같다)
        r = self.c.get('/manual?token=abc', follow_redirects=False)
        self.assertEqual(r.headers['location'], '/controller/console.html')

    def test_page_served(self):
        r = self.c.get('/controller/console.html')
        self.assertEqual(r.status_code, 200)
        self.assertIn('./js/consolepage.js', r.text)
        self.assertEqual(r.headers.get('cache-control'), 'no-cache')        # 고친 화면이 바로 먹게(app.py)
        for p in ('/controller/js/consolepage.js', '/controller/css/console.css'):
            self.assertEqual(self.c.get(p).status_code, 200, p)

    def test_old_upload_still_goes_to_sig_page(self):
        r = self.c.get('/upload', follow_redirects=False)
        self.assertEqual(r.headers['location'], '/controller/sig.html')


class PageFiles(unittest.TestCase):
    def setUp(self):
        self.html = read(CTL, 'console.html')
        self.js = read(CTL, 'js', 'consolepage.js')

    def test_html_refs_exist(self):
        refs = re.findall(r'''(?:href|src)="(\./[^"]+|/shared/[^"]+|/vendor/[^"]+)"''', self.html)
        self.assertIn('./js/consolepage.js', refs)
        self.assertIn('/shared/client.js', refs)
        for ref in refs:
            if ref.startswith('./'):
                p = os.path.join(CTL, *ref[2:].split('/'))
            elif ref.startswith('/shared/'):
                p = os.path.join(WEB, *ref[1:].split('/'))
            else:
                p = os.path.join(ROOT, *ref[1:].split('/'))
            self.assertTrue(os.path.isfile(p), ref)
        # 탭 속이 쓰는 생김새 — 조종실 index.html 과 같은 파일
        for css in ('controller.css', 'css/tools_ops.css', 'css/tools_bank.css', 'css/tools_cast.css', 'css/tools_records.css',
                    'css/donate.css', 'css/tools_sig.css', 'css/console.css'):
            self.assertIn('./' + css, self.html, css)
        self.assertIn('type="module"', self.html)
        self.assertIn('id="cp-root"', self.html)
        self.assertIn('id="cp-down"', self.html)
        self.assertIn('href="/controller/"', self.html)                     # ← 조종실
        self.assertIn('<title>후원 콘솔 · 라이브 마스터</title>', self.html)     # 옛 제목 그대로

    def test_no_outside_cdn(self):
        self.assertIsNone(re.search(r'''(?:href|src)="https?://''', self.html))
        self.assertNotIn('cdnjs', self.html)
        self.assertNotIn('font-awesome', self.html)

    def test_imports_resolve(self):
        got = imports(self.js)
        self.assertTrue(got)
        for spec, names in got:
            p = os.path.normpath(os.path.join(CTL, 'js', *spec.split('/')))
            self.assertTrue(os.path.isfile(p), spec)
            have = exported(p)
            for n in names:
                self.assertIn(n, have, '%s 에 %s 가 없다' % (spec, n))

    def test_reuses_controller_panels(self):
        """새로 만든 사본이 아니라 조종실 탭을 그대로 얹는다"""
        want = {
            './panels/ops/console.js': 'mountConsole',          # 수동 송출(+ 🏦 계좌 입금 추천 · 열쇠)
            './panels/ops/bank.js': 'bankBadge',                # 수동 송출 탭 '🏦 N'
            './panels/ops/bankmirror.js': 'mountBankMirror',    # 은행 확장 거울 · 폰 앱
            './queue.js': 'mountQueue',                         # 대기열
            './panels/records/donors.js': 'mountDonors',        # 후원 순위
            './panels/ops/opfx.js': 'mountOpFx',                # 이펙트
            './panels/ops/media.js': 'mountMedia',              # 고액 영상
            './panels/sig/admin.js': 'mountSigAdmin',           # 시그니처 관리
            './login.js': 'mountLogin',                         # 로그인 안 됐으면 여기서 바로
        }
        got = dict((s, n) for s, n in imports(self.js))
        for spec, name in want.items():
            self.assertIn(spec, got, spec)
            self.assertIn(name, got[spec], spec)
        only = code(self.js)
        self.assertIn('mountConsole(el, ctx, { solo: true })', only)
        self.assertIn("window.LM.connect({ kind: 'console' })", only)        # 🖥️ 시스템 탭에 '💸 후원 콘솔' 로 보인다
        from v2.server import hub
        self.assertIn('console', hub.KINDS)
        # 보내는 길은 하나 — 이 페이지에 송출 · 장부 주소를 따로 쓰지 않는다
        for bad in ('/api/donation', '/api/signature/play', 'lm.cmd('):
            self.assertNotIn(bad, only, bad)

    def test_old_tabs_same_order_and_names(self):
        old = read(ROOT, 'manual_send.html')
        old_labels = [re.sub(r'<[^>]+>', '', m).strip() for m in
                      re.findall(r'''<button class="tab[^"]*" id="tab-btn-\w+"[^>]*>(.*?)</button>''', old)]
        old_labels = [re.sub(r'\s*\d+\s*$', '', x).strip() for x in old_labels]          # 배지 숫자(0) 떼기
        self.assertEqual(old_labels, OLD_TABS)
        labels = re.findall(r"""\{\s*id:\s*'[a-z]+',\s*label:\s*'([^']+)'""", self.js)
        self.assertEqual(labels, OLD_TABS)
        # 배지 — 수동 송출 '🏦 N'(아직 안 쓴 계좌 입금) · 대기열 수
        self.assertRegex(self.js, r"id: 'send',[^\n]*badge: bankBadge")
        self.assertRegex(self.js, r"id: 'queue',[^\n]*badge: queueBadge")

    def test_last_tab_remembered_safely(self):
        only = code(self.js)
        self.assertIn("const KEY = 'lm2_console_tab';", self.js)
        # localStorage 는 개인 창 등에서 던진다 — 읽기 · 쓰기 모두 try 안에서
        for m in re.finditer(r'localStorage\.(?:getItem|setItem)', only):
            line = only[only.rfind('\n', 0, m.start()) + 1:only.find('\n', m.end())]
            self.assertIn('try', line, line.strip())

    def test_no_alert_confirm_sound_innerhtml(self):
        only = code(self.js)
        self.assertIsNone(re.search(r'(?<![\w.])(alert|confirm|prompt)\(', only))
        for bad in ('innerHTML', 'new Audio', 'AudioContext', '.play()', 'navigator.vibrate'):
            self.assertNotIn(bad, only, bad)

    def test_page_css(self):
        css = read(CTL, 'css', 'console.css')
        for cls in ('.cp-tabs', '.cp-tab', '.cp-tab.on', '.tab-badge.q', '.cp-note', '.cp-qthumb', '.cp-stat', '.cp-more',
                    '[data-medal="1"]', '@media (max-width: 899px)'):
            self.assertIn(cls, css, cls)
        self.assertNotIn('http', re.sub(r'/\*.*?\*/', '', css, flags=re.S))   # 바깥에서 불러오는 것 없음


class Parity(unittest.TestCase):
    """옛 후원 콘솔이 하던 일을 v2 탭들이 정말 한다 — 명령 · 주소가 서버에 있다"""
    PANELS = [('js', 'panels', 'ops', 'console.js'), ('js', 'panels', 'ops', 'bank.js'), ('js', 'panels', 'ops', 'bankmirror.js'),
              ('js', 'queue.js'), ('js', 'panels', 'records', 'donors.js'), ('js', 'panels', 'ops', 'opfx.js'),
              ('js', 'panels', 'ops', 'media.js'), ('js', 'panels', 'sig', 'admin.js'), ('js', 'panels', 'sig', 'form.js'),
              ('js', 'panels', 'sig', 'history.js')]

    def test_commands_exist(self):
        from v2.server import domain  # noqa: F401
        from v2.server.bus import COMMANDS
        sent = set()
        for p in self.PANELS:
            sent |= set(re.findall(r"""ctx\.run\(\s*'([a-z_]+\.[a-z_]+)'""", read(CTL, *p)))
        # 옛 탭의 단추들: 대기열(멈춤 · 건너뛰기 · 전부 지우기 · 빼기) · 이펙트(쏘기 · 걷기) · 고액 영상(틀기 · 멈추기) · 순위에서 빼기
        for must in ('reaction.pause', 'reaction.skip', 'reaction.stop', 'reaction.remove', 'cast.fx', 'cast.fx_clear',
                     'acctvid.play', 'acctvid.stop', 'donor.exclude'):
            self.assertIn(must, sent, must)
        for name in sent:
            self.assertIn(name, COMMANDS, name)

    def test_old_urls_still_answered(self):
        """옛 페이지가 부르던 주소 — 수동 송출 · 시그니처 목록 · 계좌 입금 추천 · 열쇠 · 시그니처 등록/고치기/지우기"""
        import shutil
        import tempfile
        from v2.server.app import create_app
        d = tempfile.mkdtemp(prefix='lm2console_')
        try:
            app = create_app(db_path=os.path.join(d, 'lm2.db'), password='pw', secret='secret-test-0123456789', sig_fetch=lambda: [])
            try:
                have = {getattr(r, 'path', '') for r in app.routes}
            finally:
                app.state.store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)
        for p in ('/api/donation', '/api/signature/play', '/api/signatures', '/api/bank/inbox', '/api/bank/inbox/{iid}/{act}',
                  '/api/bank/key', '/api/bank/key/reset', '/api/signatures/add', '/api/signatures/update/{sig_id}',
                  '/api/signatures/delete/{sig_id}', '/manual', '/manual_send', '/manual_send.html'):
            hit = p in have or any(re.sub(r'\{[^}]+\}', '{}', p) == re.sub(r'\{[^}]+\}', '{}', h) for h in have)
            self.assertTrue(hit, p)

    def test_controller_tab_links_here(self):
        con = read(CTL, 'js', 'panels', 'ops', 'console.js')
        self.assertIn("href: '/controller/console.html'", con)               # 조종실 후원 콘솔 탭 [따로 열기 ↗]
        self.assertIn('withSoloLink(blockHead(', con)
        self.assertIn('if (!solo) head.append(', con)                        # 따로 연 페이지 안에서는 안 붙인다


if __name__ == '__main__':
    unittest.main()
