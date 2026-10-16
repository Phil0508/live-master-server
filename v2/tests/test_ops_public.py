# -*- coding: utf-8 -*-
"""🌐 로그인 없는 바깥 주소 — 옛 프로그램과 **같은 답**을 주는지, 옛 코드를 실제로 돌려 맞대 본다.

옛 코드(features/signature_play.py · archive.py · legal.py)는 server.py(Flask · DB)에 기대어 그대로는 못 부른다.
그래서 가짜 server 모듈을 끼워 옛 파일을 **그대로** 읽어 들이고, 옛 셈에 쓰는 도우미(_as_int · _bc_window · _norm_donor ·
is_excluded …)는 옛 파일에서 함수 글자를 그대로 꺼내 쓴다(베끼지 않는다 — 옛 것이 바뀌면 이 검사가 알아챈다).
  📜 /api/signatures/board  — 같은 시그 목록 → 같은 줄 · 칸(번호 없음) · 금액 순 · 1분 기억 · 못 읽으면 지난 답/502
  🏆 /api/oraksil/donors    — 옛 검사(tests/oraksil_donors_test.py)와 같은 후원들 → 옛 답과 같다 · 테스트 계정 · 화면에만 · 익명 · 뺀 이름 제외
  📄 /privacy · /terms      — 옛 글과 글자 하나까지 같다
Flask 가 없는 PC 에서는 '옛 것과 맞대기' 만 건너뛰고, v2 쪽 검사는 그대로 돈다.
"""
import ast
import calendar
import contextlib
import datetime
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain import ops_public as op

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PW, SECRET = 'pw-test', 'secret-test-0123456789'
H = {'Authorization': 'Bearer ' + SECRET}

try:
    import flask  # noqa: F401
    HAVE_FLASK = os.path.exists(os.path.join(REPO, 'server.py'))
except Exception:
    HAVE_FLASK = False


def grab(relpath, *names):
    """옛 파일에서 이름 붙은 함수 · 값 줄을 글자 그대로 꺼낸다."""
    with open(os.path.join(REPO, relpath), encoding='utf-8') as f:
        src = f.read()
    out = []
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            out.append(ast.get_source_segment(src, node))
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            out.append(ast.get_source_segment(src, node))
    return '\n\n'.join(out)


def old_helpers(excluded=()):
    ns = {'os': os, 'datetime': datetime, 'time': time, 'excluded_names': lambda: set(excluded)}
    exec(grab('server.py', '_as_int', 'BC_START_H', 'BC_END_H', '_bc_shift_hours', '_bc_window', 'ts_kst'), ns)
    exec(grab('features/donor_memory.py', '_norm_donor'), ns)
    exec(grab('features/excluded.py', 'is_excluded'), ns)
    return ns


def load_old(relpath, **attrs):
    """가짜 server 모듈을 끼워 옛 파일을 그대로 불러온다."""
    from flask import Flask
    fake = types.ModuleType('server')
    fake.app = Flask('old_' + os.path.basename(relpath).replace('.py', ''))
    fake.__dict__.update(attrs)
    name = 'old_ops_' + relpath.replace('/', '_').replace('.py', '')
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, relpath))
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {'server': fake}):
        spec.loader.exec_module(mod)
    return mod, fake


SIGS = [
    {'id': 7, 'amount': 50000, 'title': ' 대박 ', 'image_url': 'https://x/7.png', 'sound_url': 'https://x/7.mp3', 'duration': 9},
    {'id': 3, 'amount': 10000, 'title': '만원', 'image_url': None, 'sound_url': 'https://x/3.mp3', 'duration': 5},
    {'id': 9, 'amount': '30000', 'title': '삼만', 'image_url': 'https://x/9.png', 'sound_url': '', 'duration': 5},
    {'id': 4, 'amount': 30000, 'title': '가나다', 'image_url': '', 'sound_url': None, 'duration': 5},
    {'id': 5, 'amount': 0, 'title': '공짜', 'image_url': '', 'sound_url': '', 'duration': 1},
    {'id': 6, 'amount': -5, 'title': '음수', 'image_url': '', 'sound_url': '', 'duration': 1},
    {'id': 8, 'amount': 20000.0, 'title': None, 'image_url': 'https://x/8.png', 'sound_url': 'https://x/8.mp3', 'duration': 2},
]


class App(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2ops_pub_')
        self.sigs = list(SIGS)
        self.fail = False

        def fetch():
            if self.fail:
                raise ConnectionError('supabase down')
            return [dict(s) for s in self.sigs]
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET, sig_fetch=fetch))
        self.bus = self.c.app.state.bus

    def tearDown(self):
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)


