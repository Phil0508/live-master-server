# -*- coding: utf-8 -*-
"""v2 핵심 흐름 — 후원 받기 → 대기함 → 선수에게 → 점수판 · 되돌리기 · 시그니처 대기줄 · 방송 시작/끝.

옛 프로그램 규칙과 같은지 본다(숫자 · 조건). 돌리기: python -m unittest discover -s v2/tests -t .
"""
import os
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain.rules import derive_name, man_won, split_points

PW, SECRET = 'testpw', 'testsecret-0123456789'
H = {'Authorization': 'Bearer ' + SECRET}
SIGS = [{'id': 1, 'amount': 10300, 'title': '사쿠란보', 'image_url': 'a.png', 'sound_url': 'a.mp3', 'duration': 8},
        {'id': 2, 'amount': 20005, 'title': '뿅뿅', 'image_url': 'b.png', 'sound_url': 'b.mp3', 'duration': 9},
        {'id': 3, 'amount': 50000, 'title': '대박', 'image_url': 'c.png', 'sound_url': 'c.mp3', 'duration': 12}]


class Rules(unittest.TestCase):
    def test_man_won(self):
        self.assertEqual([man_won(a) for a in (5999, 6000, 15999, 16000, 0, 100000)], [0, 1, 1, 2, 0, 10])

    def test_split(self):
        self.assertEqual(split_points(5, 3), [2, 2, 1])
        self.assertEqual(split_points(2, 3), [1, 1, 0])

    def test_names(self):
        self.assertEqual(derive_name('익명', '철수: 응원해요', 'manual_1')[0], '철수')
        self.assertEqual(derive_name('영희', '목표: 100만', 'toon_1')[0], '영희')          # 이름이 있으면 안 건드린다
        self.assertEqual(derive_name('익명', '10:30 에 봐요', 'x')[0], '익명')              # 숫자 · 시각
        self.assertEqual(derive_name('익명', '나: )', 'x')[0], '익명')                    # 이모티콘
        self.assertEqual(derive_name('하늘님', '', 'toon_1')[0], '하늘님')                 # 리스너는 '님' 을 안 뗀다
        self.assertEqual(derive_name('하늘님', '', 'manual_1')[0], '하늘님')               # 콘솔에 손으로 적은 이름
        self.assertEqual(derive_name('하늘님', '', 'web_1')[0], '하늘')                    # 화면을 긁던 옛 경로만 뗀다


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2flow_')
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET,
                                       sig_fetch=lambda: SIGS))
        self.cmd('session.start', names=['하율', '서아', '채원'])

    def tearDown(self):
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def cmd(self, t, **data):
        r = self.c.post('/api/cmd', json={'type': t, 'data': data}, headers=H)
        return r.status_code, r.json()

    def st(self, auth=True):
        return self.c.get('/api/state', headers=H if auth else {}).json()['slices']

    def don(self, name, amount, tx=None, msg='', **kw):
        body = dict({'name': name, 'amount': amount, 'message': msg, 'tx_id': tx}, **kw)
        r = self.c.post('/api/donation', json=body, headers=H)
        return r.status_code, r.json()

    def player(self, name, s=None):
        s = s or self.st()
        return next(p for p in s['players']['list'] if p['name'] == name)


