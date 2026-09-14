# -*- coding: utf-8 -*-
"""🤖 진행봇 — 무엇을 알리고 무엇을 안 알리는가.

봇은 방송 중에 사람 대신 말한다. 그래서 '안 하는 것' 이 '하는 것' 만큼 중요하다:
  · 켤 때마다 지나간 일을 뒤늦게 떠들면 안 된다 (첫 상태는 기준만 잡는다)
  · 주사위는 알아보기는 하되 **말하지 않는다** — 화면에 판이 보이는데 채팅이 따라 읽으면 시끄럽다
  · 같은 후원을 두 번 알리면 안 된다
  · 목표 25·50·75·90% 는 **지나는 순간** 한 번씩만
  · 문구를 고치다 없는 값을 써도 봇이 죽으면 안 된다
  · 방송이 꺼져 있으면 아무 말도 안 한다
  · 하루 예산을 넘으면 후원 감사만 남긴다
"""
import io
import json
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


CFG0 = json.load(io.open(os.path.join(ROOT, 'bot', 'config.json'), encoding='utf-8'))


def S(**kw):
    """검사용 상태 한 벌."""
    st = {'broadcast_active': True, 'bjs': [], 'latest_donation': {'time': 0, 'amount': 0},
          'dicegame': {}, 'target_goal': 0, 'bottom_fixed': {}, 'goal_offset': 0}
    st.update(kw)
    return st


def keys(evs):
    return [e.key for e in evs]


def one(evs, key):
    """그 사건 하나만 골라낸다 — 한 번에 여러 줄이 나올 수 있을 때 쓴다."""
    got = [e for e in evs if e.key == key]
    return got[0] if got else None


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
print('①-2 후원 인사는 **리액션이 화면에 나올 때** 나간다 (스포 방지)')
print('=' * 74)
# 사장님: "후원이 후원함에 들어오자마자 저게 나오면 스포니까 리액션 할 때 나오게 해줘".
# 후원은 도착과 동시에 리액션 큐에 들어가지만, 앞에 밀린 게 있으면 화면에 나오기까지 한참이다.


def RQ(i, donator, amount, **kw):
    d = {'id': i, 'donator': donator, 'amount': amount, 'title': '시그'}
    d.update(kw)
    return d


def DON(t, name, amount, queue):
    return S(latest_donation={'time': t, 'name': name, 'amount': amount},
             reaction_queue=queue)


W = {}
# ① 앞에 두 개가 밀려 있는데 후원이 들어왔다 → 아직 아무 말 안 한다
before = DON(1, '', 0, [RQ('a', '먼저', 10000), RQ('b', '그다음', 10000)])
arrive = DON(2, '구름이', 50000,
             [RQ('a', '먼저', 10000), RQ('b', '그다음', 10000), RQ('c', '구름이', 50000)])
chk('밀려 있으면 도착해도 말 안 한다', A.detect(before, arrive, waiting=W) == [],
    keys(A.detect(before, arrive, waiting=W)))
chk('대신 기다리는 상자에 넣어둔다', 'c' in W, list(W))

# ② 앞의 둘이 재생되는 동안에도 조용하다
W2 = dict(W)
mid = DON(2, '구름이', 50000, [RQ('b', '그다음', 10000), RQ('c', '구름이', 50000)])
chk('앞의 것이 나갈 때는 조용하다', A.detect(arrive, mid, waiting=W2) == [],
    keys(A.detect(arrive, mid, waiting=W2)))

# ③ 드디어 내 차례 — 큐 머리에 올라온 순간 인사한다
play = DON(2, '구름이', 50000, [RQ('c', '구름이', 50000)])
ev = A.detect(mid, play, waiting=W2)
chk('리액션이 나올 때 인사한다', keys(ev) == ['donation'], keys(ev))
chk('그 후원의 이름·금액으로 인사한다',
    ev[0].fields == {'name': '구름이', 'amount': '50,000'}, ev[0].fields)
chk('인사한 뒤에는 상자를 비운다', 'c' not in W2, list(W2))
chk('같은 것이 두 번 나가지 않는다', A.detect(play, play, waiting=W2) == [])