class Board(App):
    def test_public_shape_order(self):
        r = self.c.get('/api/signatures/board')                     # 로그인 없이
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(list(d), ['status', 'rows', 'count'])
        self.assertEqual(d['status'], 'success')
        self.assertEqual([(x['amount'], x['title']) for x in d['rows']],
                         [(10000, '만원'), (20000, ''), (30000, '가나다'), (30000, '삼만'), (50000, '대박')])
        self.assertTrue(all(set(x) == {'amount', 'title', 'image_url', 'sound_url'} for x in d['rows']))   # 번호(id) 없음
        self.assertEqual(d['rows'][0]['image_url'], '')                       # None → ''
        self.assertEqual(d['count'], 5)
        self.assertEqual(r.headers.get('cache-control'), 'public, max-age=60')
        self.assertTrue(r.text.startswith('{"status":"success","rows":['), r.text[:60])   # README ⑥ 확인 줄이 이 모양을 적어 둠

    @unittest.skipUnless(HAVE_FLASK, '옛 서버(Flask)가 없어 맞대기는 건너뛴다')
    def test_same_as_old(self):
        ns = old_helpers()
        old, fake = load_old('features/signature_play.py', _as_int=ns['_as_int'], broadcast_event=None, enqueue_signature=None,
                             file_lock=None, load_data=None, request_is_authed=lambda: False, save_data=None,
                             supabase_list_signatures=lambda: [dict(s) for s in SIGS])
        want = fake.app.test_client().get('/api/signatures/board').get_json()
        got = self.c.get('/api/signatures/board').json()
        self.assertEqual(got, want)

    def test_one_minute_memory_then_new(self):
        first = self.c.get('/api/signatures/board').json()['rows']
        self.sigs.append({'id': 11, 'amount': 70000, 'title': '새시그', 'image_url': '', 'sound_url': ''})
        self.bus.sigs.refresh()
        self.assertEqual(self.c.get('/api/signatures/board').json()['rows'], first)      # 1분 안 — 같은 답
        self.bus.ops_public_cache['board']['t'] = 0
        self.assertEqual(self.c.get('/api/signatures/board').json()['rows'][-1]['title'], '새시그')

    def test_fail_keeps_last_then_502_if_never(self):
        first = self.c.get('/api/signatures/board').json()['rows']
        self.fail = True
        self.bus.sigs.refresh()
        self.bus.ops_public_cache['board']['t'] = 0
        r = self.c.get('/api/signatures/board')
        self.assertEqual((r.status_code, r.json()['rows']), (200, first))                # 못 읽으면 지난 답
        self.bus.ops_public_cache['board'].update(t=0, rows=None)
        self.bus.sigs._rows, self.bus.sigs._at = None, 0
        r = self.c.get('/api/signatures/board')
        self.assertEqual((r.status_code, r.json()), (502, {'status': 'error', 'message': '시그 목록을 못 읽었어요', 'rows': []}))

    def test_get_only(self):
        self.assertEqual(self.c.post('/api/signatures/board', json={}).status_code, 405)


# 옛 검사(tests/oraksil_donors_test.py)와 같은 후원들 — 시각은 UTC 글자(옛 장부 모양), KST 는 +9
ARCHIVE = [
    ('2026-10-07 09:00:00', '구름빵', 500000, 'toonation'),      # 수 18:00 KST → 10-07
    ('2026-10-07 17:30:00', '구름빵님', 200000, 'toonation'),    # 목 02:30 KST → 10-07 (같은 사람)
    ('2026-10-07 18:00:00', '구름빵', 1000, 'toonation'),        # 목 03:00 KST → 창 밖(정각은 끝)
    ('2026-10-07 08:00:00', '바람', 30000, 'manual'),            # 수 17:00 KST → 창 안(정각은 시작)
    ('2026-10-07 07:59:59', '바람', 99000, 'toonation'),         # 수 16:59 KST → 창 밖
    ('2026-10-07 10:00:00', '익명', 50000, 'toonation'),
    ('2026-10-07 10:00:00', ' 익명님 ', 50000, 'toonation'),
    ('2026-10-07 10:05:00', '빼둔이', 70000, 'toonation'),       # 순위에서 뺀 이름
    ('2026-10-07 10:06:00', '영원', 0, 'toonation'),             # 0원
]
HISTORY = [
    ('2026-10-14 09:00:00', '새손님', 30000, 'toonation'),
    ('2026-10-14 09:10:00', '새손님', 20000, 'toonation'),
    ('2026-10-14 09:20:00', '테스터', 99999, 'toonation_test'),  # 테스트 계정 — 뺀다
    ('2026-10-14 09:30:00', '구름빵', 10000, 'toonation'),
    ('2026-10-11 09:00:00', '일요일', 10000, 'toonation'),       # 일요일 — 창 밖
]
WANT = [
    {'day': '2026-10-14', 'name': '새손님', 'amount': 50000, 'count': 2},
    {'day': '2026-10-14', 'name': '구름빵', 'amount': 10000, 'count': 1},
    {'day': '2026-10-07', 'name': '구름빵', 'amount': 700000, 'count': 2},
    {'day': '2026-10-07', 'name': '바람', 'amount': 30000, 'count': 1},
]