class Flow(Base):
    # ── 받기 ──
    def test_donation_to_pending_and_assign(self):
        c, r = self.don('별빛', 50000, 'toon_a1')
        self.assertEqual((c, r['status']), (200, 'success'))
        s = self.st()
        self.assertEqual(len(s['pending']), 1)
        self.assertEqual(s['popup']['donation']['amount'], 50000)
        self.assertEqual(s['tallies']['donors']['별빛']['total'], 50000)
        self.assertEqual(s['tallies']['best']['amount'], 50000)
        self.assertEqual(s['queue']['items'][0]['title'], '대박')                 # 5만 원 → 5만 원 시그
        pid = s['pending'][0]['id']
        c, r = self.cmd('pending.assign', id=pid, name='서아')
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertEqual(s['pending'], [])
        self.assertEqual((self.player('서아', s)['score'], self.player('서아', s)['contribution']), (5, 5))
        self.assertEqual(s['players']['list'][0]['name'], '서아')                  # 기여도 1등이 맨 위
        self.assertEqual(s['popup']['score']['diff'], 5)
        self.assertEqual(s['tallies']['best']['member'], '서아')
        # 두 번 눌러도 한 번
        c, r = self.cmd('pending.assign', id=pid, name='서아')
        self.assertTrue(r.get('already'))
        self.assertEqual(self.player('서아')['score'], 5)

    def test_undo_returns_to_pending(self):
        self.don('별빛', 30000, 'toon_u1')
        pid = self.st()['pending'][0]['id']
        self.cmd('pending.assign', id=pid, name='하율')
        c, r = self.cmd('score.undo')
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertEqual(self.player('하율', s)['score'], 0)
        self.assertEqual([x['id'] for x in s['pending']], [pid])                  # ⭐ 대기함으로 돌아왔다
        self.assertEqual(s['tallies']['best']['member'], '')
        self.assertEqual(s['logs'], [])
        # 다시 다른 사람에게
        self.cmd('pending.assign', id=pid, name='채원')
        self.assertEqual(self.player('채원')['score'], 3)

    def test_split(self):
        self.don('별빛', 50000, 'toon_s1')
        pid = self.st()['pending'][0]['id']
        c, r = self.cmd('pending.assign', id=pid, names=['하율', '서아', '채원'])
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertEqual([self.player(n, s)['score'] for n in ('하율', '서아', '채원')], [2, 2, 1])
        self.cmd('score.undo')                                                       # 나눠 준 것도 한 번에 되돌린다
        self.assertEqual([self.player(n)['score'] for n in ('하율', '서아', '채원')], [0, 0, 0])

    def test_unknown_player_changes_nothing(self):
        self.don('별빛', 20000, 'toon_x1')
        pid = self.st()['pending'][0]['id']
        c, r = self.cmd('pending.assign', id=pid, names=['하율', '없는사람'])
        self.assertEqual(c, 404)
        s = self.st()
        self.assertEqual(self.player('하율', s)['score'], 0)
        self.assertEqual(len(s['pending']), 1)

    def test_duplicate_tx_and_content(self):
        self.don('별빛', 20000, 'toon_d1')
        c, r = self.don('별빛', 20000, 'toon_d1')
        self.assertEqual(r.get('message'), 'Duplicate donation ignored.')
        self.don('달빛', 15000, 'web_1', msg='안녕')
        c, r = self.don('달빛', 15000, 'web_2', msg='안녕')                         # 12초 안 같은 내용(리스너 아님)
        self.assertEqual(r.get('message'), 'Duplicate donation ignored.')
        self.assertEqual(len(self.st()['pending']), 2)

    def test_display_only(self):
        c, r = self.don('쵸코맘', 1000, 'toon_s9', display_only=True)
        self.assertTrue(r.get('display_only'))
        s = self.st()
        self.assertEqual(s['pending'], [])
        self.assertTrue(s['popup']['donation']['display_only'])
        self.assertEqual(s['tallies']['donors'], {})
        self.assertEqual(s['queue']['items'], [])

    def test_small_goes_to_notice(self):
        self.don('작은손', 5000, 'manual_1')                                            # 최저선(10,000) 미만
        s = self.st()
        self.assertEqual(s['queue']['items'], [])
        self.assertEqual(s['tallies']['notice_donors'][0]['name'], '작은손')
        self.assertEqual(len(s['pending']), 1)                                          # 대기함에는 들어간다
        self.don('만원', 10000, 'manual_2')                                              # 1만 원은 제일 싼 시그
        self.assertEqual(self.st()['queue']['items'][0]['title'], '사쿠란보')

    def test_queue_merge_and_done(self):
        self.don('별빛', 20000, 'toon_q1')
        self.don('별빛', 20000, 'toon_q2')
        self.don('달빛', 20000, 'toon_q3')
        q = self.st()['queue']['items']
        self.assertEqual([(x['donator'], x['count']) for x in q], [('별빛', 2), ('달빛', 1)])
        self.assertEqual(self.st()['tallies']['sigs']['2']['count'], 3)
        # 방송판(로그인 없음)이 다 틀었다고 알린다 — 맨 앞 id 일 때만
        r = self.c.post('/api/cmd', json={'type': 'reaction.done', 'data': {'id': q[1]['id']}})
        self.assertTrue(r.json().get('ignored'))
        r = self.c.post('/api/cmd', json={'type': 'reaction.done', 'data': {'id': q[0]['id']}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x['donator'] for x in self.st()['queue']['items']], ['달빛'])
        # 방송판은 건너뛰기 · 멈춤을 못 한다
        r = self.c.post('/api/cmd', json={'type': 'reaction.stop', 'data': {}})
        self.assertEqual(r.status_code, 401)

    def test_public_hides_pending_and_logs(self):
        self.don('별빛', 20000, 'toon_p1', msg='비밀메모')
        pub = self.st(auth=False)
        self.assertNotIn('pending', pub)
        self.assertNotIn('logs', pub)
        self.assertIn('players', pub)

    def test_extra_game(self):
        self.cmd('extra.start')
        self.don('별빛', 20000, 'toon_e1')
        pid = self.st()['pending'][0]['id']
        self.cmd('pending.assign', id=pid, name='하율')
        s = self.st()
        self.assertEqual(self.player('하율', s)['score'], 0)                          # 본판은 그대로
        self.assertEqual(next(p for p in s['players']['extra'] if p['name'] == '하율')['score'], 2)
        self.cmd('extra.end')
        self.assertEqual(self.player('하율')['score'], 2)                              # 끝나면 본판에 더한다

    def test_manual_and_bottom(self):
        c, r = self.cmd('score.add', name='채원', delta=3)
        self.assertEqual(c, 200)
        self.cmd('score.add', name='채원', delta=0, contrib=7, reason='주사위')
        self.assertEqual((self.player('채원')['score'], self.player('채원')['contribution']), (3, 10))
        self.cmd('score.add', target='bottom', delta=4)
        self.assertEqual(self.st()['players']['bottom']['score'], 4)
        self.cmd('score.undo')
        self.assertEqual(self.st()['players']['bottom']['score'], 0)

    def test_end_and_restart_resets(self):
        self.don('별빛', 20000, 'toon_r1')
        self.cmd('session.end')
        s = self.st()
        self.assertEqual((s['players']['list'], s['pending'], s['queue']['items']), ([], [], []))
        c, r = self.cmd('session.start', names=['가', '나'])
        self.assertEqual(c, 200)
        self.assertEqual([p['name'] for p in self.st()['players']['list']], ['가', '나'])

    def test_legacy_auth(self):
        r = self.c.post('/api/donation', json={'name': 'x', 'amount': 1000, 'tx_id': 'toon_z'})
        self.assertEqual(r.status_code, 401)                                            # 바깥 · 로그인 없음
        os.environ['DONATION_KEY'] = 'k-123'
        try:
            r = self.c.post('/api/donation', json={'name': 'x', 'amount': 20000, 'tx_id': 'toon_z'},
                            headers={'X-Donation-Key': 'k-123'})
            self.assertEqual(r.status_code, 200)
        finally:
            del os.environ['DONATION_KEY']
        self.assertEqual(self.c.post('/api/donation', json={'name': 'x', 'amount': -5}, headers=H).status_code, 400)
        self.assertEqual(self.c.post('/api/donation', json={'name': 'x', 'amount': 'abc'}, headers=H).status_code, 400)


