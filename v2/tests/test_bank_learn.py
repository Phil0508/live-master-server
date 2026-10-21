# -*- coding: utf-8 -*-
"""📚 계좌 입금 메모 나누기 새 순서 · 배운 짝 · 미리 배우기 도구 (10-17).

운영 실측(10-17, 송출된 계좌 카드 65건): 기계가 채운 닉네임이 맞은 건 40%. 가장 흔한 실수는 붙여 쓴 메모를 통째로
닉네임에 넣는 name_only(33건). 실제 닉네임 자리: 메모 앞 44 · 가운데/뒤 10 · 메모에 없음(별명) 11.
여기서는 그 모양을 **가짜 이름**으로 만들어 새 순서(A 배운 짝 → B 지난 기록 → C 선수 이름 떼기 → 옛 split_memo)를 본다.
옛 split_memo 의 경우(test_bank.MemoSplit · 옛 tests/bank_memo_test.py)는 그대로 통과해야 한다 — 거기서 따로 본다.
"""
import contextlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain import bank
from v2.server.domain import bank_learn as bl
from v2.server.domain.bank_memo import smart_split, split_memo
from v2.tests.test_bank import Base, H, PW, SECRET
from v2.tools import import_bank_learning as tool

PLAYERS = ['밍밍', '예지랑', '행복한걸', '순자']
KNOWN = ['하루', '별사탕', '구름빵', '달빛토끼', '새손님', '익명']       # 지난 후원 기록(가짜)

# (메모, 입금자명, 배운 짝, → 닉네임, 할 말, how, sure, target) — 실측 모양을 가짜 이름으로
CASES = [
    # 메모 앞 · 붙여 씀(4~6자) — 예전엔 통째로 name_only 였다
    ('하루밍밍화이팅',           '', '', '하루',     '밍밍화이팅',          'known_name',   True,  '밍밍'),
    ('하루밍밍',                 '', '', '하루',     '밍밍',                'known_name',   True,  '밍밍'),
    ('달별밍밍',                 '', '', '달별',     '밍밍',                'player_strip', False, '밍밍'),
    ('노을예지랑',               '', '', '노을',     '예지랑',                'player_strip', False, '예지랑'),
    ('노을예지랑화이팅',         '', '', '노을',     '예지랑화이팅',          'player_strip', False, '예지랑'),
    ('달빛토끼행복한걸최고',     '', '', '달빛토끼', '행복한걸최고',            'known_name',   True,  '행복한걸'),
    ('달별밍밍아사랑해',         '', '', '달별',     '밍밍아사랑해',          'player_strip', False, '밍밍'),
    # 메모 가운데 · 뒤
    ('밍밍 하루 화이팅',         '', '', '하루',     '밍밍 화이팅',          'known_name',   True,  '밍밍'),
    ('밍밍하루최고',             '', '', '하루',     '밍밍 최고',            'known_name',   True,  '밍밍'),
    ('예지랑 노을 사랑해',       '', '', '노을',     '예지랑 사랑해',          'player_strip', False, '예지랑'),
    ('밍밍 화이팅 노을',         '', '', '노을',     '밍밍 화이팅',          'player_strip', False, '밍밍'),
    ('순자 오늘 너무 예뻐요 별사탕', '', '', '별사탕', '순자 오늘 너무 예뻐요', 'known_name', True,  '순자'),
    # 선수 이름 뒤에 할 말
    ('하루 순자 생일 축하해',    '', '', '하루',     '순자 생일 축하해',     'known_name',   True,  '순자'),
    ('노을 순자 생일 축하해',    '', '', '노을',     '순자 생일 축하해',     'player_strip', False, '순자'),
    ('새손님 순자 최고',         '', '', '새손님',   '순자 최고',            'known_name',   True,  '순자'),
    # 별명 — 메모에 닉네임이 없다(배운 짝만 안다)
    ('고마워요',                 '김가짜', '달빛토끼', '달빛토끼', '고마워요', 'learned',    True,  None),
    ('밍밍화이팅',               '김가짜', '달빛토끼', '달빛토끼', '밍밍화이팅',   'learned',    True,  '밍밍'),
    ('김가짜',                   '김가짜', '달빛토끼', '달빛토끼', '',         'learned',    True,  None),   # 메모 없이 보냄 — 실명을 할 말로 안 쓴다
    ('김가짜 밍밍 화이팅',       '김가짜', '하루',     '하루',     '밍밍 화이팅',   'learned',    True,  '밍밍'), # 실명은 할 말에서 뺀다
    ('하루밍밍',                 '김가짜', '노을',     '노을',     '하루밍밍',     'learned',    True,  '밍밍'), # 배운 짝이 지난 기록보다 먼저(메모의 이름은 할 말에 남아 대표님이 본다)
    # 옛 길 그대로
    ('김가짜',                   '김가짜', '',         '김가짜',   '',         'no_memo',    False, None),
    ('밍밍화이팅',               '', '', '',         '밍밍화이팅',      'message',      False, None),
    ('오늘도순자최고',           '', '', '',         '오늘도순자최고',  'message',      False, None),
    ('하루히사랑해',             '', '', '',         '하루히사랑해',    'message',      False, None),   # 두 글자 이름은 떨어져 있을 때만
    ('홍가짜',                   '', '', '홍가짜',   '',                'name_only',    False, None),
    ('테스트 안녕',              '', '', '테스트',   '안녕',            'first',        False, None),
    ('',                         '', '', '',         '',                'empty',        False, None),
]