def epoch(utc_text):
    return float(calendar.timegm(time.strptime(utc_text, '%Y-%m-%d %H:%M:%S')))


class Oraksil(App):
    def put(self, rows, status, session='s'):
        n = self.bus.store.db.execute('SELECT COUNT(*) FROM donations').fetchone()[0]
        for i, (ts, nm, amt, src) in enumerate(rows):          # 장부는 자동 저장(isolation_level=None)
            self.bus.store.add_donation({'id': 'd%d' % (n + i), 'tx_id': 't%d' % (n + i), 'at': epoch(ts), 'name': nm, 'amount': amt,
                                         'message': '비밀메시지', 'source': src, 'status': status, 'player': None, 'session': session})

    def fill(self):
        self.put(ARCHIVE, 'archived', 'old-1')
        self.put(HISTORY[:2], 'assigned')
        self.put(HISTORY[2:3], 'pending')
        self.put(HISTORY[3:], 'ignored')
        self.put([('2026-10-14 09:40:00', '소액손님', 5000, 'display')], 'display')    # 화면에만 — 장부 합계에 안 센다
        r = self.c.post('/api/cmd', json={'type': 'donor.exclude', 'data': {'name': '빼둔이'}}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)

    def test_same_as_old_test_cases(self):
        self.fill()
        r = self.c.get('/api/oraksil/donors')                      # 로그인 없이
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'rows': WANT})
        body = r.text
        self.assertTrue('비밀메시지' not in body and '09:00' not in body and 'toonation' not in body and 'manual' not in body)

    @unittest.skipUnless(HAVE_FLASK, '옛 서버(Flask)가 없어 맞대기는 건너뛴다')
    def test_same_as_old_code(self):
        """옛 api_oraksil_donors 를 옛 장부 모양(UTC 글자 · BROADCAST_TZ_SHIFT=9)으로 그대로 돌린 답 = v2 답."""
        self.fill()
        extra = [('2026-10-14 09:45:00', '이름  띄움 ', 40000, 'toonation'),     # 보여줄 이름은 빈칸을 다듬은 원래 이름
                 ('2026-10-14 09:46:00', '이름 띄움님', 1000, 'toonation')]
        self.put(extra, 'assigned')
        db = os.path.join(self.dir, 'old.db')
        con = sqlite3.connect(db)
        for t in ('donation_archive', 'donation_history'):
            con.execute('CREATE TABLE %s (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, name TEXT, amount INTEGER, source TEXT)' % t)
        con.executemany('INSERT INTO donation_archive (timestamp, name, amount, source) VALUES (?,?,?,?)', ARCHIVE)
        con.executemany('INSERT INTO donation_history (timestamp, name, amount, source) VALUES (?,?,?,?)', HISTORY + extra)
        con.commit()
        con.close()
        ns = old_helpers(excluded={'빼둔이'})
        old, fake = load_old('features/archive.py', BC_START_H=ns['BC_START_H'], BC_END_H=ns['BC_END_H'],
                             _bc_shift_hours=ns['_bc_shift_hours'], _bc_window=ns['_bc_window'], _norm_donor=ns['_norm_donor'],
                             db_query=lambda q: q, get_db_connection=lambda: contextlib.closing(sqlite3.connect(db)),
                             is_excluded=ns['is_excluded'], request_is_authed=lambda: False, ts_kst=ns['ts_kst'])
        with mock.patch.dict(os.environ, {'BROADCAST_TZ_SHIFT': '9'}):
            want = fake.app.test_client().get('/api/oraksil/donors').get_json()
        got = self.c.get('/api/oraksil/donors').json()
        self.assertEqual(got, want)
        self.assertIn({'day': '2026-10-14', 'name': '이름 띄움', 'amount': 41000, 'count': 2}, got['rows'])

    def test_memory_then_new_then_fail(self):
        self.fill()
        first = self.c.get('/api/oraksil/donors').json()['rows']
        self.put([('2026-10-14 10:00:00', '늦게온', 40000, 'toonation')], 'pending')
        self.assertEqual(self.c.get('/api/oraksil/donors').json()['rows'], first)     # 1분 안 — 같은 답
        self.bus.ops_public_cache['donors']['t'] = 0
        now = self.c.get('/api/oraksil/donors').json()['rows']
        self.assertIn({'day': '2026-10-14', 'name': '늦게온', 'amount': 40000, 'count': 1}, now)
        with mock.patch.object(op, '_ledger', side_effect=sqlite3.OperationalError('locked')):
            self.bus.ops_public_cache['donors']['t'] = 0
            r = self.c.get('/api/oraksil/donors')
            self.assertEqual((r.status_code, r.json()['rows']), (200, now))         # 못 읽으면 지난 답
            self.bus.ops_public_cache['donors'].update(t=0, rows=None)
            r = self.c.get('/api/oraksil/donors')
            self.assertEqual((r.status_code, r.json()), (502, {'rows': [], 'message': '후원 장부를 못 읽었어요'}))

    def test_get_only_and_empty(self):
        self.assertEqual(self.c.get('/api/oraksil/donors').json(), {'rows': []})
        self.assertEqual(self.c.post('/api/oraksil/donors', json={}).status_code, 405)

    def test_pure_rules(self):
        kst = datetime.timezone(datetime.timedelta(hours=9))
        wed = datetime.datetime(2026, 10, 14, 20, 0, tzinfo=kst).timestamp()
        rows = [(wed, '가', 10000, 'toonation'), (wed, '가님', '5000', 'manual'), (wed, '나', 'x', 'toonation'),
                (wed, '', 9000, 'toonation'), (wed, '다', 3000, 'toonation_test'), (wed + 86400 * 2, '라', 1000, 'toonation')]
        self.assertEqual(op.oraksil_rows(rows, set()), [{'day': '2026-10-14', 'name': '가', 'amount': 15000, 'count': 2}])


