# -*- coding: utf-8 -*-
"""🏦 v2 계좌 입금 추천 — 옛 tests/bank_memo_test.py · tests/bank_inbox_test.py 의 경우를 v2 로 옮겼다(10-17).

옛 동작이 정답이다: 같은 주소 · 같은 모양 · 같은 답(은행 확장 · 폰 앱을 안 고친다).
  · 메모 나누기(예전 닉네임 · 첫 낱말 · 선수 이름 앞 자르기 · AI 결과 거르기)
  · 열쇠: 로그인해야 받는다 · 틀린 열쇠 · 열쇠 없음은 401 · 새 열쇠를 만들면 옛 열쇠는 막힌다 · 옛 서버 열쇠 파일을 그대로 쓴다
  · 같은 입금(ref)은 한 번만 · 빈 목록은 '살아 있음' 신호 · 이상한 금액 · 모양은 거른다 · 1분 60번 넘으면 429
  · 배정 예상('밍밍 ＋?')은 답을 보낸 뒤에 붙는다 · 송출 · 숨김 · 되살림
  · 실명은 방송판 · 조각 · 명령 기록에 안 나간다 · 열쇠는 답 · 기록에 끝 네 글자까지만
  · 🪞 거울 · 명령 · 📱 앱 받기
AI 는 부르지 않는다(LM2_AI_OFF · 가짜 ai_post).
"""
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain import ai
from v2.server.domain import bank
from v2.server.domain import donor_memory as dm
from v2.server.domain.bank_memo import ai_split_ok, clean, split_memo
from v2.server.state import SLICES, is_public, State

PW, SECRET = 'testpw', 'testsecret-0123456789'
H = {'Authorization': 'Bearer ' + SECRET}
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PLAYERS = ['밍밍', '예지랑', '행복한걸', '순자']
DONORS = ['영원', '구름빵', '밍밍바라기', '별빛님', '밍밍', '익명', '김']   # 밍밍(선수) · 익명 · 한 글자는 닉네임 후보에서 빠진다

# (메모, 닉네임, 메시지, how, sure) — 옛 tests/bank_memo_test.py 그대로
CASES = [
    ('영원 밍밍 화이팅',        '영원',       '밍밍 화이팅',  'known',     True),
    ('영원밍밍화이팅',          '영원',       '밍밍화이팅',   'known',     True),
    ('밍밍 화이팅 영원',        '영원',       '밍밍 화이팅',  'known',     True),
    ('밍밍화이팅영원',          '영원',       '밍밍화이팅',   'known',     True),
    ('영원',                    '영원',       '',             'known',     True),
    ('영원님 밍밍 화이팅',      '영원님',     '밍밍 화이팅',  'known',     True),
    ('  영원   밍밍  ',         '영원',       '밍밍',         'known',     True),
    ('별빛 순자 응원해요',      '별빛',       '순자 응원해요', 'known',    True),
    ('밍밍바라기 예지랑 응원해', '밍밍바라기', '예지랑 응원해', 'known',   True),
    ('구름빵',                  '구름빵',     '',             'known',     True),
    ('영원히사랑해',            '',           '영원히사랑해', 'message',   False),
    ('새손님 밍밍 화이팅',      '새손님',     '밍밍 화이팅',  'first',     False),
    ('사랑둥이',                '',           '사랑둥이',     'message',   False),
    ('영원/밍밍화이팅',         '영원',       '밍밍화이팅',   'known',     True),
    ('테스트/안녕',             '테스트',     '안녕',         'first',     False),
    ('새손님, 순자 최고',       '새손님',     '순자 최고',    'first',     False),
    ('밍밍/화이팅',             '',           '밍밍/화이팅',  'message',   False),
    ('밍밍 화이팅',             '',           '밍밍 화이팅',  'message',   False),
    ('밍밍최고',                '',           '밍밍최고',     'message',   False),
    ('예지랑아 사랑해',         '',           '예지랑아 사랑해', 'message', False),
    ('오늘도 화이팅',           '',           '오늘도 화이팅', 'message',  False),
    ('화이팅',                  '',           '화이팅',       'message',   False),
    ('홍길동',                  '홍길동',     '',             'name_only', False),
    ('스트밍밍플러',            '스트',       '밍밍플러',     'player_cut', False),   # 10-14 실제 입금 — 은행이 띄어쓰기를 없앤다
    ('스트 밍밍 플러',          '스트',       '밍밍 플러',    'first',     False),
    ('화이팅밍밍',              '',           '화이팅밍밍',   'message',   False),
    ('오늘도순자최고',          '',           '오늘도순자최고', 'message', False),
    ('구름빵밍밍화이팅',        '구름빵',     '밍밍화이팅',   'known',     True),
    ('',                        '',           '',             'empty',     False),
    (None,                      '',           '',             'empty',     False),
]