# ④ 큐가 비어 있으면 도착 = 재생이다. 한 번에 인사한다
W3 = {}
now = A.detect(DON(1, '', 0, []), DON(2, '바다별', 30000, [RQ('z', '바다별', 30000)]),
               waiting=W3)
chk('큐가 비어 있으면 바로 인사한다 (그게 곧 재생이다)', keys(now) == ['donation'], keys(now))
chk('그때는 기다릴 게 없다', W3 == {}, W3)

# ⑤ 리액션이 아예 안 걸리는 후원(소액)은 깔 스포가 없다 → 바로 인사
W4 = {}
small = A.detect(DON(1, '', 0, []), DON(2, '작은손', 2000, []), waiting=W4)
chk('리액션 없는 후원은 바로 인사한다', keys(small) == ['donation'], keys(small))

# ⑥ 진행자가 건너뛰거나 큐가 넘쳐 사라지면 — 늦더라도 인사는 한다
W5 = {}
A.detect(before, arrive, waiting=W5)
gone = A.detect(arrive, DON(2, '구름이', 50000, []), waiting=W5)
chk('건너뛰어 사라져도 인사는 한다', keys(gone).count('donation') >= 1, keys(gone))
chk('그러고 상자를 비운다', W5 == {}, W5)

# ⑦ ⚠️ 큐에는 후원만 들어가는 게 아니다 — 이걸 놓치면 '주사위게임님 후원 감사합니다' 가 나간다
W6 = {}
dgq = S(latest_donation={'time': 1, 'amount': 0},
        reaction_queue=[RQ('d1', '주사위게임', 0)])
chk('주사위판이 튼 시그니처를 후원으로 착각하지 않는다',
    A.detect(S(reaction_queue=[]), dgq, waiting=W6) == [], keys(A.detect(S(reaction_queue=[]), dgq, waiting=W6)))
W7 = {}
slot = S(latest_donation={'time': 1, 'amount': 0},
         reaction_queue=[RQ('s1', '🎰 슬롯머신', 50000, skip_popup=True)])
chk('슬롯 당첨도 후원으로 착각하지 않는다',
    A.detect(S(reaction_queue=[]), slot, waiting=W7) == [])

# ⑧ 상자를 안 주면 예전처럼 — 검사에서 한 조각씩 보기 위한 길
chk('상자를 안 주면 도착할 때 인사한다 (예전 방식)',
    keys(A.detect(before, arrive)) == ['donation'])

# ⑨ 오버레이가 죽어 있을 때를 대비한 안전장치
chk('아무리 기다려도 안 나오면 먼저 인사하는 길이 있다',
    'def _sweep_waiting' in BOT and 'reaction_wait_max_sec' in BOT)
chk('그 한도를 설정으로 바꿀 수 있다', 'reaction_wait_max_sec' in CFG0)

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

# 🔇 …하지만 지금은 **아무 말도 안 한다**. 사장님: "안내봇이 주사위에 관해서 안내하는건 빼".
#    판단하는 코드는 그대로 둔다 — 문구만 비웠으니 마음이 바뀌면 문구만 넣으면 된다.
_T = A.Templates(os.path.join(ROOT, 'bot', 'messages.json'))
for k in ('dice_roll', 'dice_score', 'dice_lap', 'dice_key', 'dice_steal',
          'dice_giveall', 'dice_blackhole'):
    if _T._list(k):
        chk('주사위를 안 친다: ' + k, False, _T._list(k))
chk('주사위 사건을 알아보기는 하되 입은 막았다', True)
chk('주사위 문구는 보관함에 그대로 있다 (되돌릴 수 있다)',
    all((_T.data.get('_꺼둔_문구') or {}).get(k)
        for k in ('dice_roll', 'dice_lap', 'dice_key', 'dice_steal',
                  'dice_giveall', 'dice_blackhole')))

print()
print('=' * 74)
print('②-2 점수 배정 — 한 건씩 알리지 않는다')
print('=' * 74)
# 사장님: "후원이 나올 때 누가 후원했는지가 필요한 거지, 점수 들어가는 거 하나하나
#          쓸 필요 없어". 후원 인사에 이미 후원자 이름이 들어 있다.
_b0 = S(bjs=[{'name': '가', 'contribution': 100}, {'name': '나', 'contribution': 50}])
_b1 = S(bjs=[{'name': '가', 'contribution': 100}, {'name': '나', 'contribution': 90}])
chk('점수가 올라도 그것만으로는 아무 말 안 한다', A.detect(_b0, _b1) == [],
    keys(A.detect(_b0, _b1)))
