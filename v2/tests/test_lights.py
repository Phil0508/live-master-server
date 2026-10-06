# -*- coding: utf-8 -*-
"""v2 💡 조명(네온 · 아우디 · 속도 · 색 슬롯) · ✨ 테마 연출 — 옛 controller.html triggerNeon · updateNeonSpeed · 색 슬롯,
옛 방송판 effect_trigger(OFF · AUDI · RAINBOW · 색) 규칙, 옛 스트림덱 /api/streamdeck/neon, 옛 설정 옮기기.

돌리기: python -m unittest discover -s v2/tests -t .
"""
from v2.tests.test_flow import Base, H


class Lights(Base):
    def L(self, auth=True):
        return self.st(auth)['lights']

    def test_default_and_public(self):
        L = self.L(auth=False)                                              # 방송판(로그인 없음)도 받는다
        self.assertEqual((L['color'], L['audi'], L['speed']), ('OFF', False, 1.5))
        self.assertEqual(L['colors'], ['#ff0055', '#00e5ff', '#ff9100', '#d500f9', '#00ff00', '#ffff00', '#ff0000', '#0000ff', '#ffffff'])
        self.assertNotEqual(self.st(auth=False)['look'].get('fx'), False)   # 테마 연출 — 없으면 켜진 것

    def test_color_button_rules(self):
        """옛 effect_trigger: 색 · RAINBOW 는 네온만, AUDI 는 아우디 뒤집기(네온 그대로), OFF 는 둘 다 끔"""
        self.assertEqual(self.cmd('lights.color', color='#FF9100')[1]['ok'], True)
        self.assertEqual(self.L()['color'], '#ff9100')                      # 소문자로 맞춘다(조종실 [현재 ON] 비교)
        self.cmd('lights.color', color='AUDI')
        L = self.L()
        self.assertEqual((L['color'], L['audi']), ('#ff9100', True))
        self.assertGreater(L['at'], 0)
        self.cmd('lights.color', color='rainbow')
        self.assertEqual((self.L()['color'], self.L()['audi']), ('RAINBOW', True))
        self.cmd('lights.color', color='AUDI')
        self.assertFalse(self.L()['audi'])
        self.cmd('lights.color', color='AUDI')
        self.cmd('lights.color', color='OFF')
        self.assertEqual((self.L()['color'], self.L()['audi']), ('OFF', False))
        self.cmd('lights.color', color='0f8')                               # 세 자리 · # 없이도
        self.assertEqual(self.L()['color'], '#00ff88')

    def test_reject_bad(self):
        before = self.L()
        for bad in ('red', '', None, '#12345', 'javascript:alert(1)', 'url(x)'):
            c, r = self.cmd('lights.color', color=bad)
            self.assertEqual((c, r['ok']), (400, False), bad)
        self.assertEqual(self.cmd('lights.set', color='AUDI')[0], 400)       # 하나씩 맞추기에는 뒤집기가 없다
        self.assertEqual(self.cmd('lights.set')[0], 400)
        self.assertEqual(self.cmd('lights.set', speed='빠르게')[0], 400)
        self.assertEqual(self.cmd('lights.slot', index=9, color='#fff')[0], 404)
        self.assertEqual(self.cmd('lights.slot', index=0, color='blue')[0], 400)
        self.assertEqual(self.cmd('look.fx')[0], 400)
        self.assertEqual(self.L(), before)                                  # 거절은 아무것도 안 바꾼다
        # 로그인 없이는 못 바꾼다
        r = self.c.post('/api/cmd', json={'type': 'lights.color', 'data': {'color': 'RAINBOW'}})
        self.assertEqual(r.status_code, 401)

    def test_set_speed_slot_fx(self):
        self.cmd('lights.set', speed=9)
        self.assertEqual(self.L()['speed'], 5.0)                            # 옛 슬라이더 끝(5.0)
        self.cmd('lights.set', speed='0.05')
        self.assertEqual(self.L()['speed'], 0.3)
        self.cmd('lights.set', speed=2.26)
        self.assertEqual(self.L()['speed'], 2.3)
        self.cmd('lights.set', color='#00e5ff', audi=True)
        self.assertEqual((self.L()['color'], self.L()['audi']), ('#00e5ff', True))
        self.cmd('lights.set', color='OFF')                                  # 하나씩 맞추기의 OFF 는 네온만
        self.assertEqual((self.L()['color'], self.L()['audi']), ('OFF', True))
        self.cmd('lights.color', color='#ff0055')
        self.cmd('lights.slot', index=0, color='#ABCDEF')
        L = self.L()
        self.assertEqual(L['colors'][0], '#abcdef')
        self.assertEqual(L['color'], '#ff0055')                              # 켜 둔 색은 그대로(옛 것과 같다)
        self.cmd('look.fx', on=False)
        self.assertIs(self.st(auth=False)['look']['fx'], False)
        self.cmd('look.theme', theme='rose')
        self.assertIs(self.st()['look']['fx'], False)                        # 테마를 바꿔도 스위치는 그대로
        self.cmd('look.fx', on=True)
        self.assertIs(self.st()['look']['fx'], True)

    def test_kept_across_broadcasts(self):
        """옛 BROADCAST_KEEP_KEYS(neon_speed · saved_colors · theme_fx_enabled) — 방송을 끝내고 다시 시작해도 그대로"""
        self.cmd('lights.set', speed=3.2)
        self.cmd('lights.slot', index=4, color='#123456')
        self.cmd('lights.color', color='RAINBOW')
        self.cmd('lights.color', color='AUDI')
        self.cmd('look.fx', on=False)
        self.cmd('session.end')
        self.cmd('session.start', names=['하율'])
        L = self.L()
        self.assertEqual((L['speed'], L['colors'][4], L['color'], L['audi']), (3.2, '#123456', 'RAINBOW', True))
        self.assertIs(self.st()['look']['fx'], False)

    def test_streamdeck_neon(self):
        self.assertEqual(self.c.get('/api/streamdeck/neon').status_code, 401)
        r = self.c.get('/api/streamdeck/neon', headers=H)                   # 색이 없으면 무지개(옛 기본)
        self.assertEqual((r.status_code, r.json()['status']), (200, 'success'))
        self.assertIn('무지개', r.json()['message'])
        self.assertEqual(self.L()['color'], 'RAINBOW')
        self.c.get('/api/streamdeck/neon?color=00E5B5', headers=H)           # 옛 단추: # 없는 여섯 자리
        self.assertEqual(self.L()['color'], '#00e5b5')
        self.c.get('/api/streamdeck/neon?color=%23FF0000', headers=H)
        self.assertEqual(self.L()['color'], '#ff0000')
        r = self.c.get('/api/streamdeck/neon?color=AUDI', headers=H).json()
        self.assertTrue(self.L()['audi'])
        self.assertIn('아우디 켜짐', r['message'])
        r = self.c.get('/api/streamdeck/neon?color=OFF', headers=H).json()
        self.assertEqual((self.L()['color'], self.L()['audi']), ('OFF', False))
        r = self.c.get('/api/streamdeck/neon?color=', headers=H)               # '#' 을 그대로 써서 뒤가 잘린 주소
        self.assertEqual((r.status_code, r.json()['status']), (400, 'error'))
        r = self.c.get('/api/streamdeck/neon?color=purple&token=testsecret-0123456789')
        self.assertEqual(r.status_code, 400)

    def test_import_old(self):
        old = {'neon_speed': 2.5, 'saved_colors': ['#FF0055', 'nope', '#00ff00'], 'theme_fx_enabled': False, 'theme': 'royal',
               'effect_trigger': {'time': 1, 'color': '#00ff00'}}
        c, r = self.cmd('admin.import_old', state=old)
        self.assertTrue(r['ok'], r)
        self.assertIn('조명 속도 · 색', r['imported'])
        self.assertIn('테마 연출', r['imported'])
        L = self.L()
        self.assertEqual(L['speed'], 2.5)
        self.assertEqual(L['colors'][:4], ['#ff0055', '#00e5ff', '#00ff00', '#d500f9'])   # 이상한 칸 · 모자란 칸은 기본값(옛 6→9칸 옮기기)
        self.assertEqual(len(L['colors']), 9)
        self.assertEqual(L['color'], 'OFF')                                  # 켜 둔 색은 안 옮긴다(옛 것도 방송을 넘기면 지웠다)
        self.assertIs(self.st()['look']['fx'], False)
        self.assertEqual(self.st()['look']['theme'], 'royal')
        # 옛 값이 0 · 이상하면 옛 방송판처럼 1.5
        self.cmd('admin.import_old', state={'neon_speed': 0, 'theme_fx_enabled': True})
        self.assertEqual(self.L()['speed'], 1.5)
        self.assertIs(self.st()['look']['fx'], True)
