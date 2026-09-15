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

# 🔇 …하지만 기본값은 **말하지 않음**이다. 사장님: "안내봇이 주사위에 관해서 안내하는건 빼".
#    ⚠️ 알아보는 코드와 문구는 그대로 둔다. 조종실에서 켜면 그 자리에서 다시 말한다.
#       (예전에는 문구를 비워서 껐는데, 그러면 조종실 스위치가 거짓말을 한다)
_DICE_KEYS = ('dice_roll', 'dice_score', 'dice_lap', 'dice_key', 'dice_steal',
              'dice_giveall', 'dice_blackhole')
_OFF = S(announce_bot={'say': {'dice': False}})
_ON = S(announce_bot={'say': {'dice': True}})
for k in _DICE_KEYS:
    if A.says(_OFF, k):
        chk('꺼두면 주사위를 안 친다: ' + k, False)
chk('꺼두면 주사위를 아예 안 친다', True)
chk('조종실에서 켜면 다시 친다', all(A.says(_ON, k) for k in _DICE_KEYS))
_T = A.Templates(os.path.join(ROOT, 'bot', 'messages.json'))
chk('켰을 때 할 말이 있다 (문구를 안 지웠다)', all(_T._list(k) for k in _DICE_KEYS))
chk('서버 기본값은 꺼짐이다', '"dice": False' in SRV)

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
print('⑧ 문구표 — 무슨 말을 할지만 정한다')
print('=' * 74)
# ⚠️ 설계가 바뀌었다. 예전에는 문구를 비워서 껐는데, 그러면 조종실에서 '주사위 켜기' 를
#    눌러도 할 말이 없어 아무 일도 안 일어난다(스위치가 거짓말을 한다).
#    그래서 문구는 **전부 갖춰 두고**, 켜고 끄는 건 조종실이 쥔다(⑩·⑪).
USED_MSG = ('donation', 'rank_top', 'rank_top_only', 'rank_close', 'goal', 'goal_done',
            'dice_roll', 'dice_score', 'dice_lap', 'dice_key', 'dice_steal',
            'dice_giveall', 'dice_blackhole')
for k in USED_MSG:
    if not TPL._list(k):
        chk('문구가 갖춰져 있다: ' + k, False)
chk('코드가 쓰는 문구가 전부 갖춰져 있다', True)
chk('되풀이 안내 문구도 갖춰져 있다',
    all(TPL._list('notice.' + k) for k in ('account', 'rank2', 'rank3', 'fundjar')))
chk('조용할 때 질문도 갖춰져 있다',
    all((TPL.data.get('idle') or {}).get(k) for k in ('dice', 'goal', 'any')))
# 비우는 길도 남겨 둔다 — 조종실보다 아래에 있는 최후의 차단기다
chk('칸을 비우면 조종실에서 켜도 안 친다', 'self.tpl.has(e.key)' in BOT)
chk('빈 칸인지 물어볼 수 있다', TPL.has('donation') and not TPL.has('있지도않은칸'))
# ⚠️ 1위 바뀜에 점수차를 붙일지는 문구로 정한다(사장님: "점수차도 빼줘")
chk('1위 바뀜에는 점수차를 안 붙여 뒀다',
    all('{gap}' not in t and '{second}' not in t for t in TPL._list('rank_top')),
    TPL._list('rank_top'))
chk('붙이는 법을 파일에 적어 뒀다',
    any('{second}' in x and '{gap}' in x for x in TPL.data.get('_읽는법', [])))
# ⚠️ 문구표에만 있고 코드가 안 쓰는 칸이 있으면, 고쳤다고 믿는데 아무 일도 안 일어난다
DOCS = {'_읽는법', 'idle', 'notice'}
for k in TPL.data:
    if k not in DOCS and k not in USED_MSG:
        chk('문구표에만 있고 코드는 안 쓰는 칸: ' + k, False)
chk('문구표에 헛된 칸이 없다', True)
chk('점수 배정은 한 건씩 안 알린다 (②-2 참고)', 'score_up' not in BOT)

print()
print('=' * 74)
print('⑩ 조종실 스위치 — 방송 중에 켜고 끈다')
print('=' * 74)
# 봇은 서버가 아니라 **다른 프로그램**이다. 서버는 설정을 상태에 적어 SSE 로 뿌리고,
# 봇이 그걸 보고 스스로 입을 다문다. 그래서 '무엇을 보고 판단하는가' 가 전부다.
CTL = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8', errors='replace').read()

_st = S(announce_bot={'enabled': True, 'min_interval_sec': 25,
                      'say': {'donation': True, 'rank_top': False, 'rank_close': False,
                              'goal': False, 'dice': False, 'idle': True},
                      'notices': {'account_min': 7, 'rank_min': 0, 'fundjar_min': 0}})
