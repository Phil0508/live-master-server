# -*- coding: utf-8 -*-
"""🧪🎓 화면 테스트 · 연습 모드(10-19) — 화면 테스트는 아무것도 안 바꾼다 · 연습은 끝나면 흔적이 없다 · 진짜 후원은 잃지 않는다.

돌리기(저장소 루트에서): python -m unittest v2.tests.test_practice
"""
import random
import time

from v2.server.domain import donor_memory as dm
from v2.server.domain import practice as pr
from v2.tests.test_flow import Base, H


class PracticeBase(Base):
    def db(self):
        return self.c.app.state.store.db

    def post_test(self, **body):
        r = self.c.post('/api/donation/test', json=body, headers=H)
        return r.status_code, r.json()

    def counts(self):
        db = self.db()
        q = lambda s: db.execute(s).fetchone()[0]
        out = {t: q('SELECT COUNT(*) FROM %s' % t) for t in ('donations', 'score_log', 'donor_memory', 'alias_memory')}
        for t in ('answer_log', 'donor_person', 'donor_alias'):
            try:
                out[t] = q('SELECT COUNT(*) FROM %s' % t)
            except Exception:
                out[t] = 0
        return out


class ScreenTest(PracticeBase):
    def test_screen_test_touches_nothing(self):
        before, s0 = self.counts(), self.st()
        c, r = self.post_test(mode='screen', name='테스트별빛', amount=50000, message='화면만', title={'name': '다이아'}, level=7, via='toon')
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertEqual(s['popup']['donation']['amount'], 50000)              # 방송판엔 진짜처럼
        self.assertEqual(s['queue']['items'][-1]['title'], '대박')             # 시그니처도
        self.assertEqual(s['pending'], s0['pending'])                         # 대기함 그대로
        self.assertEqual(s['tallies']['donors'], s0['tallies']['donors'])     # 순위 그대로
        self.assertEqual(s['tallies']['best'], s0['tallies']['best'])
        after = self.counts()
        self.assertEqual(after['donations'], before['donations'] + 1)          # 'display' 줄 하나만
        row = self.db().execute("SELECT source, status FROM donations ORDER BY at DESC LIMIT 1").fetchone()
        self.assertEqual((row['source'], row['status']), ('test_page', 'display'))
        for k in ('score_log', 'donor_memory', 'answer_log', 'donor_person'):
            self.assertEqual(after[k], before[k], k)

    def test_small_goes_to_band_and_bundle_count(self):
        c, r = self.post_test(mode='screen', name='소액', amount=5000, message='띵동')
        self.assertEqual(c, 200, r)
        self.assertTrue(self.st()['popup']['donation'].get('display_only'))
        c, r = self.post_test(mode='screen', name='묶음', amount=50000, count=3)
        self.assertEqual((c, len(r['ids'])), (200, 3))

    def test_needs_login_and_practice_mode_needs_practice(self):
        r = self.c.post('/api/donation/test', json={'mode': 'screen', 'name': 'x', 'amount': 1000})
        self.assertEqual(r.status_code, 401)
        c, r = self.post_test(mode='practice', name='x', amount=10000)
        self.assertEqual(c, 409)


