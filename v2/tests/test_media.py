# -*- coding: utf-8 -*-
"""v2 계좌 고액후원 영상 · 노래방."""
import unittest

from v2.tests.test_flow import Base, H


class Media(Base):
    def test_acct_video(self):
        c, r = self.cmd('acctvid.play', tier=0)
        self.assertFalse(r['played'])                                   # 영상이 없는 구간
        self.cmd('acctvid.set', tier=0, video='https://x/v.mp4')
        c, r = self.cmd('acctvid.play', tier=0)
        now = self.st(auth=False)['acct_video']['now']
        self.assertEqual((r['played'], now['label']), (True, '20만'))
        r = self.c.post('/api/cmd', json={'type': 'acctvid.ended', 'data': {'at': now['at'] - 1}}).json()
        self.assertTrue(r.get('ignored'))                               # 다른 영상의 끝 보고는 무시
        self.c.post('/api/cmd', json={'type': 'acctvid.ended', 'data': {'at': now['at']}})
        self.assertIsNone(self.st()['acct_video']['now'])
        self.assertEqual(self.cmd('acctvid.play', tier=99)[0], 400)

    def test_upload_checks(self):
        r = self.c.post('/api/account/video/upload', data={'tier': '0'}, files={'file': ('a.exe', b'x', 'application/octet-stream')}, headers=H)
        self.assertEqual(r.status_code, 400)
        r = self.c.post('/api/account/video/upload', data={'tier': '0'}, files={'file': ('a.mp4', b'x', 'video/mp4')})
        self.assertEqual(r.status_code, 401)

    def test_karaoke(self):
        self.cmd('karaoke.play', video='https://youtu.be/abc')
        self.assertTrue(self.st(auth=False)['karaoke']['on'])
        self.cmd('karaoke.stop')
        self.assertFalse(self.st()['karaoke']['on'])
        self.assertEqual(self.cmd('karaoke.play', video='')[0], 400)


if __name__ == '__main__':
    unittest.main()