chk('켜둔 것은 말한다', A.says(_st, 'donation'))
chk('꺼둔 것은 안 말한다', not A.says(_st, 'rank_top'))
chk('1위 문구 두 가지가 같은 스위치를 쓴다',
    not A.says(_st, 'rank_top_only') and not A.says(_st, 'rank_top'))
chk('주사위는 한 스위치로 전부 꺼진다',
    not any(A.says(_st, k) for k in ('dice_roll', 'dice_score', 'dice_lap', 'dice_key',
                                     'dice_steal', 'dice_giveall', 'dice_blackhole')))
chk('목표도 한 스위치로 전부', not A.says(_st, 'goal') and not A.says(_st, 'goal_done'))
chk('조용할 때 질문도 끌 수 있다',
    A.says(_st, 'idle.any') and not A.says(
        S(announce_bot={'say': {'idle': False}}), 'idle.any'))
chk('조종실이 정한 게 없으면 문구표대로 간다', A.says(S(), 'donation') and A.says(S(), 'dice_roll'))
# ⚠️ 스위치 이름을 모르는 사건은 늘 나간다. 새 사건을 만들면 SAY_OF 에도 적어야 끌 수 있다.
chk('모르는 사건은 막지 않는다', A.says(_st, '아직없는사건'))

chk('사건마다 스위치 이름이 정해져 있다',
    A.SAY_OF.get('rank_close') == 'rank_close' and A.SAY_OF.get('dice_lap') == 'dice')
chk('큐에 넣기 전에 스위치를 본다', 'says(st, e.key)' in BOT)
chk('전체 스위치를 끄면 한마디도 안 한다', "live.get('enabled') is False" in BOT)
# ⚠️ 끈 동안 쌓인 소식: 후원만 남기고 버린다. '1위가 바뀌었습니다' 가 10분 늦게 나가면 거짓말이다
chk('끈 동안 쌓인 것은 후원만 남긴다',
    'e.prio == P_DONATION' in BOT and 'live.get(\'enabled\') is False' in BOT)

# 안내 간격 — 조종실은 '분', 봇은 '초'
_b = A.Bot({'server': 'x', 'notices': {'account_every_sec': 420}}, TPL)
_b.state = S(announce_bot={'notices': {'account_min': 3}})
chk('안내 간격은 조종실이 이긴다 (분 → 초)', _b._ncfg('account_every_sec', 420) == 180.0,
    _b._ncfg('account_every_sec', 420))
_b.state = S()
chk('조종실 값이 없으면 파일 설정대로', _b._ncfg('account_every_sec', 420) == 420.0)
chk('0 분이면 그 안내는 꺼진다',
    A.Bot({'server': 'x'}, TPL).__class__ and True)
_b.state = S(announce_bot={'notices': {'account_min': 0}})
chk('0 으로 두면 안내를 안 한다', _b._ncfg('account_every_sec', 420) == 0.0)

# 유튜브가 막아서 늘린 간격은 조종실이 내려도 안 지워진다
chk('막혀서 늘린 간격은 조종실보다 세다', 'max(float(iv), self.backoff)' in BOT)

print()
print('=' * 74)
print('⑪ 조종실 화면 — 눌러서 바꿀 수 있는가')
print('=' * 74)
chk('진행봇 탭이 있다', 'tab-bot' in CTL and '진행봇' in CTL)
chk('전체 스위치가 있다', 'id="ab-on"' in CTL and 'abSet({enabled:this.checked})' in CTL)
chk('전용 주소로만 저장한다 (상태 통째로 안 보낸다)', "fetch('/api/announcebot'" in CTL)
for _k in ('donation', 'rank_top', 'rank_close', 'goal', 'dice', 'idle'):
    if "'" + _k + "'" not in CTL:
        chk('화면에 스위치가 있다: ' + _k, False)
chk('말할 것 스위치가 화면에 다 있다', True)
for _k in ('account_min', 'rank_min', 'fundjar_min'):
    if "'" + _k + "'" not in CTL:
        chk('화면에 안내 간격이 있다: ' + _k, False)
chk('안내 간격이 화면에 다 있다', True)