if __name__ == '__main__':
    unittest.main()


class Console(Base):
    def test_console_play(self):
        r = self.c.post('/api/signature/play', json={'amount': 20000, 'name': '계좌손님', 'count': 3}, headers=H).json()
        self.assertEqual((r['status'], r['count'], r['title']), ('success', 3, '뿅뿅'))
        q = self.st()['queue']['items']
        self.assertEqual((q[-1]['donator'], q[-1]['count']), ('계좌손님', 3))
        self.assertEqual(self.st()['tallies']['sigs'], {})                     # 재생 전용 — 집계에 안 넣는다
        r = self.c.post('/api/signature/play', json={'amount': 3000, 'name': '소액'}, headers=H).json()
        self.assertTrue(r['display_only'])
        self.assertTrue(self.st()['popup']['donation']['display_only'])
        r = self.c.post('/api/signature/play', json={'sig_id': 3, 'name': '골라틀기'}, headers=H).json()
        self.assertEqual(r['title'], '대박')
        self.assertEqual(self.c.post('/api/signature/play', json={'amount': 20000}).status_code, 401)
        self.assertEqual(self.c.get('/api/signatures', headers=H).json()['count'], 3)


class Preflight(Base):
    def test_preflight(self):
        self.assertEqual(self.c.get('/api/preflight').status_code, 401)
        with self.c.websocket_connect('/ws?kind=overlay') as ov, self.c.websocket_connect('/ws?kind=overlay&monitor=1') as mon:
            ov.receive_json(); mon.receive_json()
            d = self.c.get('/api/preflight?deep=1', headers=H).json()
            self.assertEqual((d['screens']['overlay'], d['screens']['monitor']), (1, 1))
            self.assertTrue(d['broadcast_active'])
            self.assertEqual((d['sig']['count'], d['sig']['cheapest']), (3, 10300))
            self.assertIn(d['listener']['level'], ('none', 'ok', 'connecting', 'down'))


