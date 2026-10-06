# -*- coding: utf-8 -*-
"""🎚️ 옛 설정 더 옮기기 — 시그니처 보이는 모습 · 목록 개수 · 효과음 · 노래방 음량 · 💾 세이브 슬롯(순서표).

옛 숫자 · 범위 · 기본값과 같은지(admin.html 막대 min/max · server.py DEFAULT_STATE · features/show_api.py) 본다.
돌리기: python -m unittest discover -s v2/tests -t .
"""
from v2.tests.test_flow import Base, H


class SigView(Base):
    def test_defaults_are_old_defaults(self):
        s = self.st()
        self.assertEqual(s['sigview'], {'big_scale': 1.0, 'small_scale': 0.6, 'min_x': 180, 'min_y': 600, 'shrink_delay': 2500,
                                        'title_size': 150, 'title_duration': 3500, 'title_suffix': '업'})
        self.assertIn('sigview', self.st(auth=False))                       # 방송판(로그인 없음)이 받는다

    def test_clamped_to_old_ranges(self):
        c, r = self.cmd('sigview.set', big_scale=5, small_scale=0.1, shrink_delay=100, title_size=10, title_duration=99999,
                        min_x=-30, min_y=5000)
        self.assertEqual(c, 200, r)
        v = self.st()['sigview']
        self.assertEqual((v['big_scale'], v['small_scale'], v['shrink_delay'], v['title_size'], v['title_duration'], v['min_x'], v['min_y']),
                         (2.0, 0.3, 500, 60, 8000, 0, 1920))
        self.cmd('sigview.set', big_scale=0.1, small_scale=9, shrink_delay=60000, title_size=999, title_duration=1)
        v = self.st()['sigview']
        self.assertEqual((v['big_scale'], v['small_scale'], v['shrink_delay'], v['title_size'], v['title_duration']),
                         (0.5, 1.5, 6000, 300, 1000))

    def test_partial_and_suffix(self):
        self.cmd('sigview.set', shrink_delay=4000)
        v = self.st()['sigview']
        self.assertEqual((v['shrink_delay'], v['big_scale']), (4000, 1.0))        # 보낸 칸만
        self.cmd('sigview.set', title_suffix=' 최고에요요요\n')
        self.assertEqual(self.st()['sigview']['title_suffix'], ' 최고에요요')      # 적은 그대로 6자까지(앞 띄어쓰기도)
        self.cmd('sigview.set', title_suffix='')
        self.assertEqual(self.st()['sigview']['title_suffix'], '')                # 비워도 된다(이름만)

    def test_rejects_bad_numbers(self):
        self.assertEqual(self.cmd('sigview.set', big_scale='abc')[0], 400)
        self.assertEqual(self.cmd('sigview.set', nothing=1)[0], 400)
        self.assertEqual(self.st()['sigview']['big_scale'], 1.0)


class LookExtra(Base):
    def test_limits(self):
        s = self.st()
        self.assertNotIn('sig_tally_limit', s['look'])        # 없으면 방송판이 기본(6 · 5)으로 읽는다
        self.cmd('look.limits', sig_tally_limit=99, donor_rank_limit=1)
        look = self.st(auth=False)['look']
        self.assertEqual((look['sig_tally_limit'], look['donor_rank_limit']), (12, 3))
        self.cmd('look.limits', sig_tally_limit=1, donor_rank_limit=99)
        look = self.st()['look']
        self.assertEqual((look['sig_tally_limit'], look['donor_rank_limit']), (3, 10))
        self.assertEqual(self.cmd('look.limits', sig_tally_limit='x')[0], 400)
        self.assertEqual(self.cmd('look.limits')[0], 400)
        self.assertEqual(self.st()['look']['theme'], 'default')                    # 테마는 그대로

    def test_sfx_switch(self):
        self.assertNotIn('sfx', self.st()['look'])            # 없으면 켜짐(옛 sfx_enabled 기본 True)
        self.cmd('look.sfx', on=False)
        self.assertIs(self.st(auth=False)['look']['sfx'], False)
        self.cmd('look.sfx', on=True)
        self.assertIs(self.st()['look']['sfx'], True)
        self.assertEqual(self.cmd('look.sfx')[0], 400)

    def test_settings_survive_broadcasts(self):
        self.cmd('look.limits', donor_rank_limit=8)
        self.cmd('look.sfx', on=False)
        self.cmd('sigview.set', min_x=300)
        self.cmd('karaoke.volume', volume=40)
        self.cmd('session.end')
        self.cmd('session.start', names=['하율'])
        s = self.st()
        self.assertEqual((s['look']['donor_rank_limit'], s['look']['sfx'], s['sigview']['min_x'], s['karaoke']['volume']),
                         (8, False, 300, 40))