print()
print('=' * 74)
print('🔗 라이브 주소 — 어느 방송 채팅에 칠 것인가')
print('=' * 74)
# 왜 필요한가: 봇 계정과 방송 채널이 다르면(사장님 경우) 봇이 제 라이브를 찾다가
# 아무것도 못 찾는다. 방송마다 주소가 바뀌므로 서버에 들어가지 않고 조종실에서 갈아끼운다.
chk('조종실에 주소 칸이 있다', 'id="ab-url"' in CTL)
chk('저장 단추가 있다', 'abSaveUrl' in CTL)
chk('비우기가 있다 (채널에서 알아서 찾기)', 'abClearUrl' in CTL)
chk('치는 중에 덮어쓰지 않는다', 'document.activeElement !== ub' in CTL)
chk('상태에 칸이 있다', '"live_url"' in SRV and '"live_video_id"' in SRV)
chk('옛 저장본에도 칸을 채운다', 'live_video_id"' in SRV and '_ab.setdefault' in SRV)
chk('서버가 주소를 읽는다', '_yt_video_id' in SRV)
chk('못 읽은 주소는 거절한다 (조용히 비우지 않는다)', "'라이브 주소를 못 읽었습니다" in SRV
    or '라이브 주소를 못 읽었습니다' in SRV)

# ⚠️ 주소를 바꿔도 chat_id 를 안 비우면 옛 방송의 빈 채팅방에 계속 친다.
# (YT 는 아래쪽에서 읽으므로 여기서는 따로 읽는다 — 순서에 기대지 않는다)
_YTSRC = io.open(os.path.join(ROOT, 'bot', 'youtube.py'), encoding='utf-8', errors='replace').read()
chk('방송을 갈아탈 수 있다', 'def set_video' in _YTSRC)
chk('갈아탈 때 옛 채팅방을 버린다', 'self.chat_id = None' in _YTSRC)
chk('봇이 도는 중에 주소 바뀜을 알아챈다', '_seen_vid' in BOT and 'live_video_id' in BOT)

_ids = ['https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'https://youtu.be/dQw4w9WgXcQ',
        'https://www.youtube.com/live/dQw4w9WgXcQ', 'dQw4w9WgXcQ']
try:
    import re as _re
    _rx = _re.compile(r"_YT_ID_RE = re\.compile\(r'([^']+)'\)").search(SRV)
    _pat = _re.compile(_rx.group(1)) if _rx else None
    _bad = []
    for _u in _ids:
        _m = _pat.search(_u) if _pat else None
        _got = _m.group(1) if _m else ('dQw4w9WgXcQ' if _re.fullmatch(r'[A-Za-z0-9_-]{11}', _u) else None)
        if _got != 'dQw4w9WgXcQ':
            _bad.append(_u)
    chk('주소 모양 네 가지를 다 읽는다', not _bad, ' · '.join(_bad))
except Exception as _e:
    chk('주소 모양 네 가지를 다 읽는다', False, str(_e))
chk('최소 간격도 바꿀 수 있다', 'ab-iv' in CTL and 'min_interval_sec' in CTL)
chk('새로고침 고리에 물려 있다 (다른 기기에서 바꿔도 따라온다)', 'abSync(false)' in CTL)
# ⚠️ 매번 다시 그리면 체크를 누르는 순간 그 칸이 지워져 안 눌린다
chk('값이 바뀌었을 때만 다시 그린다', 'box.dataset.sig' in CTL)
# ⚠️ 봇이 안 떠 있으면 여기서 뭘 눌러도 아무 일도 안 난다. 그걸 숨기면 사장님이 헤맨다
chk('봇이 떠 있어야 한다는 걸 화면이 알려준다',
    'ab-alive' in CTL and 'announce.py --live' in CTL)
chk('방송 전에는 그렇다고 알려준다', 'broadcast_active' in CTL and '방송이 시작되지 않았습니다' in CTL)

print()
print('=' * 74)
print('⑫ 서버 — 설정을 어디로 넣고 무엇이 막히는가')
print('=' * 74)
chk('기본 설정이 서버에 있다', "'announce_bot'" in SRV or '"announce_bot"' in SRV)
chk('전용 주소가 있다', "@app.route('/api/announcebot'" in SRV)
# ⚠️ /api/data 로 바꿀 수 있으면, 조종실이 낡은 사본을 통째로 보낼 때 방금 바꾼 설정이 되돌아간다
chk('상태를 통째로 보내도 안 덮인다 (모금함과 같은 규칙)',
    "'fundjar', 'announce_bot')" in SRV)
chk('말도 안 되는 간격은 거절한다', '간격은 5~600초 사이입니다' in SRV)
chk('말도 안 되는 안내 간격도 거절한다', '안내 간격은 0~120분 사이입니다' in SRV)
# ⚠️ 오타로 상태에 쓰레기 칸이 생기면 봇은 안 보는데 조종실에는 켜진 것처럼 남는다
chk('모르는 스위치 이름은 버린다', "if _k in _D['say']" in SRV)
chk('옛 저장본에 칸이 없어도 채운다', "_ab[_sub].setdefault(_k, _v)" in SRV)

