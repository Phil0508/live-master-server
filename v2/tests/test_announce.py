# -*- coding: utf-8 -*-
"""v2 진행봇 설정(announce_bot) — 옛 /api/announcebot 과 같은 검사 · 같은 모양인지 본다.

⚠️ 조각 · 명령 등록은 domain/__init__.py 가 한다. 붙이기 전에도 이 검사가 돌도록 여기서 직접 불러온다.
"""
import copy
import unittest

from v2.server.domain import announce as an          # noqa: F401  (조각 · 명령 등록)
from v2.server.bus import Ctx
from v2.server.state import Work
from v2.tests.test_flow import Base


class VideoId(unittest.TestCase):
    def test_shapes(self):
        vid = 'dQw4w9WgXcQ'
        for u in ('https://www.youtube.com/watch?v=%s&t=3' % vid, 'https://youtu.be/%s' % vid,
                  'https://www.youtube.com/live/%s?si=x' % vid, 'https://youtube.com/shorts/%s' % vid,
                  'https://www.youtube.com/embed/%s' % vid, '  %s ' % vid):
            self.assertEqual(an.yt_video_id(u), vid, u)
        self.assertEqual(an.yt_video_id(''), '')                 # 비우기
        self.assertEqual(an.yt_video_id('   '), '')
        self.assertIsNone(an.yt_video_id('https://www.youtube.com/@angel'))   # 못 읽음 — 비우기와 다르다
        self.assertIsNone(an.yt_video_id('abc'))