class KaraokeVolume(Base):
    def test_volume(self):
        self.assertEqual(self.st()['karaoke']['volume'], 70)
        self.cmd('karaoke.volume', volume=135)
        self.assertEqual(self.st()['karaoke']['volume'], 100)
        self.cmd('karaoke.volume', volume=-5)
        self.assertEqual(self.st()['karaoke']['volume'], 0)
        self.cmd('karaoke.volume', volume=55)
        self.assertEqual(self.cmd('karaoke.volume', volume='큼')[0], 400)
        self.cmd('karaoke.play', video='dQw4w9WgXcQ')
        k = self.st(auth=False)['karaoke']
        self.assertEqual((k['on'], k['video'], k['volume']), (True, 'dQw4w9WgXcQ', 55))     # 켜도 음량이 남는다
        self.cmd('karaoke.stop')
        self.assertEqual(self.st()['karaoke']['volume'], 55)


class Presets(Base):
    def setup_screen(self, stage, x, hud_on):
        self.cmd('show.stage', stage=stage)
        self.cmd('layout.set', id='ranking', x=x, y=200)
        for k in hud_on:
            self.cmd('show.hud', key=k, on=True)

    def ids(self):
        return [p['id'] for p in self.st()['presets']['list']]

    def test_private(self):
        self.assertNotIn('presets', self.st(auth=False))
        self.assertIn('presets', self.st())

    def test_save_contents_and_names(self):
        self.setup_screen('pinball', 900, ['best'])
        c, r = self.cmd('preset.save')
        self.assertEqual(c, 200, r)
        p = self.st()['presets']['list'][0]
        self.assertEqual(p['name'], '슬롯 1')
        self.assertEqual(p['stage'], 'pinball')
        self.assertEqual(p['layout'], {'ranking': {'x': 900.0, 'y': 200.0}})
        self.assertTrue(p['hud']['best'])
        self.assertEqual(r['id'], p['id'])
        c, r = self.cmd('preset.save', name='가' * 40)
        self.assertEqual(len(self.st()['presets']['list'][1]['name']), 30)
        # 잠깐 판(룰렛 · 슬롯)이 떠 있으면 돌아갈 무대를 담는다(옛 cue_from_state)
        s = self.st()
        self.cmd('show.stage', stage='dicegame')
        self.c.app.state.bus.state.slices['show'] = dict(s['show'], stage='roulette', ret='dicegame')
        self.cmd('preset.save', name='룰렛 중')
        self.assertEqual(self.st()['presets']['list'][2]['stage'], 'dicegame')

    def test_overwrite_rename_errors(self):
        self.cmd('preset.save', name='하나')
        pid = self.ids()[0]
        self.setup_screen('quiz', 500, [])
        self.cmd('preset.save', id=pid)
        p = self.st()['presets']['list'][0]
        self.assertEqual((p['name'], p['stage'], p['layout']['ranking']['x']), ('하나', 'quiz', 500.0))
        self.assertEqual(len(self.ids()), 1)                                  # 덮어쓰기는 칸이 안 늘어난다
        self.assertEqual(self.cmd('preset.rename', id=pid, name='   ')[0], 400)
        self.assertEqual(self.cmd('preset.rename', id='nope', name='x')[0], 404)
        self.cmd('preset.rename', id=pid, name='  1차   대결 ')
        self.assertEqual(self.st()['presets']['list'][0]['name'], '1차 대결')
        self.assertEqual(self.cmd('preset.apply', id='nope')[0], 404)
        self.assertEqual(self.cmd('preset.delete', id='nope')[0], 404)

    def test_apply_restores_screen_only(self):
        self.setup_screen('pinball', 900, ['best', 'fundjar'])
        self.cmd('preset.save', name='핀볼')
        pid = self.ids()[0]
        # 화면을 바꾸고 · 점수 · 테마도 바꾼다
        self.cmd('show.stage', stage='quiz')
        self.cmd('layout.set', id='ranking', x=100)
        self.cmd('layout.set', id='gauge', x=50, y=50)
        self.cmd('show.hud', key='best', on=False)
        self.cmd('show.hud', key='fundjar', on=False)
        self.cmd('look.theme', theme='rose')
        self.cmd('score.add', name='하율', delta=7)
        c, r = self.cmd('preset.apply', id=pid)
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertEqual(s['show']['stage'], 'pinball')
        self.assertEqual(s['layout']['widgets'], {'ranking': {'x': 900.0, 'y': 200.0}})   # 저장 때 기본 자리였던 게이지는 기본으로
        self.assertTrue(s['show']['hud']['best'])
        self.assertTrue(s['show']['hud']['fundjar'] and s['fundjar']['enabled'])       # 모금함 스위치도 같이
        self.assertEqual(s['show']['cue_at'], 0)
        self.assertEqual(s['look']['theme'], 'rose')                                   # 테마 · 점수는 안 건드린다
        self.assertEqual(self.player('하율', s)['score'], 7)
        self.assertEqual(r['name'], '핀볼')

    def test_cue_next_prev_go(self):
        c, r = self.cmd('show.cue', dir='next')
        self.assertEqual(c, 409)
        self.assertIn('비어 있어요', r['error'])
        for st, nm in (('pinball', 'A'), ('quiz', 'B'), (None, 'C')):
            self.cmd('show.stage', stage=st)
            self.cmd('preset.save', name=nm)
        self.cmd('show.stage', stage='dicegame')
        c, r = self.cmd('show.cue', dir='next')
        self.assertEqual((c, r['at'], self.st()['show']['stage']), (200, 0, 'pinball'))
        self.cmd('show.cue', dir='next')
        self.cmd('show.cue', dir='next')
        s = self.st()
        self.assertEqual((s['show']['cue_at'], s['show']['stage']), (2, None))
        c, r = self.cmd('show.cue', dir='next')
        self.assertEqual((c, r['error']), (409, '순서표 끝이에요'))
        self.cmd('show.cue', dir='prev')
        self.assertEqual(self.st()['show']['stage'], 'quiz')
        self.cmd('show.cue', dir='go', id=self.ids()[0])
        self.assertEqual(self.st()['show']['cue_at'], 0)
        self.assertEqual(self.cmd('show.cue', dir='sideways')[0], 400)
        # 방송 시작 · 끝 — 처음부터
        self.cmd('session.end')
        self.assertEqual(self.st()['show']['cue_at'], -1)
        self.assertEqual(len(self.ids()), 3)                                          # 슬롯은 방송이 바뀌어도 남는다

    def test_move_delete_keep_cue(self):
        for nm in 'ABCD':
            self.cmd('preset.save', name=nm)
        a, b, c_, d = self.ids()
        self.cmd('show.cue', dir='go', id=b)                     # 지금 = B(1)
        self.cmd('preset.move', id=b, dir=-1)                    # B 를 앞으로 → B A C D
        self.assertEqual(self.ids(), [b, a, c_, d])
        self.assertEqual(self.st()['show']['cue_at'], 0)          # 여전히 B
        self.cmd('preset.move', id=b, dir=-1)                    # 맨 앞에서 더 앞으로 — 그대로
        self.assertEqual(self.ids(), [b, a, c_, d])
        self.cmd('preset.move', id=c_, dir=1)                    # B A D C — 지금 단계(B)는 그대로
        self.assertEqual(self.st()['show']['cue_at'], 0)
        self.cmd('show.cue', dir='go', id=d)                     # 지금 = D(2)
        self.cmd('preset.delete', id=d)                          # 지금 단계를 지우면 바로 앞(A, 1)을 가리킨다
        self.assertEqual((self.ids(), self.st()['show']['cue_at']), ([b, a, c_], 1))
        c, r = self.cmd('show.cue', dir='next')                  # [다음 ▶] 은 지운 단계 다음 것
        self.assertEqual(r['name'], 'C')
        self.cmd('preset.delete', id=b)                          # 앞의 것을 지우면 한 칸 당겨진다
        self.assertEqual(self.st()['show']['cue_at'], 1)

    def test_max_60(self):
        for i in range(60):
            self.assertEqual(self.cmd('preset.save', name=str(i))[0], 200)
        c, r = self.cmd('preset.save', name='넘침')
        self.assertEqual(c, 400)
        self.assertIn('60', r['error'])

    def test_old_board_only_slot_keeps_match(self):
        """옛 슬롯(board 만, 무대 없음)은 대결 · 지옥탈출 · 퇴근빵 무대를 그대로 둔다(옛 apply_cue)."""
        old = {'layout_presets': [{'id': 'pold1', 'name': '옛 휴식', 'board': '', 'switches': {'best_enabled': True, 'ticker_enabled': False},
                                   'layout': {'ranking': {'x_px': 10, 'y_px': 10, 'scale': 1}}, 'saved_at': 1700000000},
                                  {'id': 'pold2', 'name': '옛 룰렛', 'board': 'roulette', 'hud': {'notice': True}}]}
        c, r = self.cmd('admin.import_old', state=old)
        self.assertEqual(c, 200, r)
        ps = self.st()['presets']['list']
        self.assertEqual([p['id'] for p in ps], ['pold1', 'pold2'])
        self.assertNotIn('layout', ps[0])                                    # 옛 좌표는 기준점이 달라 안 옮긴다
        self.assertEqual(ps[0]['hud'], {'best': True})                       # 전광판(ticker)은 v2 에 없다
        self.cmd('show.stage', stage='match')
        self.cmd('layout.set', id='gauge', x=1, y=1)
        self.cmd('preset.apply', id='pold1')
        s = self.st()
        self.assertEqual(s['show']['stage'], 'match')
        self.assertTrue(s['show']['hud']['best'])
        self.assertEqual(s['layout']['widgets'], {'gauge': {'x': 1.0, 'y': 1.0}})     # 자리는 안 건드린다
        self.cmd('preset.apply', id='pold2')
        self.assertEqual(self.st()['show']['stage'], 'roulette')
        self.cmd('admin.import_old', state=old)                               # 두 번 옮겨도 겹치지 않는다
        self.assertEqual(len(self.st()['presets']['list']), 2)


