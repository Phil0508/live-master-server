# -*- coding: utf-8 -*-
"""🎲 주사위게임 — 옛 tests/dice_test.py · dice_fix_test.py · dice_preset_test.py · dice_timing_test.py 가 지키던 규칙.

돌리기(저장소 루트에서): python -m unittest v2.tests.test_dicegame
"""
import ast
import io
import os
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from v2.server.domain import dicegame as dg      # ⚠️ create_app 보다 먼저 — 조각 · 명령이 등록돼야 한다
from v2.server.domain import players as pl
from v2.server.app import create_app
from v2.server.bus import command
from v2.server.domain.signatures import Signatures

PW, SECRET = 'testpw', 'testsecret-0123456789'
H = {'Authorization': 'Bearer ' + SECRET}
SIG_BIG = {'id': 10003, 'amount': 100000, 'title': '대박 시그', 'image_url': 'big.png', 'sound_url': 'big.mp3', 'duration': 9}
SIG_CHEAP = {'id': 10040, 'amount': 10000, 'title': '싼 시그', 'image_url': 'c.png', 'sound_url': 'c.mp3', 'duration': 5}
SIGS = [SIG_CHEAP, SIG_BIG,
        {'id': 1, 'amount': 30000, 'title': '이꾸욧', 'image_url': '', 'sound_url': 'a.mp3', 'duration': 5},
        {'id': 2, 'amount': 30000, 'title': ' 포카치노 ', 'image_url': '', 'sound_url': 'b.mp3', 'duration': 5},
        {'id': 3, 'amount': 30000, 'title': '멈춘 시간', 'image_url': '', 'sound_url': 'c.mp3', 'duration': 5}]
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 검사용 명령 — 연출 시간이 지난 것처럼 · 공용 고리가 걸린 것처럼 ──
@command('t.dice_age')
def _t_age(ctx, data):
    """앞 굴림을 1분 전 것으로 — 연타 막기를 기다리지 않고 다음 굴림을 본다."""
    a = ctx.edit('dicegame')['action']
    if a.get('ts'):
        a['ts'] -= 60000


@command('t.roster')
def _t_roster(ctx, data):
    """players 에 ON_ROSTER 고리가 걸렸을 때와 같다 — 명단이 바뀐 그 자리에서 말을 맞춘다."""
    dg.on_roster(ctx)


@command('t.rename')
def _t_rename(ctx, data):
    """players.rename + ON_RENAME 고리 — 고리를 걸면 이렇게 돈다."""
    pl.players_rename(ctx, data)
    dg.on_rename(ctx, data['from'], data['to'])


class Base(unittest.TestCase):
    NAMES = ['가', '나', '다', '라']

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2dice_')
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET,
                                       sig_fetch=lambda: SIGS))
        self.cmd('session.start', names=self.NAMES)

    def tearDown(self):
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def cmd(self, t, auth=True, **data):
        r = self.c.post('/api/cmd', json={'type': t, 'data': data}, headers=H if auth else {})
        return r.status_code, r.json()

    def ok(self, t, **data):
        c, r = self.cmd(t, **data)
        self.assertEqual(c, 200, (t, r))
        return r

    def st(self, auth=True):
        return self.c.get('/api/state', headers=H if auth else {}).json()['slices']

    def g(self):
        return self.st()['dicegame']

    def pv(self):
        return self.st()['dicegame_private']

    def bd(self):
        return {r['name']: r['pts'] for r in self.g()['board']}

    def pieces(self):
        return {p['name']: p for p in self.g()['pieces']}

    def player(self, name):
        return next(p for p in self.st()['players']['list'] if p['name'] == name)

    def board(self, tile_type='blank', cols=8, rows=5, **tile):
        """판을 깔고(한 판 값 0) 1번부터 끝까지 같은 칸으로."""
        r = self.ok('dice.setup', cols=cols, rows=rows, dice=1, roll_price=0)
        for i in range(1, r['tiles']):
            self.ok('dice.tile', **dict({'id': i, 'type': tile_type}, **tile))
        return r['tiles']

    def roll(self, **data):
        """연타 막기를 지나게 앞 굴림을 묵힌 뒤 굴린다."""
        self.ok('t.dice_age')
        return self.ok('dice.roll', **data)


