# -*- coding: utf-8 -*-
"""🤖 진행봇 — 무엇을 알리고 무엇을 안 알리는가.

봇은 방송 중에 사람 대신 말한다. 그래서 '안 하는 것' 이 '하는 것' 만큼 중요하다:
  · 켤 때마다 지나간 일을 뒤늦게 떠들면 안 된다 (첫 상태는 기준만 잡는다)
  · 한 번 굴림에 한 줄만. 사건마다 한 줄이면 채팅이 도배된다
  · 같은 후원을 두 번 알리면 안 된다
  · 목표 25·50·75·90% 는 **지나는 순간** 한 번씩만
  · 문구를 고치다 없는 값을 써도 봇이 죽으면 안 된다
  · 방송이 꺼져 있으면 아무 말도 안 한다
  · 하루 예산을 넘으면 후원 감사만 남긴다
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
sys.path.insert(0, os.path.join(ROOT, 'bot'))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


import announce as A   # noqa: E402

BOT = io.open(os.path.join(ROOT, 'bot', 'announce.py'), encoding='utf-8', errors='replace').read()
SRV = io.open(os.path.join(ROOT, 'server.py'), encoding='utf-8', errors='replace').read()


def S(**kw):
    """검사용 상태 한 벌."""
    st = {'broadcast_active': True, 'bjs': [], 'latest_donation': {'time': 0, 'amount': 0},
          'dicegame': {}, 'target_goal': 0, 'bottom_fixed': {}, 'goal_offset': 0}
    st.update(kw)
    return st


def keys(evs):
    return [e.key for e in evs]


print('=' * 74)
print('① 후원')
print('=' * 74)
a = S(latest_donation={'time': 100, 'amount': 10000, 'name': '구름이'})
b = S(latest_donation={'time': 200, 'amount': 10000, 'name': '구름이'})
chk('새 후원을 알린다', keys(A.detect(a, b)) == ['donation'], keys(A.detect(a, b)))
chk('같은 후원은 두 번 안 알린다', A.detect(b, b) == [], keys(A.detect(b, b)))
z = S(latest_donation={'time': 300, 'amount': 0, 'name': '구름이'})
chk('0원 후원은 안 알린다', A.detect(b, z) == [], keys(A.detect(b, z)))
chk('금액에 쉼표를 넣는다', A.detect(a, b)[0].fields['amount'] == '10,000',
    A.detect(a, b)[0].fields['amount'])

print()
print('=' * 74)
print('② 주사위 — 한 번 굴림에 한 줄만')
print('=' * 74)


def roll(ts, **extra):
    act = {'ts': ts, 'type': 'ROLL', 'piece': '예지랑', 'dice': [5], 'to': 10,
           'tile': {'type': 'mission', 'label': '코끼리코'}}
    act.update(extra)
    return S(dicegame={'action': act})


r0, r1 = roll(1), roll(2)
chk('굴리면 한 줄', len(A.detect(r0, r1)) == 1, keys(A.detect(r0, r1)))
chk('같은 굴림은 다시 안 알린다', A.detect(r1, r1) == [])
# ⚠️ 조종실에서 말을 손으로 옮긴 것(MOVE)은 게임 사건이 아니다 — 판 정리할 때마다 떠들면 안 된다
mv = S(dicegame={'action': {'ts': 99, 'type': 'MOVE', 'piece': '예지랑', 'to': 0}})
chk('손으로 옮긴 것은 안 알린다', A.detect(r1, mv) == [], keys(A.detect(r1, mv)))
chk('그냥 이동은 dice_roll', keys(A.detect(r0, r1)) == ['dice_roll'])
chk('주사위 눈을 합쳐 적는다', A.detect(r0, roll(3, dice=[3, 4]))[0].fields['dice'] == '3+4')

lap = roll(4, lap_contrib={'name': '예지랑', 'points': 10})
chk('한 바퀴면 dice_lap', keys(A.detect(r0, lap)) == ['dice_lap'])
chk('한 바퀴 점수를 싣는다', A.detect(r0, lap)[0].fields['points'] == 10)

# ⚠️ 한 굴림에 여러 사건이 겹칠 수 있다(한 바퀴 돌며 블랙홀). 그때도 한 줄이어야 한다.
bh = roll(5, lap_contrib={'name': '예지랑', 'points': 10}, after={'kind': 'goto', 'to': 0})
chk('블랙홀이 한 바퀴보다 앞선다', keys(A.detect(r0, bh)) == ['dice_blackhole'], keys(A.detect(r0, bh)))
chk('겹쳐도 한 줄', len(A.detect(r0, bh)) == 1)

key = roll(6, key='파산', key_effect='전용 판 점수가 0이 됩니다')
chk('황금열쇠를 알린다', keys(A.detect(r0, key)) == ['dice_key'])
chk('열쇠 내용을 싣는다', '0이 됩니다' in A.detect(r0, key)[0].fields['effect'])
st = roll(7, steal={'taker': '예지랑', 'per': 5})
chk('뺏어오기를 알린다', keys(A.detect(r0, st)) == ['dice_steal'])

big = {'dice_blackhole', 'dice_key', 'dice_steal', 'dice_giveall', 'dice_lap'}
# 1위가 바뀌는 건 그냥 굴림보다 위다 — 큐가 밀릴 때 순서가 거꾸로 남으면 안 된다
chk('1위 바뀜이 그냥 굴림보다 앞선다', A.P_RANK < A.P_DICE, (A.P_RANK, A.P_DICE))
chk('후원이 제일 앞선다', A.P_DONATION < min(A.P_DICE_BIG, A.P_RANK, A.P_DICE, A.P_GOAL))
chk('큰 사건은 그냥 굴림보다 먼저 나간다',
    all(A.detect(r0, roll(9, **x))[0].prio == A.P_DICE_BIG
        for x in ({'after': {'kind': 'goto'}}, {'key_effect': 'x'},
                  {'steal': {'per': 5}}, {'lap_contrib': {'points': 10}})))

print()
print('=' * 74)
print('③ 1위 · 목표')
print('=' * 74)
p = S(bjs=[{'name': '가', 'contribution': 10}, {'name': '나', 'contribution': 5}])
c = S(bjs=[{'name': '가', 'contribution': 10}, {'name': '나', 'contribution': 30}])
chk('1위가 바뀌면 알린다', keys(A.detect(p, c)) == ['rank_top'], keys(A.detect(p, c)))
chk('누가 1등인지 싣는다', A.detect(p, c)[0].fields['name'] == '나')
chk('안 바뀌면 안 알린다', A.detect(c, c) == [])
chk('아무도 기여도가 없으면 안 알린다',
    A.detect(S(bjs=[{'name': '가', 'contribution': 0}]),
             S(bjs=[{'name': '가', 'contribution': 0}])) == [])

g0 = S(target_goal=100000, bjs=[{'name': '가', 'score': 40000}])
g1 = S(target_goal=100000, bjs=[{'name': '가', 'score': 55000}])
chk('50%를 지나면 알린다', keys(A.detect(g0, g1)) == ['goal'], keys(A.detect(g0, g1)))
chk('몇 %인지 · 얼마 남았는지 싣는다',
    A.detect(g0, g1)[0].fields == {'percent': 50, 'remain': '45,000'},
    A.detect(g0, g1)[0].fields)
chk('같은 구간에서 또 알리지 않는다',
    A.detect(g1, S(target_goal=100000, bjs=[{'name': '가', 'score': 60000}])) == [])
chk('목표를 넘으면 축하', keys(A.detect(g1, S(target_goal=100000,
                                            bjs=[{'name': '가', 'score': 120000}]))) == ['goal_done'])
chk('목표가 0이면 아무 말 안 한다', A.detect(S(), S(bjs=[{'name': '가', 'score': 9999}])) == [])
# ⚠️ 막대와 같은 셈이어야 한다 — 기여도 합을 쓰면 막대가 차기 전에 '넘었다' 고 한다
chk('목표 셈이 서버(_goal_waiting)와 같다',
    "bottom_fixed" in BOT and "goal_offset" in BOT
    and "state.get('goal_offset')" in SRV)
chk('운영비·보정도 센다',
    A.goal_total({'bjs': [{'score': 10}], 'bottom_fixed': {'score': 20}, 'goal_offset': 30}) == 60)

print()
print('=' * 74)
print('④ 문구표 — 사장님이 고치다 틀려도 안 죽는다')
print('=' * 74)
T = A.Templates(os.path.join(ROOT, 'bot', 'messages.json'))
chk('문구표를 읽는다', bool(T.render('donation', {'name': '가', 'amount': '1,000'})))
chk('빈칸을 채운다', '가님' in T.render('donation', {'name': '가', 'amount': '1,000'}))
s1 = T.render('donation', {'name': '가', 'amount': '1'})
s2 = T.render('donation', {'name': '가', 'amount': '1'})
chk('같은 말을 연달아 안 쓴다 (돌아가며)', s1 != s2, (s1, s2))
chk('없는 값을 쓰면 안 치고 넘어간다 (안 죽는다)',
    T.render('donation', {'name': '가'}) is None)
chk('없는 칸이면 안 친다', T.render('있지도않은칸', {}) is None)
T2 = A.Templates(os.path.join(ROOT, 'bot', 'messages.json'))
T2.data['donation'] = []
chk('칸을 비우면 그 사건은 안 친다 (말 줄이는 손잡이)',
    T2.render('donation', {'name': '가', 'amount': '1'}) is None)
for k in ('dice_roll', 'dice_lap', 'dice_key', 'dice_steal', 'dice_giveall',
          'dice_blackhole', 'dice_score', 'rank_top', 'goal', 'goal_done'):
    if not T.data.get(k):
        chk('문구가 있다: ' + k, False)
chk('쓰는 문구가 전부 문구표에 있다', True)
for k in ('dice', 'goal', 'any'):
    chk('조용할 때 질문이 있다: ' + k, bool((T.data.get('idle') or {}).get(k)))

print()
print('=' * 74)
print('⑤ 말수·안전 — 코드에 규칙이 박혀 있는가')
print('=' * 74)
chk('첫 상태로는 아무 말도 안 한다 (켤 때마다 지난 일을 떠들면 안 된다)',
    'if self.prev is None:' in BOT and '기준 상태를 잡았습니다' in BOT)
chk('최소 간격을 지킨다', 'now - self.last_sent < self.interval' in BOT)
chk('방송이 꺼져 있으면 조용하다', "self.state.get('broadcast_active')" in BOT)
chk('밀리면 낮은 것부터 버린다 (뒤늦은 소식은 더 이상하다)',
    'len(self.q) > 6' in BOT and 'sorted(self.q, key=lambda x: (x.prio, x.at))' in BOT)
chk('하루 예산을 넘으면 후원 감사만 남긴다',
    "self.sent_today >= int(self.cfg.get('daily_budget'" in BOT and 'e.prio != P_DONATION' in BOT)
chk('막히면 스스로 느려진다', "'rateLimit' in str(err)" in BOT and 'self.interval * 2' in BOT)
chk('조용할 때만 질문한다', 'idle_after_sec' in BOT and 'P_IDLE' in BOT)
chk('AI 를 안 쓴다 (안내만 하면 된다)',
    not re.search(r'nvidia|openai|anthropic|nim|gpt', BOT, re.I))
chk('방송 서버 코드를 안 건드린다 (봇은 그냥 또 하나의 손님)',
    '/api/stream' in BOT and 'import server' not in BOT)
chk('입 막고 돌리는 게 기본 (--live 를 줘야 진짜 친다)',
    "'--live'" in BOT and 'action=\'store_true\'' in BOT and 'dryrun.log' in BOT)
chk('입 막았을 때는 유튜브 쪽을 아예 안 불러온다',
    'from youtube import YouTube' in BOT and BOT.index('if args.live') < BOT.index('from youtube'))
chk('새 의존성이 없다 (표준 라이브러리만)',
    not re.search(r'^\s*import\s+(requests|google|httpx)', BOT, re.M))

print()
print('=' * 74)
print('⑥ 계정 연동 · 유튜브로 내보내기')
print('=' * 74)
LINK = io.open(os.path.join(ROOT, 'bot', 'link.py'), encoding='utf-8', errors='replace').read()
YT = io.open(os.path.join(ROOT, 'bot', 'youtube.py'), encoding='utf-8', errors='replace').read()
GI = io.open(os.path.join(ROOT, '.gitignore'), encoding='utf-8', errors='replace').read()

# 권한은 연동할 때 한 번만 받는다. 전송 쪽은 그때 받은 열쇠만 쓰므로 권한 문자열이 없다.
# ⚠️ force-ssl 은 '채팅 쓰기' 에 필요한 최소 권한이다. 영상 관리까지 되는 넓은 권한을
#    받으면 열쇠가 새어나갔을 때 피해가 커진다.
chk('채팅 쓰기에 필요한 최소 권한만 받는다', 'youtube.force-ssl' in LINK)
chk('넓은 권한은 안 받는다',
    'youtubepartner' not in LINK and "'https://www.googleapis.com/auth/youtube'" not in LINK)
# ⚠️ 둘 다 없으면 갱신 토큰이 안 와서 한 시간 뒤 봇이 조용히 멈춘다
chk('갱신 토큰을 받게 돼 있다', "'access_type': 'offline'" in LINK and "'prompt': 'consent'" in LINK)
chk('갱신 토큰이 안 오면 알려준다', 'refresh_token' in LINK and '갱신 토큰이 안 왔습니다' in LINK)
# ⚠️ 제일 흔한 실수가 본계정으로 로그인하는 것이다 — 어느 채널에 묶였는지 반드시 보여준다
chk('어느 계정에 묶였는지 보여준다 (본계정 실수 잡기)',
    'def whoami' in LINK and 'channels?part=snippet&mine=true' in LINK
    and '본계정이면 다시 연동' in LINK)
chk('나중에 확인할 길이 있다', "'--check'" in LINK and 'def check()' in LINK)
chk('열쇠는 저장소에 안 올라간다', 'bot/token.json' in GI)
chk('열쇠를 남에게 주지 말라고 적어 뒀다', '남에게 보내지 마세요' in LINK)

chk('채팅 한 줄 올리는 모양이 맞다',
    "'type': 'textMessageEvent'" in YT and "'liveChatId'" in YT
    and "'textMessageDetails'" in YT and 'messageText' in YT)
chk('라이브를 자동으로 찾는다 (방송마다 주소 안 붙여넣게)',
    'broadcastStatus=active' in YT and 'mine=true' in YT)
chk('방송이 끝나면 채팅방을 다시 찾는다',
    "'liveChatEnded' in detail" in YT and 'self.chat_id = None' in YT)
chk('올리다 실패해도 봇은 안 죽는다', 'return False,' in YT and 'except Exception as e' in YT)
chk('토큰은 만료 전에 미리 바꾼다', 'self._exp - 60' in YT)
chk('연동·전송도 새 의존성이 없다',
    not re.search(r'^\s*import\s+(requests|google|httpx|oauthlib)', LINK + YT, re.M))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
if BAD:
    for b in BAD:
        print('  - ' + b)
    sys.exit(1)
