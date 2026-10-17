# -*- coding: utf-8 -*-
"""🧹 후원 장부 청소 기준 — '진짜 후원인가' · '시험 이름 같은가' 를 한 곳에서 정한다(후원자 장부 · 옛 기억 잇기 · 딱지가 다 이걸 부른다).

진짜 후원이 아닌 것(is_real_donation → False)
  - source 'mobile'          옛 프로그램의 손 점수 조정('수동 점수 조작') — 돈이 아니다. 음수도 있고 이름이 선수 이름 · Player 1 이다.
  - source 'toonation_test'  투네이션 테스트(리스너 toon_t2_) — 실제 돈이 아니다.
  - 메시지에 '수동 점수 조작'  source 가 다르게 적혔어도 손 점수다.
  - 금액 0 이하               돈이 안 들어왔다(옛 장부에 0원 시그니처 신청 · 음수 조정이 있다).
  ⚠️ 'display'(화면에만 뜬 소액)는 돈이 들어온 것이라 진짜 후원이다 — 합계 · 순위에서 빼는 것은 rules.COUNTED 가 따로 한다.

시험 이름(test_name_reason → 이유 글자, 아니면 '')
  - 숫자만('1' · '11' · '1111' · '123546789') · 'Player N' · '테스트/test' 가 들어간 이름.
  - ⚠️ 지우지 않는다. 장부 · 기억에는 그대로 두고 '시험 의심' 표시만 한다 — 대표님이 확인한다.
  - 선수 칸의 시험 이름(고수달 · 도재규 · 한명 · 김철수 …)은 글자로는 못 가른다 → test_player_reason(name, roster):
    지금 선수 명단(players 조각)에 없으면 '명단에 없음'. 명단은 하드코딩하지 않는다.
"""
import re

from .rules import ANONYMOUS_NAMES

NOT_REAL_SOURCES = ('mobile', 'toonation_test')
MANUAL_SCORE_MSG = '수동 점수 조작'
TEST_TX_PREFIX = 'toon_t2_'          # 리스너가 투네이션 테스트에 붙이는 표

_PLAYER_N = re.compile(r'^player\s*\d+$', re.I)
_TEST_WORD = re.compile(r'테스트|test', re.I)


def _get(row, key, default=None):
    """dict · sqlite3.Row 둘 다 읽는다(없는 칸이면 default)."""
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if v is None else v


def is_real_donation(row):
    """장부 한 줄이 진짜 후원(돈이 들어온 것)인가."""
    if not row:
        return False
    if str(_get(row, 'source', '') or '') in NOT_REAL_SOURCES:
        return False
    if str(_get(row, 'tx_id', '') or '').startswith(TEST_TX_PREFIX):
        return False
    if MANUAL_SCORE_MSG in str(_get(row, 'message', '') or ''):
        return False
    try:
        amount = int(_get(row, 'amount', 0) or 0)
    except (TypeError, ValueError):
        return False
    return amount > 0


def test_name_reason(name):
    """후원자 이름이 시험용 같으면 이유(짧은 글), 아니면 ''. 익명 · 빈 이름은 시험이 아니다('')."""
    n = ' '.join(str(name or '').split())
    if n.endswith('님'):
        n = n[:-1].strip()
    if not n or n.lower() in ANONYMOUS_NAMES:
        return ''
    if n.replace(' ', '').isdigit():
        return '숫자만'
    if _PLAYER_N.match(n):
        return 'Player N'
    if _TEST_WORD.search(n):
        return '테스트 글자'
    return ''


def test_player_reason(name, roster):
    """선수 칸 이름이 시험용 같으면 이유. 이름 글자로 먼저 보고(test_name_reason), 그다음 지금 명단에 없으면 '명단에 없음'.
       roster 가 비어 있으면(방송이 끝나 명단을 비운 때) 명단으로는 판단하지 않는다 — 모두 시험이 되어 버린다."""
    why = test_name_reason(name)
    if why:
        return why
    names = {str(p).strip() for p in (roster or []) if str(p or '').strip()}
    if names and str(name or '').strip() not in names:
        return '명단에 없음'
    return ''
