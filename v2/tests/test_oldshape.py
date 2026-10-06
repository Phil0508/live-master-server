# -*- coding: utf-8 -*-
"""v2 조각 → 옛 상태 모양(v2/tools/oldshape.py) · 진행봇 v2 연결부(v2/tools/bot_v2.py).

⚠️ 옛 봇의 판단 코드(bot/announce.py 의 detect · notice_*)를 **진짜로** 불러 v2 서버가 만든 조각을 먹여 본다
   — 흉내 낸 판단으로 검사하면 진짜 어긋남을 가린다.
"""
import contextlib
import io
import json
import os
import sys
import unittest
from unittest import mock

from v2.server.domain import announce as an          # noqa: F401  (조각 · 명령 등록 — __init__ 에 붙이기 전에도)
from v2.tests.test_flow import Base
from v2.tools.oldshape import to_old

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'bot'))
import announce as A      # noqa: E402  옛 봇 — 불러올 때 IPv4 고정을 건다
import net                # noqa: E402
net.undo()                # 검사 프로세스의 다른 검사에는 안 남긴다
from v2.tools import bot_v2   # noqa: E402
net.undo()


def SL(**kw):
    """v2 조각 한 벌(검사용)."""
    s = {'session': {'live': True}, 'players': {'list': [], 'extra': [], 'extra_active': False, 'bottom': {'name': '운영비', 'score': 0}},
         'goal': {'target': 0, 'offset': 0}, 'popup': {'donation': None, 'score': None, 'takeover': None},
         'queue': {'items': [], 'paused': False, 'volume': 0.5}, 'show': {'stage': None},
         'dicegame': {'action': {}}, 'account': {'bank': '', 'acc_num': '', 'name': ''},
         'fundjar': {'name': '모금함', 'enabled': False, 'seed': 200000, 'score': 0},
         'tallies': {'donors': {}}, 'announce_bot': dict(an.DEFAULT)}
    s.update(kw)
    return s


class Pure(unittest.TestCase):
    def test_mapping(self):
        o = to_old(SL(players={'list': [{'name': '하율', 'score': 3, 'contribution': 5}], 'extra': [{'name': '번외', 'score': 1, 'contribution': 1}],
                               'extra_active': True, 'bottom': {'name': '운영비', 'score': 7}},
                      goal={'target': 50, 'offset': -2},
                      popup={'donation': {'id': 'don_1', 'name': '별빛', 'amount': 50000, 'message': '응원', 'at': 1700000000123}},
                      queue={'items': [{'id': 'rq_1', 'donator': '별빛', 'amount': 50000}], 'paused': True},
                      show={'stage': 'dicegame'}, dicegame={'action': {'type': 'ROLL', 'ts': 5}},
                      account={'bank': '기업', 'acc_num': '464-1', 'name': '엔젤'},
                      tallies={'donors': {'별빛': {'name': '별빛 ', 'total': 50000, 'count': 1}}}))
        self.assertTrue(o['broadcast_active'])
        self.assertEqual(o['bjs'], [{'name': '하율', 'score': 3, 'contribution': 5}])
        self.assertEqual(o['extra_bjs'][0]['name'], '번외')
        self.assertEqual(o['bottom_fixed'], {'name': '운영비', 'score': 7})
        self.assertEqual((o['target_goal'], o['goal_offset']), (50, -2))
        ld = o['latest_donation']
        self.assertEqual((ld['name'], ld['amount'], ld['message'], ld['id']), ('별빛', 50000, '응원', 'don_1'))
        self.assertAlmostEqual(ld['time'], 1700000000.123)        # ms → 초
        self.assertEqual(o['reaction_queue'][0]['id'], 'rq_1')
        self.assertTrue(o['reaction_paused'])
        self.assertTrue(o['dicegame']['enabled'])                # v2 엔 스위치가 없다 — 무대가 주사위면 켜짐
        self.assertEqual(o['dicegame']['action']['ts'], 5)
        self.assertEqual(o['account']['acc_num'], '464-1')
        self.assertEqual(o['donor_tally'], {'별빛 ': {'total': 50000, 'count': 1}})
        self.assertEqual(o['announce_bot'], an.DEFAULT)
        self.assertEqual(A.goal_total(o), 7 + 3 - 2)              # 옛 셈 = v2 게이지 셈(운영비 + 본판 점수 + offset)

    def test_empty_and_missing(self):
        o = to_old({})
        self.assertFalse(o['broadcast_active'])
        self.assertEqual(o['latest_donation'], {'name': '', 'amount': 0, 'message': '', 'time': 0})
        self.assertEqual((o['bjs'], o['reaction_queue'], o['target_goal']), ([], [], 0))
        self.assertFalse(o['dicegame']['enabled'])
        self.assertIs(o['announce_bot']['enabled'], False)        # 조종실이 끌 수 없는 봇은 입을 다문다
        self.assertEqual(to_old(None)['bjs'], [])
        o = to_old(SL(popup={'donation': {'id': 'x', 'name': 'a', 'amount': 3000, 'at': 1000, 'display_only': True}}))
        self.assertTrue(o['latest_donation']['display_only'])

    def test_fresh_objects(self):
        sl = SL(players={'list': [{'name': '하율', 'score': 1, 'contribution': 1}], 'bottom': {'score': 0}})
        o = to_old(sl)
        o['bjs'][0]['contribution'] = 99
        o['announce_bot']['say']['donation'] = False
        self.assertEqual(sl['players']['list'][0]['contribution'], 1)
        self.assertTrue(sl['announce_bot']['say']['donation'])

    def test_notices_read_same_values(self):
        o = to_old(SL(account={'bank': '기업은행', 'acc_num': '464-0', 'name': '엔젤컴퍼니'},
                      fundjar={'enabled': True, 'seed': 200000, 'score': 30000},
                      players={'list': [{'name': '가', 'score': 0, 'contribution': 30}, {'name': '나', 'score': 0, 'contribution': 10},
                                        {'name': '다', 'score': 0, 'contribution': 5}], 'bottom': {'score': 0}}))
        self.assertEqual(A.notice_account(o), ('notice.account', {'bank': '기업은행', 'acc_num': '464-0', 'holder': '엔젤컴퍼니'}))
        self.assertEqual(A.notice_fundjar(o)[1]['total'], '230,000')
        self.assertEqual(A.notice_rank(o)[0], 'notice.rank3')


