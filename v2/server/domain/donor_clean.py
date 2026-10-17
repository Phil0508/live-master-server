# -*- coding: utf-8 -*-
"""🧹 '후원 아님' · '시험 이름' 판정 — ⚠️ 임시 — 갈래 가 것으로 바뀜(합칠 때 갈래 '가' 의 donor_clean.py 로 통째로 바꾼다).

갈래 '나'(후원자 장부)가 먼저 쓰려고 같은 이름 · 같은 함수 모양으로 만든 최소판이다(설계서 '후원 아님 판정').
  is_real_donation(row) -> bool       진짜 후원인가(손 점수 · 테스트 · 0원 이하는 아님)
  test_name_reason(name) -> str|''    시험 이름 같으면 까닭, 아니면 ''
"""
import re

NOT_DONATION_SOURCES = ('mobile', 'toonation_test')
MANUAL_SCORE_MSG = '수동 점수 조작'
_PLAYER_N = re.compile(r'^player\s*\d+$', re.I)
_TEST_WORDS = ('테스트', 'test')


def is_real_donation(row):
    """장부 줄(dict) 하나가 진짜 후원인가. mobile(손 점수 조정) · toonation_test · '수동 점수 조작' · 0원 이하 → 아님."""
    row = row or {}
    if str(row.get('source') or '') in NOT_DONATION_SOURCES:
        return False
    if MANUAL_SCORE_MSG in str(row.get('message') or ''):
        return False
    try:
        return int(row.get('amount') or 0) > 0
    except (TypeError, ValueError):
        return False


def test_name_reason(name):
    """시험 이름 같으면 까닭(사람 말), 아니면 ''. 지우지 않는다 — '시험 의심' 표시에만 쓴다."""
    n = ''.join(str(name or '').split())
    if not n:
        return ''
    if n.isdigit():
        return '숫자만'
    if _PLAYER_N.match(n):
        return "'Player N'"
    low = n.lower()
    if any(w in low for w in _TEST_WORDS):
        return "'테스트' 글자"
    return ''
