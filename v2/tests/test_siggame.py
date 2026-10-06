# -*- coding: utf-8 -*-
"""v2 시그뒤집기 — 옛 tests/sg_test.py 의 규칙을 그대로 본다. 무엇보다: 덮인 카드의 속이 방송판(로그인 없음)으로 안 샌다.

돌리기(저장소 루트에서): python -m unittest v2.tests.test_siggame
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain import siggame as sg      # ⚠️ domain/__init__ 에 아직 안 들어가 있다 — 여기서 직접 불러 등록한다

PW, SECRET = 'testpw', 'testsecret-0123456789'
H = {'Authorization': 'Bearer ' + SECRET}
# 이름 · 그림 주소를 일부러 눈에 띄게 — 공개 쪽지에 한 글자라도 섞이면 찾아낸다
SIGS = [{'id': 100 + i, 'amount': 10000 + i * 1000, 'title': '비밀카드%02d' % i, 'image_url': 'secret%02d.png' % i,
         'sound_url': 's%02d.mp3' % i, 'duration': 8} for i in range(1, 21)]
IDS16 = [s['id'] for s in SIGS[:16]]


class Clock:
    """명령 시각만 바꾼다(bus 가 쓰는 time 만 갈아 끼운다)."""

    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2sg_')
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET,
                                       sig_fetch=lambda: SIGS))
        self.cmd('session.start', names=['하율', '서아'])

    def tearDown(self):
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def cmd(self, t, auth=True, **data):
        r = self.c.post('/api/cmd', json={'type': t, 'data': data}, headers=H if auth else {})
        return r.status_code, r.json()

    def picks(self, ids, auth=True):
        r = self.c.post('/api/siggame/picks', json={'picks': ids}, headers=H if auth else {})
        return r.status_code, r.json()

    def st(self, auth=True):
        return self.c.get('/api/state', headers=H if auth else {}).json()['slices']

    def game(self, auth=True):
        return self.st(auth)['siggame']

    def deck(self):
        # ⚠️ 카드 앞면은 숨김 조각 — 조종실에도 안 간다. 검사는 서버 안을 직접 본다
        return self.c.app.state.bus.state.get('siggame_deck')

    def start(self, ids=IDS16, **kw):
        self.assertEqual(self.picks(ids)[0], 200)
        c, r = self.cmd('sig.deal', **dict({'minutes': 10, 'target': 5}, **kw))
        self.assertEqual(c, 200, r)
        return r

    def goals(self, g=None):
        return [c for c in (g or self.game())['cards'] if c.get('flippedAt')]


class SigGame(Base):
    def test_auth(self):
        for t, d in [('sig.deal', {}), ('sig.flip', {'id': 1}), ('sig.clear', {}), ('sig.show', {'on': True}),
                     ('sig.done', {'id': 1}), ('sig.peek', {}), ('sig.timer', {'action': 'START'})]:
            self.assertEqual(self.cmd(t, auth=False, **d)[0], 401, t)
        self.assertEqual(self.picks(IDS16, auth=False)[0], 401)
        # 까보기 끝은 방송판이 부른다 — 로그인 없이 되지만 덮기만 한다
        c, r = self.cmd('sig.peek_end', auth=False)
        self.assertEqual(c, 200)
        self.assertTrue(r.get('ignored'))

    def test_picks(self):
        c, r = self.picks(IDS16)
        self.assertEqual((c, r['count'], r['missing'], r['requested']), (200, 16, [], 16))
        self.assertEqual(self.deck()['picks'][0]['title'], '비밀카드01')
        self.assertNotIn('picks', self.game())                                      # 공개 조각엔 고른 목록이 없다
        self.assertEqual(self.picks([])[0], 400)                                    # 빈 목록
        self.assertEqual(self.picks(list(range(1, 50)))[0], 400)                    # 36장 초과
        self.assertEqual(self.picks('notalist')[0], 400)                            # 목록이 아님
        c, r = self.picks([101, 9999])
        self.assertEqual((c, r['count'], r['missing']), (200, 1, [9999]))           # 없는 것은 빼고 알려 준다
        self.assertEqual(self.picks([9998, 9999])[0], 400)                          # 하나도 못 찾으면 거절
        self.assertEqual(len(self.deck()['picks']), 1)                              # 거절은 아무것도 안 바꾼다

    def test_deal_masks_cards(self):
        r = self.start()
        self.assertEqual((r['count'], r['cols'], r['rows'], r['target']), (16, 4, 4, 5))
        s = self.st()
        self.assertEqual(s['show']['stage'], 'siggame')                              # 깔면 무대를 차지한다
        g = s['siggame']
        self.assertTrue(all(c == {'id': c['id'], 'state': 'HIDDEN'} for c in g['cards']))   # 번호와 '덮임'만
        self.assertEqual([c['id'] for c in g['cards']], list(range(1, 17)))
        self.assertEqual((g['timer']['status'], g['timer']['timeLeft']), ('STOPPED', 600))
        self.assertEqual(g['action']['type'], 'PLACE')
        self.assertEqual(len(self.deck()['cards']), 16)                               # 정답은 숨김 조각에
        self.assertNotIn('siggame_deck', s)                                              # ⭐ 조종실에도 안 간다
        pub = self.c.get('/api/state').json()
        self.assertNotIn('siggame_deck', pub['slices'])
        txt = json.dumps(pub, ensure_ascii=False)
        self.assertNotIn('비밀카드', txt)
        self.assertNotIn('secret', txt)

    def test_flip(self):
        self.start()
        c, r = self.cmd('sig.flip', id=3)
        self.assertEqual(c, 200, r)
        face = next(x for x in self.deck()['cards'] if x['id'] == 3)
        self.assertEqual((r['title'], r['amount'], r['remaining_flips']), (face['title'], face['amount'], 4))
        g = self.game(auth=False)
        c3 = next(x for x in g['cards'] if x['id'] == 3)
        self.assertEqual((c3['state'], c3['image'], c3['title']), ('REVEALED', face['image'], face['title']))
        self.assertTrue(c3['flippedAt'])
        self.assertTrue(all(x == {'id': x['id'], 'state': 'HIDDEN'} for x in g['cards'] if x['id'] != 3))
        self.assertEqual(g['action'], {'type': 'FLIP', 'ts': c3['flippedAt'], 'id': 3})
        c, r = self.cmd('sig.flip', id=3)
        self.assertTrue(r.get('already'))                                            # 같은 카드 다시 → already
        self.assertEqual(self.cmd('sig.flip', id=999)[0], 404)
        for cid in (1, 2, 4, 5):
            self.cmd('sig.flip', id=cid)
        c, r = self.cmd('sig.flip', id=6)
        self.assertEqual(c, 400)                                                     # 목표(5장)를 넘겨 못 뒤집는다
        self.assertIn('이미 5장', r['error'])
        self.assertEqual(sum(1 for x in self.game()['cards'] if x['state'] == 'REVEALED'), 5)
        for bad in ({'id': 'abc'}, {}, {'id': None}):                                # 이상한 번호
            r = self.c.post('/api/cmd', json={'type': 'sig.flip', 'data': bad}, headers=H)
            self.assertEqual(r.status_code, 400, bad)

    def test_done_and_allclear(self):
        hooked = []
        sg.ON_ALLCLEAR.append(lambda ctx, n: hooked.append(n))
        try:
            self.start()
            for cid in (1, 2, 3, 4, 5):
                self.cmd('sig.flip', id=cid)
            self.assertEqual(self.cmd('sig.done', id=7)[0], 400)                        # 안 뒤집은 카드
            self.assertEqual(self.cmd('sig.done', id=99)[0], 404)
            before = sum(c['amount'] for c in self.goals() if not c['doneAt'])
            for cid in (3, 1, 2, 4):
                self.assertTrue(self.cmd('sig.done', id=cid)[1]['done'])
            g = self.game(auth=False)
            self.assertEqual(sum(1 for c in g['cards'] if c.get('doneAt')), 4)
            # 왼쪽 숫자(받아야 할 돈)는 받아낸 만큼 줄어든다 — 사장님 규칙
            after = sum(c['amount'] for c in self.goals(g) if not c['doneAt'])
            self.assertEqual(after, before - sum(c['amount'] for c in self.goals(g) if c['id'] in (1, 2, 3, 4)))
            self.cmd('sig.done', id=5)
            c, r = self.cmd('sig.done', id=5, done=False)
            self.assertEqual((c, r['done']), (200, False))                              # 달성 취소
            self.assertIsNone(self.game()['action'])
            self.cmd('sig.done', id=5)                                                  # 안 주면 뒤집기
            self.assertTrue(next(c for c in self.game()['cards'] if c['id'] == 5)['doneAt'])
            self.cmd('sig.done', id=5)
            c, r = self.cmd('sig.allclear')                                             # 1장 비운 채 → 남은 것까지 한 번에
            self.assertEqual((c, r['count'], r['filled']), (200, 5, 1))
            g = self.game()
            self.assertEqual(sum(1 for c in g['cards'] if c.get('doneAt')), 5)
            self.assertEqual((g['action']['type'], g['action']['count']), ('ALLCLEAR', 5))
            self.assertEqual(hooked, [5])
        finally:
            sg.ON_ALLCLEAR.clear()

    def test_timer(self):
        self.start()
        clock = Clock(1_800_000_000.0)
        with mock.patch('v2.server.bus.time', clock):
            c, r = self.cmd('sig.timer', action='START')
            self.assertEqual((c, r['timer']['status']), (200, 'PLAYING'))
            self.assertEqual(r['timer']['expiresAt'], int(clock.t * 1000) + 600000)   # 끝나는 시각만 둔다
            self.assertEqual(self.cmd('sig.timer', action='start')[0], 200)            # 돌고 있으면 그대로
            self.assertEqual(self.game()['timer']['expiresAt'], r['timer']['expiresAt'])
            clock.t += 1.2
            c, r = self.cmd('sig.timer', action='PAUSE')
            self.assertEqual((r['timer']['status'], r['timer']['timeLeft'], r['timer']['expiresAt']), ('PAUSED', 598, None))
            c, r = self.cmd('sig.timer', action='STOP', minutes=3)
            self.assertEqual((r['timer']['status'], r['timer']['timeLeft']), ('STOPPED', 180))
            self.assertEqual(self.cmd('sig.timer', action='WAT')[0], 400)
            self.assertEqual(self.cmd('sig.timer', action='STOP', minutes=0)[1]['timer']['timeLeft'], 0)
            self.assertEqual(self.cmd('sig.timer', action='START')[0], 400)              # 남은 시간이 없다
            self.assertEqual(self.cmd('sig.timer', action='STOP', minutes=9999)[1]['timer']['timeLeft'], 10800)

    def test_reveal_shuffle_clear(self):
        self.start()
        for cid in (1, 2, 3, 4, 5):
            self.cmd('sig.flip', id=cid)
        self.cmd('sig.done', id=1)
        self.cmd('sig.lift', on=True)
        self.assertEqual(self.cmd('sig.reveal')[0], 200)
        g = self.game(auth=False)
        self.assertTrue(all(c['state'] == 'REVEALED' for c in g['cards']))
        self.assertEqual(len(self.goals(g)), 5)                                          # 구경용 공개는 목표가 아니다
        self.assertEqual(self.cmd('sig.flip', id=9)[1].get('already'), True)
        order = [c['sig_id'] for c in self.deck()['cards']]
        c, r = self.cmd('sig.shuffle', seed=3)
        self.assertEqual(c, 200)
        g = self.game(auth=False)
        self.assertTrue(all(c == {'id': c['id'], 'state': 'HIDDEN'} for c in g['cards']))   # 다시 전부 덮인다
        self.assertFalse(any(c['doneAt'] or c['flippedAt'] for c in self.deck()['cards']))  # 달성 기록도 지운다
        self.assertFalse(g['compact'])
        self.assertIn(g['action']['animIndex'], (1, 2, 3, 4))
        self.assertEqual(sorted(c['sig_id'] for c in self.deck()['cards']), sorted(order))  # 같은 카드, 자리만
        self.assertEqual(self.cmd('sig.clear')[0], 200)
        s = self.st()
        self.assertEqual((s['siggame']['cards'], self.deck()['cards']), ([], []))
        self.assertEqual(len(self.deck()['picks']), 16)                             # 고른 시그니처는 남는다
        self.assertIsNone(s['show']['stage'])                                             # 치우면 내린다
        self.assertEqual(s['siggame']['timer']['timeLeft'], 600)
        # 카드 없이
        c, r = self.cmd('sig.show', on=True)
        self.assertEqual((c, r['on'], r['cards']), (200, True, 0))                        # 켜지긴 한다
        self.assertEqual(self.st()['show']['stage'], 'siggame')
        for t in ('sig.shuffle', 'sig.allclear', 'sig.peek', 'sig.reveal'):
            self.assertEqual(self.cmd(t)[0], 400, t)
        self.cmd('sig.show', on=False)
        self.assertIsNone(self.st()['show']['stage'])

    def test_show_off_leaves_other_stage(self):
        self.cmd('show.stage', stage='match')
        self.cmd('sig.show', on=False)                                                    # 다른 판이 올라와 있으면 그대로
        self.assertEqual(self.st()['show']['stage'], 'match')
        self.start()
        self.assertEqual(self.st()['show']['stage'], 'siggame')

    def test_limits(self):
        self.picks([s['id'] for s in SIGS[:6]])
        self.cmd('sig.deal', minutes=5, target=3)
        self.assertEqual(self.cmd('sig.set', target=99)[1]['target'], 6)                 # 깔린 장수를 못 넘는다
        self.assertEqual(self.cmd('sig.set', target=0)[1]['target'], 1)
        self.assertEqual(self.cmd('sig.set', target='x')[1]['target'], 1)                # 숫자가 아니면 그대로
        self.assertEqual(self.cmd('sig.set', opacity=5)[1]['opacity'], 1.0)
        self.assertEqual(self.cmd('sig.set', opacity=0)[1]['opacity'], 0.1)
        self.assertEqual(self.cmd('sig.set', opacity='x')[1]['opacity'], 0.1)
        c, r = self.cmd('sig.deal', minutes=5, target=20)
        self.assertEqual(r['target'], 6)                                                  # 깔 때도 고른 장수를 넘지 않는다
        self.assertEqual((r['cols'], r['rows']), (3, 2))
        self.cmd('sig.deal', minutes=9999)
        self.assertEqual(self.game()['timer']['timeLeft'], 180 * 60)                      # 180분으로 자른다
        self.cmd('sig.deal', minutes='x')
        self.assertEqual(self.game()['timer']['timeLeft'], 600)
        self.cmd('sig.clear')
        self.assertEqual(self.cmd('sig.set', target=30)[1]['target'], 30)                 # 안 깔렸으면 36까지
        self.assertEqual(self.cmd('sig.set', target=99)[1]['target'], 36)
        # /api/cmd 로 바로 보내면 시그니처 목록(sigs)이 없다 — 찾을 수 없다고 거절하고 고른 것은 그대로
        c, r = self.cmd('sig.picks', picks=[101])
        self.assertEqual(c, 400)
        self.assertEqual(len(self.deck()['picks']), 6)

    def test_deal_needs_picks(self):
        c, r = self.cmd('sig.deal')
        self.assertEqual(c, 400)
        self.assertIn('먼저 시그니처', r['error'])

    def test_lift(self):
        self.picks([s['id'] for s in SIGS[:8]])
        self.cmd('sig.deal', target=6)
        self.assertEqual(self.cmd('sig.lift', on=True)[0], 400)                          # 뒤집은 목표가 없다
        self.cmd('sig.flip', id=2)
        self.cmd('sig.flip', id=5)
        c, r = self.cmd('sig.lift')
        self.assertEqual((c, r['compact'], r['goals']), (200, True, 2))
        self.assertEqual(self.game()['action']['type'], 'LIFT')
        self.assertFalse(self.cmd('sig.lift')[1]['compact'])                              # 다시 누르면 판 전체로
        for cid in (1, 3, 4, 6):
            self.cmd('sig.flip', id=cid)
        c, r = self.cmd('sig.lift', on=True)
        self.assertEqual(c, 400)                                                          # 6장은 한 줄에 못 올린다
        self.assertEqual(self.cmd('sig.lift', on=False)[0], 200)                          # 내리기는 언제나

    def test_peek(self):
        self.start()
        self.cmd('sig.flip', id=1)
        clock = Clock(1_800_000_000.0)
        with mock.patch('v2.server.bus.time', clock):
            c, r = self.cmd('sig.peek')
            self.assertEqual((c, r['count']), (200, 15))
            g = self.game(auth=False)
            hidden = [c for c in g['cards'] if c['id'] != 1]
            faces = {c['id']: c for c in self.deck()['cards']}
            # 까보기 중에는 속이 실린다 — state 는 HIDDEN 그대로, 목표도 아니다
            self.assertTrue(all(c['state'] == 'HIDDEN' and c['title'] == faces[c['id']]['title'] and not c['flippedAt']
                                for c in hidden))
            clock.t += 3
            c, r = self.cmd('sig.peek_end', auth=False)                                   # 일찍 → 무시
            self.assertTrue(r.get('ignored'))
            self.assertIn('title', self.game(auth=False)['cards'][5])
            clock.t += 3.0
            c, r = self.cmd('sig.peek_end', auth=False)                                   # 6초 → 다시 덮는다
            self.assertEqual(c, 200)
            self.assertFalse(r.get('ignored'))
            g = self.game(auth=False)
            self.assertTrue(all(c == {'id': c['id'], 'state': 'HIDDEN'} for c in g['cards'] if c['id'] != 1))
            self.assertTrue(g['action']['closed'])
            self.assertTrue(self.cmd('sig.peek_end', auth=False)[1].get('ignored'))       # 두 번째 화면이 또 보내도 그대로
            self.assertEqual(next(c for c in g['cards'] if c['id'] == 1)['state'], 'REVEALED')
            # 끝 신호가 안 와도 6초 뒤 다른 명령이 덮는다
            self.cmd('sig.peek')
            self.assertIn('title', self.game(auth=False)['cards'][5])
            clock.t += 7
            self.cmd('sig.set', opacity=0.9)
            self.assertEqual(self.game(auth=False)['cards'][5], {'id': 6, 'state': 'HIDDEN'})
            # 까보기 바로 0.2초 전(시계 어긋남 여유)이면 끝낸다
            self.cmd('sig.peek')
            clock.t += 5.8
            self.assertFalse(self.cmd('sig.peek_end', auth=False)[1].get('ignored'))
            self.assertEqual(self.game(auth=False)['cards'][5], {'id': 6, 'state': 'HIDDEN'})
            # 전부 공개한 카드도 목표가 아니라 '안 뽑힌' 카드다 — 까볼 수 있다(옛 것과 같다)
            self.cmd('sig.reveal')
            self.assertEqual(self.cmd('sig.peek')[0], 200)
        # 전부 목표로 뒤집었으면 까볼 것이 없다
        self.picks([s['id'] for s in SIGS[:3]])
        self.cmd('sig.deal', target=3)
        for cid in (1, 2, 3):
            self.cmd('sig.flip', id=cid)
        c, r = self.cmd('sig.peek')
        self.assertEqual(c, 400)
        self.assertIn('안 뽑힌', r['error'])

    def test_seed(self):
        self.picks(IDS16)
        self.cmd('sig.deal', seed=7)
        a = [c['sig_id'] for c in self.deck()['cards']]
        self.cmd('sig.deal', seed=7)
        self.assertEqual([c['sig_id'] for c in self.deck()['cards']], a)                  # 같은 씨앗 → 같은 배치
        self.cmd('sig.deal', seed=8)
        self.assertNotEqual([c['sig_id'] for c in self.deck()['cards']], a)
        self.assertEqual(sorted(a), sorted(IDS16))

    def test_session_reset(self):
        self.start()
        self.cmd('sig.flip', id=2)
        self.cmd('sig.lift', on=True)
        self.cmd('sig.set', opacity=0.5)
        self.cmd('sig.timer', action='START')
        self.cmd('session.end')
        s = self.st()
        g = s['siggame']
        self.assertEqual((g['cards'], g['action'], g['compact']), ([], None, False))
        self.assertEqual(g['timer'], {'status': 'STOPPED', 'timeLeft': 600, 'expiresAt': None})
        self.assertEqual((g['opacity'], g['target']), (0.5, 5))                           # 설정은 남긴다
        self.assertEqual(self.deck()['cards'], [])
        self.assertEqual(len(self.deck()['picks']), 16)                             # 고른 시그니처도 남긴다
        self.assertIsNone(s['show']['stage'])
        self.cmd('session.start', names=['가'])
        self.assertEqual(self.cmd('sig.deal')[0], 200)                                    # 다음 방송에 그대로 깐다

    def test_failed_command_changes_nothing(self):
        self.start()
        for cid in (1, 2, 3, 4, 5):
            self.cmd('sig.flip', id=cid)
        def state():
            d = self.c.get('/api/state', headers=H).json()
            d.pop('now', None)                       # 서버 시각은 매번 다르다
            return d
        before = state()
        self.assertEqual(self.cmd('sig.flip', id=6)[0], 400)
        self.assertEqual(state(), before)


class NeverLeaks(Base):
    """⭐ 덮인 카드의 속은 로그인 없는 화면에 한 번도 안 간다 — 통째(snapshot)든 쪽지(patch)든."""

    def test_websocket(self):
        with self.c.websocket_connect('/ws?kind=overlay') as ov, \
                self.c.websocket_connect('/ws?kind=controller&token=' + SECRET) as ct:
            msgs, cmsgs = [ov.receive_text()], [ct.receive_text()]
            n = 0
            self.assertEqual(self.picks(IDS16)[0], 200); n += 1
            self.assertEqual(self.cmd('sig.deal', seed=11)[0], 200); n += 1
            self.assertEqual(self.cmd('sig.flip', id=4)[0], 200); n += 1
            self.assertEqual(self.cmd('sig.done', id=4)[0], 200); n += 1
            self.assertEqual(self.cmd('sig.lift', on=True)[0], 200); n += 1
            self.assertEqual(self.cmd('sig.flip', id=99)[0], 404)                         # 실패는 쪽지가 없다
            self.assertEqual(self.cmd('sig.shuffle', seed=12)[0], 200); n += 1
            self.assertEqual(self.cmd('sig.timer', action='START')[0], 200); n += 1
            for _ in range(n):
                msgs.append(ov.receive_text())
                cmsgs.append(ct.receive_text())
            ov.send_json({'t': 'resync'})
            msgs.append(ov.receive_text())
        # 한 번이라도 열렸던 카드는 4번 하나 — 그때 그 자리에 있던 시그만 공개됐다
        seen_open = set()
        for raw in msgs:
            m = json.loads(raw)
            sl = m.get('slices') or {}
            self.assertNotIn('siggame_deck', sl)
            for c in (sl.get('siggame') or {}).get('cards') or []:
                if c['state'] == 'HIDDEN':
                    self.assertEqual(c, {'id': c['id'], 'state': 'HIDDEN'})
                else:
                    seen_open.add(c['title'])
        self.assertEqual(len(seen_open), 1)
        secret_titles = {s['title'] for s in SIGS} - seen_open
        secret_imgs = {s['image_url'] for s in SIGS if s['title'] not in seen_open}
        blob = '\n'.join(msgs)
        for t in secret_titles | secret_imgs:
            self.assertNotIn(t, blob)
        # ⭐ 조종실(로그인)도 카드 앞면 조각을 안 받는다(옛 것과 같다 — '사장님도 모르는 편이 공정')
        self.assertFalse(any('siggame_deck' in (json.loads(x).get('slices') or {}) for x in cmsgs))

    def test_http_state(self):
        self.start()
        self.cmd('sig.flip', id=2)
        open_title = next(c for c in self.deck()['cards'] if c['id'] == 2)['title']
        pub = json.dumps(self.c.get('/api/state').json(), ensure_ascii=False)
        for s in SIGS:
            if s['title'] != open_title:
                self.assertNotIn(s['title'], pub)
                self.assertNotIn(s['image_url'], pub)
        self.assertIn(open_title, pub)
        # 로그인한 화면도 공개 조각 자체는 가려져 있다(속은 비공개 조각에만)
        g = self.game()
        self.assertTrue(all(c == {'id': c['id'], 'state': 'HIDDEN'} for c in g['cards'] if c['id'] != 2))


if __name__ == '__main__':
    unittest.main()