class Setup(Base):
    def test_setup_ring_and_clamp(self):
        r = self.ok('dice.setup', cols=7, rows=5, dice=2)
        self.assertEqual(r['tiles'], 20)                                   # 7×5 → 테두리 20칸
        g = self.g()
        self.assertEqual(g['tiles'][0]['type'], 'start')
        self.assertEqual(self.st()['show']['stage'], 'dicegame')          # 깔면 무대에 오른다
        self.assertEqual([p['pos'] for p in g['pieces']], [0, 0, 0, 0])
        self.ok('dice.setup', cols=999, rows=-3, dice=9)
        g = self.g()
        self.assertEqual((g['cols'], g['rows'], g['dice']), (10, 3, 2))
        self.assertEqual(self.cmd('dice.setup', cols='일곱')[0], 400)      # 숫자가 아니면 잘라내지 않고 거절
        self.ok('dice.setup', cols=8, rows=5)
        self.assertEqual(self.g()['dice'], 1)                              # 개수를 안 보내면 한 개

    def test_setup_keeps_tiles_and_prices(self):
        self.ok('dice.setup', cols=7, rows=5, roll_price=30000, lap_contrib=7)
        self.ok('dice.tile', id=3, type='mission', label='팔굽혀펴기')
        self.ok('dice.tile', id=6, type='sig', sig_id=10003, sig=SIG_BIG)
        self.ok('dice.setup', cols=6, rows=4)                              # 16칸으로 줄여도
        g = self.g()
        self.assertEqual((g['tiles'][3]['label'], g['tiles'][6]['type']), ('팔굽혀펴기', 'sig'))
        self.assertEqual((g['roll_price'], g['lap_contrib']), (30000, 7))  # 단가는 쓰던 값 그대로

    def test_tile_edit(self):
        self.ok('dice.setup', cols=7, rows=5)
        self.ok('dice.tile', id=5, type='score', points=99999)
        self.assertEqual(self.g()['tiles'][5]['points'], 1000)            # ±1000 으로 잘린다
        self.ok('dice.tile', id=7, type='move', points=-5)
        self.assertEqual(self.g()['tiles'][7]['points'], -5)              # 싱크홀 숫자도 저장(예전엔 0)
        self.ok('dice.tile', id=6, type='sig', sig_id=10003, sig=SIG_BIG)
        t6 = self.g()['tiles'][6]
        self.assertEqual((t6['sig']['sound_url'], t6['label']), ('big.mp3', '대박 시그'))   # 재생 정보까지 미리
        self.assertEqual(self.cmd('dice.tile', id=0, type='mission', label='x')[0], 400)   # 출발 칸
        self.assertEqual(self.cmd('dice.tile', id=999, type='mission')[0], 400)
        self.assertEqual(self.cmd('dice.tile', id=4, type='함정')[0], 400)
        self.assertEqual(self.cmd('dice.tile', id=4, type='sig')[0], 400)                    # 시그를 안 고름
        self.assertEqual(self.cmd('dice.tile', id=4, type='sig', sig_id=777)[0], 404)        # 못 찾음
        self.assertEqual(self.cmd('dice.keys', keys='목록아님')[0], 400)

    def test_prefetch_outside_command(self):
        class FakeBus:
            sigs = Signatures(fetch=lambda: SIGS)
        d = dg.PREFETCH['dice.tile'](FakeBus, {'id': 3, 'type': 'sig', 'sig_id': 10003})
        self.assertEqual(d['sig']['title'], '대박 시그')
        d = dg.PREFETCH['dice.preset'](FakeBus, {'name': 'basic22'})
        self.assertEqual(len(d['sigs']), len(SIGS))


class Privacy(Base):
    def test_login_and_keys_hidden(self):
        for t in ('dice.setup', 'dice.roll', 'dice.tile', 'dice.keys', 'dice.move', 'dice.reset', 'dice.shield',
                  'dice.board', 'dice.settle', 'dice.preset'):
            self.assertEqual(self.cmd(t, auth=False)[0], 401, t)
        self.ok('dice.setup', cols=7, rows=5)
        self.ok('dice.keys', keys=['비밀1', '비밀2', '  '])
        pub = self.st(auth=False)
        self.assertNotIn('dicegame_private', pub)                          # 덱은 비공개 조각에만
        self.assertNotIn('keys', pub['dicegame'])
        self.assertEqual(pub['dicegame']['keys_count'], 2)                 # 장수만(화면 표시용)
        self.assertEqual(len(pub['dicegame']['tiles']), 20)                # 판 자체는 보인다
        self.assertEqual(self.pv()['keys'], ['비밀1', '비밀2'])
        # 방송판 연결로 가는 쪽지에도 덱이 없다
        with self.c.websocket_connect('/ws?kind=overlay') as ov:
            ov.receive_json()
            self.ok('dice.keys', keys=['비밀3'])
            msg = ov.receive_json()
            self.assertEqual(msg['t'], 'patch')
            self.assertNotIn('dicegame_private', msg['slices'])
            self.assertNotIn('비밀3', str(msg))


