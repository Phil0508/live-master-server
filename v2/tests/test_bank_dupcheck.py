# -*- coding: utf-8 -*-
"""🏦 계좌 입금 송출 전 '이미 넣은 입금 같아요' 판정(대표님 10-17 · w2side).

후원 콘솔에서 계좌 입금 카드 [채우기] → [송출] 할 때 조종실이 먼저 POST /api/bank/dupcheck 로 묻고,
warns 가 있으면 '이미 넣은 것 같아요 — 그래도 보낼까요?' 를 한 번 띄운다(막지는 않는다).
"""
import json
import os
import time
import unittest

from v2.server.domain import bank
from v2.tests.test_bank import Base, D1, D2, D3, H

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DupCheck(Base):
    def setUp(self):
        super().setUp()
        self.K = self.key()
        self.dep(self.K, [D1, D2, D3])
        self.items = {i['amount']: i for i in self.inbox()['items']}

    def check(self, iid, name, amount, ledger=True, **kw):
        r = self.c.post('/api/bank/dupcheck', json={'id': iid, 'name': name, 'amount': amount, 'ledger': ledger}, headers=H, **kw)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['warns']

    def codes(self, *a, **kw):
        return [w['code'] for w in self.check(*a, **kw)]

    def donate(self, name, amount, tx):
        r = self.c.post('/api/donation', json={'name': name, 'amount': amount, 'message': '', 'tx_id': tx}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)

    def test_login_and_readonly(self):
        a = self.items[50000]
        r = self.c.post('/api/bank/dupcheck', json={'id': a['id'], 'name': '영원', 'amount': 50000, 'ledger': True})
        self.assertEqual(r.status_code, 401)                                                  # 로그인한 조종실만
        n0 = self.bus.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        d0 = self.bus.store.db.execute('SELECT COUNT(*) FROM donations').fetchone()[0]
        self.assertEqual(self.codes(a['id'], a['name'] or '익명', 50000), [])                  # 처음 보내는 입금 — 그냥 보낸다
        self.assertEqual(self.bus.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], n0)     # 판정은 아무것도 안 바꾼다
        self.assertEqual(self.bus.store.db.execute('SELECT COUNT(*) FROM donations').fetchone()[0], d0)
        self.assertEqual(self.inbox()['items'][-1]['status'], 'new')

    def test_same_deposit_already_sent(self):
        a = self.items[50000]
        self.donate('영원', 50000, 'manual_bank_' + a['id'])                                  # 한 번 송출(장부에 넣기)
        w = self.check(a['id'], '영원', 50000)
        self.assertEqual([x['code'] for x in w], ['sent_id'])                                  # 자기 줄은 '30분 안 같은 줄' 로 또 세지 않는다
        self.assertIn('이미 송출', w[0]['text'])
        self.assertNotIn('김진짜', json.dumps(w, ensure_ascii=False))                          # 실명(holder)은 답에 없다
        # ×N 으로 보냈어도(manual_bank_<번호>_2) 같은 입금
        b = self.items[10000]
        self.donate('새손님', 10000, 'manual_bank_%s_2' % b['id'])
        self.assertIn('sent_id', self.codes(b['id'], '새손님', 10000))
        # '_' 가 LIKE 에서 아무 글자로 읽히지 않는다 — 번호가 앞부분만 같은 다른 입금은 아니다
        self.assertNotIn('sent_id', self.codes(a['id'][:-1], '아무개', 1234))

    def test_used_without_ledger(self):
        b = self.items[30000]
        self.c.post('/api/bank/inbox/%s/used' % b['id'], json={'name': '홍길동'}, headers=H)   # 장부에 넣기 없이 시그니처만 틀고 '씀'
        w = self.check(b['id'], '홍길동', 30000, ledger=False)
        self.assertEqual([x['code'] for x in w], ['sent_id'])
        self.assertIn('장부에 넣기 없이', w[0]['text'])

    def test_same_name_amount_within_30min(self):
        b = self.items[30000]
        self.donate('홍길동', 30000, 'toon_dup_1')                                            # 투네이션으로 이미 들어옴
        w = self.check(b['id'], ' 홍길동 ', 30000)                                             # 앞뒤 빈칸은 같은 이름
        self.assertEqual([x['code'] for x in w], ['same_recent'])
        self.assertIn('투네이션', w[0]['text'])
        self.assertIn('30,000', w[0]['text'])
        self.assertEqual(self.codes(b['id'], '홍길동', 30001), [])                              # 금액이 다르면 다른 후원
        self.assertEqual(self.codes(b['id'], '홍길순', 30000), [])                              # 이름이 다르면 다른 후원
        # 30분이 지나면 묻지 않는다
        later = time.time() + bank.DUP_WINDOW_SEC + 5
        self.assertEqual(bank.dup_warns(self.bus.store, b['id'], '홍길동', 30000, True, now=later), [])

    def test_phone_and_web_caught_same_deposit(self):
        # 폰 앱 · 은행 확장이 같은 입금을 따로 잡으면 카드 번호가 다르다 — 한쪽을 송출했으면 다른 쪽에서 묻는다
        self.c.post('/api/bank/deposit', json={'source': 'phone', 'deposits': [dict(D1)]}, headers={'X-Bank-Key': self.K})
        web = self.items[50000]
        phone = next(i for i in self.inbox()['items'] if i['source'] == 'phone')
        self.assertNotEqual(web['id'], phone['id'])
        self.c.post('/api/bank/inbox/%s/used' % web['id'], json={'name': '아무개'}, headers=H)   # 장부 없이 송출 · 다른 이름으로
        self.assertEqual(self.codes(phone['id'], '다른이름', 50000), ['same_card'])            # 같은 금액 · 같은 입금자(실명)
        self.assertEqual(self.codes(phone['id'], '다른이름', 40000), [])

    def test_no_ledger_big_amount(self):
        a = self.items[50000]
        w = self.check(a['id'], '영원', 50000, ledger=False)
        self.assertEqual([x['code'] for x in w], ['no_ledger_big'])
        self.assertIn("'장부에 넣기' 가 꺼져", w[0]['text'])
        self.assertEqual(self.codes(a['id'], '영원', bank.NO_LEDGER_BIG - 1, ledger=False), [])  # 작은 금액은 그냥
        self.assertEqual(self.codes(a['id'], '영원', 50000, ledger=True), [])

    def test_bad_input_is_harmless(self):
        self.assertEqual(self.codes('', '', 'abc'), [])
        self.assertEqual(self.codes(None, None, None, ledger=False), [])
        self.assertEqual(self.codes('없는번호', '영원', 50000), [])


class Wiring(unittest.TestCase):
    """조종실 후원 콘솔이 보내기 전에 묻는가(화면은 헤드리스로 따로 봤다)."""

    def test_console_asks_before_bank_send(self):
        with open(os.path.join(ROOT, 'v2', 'web', 'controller', 'js', 'panels', 'ops', 'console.js'), encoding='utf-8') as f:
            src = f.read()
        self.assertTrue("'/api/bank/dupcheck'" in src, '후원 콘솔이 보내기 전에 묻지 않는다')
        self.assertTrue('이미 넣은 것 같아요 — 그래도 보낼까요?' in src, '확인 상자 글이 없다')
        # 묻는 것이 보내기(/api/donation · /api/signature/play)보다 먼저다
        self.assertLess(src.find("'/api/bank/dupcheck'"), src.find('for (const [path, body] of jobs)'))


if __name__ == '__main__':
    unittest.main()
