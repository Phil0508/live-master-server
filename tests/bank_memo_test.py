# -*- coding: utf-8 -*-
"""🏦 계좌 입금 메모 나누기(features/bank_memo.py) — 서버 없이 부른다.

대표님 10-13: 메모는 '영원 밍밍 화이팅' 처럼 닉네임 + 할 말인데, 모양이 섞여 있다(할 말만 · 붙여 씀 · 이름만).
나눈 결과는 후원 콘솔의 '추천' 이다 — 확실한 것(예전 닉네임)만 sure=True.
"""
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, ROOT)
from features.bank_memo import ai_split_ok, clean, split_memo  # noqa: E402

OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:200]) if detail else ''))


PLAYERS = ['밍밍', '예지랑', '행복한걸', '순자']
DONORS = ['영원', '구름빵', '밍밍바라기', '별빛님', '밍밍', '익명', '김']   # 밍밍(선수) · 익명 · 한 글자는 닉네임 후보에서 빠진다

# (메모, 닉네임, 메시지, how, sure)
CASES = [
    ('영원 밍밍 화이팅',        '영원',       '밍밍 화이팅',  'known',     True),
    ('영원밍밍화이팅',          '영원',       '밍밍화이팅',   'known',     True),
    ('밍밍 화이팅 영원',        '영원',       '밍밍 화이팅',  'known',     True),
    ('밍밍화이팅영원',          '영원',       '밍밍화이팅',   'known',     True),
    ('영원',                    '영원',       '',             'known',     True),
    ('영원님 밍밍 화이팅',      '영원님',     '밍밍 화이팅',  'known',     True),     # 님은 적힌 그대로(기억은 님을 떼고 맞댄다)
    ('  영원   밍밍  ',         '영원',       '밍밍',         'known',     True),
    ('별빛 순자 응원해요',      '별빛',       '순자 응원해요', 'known',    True),     # 기억엔 '별빛님' — 님을 떼고 본다
    ('밍밍바라기 예지랑 응원해', '밍밍바라기', '예지랑 응원해', 'known',   True),     # 선수 이름이 든 닉네임 · 긴 것 먼저
    ('구름빵',                  '구름빵',     '',             'known',     True),
    ('영원히사랑해',            '',           '영원히사랑해', 'message',   False),    # '영원' + '히사랑해' 로 자르면 안 된다
    ('새손님 밍밍 화이팅',      '새손님',     '밍밍 화이팅',  'first',     False),    # '님' 으로 끝나는 닉네임 — 떼지 않는다
    ('사랑둥이',                '',           '사랑둥이',     'message',   False),    # 응원 말이 든 한 낱말은 할 말로 본다(원문이 같이 보인다)
    ('밍밍 화이팅',             '',           '밍밍 화이팅',  'message',   False),
    ('밍밍최고',                '',           '밍밍최고',     'message',   False),
    ('예지랑아 사랑해',         '',           '예지랑아 사랑해', 'message', False),
    ('오늘도 화이팅',           '',           '오늘도 화이팅', 'message',  False),
    ('화이팅',                  '',           '화이팅',       'message',   False),
    ('홍길동',                  '홍길동',     '',             'name_only', False),    # 메모 없이 보낸 실명일 수 있다
    ('',                        '',           '',             'empty',     False),
    (None,                      '',           '',             'empty',     False),
]

print('=' * 74)
print('🏦 계좌 입금 메모 나누기')
print('=' * 74)
for memo, nm, msg, how, sure in CASES:
    r = split_memo(memo, PLAYERS, DONORS)
    got = (r['name'], r['message'], r['how'], r['sure'])
    chk('%r → %s / %s' % (memo, nm or '(닉네임 없음)', msg or '(메시지 없음)'), got == (nm, msg, how, sure), got)

r = split_memo('영원 밍밍 화이팅', [{'name': '밍밍'}], DONORS)
chk('선수는 {"name": …} 모양으로 와도 된다', r['name'] == '영원' and r['message'] == '밍밍 화이팅', r)
r = split_memo('영원 밍밍 화이팅', [], [])
chk('기억도 선수도 없으면 첫 낱말 추천(확실하지 않음)', r == {'name': '영원', 'message': '밍밍 화이팅', 'how': 'first', 'sure': False}, r)
chk('아주 긴 메모는 잘라서 본다', len(clean('가' * 200)) == 40)

print('④ AI 가 나눈 결과 확인(지어낸 글자 거르기)')
chk('앞 닉네임 · 띄어쓰기 달라도 통과', ai_split_ok('영원밍밍화이팅', '영원', '밍밍 화이팅'))
chk('뒤 닉네임 통과', ai_split_ok('밍밍 화이팅 영원', '영원', '밍밍 화이팅'))
chk('닉네임 없음 · 메시지 = 메모면 통과', ai_split_ok('밍밍 화이팅', '', '밍밍화이팅'))
chk('메모에 없는 닉네임은 거른다', not ai_split_ok('영원 밍밍 화이팅', '영원이', '밍밍 화이팅'))
chk('가운데 토막은 닉네임이 아니다', not ai_split_ok('영원 밍밍 화이팅', '밍밍', '영원 화이팅'))
chk('글자를 바꾼 메시지는 거른다', not ai_split_ok('영원 밍밍 화이팅', '영원', '밍밍 파이팅'))
chk('빈 메모는 거른다', not ai_split_ok('', '', ''))

print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
