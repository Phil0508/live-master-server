# -*- coding: utf-8 -*-
"""v2 🎆 방송판 시그니처 연출 · 미리받기 · 📺 따로 띄우는 화면(10-17 이사 — sigfx 갈래).

- 공개 시그니처 목록(/api/sigfx/sigs): 로그인 없이 · 칸은 id · 그림 · 소리 · 길이만(이름 · 금액 없음 · 순서 섞음 — 옛 _PUBLIC_SIG_FIELDS) · 못 읽으면 빈 목록.
- 옛 주소(/alertbox · /signature-display · /slot)를 열면 방송판 ?only= 화면으로(뒤 ?… 그대로).
- 연출 파일 · 화면 파일이 나간다. 따로 띄운 화면은 서버가 '방송판' 과 따로 센다(점검표가 OBS 방송판을 잘못 세지 않게).
- 연출 규칙(어떤 시그에 어떤 연출 · 계엄령 · 'OO업' · 카드 축소 시점 · 층 순서)은 node 로 순수 함수를 본다(v2/tests/js/sigfx_check.mjs).
- 옛 파일이 아직 저장소에 있으면 v2 사본이 글자 하나 안 다른지 · 옛 금액 표와 같은지 본다(갈아탄 뒤 옛 파일을 지우면 건너뛴다).
⚠️ 진짜 Supabase 는 안 부른다 — 가짜 목록(sig_fetch)을 넣는다.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain import sigfx as sf
from v2.tests.test_flow import PW, SECRET, H

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.dirname(HERE)
REPO = os.path.dirname(V2)
OVERLAY = os.path.join(V2, 'web', 'overlay')

SIGS = [{'id': 7, 'amount': 300000, 'title': '푸차', 'image_url': 'https://x/p.png', 'sound_url': 'https://x/p.mp3', 'duration': 12,
         'created_at': '2026-01-01', 'storage_path': 'images/7.png'},
        {'id': 3, 'amount': 10300, 'title': '사쿠란보', 'image_url': 'https://x/a.png', 'sound_url': 'https://x/a.mp3', 'duration': 8},
        {'id': 9, 'amount': None, 'title': '금액 없음'}]


class Base(unittest.TestCase):
    fetch = staticmethod(lambda: SIGS)

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2sigfx_')
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET,
                                       sig_fetch=type(self).fetch))

    def tearDown(self):
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)


class PublicList(Base):
    def test_no_login_only_public_fields(self):
        r = self.c.get('/api/sigfx/sigs')                       # 쿠키 · 열쇠 없이(방송판)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get('cache-control'), 'no-store')
        d = r.json()
        self.assertEqual(d['status'], 'success')
        self.assertEqual(d['count'], 2)                           # 금액 없는 줄은 보관소 목록(bus.sigs)이 이미 뺀다
        self.assertEqual(sorted(s['id'] for s in d['signatures']), [3, 7])
        for s in d['signatures']:
            # 이름 · 금액은 안 나간다(시그 뒤집기 카드 번호 → 이름 · 금액을 로그인 없이 못 알게 — 옛 것 그대로). 다른 칸도 안 나간다
            self.assertTrue(set(s) <= set(sf.PUBLIC_KEYS), s)
            self.assertNotIn('title', s)
            self.assertNotIn('amount', s)
        self.assertNotIn('푸차', r.text)
        self.assertNotIn('300000', r.text)
        by = {s['id']: s for s in d['signatures']}
        self.assertEqual(by[7]['sound_url'], 'https://x/p.mp3')
        self.assertEqual(by[7]['image_url'], 'https://x/p.png')

    def test_order_is_shuffled(self):
        rows = [{'id': i, 'amount': i * 1000} for i in range(30)]
        orders = {tuple(x['id'] for x in sf.public_rows(rows)) for _ in range(20)}
        self.assertGreater(len(orders), 1)                        # 금액순 그대로 내보내지 않는다(옛 random.shuffle)
        self.assertEqual(sorted(x['id'] for x in sf.public_rows(rows)), list(range(30)))

    def test_controller_list_still_needs_login(self):
        self.assertEqual(self.c.get('/api/signatures').status_code, 401)
        self.assertEqual(self.c.get('/api/signatures', headers=H).status_code, 200)

    def test_public_rows_shape(self):
        self.assertEqual(sf.public_rows([{'id': 1, 'amount': 5, 'title': 't', 'x': 1, 'image_url': 'i'}, 'bad'], shuffle=False),
                         [{'id': 1, 'image_url': 'i'}])
        self.assertEqual(sf.public_rows(None), [])
        self.assertEqual(set(sf.PUBLIC_KEYS), {'id', 'image_url', 'sound_url', 'duration'})


class PublicListDown(Base):
    @staticmethod
    def fetch():
        raise RuntimeError('보관소가 안 답함')

    def test_store_down_gives_empty_list(self):
        r = self.c.get('/api/sigfx/sigs')
        self.assertEqual((r.status_code, r.json()['count'], r.json()['signatures']), (200, 0, []))


class OldAddresses(Base):
    def test_redirects_keep_query(self):
        cases = {
            '/alertbox': '/overlay/?only=alert', '/alertbox.html?x=1': '/overlay/?only=alert&x=1',
            '/signature-display': '/overlay/?only=sig', '/signature-display.html': '/overlay/?only=sig',
            '/signature_display.html?transparent=1': '/overlay/?only=sig&transparent=1',
            '/slot': '/overlay/?only=slot', '/slot.html?only=alert&a=b': '/overlay/?only=slot&a=b',
        }
        for src, want in cases.items():
            r = self.c.get(src, follow_redirects=False)
            self.assertEqual((src, r.status_code, r.headers.get('location')), (src, 302, want))

    def test_view_url(self):
        self.assertEqual(sf.view_url('sig', ''), '/overlay/?only=sig')
        self.assertEqual(sf.view_url('sig', 'only=x&transparent=1'), '/overlay/?only=sig&transparent=1')

    def test_screen_files_served(self):
        for p in ('/overlay/sigfx/sig-fx.js', '/overlay/sigfx/sig-fx-gl.js', '/overlay/css/sigfx.css', '/overlay/groups/sigfx.js',
                  '/overlay/widgets/sigfx/stage.js', '/overlay/widgets/sigfx/warn.js', '/overlay/widgets/sigfx/rules.js',
                  '/overlay/widgets/sigfx/unlock.js', '/overlay/widgets/sigfx/sigdisp.js', '/vendor/sigfx/baton.webp'):
            self.assertEqual((p, self.c.get(p).status_code), (p, 200))
        html = self.c.get('/overlay/?only=alert').text
        self.assertIn('/overlay/css/sigfx.css', html)


class ViewKinds(Base):
    def test_alertbox_not_counted_as_overlay(self):
        with self.c.websocket_connect('/ws?kind=alertbox') as a, self.c.websocket_connect('/ws?kind=overlay') as o:
            self.assertEqual(a.receive_json()['t'], 'snapshot')
            self.assertEqual(o.receive_json()['t'], 'snapshot')
            kinds = sorted(s['kind'] for s in self.c.get('/api/screens', headers=H).json()['screens'])
            self.assertEqual(kinds, ['alertbox', 'overlay'])
            sc = self.c.get('/api/preflight', headers=H).json()['screens']
            self.assertEqual((sc['overlay'], sc['total']), (1, 2))      # 알림창은 '방송판' 으로 세지 않는다

    def test_sig_and_slot_kinds(self):
        from v2.server.hub import KINDS
        for k in ('alertbox', 'sigdisp', 'slot'):
            self.assertIn(k, KINDS)


@unittest.skipUnless(shutil.which('node'), 'node 가 없으면 건너뛴다')
class JsRules(unittest.TestCase):
    def test_rules_and_layers(self):
        p = subprocess.run(['node', os.path.join(HERE, 'js', 'sigfx_check.mjs')], capture_output=True, text=True,
                           encoding='utf-8', timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(p.stdout.strip().startswith('ok '), p.stdout)


class SameAsOld(unittest.TestCase):
    """옛 방송판이 저장소에 있는 동안 — v2 사본이 같은지(옛 것을 고치면 v2 도 같이 고치라는 경보)."""

    def test_lib_files_identical(self):
        for name in ('sig-fx.js', 'sig-fx-gl.js'):
            old = os.path.join(REPO, name)
            if not os.path.exists(old):
                self.skipTest('옛 파일이 없다(갈아탄 뒤)')
            with open(old, 'rb') as f1, open(os.path.join(OVERLAY, 'sigfx', name), 'rb') as f2:
                a, b = f1.read().replace(b'\r\n', b'\n'), f2.read().replace(b'\r\n', b'\n')
            self.assertEqual(a, b, name + ' 사본이 옛 것과 다르다')

    def test_public_fields_same_as_old(self):
        old = os.path.join(REPO, 'features', 'signature_play.py')
        if not os.path.exists(old):
            self.skipTest('옛 파일이 없다(갈아탄 뒤)')
        with open(old, encoding='utf-8') as f:
            m = re.search(r"_PUBLIC_SIG_FIELDS = \(([^)]*)\)", f.read())
        self.assertIsNotNone(m)
        self.assertEqual(tuple(re.findall(r"'(\w+)'", m.group(1))), sf.PUBLIC_KEYS)

    def test_amount_table_same_as_old(self):
        old = os.path.join(REPO, 'overlay.html')
        if not os.path.exists(old):
            self.skipTest('옛 방송판이 없다(갈아탄 뒤)')
        with open(old, encoding='utf-8') as f:
            src = f.read()
        m = re.search(r'const SIGFX_BY_AMOUNT = \{(.*?)\};', src, re.S)
        self.assertIsNotNone(m)
        want = dict((int(a), k) for a, k in re.findall(r"(\d+):\s*'(\w+)'", m.group(1)))
        with open(os.path.join(OVERLAY, 'widgets', 'sigfx', 'rules.js'), encoding='utf-8') as f:
            mine = f.read()
        m2 = re.search(r'export const SIGFX_BY_AMOUNT = \{(.*?)\};', mine, re.S)
        got = dict((int(a), k) for a, k in re.findall(r"(\d+):\s*'(\w+)'", m2.group(1)))
        self.assertEqual(got, want)
        self.assertIn('MARTIAL_LAW_AMOUNT = 250000', src)
        self.assertIn("opFxFire({ kinds: ['warn'], message: '주의 계엄령 발동' })", src)
        self.assertIn("MARTIAL_LAW_MESSAGE = '주의 계엄령 발동'", mine)


if __name__ == '__main__':
    unittest.main()