class ProxiedDonation(App):
    """Caddyfile.switch 가 큰 주소의 /api/donation 을 v2 로 넘긴다 — Caddy 를 거친 요청(X-Forwarded-For)은 '이 서버 안' 이 아니다.
    로그인 · X-Donation-Key 없이 바깥에서 부르면 401 이고 장부에 한 줄도 안 생겨야 한다(가짜 후원으로 돈 · 점수가 바뀌지 않게)."""

    class Req:
        def __init__(self, host, headers):
            self.client = types.SimpleNamespace(host=host)
            self.headers = headers

    def test_local_only_without_proxy_headers(self):
        from v2.server.domain import legacy_routes as lr
        self.assertTrue(lr._local(self.Req('127.0.0.1', {})))                                   # 리스너(같은 서버)
        self.assertFalse(lr._local(self.Req('127.0.0.1', {'x-forwarded-for': '203.0.113.9'})))  # Caddy 를 거친 바깥 요청
        self.assertFalse(lr._local(self.Req('127.0.0.1', {'x-real-ip': '203.0.113.9'})))
        self.assertFalse(lr._local(self.Req('203.0.113.9', {})))

    def test_outside_without_key_refused_and_nothing_written(self):
        with mock.patch.dict(os.environ, {'DONATION_KEY': 'k-ops'}):
            r = self.c.post('/api/donation', json={'name': '가짜', 'amount': 500000, 'tx_id': 'toon_fake1'},
                            headers={'X-Forwarded-For': '203.0.113.9'})
            self.assertEqual(r.status_code, 401)
            r = self.c.post('/api/donation', json={'name': '가짜', 'amount': 500000, 'tx_id': 'toon_fake2'},
                            headers={'X-Forwarded-For': '203.0.113.9', 'X-Donation-Key': 'wrong'})
            self.assertEqual(r.status_code, 401)
        self.assertEqual(self.bus.store.db.execute('SELECT COUNT(*) FROM donations').fetchone()[0], 0)


class Legal(App):
    def test_public_html(self):
        for p, title in (('/privacy', '개인정보처리방침'), ('/terms', '서비스 약관')):
            r = self.c.get(p)
            self.assertEqual(r.status_code, 200, p)
            self.assertTrue(r.headers['content-type'].startswith('text/html'))
            self.assertIn('<title>%s · 엔젤컴퍼니</title>' % title, r.text)

    @unittest.skipUnless(HAVE_FLASK, '옛 서버(Flask)가 없어 맞대기는 건너뛴다')
    def test_same_text_as_old(self):
        old, fake = load_old('features/legal.py', serve_html_file=lambda name: name)
        self.assertEqual(self.c.get('/privacy').text, old.serve_privacy())
        self.assertEqual(self.c.get('/terms').text, old.serve_terms())


if __name__ == '__main__':
    unittest.main()