class Roll(Base):
    def test_roll_server_is_truth(self):
        self.ok('dice.setup', cols=7, rows=5, dice=2)
        r = self.ok('dice.roll')
        g = self.g()
        act = g['action']
        self.assertEqual(len(r['dice']), 2)
        self.assertTrue(all(1 <= d <= 6 for d in r['dice']))
        self.assertEqual(self.pieces()['가']['pos'], sum(r['dice']) % 20)      # 차례 말(가)이 눈의 합만큼
        self.assertEqual(len(act['path']), sum(r['dice']))
        self.assertEqual((act['type'], act['to'], act['plan']), ('ROLL', r['to'], dg.plan(act)))
        c, r2 = self.cmd('dice.roll')
        self.assertEqual(c, 429)                                                # 연출이 끝나기 전의 연타
        self.assertIn('초 뒤', r2['error'])
        self.assertEqual(self.g()['action']['ts'], act['ts'])                   # 거절은 아무것도 안 바꾼다

    def test_seed_is_deterministic(self):
        self.board('key')
        self.ok('dice.keys', keys=['가위', '바위', '보', '꽝'])
        a = self.roll(piece='가', seed=7)
        self.ok('dice.move', piece='가', pos=0)
        b = self.roll(piece='가', seed=7)
        self.assertEqual((a['dice'], a['key']), (b['dice'], b['key']))
        self.assertIn(a['key'], ('가위', '바위', '보', '꽝'))
        self.assertEqual(self.g()['action']['key'], b['key'])                  # 신호의 카드 = 응답의 카드
        self.ok('t.dice_age')
        self.assertEqual(self.cmd('dice.roll', seed={'x': 1})[0], 400)
        self.assertEqual(self.cmd('dice.roll', seed=[1])[0], 400)

    def test_value_and_dice_count(self):
        self.ok('dice.setup', cols=8, rows=5)
        self.assertEqual(self.cmd('dice.roll', value=7)[0], 400)
        self.assertEqual(self.cmd('dice.roll', value='셋')[0], 400)
        seen = set()
        for s in range(12):
            r = self.roll(seed=s)
            seen.add(len(r['dice']))
            self.assertTrue(1 <= r['dice'][0] <= 6)
        self.assertEqual(seen, {1})                                             # 굴릴 때마다 딱 한 개

    def test_stage_messages(self):
        self.board()
        self.ok('show.stage', stage='siggame')
        c, r = self.cmd('dice.roll', value=3)
        self.assertEqual(c, 400)
        self.assertIn('시그뒤집기', r['error'])
        self.assertIn('무대', r['error'])
        self.ok('show.stage', stage=None)
        c, r = self.cmd('dice.roll', value=3)
        self.assertIn('안 떠 있어요', r['error'])
        self.ok('show.stage', stage='dicegame')
        self.ok('dice.roll', value=3)
        self.ok('dice.reset')
        g = self.g()
        self.assertEqual([p['pos'] for p in g['pieces']], [0, 0, 0, 0])
        self.assertIsNone(self.st()['show']['stage'])                           # 정리하면 무대에서 내려간다
        self.assertEqual(len(g['tiles']), 22)                                   # 칸은 남는다

    def test_no_board(self):
        self.assertIn('판을 깔아', self.cmd('dice.roll')[1]['error'])
        self.assertEqual(self.cmd('dice.move', pos=1)[0], 400)

    def test_lap_passing(self):
        self.ok('dice.setup', cols=7, rows=5, roll_price=0)                    # 20칸, 한 바퀴 10점
        self.ok('dice.move', pos=19)
        r = self.roll(value=1)                                                   # 19 + 1 → 출발
        p = self.pieces()['가']
        self.assertEqual((p['pos'], p['laps'], r['lap']), (0, 1, True))
        self.assertEqual(r['lap_contrib'], {'name': '가', 'points': 10})
        self.ok('dice.move', pos=19)
        r = self.roll(value=3)                                                   # 지나치기만 해도
        p = self.pieces()['가']
        self.assertEqual((p['pos'], p['laps'], r['lap']), (2, 2, True))
        self.ok('dice.move', pos=0)
        r = self.roll(value=5)                                                   # 출발에서 떠나는 것은 아니다
        self.assertEqual((self.pieces()['가']['laps'], r['lap']), (2, False))
        self.assertEqual(self.bd()['가'], 20)
        self.assertEqual((self.player('가')['score'], self.player('가')['contribution']), (0, 0))   # 엑셀판은 그대로

    def test_score_tile_dedicated_board(self):
        self.board('score', cols=4, rows=3, points=2)                          # 10칸 — 어디 떨어져도 점수 칸
        r = self.roll(player='가', value=3)
        self.assertEqual(r['scored'], {'name': '가', 'points': 2})
        self.assertEqual(self.bd()['가'], 2)
        self.assertEqual((self.player('가')['score'], self.player('가')['contribution']), (0, 0))
        log = self.pv()['log'][0]
        self.assertEqual((log['name'], log['val'], log['before'], log['after']), ('가', 2, 0, 2))
        self.assertIn('점수 칸', log['why'])
        self.ok('dice.move', piece='나', pos=0)
        r = self.roll(piece='나', value=2)                                      # 사람 없이 말만 → 말 주인이 받는다
        self.assertEqual((r['piece'], self.bd()['나'], self.bd()['가']), ('나', 2, 2))
        r = self.roll(player='없는사람', value=1)
        self.assertIn('못 찾아', r['note'])
        self.assertEqual(self.st()['pending'], [])                              # 주사위는 대기함에 카드를 안 올린다

    def test_bang_zero_gives_nothing(self):
        self.board('score', label='꽝!', points=0)
        r = self.roll(player='가', value=2)
        self.assertIsNone(r['scored'])
        self.assertEqual(self.bd()['가'], 0)

    def test_sig_tile(self):
        n = self.board('sig', sig_id=10003, sig=SIG_BIG)
        self.ok('dice.setup', cols=8, rows=5, roll_price=20000)                # 같은 칸 그대로 · 한 판 2만 원
        self.assertEqual(n, 22)
        r = self.roll(piece='가', value=2)
        q = self.st()['queue']['items']
        self.assertEqual(len(q), 1)
        it = q[0]
        self.assertEqual((it['donator'], it['amount'], it['skip_popup'], it['source'], it['banner']),
                         ('가', 0, True, 'dice', '가 · 시그 칸 도착'))           # 후원이 아니다 — 누가 밟았는지만
        act = self.g()['action']
        exp = 380 + 2 * 300 + 120 + 1500                                         # 말이 닿고 + 카드 1.5초
        self.assertEqual(act['plan']['gate'], exp)
        self.assertEqual(it['play_after'], act['ts'] + exp)
        self.assertEqual(self.st()['tallies']['sigs'], {})                     # 시그 순위 집계에 안 센다
        self.assertEqual(r['contrib']['points'], 8)                             # 10만 − 2만 = 8점
        self.assertEqual(self.bd()['가'], 8)
        self.assertEqual(act['tile']['image'], 'big.png')
        # 한 판 값보다 싼 시그는 기여도 0(빼앗지는 않는다)
        self.ok('dice.tile', id=4, type='sig', sig_id=10040, sig=SIG_CHEAP)
        r = self.roll(piece='가', value=2)
        self.assertIsNone(r['contrib'])
        self.assertEqual(self.bd()['가'], 8)


