# -*- coding: utf-8 -*-
"""🧱 검사 울타리 (sturdy 10-17) — 그냥 돌려도 검사가 바깥(진짜 Supabase · NVIDIA)으로 안 나가는지.

v2/tests/__init__.py 가 꾸러미를 불러오는 순간 Supabase · NVIDIA 주소를 닫힌 포트로 돌리고 NVIDIA 열쇠를 비운다.
⚠️ 전에는 가짜 시그니처 목록 없이 서버를 만드는 검사(후원 받기 · 옛 장부 옮기기 · 진짜 서버 띄우기)가 저장소의
   SUPABASE_CREDENTIALS.txt 를 읽고 진짜 Supabase 에 물으러 나갔다(조사 10-17).
"""
import os
import unittest

from v2.tests import CLOSED


class Fence(unittest.TestCase):
    def test_env_closed(self):
        self.assertEqual(os.environ.get('SUPABASE_URL'), CLOSED)
        self.assertEqual(os.environ.get('SUPABASE_SECRET_KEY'), 'x')
        self.assertEqual(os.environ.get('LM2_NIM_URL'), CLOSED)
        self.assertEqual(os.environ.get('NVIDIA_API_KEY'), '')
        self.assertNotIn('ANTHROPIC_API_KEY', os.environ)
        self.assertTrue(CLOSED.startswith('http://127.0.0.1:'))

    def test_server_parts_see_closed_addresses(self):
        """서버 부품이 실제로 읽는 값 — 파일(SUPABASE_CREDENTIALS.txt)이 있어도 환경변수가 먼저다."""
        from v2.server.domain import ai
        from v2.server.domain import signatures
        url, key = signatures._supabase_config()
        self.assertEqual((url, key), (CLOSED, 'x'))
        self.assertEqual(ai.NIM_URL, CLOSED)
        # 시그니처 관리 · 영상 올리기도 같은 함수로 주소를 읽는다
        from v2.server.domain import media, sigadmin
        self.assertIs(sigadmin._supabase_config, signatures._supabase_config)
        self.assertIs(media._supabase_config, signatures._supabase_config)

    def test_live_server_inherits(self):
        """진짜 서버를 띄우는 검사(test_live)는 os.environ 을 물려준다 — 같은 울타리 안이다."""
        env = dict(os.environ)
        self.assertEqual(env['SUPABASE_URL'], CLOSED)
        self.assertEqual(env['LM2_NIM_URL'], CLOSED)


if __name__ == '__main__':
    unittest.main()
