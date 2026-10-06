# -*- coding: utf-8 -*-
"""v2 투네이션 테스트 계정 설정 — 파일에 적고, 열쇠는 끝 네 글자만 보여 준다."""
import os
import tempfile
import unittest

from v2.server.domain import toon_accounts as ta
from v2.tests.test_flow import Base, H


class ToonAccounts(Base):
    def setUp(self):
        super().setUp()
        self._old = ta.ACCOUNTS_FILE
        ta.ACCOUNTS_FILE = os.path.join(self.dir, 'toon_accounts.json')

    def tearDown(self):
        ta.ACCOUNTS_FILE = self._old
        super().tearDown()

    def test_set_and_mask(self):
        self.assertEqual(self.c.get('/api/toon/accounts').status_code, 401)
        r = self.c.post('/api/toon/accounts', json={'test_url': 'https://toon.at/widget/alertbox/abcdefgh1234'}, headers=H).json()
        self.assertEqual(r['test']['masked'], 'toon.at/widget/alertbox/••••1234')
        self.assertNotIn('abcdefgh', str(r))                                    # 열쇠는 안 보낸다
        self.assertEqual(self.c.post('/api/toon/accounts', json={'test_url': 'https://x.com'}, headers=H).status_code, 400)
        r = self.c.post('/api/toon/accounts', json={'enabled': False}, headers=H).json()
        self.assertFalse(r['test']['enabled'])


if __name__ == '__main__':
    unittest.main()