chk('나눠주기도 조용하다',
    A.detect(_b0, S(bjs=[{'name': '가', 'contribution': 130},
                         {'name': '나', 'contribution': 80}])) == [])
chk('배정 알림 코드가 남아 있지 않다',
    'score_up' not in BOT and 'P_SCORE' not in BOT)
# 대신 후원 인사가 '누가 얼마' 를 말한다 — 그게 사장님이 필요하다고 한 그것이다
_t = A.Templates(os.path.join(ROOT, 'bot', 'messages.json'))
chk('후원 인사에 후원자 이름이 들어간다',
    all('{name}' in x for x in _t._list('donation')), _t._list('donation'))
chk('후원 인사에 금액도 들어간다', all('{amount}' in x for x in _t._list('donation')))

print()
print('=' * 74)
print('③ 1위 · 목표')
print('=' * 74)
p = S(bjs=[{'name': '가', 'contribution': 10}, {'name': '나', 'contribution': 5}])
c = S(bjs=[{'name': '가', 'contribution': 10}, {'name': '나', 'contribution': 30}])
chk('1위가 바뀌면 알린다', keys(A.detect(p, c)) == ['rank_top'], keys(A.detect(p, c)))
chk('누가 1등인지 싣는다', one(A.detect(p, c), 'rank_top').fields['name'] == '나')
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
print('⑥ 순위 격차 · 접전')
print('=' * 74)
# 화면 순위표는 기여도 순이다. 봇이 말하는 순위가 화면과 다르면 시청자가 봇을 안 믿는다.
three = S(bjs=[{'name': '가', 'contribution': 300000},
               {'name': '나', 'contribution': 120000},
               {'name': '다', 'contribution': 50000}])
chk('기여도 큰 순으로 줄 세운다',
    [r[1] for r in A.rank_rows(three)] == ['가', '나', '다'], A.rank_rows(three))
chk('기여도 0 은 순위에 안 넣는다',
    A.rank_rows(S(bjs=[{'name': '가', 'contribution': 0}])) == [])
chk('동점이면 이름순 — 서버와 같은 규칙',
    [r[1] for r in A.rank_rows(S(bjs=[{'name': '나', 'contribution': 5},
                                      {'name': '가', 'contribution': 5}]))] == ['가', '나'])

# 1위가 바뀌면 '2위와 몇 점 차' 까지
p2 = S(bjs=[{'name': '가', 'contribution': 100}, {'name': '나', 'contribution': 10}])
c2 = S(bjs=[{'name': '가', 'contribution': 100}, {'name': '나', 'contribution': 150}])
e = one(A.detect(p2, c2), 'rank_top')
chk('1위 바뀜에 2위 이름이 실린다', e.fields.get('second') == '가', e.fields)
chk('1위 바뀜에 격차가 실린다', e.fields.get('gap') == '50', e.fields)
chk('혼자면 격차 없는 칸을 쓴다',
    keys(A.detect(S(bjs=[{'name': '가', 'contribution': 0}]),
                  S(bjs=[{'name': '가', 'contribution': 9}]))) == ['rank_top_only'])

# 접전 — 격차가 기준 밑으로 **내려오는 순간**만
far = S(bjs=[{'name': '가', 'contribution': 300000}, {'name': '나', 'contribution': 100000}])
near = S(bjs=[{'name': '가', 'contribution': 300000}, {'name': '나', 'contribution': 280000}])
chk('격차가 좁혀지면 접전을 외친다', 'rank_close' in keys(A.detect(far, near)), keys(A.detect(far, near)))
chk('접전 격차를 싣는다', one(A.detect(far, near), 'rank_close').fields['gap'] == '20,000')
chk('이미 붙어 있으면 다시 안 외친다', A.detect(near, near) == [], keys(A.detect(near, near)))
nearer = S(bjs=[{'name': '가', 'contribution': 300000}, {'name': '나', 'contribution': 295000}])
chk('붙은 채로 더 붙어도 안 외친다', one(A.detect(near, nearer), 'rank_close') is None,
    keys(A.detect(near, nearer)))
