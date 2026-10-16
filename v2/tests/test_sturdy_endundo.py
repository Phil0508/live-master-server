# -*- coding: utf-8 -*-
"""⏪ [방송 끝] 되살리기 (sturdy 10-17) — 실수로 방송을 끝냈을 때 조종실 단추 한 번으로 끝내기 직전으로.

옛 것: 방송 종료 때 '방송 종료 자동 백업' 복구 지점 → 타임머신 [복구]. v2: session.end 가 바꾼 조각의 전 · 뒤 값을 장부
restore_points 에 같은 묶음으로 적고, session.undo_end 가 되살린다. 장부 표(donations · score_log)는 손대지 않는다.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain.endundo import UNDO_MAX_SEC, merge3, merge_tallies

PW, SECRET = 'testpw', 'testsecret-0123456789'
H = {'Authorization': 'Bearer ' + SECRET}
SIGS = [{'id': 1, 'amount': 10300, 'title': '사쿠란보', 'image_url': 'a.png', 'sound_url': 'a.mp3', 'duration': 8},
        {'id': 2, 'amount': 20005, 'title': '뿅뿅', 'image_url': 'b.png', 'sound_url': 'b.mp3', 'duration': 9},
        {'id': 3, 'amount': 50000, 'title': '대박', 'image_url': 'c.png', 'sound_url': 'c.mp3', 'duration': 12}]
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAMES = ['하율', '서아', '채원']


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2undo_')
        self.db = os.path.join(self.dir, 'lm2.db')
        self.c = self.app()

    def app(self):
        return TestClient(create_app(db_path=self.db, password=PW, secret=SECRET, sig_fetch=lambda: SIGS))

    def tearDown(self):
        try:
            self.c.app.state.store.close()
        except Exception:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    @property
    def store(self):
        return self.c.app.state.store

    def cmd(self, t, **data):
        r = self.c.post('/api/cmd', json={'type': t, 'data': data}, headers=H)
        return r.status_code, r.json()

    def ok(self, t, **data):
        code, r = self.cmd(t, **data)
        self.assertEqual(code, 200, (t, r))
        return r

    def st(self):
        return self.c.get('/api/state', headers=H).json()['slices']

    def don(self, name, amount, tx):
        r = self.c.post('/api/donation', json={'name': name, 'amount': amount, 'message': '', 'tx_id': tx}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def ledger(self):
        db = self.store.db
        return ([dict(r) for r in db.execute('SELECT * FROM donations ORDER BY id')],
                [dict(r) for r in db.execute('SELECT * FROM score_log ORDER BY id')])

    def pending_ids(self, s=None):
        return [x['id'] for x in (s or self.st())['pending']]

    def score(self, name, s=None):
        return next(p for p in (s or self.st())['players']['list'] if p['name'] == name)

    def busy_broadcast(self):
        """점수 · 대기함 · 시그니처 대기줄 · 기록 · 목표 보정이 쌓인 방송."""
        self.ok('session.start', names=NAMES)
        self.don('별빛', 30000, 'toon_a1')                 # 시그니처 대기줄에 들어간다
        pid = self.pending_ids()[0]
        self.ok('pending.assign', id=pid, name='하율')
        self.don('달빛', 20005, 'toon_a2')                 # 대기함에 남는다
        self.ok('score.add', name='서아', delta=3)
        self.ok('goal.set', target=100, offset=7)


class Undo(Base):
    def test_undo_brings_back_everything_and_ledger_is_untouched(self):
        self.busy_broadcast()
        before = self.st()
        led0 = self.ledger()
        self.assertTrue(before['queue']['items'] and before['pending'] and before['logs'])
        self.ok('session.end')
        mid = self.st()
        self.assertFalse(mid['session']['live'])
        self.assertEqual((mid['players']['list'], mid['pending'], mid['queue']['items'], mid['logs']), ([], [], [], []))
        self.assertEqual(self.ledger(), led0, '방송 끝이 장부 표를 바꿨다')
        e = mid['endundo']
        self.assertTrue(e['ready'])
        self.assertEqual((e['players'], e['pending'], e['score_total']), (3, 1, before['players']['list'][0]['score'] + 3))
        self.assertAlmostEqual(e['until'] - e['at'], UNDO_MAX_SEC)
        self.assertNotIn('endundo', self.c.get('/api/state').json()['slices'], '되살리기 요약은 비공개 조각이다')
        self.assertEqual(self.c.get('/api/deploy/ok').status_code, 200)

        r = self.ok('session.undo_end')
        self.assertIn('players', r['restored'])
        self.assertEqual(r['merged'], [])
        after = self.st()
        for k in before:
            if k in ('popup', 'endundo'):
                continue
            self.assertEqual(after[k], before[k], '%s 조각이 끝내기 전과 다르다' % k)
        self.assertFalse(after['endundo']['ready'])
        self.assertEqual(self.ledger(), led0, '되살리기가 장부 표를 바꿨다')
        self.assertEqual(self.c.get('/api/deploy/ok').status_code, 409, '다시 방송 중 — 배포 잠금')
        # 되살린 뒤에도 같은 회차라 되돌리기(score.undo)가 이어진다
        self.ok('score.undo')
        self.assertEqual(self.score('서아')['score'], 0)

    def test_popup_is_not_replayed(self):
        self.busy_broadcast()
        self.ok('session.end')
        self.ok('session.undo_end')
        p = self.st()['popup']
        self.assertIsNone(p.get('donation'), '지난 후원 알림이 방송판에 다시 뜬다')

    def test_donations_after_end_are_kept(self):
        self.ok('session.start', names=NAMES)
        self.don('별빛', 30000, 'toon_b1')
        self.don('조각', 5000, 'toon_b0')
        pre_ids = self.pending_ids()
        self.ok('session.end')
        self.don('달빛', 20000, 'toon_b2')                 # 끝낸 뒤에도 리스너는 보낸다
        self.don('별빛', 10000, 'toon_b3')
        mid_ids = self.pending_ids()
        r = self.ok('session.undo_end')
        self.assertIn('pending', r['merged'])
        self.assertIn('tallies', r['merged'])
        s = self.st()
        self.assertEqual(self.pending_ids(s), pre_ids + mid_ids, '끝낸 뒤 들어온 후원 카드가 사라졌다')
        d = s['tallies']['donors']
        self.assertEqual((d['별빛']['total'], d['별빛']['count']), (40000, 2))
        self.assertEqual((d['달빛']['total'], d['달빛']['count']), (20000, 1))
        self.assertEqual(s['tallies']['best']['amount'], 30000)
        self.assertEqual(s['tallies']['vip']['별빛']['rank'], 1)
        self.assertTrue(s['session']['live'])

    def test_rules(self):
        code, r = self.cmd('session.undo_end')
        self.assertEqual(code, 404, r)                     # 끝낸 적이 없다
        self.ok('session.start', names=NAMES)
        code, r = self.cmd('session.undo_end')
        self.assertEqual(code, 409, r)                     # 방송 중
        self.ok('score.add', name='하율', delta=1)
        self.ok('session.end')
        self.ok('session.undo_end')
        code, r = self.cmd('session.undo_end')
        self.assertEqual(code, 409, r)                     # 두 번 눌러도 한 번(이미 방송 중)
        self.assertEqual(self.score('하율')['score'], 1)
        # 또 끝내고 또 되살릴 수 있다(새 지점)
        self.ok('session.end')
        self.ok('session.undo_end')
        self.assertEqual(self.score('하율')['score'], 1)
        # 끝낸 뒤 새 방송을 시작했으면 지난 방송은 안 살린다
        self.ok('session.end')
        self.ok('session.start', names=['새사람'])
        self.assertFalse(self.st()['endundo']['ready'])
        code, r = self.cmd('session.undo_end')
        self.assertEqual(code, 409, r)
        self.ok('session.end')
        self.ok('session.undo_end')                        # 마지막에 끝낸 '새사람' 방송이 돌아온다
        self.assertEqual([p['name'] for p in self.st()['players']['list']], ['새사람'])

    def test_used_point_and_failed_end_leave_nothing(self):
        n0 = self.store.db.execute('SELECT COUNT(*) FROM restore_points').fetchone()[0]
        code, _ = self.cmd('session.end')                   # 방송 중이 아니다 — 실패한 끝내기는 지점을 안 남긴다
        self.assertEqual(code, 409)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM restore_points').fetchone()[0], n0)
        self.ok('session.start', names=NAMES)
        self.ok('session.end')
        self.ok('session.undo_end')
        self.ok('session.end')
        # 장부에서 직접 마지막 지점을 '다 쓴 것' 으로 만들면 되살리지 않는다
        self.store.db.execute('UPDATE restore_points SET used_at = 1 WHERE id = (SELECT MAX(id) FROM restore_points)')
        code, r = self.cmd('session.undo_end')
        self.assertEqual(code, 404, r)

    def test_too_old(self):
        self.busy_broadcast()
        self.ok('session.end')
        self.store.db.execute('UPDATE restore_points SET at = at - ?', (UNDO_MAX_SEC + 60,))
        code, r = self.cmd('session.undo_end')
        self.assertEqual(code, 409, r)
        self.assertIn('시간', r['error'])
        self.assertFalse(self.st()['session']['live'])

    def test_end_screen_is_lowered(self):
        self.busy_broadcast()
        self.ok('session.end')
        self.ok('screen.set', mode='end', title='오늘도 감사')
        self.ok('session.undo_end')
        sc = self.st()['screen']
        self.assertEqual(sc['mode'], 'off')
        self.assertIsNone(sc['snap'])
        self.assertEqual(sc['title'], '오늘도 감사')       # 끝낸 뒤 고친 글자는 그대로(다음에 쓸 수 있게)

    def test_rearms_game_timers(self):
        self.ok('session.start', names=NAMES)
        self.ok('roulette.spin')
        self.ok('roulette.stop', seed=3)
        self.ok('session.end')                              # 룰렛이 서는 중에 끝냈다
        self.store.db.execute('DELETE FROM timers')         # 그사이 헛돈 예약(끝난 판의 done)은 지났다고 치자
        self.ok('session.undo_end')
        s = self.st()
        self.assertEqual((s['roulette']['phase'], s['show']['stage']), ('stopping', 'roulette'))
        rows = self.store.timers()
        self.assertEqual([(t['type'], t['data']) for t in rows], [('roulette.done', {'round': s['roulette']['round']})])

    def test_survives_restart(self):
        self.busy_broadcast()
        before = self.st()
        self.ok('session.end')
        self.c.app.state.store.close()
        self.c = self.app()                                 # 끝낸 뒤 서버가 다시 켜졌다
        self.ok('session.undo_end')
        after = self.st()
        self.assertEqual(after['players'], before['players'])
        self.assertEqual(after['pending'], before['pending'])


class Review(Base):
    """검토(10-17) — 보고서에 있었지만 검사가 따로 안 보던 것."""

    def test_undo_needs_login(self):
        """로그인 없는 화면(방송판 · 아무나)은 방송을 다시 '방송 중' 으로 못 돌린다 — HTTP · WS 둘 다."""
        self.busy_broadcast()
        self.ok('session.end')
        r = self.c.post('/api/cmd', json={'type': 'session.undo_end', 'data': {}, 'cid': 'c-anon-0001'})
        self.assertEqual(r.status_code, 401, r.text)
        with self.c.websocket_connect('/ws?kind=overlay') as ws:
            first = ws.receive_json()                          # 통째(snapshot)
            self.assertFalse(first.get('authed'))
            ws.send_json({'t': 'cmd', 'id': 1, 'type': 'session.undo_end', 'data': {}, 'cid': 'c-anon-0002'})
            while True:
                m = ws.receive_json()
                if m.get('t') == 'result':
                    break
            self.assertFalse(m['ok'])
            self.assertEqual(m['code'], 401)
        s = self.st()
        self.assertFalse(s['session']['live'])
        self.assertTrue(s['endundo']['ready'], '로그인 없는 시도가 지점을 써 버렸다')
        self.ok('session.undo_end')                          # 조종실은 여전히 되살릴 수 있다
        self.assertTrue(self.st()['session']['live'])

    def test_signature_queued_after_end_is_kept(self):
        """끝낸 뒤 시그니처 금액 후원이 와서 대기줄에 들어갔으면, 되살린 뒤 끝내기 전 대기줄 뒤에 이어 붙는다."""
        self.busy_broadcast()
        pre_q = [x['id'] for x in self.st()['queue']['items']]
        self.assertTrue(pre_q)
        self.ok('session.end')
        self.don('햇빛', 50000, 'toon_q1')
        mid_q = [x['id'] for x in self.st()['queue']['items']]
        self.assertTrue([i for i in mid_q if i not in pre_q], '끝낸 뒤 후원이 대기줄에 안 들어갔다(검사가 헛돈다)')
        self.ok('session.undo_end')
        got = [x['id'] for x in self.st()['queue']['items']]
        self.assertEqual(got, pre_q + [i for i in mid_q if i not in pre_q], '끝낸 뒤 들어온 시그니처가 대기줄에서 사라졌다')

    def test_restore_point_never_reaches_overlay(self):
        """endundo 조각은 로그인 없는 화면의 통째(snapshot) · 바뀐 조각(patch) 어디에도 안 실린다."""
        with self.c.websocket_connect('/ws?kind=overlay') as ws:
            snap = ws.receive_json()
            self.assertNotIn('endundo', snap.get('slices') or {})
            self.busy_broadcast()
            self.ok('session.end')
            self.ok('session.undo_end')
            ws.send_json({'t': 'resync'})
            seen = 0
            while True:
                m = ws.receive_json()
                seen += 1
                self.assertNotIn('endundo', m.get('slices') or {}, m.get('t'))
                if m.get('t') == 'snapshot':
                    break
            self.assertGreater(seen, 3, '바뀐 조각 쪽지를 하나도 못 봤다(검사가 헛돈다)')


class Merge(unittest.TestCase):
    def test_merge3(self):
        self.assertEqual(merge3({'a': 1}, {'a': 0}, {'a': 0}), {'a': 1})              # 끝낸 뒤 그대로 → 끝내기 전
        self.assertEqual(merge3({'a': 1, 'b': 1}, {'a': 0, 'b': 1}, {'a': 0, 'b': 2}), {'a': 1, 'b': 2})   # 칸마다
        self.assertEqual(merge3('x', 'y', 'z'), 'z')                                      # 둘 다 바뀐 글자 — 나중 것
        self.assertEqual(merge3([{'id': 1}], [], [{'id': 2}]), [{'id': 1}, {'id': 2}])   # 이어 붙이기
        self.assertEqual(merge3([{'id': 1}, {'id': 2}], [{'id': 2}], []), [{'id': 1}])  # 끝낸 뒤 뺀 것은 뺀다
        self.assertEqual(merge3([1, 2], [], [3]), [1, 2, 3])
        self.assertEqual(merge3({'a': {'x': 1}}, {}, {'b': 2}), {'a': {'x': 1}, 'b': 2})

    def test_merge_tallies(self):
        pre = {'donors': {'a': {'name': 'a', 'total': 100, 'count': 1}}, 'best': {'name': 'a', 'amount': 100},
               'notice_donors': [{'name': 'z', 'amount': 1, 'ts': 1}], 'sigs': {'1': {'title': 't', 'count': 2, 'donors': {'a': 2}}}}
        post = {'donors': {}, 'best': None, 'notice_donors': [], 'sigs': {}}
        cur = {'donors': {'a': {'name': 'a님', 'total': 50, 'count': 1}, 'b': {'name': 'b', 'total': 30, 'count': 1}},
               'best': {'name': 'a님', 'amount': 50}, 'notice_donors': [{'name': 'y', 'amount': 2, 'ts': 2}],
               'sigs': {'1': {'title': 't', 'count': 1, 'donors': {'b': 1}}}}
        out = merge_tallies(pre, post, cur)
        self.assertEqual(out['donors']['a'], {'name': 'a님', 'total': 150, 'count': 2})
        self.assertEqual(out['donors']['b']['total'], 30)
        self.assertEqual(out['best']['amount'], 100)
        self.assertEqual([x['name'] for x in out['notice_donors']], ['z', 'y'])
        self.assertEqual(out['sigs']['1']['count'], 3)
        self.assertEqual(out['sigs']['1']['donors'], {'a': 2, 'b': 1})


NODE_VIEW = r"""
import { pathToFileURL } from 'node:url';
const { endUndoView } = await import(pathToFileURL(process.argv[1]).href);
const now = 1800000000;
const e = { ready: true, at: now - 300, until: now - 300 + 43200, players: 3, score_total: 12, pending: 2, queue: 1 };
const out = {
    hidden_not_ready: !endUndoView({ ready: false, at: now }, now).show,
    hidden_none: !endUndoView(null, now).show,
    hidden_after_until: !endUndoView(e, e.until + 1).show,
    shown: endUndoView(e, now).show,
    detail: endUndoView(e, now).detail,
    body: endUndoView(e, now).body,
};
console.log(JSON.stringify(out));
"""


class ControllerView(unittest.TestCase):
    def test_end_undo_view(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node 가 없습니다')
        js = os.path.join(ROOT, 'v2', 'web', 'controller', 'js', 'endundo.js')
        r = subprocess.run([node, '--input-type=module', '-e', NODE_VIEW, js], capture_output=True, text=True,
                           encoding='utf-8', timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(out['hidden_not_ready'] and out['hidden_none'] and out['hidden_after_until'] and out['shown'], out)
        for part in ('5분 전', '플레이어 3명', '점수 합 12', '대기함 2건', '시그니처 대기줄 1개'):
            self.assertIn(part, out['detail'])
        self.assertIn('장부', out['body'])


if __name__ == '__main__':
    unittest.main()