class Settings(Base):
    def bot(self):
        return self.st()['announce_bot']

    def test_default_shape_and_private(self):
        self.assertEqual(self.bot(), an.DEFAULT)                 # 옛 DEFAULT_STATE['announce_bot'] 그대로
        pub = self.st(auth=False)
        self.assertNotIn('announce_bot', pub)                    # 방송판(로그인 없음)엔 안 간다
        self.assertNotIn('announce_status', pub)

    def test_set_partial(self):
        c, r = self.cmd('bot.set', enabled=False, min_interval_sec='40', say={'rank_close': True, 'bogus': True},
                        notices={'rank_min': 3, 'nope': 5})
        self.assertEqual(c, 200, r)
        b = self.bot()
        self.assertFalse(b['enabled'])
        self.assertEqual(b['min_interval_sec'], 40)
        self.assertTrue(b['say']['rank_close'])
        self.assertNotIn('bogus', b['say'])                      # 모르는 이름은 조용히 버린다
        self.assertNotIn('nope', b['notices'])
        self.assertEqual(b['notices'], {'account_min': 7, 'rank_min': 3, 'fundjar_min': 0})
        self.assertTrue(b['say']['donation'])                    # 안 보낸 칸은 그대로
        self.cmd('bot.set', on=True)                             # on 도 받는다
        self.assertTrue(self.bot()['enabled'])

    def test_validation_is_atomic(self):
        for bad in (4, 601, 'abc', True, [5]):
            c, r = self.cmd('bot.set', enabled=False, min_interval_sec=bad)
            self.assertEqual(c, 400, bad)
            self.assertIn('5~600', r['error'])
        self.assertTrue(self.bot()['enabled'])                   # ⭐ 옛 것은 여기서 enabled 가 바뀐 채 남았다
        for bad in (121, -1, 'x', None):
            c, r = self.cmd('bot.set', notices={'account_min': bad})
            self.assertEqual(c, 400, bad)
            self.assertIn('0~120', r['error'])
        self.assertEqual(self.cmd('bot.set', say=['donation'])[0], 400)
        self.assertEqual(self.bot(), an.DEFAULT)
        self.assertEqual(self.cmd('bot.set', min_interval_sec=None)[0], 200)   # None 은 '안 보냄'(옛 것과 같다)

    def test_live_url(self):
        c, _ = self.cmd('bot.set', live_url=' https://youtu.be/AbCdEfGhIjK ')
        self.assertEqual(c, 200)
        b = self.bot()
        self.assertEqual((b['live_url'], b['live_video_id']), ('https://youtu.be/AbCdEfGhIjK', 'AbCdEfGhIjK'))
        c, r = self.cmd('bot.set', live_url='https://www.youtube.com/@angel')
        self.assertEqual(c, 400)
        self.assertIn('라이브 주소', r['error'])
        self.assertEqual(self.bot()['live_video_id'], 'AbCdEfGhIjK')       # 못 읽은 주소로 지우지 않는다
        self.cmd('bot.set', live_url='')
        b = self.bot()
        self.assertEqual((b['live_url'], b['live_video_id']), ('', ''))  # 비우면 봇이 채널에서 찾는다

    def test_say_and_notice(self):
        self.cmd('bot.say', key='dice')
        self.assertTrue(self.bot()['say']['dice'])               # on 없으면 뒤집기
        self.cmd('bot.say', key='dice', on=False)
        self.assertFalse(self.bot()['say']['dice'])
        self.cmd('bot.say', key='idle', on=False)
        self.assertFalse(self.bot()['say']['idle'])
        c, r = self.cmd('bot.say', key='nope', on=True)
        self.assertEqual(c, 404)
        self.cmd('bot.notice', key='fundjar_min', min=15)
        self.assertEqual(self.bot()['notices']['fundjar_min'], 15)
        self.assertEqual(self.cmd('bot.notice', key='fundjar_min', min=200)[0], 400)
        self.assertEqual(self.cmd('bot.notice', key='x', min=1)[0], 404)

    def test_survives_session_and_fills_old_saved(self):
        self.cmd('bot.set', min_interval_sec=60, live_url='AbCdEfGhIjK')
        self.cmd('session.end')
        self.assertEqual(self.bot()['min_interval_sec'], 60)    # 방송 끝에 설정을 안 지운다
        # 옛 저장본(새 칸이 없는 것)이 돌아왔다고 치고 — 방송 시작 때 값은 그대로, 빠진 칸만 채운다
        bus = self.c.app.state.bus
        old = copy.deepcopy(bus.state.slices['announce_bot'])
        del old['say']['idle'], old['notices']['fundjar_min'], old['live_url']
        bus.state.slices['announce_bot'] = old
        self.cmd('session.start', names=['가', '나'])
        b = self.bot()
        self.assertEqual(b['min_interval_sec'], 60)
        self.assertTrue(b['say']['idle'])
        self.assertEqual(b['notices']['fundjar_min'], 0)
        self.assertEqual(b['live_url'], '')
        self.assertEqual(b['live_video_id'], 'AbCdEfGhIjK')

    def test_hello(self):
        c, _ = self.cmd('bot.hello', mode='dry', pid=1234, host='pc')
        self.assertEqual(c, 200)
        s = self.st()
        self.assertEqual((s['announce_status']['mode'], s['announce_status']['pid']), ('dry', 1234))
        self.assertGreater(s['announce_status']['since'], 0)
        self.assertEqual(s['announce_bot'], an.DEFAULT)          # 봇은 설정을 안 바꾼다
        self.assertEqual(self.cmd('bot.hello', mode='loud')[0], 400)
        self.assertEqual(self.c.post('/api/cmd', json={'type': 'bot.set', 'data': {'enabled': False}}).status_code, 401)

    def test_import_old(self):
        bus = self.c.app.state.bus
        ctx = Ctx(bus, Work(bus.state), 'test')
        old = {'announce_bot': {'enabled': False, 'min_interval_sec': 30, 'live_url': 'https://youtu.be/AbCdEfGhIjK',
                                'live_video_id': 'ignored', 'say': {'goal': True, 'zzz': 1}, 'notices': {'rank_min': 9}}}
        self.assertTrue(an.import_old(ctx, old))
        b = ctx.work.changed()['announce_bot']
        self.assertEqual((b['enabled'], b['min_interval_sec'], b['live_video_id']), (False, 30, 'AbCdEfGhIjK'))
        self.assertTrue(b['say']['goal'])
        self.assertEqual(b['notices']['rank_min'], 9)
        self.assertFalse(an.import_old(Ctx(bus, Work(bus.state), 't'), {'theme': 'x'}))


if __name__ == '__main__':
    unittest.main()