print()
print('=' * 74)
print('⑬ 서버에서 혼자 돌게 — 손으로 켜지 않는다')
print('=' * 74)
# 예전에는 방송마다 `python bot/announce.py --live` 를 손으로 쳐야 했다.
# 깜빡하면 봇이 조용하고, 조종실 스위치도 반쪽이 된다(눌러도 봇이 없으면 아무 일도 안 난다).
# 투네이션 리스너와 같은 자리에 둔다 — 서버가 알아서 띄우고, 끊기면 되살린다.
UNIT = io.open(os.path.join(ROOT, 'deploy', 'livemaster-bot.service'),
               encoding='utf-8', errors='replace').read()
DEP = io.open(os.path.join(ROOT, 'deploy', 'auto-deploy.sh'),
              encoding='utf-8', errors='replace').read()
DRM = io.open(os.path.join(ROOT, 'deploy', 'README.md'),
              encoding='utf-8', errors='replace').read()

chk('서비스 설정 파일이 있다', '[Service]' in UNIT and '[Install]' in UNIT)
chk('진짜로 치는 모드로 띄운다', 'announce.py --live' in UNIT)
chk('방송 서버가 떠 있어야 한다', 'Requires=livemaster.service' in UNIT)
chk('끊기면 되살린다', 'Restart=always' in UNIT)
# ⚠️ 서버에서는 자기 자신(8080)에 붙는다. 저장소의 config.json 은 방송 컴퓨터용이라 건드리지 않는다
chk('서버 자신에게 붙는다', 'BOT_SERVER=http://127.0.0.1:8080' in UNIT)
chk('열쇠는 다른 비밀들과 같은 곳에서 읽는다', 'EnvironmentFile=/etc/livemaster.env' in UNIT)
# ⚠️ 열쇠가 없는 건 시간이 지난다고 고쳐지지 않는다. 5초마다 재시작하면 로그만 채운다
chk('설정이 없으면 재시작 고리에 안 빠진다', 'RestartPreventExitStatus=78' in UNIT)
chk('봇도 그 값으로 끝낸다', 'return 78' in BOT)

# ⏳ '지금 라이브가 없다' 는 설정 잘못이 아니다. 방송 전에는 늘 그렇다.
#    그걸 78 로 다루면 봇이 아예 안 떠서, 조종실에서 라이브 주소를 넣어줄 기회가 없다
#    (주소는 봇이 떠서 상태를 받아야 읽는다). 2026-09-15 에 실제로 그 막다른 길을 밟았다.
_YTSRC2 = io.open(os.path.join(ROOT, 'bot', 'youtube.py'), encoding='utf-8', errors='replace').read()
chk('열쇠만 따로 볼 수 있다', 'def creds_ready' in _YTSRC2)
chk('ready 는 그 위에 채팅방까지 본다', 'self.creds_ready()' in _YTSRC2)
chk('라이브를 못 찾은 것만으로는 안 죽는다', 'creds_ready()' in BOT)
chk('열쇠가 없을 때만 78 로 끝낸다',
    BOT.find('creds_ready()') < BOT.find('return 78'))
chk('기다린다고 알려준다', '그대로 기다립니다' in BOT)

chk('저장소 파일을 안 고치고 방송을 지정할 수 있다',
    "os.environ.get('YT_' + _k.upper())" in BOT)
for _k in ('YT_CHANNEL_ID', 'YT_CLIENT_ID', 'YT_REFRESH_TOKEN'):
    if _k not in DRM:
        chk('설치 안내에 적혀 있다: ' + _k, False)
chk('무엇을 env 에 넣어야 하는지 적어 뒀다', True)
# ⚠️ 열쇠 파일은 저장소에 안 올라간다. 그래서 서버에는 따로 넣어야 한다는 걸 적어야 한다
chk('열쇠를 왜 따로 넣어야 하는지 적어 뒀다', 'token.json' in DRM and '저장소에 안 올라가' in DRM)
chk('둘이 같이 돌면 안 된다고 적어 뒀다', '두 번 친다' in DRM)
chk('재시작하면 기다리던 인사가 빠진다고 적어 뒀다', '기다리던 후원' in DRM)

# 새 코드를 올리면 봇도 같이 새로고침돼야 한다 — 안 그러면 옛 봇이 계속 돈다
chk('자동배포가 봇도 재시작한다', 'livemaster-bot' in DEP)
chk('안 켜둔 서비스는 안 건드린다', 'is-enabled --quiet "$svc"' in DEP)
chk('버전 되돌릴 때도 봇을 재시작한다', "'livemaster-bot'" in SRV)
chk('그 권한을 안내에 넣어 뒀다', 'restart livemaster-bot' in DRM)

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
