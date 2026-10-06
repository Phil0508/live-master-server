# -*- coding: utf-8 -*-
"""v2 모금함 · 시작/끝 화면."""
import unittest

from v2.tests.test_flow import Base, H


class Extras(Base):
    def test_jar(self):
        self.cmd('fundjar.set', enabled=True, seed=100000)
        self.don('별빛', 30000, 'toon_j1')
        pid = self.st()['pending'][0]['id']
        self.cmd('pending.to_jar', id=pid)
        s = self.st()
        self.assertEqual(s['fundjar']['score'], 30000)                 # 원 그대로
        self.assertEqual(s['pending'], [])
        self.cmd('score.undo')
        s = self.st()
        self.assertEqual(s['fundjar']['score'], 0)
        self.assertEqual([x['id'] for x in s['pending']], [pid])      # 대기함으로 돌아온다
        self.cmd('fundjar.add', delta=5000)
        self.cmd('session.end')
        j = self.st()['fundjar']
        self.assertEqual((j['score'], j['seed']), (0, 100000))         # 종잣돈은 그대로

    def test_screen_and_snapshot(self):
        self.cmd('screen.set', mode='start', minutes=5, title='오늘은 추석 특집', names=['하율', '하율', '서아'])
        s = self.st()['screen']
        self.assertEqual((s['mode'], s['names']), ('start', ['하율', '서아']))
        self.assertGreater(s['start_at'], 0)
        self.cmd('score.add', name='채원', delta=4)
        self.don('익명', 20000, 'toon_k1')
        self.don('별빛', 50000, 'toon_k2')
        self.cmd('screen.set', mode='end', title='고마워요')
        self.cmd('session.end')
        snap = self.st()['screen']['snap']
        self.assertEqual(snap['members'][0]['name'], '채원')            # 끝내기 전 기록이 얼어 있다
        self.assertEqual([d['name'] for d in snap['donors']], ['별빛'])  # 익명은 기본으로 뺀다
        self.assertEqual(snap['best']['amount'], 50000)
        self.cmd('session.start', names=['가'])
        self.assertIsNone(self.st()['screen']['snap'])
        self.assertEqual(self.st()['screen']['mode'], 'off')            # 끝 화면은 새 방송 시작 때 내린다


if __name__ == '__main__':
    unittest.main()


class Ledger(Base):
    def test_ledger_survives_end(self):
        self.don('별빛', 30000, 'toon_l1')
        self.don('달빛', 20000, 'toon_l2')
        sid = self.st()['session']['id']
        pid = self.st()['pending'][0]['id']
        self.cmd('pending.assign', id=pid, name='하율')
        self.cmd('session.end')
        r = self.c.get('/api/ledger?session=' + sid, headers=H).json()
        self.assertEqual((r['count'], r['total']), (2, 50000))         # 끝내도 장부는 남는다
        self.assertEqual({x['status'] for x in r['rows']}, {'assigned', 'pending'})
        s = self.c.get('/api/sessions', headers=H).json()['sessions']
        self.assertEqual(s[0]['session'], sid)
        sc = self.c.get('/api/scores?session=' + sid, headers=H).json()['rows']
        self.assertEqual(sum(r['delta'] for r in sc if r['field'] == 'score'), 3)
        self.assertEqual(self.c.get('/api/ledger').status_code, 401)


class JarSwitch(Base):
    def test_one_switch(self):
        self.cmd('fundjar.set', enabled=True)
        self.assertTrue(self.st()['show']['hud']['fundjar'])
        self.cmd('show.hud', key='fundjar', on=False)
        self.assertFalse(self.st()['fundjar']['enabled'])


class LedgerGaps(Base):
    """장부 도우미가 찾은 구멍 — 후원 없는 방송 · 원래 이름 · 대소문자 · 점검 실측."""

    def test_quiet_session_listed(self):
        sid = self.st()['session']['id']
        self.cmd('session.end')
        s = self.c.get('/api/sessions', headers=H).json()['sessions']
        row = [r for r in s if r['session'] == sid][0]
        self.assertEqual((row['n'], row['total']), (0, 0))              # 후원 0건이어도 나온다
        self.assertTrue(row['started_at'] and row['ended_at'])
        self.assertFalse(row['current'])

    def test_scores_only_session(self):
        sid = self.st()['session']['id']
        self.cmd('score.add', name='채원', delta=2)
        row = [r for r in self.c.get('/api/sessions', headers=H).json()['sessions'] if r['session'] == sid][0]
        self.assertEqual((row['n'], row['scores']), (0, 2))             # 점수 + 기여도 두 줄
        self.assertTrue(row['current'])

    def test_exclude_keeps_shown_name(self):
        self.don('Star님', 30000, 'web_x1')       # 옛 경로는 '님' 을 뗀다 → 'Star'
        self.cmd('donor.exclude', name='Star')
        r = self.c.get('/api/state', headers=H).json()['slices']['donor_rules']
        self.assertEqual(r['names'], {'Star': 'Star'})
        self.cmd('donor.include', name='Star')
        r = self.c.get('/api/state', headers=H).json()['slices']['donor_rules']
        self.assertEqual((r['excluded'], r['names']), ([], {}))

    def test_ledger_search_ignores_case(self):
        self.don('StarLight', 10000, 'toon_c1')
        self.don('달빛', 20000, 'toon_c2')
        r = self.c.get('/api/ledger?q=starl', headers=H).json()
        self.assertEqual([x['name'] for x in r['rows']], ['StarLight'])

    def test_preflight_storage_probe(self):
        p = self.c.get('/api/preflight', headers=H).json()
        self.assertTrue(p['storage']['ok'])
        self.assertIsInstance(p['storage']['ms'], float)
        self.assertIn('overlay_obs', p['screens'])


class Device(unittest.TestCase):
    def test_device(self):
        from v2.server.hub import device
        self.assertEqual(device('Mozilla/5.0 (Windows NT 10.0) OBS/30.1.2'), 'obs')
        self.assertEqual(device('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)'), 'iphone')
        self.assertEqual(device('', obs_hint=True), 'obs')
        self.assertEqual(device(None), 'other')


class GoalWin(Base):
    def test_celebrate_and_dismiss(self):
        self.cmd('goal.set', target=3)
        self.cmd('score.add', name='하율', delta=3)
        self.cmd('goal.dismiss')
        s = self.st()
        self.assertEqual(s['goal']['done'], 3)
        self.assertFalse(s['popup'].get('goal'))                    # 닫기는 연출을 안 내보낸다
        self.cmd('goal.set', target=5)
        self.assertNotEqual(self.st()['goal']['done'], 5)           # 목표를 바꾸면 다시 뜬다
        self.cmd('score.add', name='하율', delta=2)
        self.cmd('goal.celebrate')
        s = self.st()
        self.assertEqual((s['goal']['done'], s['popup']['goal']['target']), (5, 5))
        self.cmd('session.end')
        self.assertEqual(self.st()['goal']['done'], 0)