class MemoSplit(unittest.TestCase):
    def test_cases(self):
        for memo, nm, msg, how, sure in CASES:
            with self.subTest(memo=memo):
                r = split_memo(memo, PLAYERS, DONORS)
                self.assertEqual((r['name'], r['message'], r['how'], r['sure']), (nm, msg, how, sure))

    def test_shapes(self):
        r = split_memo('영원 밍밍 화이팅', [{'name': '밍밍'}], DONORS)
        self.assertEqual((r['name'], r['message']), ('영원', '밍밍 화이팅'))                  # 선수가 {"name": …} 모양이어도
        self.assertEqual(split_memo('영원 밍밍 화이팅', [], []), {'name': '영원', 'message': '밍밍 화이팅', 'how': 'first', 'sure': False})
        self.assertEqual(len(clean('가' * 200)), 40)                                         # 아주 긴 메모는 잘라서 본다

    def test_ai_split_ok(self):
        self.assertTrue(ai_split_ok('영원밍밍화이팅', '영원', '밍밍 화이팅'))
        self.assertTrue(ai_split_ok('밍밍 화이팅 영원', '영원', '밍밍 화이팅'))
        self.assertTrue(ai_split_ok('밍밍 화이팅', '', '밍밍화이팅'))
        self.assertTrue(ai_split_ok('테스트/안녕', '테스트', '안녕'))
        self.assertFalse(ai_split_ok('영원 밍밍 화이팅', '영원이', '밍밍 화이팅'))           # 메모에 없는 닉네임
        self.assertFalse(ai_split_ok('영원 밍밍 화이팅', '밍밍', '영원 화이팅'))             # 가운데 토막
        self.assertFalse(ai_split_ok('영원 밍밍 화이팅', '영원', '밍밍 파이팅'))             # 글자를 바꾼 메시지
        self.assertFalse(ai_split_ok('', '', ''))

    def test_same_as_old(self):
        """옛 features/bank_memo.py 와 한 글자도 다르지 않게 나누는가 — 같은 입력을 둘 다에 넣어 본다."""
        import importlib.util
        import sys
        old_path = os.path.join(ROOT, 'features', 'bank_memo.py')
        if not os.path.exists(old_path):
            self.skipTest('옛 features/bank_memo.py 가 없다(옛 프로그램을 걷어낸 뒤)')
        sys.path.insert(0, ROOT)
        try:
            spec = importlib.util.spec_from_file_location('old_bank_memo', old_path)
            old = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(old)
        except Exception as e:      # 옛 features/ai_facts 를 못 불러오면(부품 없음) 건너뛴다
            self.skipTest('옛 모듈을 못 불러옴: %s' % type(e).__name__)
        finally:
            sys.path.remove(ROOT)
        extra = ['밍밍아 오늘도 고마워', '구름빵님 순자', '행복한걸최고', '김철수', '   ', '♡영원♡ 밍밍', '영원,', '예지랑이랑 순자']
        for memo in [c[0] for c in CASES] + extra:
            with self.subTest(memo=memo):
                self.assertEqual(split_memo(memo, PLAYERS, DONORS), old.split_memo(memo, PLAYERS, DONORS))


class Base(unittest.TestCase):
    NAMES = ['밍밍', '예지랑', '순자']

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2bank_')
        self._saved = (bank.KEY_FILE, bank.APP_APK, bank.APP_VER)
        bank.KEY_FILE = os.path.join(self.dir, 'bank_key.json')
        bank.APP_APK = os.path.join(self.dir, 'angel-bankphone.apk')
        bank.APP_VER = os.path.join(self.dir, 'version.txt')
        self._env = {k: os.environ.pop(k, None) for k in ('LM2_BANK_KEY', 'LM2_TRIAL')}
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET, sig_fetch=lambda: []))
        self.bus = self.c.app.state.bus
        self.cmd('session.start', names=self.NAMES)

    def tearDown(self):
        self.c.app.state.store.close()
        bank.KEY_FILE, bank.APP_APK, bank.APP_VER = self._saved
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.dir, ignore_errors=True)

    def cmd(self, t, **data):
        return self.c.post('/api/cmd', json={'type': t, 'data': data}, headers=H).json()

    def dep(self, key, deps, **kw):
        hdr = {'X-Bank-Key': key} if key is not None else {}
        return self.c.post('/api/bank/deposit', json=dict(dict(source='web', deposits=deps), **kw), headers=hdr)

    def inbox(self):
        return self.c.get('/api/bank/inbox', headers=H).json()

    def key(self):
        return self.c.get('/api/bank/key', headers=H).json()['key']


