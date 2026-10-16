# -*- coding: utf-8 -*-
"""v2 퇴근빵 · 지옥탈출 — 목표를 넘기면 서버가 바로 대기함에 카드를 만든다.

10-17(w2races) — 지옥 · 퇴근을 무대에서 빼고(늘 붙는 칸), 다시 판정(_recheck) 하나로 되돌리기 · 목표 바꾸기 · 이름 바꾸기 ·
번외 판을 맞췄다. 조사 보고서의 재현 스크립트(hellrepro/repro.py) 사례를 그대로 옮겼다:
undo · goalraise · goalzero · extra · rename · stage · restart · neg.
"""
import os
import shutil
import subprocess
import unittest

from v2.tests.test_flow import Base

HERE = os.path.dirname(os.path.abspath(__file__))


class Races(Base):
    def cards(self, s=None):
        s = s or self.st()
        return [(d['name'], d['kind']) for d in s['pending'] if d.get('type') == 'off_work']

    def card_id(self, name, kind):
        return next(d['id'] for d in self.st()['pending'] if d.get('type') == 'off_work' and d['name'] == name and d['kind'] == kind)

    # ── 옛 검사(모양만 새 규칙에 맞췄다) ──
    def test_home(self):
        self.cmd('home.goal', name='하율', goal=10)
        self.cmd('home.on', on=True)
        self.assertIsNone(self.st()['show']['stage'])                     # 퇴근빵은 무대를 안 쓴다
        self.cmd('score.add', name='하율', delta=9)
        self.assertEqual(self.cards(), [])
        self.cmd('score.add', name='하율', delta=1)
        self.assertEqual(self.cards(), [('하율', 'home')])
        self.cmd('score.add', name='하율', delta=5)                       # 또 넘겨도 한 번
        self.assertEqual(self.cards(), [('하율', 'home')])
        cid = self.st()['pending'][0]['id']
        self.cmd('offwork.send', id=cid)
        s = self.st()
        self.assertEqual(s['popup']['offwork']['name'], '하율')
        self.assertEqual(self.cards(), [])
        self.cmd('session.end')
        self.assertEqual(self.st()['home']['goals'], {'하율': 10})          # 목표는 남는다

    def test_hell(self):
        self.cmd('score.add', name='서아', delta=7)
        c, r = self.cmd('hell.start')
        self.assertEqual(c, 200, r)
        s = self.st()
        h = s['hell']
        self.assertEqual(h['goals'], {'서아': 50, '하율': 40, '채원': 30})   # 지금 점수 순 · 같으면 줄 순서
        self.assertTrue(h['on'] and h['shown'])
        self.assertIsNone(s['show']['stage'])                              # 무대는 안 건드린다
        self.cmd('hell.goal', name='채원', goal=3)
        self.cmd('score.add', name='채원', delta=3)
        self.assertEqual(self.cards(), [('채원', 'hell')])
        self.cmd('hell.goal', name='채원', goal=10)                         # 목표를 올리면 다시 진행 중
        self.assertNotIn('채원', self.st()['hell']['escaped'])
        self.cmd('hell.start')                                               # 다시 시작하면 지난 카드는 걷는다
        self.assertEqual(self.cards(), [])
        self.assertEqual(self.cmd('hell.goal', name='없음', goal=1)[0], 404)

    # ── repro: undo — 잘못 배정 → 탈출 카드 → 되돌리기 ──
    def test_undo_takes_back_false_escape(self):
        self.cmd('score.add', name='서아', delta=10)
        self.cmd('hell.start', targets=[20, 15, 10, 5])
        self.cmd('score.add', name='서아', delta=25)
        self.assertEqual(self.cards(), [('서아', 'hell')])
        self.cmd('score.undo')
        s = self.st()
        self.assertEqual(s['hell']['escaped'], [])                          # 거짓 탈출이 풀린다
        self.assertEqual(self.cards(s), [])                                 # 안 보낸 카드는 걷힌다
        self.cmd('score.add', name='서아', delta=20)                        # 진짜로 채우면 카드가 다시 온다
        self.assertEqual(self.cards(), [('서아', 'hell')])
        self.assertEqual(self.st()['hell']['escaped'], ['서아'])

    def test_undo_after_send_then_real_reach(self):
        """송출한 뒤 되돌리기 → 진짜로 채우면 카드가 다시(옛 것은 escaped 에 이름이 남아 영영 안 왔다)."""
        self.cmd('hell.start', targets=[20, 15, 10, 5])
        self.cmd('score.add', name='하율', delta=40)
        self.cmd('offwork.send', id=self.card_id('하율', 'hell'))
        self.cmd('score.undo')
        self.assertNotIn('하율', self.st()['hell']['escaped'])
        self.cmd('score.add', name='하율', delta=40)
        self.assertEqual(self.cards(), [('하율', 'hell')])

    def test_undo_home(self):
        self.cmd('home.goal', name='채원', goal=5)
        self.cmd('home.on', on=True)
        self.cmd('score.add', name='채원', delta=5)
        self.assertEqual(self.cards(), [('채원', 'home')])
        self.cmd('score.undo')
        s = self.st()
        self.assertEqual((s['home']['notified'], self.cards(s)), ([], []))

    def test_undo_of_donation_assign(self):
        """후원 배정을 되돌려도(후원은 대기함으로 돌아온다) 탈출 카드는 걷힌다."""
        self.cmd('hell.start', targets=[3, 3, 3, 3])
        self.don('별빛', 50000, 'toon_r1')
        pid = next(d['id'] for d in self.st()['pending'] if d.get('type') != 'off_work')
        c, r = self.cmd('pending.assign', id=pid, name='하율')
        self.assertEqual(c, 200, r)
        self.assertEqual(self.cards(), [('하율', 'hell')])
        self.cmd('score.undo')
        s = self.st()
        self.assertEqual(self.cards(s), [])
        self.assertEqual(len([d for d in s['pending'] if d.get('type') != 'off_work']), 1)

    # ── repro: goalraise · goalzero ──
    def test_goal_raise_takes_back_card(self):
        self.cmd('hell.start')
        self.cmd('hell.goal', name='채원', goal=1)
        self.cmd('score.add', name='채원', delta=1)
        self.assertEqual(self.cards(), [('채원', 'hell')])
        self.cmd('hell.goal', name='채원', goal=30)
        s = self.st()
        self.assertEqual((s['hell']['escaped'], self.cards(s)), ([], []))
        # 퇴근빵도 같다
        self.cmd('home.goal', name='서아', goal=2)
        self.cmd('home.on', on=True)
        self.cmd('score.add', name='서아', delta=2)
        self.assertIn(('서아', 'home'), self.cards())
        self.cmd('home.goal', name='서아', goal=9)
        self.assertNotIn(('서아', 'home'), self.cards())

    def test_goal_zero_is_no_goal(self):
        self.cmd('hell.start', targets=[20, 15, 10, 0])
        self.cmd('score.add', name='하율', delta=1)
        self.assertEqual(self.cards(), [])                                  # 목표 0 = 판정 안 함
        self.cmd('hell.goal', name='채원', goal=0)
        self.assertEqual(self.st()['hell']['escaped'], [])
        self.cmd('hell.goal', name='채원', goal=1)
        self.cmd('score.add', name='채원', delta=1)
        self.assertEqual(self.cards(), [('채원', 'hell')])
        self.cmd('hell.goal', name='채원', goal=0)                          # 탈출했다가 목표를 지우면 카드도 걷는다
        self.assertEqual(self.cards(), [])

    # ── repro: extra — 번외 판 점수는 본판에 합쳐질 때 센다(옛 것과 같다) ──
    def test_extra_counts_when_merged(self):
        self.cmd('hell.start', targets=[5, 5, 5, 5])
        self.cmd('extra.start')
        self.cmd('score.add', name='채원', delta=30)                        # 번외 판으로 간다
        self.assertEqual(self.cards(), [])                                  # 번외 판 점수는 아직 안 센다
        self.cmd('extra.end')                                               # 본판에 합쳐짐 → 바로 카드
        self.assertEqual(self.cards(), [('채원', 'hell')])

    def test_extra_cancel_no_card(self):
        self.cmd('home.goal', name='하율', goal=3)
        self.cmd('home.on', on=True)
        self.cmd('extra.start')
        self.cmd('score.add', name='하율', delta=9)
        self.cmd('extra.cancel')
        self.assertEqual(self.cards(), [])

    # ── repro: rename ──
    def test_rename_follows(self):
        self.cmd('home.goal', name='서아', goal=50)
        self.cmd('hell.start', targets=[10, 10, 10, 10])
        self.cmd('score.add', name='채원', delta=10)
        self.assertEqual(self.cards(), [('채원', 'hell')])
        self.cmd('players.rename', **{'from': '채원', 'to': '채원2'})
        self.cmd('players.rename', **{'from': '서아', 'to': '서아님'})
        s = self.st()
        self.assertIn('채원2', s['hell']['goals'])
        self.assertIn('채원2', s['hell']['base'])
        self.assertEqual(s['hell']['escaped'], ['채원2'])
        self.assertEqual(self.cards(s), [('채원2', 'hell')])                # 카드 이름도
        self.assertEqual(s['home']['goals'], {'서아님': 50})
        self.cmd('score.add', name='하율', delta=10)
        self.assertEqual(sorted(self.cards()), [('채원2', 'hell'), ('하율', 'hell')])

    # ── repro: stage — 다른 게임을 켜도 지옥 · 퇴근이 안 꺼진다 ──
    def test_other_games_dont_turn_off(self):
        self.cmd('hell.start', targets=[20, 15, 10, 5])
        self.cmd('roulette.spin')
        s = self.st()
        self.assertEqual(s['show']['stage'], 'roulette')
        self.assertIsNone(s['show']['ret'])                                 # 돌아갈 무대가 없다(지옥은 무대가 아니다)
        self.assertTrue(s['hell']['on'] and s['hell']['shown'])
        self.cmd('roulette.reset')
        self.assertIsNone(self.st()['show']['stage'])
        self.cmd('match.open')
        self.assertTrue(self.st()['hell']['shown'])
        self.cmd('match.close')
        s = self.st()
        self.assertIsNone(s['show']['stage'])
        self.assertTrue(s['hell']['on'] and s['hell']['shown'])            # 대결이 끝나도 그대로 떠 있다

    def test_hell_show_hide_keeps_record(self):
        self.cmd('hell.start', targets=[20, 15, 10, 5])
        self.cmd('score.add', name='하율', delta=3)
        self.cmd('hell.show', on=False)
        s = self.st()
        self.assertTrue(s['hell']['on'])
        self.assertFalse(s['hell']['shown'])
        self.cmd('score.add', name='하율', delta=20)                        # 숨긴 동안에도 센다
        self.assertEqual(self.cards(), [('하율', 'hell')])
        self.cmd('hell.show', on=True)
        self.assertTrue(self.st()['hell']['shown'])
        self.cmd('session.end')
        self.cmd('session.start', names=['하율'])
        self.assertEqual(self.cmd('hell.show', on=True)[0], 409)            # 시작 전이면 '먼저 시작'

    def test_hell_off_then_resume(self):
        self.cmd('hell.start', targets=[20, 15, 10, 5])
        base = self.st()['hell']['base']
        self.cmd('hell.off')
        s = self.st()
        self.assertFalse(s['hell']['on'] or s['hell']['shown'])
        self.assertEqual(s['hell']['base'], base)                           # 기록은 남는다
        self.cmd('score.add', name='채원', delta=50)
        self.assertEqual(self.cards(), [])                                  # 끝낸 동안은 카드 없음
        self.cmd('hell.resume')
        s = self.st()
        self.assertTrue(s['hell']['on'] and s['hell']['shown'])
        self.assertEqual(s['hell']['base'], base)
        self.assertEqual(self.cards(s), [('채원', 'hell')])                  # 이어서 세면 바로 판정

    def test_old_stage_names_become_switches(self):
        """옛 순서표 · 무대 단추가 보내는 show.stage 'hell' · 'home_race' — 무대는 그대로, 스위치만."""
        c, r = self.cmd('show.stage', stage='hell')
        self.assertEqual(c, 409, r)                                         # 시작 전이면 '먼저 시작'
        self.cmd('match.open')
        c, r = self.cmd('show.stage', stage='home_race')
        self.assertEqual(c, 200, r)
        self.assertEqual(r.get('race'), 'home_race')
        s = self.st()
        self.assertTrue(s['home']['on'])
        self.assertEqual(s['show']['stage'], 'match')                       # 대결은 안 내려간다
        self.cmd('hell.start')
        self.cmd('hell.off')
        self.cmd('show.stage', stage='hell')                                # 끝낸 지옥 → 이어서(옛 /api/show 와 같다)
        s = self.st()
        self.assertTrue(s['hell']['on'] and s['hell']['shown'])
        self.assertEqual(s['show']['stage'], 'match')

    def test_home_off_during_roulette_stays_off(self):
        """퇴근빵 끄고 룰렛이 끝나도 다시 안 뜬다(옛 ret 로 돌아오던 것)."""
        self.cmd('home.on', on=True)
        self.cmd('roulette.spin')
        self.cmd('home.on', on=False)
        self.cmd('roulette.reset')
        s = self.st()
        self.assertFalse(s['home']['on'])
        self.assertIsNone(s['show']['stage'])

    def test_old_cue_with_race_stage(self):
        """옛 순서표 단계(무대 hell · home_race) — 그 판을 켜고 무대는 비운다. 시작 전 지옥이면 실패 없이 넘어간다."""
        bus = self.c.app.state.bus
        bus.state.slices['presets'] = {'list': [
            {'id': 'p1', 'name': '지옥', 'stage': 'hell', 'hud': {}},
            {'id': 'p2', 'name': '퇴근', 'stage': 'home_race', 'hud': {}},
            {'id': 'p3', 'name': '대결', 'stage': 'match', 'hud': {}}]}
        self.cmd('match.open')
        c, r = self.cmd('show.cue', dir='next')
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertFalse(s['hell']['on'])
        self.assertIsNone(s['show']['stage'])
        self.cmd('hell.start')
        self.cmd('hell.off')
        self.cmd('show.cue', dir='go', id='p1')
        self.assertTrue(self.st()['hell']['shown'])
        self.cmd('show.cue', dir='next')
        self.assertTrue(self.st()['home']['on'])
        self.cmd('show.cue', dir='next')                                    # 대결 단계 — 지옥 · 퇴근은 안 꺼진다
        s = self.st()
        self.assertEqual(s['show']['stage'], 'match')
        self.assertTrue(s['hell']['shown'] and s['home']['on'])

    def test_migrate_saved_stage(self):
        """10-17 전 저장본 — 무대에 hell 이 있고 hell 조각에 shown 이 없다 → 다음 명령에서 무대를 비우고 보이게."""
        self.cmd('hell.start')
        bus = self.c.app.state.bus
        h = dict(bus.state.slices['hell'])
        h.pop('shown')
        bus.state.slices['hell'] = h
        bus.state.slices['show'] = dict(bus.state.slices['show'], stage='hell', ret=None)
        bus.state.slices['home'] = dict(bus.state.slices['home'], on=True)    # 옛 것: 켜졌지만 무대에 없어 안 보이던 퇴근빵
        self.cmd('notice.every', period=300)
        s = self.st()
        self.assertIsNone(s['show']['stage'])
        self.assertTrue(s['hell']['on'] and s['hell']['shown'])
        self.assertFalse(s['home']['on'])
        # 룰렛 뒤 돌아갈 자리(ret)에 남은 home_race
        bus.state.slices['show'] = dict(bus.state.slices['show'], stage='roulette', ret='home_race')
        self.cmd('notice.every', period=300)
        s = self.st()
        self.assertEqual((s['show']['stage'], s['show']['ret']), ('roulette', None))
        self.assertTrue(s['home']['on'])

    # ── repro: restart — 방송을 끝냈다 다시 시작하면 퇴근빵은 꺼진다(목표는 남김) ──
    def test_restart_turns_home_off(self):
        self.cmd('home.goal', name='서아', goal=5)
        self.cmd('home.on', on=True)
        self.cmd('hell.start')
        self.cmd('session.end')
        self.cmd('session.start', names=['서아', '하율'])
        s = self.st()
        self.assertFalse(s['home']['on'])
        self.assertEqual(s['home']['goals'], {'서아': 5})
        self.assertFalse(s['hell']['on'] or s['hell']['shown'])

    # ── repro: neg — 이상한 목표 ──
    def test_bad_goals(self):
        self.assertEqual(self.cmd('hell.start', targets=['abc'])[0], 400)
        c, r = self.cmd('hell.start', targets=[])
        self.assertEqual(c, 200, r)
        self.assertEqual(sorted(self.st()['hell']['goals'].values()), [30, 40, 50])
        self.cmd('hell.start', targets=[-5, 1e12])
        g = self.st()['hell']['goals']
        self.assertEqual(sorted(g.values()), [0, 100000, 100000])           # 0 ~ 10만으로 자른다
        for bad in ('nan', 'inf', '-inf', None, 'x'):
            self.assertEqual(self.cmd('hell.goal', name='서아', goal=bad)[0], 400, bad)
            self.assertEqual(self.cmd('home.goal', name='서아', goal=bad)[0], 400, bad)
        self.assertEqual(self.cmd('hell.start', targets='50')[0], 400)



@unittest.skipUnless(shutil.which('node'), 'node 가 없으면 건너뛴다')
class RaceOverlayJs(unittest.TestCase):
    """방송판 규칙(race_view.js · 계좌 비키기 · 층) — node 로 순수 함수만(v2/tests/js/races_check.mjs)."""

    def test_rules(self):
        p = subprocess.run(['node', os.path.join(HERE, 'js', 'races_check.mjs')], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr or p.stdout)
        self.assertTrue(p.stdout.startswith('ok'), p.stdout)


if __name__ == '__main__':
    unittest.main()