class Tiles(Base):
    def setUp(self):
        super().setUp()
        self.board()
        self.ok('dice.tile', id=5, type='steal', label='각 플레이어에게서 5점씩', points=5)
        self.ok('dice.tile', id=21, type='goto', label='블랙홀 · 출발점으로', points=0)
        self.ok('dice.tile', id=3, type='score', points=10)

    def test_steal_and_blackhole(self):
        self.assertEqual(self.bd(), {'가': 0, '나': 0, '다': 0, '라': 0})
        self.roll(piece='가', value=3)
        self.assertEqual(self.bd()['가'], 10)
        r = self.roll(piece='나', value=5)
        self.assertEqual((r['steal']['taker'], r['steal']['per'], len(r['steal']['from'])), ('나', 5, 3))
        self.assertEqual(self.bd(), {'가': 5, '나': 15, '다': -5, '라': -5})     # 마이너스 됨
        self.assertEqual(sum(self.bd().values()), 10)                           # 총점은 그대로
        self.ok('dice.move', piece='다', pos=18)
        r = self.roll(piece='다', value=3)                                      # 18 + 3 = 21 블랙홀
        af = self.g()['action']['after']
        self.assertEqual((af['kind'], af['from'], af['to'], af['rev']), ('goto', 21, 0, True))
        self.assertEqual(af['path'], [(21 - i) % 22 for i in range(1, 22)])     # 거꾸로 걸어서
        self.assertIsNone(r['lap_contrib'])                                     # 끌려가 출발에 닿은 건 한 바퀴가 아니다
        self.assertEqual(self.pieces()['다']['laps'], 0)
        plan = self.g()['action']['plan']
        self.assertEqual(plan['afStep'], max(90, round(2400 / 21)))             # 길면 빠르게 밟는다

    def test_sinkhole_lands_on_score(self):
        self.ok('dice.tile', id=7, type='move', label='싱크홀', points=-5)
        self.ok('dice.tile', id=2, type='score', label='기여도 4', points=4)
        self.ok('dice.move', piece='가', pos=4)
        r = self.roll(piece='가', value=3)                                      # 7 → 뒤로 5 → 2
        af = self.g()['action']['after']
        self.assertEqual((af['to'], af['path'], af['rev']), (2, [6, 5, 4, 3, 2], True))
        self.assertEqual(af['scored'], {'name': '가', 'points': 4})             # 끌려간 자리도 제 일을 한다
        self.assertEqual((self.pieces()['가']['pos'], r['to']), (2, 2))

    def test_giveall(self):
        self.ok('dice.tile', id=9, type='giveall', label='전원', points=3)
        self.ok('dice.move', piece='라', pos=4)
        r = self.roll(piece='라', value=5)
        self.assertEqual(r['giveall'], {'points': 3, 'names': ['가', '나', '다', '라']})
        self.assertEqual(set(self.bd().values()), {3})