class Practice(PracticeBase):
    def setUp(self):
        super().setUp()
        # 지난 방송: 진짜 후원 하나 · 배정 하나 → 끝
        _, r = self.don('단골', 30000, 'toon_old1', '하율 화이팅')
        pid = self.st()['pending'][0]['id']
        self.cmd('pending.assign', id=pid, name='하율')
        self.cmd('session.end')

    def test_live_blocks_start(self):
        self.cmd('session.start', names=['하율', '서아'])
        c, r = self.cmd('practice.start', names=['하율', '서아'])
        self.assertEqual(c, 409, r)

    def test_practice_leaves_no_trace_and_keeps_real(self):
        s0, n0 = self.st(), self.counts()
        mem0 = [dict(x) for x in self.db().execute('SELECT * FROM donor_memory ORDER BY id')]
        c, r = self.cmd('practice.start', names=['하율', '서아', '채원'])
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertTrue(s['practice']['on'])
        self.assertTrue(s['session']['live'])
        self.assertEqual(self.c.get('/api/deploy/ok').status_code, 409)       # 연습 중 배포 잠금
        ids = []
        for i, (nm, amt) in enumerate([('단골', 10000), ('새얼굴', 20000), ('별빛', 50000), ('구름', 10000)]):
            c, r = self.post_test(mode='practice', name=nm, amount=amt, message='하율 화이팅', expect='하율')
            self.assertEqual(c, 200, r)
            ids += r['ids']
        pend = {x['id']: x for x in self.st()['pending']}
        self.assertTrue(all(pend[i].get('practice') for i in ids))
        self.cmd('pending.assign', id=ids[0], name='하율')
        self.cmd('pending.assign', id=ids[1], name='서아')
        self.cmd('pending.assign', id=ids[2], name='하율')
        self.cmd('pending.ignore', id=ids[3])
        self.cmd('score.undo')                                                 # 마지막 배정 되돌리기
        self.cmd('pending.assign', id=ids[2], name='채원')
        # 연습 중 진짜 후원 — 들어오되 손댈 수 없다
        c, r = self.don('진짜손님', 30000, 'toon_real1', '서아 사랑해')
        self.assertEqual(c, 200, r)
        real = next(x for x in self.st()['pending'] if not x.get('practice'))
        c, r = self.cmd('pending.assign', id=real['id'], name='서아')
        self.assertEqual(c, 409, r)
        self.assertEqual(self.st()['practice']['real'], 1)
        # 아무것도 배우지 않았다
        mem1 = [dict(x) for x in self.db().execute('SELECT * FROM donor_memory ORDER BY id')]
        self.assertEqual(mem1, mem0)
        c, r = self.cmd('practice.end')
        self.assertEqual(c, 200, r)
        sm = r['summary']
        self.assertEqual((sm['cards'], sm['given'], sm['ignored'], sm['checked'], sm['correct']), (4, 3, 1, 3, 1))
        s = self.st()
        self.assertFalse(s['practice']['on'])
        self.assertFalse(s['session']['live'])
        self.assertEqual(s['session']['id'], s0['session']['id'])
        self.assertEqual(s['players'], s0['players'])
        self.assertEqual([x['id'] for x in s['pending']], [real['id']])        # 진짜 카드만 남았다
        self.assertEqual(s['tallies']['donors'].get('진짜손', {}).get('total'), 30000)        # norm_donor 가 끝 '님' 을 뗀다
        self.assertEqual(s['tallies']['donors'].get('단골'), s0['tallies']['donors'].get('단골'))
        self.assertTrue(any(x.get('don_ids') == [real['id']] for x in s['queue']['items']))   # 진짜 시그니처도
        n1 = self.counts()
        self.assertEqual(n1['donations'], n0['donations'] + 1)                 # 진짜 줄 하나만 더
        self.assertEqual(n1['score_log'], n0['score_log'])
        for k in ('donor_memory', 'alias_memory', 'answer_log'):
            self.assertEqual(n1[k], n0[k], k)
        for k in ('donor_person', 'donor_alias'):                             # 진짜 손님 카드 하나만 — 연습 이름은 카드가 없다
            self.assertEqual(n1[k], n0[k] + 1, k)
        names = {r[0] for r in self.db().execute('SELECT name FROM donor_alias')}
        self.assertFalse(names & {'새얼굴', '별빛', '구름'})
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM donations WHERE source IN ('practice', 'test_page')").fetchone()[0], 0)
        row = self.db().execute("SELECT session FROM donations WHERE tx_id = 'toon_real1'").fetchone()
        self.assertEqual(row['session'], s0['session']['id'])
        self.assertEqual(self.c.get('/api/deploy/ok').status_code, 200)
        # 연습 뒤 진짜 카드는 이제 줄 수 있다
        c, r = self.cmd('pending.assign', id=real['id'], name='서아')
        self.assertNotIn('연습', r.get('error', ''))   # 연습 막기는 풀렸다(방송 중이 아니라 점수판에 선수가 없어 다른 까닭으로만 거절)

    def test_end_survives_restart(self):
        self.cmd('practice.start', names=['하율', '서아'])
        self.post_test(mode='practice', name='a', amount=10000)
        app = self.c.app
        from fastapi.testclient import TestClient
        from v2.server.app import create_app
        from v2.tests.test_flow import PW, SECRET, SIGS
        import os
        app.state.store.close()
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET, sig_fetch=lambda: SIGS))
        self.assertTrue(self.st()['practice']['on'])
        c, r = self.cmd('practice.end')
        self.assertEqual(c, 200, r)
        self.assertFalse(self.st()['session']['live'])

    def test_bad_names_leave_nothing(self):
        c, r = self.cmd('practice.start', names=[])
        self.assertEqual(c, 400, r)
        self.assertFalse(self.st()['practice'].get('on'))
        self.assertIsNone(self.c.app.state.store.last_restore_point('practice'))


class Samples(PracticeBase):
    def test_samples_have_expect_from_history(self):
        store = self.c.app.state.store
        for i in range(6):
            dm.remember_assignment(store, '하율단골', '하율', 1, '', ref='h%d' % i, at=1000 + i)
            dm.remember_assignment(store, '서아단골', '서아', 1, '', ref='s%d' % i, at=1000 + i)
        items = pr.make_samples(self.db(), 40, ['하율', '서아', '채원'], rng=random.Random(3))
        self.assertEqual(len(items), 20)                                       # 한 번에 20개까지
        for it in items:
            self.assertGreater(it['amount'], 0)
            if it['name'] == '하율단골' and not any(p in it['message'] for p in ('서아', '채원')):
                self.assertEqual(it['expect'], '하율')
            for p in ('하율', '서아', '채원'):
                if p in it['message']:
                    self.assertEqual(it['expect'], p)
        r = self.c.get('/api/practice/sample?n=3', headers=H)
        self.assertEqual((r.status_code, len(r.json()['items'])), (200, 3))
        self.assertEqual(self.c.get('/api/practice/sample').status_code, 401)