class SmartSplit(unittest.TestCase):
    def test_cases(self):
        for memo, holder, learned, nm, msg, how, sure, tgt in CASES:
            with self.subTest(memo=memo, learned=learned):
                r = smart_split(memo, PLAYERS, KNOWN, learned=learned, holder=holder)
                self.assertEqual((r['name'], r['message'], r['how'], r['sure'], r['target']), (nm, msg, how, sure, tgt))

    def test_better_than_old(self):
        """실측 모양(붙여 씀 · 가운데 · 별명) — 옛 split_memo 는 대부분 놓치고 새 순서는 다 맞힌다."""
        shapes = [c for c in CASES if c[5] in ('learned', 'known_name', 'player_strip')]
        new = sum(smart_split(m, PLAYERS, KNOWN, learned=lv, holder=h)['name'] == nm for m, h, lv, nm, *_ in shapes)
        old = sum(split_memo(m, PLAYERS, KNOWN)['name'] == nm for m, h, lv, nm, *_ in shapes)
        self.assertEqual(new, len(shapes))
        self.assertLess(old, len(shapes) // 2 + 2, old)
        name_only = sum(split_memo(m, PLAYERS, KNOWN)['how'] == 'name_only' for m, *_ in shapes)
        self.assertGreater(name_only, 0)                                                     # 예전엔 붙여 쓴 메모가 '이름만' 이었다
        self.assertEqual(sum(smart_split(m, PLAYERS, KNOWN, learned=lv, holder=h)['how'] == 'name_only' for m, h, lv, *_ in shapes), 0)

    def test_exclusions(self):
        # 선수 · 운영비 · 번외 판 이름은 지난 기록 닉네임으로 안 쓴다
        self.assertNotEqual(smart_split('순자화이팅', PLAYERS, ['순자'])['how'], 'known_name')
        self.assertNotEqual(smart_split('운영비 밍밍', PLAYERS, ['운영비'], exclude=['운영비'])['how'], 'known_name')
        self.assertEqual(smart_split('번외왕 밍밍', PLAYERS, ['번외왕'])['how'], 'known_name')
        self.assertNotEqual(smart_split('번외왕 밍밍', PLAYERS, ['번외왕'], exclude=['번외왕'])['how'], 'known_name')
        # 가장 긴 이름이 이긴다
        r = smart_split('달빛토끼밍밍', PLAYERS, ['달빛', '달빛토끼'])
        self.assertEqual((r['name'], r['how']), ('달빛토끼', 'known_name'))
        # 세 글자 이상 이름은 붙어 있어도 찾는다
        self.assertEqual(smart_split('우리별사탕왔어요', PLAYERS, KNOWN)['name'], '별사탕')
        # 선수 이름이 {"name": …} 모양이어도
        self.assertEqual(smart_split('노을밍밍', [{'name': '밍밍'}], [])['name'], '노을')


class Learning(Base):
    """송출하면 입금자명 → 보낸 이름을 배우고, 다음 카드에 먼저 쓴다. 실명은 어디에도 안 나간다."""

    def card(self, K, ref, memo, holder, amount=20000):
        self.dep(K, [{'ref': ref, 'amount': amount, 'fields': [['거래내용', memo], ['상대계좌예금주명', holder]]}])
        return next(i for i in self.inbox()['items'] if i['amount'] == amount and i['memo'] == bank.clean(memo))

    def send(self, cid, name, n=None, amount=20000):
        tx = 'manual_bank_' + cid + ('_%d' % n if n else '')
        r = self.c.post('/api/donation', json={'name': name, 'amount': amount, 'message': '', 'tx_id': tx}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)

    def used(self, cid, name):
        self.assertEqual(self.c.post('/api/bank/inbox/%s/used' % cid, json={'name': name}, headers=H).json(), {'status': 'success'})

    def test_learn_and_suggest(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            K = self.key()
            c1 = self.card(K, 'l1', '고마워요', '김가짜', 20001)
            self.assertNotEqual(c1['how'], 'learned')
            self.send(c1['id'], '달빛토끼', amount=20001)                                    # [채우기] → [송출](장부에 넣기)
            self.used(c1['id'], '달빛토끼')
            c2 = self.card(K, 'l2', '밍밍 화이팅', '김가짜', 20002)                           # 같은 입금자 · 메모엔 닉네임 없음
            self.assertEqual((c2['name'], c2['message'], c2['how'], c2['sure'], c2['target']),
                             ('달빛토끼', '밍밍 화이팅', 'learned', True, '밍밍'))
            self.assertEqual(c2['target_why'], bank.MEMO_TARGET_WHY)
            self.assertEqual(self.card(K, 'l2b', '김 가짜', '김 가짜', 20009)['name'], '달빛토끼')   # 띄어 써도 같은 입금자 · 메모 없이 보냄
            self.assertEqual(self.card(K, 'l2c', '밍밍 화이팅', '이가상', 20010)['how'], 'message')  # 다른 입금자는 모른다

            # 한 카드는 첫 이름만(×N · 나눠 보내기) — 뒤 이름 · [송출] 끝 표시가 덮지 않는다
            self.send(c2['id'], '새별', 1, amount=20002)
            self.send(c2['id'], '다른별', 2, amount=20002)
            self.used(c2['id'], '다른별')
            c3 = self.card(K, 'l3', '하루밍밍', '김가짜', 20003)
            self.assertEqual((c3['name'], c3['how']), ('새별', 'learned'))                   # 같은 입금자는 가장 최근 카드의 이름

            # 시그니처만 보냈어도(장부 없이 — /api/donation 안 부름) [송출] 끝 표시로 배운다
            self.used(c3['id'], '마지막별')
            self.assertEqual(self.card(K, 'l4', '안녕', '김가짜', 20004)['name'], '마지막별')

            # 익명 · 수동송출은 안 배운다
            c5 = self.card(K, 'l5', '익명으로', '최허구', 20005)
            self.used(c5['id'], '익명')
            self.assertNotEqual(self.card(K, 'l6', '익명으로2', '최허구', 20006)['how'], 'learned')

            # 서버를 다시 켜도 남는다
            self.c.app.state.store.close()
            self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET, sig_fetch=lambda: []))
            self.bus = self.c.app.state.bus
            self.cmd('session.start', names=self.NAMES)
            self.assertEqual(self.card(self.key(), 'l7', '밍밍', '김가짜', 20007)['name'], '마지막별')

        # ── 실명은 어디에도 안 나간다 ──
        self.assertNotIn('김가짜', out.getvalue())                                           # 서버 기록(print)
        rows = [tuple(r) for r in self.bus.store.db.execute('SELECT * FROM bank_learn')]
        self.assertTrue(rows)
        self.assertNotIn('김가짜', json.dumps(rows, ensure_ascii=False))                    # 배운 짝 표엔 지문만
        self.assertNotIn('가짜', json.dumps(rows, ensure_ascii=False))
        self.assertEqual(bl.lookup(self.bus.store.db, '김가짜'), '마지막별')
        for authed in (False, True):
            st = self.c.get('/api/state', headers=H if authed else {}).text
            self.assertNotIn('김가짜', st)
            self.assertNotIn('bank_learn', st)
        ev = json.dumps([dict(r) for r in self.bus.store.db.execute('SELECT * FROM events')], ensure_ascii=False)
        self.assertNotIn('김가짜', ev)
        self.assertNotIn('김가짜', json.dumps(self.c.get('/api/events?limit=500', headers=H).json(), ensure_ascii=False))

    def test_unauthed_or_other_tx_does_not_learn(self):
        K = self.key()
        c1 = self.card(K, 'u1', '안녕하세요', '김가짜', 30001)
        r = self.c.post('/api/donation', json={'name': '도둑별', 'amount': 30001, 'tx_id': 'manual_bank_' + c1['id']})
        self.assertEqual(r.status_code, 401)                                                 # 로그인 없이는 후원도 · 배우기도 안 된다
        self.c.post('/api/donation', json={'name': '보통별', 'amount': 30001, 'tx_id': 'manual_123'}, headers=H)
        self.c.post('/api/donation', json={'name': '보통별', 'amount': 30001, 'tx_id': 'manual_bank_nope'}, headers=H)
        self.assertEqual(bl.count(self.bus.store.db), 0)
        self.assertEqual(bank.learn_card(self.bus.store, '', '별'), False)

    def test_learn_rules(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        self.assertTrue(bl.learn(db, '김가짜', '하나', 'b1', at=100))
        self.assertFalse(bl.learn(db, '김가짜', '둘', 'b1', at=200))                           # 같은 카드 — 첫 이름
        self.assertFalse(bl.learn(db, '김가짜', '옛것', 'b0', at=50))                          # 더 오래된 것은 안 덮는다
        self.assertTrue(bl.learn(db, '김가짜', '셋', 'b2', at=300))
        self.assertEqual(bl.lookup(db, ' 김 가짜 '), '셋')
        self.assertFalse(bl.learn(db, '', '넷', 'b3'))
        self.assertFalse(bl.learn(db, '김가짜', '수동송출', 'b3'))
        empty = sqlite3.connect(':memory:')
        self.addCleanup(empty.close)
        self.assertEqual(bl.lookup(empty, '김가짜'), '')                                     # 표가 없어도 넘어지지 않는다
        self.assertEqual([bl.card_of_tx(t) for t in ('manual_bank_b0123456789ab', 'manual_bank_b0123456789ab_2', 'manual_77', 'x')],
                         ['b0123456789ab', 'b0123456789ab', '', ''])
        self.assertNotIn('김가짜', bl.holder_key('김가짜'))

    def test_pass_through_holders_never_learn(self):
        # 10-21 토스 입금은 예금주가 '（주）비바리퍼블리카' — 한 번 배운 닉네임이 모든 토스 입금에 붙던 것
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        for h in ('（주）비바리퍼블리카', '(주)비바리퍼블리카', '㈜카카오페이', '네이버파이낸셜', '토스'):
            self.assertFalse(bl.learn(db, h, '앞뒤', 'b9', at=100), h)
            self.assertEqual(bl.lookup(db, h), '', h)
            self.assertEqual(bl.holder_key(h), '', h)
        self.assertTrue(bl.learn(db, '김토스', '사람', 'b8', at=100))          # 이름에 '토스' 가 들어간 사람은 그대로
        self.assertEqual(bl.lookup(db, '김토스'), '사람')
        self.assertTrue(bl.is_pass_through('（주） 비바리퍼블리카'))


# ── 미리 배우기 도구 ──────────────────────────────────────
OLD_SCHEMA = (
    "CREATE TABLE donation_history (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, name TEXT, amount INTEGER,"
    " current_total INTEGER, message TEXT, source TEXT, tx_id TEXT)",
    "CREATE TABLE donation_archive (id INTEGER PRIMARY KEY AUTOINCREMENT, archived_at TEXT, session_label TEXT, timestamp TEXT,"
    " name TEXT, amount INTEGER, current_total INTEGER, message TEXT, source TEXT, tx_id TEXT)",
)
B1, B2, B3, B4 = 'b111111111111', 'b222222222222', 'b333333333333', 'b444444444444'


class Tool(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2learn_')
        self.inbox = os.path.join(self.dir, 'bank_inbox.json')
        with open(self.inbox, 'w', encoding='utf-8') as f:
            json.dump({'items': [
                {'id': B1, 'ref': 'web:R1', 'holder': '김가짜', 'status': 'used', 'memo': '고마워요'},
                {'id': B2, 'ref': 'phone:R2xyz9', 'holder': '이가상', 'status': 'used'},
                {'id': B3, 'ref': 'web:R3', 'holder': '김가짜', 'status': 'used'},
                {'id': 'b999999999999', 'ref': 'web:R9', 'holder': '', 'status': 'used'},          # 입금자명 없음 — 못 배운다
            ], 'seen': {}, 'cmds': {}}, f, ensure_ascii=False)
        self.old = os.path.join(self.dir, 'old.db')
        c = sqlite3.connect(self.old)
        for q in OLD_SCHEMA:
            c.execute(q)
        c.executemany("INSERT INTO donation_archive (archived_at, session_label, timestamp, name, amount, message, source, tx_id)"
                      " VALUES ('2026-10-11', '회차1', ?, ?, 10000, '', 'manual', ?)", [
                          ('2026-10-10 12:00:00', '달빛', 'manual_bank_' + B1),
                          ('2026-10-10 12:00:05', '다른', 'manual_bank_' + B1 + '_2'),         # 같은 카드 뒤 줄 — 첫 이름만
                          ('2026-10-10 13:00:00', '별', 'manual_bank_R2xyz9'),                   # 카드 id 대신 ref
                          ('2026-10-10 14:00:00', '없는카드', 'manual_bank_bzzzzzzzzzzzz'),     # 못 찾는 카드
                          ('2026-10-10 15:00:00', '토스', 'toon_123')])                         # 계좌 송출 아님
        c.execute("INSERT INTO donation_history (timestamp, name, amount, message, source, tx_id) VALUES "
                  "('2026-10-15 12:00:00', '새달빛', 10000, '', 'manual', ?)", ('manual_bank_' + B3,))   # 같은 입금자 · 더 최근
        c.execute("INSERT INTO donation_history (timestamp, name, amount, message, source, tx_id) VALUES "
                  "('2026-10-15 12:30:00', '익명', 10000, '', 'manual', 'manual_bank_b999999999999')")
        c.commit()
        c.close()
        self.v2 = os.path.join(self.dir, 'lm2.db')
        self.c = TestClient(create_app(db_path=self.v2, password=PW, secret=SECRET, sig_fetch=lambda: []))      # 서버가 켜진 채로
        db = self.c.app.state.store.db
        bank._db(self.c.app.state.store)
        db.execute("INSERT INTO bank_inbox (id, ref, source, amount, at, memo, holder) VALUES (?, 'web:R4', 'web', 5000, ?, '밍밍', '박허구')",
                   (B4, time.time()))
        db.execute("INSERT INTO donations (id, tx_id, at, name, amount, status) VALUES ('d4', ?, ?, '허구별', 5000, 'pending')",
                   ('manual_bank_' + B4, time.time()))

    def tearDown(self):
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_tool(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = tool.main(['--inbox', self.inbox, '--sqlite', self.old, '--v2-db', self.v2, '--db-tz', 'kst'] + list(extra))
        txt = out.getvalue()
        for s in ('김가짜', '이가상', '박허구', '달빛', '새달빛', '허구별'):
            self.assertNotIn(s, txt)                                                         # 실명 · 닉네임은 안 찍는다 — 건수만
        return rc, txt

    def look(self, holder):
        return bl.lookup(self.c.app.state.store.db, holder)

    def test_count_then_write(self):
        rc, txt = self.run_tool()
        self.assertEqual(rc, 0)
        self.assertIn('세어 보기만', txt)
        self.assertIn('입금자 3명의 짝', txt)
        self.assertIn('못 찾은 줄 2', txt)                                                   # 없는 카드 · 입금자명 없는 카드
        self.assertEqual(bl.count(self.c.app.state.store.db), 0)                            # 세어 보기는 아무것도 안 바꾼다
        rc, txt = self.run_tool('--write')
        self.assertEqual(rc, 0)
        self.assertIn('새 짝 3', txt)
        self.assertEqual((self.look('김가짜'), self.look('이가상'), self.look('박허구')), ('새달빛', '별', '허구별'))
        rc, txt = self.run_tool('--write')                                                   # 두 번 돌려도 그대로
        self.assertIn('새 짝 0 · 바꾼 짝 0 · 그대로(더 최근에 배운 것 · 같은 카드) 3', txt)
        # 켜진 서버가 바로 쓴다(표를 메모리에 쥐지 않는다)
        K = self.c.get('/api/bank/key', headers=H).json()['key']
        self.c.post('/api/cmd', json={'type': 'session.start', 'data': {'names': ['밍밍', '순자']}}, headers=H)
        self.c.post('/api/bank/deposit', json={'source': 'web', 'deposits': [
            {'ref': 'n1', 'amount': 7000, 'fields': [['거래내용', '순자 화이팅'], ['상대계좌예금주명', '김가짜']]}]}, headers={'X-Bank-Key': K})
        it = self.c.get('/api/bank/inbox', headers=H).json()['items'][0]
        self.assertEqual((it['name'], it['how'], it['message'], it['target']), ('새달빛', 'learned', '순자 화이팅', '순자'))

    def test_live_newer_wins(self):
        bl.learn(self.c.app.state.store.db, '김가짜', '방송중이름', 'bLIVE00000000', at=time.time() + 60)
        rc, txt = self.run_tool('--write')
        self.assertEqual(self.look('김가짜'), '방송중이름')                                  # 방송 중에 배운 것(더 최근)을 덮지 않는다
        self.assertEqual(self.look('이가상'), '별')

    def test_old_only_and_missing(self):
        rc, txt = self.run_tool('--write', '--no-v2')
        self.assertEqual((self.look('김가짜'), self.look('박허구')), ('새달빛', ''))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(tool.main(['--v2-db', os.path.join(self.dir, 'nope.db')]), 2)  # v2 장부가 없으면 만들지 않고 멈춘다
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'nope.db')))
        self.assertEqual(tool.read_inbox(os.path.join(self.dir, 'none.json')), [])
        with open(os.path.join(self.dir, 'bad.json'), 'w', encoding='utf-8') as f:
            f.write('{깨짐')
        self.assertEqual(tool.read_inbox(os.path.join(self.dir, 'bad.json')), [])


if __name__ == '__main__':
    unittest.main()