class Keys(Base):
    def setUp(self):
        super().setUp()
        self.board()
        self.ok('dice.tile', id=5, type='key')

    def key(self, text, who='가', start=0, value=5):
        self.ok('dice.keys', keys=[text])
        self.ok('dice.move', piece=who, pos=start)
        return self.roll(piece=who, value=value)

    def test_effect_parse(self):
        e = dg.key_effect
        self.assertEqual(e('기여도 1등과 바꾸기'), {'kind': 'swap', 'n': 1})       # '기여도 N' 보다 먼저
        self.assertEqual(e('뒤로 7칸'), {'kind': 'back', 'n': 7})
        self.assertEqual(e('출발지로 (뒤)')['kind'], 'start')
        self.assertEqual(e('기여도 -20'), {'kind': 'contrib', 'n': -20})
        self.assertEqual(e('실드권')['kind'], 'shield')
        self.assertEqual(e('쉴드권')['kind'], 'shield')
        self.assertIsNone(e('노래 한 곡'))

    def test_start_walks_back(self):
        self.key('출발지로 (뒤)')
        af = self.g()['action']['after']
        self.assertEqual((af['to'], af['path'], af['rev']), (0, [4, 3, 2, 1, 0], True))
        self.assertEqual((self.pieces()['가']['pos'], self.pieces()['가']['laps']), (0, 0))

    def test_back_lands_on_score(self):
        self.ok('dice.tile', id=1, type='score', points=10)
        r = self.key('뒤로 4칸')
        af = self.g()['action']['after']
        self.assertEqual((af['to'], af['path'], af['scored']), (1, [4, 3, 2, 1], {'name': '가', 'points': 10}))
        self.assertEqual(r['to'], 1)
        self.assertEqual(self.g()['action']['plan']['afStart'], 3200)          # 열쇠 칸은 뽑기 뒤에 걷는다

    def test_swap_bankrupt_contrib(self):
        self.ok('dice.board', do='set', name='나', pts=30)
        r = self.key('기여도 1등과 바꾸기')
        self.assertEqual(self.bd()['가'], 30)
        self.assertEqual(self.bd()['나'], 0)
        self.assertEqual(r['key_effect'], '가 0 ↔ 나 30')
        self.key('파산')
        self.assertEqual(self.bd()['가'], 0)
        self.key('기여도 50')
        self.assertEqual(self.bd()['가'], 50)
        self.assertEqual(self.player('가')['contribution'], 0)                 # 엑셀판은 안 건드린다

    def test_shield_is_manual(self):
        self.key('실드권')
        self.assertTrue(self.pieces()['가']['shield'])
        self.ok('dice.tile', id=8, type='score', points=-10)
        self.ok('dice.move', piece='가', pos=5)
        self.roll(piece='가', value=3)                                          # 마이너스 칸 — 쉴드가 저절로 막지 않는다
        self.assertEqual(self.bd()['가'], -10)
        self.assertTrue(self.pieces()['가']['shield'])
        r = self.ok('dice.shield', piece='가', on=False)                        # 진행자가 [사용함]
        self.assertEqual((r['piece'], r['shield']), ('가', False))
        self.assertFalse(self.pieces()['가']['shield'])
        self.assertEqual(self.cmd('dice.shield', piece='없음', on=True)[0], 400)
        self.assertEqual(self.cmd('dice.shield', on=True)[0], 400)

    def test_choose_then_move(self):
        self.ok('dice.tile', id=10, type='score', points=10)
        self.key('원하는 곳으로')
        self.assertTrue(self.pieces()['가']['choose'])
        c, _ = self.cmd('dice.roll', piece='가', value=1)
        self.assertEqual(c, 429)
        self.assertTrue(self.pieces()['가']['choose'])                         # 거절된 굴림은 선택권을 안 지운다
        r = self.ok('dice.move', piece='가', pos=10)
        self.assertEqual((r['scored'], r['choose']), ({'name': '가', 'points': 10}, True))
        act = self.g()['action']
        self.assertEqual((act['type'], act['tile']['type']), ('MOVE', 'score'))
        r = self.ok('dice.move', piece='가', pos=11)                            # 두 번째는 효과 없음
        self.assertNotIn('scored', r)
        self.assertNotIn('tile', self.g()['action'])
        self.assertEqual(self.bd()['가'], 10)

    def test_again_nothing_unknown_empty(self):
        self.assertTrue(self.key('한 번 더')['again'])
        self.assertEqual(self.key('꽝')['key_effect'], '꽝')
        r = self.key('노래 한 곡')
        self.assertEqual(r['key'], '노래 한 곡')
        self.assertIsNone(r['key_effect'])
        self.ok('dice.keys', keys=[])
        self.ok('dice.move', piece='가', pos=0)
        self.assertIn('비어 있습니다', self.roll(piece='가', value=5)['key'])

    def test_dragged_key_does_not_move_again(self):
        self.ok('dice.tile', id=9, type='move', points=-4)                      # 9 → 5(열쇠 칸)
        self.ok('dice.keys', keys=['뒤로 3칸'])
        self.ok('dice.move', piece='가', pos=6)
        self.roll(piece='가', value=3)
        af = self.g()['action']['after']
        self.assertEqual((af['to'], af['key'], af['key_kind']), (5, '뒤로 3칸', 'back'))
        self.assertIn('다시 옮기지 않는다', af['key_effect'])
        self.assertEqual(self.pieces()['가']['pos'], 5)