class WithOldDetect(Base):
    """v2 서버가 실제로 만든 조각 → to_old → 옛 detect. 옛 봇과 같은 순간에 같은 말을 고르나."""

    def old(self):
        return to_old(self.st())

    def test_donation_waits_for_reaction_and_rank(self):
        waiting = {}
        prev = self.old()
        self.don('별빛', 50000, 'toon_o1')                         # 빈 대기줄 → 바로 재생 → 바로 인사
        cur = self.old()
        ev = A.detect(prev, cur, waiting=waiting)
        self.assertEqual([(e.key, e.fields) for e in ev], [('donation', {'name': '별빛', 'amount': '50,000'})])
        prev = cur
        self.don('달빛', 20005, 'toon_o2')                         # 앞에 재생 중 → 리액션이 나올 때까지 기다린다
        cur = self.old()
        self.assertEqual(A.detect(prev, cur, waiting=waiting), [])
        self.assertEqual(len(waiting), 1)
        prev = cur
        head = self.st()['queue']['items'][0]['id']
        self.c.post('/api/cmd', json={'type': 'reaction.done', 'data': {'id': head}})   # 방송판이 다 틀었다(로그인 없음)
        cur = self.old()
        ev = A.detect(prev, cur, waiting=waiting)
        self.assertEqual([(e.key, e.fields['name']) for e in ev], [('donation', '달빛')])
        self.assertEqual(waiting, {})
        prev = cur
        self.cmd('score.add', name='서아', delta=3)
        cur = self.old()
        ev = A.detect(prev, cur, waiting=waiting)
        self.assertEqual([(e.key, e.fields) for e in ev], [('rank_top_only', {'name': '서아'})])
        prev = cur
        self.cmd('score.add', name='채원', delta=5)
        ev = A.detect(prev, self.old(), waiting=waiting)
        self.assertEqual([(e.key, e.fields) for e in ev], [('rank_top', {'name': '채원', 'second': '서아', 'gap': '2'})])

    def test_small_display_only_greets_now(self):
        prev = self.old()
        self.don('소액', 3000, 'toon_o3', display_only=True)
        ev = A.detect(prev, self.old(), waiting={})
        self.assertEqual([(e.key, e.fields['amount']) for e in ev], [('donation', '3,000')])

    def test_goal_marks(self):
        self.cmd('goal.set', target=10)
        prev = self.old()
        self.cmd('score.add', name='하율', delta=5)
        ev = [e for e in A.detect(prev, self.old()) if e.key.startswith('goal')]
        self.assertEqual([(e.key, e.fields['percent']) for e in ev], [('goal', 25)])   # 여러 금을 한 번에 넘어도 한 줄(옛 것과 같다)
        prev = self.old()
        self.cmd('score.add', name='서아', delta=5)
        ev = [e for e in A.detect(prev, self.old()) if e.key.startswith('goal')]
        self.assertEqual([e.key for e in ev], ['goal_done'])

    def test_switches_reach_old_says(self):
        self.cmd('bot.set', say={'rank_top': False})
        o = self.old()
        self.assertFalse(A.says(o, 'rank_top'))
        self.assertTrue(A.says(o, 'donation'))
        self.assertFalse(A.says(o, 'dice_roll'))                  # 주사위는 기본 꺼짐
        self.cmd('bot.notice', key='rank_min', min=2)
        bot = A.Bot({'notices': {}}, A.Templates(os.path.join(REPO, 'bot', 'messages.json')))
        bot.state = self.old()
        self.assertEqual(bot._ncfg('rank_every_sec', 480), 120.0)  # 조종실 분 → 봇 초


