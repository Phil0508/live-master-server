# -*- coding: utf-8 -*-
"""정답지(answer_log) 표 모양은 서버(donor_book)와 옛 기억 잇기 도구(relink_old_memory)가 같아야 한다 — 10-17 합치며."""
import unittest

from v2.server.domain import donor_book
from v2.tools import relink_old_memory


class AnswerLogSchemaSame(unittest.TestCase):
    def test_same(self):
        srv = tuple(q for q in donor_book.SCHEMA if 'answer_log' in q)
        self.assertEqual(srv, tuple(relink_old_memory.ANSWER_LOG_SCHEMA))


if __name__ == '__main__':
    unittest.main()