class Turn(Base):
    def test_turn_stays_and_follows_pick(self):
        self.board('score', cols=7, rows=5, points=10)
        self.assertEqual(list(self.pieces()), ['가', '나', '다', '라'])
        r = self.roll(piece='라', value=3)
        self.assertEqual(r['piece'], '라')
        self.assertEqual(list(self.pieces()), ['가', '나', '다', '라'])         # 1등으로 뛰어도 말 순서는 그대로
        r = self.roll(value=2)
        self.assertEqual(r['piece'], '라')                                      # 굴려도 차례는 안 넘어간다
        self.assertEqual(self.bd()['라'], 20)
        self.roll(piece='가', value=1)
        g = self.g()
        self.assertEqual(g['pieces'][g['turn']]['name'], '가')
        r = self.ok('dice.move', pos=9)                                         # 안 고르면 차례 말
        self.assertEqual(r['piece'], '가')
        self.assertEqual(self.pieces()['가']['pos'], 9)
        self.assertEqual(self.cmd('dice.move', pos=999)[0], 400)
        self.assertEqual(self.cmd('dice.move', piece='없음', pos=1)[0], 400)


class Roster(Base):
    def test_add_remove_keeps_positions_and_turn(self):
        self.board('score', cols=7, rows=5, points=10)
        self.ok('dice.move', piece='가', pos=5)
        self.ok('dice.move', piece='나', pos=7)
        self.roll(piece='라', value=2)
        for n in ('마', '바'):
            self.ok('players.add', name=n)
        self.ok('t.roster')
        g = self.g()
        self.assertEqual([p['name'] for p in g['pieces']], ['가', '나', '다', '라', '마', '바'])
        self.assertEqual((self.pieces()['가']['pos'], self.pieces()['나']['pos']), (5, 7))
        self.assertEqual(g['pieces'][g['turn']]['name'], '라')
        self.ok('players.remove', name='가')                                    # 차례 앞사람을 빼도
        self.ok('t.roster')
        g = self.g()
        self.assertEqual(g['pieces'][g['turn']]['name'], '라')
        self.assertEqual(self.pv()['parked']['가']['pos'], 5)                   # 🅿️ 맡아 둔다
        self.ok('players.remove', name='라')                                    # 차례인 사람을 빼면 다음 사람
        self.ok('t.roster')
        g = self.g()
        self.assertEqual(g['pieces'][g['turn']]['name'], '마')
        self.assertEqual(self.pv()['parked']['라']['pts'], 10)
        self.ok('players.add', name='가')                                       # 돌아오면 그대로
        self.ok('t.roster')
        self.assertEqual(self.pieces()['가']['pos'], 5)
        self.assertNotIn('가', self.pv()['parked'])
        self.assertNotIn('다', self.pv()['parked'])                             # 출발 칸 · 0점은 안 맡는다(다는 판에 있다)

    def test_lazy_sync_without_hook(self):
        self.board()
        self.ok('players.add', name='마')
        r = self.roll(piece='마', value=1)                                      # 고리가 없어도 다음 주사위 명령 때 맞춘다
        self.assertEqual(r['piece'], '마')

    def test_rename_hook(self):
        self.board('score', points=10)
        self.roll(piece='나', value=4)
        self.ok('t.rename', **{'from': '나', 'to': '나나'})
        self.assertEqual((self.pieces()['나나']['pos'], self.bd()['나나']), (4, 10))   # 자리 · 점수를 물려받는다
        self.assertNotIn('나', self.pv()['parked'])
        self.assertEqual(list(self.pieces()), ['가', '나나', '다', '라'])        # 제자리(차례 순서 그대로)
        self.ok('t.rename', **{'from': '나나', 'to': '나'})
        self.assertEqual((self.pieces()['나']['pos'], self.bd()['나']), (4, 10))

    def test_empty_roster_keeps_pieces(self):
        self.board()
        self.ok('session.end')                                                   # 방송 끝 — 명단이 한 번에 빈다
        self.ok('t.roster')
        self.assertEqual(list(self.pieces()), self.NAMES)                      # 명단이 비어도 말은 그대로

    def test_remove_one_parks_piece(self):
        # 명단 고리(ON_ROSTER) — 한 명을 빼면 그 말은 그 자리에서 비켜 두었다가(parked) 돌아오면 되살린다
        self.board()
        self.ok('dice.board', do='add', name='가', pts=4)
        self.ok('players.remove', name='가')
        self.assertNotIn('가', self.pieces())
        self.assertEqual(self.pv()['parked']['가']['pts'], 4)
        self.ok('players.add', name='가')
        self.assertIn('가', self.pieces())
        self.assertEqual(self.bd()['가'], 4)