chk('기준을 0 으로 두면 접전을 안 쓴다',
    'rank_close' not in keys(A.detect(far, near, close_gap=0)))
chk('벌어지는 쪽으로는 안 외친다', 'rank_close' not in keys(A.detect(near, far)))

print()
print('=' * 74)
print('⑦ 주기 안내 — 중간에 들어온 시청자용')
print('=' * 74)
acc = S(account={'bank': '기업은행', 'acc_num': '464-068673-04-016', 'name': '엔젤컴퍼니'})
got = A.notice_account(acc)
chk('계좌 안내를 만든다', got and got[0] == 'notice.account', got)
chk('계좌번호를 그대로 싣는다', got[1]['acc_num'] == '464-068673-04-016')
chk('계좌가 없으면 안 만든다', A.notice_account(S()) is None)

chk('셋 이상이면 3위까지', A.notice_rank(three)[0] == 'notice.rank3')
r3 = A.notice_rank(three)[1]
chk('1·2위 격차를 싣는다', r3['gap'] == '180,000', r3)
chk('2·3위 격차도 싣는다', r3['gap2'] == '70,000', r3)
chk('숫자에 쉼표를 넣는다', r3['first_score'] == '300,000')
chk('둘뿐이면 2위까지', A.notice_rank(S(bjs=[{'name': '가', 'contribution': 9},
                                            {'name': '나', 'contribution': 4}]))[0] == 'notice.rank2')
chk('혼자면 순위 안내를 안 한다',
    A.notice_rank(S(bjs=[{'name': '가', 'contribution': 9}])) is None)

jar = S(fundjar={'enabled': True, 'seed': 200000, 'score': 137000})
chk('모금함 안내를 만든다', A.notice_fundjar(jar)[0] == 'notice.fundjar')
chk('모금함은 종잣돈+후원분을 더한다', A.notice_fundjar(jar)[1]['total'] == '337,000',
    A.notice_fundjar(jar)[1])
chk('모금함이 꺼져 있으면 안 한다',
    A.notice_fundjar(S(fundjar={'enabled': False, 'seed': 200000})) is None)
chk('모금함이 0 이면 안 한다',
    A.notice_fundjar(S(fundjar={'enabled': True, 'seed': 0, 'score': 0})) is None)

# 문구표의 빈칸이 실제로 다 채워지는가 — 하나라도 안 맞으면 그 안내는 통째로 안 나간다
TPL = A.Templates(os.path.join(ROOT, 'bot', 'messages.json'))
CFG = json.load(io.open(os.path.join(ROOT, 'bot', 'config.json'), encoding='utf-8'))
for key, fields in [A.notice_account(acc), A.notice_rank(three), A.notice_fundjar(jar)]:
    opts = TPL._list(key)
    outs = [TPL.render(key, fields) for _ in opts]   # 돌아가며 쓰니 모든 문구를 한 번씩 본다
    chk('문구 \"%s\" 가 빠짐없이 채워진다' % key, bool(opts) and all(outs), outs)

chk('안내는 사건보다 뒤로 밀린다',
    A.P_DONATION < A.P_DICE_BIG < A.P_RANK < A.P_NOTICE < A.P_IDLE)

print()
print('=' * 74)
print('⑧ 무엇을 안 치는가 — 사장님이 빼 달라 하신 것들')
print('=' * 74)
# 화면에 이미 다 있는 것들이다. 채팅까지 같은 말을 하면 시끄럽기만 하다.
# 주사위는 ② 에서 따로 본다 — 알아보기는 하되 입은 막았다
chk('목표 진행(50%)을 안 친다', TPL._list('goal') == [], TPL._list('goal'))
chk('목표 달성도 안 친다', TPL._list('goal_done') == [])
chk('접전(점수차)을 안 친다', TPL._list('rank_close') == [])
chk('순위 요약(점수차)을 꺼 뒀다', CFG['notices']['rank_every_sec'] == 0)
chk('모금함을 꺼 뒀다', CFG['notices']['fundjar_every_sec'] == 0)
chk('1위 바뀜에는 점수차를 안 붙인다',
    all('{gap}' not in t and '{second}' not in t for t in TPL._list('rank_top')),
    TPL._list('rank_top'))