class FakeWS:
    def __init__(self, msgs):
        self.msgs, self.sent = list(msgs), []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def recv(self, timeout=None):
        if not self.msgs:
            raise ConnectionError('끝')
        return json.dumps(self.msgs.pop(0), ensure_ascii=False)

    def send(self, s):
        self.sent.append(json.loads(s))


class Adapter(unittest.TestCase):
    """WebSocket 쪽지 처리 — 통째 → 이어 붙이기 → 번호가 비면 통째 다시."""

    def run_bot(self, msgs, env=None):
        ws = FakeWS(msgs)
        fed = []
        with mock.patch.dict(os.environ, env if env is not None else {'BOT_V2_TOKEN': 'tok'}, clear=True), \
                mock.patch('websockets.sync.client.connect', lambda *a, **k: ws), \
                contextlib.redirect_stdout(io.StringIO()):
            bot = bot_v2.V2Bot({'server': 'http://x', 'notices': {}}, A.Templates(os.path.join(REPO, 'bot', 'messages.json')))
            orig = bot._on_state
            bot._on_state = lambda st: (fed.append(st), orig(st))
            try:
                bot._listen()
            except ConnectionError:
                pass
        return bot, ws, fed

    def test_patches_gap_and_resync(self):
        don = lambda i, n: {'popup': {'donation': {'id': 'd%d' % i, 'name': n, 'amount': 10000, 'at': 1000 * i}}}
        msgs = [{'t': 'snapshot', 'seq': 5, 'authed': True, 'slices': SL()},
                {'t': 'patch', 'seq': 6, 'slices': don(1, '하나')},
                {'t': 'patch', 'seq': 7, 'slices': {}},              # 번호만(바뀐 조각 없음)
                {'t': 'ping'},
                {'t': 'patch', 'seq': 9, 'slices': don(2, '빠짐')},   # 8 이 빠졌다 → 통째 다시
                {'t': 'patch', 'seq': 10, 'slices': don(3, '무시')},  # 통째를 기다리는 동안은 버린다
                {'t': 'snapshot', 'seq': 10, 'authed': True, 'slices': SL(**don(3, '셋'))},
                {'t': 'patch', 'seq': 10, 'slices': don(9, '옛것')},  # 이미 본 번호
                {'t': 'patch', 'seq': 11, 'slices': don(4, '넷')},
                {'t': 'result', 'id': 'hello', 'ok': False, 'error': '모르는 명령'}]
        bot, ws, fed = self.run_bot(msgs)
        self.assertEqual([s['latest_donation']['name'] for s in fed], ['', '하나', '셋', '넷'])
        self.assertEqual(ws.sent[0]['type'], 'bot.hello')           # 붙자마자 한 번
        self.assertEqual(ws.sent[0]['data']['mode'], 'dry')
        self.assertEqual([m for m in ws.sent if m.get('t') == 'resync'], [{'t': 'resync'}])
        self.assertEqual(bot.seq, 11)
        self.assertEqual([e.fields['name'] for e in bot.q], ['하나', '셋', '넷'])   # 첫 통째는 기준만, 그 뒤만 알린다

    def test_not_authed_stops(self):
        bot, ws, fed = self.run_bot([{'t': 'snapshot', 'seq': 1, 'authed': False, 'slices': {}}])
        self.assertTrue(bot.stop)
        self.assertEqual(bot.exit_code, 78)
        self.assertEqual(fed, [])
        bot, ws, fed = self.run_bot([], env={})                      # 로그인할 값이 없다
        self.assertEqual(bot.exit_code, 78)

    def test_dry_path_is_v2(self):
        bot, _, _ = self.run_bot([])
        self.assertTrue(bot.dry_path.endswith(os.path.join('v2', 'data', 'bot_dryrun.log')))
        self.assertEqual(bot_v2.ws_url('https://a.b:8443/'), 'wss://a.b:8443/ws?kind=bot')
        self.assertEqual(bot_v2.ws_url('http://127.0.0.1:5300'), 'ws://127.0.0.1:5300/ws?kind=bot')


if __name__ == '__main__':
    unittest.main()