class Settle(Base):
    NAMES = ['가', '나']

    def test_settle_skip_and_undo(self):
        self.board()
        self.ok('dice.board', do='add', name='가', pts=10)
        self.ok('dice.board', do='add', name='나', pts=7)
        self.assertEqual(self.cmd('dice.board', do='add', name='없음', pts=1)[0], 400)
        self.assertEqual(self.cmd('dice.board', do='apply')[0], 400)           # 옮기기는 dice.settle 로만
        for n in ('가', '나'):
            self.ok('players.remove', name=n)
        # 가 를 뺄 때 명단 고리가 가 의 말 · 점수를 비켜 두었다(parked). 나 는 명단이 빈 뒤라 판에 그대로
        r = self.ok('dice.settle')
        self.assertEqual({x['name']: x['points'] for x in r['skipped']}, {'가': 10, '나': 7})
        self.assertEqual(self.bd(), {'나': 7})                                   # 못 옮긴 점수는 남는다(가 는 비켜 둔 곳에)
        self.assertEqual(self.pv()['parked']['가']['pts'], 10)
        self.ok('players.add', name='나')                                       # 나만 돌아왔다
        r = self.ok('dice.settle')
        self.assertEqual(r['moved'], [{'name': '나', 'points': 7}])
        self.assertEqual(r['skipped'], [{'name': '가', 'points': 10, 'parked': True}])
        self.assertEqual((self.player('나')['score'], self.player('나')['contribution']), (0, 7))
        self.assertEqual(self.bd(), {'나': 0})
        self.assertEqual(self.st()['logs'][0]['why'], '🎲 주사위게임 정산')
        self.ok('score.undo')                                                   # 정산을 되돌리면 판 점수도 돌아온다
        self.assertEqual(self.player('나')['contribution'], 0)
        self.assertEqual(self.bd(), {'나': 7})
        self.assertEqual(self.pv()['settles'], {})

    def test_board_reset_set(self):
        self.board()
        self.ok('dice.board', do='set', name='가', pts=-3)
        self.assertEqual(self.bd()['가'], -3)
        self.assertEqual(self.pv()['log'][0]['why'], '손으로 고침')
        self.ok('dice.board', do='reset')
        self.assertEqual(self.bd(), {'가': 0, '나': 0})
        self.assertEqual(self.cmd('dice.board', do='set', name='가', pts='x')[0], 400)


class Session(Base):
    def test_end_resets_round_keeps_setup(self):
        self.board('score', points=10)
        self.ok('dice.keys', keys=['실드권'])
        self.ok('dice.tile', id=5, type='key')
        self.ok('dice.move', piece='가', pos=0)
        self.roll(piece='가', value=5)
        self.ok('players.remove', name='나')
        self.ok('dice.board', do='set', name='다', pts=4)                      # 나는 이미 맡겨졌다(점수 0 → 버려짐)
        self.assertTrue(self.pieces()['가']['shield'])
        self.ok('session.end')
        g, pv = self.g(), self.pv()
        self.assertTrue(all(not r['pts'] for r in g['board']))
        self.assertFalse(any(p['shield'] or p['choose'] or p['pos'] for p in g['pieces']))
        self.assertEqual((pv['parked'], pv['log'], g['action'], g['turn']), ({}, [], {}, 0))
        self.assertEqual((len(g['tiles']), g['keys_count'], pv['keys']), (22, 1, ['실드권']))   # 판 · 덱은 다음 주에도
        self.ok('session.start', names=['가', '마'])
        self.assertEqual(list(self.pieces()), ['가', '마'])
        self.assertTrue(all(v == 0 for v in self.bd().values()))


