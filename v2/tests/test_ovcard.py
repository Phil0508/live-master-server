# -*- coding: utf-8 -*-
"""🚦 방송판 가운데 차례 · 다시 붙은 방송판의 지난 카드 · 출연진 전광판 시작 신호(10-17 v2ov/card).

① 시그니처가 가운데 떠 있는 동안 온 일반 후원 카드가 시그 카드 밑에 깔리던 것 — 카드가 기다린다.
   시그니처는 떠 있는 카드만 기다리고, 카드 쪽은 새 카드를 꺼내기 전에 기다리는 시그에 차례를 넘긴다(교착 · 밀림 없음).
   규칙은 v2/web/overlay/turns.js(node 로 본다: js/ovcard_check.mjs), 위젯이 그 규칙을 쓰는지는 구조로 본다.
⑧ 끊긴 사이 들어온 카드 — 서버 popup.recent(최근 8개, id · 가림 적용)에서 방송판이 안 본 것 · 30초 안의 것만 차례로.
   popup.donation 은 그대로(조종실 등 옛 화면이 읽는다).
⑥ 출연진 전광판(?only=sig)이 방송판보다 먼저 뜨던 것 — 방송판이 reaction.started(로그인 없이)로 '지금 트는 것' 을 알리고
   전광판은 그것을 따른다. 신호가 없으면 멈춤 · play_after(서버 시계)를 지키고 잠시 기다린 뒤.
"""
import os
import re
import shutil
import subprocess
import unittest

from v2.server.domain import players as pl
from v2.tests.test_flow import Base, H

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
OV = os.path.join(ROOT, 'v2', 'web', 'overlay')


def src(*p):
    with open(os.path.join(OV, *p), encoding='utf-8') as f:
        return f.read()