class ImportOld(Base):
    def test_old_keys(self):
        old = {'reaction_big_scale': 1.35, 'reaction_small_scale': 0.45, 'reaction_min_x': 220, 'reaction_min_y': 'abc',
               'reaction_shrink_delay': 3000, 'reaction_title_enabled': False, 'reaction_title_size': 999,
               'reaction_title_duration': 4200, 'reaction_title_suffix': '최고업',
               'sig_tally_limit': 9, 'donor_rank_limit': 30, 'sfx_enabled': False, 'karaoke_volume': 65}
        c, r = self.cmd('admin.import_old', state=old)
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertEqual(s['sigview'], {'big_scale': 1.35, 'small_scale': 0.45, 'min_x': 220, 'min_y': 600, 'shrink_delay': 3000,
                                        'title_size': 300, 'title_duration': 4200, 'title_suffix': '최고업'})
        self.assertFalse(s['show']['alerts']['reaction_title'])
        self.assertEqual((s['look']['sig_tally_limit'], s['look']['donor_rank_limit'], s['look']['sfx']), (9, 10, False))
        self.assertEqual(s['karaoke']['volume'], 65)
        self.assertIn('시그니처 보이는 모습', r['imported'])


class DonorRankOptions(Base):
    def test_look_donor(self):
        self.cmd('look.donor', amount=False, anon=True)
        look = self.st()['look']
        self.assertEqual((look['donor_amount'], look['donor_anon']), (False, True))
        r = self.c.post('/api/cmd', json={'type': 'look.donor', 'data': {}}, headers=H).json()
        self.assertFalse(r['ok'])