class Presets(Base):
    def test_basic22(self):
        r = self.ok('dice.preset', name='basic22', sigs=SIGS)
        g = self.g()
        self.assertEqual((r['tiles'], g['cols'], g['rows'], g['dice'], r['missing']), (22, 8, 5, 1, []))
        tiles = g['tiles']
        got = {}
        for t in tiles[1:]:
            k = (t['type'], t.get('points')) if t['type'] == 'score' else (t['type'], t['label'])
            got[k] = got.get(k, 0) + 1
        self.assertEqual(got, {('sig', '이꾸욧'): 2, ('sig', '포카치노'): 1, ('sig', '멈춘시간'): 2,
                               ('score', 0): 2, ('score', 5): 3, ('score', 10): 2, ('score', 20): 1,
                               ('mission', '코끼리코'): 3, ('mission', '고수'): 2, ('mission', '완력기'): 3})
        sig_ids = [t['id'] for t in tiles if t['type'] == 'sig']
        self.assertGreaterEqual(min(b - a for a, b in zip(sig_ids, sig_ids[1:])), 3)   # 시그가 흩어져 있다
        self.assertEqual(tiles[10]['sig']['id'], 2)                              # ' 포카치노 ' 를 찾았다
        self.assertEqual(tiles[6]['sig']['id'], 3)                               # '멈춘 시간' 을 찾았다
        self.assertEqual(self.st()['show']['stage'], 'dicegame')

    def test_basic22_missing_sig(self):
        r = self.ok('dice.preset', name='basic22', sigs=[s for s in SIGS if s['id'] != 2])
        self.assertEqual(r['missing'], ['10번 “포카치노”'])
        self.assertEqual(self.g()['tiles'][10], {'id': 10, 'type': 'blank', 'label': ''})   # 엉뚱한 걸 안 붙인다

    def test_draw22_and_tiles_only(self):
        self.assertEqual(self.cmd('dice.preset', name='draw22', tiles_only=True)[0], 400)   # 22칸 판이 없다
        r = self.ok('dice.preset', name='draw22')
        self.assertEqual(r['keys'], 10)
        t = self.g()['tiles']
        self.assertEqual((t[7]['type'], t[7]['points'], t[11]['type'], t[21]['type']), ('move', -5, 'steal', 'goto'))
        self.ok('dice.move', piece='나', pos=13)
        self.ok('dice.preset', name='draw22', tiles_only=True)                  # 칸만 — 말 위치는 그대로
        self.assertEqual(self.pieces()['나']['pos'], 13)
        self.assertEqual(self.cmd('dice.preset', name='nope')[0], 400)

    def test_find_sig(self):
        L = [{'id': 1, 'title': '이꾸욧'}, {'id': 2, 'title': ' 포카치노 '}, {'id': 3, 'title': '멈춘 시간'},
             {'id': 4, 'title': '"이꾸욧!"'}, {'id': 5, 'title': '포카치노 챌린지'}, {'id': 6, 'title': '전혀다른것'}]
        f = lambda n, lst=L: (dg.find_sig(lst, n) or {}).get('id')
        self.assertEqual((f('이꾸욧'), f('포카치노'), f('멈춘시간'), f('없는이름')), (1, 2, 3, None))
        self.assertEqual(f('이꾸욧', [{'id': 9, 'title': '"이꾸욧!"'}]), 9)       # 따옴표 · 느낌표
        self.assertEqual(f('포카치노', [{'id': 8, 'title': '포카치노 챌린지'}]), 8)   # 뒤에 말이 붙어도


class Timing(unittest.TestCase):
    """서버 시간표(plan)가 옛 _dicegame_plan(== 방송판 dgRollPlan)과 같은 값을 내는가 — 옛 dice_timing_test 의 굴림들."""

    def test_formula(self):
        s = dg.plan({'manual': True, 'dice': [6], 'path': list(range(6)), 'tile': {'type': 'sig'}})
        self.assertEqual((s['land'], s['gate']), (380 + 1800 + 120, 380 + 1800 + 120 + 1500))
        s = dg.plan({'dice': [3], 'path': [1, 2, 3], 'tile': {'type': 'key'}})
        self.assertEqual(s['gate'], 250 + 1300 + 900 + 120 + 1700 + 1500)

    def test_matches_old(self):
        src = os.path.join(ROOT, 'features', 'dicegame.py')
        if not os.path.exists(src):
            self.skipTest('옛 features/dicegame.py 가 없다')
        with io.open(src, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        keep = [n for n in tree.body
                if (isinstance(n, ast.Assign) and any(getattr(t, 'id', '') in ('DG_SIG_BEAT', 'DG_CARD_BEAT', 'DG_KEY_DRAW')
                                                       for t in n.targets))
                or (isinstance(n, ast.FunctionDef) and n.name == '_dicegame_plan')]
        ns = {}
        exec(compile(ast.Module(body=keep, type_ignores=[]), 'old_plan', 'exec'), ns)
        P = lambda n: list(range(1, n + 1))
        cases = [{'dice': [3], 'path': P(3), 'tile': {'type': 'score'}},
                 {'manual': True, 'dice': [6], 'path': P(6), 'tile': {'type': 'sig'}},
                 {'dice': [6, 6], 'path': P(12), 'tile': {'type': 'sig'}},
                 {'manual': True, 'dice': [4], 'path': P(4), 'tile': {'type': 'key'},
                  'after': {'rev': True, 'path': P(7), 'tile': {'type': 'score'}}},
                 {'dice': [5], 'path': P(5), 'tile': {'type': 'move'}, 'after': {'rev': True, 'path': P(5), 'tile': {'type': 'key'}}},
                 {'dice': [1], 'path': P(1), 'tile': {'type': 'key'}, 'after': {'rev': False, 'path': P(9), 'tile': {'type': 'blank'}}},
                 {'dice': [2], 'path': P(2)}]
        cases += [{'manual': True, 'dice': [1], 'path': P(1), 'tile': {'type': 'goto'},
                   'after': {'rev': True, 'path': P(n), 'tile': {'type': 'start'}}} for n in range(9, 32)]
        for c in cases:
            mine = dg.plan(c)
            self.assertEqual({'land': mine['land'], 'gate': mine['gate']}, ns['_dicegame_plan'](c), c)


if __name__ == '__main__':
    unittest.main()