@unittest.skipUnless(shutil.which('node'), 'node 가 없으면 건너뛴다')
class JsRules(unittest.TestCase):
    def test_turn_rules(self):
        p = subprocess.run(['node', os.path.join(HERE, 'js', 'ovcard_check.mjs')], capture_output=True, text=True,
                           encoding='utf-8', timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(p.stdout.strip().startswith('ok '), p.stdout)


class Structure(unittest.TestCase):
    """위젯이 차례 규칙을 실제로 쓰는가 — 화면 없이 글자로 본다."""

    def test_donation_waits_for_sig_center(self):
        s = src('widgets', 'donation.js')
        self.assertIn("from '../turns.js'", s)
        self.assertIn("opts.stage.use('sigCenter')", s)
        self.assertRegex(s, r"cardTurn\(\{ busy, queued: queue\.length, sigCenter")
        self.assertIn('s.sig.kick()', s)                                  # 기다리는 시그에 먼저 넘긴다
        self.assertRegex(s, r"busy\(\) \{ return busy; \}")              # 줄 선 카드는 시그를 막지 않는다(교착 · 밀림 방지)
        self.assertIn('sig.onFree(', s)
        self.assertIn('pendingCards(', s)                                 # 다시 붙으면 지난 카드 여러 개
        self.assertIn('pop.recent', s)
        # 시그니처가 부탁한 카드(rq)는 줄 맨 앞
        self.assertIn('queue.splice(i, 0, { d, done })', s)

    def test_signature_provides_center_and_uses_server_clock(self):
        s = src('widgets', 'signature.js')
        self.assertIn("opts.stage.provide('sigCenter'", s)
        for k in ('center: centerBusy', 'wants: wantsTurn', 'kick()', 'onFree(fn)'):
            self.assertIn(k, s)
        self.assertNotRegex(s, r"play_after\)\s*\|\|\s*0\)\s*-\s*Date\.now\(\)")   # 서버 시계로(lm.serverNow)
        self.assertRegex(s, r"play_after\)\s*\|\|\s*0\)\s*-\s*now\(\)")
        self.assertIn('lm.serverNow', s)
        # 가운데를 비울 때 · 끝날 때 · 끊을 때 카드를 놓아준다
        self.assertGreaterEqual(s.count('centerFreed()'), 3)
        # 시작 신호 — 담당 창만 · 미리보기는 안 보낸다
        m = re.search(r"function sendStarted\(it\) \{(.*?)\n    \}", s, re.S)
        self.assertTrue(m)
        self.assertIn('opts.monitor || !isLeader()', m.group(1))
        self.assertIn("'reaction.started'", m.group(1))

    def test_sigdisp_follows_started(self):
        s = src('widgets', 'sigfx', 'sigdisp.js')
        self.assertIn('sigDispShow(', s)
        self.assertIn('lm.serverNow', s)
        self.assertIn("lm.on('queue', render)", s)


class Recent(Base):
    def pub(self):
        return self.st(auth=False)['popup']

    def test_keeps_last_eight_in_order_and_donation_unchanged(self):
        for i in range(10):
            self.assertEqual(self.don('사람%d' % i, 30000 + i, 'toon_r%d' % i, msg='m%d' % i)[0], 200)
        p = self.st()['popup']
        rec = p['recent']
        self.assertEqual(len(rec), pl.POPUP_RECENT_MAX)
        self.assertEqual([x['name'] for x in rec], ['사람%d' % i for i in range(2, 10)])     # 오래된 순
        self.assertEqual(rec[-1]['id'], p['donation']['id'])
        self.assertTrue(all(x['id'].startswith('don_') and x['at'] > 0 for x in rec))
        self.assertNotIn('sig', p['donation'])                                              # 옛 칸은 그대로
        self.assertEqual(set(p['donation']) - {'donor_title', 'donor_level'}, {'id', 'name', 'amount', 'message', 'at'})

    def test_sig_donation_marked(self):
        self.don('별빛', 10300, 'toon_s1', msg='시그')          # 1만 300원 시그니처
        self.don('달빛', 9000, 'toon_s2', msg='카드')            # 최저 시그 미만 — 시그 없음
        rec = self.pub()['recent']
        self.assertEqual([(x['name'], bool(x.get('sig'))) for x in rec], [('별빛', True), ('달빛', False)])

    def test_display_only_and_console_play_also_recorded(self):
        self.don('작은별', 3000, 'toon_d1', display_only=True)
        self.assertEqual(self.cmd('signature.play', name='콘솔', amount=500, message='x', display=True)[0], 200)
        rec = self.pub()['recent']
        self.assertEqual([(x['name'], x.get('display_only')) for x in rec], [('작은별', True), ('콘솔', True)])

    def test_masked_on_air_raw_for_controller(self):
        self.assertEqual(self.cmd('mask.word.add', word='시발')[0], 200)
        self.don('별빛', 30000, 'toon_k1', msg='연락 010-1234-5678')
        self.don('달빛', 30000, 'toon_k2', msg='나쁜말 시발')
        rec = self.pub()['recent']
        self.assertEqual([x['message'] for x in rec], ['연락 ●●●', '나쁜말 ●●●'])
        self.assertEqual([x['message'] for x in self.st()['popup']['recent']], ['연락 010-1234-5678', '나쁜말 시발'])
        # [가리기] — 지난 카드에서도 통째로
        did = rec[0]['id']
        self.assertEqual(self.cmd('mask.hide', id=did)[0], 200)
        self.assertEqual(self.pub()['recent'][0]['message'], '')

    def test_overlay_socket_gets_masked_recent(self):
        self.assertEqual(self.cmd('mask.word.add', word='시발')[0], 200)
        self.don('별빛', 30000, 'toon_w1', msg='시발 화이팅')
        with self.c.websocket_connect('/ws?kind=overlay') as ov:
            snap = ov.receive_json()
            rec = snap['slices']['popup']['recent']
            self.assertEqual(rec[-1]['message'], '●●● 화이팅')

    def test_replay_encore_hidden_src_not_leaked(self):
        self.don('별빛', 30000, 'toon_e1', msg='비밀')
        did = self.pub()['recent'][0]['id']
        self.assertEqual(self.cmd('mask.hide', id=did)[0], 200)
        r = self.c.post('/api/donation/replay', json={'id': did}, headers=H)
        self.assertEqual(r.status_code, 200, r.json())
        rec = self.pub()['recent']
        self.assertTrue(rec[-1]['encore'])
        self.assertEqual(rec[-1]['message'], '')
        self.assertTrue(all('src' not in x for x in rec))

    def test_new_session_clears(self):
        self.don('별빛', 30000, 'toon_n1')
        self.assertEqual(len(self.pub()['recent']), 1)
        self.cmd('session.end')
        self.assertEqual(self.pub().get('recent'), [])
        self.cmd('session.start', names=['하율'])
        self.assertEqual(self.pub().get('recent'), [])


class Started(Base):
    def started(self, **data):
        r = self.c.post('/api/cmd', json={'type': 'reaction.started', 'data': data})       # 로그인 없이(방송판)
        return r.status_code, r.json()

    def head(self):
        return self.st(auth=False)['queue']['items'][0]

    def test_marks_head_once_without_login(self):
        self.don('별빛', 10300, 'toon_t1')
        h = self.head()
        self.assertNotIn('started', h)
        c, r = self.started(id=h['id'], replay=0)
        self.assertEqual(c, 200, r)
        st = self.head()['started']
        self.assertEqual(st['replay'], 0)
        self.assertGreater(st['at'], 0)
        c, r = self.started(id=h['id'], replay=0)                       # 두 화면 · 다시 보냄 — 처음 것만
        self.assertTrue(r.get('notes', r).get('ignored', True))
        self.assertEqual(self.head()['started'], st)

    def test_wrong_id_or_replay_ignored(self):
        self.don('별빛', 10300, 'toon_t2')
        self.don('달빛', 20005, 'toon_t3')
        items = self.st()['queue']['items']
        self.started(id=items[1]['id'], replay=0)                        # 맨 앞이 아님
        self.started(id=items[0]['id'], replay=3)                        # 회차가 다름
        self.started(id=items[0]['id'], replay='x')
        self.assertTrue(all('started' not in x for x in self.st()['queue']['items']))

    def test_play_all_next_round_needs_new_signal(self):
        self.don('별빛', 10300, 'toon_p1')
        self.don('별빛', 10300, 'toon_p2')                                # ×2 로 묶임
        h = self.head()
        self.assertEqual(h['count'], 2)
        self.assertEqual(self.cmd('reaction.playall', id=h['id'])[0], 200)
        self.started(id=h['id'], replay=0)
        self.c.post('/api/cmd', json={'type': 'reaction.done', 'data': {'id': h['id'], 'replay': 0}})
        h2 = self.head()
        self.assertEqual((h2['replay'], h2['started']['replay']), (1, 0))  # 다음 회차 — 앞 회차 신호(전광판은 기다린다)
        self.started(id=h['id'], replay=1)
        self.assertEqual(self.head()['started']['replay'], 1)

    def test_again_row_does_not_copy_started(self):
        self.don('별빛', 10300, 'toon_g1')
        self.don('별빛', 10300, 'toon_g2')
        h = self.head()
        self.started(id=h['id'], replay=0)
        self.c.post('/api/cmd', json={'type': 'reaction.done', 'data': {'id': h['id'], 'replay': 0}})   # 한 번만 틀고 빠짐
        self.assertEqual(self.cmd('reaction.playall', id=h['id'])[0], 200)                               # 남은 만큼 이어 틀기
        again = self.st()['queue']['items'][0]
        self.assertEqual(again.get('again_of'), h['id'])
        self.assertNotIn('started', again)


if __name__ == '__main__':
    unittest.main()