# 남는 것 — 이게 전부다
chk('후원 감사는 남는다', bool(TPL._list('donation')))
chk('점수 배정은 한 건씩 안 알린다 (②-2 참고)', 'score_up' not in BOT)
chk('1위 바뀜은 남는다', bool(TPL._list('rank_top')))
chk('계좌 안내는 남는다',
    bool(TPL._list('notice.account')) and CFG['notices']['account_every_sec'] > 0)
chk('조용할 때 질문은 남는다', bool(TPL._list('idle.any')))

# 되돌릴 수 있어야 한다 — 지운 게 아니라 옮긴 것이다
BOX = TPL.data.get('_꺼둔_문구') or {}
for k in ('dice_roll', 'dice_lap', 'dice_key', 'dice_steal', 'dice_giveall',
          'dice_blackhole', 'goal', 'goal_done', 'rank_close'):
    if not BOX.get(k):
        chk('되돌릴 문구가 남아 있다: ' + k, False)
chk('꺼 둔 문구를 전부 되돌릴 수 있다', True)

chk('문구가 빈 사건은 큐에 넣지도 않는다', 'self.tpl.has(e.key)' in BOT)
chk('빈 칸인지 물어볼 수 있다', TPL.has('donation') and not TPL.has('goal'))
# ⚠️ 주사위판이 켜져 있으면 질문 바구니가 'dice' 로 간다. 그걸 비웠으니
#    보통 질문으로 되돌아가야 한다 — 안 그러면 봇이 내내 한마디도 안 한다.
chk('비운 질문 바구니는 보통 질문으로 되돌아간다',
    "key = 'idle.any'" in BOT and 'if not self.tpl.has(key)' in BOT)

print()
print('=' * 74)
print('⑨ 문구표 — 사장님이 고치다 틀려도 안 죽는다')
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
# 코드가 쓰는 칸 전부. 일부러 비워 둔 것(그냥 굴림·점수 칸)은 빼고 센다 —
# 비워 두는 것도 손잡이다. 대신 보관함에 남아 있는지는 ⑧ 에서 따로 본다.
# 🔇 사장님이 "빼 달라" 하신 것들. 지우지 않고 _꺼둔_문구 에 옮겨 뒀다 —
#    코드는 그대로라 문구만 되돌리면 다시 켜진다.
MUTED = ('dice_roll', 'dice_score', 'dice_lap', 'dice_key', 'dice_steal',
         'dice_giveall', 'dice_blackhole', 'goal', 'goal_done', 'rank_close')
USED = ('dice_roll', 'dice_lap', 'dice_key', 'dice_steal', 'dice_giveall',
        'dice_blackhole', 'dice_score', 'rank_top', 'rank_top_only', 'rank_close',
        'goal', 'goal_done', 'notice.account', 'notice.rank2', 'notice.rank3',
        'notice.fundjar')
for k in USED:
    if k in MUTED:
        continue
    if not T._list(k):
        chk('문구가 있다: ' + k, False)
chk('쓰는 문구가 전부 문구표에 있다', True)
# 반대쪽도 본다 — 코드가 안 쓰는 칸을 문구표에만 적어 두면 사장님은 고쳤다고 믿는데
# 아무 일도 안 일어난다. 그게 제일 찾기 어려운 고장이다.
DOCS = {'_읽는법', '_꺼둔_문구', 'idle'}
for k in T.data:
    if k in DOCS:
        continue
    kk = ['notice.' + x for x in T.data[k] if not x.startswith('_')] if k == 'notice' else [k]
    for one in kk:
        if one not in USED and one != 'donation':
            chk('문구표에만 있고 코드는 안 쓰는 칸: ' + one, False)
chk('문구표에 헛된 칸이 없다', True)
# ⚠️ 'dice'·'goal' 바구니는 일부러 비워 뒀다(주사위·목표 얘기를 안 하기로 했다).
#    그래서 'any' 만 있으면 된다 — 비운 바구니는 코드가 'any' 로 되돌린다(⑧ 에서 확인).
chk('조용할 때 질문이 있다: any', bool((T.data.get('idle') or {}).get('any')))

print()
print('=' * 74)
print('⑪ 말수·안전 — 코드에 규칙이 박혀 있는가')
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
print('⑫ 계정 연동 · 유튜브로 내보내기')
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