class Show(Base):
    def test_stage_temp_returns(self):
        self.cmd('show.stage', stage='match')
        from v2.server.domain import show as sh
        # 잠깐 올라온 룰렛이 끝나면 대결로 돌아간다 — 명령 안에서 쓰는 함수라 버스로 직접 부른다
        bus = self.c.app.state.bus
        from v2.server.bus import command
        @command('t.roulette')
        def _t(ctx, data):
            if data.get('end'):
                sh.end_temp(ctx, 'roulette')
            else:
                sh.set_stage(ctx, 'roulette', temp=True)
        self.cmd('t.roulette')
        self.assertEqual(self.st()['show']['stage'], 'roulette')
        self.cmd('t.roulette', end=True)
        self.assertEqual(self.st()['show']['stage'], 'match')
        self.assertEqual(self.cmd('show.stage', stage='nope')[0], 400)

    def test_notice(self):
        self.cmd('notice.add', text='둘째 공지')
        self.cmd('notice.move', index=1, dir=-1)
        n = self.st()['notice']
        self.assertEqual(n['msgs'][0], '둘째 공지')
        self.cmd('notice.now', index=0)
        self.assertEqual(self.st()['notice']['now']['idx'], 0)
        self.assertEqual(self.cmd('notice.add', text='   ')[0], 400)
        self.cmd('notice.every', period=5, speed=999)
        n = self.st()['notice']
        self.assertEqual((n['period'], n['speed']), (20, 400))

    def test_hud_account(self):
        self.cmd('show.hud', key='best', on=True)
        self.cmd('account.set', bank='국민', acc_num='123-45', name='엔젤')
        s = self.st(auth=False)
        self.assertTrue(s['show']['hud']['best'])
        self.assertEqual(s['account']['bank'], '국민')


class Cards(Base):
    def test_contrib_card(self):
        from v2.server.bus import command
        from v2.server.domain.donation import add_pending_card

        @command('t.card')
        def _t(ctx, data):
            ctx.notes['id'] = add_pending_card(ctx, '주사위', 12, '주사위 보너스')
        c, r = self.cmd('t.card')
        c, r2 = self.cmd('pending.assign', id=r['id'], names=['하율', '서아'])
        self.assertEqual(c, 200, r2)
        s = self.st()
        self.assertEqual([(self.player(n, s)['score'], self.player(n, s)['contribution']) for n in ('하율', '서아')], [(0, 6), (0, 6)])


class ExtraUndo(Base):
    def test_undo_after_extra_end_and_cancel(self):
        self.cmd('extra.start')
        self.cmd('score.add', name='하율', delta=4)
        self.cmd('extra.end')                                                     # 본판에 더해졌다
        self.assertEqual(self.player('하율')['score'], 4)
        c, r = self.cmd('score.undo')
        self.assertEqual(self.player('하율')['score'], 0)                          # ⭐ 본판에서 뺀다
        self.assertEqual(r['rows'][0]['name'], '하율')
        self.cmd('extra.start')
        self.cmd('score.add', name='서아', delta=3)
        self.cmd('extra.cancel')                                                  # 버렸다
        c, r = self.cmd('score.undo')
        self.assertEqual(self.player('서아')['score'], 0)                          # 본판엔 손대지 않는다
        self.assertEqual(r['skipped'], ['서아'])


class PlayAll(Base):
    def test_two_overlays_dont_double_count(self):
        self.c.post('/api/signature/play', json={'amount': 20000, 'name': '계좌', 'count': 3}, headers=H)
        it = self.st()['queue']['items'][0]
        self.cmd('reaction.playall', id=it['id'], on=True)
        done = lambda rp: self.c.post('/api/cmd', json={'type': 'reaction.done', 'data': {'id': it['id'], 'replay': rp}}).json()
        done(0)
        self.assertTrue(done(0).get('ignored'))                                   # 두 번째 화면의 같은 회차 보고
        self.assertEqual(self.st()['queue']['items'][0]['count'], 2)
        done(1)
        self.assertEqual(self.st()['queue']['items'][0]['count'], 1)
        done(2)
        self.assertEqual(self.st()['queue']['items'], [])


class Layout(Base):
    def test_layout(self):
        self.cmd('layout.set', id='ranking', x=100, y=99999, scale=9)
        w = self.st(auth=False)['layout']['widgets']['ranking']
        self.assertEqual((w['x'], w['y'], w['scale']), (100, 2880, 4.0))          # 화면 밖 · 너무 큼은 잘라 낸다
        self.assertEqual(self.cmd('layout.set', id='ranking', x='abc')[0], 400)
        self.cmd('layout.reset', id='ranking')
        self.assertEqual(self.st()['layout']['widgets'], {})
        self.cmd('layout.set', id='gauge', x=10)
        self.assertEqual(self.cmd('layout.reset')[0], 400)                         # 빈 id 로 전부 날리지 않는다
        self.cmd('layout.reset', all=True)
        self.assertEqual(self.st()['layout']['widgets'], {})
