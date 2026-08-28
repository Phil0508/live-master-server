# -*- coding: utf-8 -*-
"""8단계 - 오토파일럿 판단의 경계 조건. '엉뚱한 사람에게 자동으로 가는' 길이 있는가."""
import os, shutil, sys
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('HEADLESS', '1')
os.environ.setdefault('ADMIN_PASSWORD', 'lt-sandbox-pw')
os.environ.setdefault('SESSION_SECRET', 'lt-sandbox-secret-0123456789')
SRC = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.join(SRC, 'edgebox')
os.makedirs(HERE, exist_ok=True)
shutil.copy2(os.path.join(SRC, 'server.py'), os.path.join(HERE, 'server.py'))
for f in ('live_master.db', 'live_master.db-wal', 'live_master.db-shm'):
    p = os.path.join(HERE, f)
    if os.path.exists(p):
        os.remove(p)
sys.path.insert(0, HERE)
os.chdir(HERE)
import server as SV
# 실제 서버는 뜰 때 init_db() 를 부른다(__main__ / load_data). 모듈로만 불러 쓰면
# donor_memory 표가 없어 이력 기억이 통째로 실패하고, 그게 검사 실패로 보인다.
SV.init_db()

OK, BAD, WARN = [], [], []


def chk(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print(("  [OK] " if cond else "  [!!] ") + name + (("  -- " + str(detail)[:120]) if detail else ""))


def warn(name, detail=""):
    WARN.append(name)
    print("  [주의] " + name + (("  -- " + str(detail)[:120]) if detail else ""))


print("\n" + "=" * 74)
print("(1) 별명 후보 뽑기 - 무엇이 별명이 되는가")
print("=" * 74)
for msg, expect_note in [
    ('밍밍이 화이팅', "'밍밍' 이 남아야 한다"),
    ('제이양 가즈아', "'제이양'"),
    ('오늘도 재밌게 잘 봤습니다', '흔한 말'),
    ('ㄱㅇㅈ', '초성'),
    ('', '빈 메시지'),
    ('123456', '숫자만'),
    ('a' * 200, '아주 긴 한 덩어리'),
    ('철수형 힘내요', "'철수형'"),
]:
    print("    %-24s -> %s   (%s)" % (repr(msg)[:24], SV.alias_tokens(msg), expect_note))

chk("빈 메시지는 별명 후보가 없다", SV.alias_tokens('') == [])
chk("숫자만은 별명이 안 된다", SV.alias_tokens('123456') == [])
chk("흔한 인사말은 걸러진다", '화이팅' not in SV.alias_tokens('화이팅 화이팅'))
chk("후보는 6개를 넘지 않는다", len(SV.alias_tokens(' '.join('토막%d' % i for i in range(20)))) <= 6)

print("\n" + "=" * 74)
print("(2) 메시지 안 이름 찾기 - 짧은 이름이 엉뚱하게 걸리는가")
print("=" * 74)
CASES = [
    (['가', '나', '다'], '가즈아!!', '가', "1글자 이름 '가' 가 '가즈아' 에 걸리는가"),
    (['민', '수'], '민트초코 맛있다', '민', "1글자 이름 '민' 이 '민트초코' 에"),
    (['제이양', '밍밍', '철수'], '제이양 화이팅', '제이양', '정상'),
    (['제이양', '밍밍', '철수'], '밍밍이 최고', '밍밍', '정상(접미사)'),
    (['제이양', '밍밍', '철수'], '철수했다가 다시 왔어요', '철수', "'철수했다' 안의 '철수'"),
    (['영희', '철수'], '영희랑 철수 둘 다', None, '두 명 -> 사람에게'),
]
for players, msg, expect, note in CASES:
    r = SV.suggest_target('테스터', 10000, msg, players)
    hit = r.get('target')
    tier = r.get('tier')
    mark = "위험" if (hit == expect and expect is not None and '가즈아' in msg) else ""
    print("    %-22s %-16s -> %-6s %-8s  (%s)" % (str(players), repr(msg)[:16], hit, tier, note))

r = SV.suggest_target('테스터', 10000, '가즈아!!', ['가', '나', '다'])
if r.get('target') == '가' and r.get('tier') == 'auto':
    warn("1글자 이름이 다른 낱말 속에 들어 있으면 자동 배정된다",
         "'가즈아' -> %s (%s, %.2f)" % (r['target'], r['tier'], r['confidence']))
else:
    chk("1글자 이름이 낱말 속에 걸리지 않는다", True, r.get('target'))

r = SV.suggest_target('테스터', 10000, '철수했다가 다시 왔어요', ['제이양', '밍밍', '철수'])
if r.get('target') == '철수' and r.get('tier') == 'auto':
    warn("이름과 같은 일반 낱말이 있으면 자동 배정된다",
         "'철수했다' -> %s (%.2f)" % (r['target'], r['confidence']))

print("\n" + "=" * 74)
print("(3) 별명 기억 - 한 번 본 말도 추천이 되는가")
print("=" * 74)
SV.remember_assignment('갑', '밍밍', 10000, '오늘도 잘봤어요')
r = SV.suggest_target('을', 10000, '오늘도 잘봤어요', ['제이양', '밍밍', '철수'])
print("    한 번만 본 말 '오늘도' -> %s (%s, %.2f)" % (r.get('target'), r.get('tier'), r.get('confidence')))
chk("한 번만 본 말로는 자동 배정하지 않는다", r.get('tier') != 'auto',
    "%s %.2f" % (r.get('tier'), r.get('confidence')))
if r.get('target'):
    warn("한 번만 본 말이 곧바로 '추천' 으로 뜬다",
         "'%s' -> %s (%.2f)" % ((r.get('why') or '')[:30], r.get('target'), r.get('confidence')))

print("    같은 말이 다른 사람에게도 가면?")
SV.remember_assignment('병', '철수', 10000, '오늘도 잘봤어요')
r = SV.suggest_target('정', 10000, '오늘도 잘봤어요', ['제이양', '밍밍', '철수'])
chk("두 사람을 가리킨 말은 버린다", r.get('source') != '별명', "%s / %s" % (r.get('source'), r.get('target')))

print("\n" + "=" * 74)
print("(4) 후원자 이력 - 몇 번부터 자동인가")
print("=" * 74)
for n in range(1, 7):
    donor = '단골%d' % n
    for _ in range(n):
        SV.remember_assignment(donor, '제이양', 10000, 'ㅁㅁㅁ%d' % n)
    r = SV.suggest_target(donor, 10000, '알수없는말%d' % n, ['제이양', '밍밍', '철수'])
    print("    %d번 모두 같은 사람 -> %-5s %-8s %.2f" % (n, r.get('target'), r.get('tier'), r.get('confidence')))
r1 = SV.suggest_target('단골1', 10000, '알수없는말1', ['제이양', '밍밍', '철수'])
chk("한 번뿐인 이력으로는 배정하지 않는다", r1.get('target') is None, r1.get('target'))
r4 = SV.suggest_target('단골4', 10000, '알수없는말4', ['제이양', '밍밍', '철수'])
chk("4번 이상 같으면 자동", r4.get('tier') == 'auto', "%s %.2f" % (r4.get('tier'), r4.get('confidence')))

print("    이력이 갈리면?")
SV.remember_assignment('갈림', '제이양', 1000, 'x1')
SV.remember_assignment('갈림', '제이양', 1000, 'x2')
SV.remember_assignment('갈림', '밍밍', 1000, 'x3')
r = SV.suggest_target('갈림', 10000, '알수없는말', ['제이양', '밍밍', '철수'])
chk("이력이 갈리면 자동 배정하지 않는다", r.get('tier') != 'auto',
    "%s %s %.2f" % (r.get('target'), r.get('tier'), r.get('confidence')))

print("\n" + "=" * 74)
print("(5) 이름이 바뀐 뒤 - 지금 없는 사람을 가리키면")
print("=" * 74)
r = SV.suggest_target('단골4', 10000, '알수없는말', ['새사람A', '새사람B'])
chk("지금 없는 사람은 추천하지 않는다", r.get('target') in (None, '새사람A', '새사람B'), r.get('target'))
chk("지금 없는 사람이면 모름", r.get('target') is None, r)

r = SV.suggest_target(None, 10000, None, ['가', '나'])
chk("후원자·메시지가 None 이어도 안 죽는다", r.get('target') is None, r.get('tier'))
r = SV.suggest_target('x', 0, 'y', [])
chk("플레이어가 없어도 안 죽는다", r.get('target') is None)
r = SV.suggest_target('x', 0, 'y', [{'name': '가'}, {'name': None}, {}])
chk("플레이어 목록이 지저분해도 안 죽는다", r is not None, r.get('tier'))

print("\n" + "=" * 74)
print("통과 %d · 실패 %d · 주의 %d" % (len(OK), len(BAD), len(WARN)))
for b in BAD:
    print("   [실패] " + b)
for w in WARN:
    print("   [주의] " + w)
print("=" * 74)
