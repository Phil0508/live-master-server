# -*- coding: utf-8 -*-
"""📏 옛 프로그램에서 그대로 옮긴 규칙 — 숫자 · 조건을 바꾸지 않는다(대표님이 방송으로 다듬어 온 것).

출처: server.py man_won · features/donation.py 이름 보정 · features/donor_memory.py _norm_donor
"""

POINT_WON = 10000            # 1점 = 1만 원
SIG_ROUND_FLOOR = 10000      # 시그니처 최저선은 1만 원을 못 넘는다(1만 원은 제일 싼 시그)
SMALL_DISPLAY_MAX = 10000    # 1만 원 미만 '화면에만' 후원
DEDUPE_WINDOW = 12.0         # 같은 이름 · 금액 · 메시지가 12초 안에 또 오면 한 번으로
QUEUE_MAX = 40               # 시그니처 대기줄 최대
LOG_MAX = 200                # 조종실에 보이는 점수 기록 수
NOTICE_DONORS_MAX = 20
# 합계 · 순위에 세는 후원 상태 — 'display'(화면에만 뜬 소액)는 안 센다.
# 'archived' = 옛 프로그램 장부에서 옮겨 온 지난 기록(v2/tools/import_old_db.py — 누구에게 갔는지는 모른다)
COUNTED = ('pending', 'assigned', 'ignored', 'archived')

ANONYMOUS_NAMES = {'', '-', '익명', '익명의 후원자', '익명후원자', '무명', '후원자', 'anonymous', 'anon', 'unknown'}
_EMOTICON_AFTER_COLON = set(')(dDpPoO3/\\|<>^_-*;')


def man_won(amount):
    """원 → 점수(만 원 단위, 6천 원부터 올림). 5,999 → 0 · 6,000 → 1 · 15,999 → 1 · 16,000 → 2"""
    try:
        a = int(amount)
    except (TypeError, ValueError):
        return 0
    return (a + 4000) // POINT_WON


def norm_donor(name):
    """같은 사람이 '홍길동' · '홍길동님' · ' 홍길동 ' 으로 갈라지지 않게."""
    n = ' '.join(str(name or '').split())
    if n.endswith('님'):
        n = n[:-1].strip()
    return n or '익명'


def name_is_missing(name):
    return str(name or '').strip().lower() in ANONYMOUS_NAMES


def looks_like_proxy_name(prefix, rest):
    """'철수: 응원해요' 의 '철수' 가 이름으로 보이는가 — 아닐 게 확실한 것만 걸러 낸다."""
    if not prefix or len(prefix) > 12:
        return False
    if not rest:
        return False
    if rest[0] in _EMOTICON_AFTER_COLON:
        return False
    if prefix.isdigit():
        return False
    if any(ch in prefix for ch in '.,!?~…'):
        return False
    if not any(ch.isalnum() for ch in prefix):
        return False
    return True


def derive_name(name, message, tx_id):
    """플랫폼이 이름을 안 줬을 때만 메시지 '닉네임: 내용' 에서 이름을 가져온다.
       돌려받는 값: (보일 이름, 원래 이름, 메시지)"""
    orig = str(name or '').strip()
    parsed = orig
    msg = str(message or '').strip()
    split_msg = msg.replace('：', ':')
    if name_is_missing(orig) and split_msg and ':' in split_msg and not msg.startswith('[시그니처 신청:'):
        ch = ':' if ':' in msg else '：'
        a, _, b = msg.partition(ch)
        if looks_like_proxy_name(a.strip(), b.strip()):
            parsed, msg = a.strip(), b.strip()
    # '님' 떼기는 화면 글자를 긁던 시절의 보정 — 리스너(toon_)는 닉네임을 그대로 주고, 콘솔(manual_)은 진행자가 손으로 적은 이름이다
    if not str(tx_id or '').startswith(('toon_', 'manual_')) and parsed.endswith('님') and len(parsed) > 1:
        parsed = parsed[:-1]
    return (parsed or '익명'), orig, msg


def split_points(total, n):
    """나눠 주기 — 똑같이 나누고 남는 점수는 앞사람부터 1점씩."""
    if n <= 0:
        return []
    base, rem = divmod(int(total), n)
    return [base + (1 if i < rem else 0) for i in range(n)]