D1 = {'ref': 'r1', 'amount': 50000, 'when': '2026.10.14 19:01:02', 'fields': [['거래내용', '영원밍밍화이팅'], ['상대계좌예금주명', '김진짜']]}
D2 = {'ref': 'r2', 'amount': 30000, 'when': '2026.10.14 19:02:00', 'fields': [['거래내용', '홍길동'], ['상대계좌예금주명', '홍길동']]}
D3 = {'ref': 'r3', 'amount': 10000, 'when': '2026.10.14 19:03:00', 'fields': {'입금자명': '새손님 순자 최고'}}


class Inbox(Base):
    def test_key_rules(self):
        self.assertEqual(self.dep(None, []).status_code, 401)                               # 열쇠를 아직 안 만들었으면 401
        self.assertEqual(self.dep('x' * 32, []).status_code, 401)
        self.assertEqual(self.c.get('/api/bank/key').status_code, 401)                       # 열쇠는 로그인해야 받는다
        k = self.key()
        self.assertEqual(len(k), 32)
        self.assertEqual(self.key(), k)                                                      # 다시 물어도 같은 열쇠
        r = self.dep('x' * 32, [])
        self.assertEqual(r.status_code, 401)
        self.assertTrue(r.json().get('bad_key'))
        self.assertIn('[은행 확장 연결]', r.json()['message'])
        self.assertEqual(self.dep(None, []).status_code, 401)
        # 파일은 서버 사용자만 읽게(리눅스) · 옛 서버와 같은 모양 {key, created}
        with open(bank.KEY_FILE, encoding='utf-8') as f:
            saved = json.load(f)
        self.assertEqual(saved['key'], k)
        self.assertIn('created', saved)
        if os.name == 'posix':
            self.assertEqual(os.stat(bank.KEY_FILE).st_mode & 0o777, 0o600)
        # 새 열쇠를 만들면 옛 열쇠는 막힌다
        self.assertEqual(self.c.post('/api/bank/key/reset').status_code, 401)
        k2 = self.c.post('/api/bank/key/reset', headers=H).json()['key']
        self.assertNotEqual(k2, k)
        self.assertEqual(self.dep(k, []).status_code, 401)
        self.assertEqual(self.dep(k2, []).status_code, 200)

    def test_old_key_file_is_taken_over(self):
        """🔑 옛 서버가 만든 bank_key.json 을 그대로 쓴다 — 확장 · 폰 앱을 다시 설정하지 않는다."""
        old = 'a1b2c3d4' * 4
        with open(bank.KEY_FILE, 'w', encoding='utf-8') as f:
            json.dump({'key': old, 'created': 1760000000}, f)
        r = self.dep(old, [], note='옛 열쇠 그대로')
        self.assertEqual((r.status_code, r.json()), (200, {'status': 'success', 'added': 0, 'cmds': []}))
        self.assertEqual(self.key(), old)
        b = self.inbox()
        self.assertTrue(b['key_set'])
        self.assertEqual(b['key_tail'], '••••' + old[-4:])
        self.assertNotIn(old, json.dumps(b))                                                 # 목록 답엔 끝 네 글자만
        self.assertNotIn(old, json.dumps(self.c.get('/api/bank/ext', headers=H).json()))
        self.assertNotIn(old, json.dumps(self.c.get('/api/state', headers=H).json(), ensure_ascii=False))

    def test_env_key(self):
        os.environ['LM2_BANK_KEY'] = 'envkey-0123456789abcdef'
        self.assertEqual(self.dep('envkey-0123456789abcdef', []).status_code, 200)
        self.assertEqual(self.c.get('/api/bank/key', headers=H).json()['from'], 'env')
        r = self.c.post('/api/bank/key/reset', headers=H)
        self.assertEqual(r.status_code, 409)                                                 # 서버 설정에 박힌 열쇠는 못 바꾼다
        self.assertFalse(os.path.exists(bank.KEY_FILE))

    def test_trial_locks_key(self):
        os.environ['LM2_TRIAL'] = '1'
        r = self.c.get('/api/bank/key', headers=H)
        self.assertEqual(r.status_code, 403)                                                 # 옛 프로그램과 같이 쓰는 열쇠 — 새로 안 만든다
        self.assertTrue(r.json().get('trial'))
        self.assertFalse(os.path.exists(bank.KEY_FILE))
        with open(bank.KEY_FILE, 'w', encoding='utf-8') as f:
            json.dump({'key': 'k' * 32}, f)
        self.assertEqual(self.key(), 'k' * 32)                                               # 있는 열쇠는 보여 준다
        self.assertEqual(self.c.post('/api/bank/key/reset', headers=H).status_code, 403)
        self.assertEqual(self.key(), 'k' * 32)

    def test_flow(self):
        dm.remember_assignment(self.bus.store, '영원', '밍밍', 50000, '밍밍 화이팅')
        K = self.key()
        r = self.dep(K, [], note='조회 12번 · 표 찾음')
        self.assertEqual((r.status_code, r.json()['added']), (200, 0))                       # 빈 목록 = 살아 있음 신호
        self.assertEqual(self.c.get('/api/bank/inbox').status_code, 401)                     # 추천 목록은 로그인해야 본다
        b = self.inbox()
        self.assertLess(b['link']['web']['age_sec'], 5)
        self.assertEqual(b['link']['web']['note'], '조회 12번 · 표 찾음')
        ver0 = self.c.get('/api/state', headers=H).json()['slices']['bank']['ver']

        # ── 입금 ──
        r = self.dep(K, [D1, D2, D3])
        self.assertEqual(r.json(), {'status': 'success', 'added': 3, 'cmds': []})
        self.assertEqual(self.dep(K, [D1]).json()['added'], 0)                               # 같은 입금(ref)은 다시 안 올라간다
        bad = [{'ref': 'x1', 'amount': 0}, {'ref': 'x2', 'amount': '많이'}, {'ref': 'x3', 'amount': -5},
               {'ref': 'x4', 'amount': 10 ** 9}, {'amount': 1000}, '문자열', None]
        self.assertEqual(self.dep(K, bad).json()['added'], 0)                                # 이상한 금액 · ref 없는 줄은 거른다
        self.assertEqual(self.c.post('/api/bank/deposit', json={'deposits': {'a': 1}}, headers={'X-Bank-Key': K}).status_code, 400)
        self.assertEqual(self.c.post('/api/bank/deposit', json={'deposits': [{}] * 31}, headers={'X-Bank-Key': K}).status_code, 400)

        items = {i['amount']: i for i in self.inbox()['items']}
        a = items[50000]
        # 📚 10-17: 붙여 써도 지난 기록의 닉네임(known_name) · 할 말은 닉네임 · 선수 이름을 뺀 나머지 · 선수는 '누구 몫'(target)
        self.assertEqual((a['name'], a['message'], a['how'], a['sure']), ('영원', '밍밍화이팅', 'known_name', True))
        self.assertEqual((a['memo'], a['holder']), ('영원밍밍화이팅', '김진짜'))                # 메모 칸과 실명 칸을 따로
        h = items[30000]
        self.assertEqual((h['how'], h['name'], h['message']), ('no_memo', '홍길동', ''))       # 메모 없이 보낸 입금은 금액 · 입금자명만
        n = items[10000]
        self.assertEqual((n['name'], n['message'], n['how'], n['sure']), ('새손님', '순자 최고', 'player_strip', False))
        self.assertEqual([i['amount'] for i in self.inbox()['items']], [10000, 30000, 50000])   # 최근 것이 위
        self.assertEqual(set(VIEW_KEYS), set(a))                                             # 옛 _view 와 같은 칸

        # 배정 예상은 답을 보낸 뒤에 붙는다(검사 손님은 뒤일까지 기다려 준다)
        self.assertTrue(all(i['ai'] == 'done' for i in items.values()), [i['ai'] for i in items.values()])
        self.assertEqual(items[50000]['target'], '밍밍')                                      # 영원밍밍화이팅 → 밍밍 ＋?
        self.assertEqual(items[10000]['target'], '순자')                                      # 새손님 순자 최고 → 순자 ＋?
        self.assertFalse(items[30000]['target'])                                             # 메시지 없는 입금은 예상 안 함
        self.assertGreater(items[50000]['target_conf'], 0.5)
        self.assertTrue(items[50000]['target_why'])

        # ── 조종실 신호(비공개 조각 bank) — 이름 · 금액 없이 ──
        sl = self.c.get('/api/state', headers=H).json()['slices']
        self.assertGreater(sl['bank']['ver'], ver0)
        self.assertEqual(sl['bank']['new'], 3)
        self.assertEqual(sl['bank']['newest'], self.inbox()['items'][0]['id'])
        self.assertEqual(set(sl['bank']), {'ver', 'new', 'hidden', 'newest'})

        # ── 실명은 바깥으로 안 나간다 ──
        pub = self.c.get('/api/state').text
        self.assertNotIn('김진짜', pub)
        self.assertNotIn('영원밍밍', pub)
        self.assertNotIn('bank', self.c.get('/api/state').json()['slices'])                 # 방송판(로그인 없음)엔 조각도 안 간다
        self.assertFalse(is_public('bank'))
        self.assertNotIn('bank', State().snapshot(False))
        priv = json.dumps(self.c.get('/api/state', headers=H).json(), ensure_ascii=False)
        self.assertNotIn('김진짜', priv)                                                     # 조각(로그인)에도 실명은 없다
        ev = json.dumps([dict(r) for r in self.bus.store.db.execute('SELECT * FROM events')], ensure_ascii=False)
        self.assertNotIn('김진짜', ev)                                                       # 명령 기록에도 없다
        self.assertNotIn('영원밍밍', ev)
        self.assertNotIn(K, ev)
        self.assertNotIn('김진짜', json.dumps(self.c.get('/api/events?limit=200', headers=H).json(), ensure_ascii=False))

        # ── 송출 · 숨김 · 되살림 ──
        iid = items[50000]['id']
        self.assertEqual(self.c.post('/api/bank/inbox/%s/used' % iid, json={'name': '영원'}).status_code, 401)
        r = self.c.post('/api/bank/inbox/%s/used' % iid, json={'name': '영원'}, headers=H)
        self.assertEqual(r.json(), {'status': 'success'})
        self.assertNotIn(iid, [i['id'] for i in self.inbox()['items']])                      # 송출하면 추천 칸에서 빠진다
        iid2 = items[30000]['id']
        self.c.post('/api/bank/inbox/%s/dismiss' % iid2, headers=H)
        b = self.inbox()
        self.assertNotIn(iid2, [i['id'] for i in b['items']])
        self.assertIn(iid2, [i['id'] for i in b['hidden']])                                  # 숨기면 숨긴 목록으로
        self.assertEqual(self.c.get('/api/state', headers=H).json()['slices']['bank']['hidden'], 1)
        self.c.post('/api/bank/inbox/%s/restore' % iid2, headers=H)
        self.assertIn(iid2, [i['id'] for i in self.inbox()['items']])                        # 되살리면 다시 추천 칸으로
        self.assertEqual(self.c.post('/api/bank/inbox/%s/eat' % iid2, headers=H).status_code, 400)
        self.assertEqual(self.c.post('/api/bank/inbox/nope/used', headers=H).status_code, 404)

        # 송출할 때 쓴 이름은 바로 기억 — 같은 방송에서 '새손님…' 이 다시 오면 확실한 닉네임
        self.c.post('/api/bank/inbox/%s/used' % items[10000]['id'], json={'name': '새손님'}, headers=H)
        self.dep(K, [{'ref': 'r9', 'amount': 20000, 'fields': [['거래내용', '새손님예지랑화이팅']]}])
        n2 = next(i for i in self.inbox()['items'] if i['amount'] == 20000)
        self.assertEqual((n2['name'], n2['how']), ('새손님', 'known_name'))
        self.assertEqual(n2['target'], '예지랑')

        # 같은 ref 라도 폰과 웹은 다른 입금(옛 ref = source:ref)
        self.assertEqual(self.c.post('/api/bank/deposit', json={'source': 'phone', 'deposits': [dict(D1)]},
                                     headers={'X-Bank-Key': K}).json()['added'], 1)
        ph = next(i for i in self.inbox()['items'] if i['source'] == 'phone')
        self.assertEqual(ph['amount'], 50000)

    def test_keep_36h_and_300(self):
        K = self.key()
        self.dep(K, [{'ref': 'old', 'amount': 1000, 'fields': [['내용', '옛날']]}])
        self.bus.store.db.execute("UPDATE bank_inbox SET at = at - ? WHERE ref = 'web:old'", (bank.KEEP_SEC + 5,))
        self.dep(K, [{'ref': 'new', 'amount': 2000, 'fields': [['내용', '새것']]}])
        refs = [r['ref'] for r in self.bus.store.db.execute('SELECT ref FROM bank_inbox')]
        self.assertEqual(refs, ['web:new'])                                                  # 36시간 넘은 것은 지운다
        bank._rt(self.bus)['posts'].clear()
        for k in range(11):
            self.dep(K, [{'ref': 'm%d_%d' % (k, j), 'amount': 1000 + j, 'fields': [['내용', 'x']]} for j in range(30)])
        n = self.bus.store.db.execute('SELECT COUNT(*) AS n FROM bank_inbox').fetchone()['n']
        self.assertEqual(n, bank.KEEP_MAX)

    def test_rate_limit(self):
        K = self.key()
        bank._rt(self.bus)['posts'].clear()
        codes = [self.dep(K, []).status_code for _ in range(61)]
        self.assertEqual(codes[:60].count(200), 60)
        self.assertEqual(codes[60], 429)                                                     # 1분에 60번 넘게 보내면 429

    def test_app_download(self):
        self.assertEqual(self.c.get('/download/bankphone.apk').status_code, 404)              # 아직 올라온 앱 파일이 없어요
        self.assertFalse(self.c.get('/api/bank/app', headers=H).json()['ready'])
        apk = b'PK\x03\x04' + os.urandom(2000)
        with open(bank.APP_APK, 'wb') as f:
            f.write(apk)
        with open(bank.APP_VER, 'w', encoding='utf-8') as f:
            f.write('0.2\n')
        r = self.c.get('/download/bankphone.apk')                                            # 로그인 없이 그대로 받아진다
        self.assertEqual((r.status_code, r.content), (200, apk))
        self.assertTrue(r.headers['content-type'].startswith('application/vnd.android.package-archive'))
        self.assertIn('angel-bankphone-0.2.apk', r.headers['content-disposition'])
        self.assertIn('attachment', r.headers['content-disposition'])
        self.assertEqual(self.c.get('/api/bank/app').status_code, 401)                       # 판 번호 조회는 로그인해야
        d = self.c.get('/api/bank/app', headers=H).json()
        self.assertEqual((d['ready'], d['version'], d['size'], d['url']), (True, '0.2', len(apk), '/download/bankphone.apk'))

    def test_real_apk_in_repo(self):
        """저장소에 있는 진짜 앱 파일(bank-phone/dist)을 v2 가 같은 자리에서 내준다."""
        real = os.path.join(ROOT, 'bank-phone', 'dist', 'angel-bankphone.apk')
        if not os.path.exists(real):
            self.skipTest('bank-phone/dist 가 없다')
        self.assertEqual(self._saved[1], real)

    def test_mirror_and_cmds(self):
        K = self.key()
        state = {'v': '0.5.0', 'enabled': True, 'interval': 30, 'clicks': 12, 'lastOkAt': 1760000000000, 'startedAt': 1759990000000,
                 'dateOk': True, 'status': '자동 조회 중 · 30초마다 · 다음 12초 뒤', 'cls': 'ok', 'dead': False, 'rows': 8,
                 'found': [{'at': 1760000000000, 'when': '2026-10-14 17:08:40', 'dep': 20000, 'memo': '스트밍밍플러' + '가' * 60}] * 12,
                 'log': ['17:08:52 새 입금 20,000원 스트밍밍플러'] * 10, 'secret_extra': 'x' * 500}
        r = self.dep(K, [], note='자동 조회 12번', state=state)
        self.assertEqual((r.status_code, r.json().get('cmds')), (200, []))
        self.assertEqual(self.c.get('/api/bank/ext').status_code, 401)                       # 거울은 로그인해야 본다
        e = self.c.get('/api/bank/ext', headers=H).json()
        w = e['link']['web']
        self.assertLess(w['age_sec'], 5)
        self.assertTrue(w['state']['status'].startswith('자동 조회 중'))
        self.assertEqual((w['state']['cls'], w['state']['clicks'], w['state']['enabled']), ('ok', 12, True))
        self.assertEqual(len(w['state']['found']), 8)                                        # 찾은 입금 8건 · 메모 40자 · 기록 6줄
        self.assertEqual(len(w['state']['found'][0]['memo']), 40)
        self.assertEqual(len(w['state']['log']), 6)
        self.assertNotIn('secret_extra', w['state'])                                         # 모르는 칸은 버린다
        self.assertEqual((e['new'], e['newest']), (0, None))
        self.dep(K, [D1])
        e = self.c.get('/api/bank/ext', headers=H).json()
        self.assertEqual(e['new'], len(self.inbox()['items']))                               # 미처리 수와 가장 새 카드(초록 띠 재료)
        self.assertEqual(e['newest']['id'], self.inbox()['items'][0]['id'])
        self.assertEqual(e['newest']['holder'], '김진짜')                                    # 로그인한 조종실에는 보인다

        self.assertEqual(self.c.post('/api/bank/ext/cmd', json={'t': 'press'}).status_code, 401)
        self.assertEqual(self.c.post('/api/bank/ext/cmd', json={'t': 'reboot'}, headers=H).status_code, 400)
        self.assertEqual(self.c.post('/api/bank/ext/cmd', json={'t': 'enable'}, headers=H).status_code, 400)
        self.assertEqual(self.c.post('/api/bank/ext/cmd', json={'t': 'interval', 'sec': 45}, headers=H).status_code, 400)
        self.assertEqual(self.c.post('/api/bank/ext/cmd', json={'t': 'interval', 'sec': 5}, headers=H).status_code, 200)   # 10-17 5초도(확장 0.5)
        self.c.post('/api/bank/ext/cmd', json={'t': 'enable', 'on': False}, headers=H)
        self.c.post('/api/bank/ext/cmd', json={'t': 'enable', 'on': True}, headers=H)
        pend = self.c.post('/api/bank/ext/cmd', json={'t': 'interval', 'sec': 60}, headers=H).json()['pending']
        self.assertEqual([x['t'] for x in pend], ['enable', 'interval'])                      # 같은 종류는 마지막 것만(끄기→켜기 = 켜기)
        self.assertIs(pend[0]['on'], True)
        self.assertEqual(pend[1]['sec'], 60)
        self.assertEqual(self.c.get('/api/bank/ext', headers=H).json()['pending']['web'], pend)
        got = self.dep(K, [], note='자동 조회 13번', state=state).json()
        self.assertEqual([x['t'] for x in got['cmds']], ['enable', 'interval'])              # 확장의 다음 신호 답에 실려 간다
        self.assertEqual(self.dep(K, [], state=state).json()['cmds'], [])                    # 한 번 넘긴 명령은 지워진다
        self.assertFalse((self.c.get('/api/bank/ext', headers=H).json()['pending'] or {}).get('web'))
        self.c.post('/api/bank/ext/cmd', json={'t': 'press', 'source': 'phone'}, headers=H)
        self.assertEqual(self.dep(K, [], state=state).json()['cmds'], [])                    # 폰에 넣은 명령은 웹 신호엔 안 실린다
        ph = self.c.post('/api/bank/deposit', json={'source': 'phone', 'deposits': []}, headers={'X-Bank-Key': K}).json()
        self.assertEqual([x['t'] for x in ph['cmds']], ['press'])
        # 서버를 다시 켜도 기다리는 명령 · 마지막 신호가 남는다(옛 bank_inbox.json 처럼)
        self.c.post('/api/bank/ext/cmd', json={'t': 'rebase'}, headers=H)
        self.c.app.state.store.close()
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET, sig_fetch=lambda: []))
        self.bus = self.c.app.state.bus
        e = self.c.get('/api/bank/ext', headers=H).json()
        self.assertEqual([x['t'] for x in e['pending']['web']], ['rebase'])
        self.assertIn('web', e['link'])
        self.assertEqual(len(self.inbox()['items']), 1)

    def test_heartbeat_does_not_spam_screens(self):
        """25초마다 오는 '살아 있음' 신호는 명령 줄을 안 지난다 — 모든 화면에 빈 쪽지가 가지 않게."""
        K = self.key()
        seq = self.c.get('/api/state', headers=H).json()['seq']
        for _ in range(5):
            self.dep(K, [], note='살아 있음')
        self.assertEqual(self.c.get('/api/state', headers=H).json()['seq'], seq)
        self.dep(K, [D1])
        self.assertGreater(self.c.get('/api/state', headers=H).json()['seq'], seq)

    def test_ai_split_when_unsure(self):
        """애매한 메모(옛 길로 떨어진 첫 낱말 · 할 말만)는 AI 에게 나눠 달라고 한다 — 지어낸 글자가 있으면 버린다.
           📚 10-17: 선수 이름이 든 메모는 '선수 이름 떼기'(player_strip)가 먼저 나눠서 AI 에게 안 묻는다."""
        K = self.key()
        calls = []

        def fake_post(models, body, timeout):
            sysmsg = body['messages'][0]['content']
            calls.append(sysmsg)
            if '계좌 후원 메모' in sysmsg:
                memo = body['messages'][1]['content']
                ans = {'테스트 안녕': {'name': '테스트', 'message': '안녕'},                   # 맞게 나눔 — 그대로라 바뀐 것 없음
                       '화이팅 별사탕': {'name': '별사탕', 'message': '화이팅'},              # 뒤 닉네임을 찾아냄
                       '가나다 라마바': {'name': '가나', 'message': '다라마바!!'}}.get(memo, {})
                return ai._Reply(200, json.dumps(ans, ensure_ascii=False)), 200, 'fake'
            return ai._Reply(200, '{"target": null, "confidence": 0}'), 200, 'fake'

        with mock.patch.object(ai, 'ai_on', lambda: True), mock.patch.object(ai, 'nim_allowed', lambda: True),                 mock.patch.object(ai, 'ai_post', fake_post):
            self.dep(K, [{'ref': 'a1', 'amount': 11000, 'fields': [['내용', '테스트 안녕']]},
                         {'ref': 'a2', 'amount': 12000, 'fields': [['내용', '화이팅 별사탕']]},
                         {'ref': 'a3', 'amount': 13000, 'fields': [['내용', '가나다 라마바']]},
                         {'ref': 'a4', 'amount': 14000, 'fields': [['내용', '스트밍밍플러']]},
                         {'ref': 'a5', 'amount': 15000, 'fields': [['내용', '밍밍 화이팅 별사탕']]}])
        items = {i['amount']: i for i in self.inbox()['items']}
        self.assertEqual((items[11000]['name'], items[11000]['how']), ('테스트', 'first'))
        self.assertEqual((items[12000]['name'], items[12000]['message'], items[12000]['how']), ('별사탕', '화이팅', 'ai'))
        self.assertEqual((items[13000]['name'], items[13000]['how']), ('가나다', 'first'))   # 지어낸 글자('!!') — 버린다
        # 선수 이름이 든 메모는 AI 에게 안 묻는다 — 선수 이름을 떼고 남은 덩어리 · 선수는 바로 '누구 몫'
        self.assertEqual((items[14000]['name'], items[14000]['message'], items[14000]['how'], items[14000]['target']),
                         ('스트', '밍밍플러', 'player_strip', '밍밍'))
        self.assertEqual((items[15000]['name'], items[15000]['message'], items[15000]['how'], items[15000]['target']),
                         ('별사탕', '밍밍 화이팅', 'player_strip', '밍밍'))
        self.assertEqual(items[15000]['target_why'], bank.MEMO_TARGET_WHY)
        self.assertEqual(sum('계좌 후원 메모' in c for c in calls), 3)
        self.assertTrue(all(i['ai'] == 'done' for i in items.values()))

    def test_backup_has_no_real_names(self):
        """💾 장부 백업(14벌 · 바깥 보관소로도 갈 수 있다)엔 입금 카드 · 확장 신호를 넣지 않는다.
           옛 프로그램은 실명을 bank_inbox.json 에 36시간만 두고 백업하지 않았다 — 지운 글자도 파일에 안 남아야 한다."""
        import gzip
        from v2.tools import backup_db as bk
        K = self.key()
        self.dep(K, [D1], state={'status': '자동 조회 중', 'found': [{'memo': '김진짜메모'}], 'log': ['새 입금 김진짜']})
        self.c.post('/api/bank/ext/cmd', json={'t': 'press'}, headers=H)
        self.bus.store.db.execute("INSERT INTO donations (id, tx_id, at, name, amount, status) VALUES ('d9', 't9', 1, '별빛', 50000, 'pending')")
        p = bk.snapshot(os.path.join(self.dir, 'lm2.db'), os.path.join(self.dir, 'bk'))      # 서버가 켜진 채로
        with gzip.open(p, 'rb') as g:
            raw = g.read()
        for s in ('김진짜', '영원밍밍화이팅'):
            self.assertNotIn(s.encode('utf-8'), raw)                                         # 지운 줄의 글자도 빈 쪽에 안 남는다
        back = os.path.join(self.dir, 'back.db')
        with open(back, 'wb') as f:
            f.write(raw)
        c = sqlite3.connect(back)
        try:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM bank_inbox').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM bank_meta').fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT name FROM donations WHERE id = 'd9'").fetchone()[0], '별빛')   # 장부는 그대로
        finally:
            c.close()
        self.assertEqual(len(self.inbox()['items']), 1)                                      # 돌아가는 장부의 카드는 그대로
        self.assertIn('김진짜', json.dumps(self.c.get('/api/bank/ext', headers=H).json(), ensure_ascii=False))
        self.assertEqual(bk.scrub_private(sqlite3.connect(':memory:')), [])                  # 표가 없으면(옛 장부) 아무것도 안 한다

    def test_ai_off_never_called(self):
        """AI 가 꺼져 있으면(열쇠 없음 · LM2_AI_OFF) 부르지 않고, 카드는 규칙만으로 끝난다('예상 중…' 에 머물지 않는다)."""
        K = self.key()
        post = mock.Mock(side_effect=AssertionError('AI 를 부르면 안 된다'))
        with mock.patch.object(ai, 'ai_on', lambda: False), mock.patch.object(ai, 'ai_post', post),                 mock.patch.object(ai, 'nim_post', post):
            r = self.dep(K, [{'ref': 'z1', 'amount': 5000, 'fields': [['내용', '테스트 순자 안녕']]},
                             {'ref': 'z2', 'amount': 6000, 'fields': [['내용', '가나다 라마']]}])
        self.assertEqual(r.json()['added'], 2)
        post.assert_not_called()
        items = {i['amount']: i for i in self.inbox()['items']}
        self.assertEqual((items[5000]['ai'], items[5000]['how'], items[5000]['target']), ('done', 'player_strip', '순자'))
        self.assertEqual((items[6000]['ai'], items[6000]['how'], items[6000]['target']), ('done', 'first', None))


VIEW_KEYS = ('id', 'source', 'amount', 'when', 'at', 'memo', 'holder', 'name', 'message', 'how', 'sure',
             'target', 'target_conf', 'target_why', 'ai', 'status')


class Files(unittest.TestCase):
    """저장소 · 화면 파일에서 확인할 것(옛 bank_inbox_test 의 글자 검사 자리)."""

    def read(self, *p):
        with open(os.path.join(ROOT, *p), encoding='utf-8') as f:
            return f.read()

    def test_gitignore(self):
        gi = self.read('.gitignore')
        self.assertIn('bank_key.json', gi)                                                    # 열쇠 파일 · 장부(SQLite)는 저장소에 안 올라간다
        self.assertIn('*.db', gi)

    def test_slice_is_private(self):
        self.assertIn('bank', SLICES)
        self.assertFalse(is_public('bank'))


if __name__ == '__main__':
    unittest.main()
