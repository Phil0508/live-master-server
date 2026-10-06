# -*- coding: utf-8 -*-
"""v2 대결(match) — 옛 규칙(숫자 · 조건)이 그대로인지 본다.

시계는 가짜(bus.time)로 돌린다 — 3분짜리 판을 3분 기다리지 않게.
돌리기(저장소 루트에서):  python -m unittest v2.tests.test_match
"""
import types
import unittest
from unittest import mock

from v2.server import bus as busmod
from v2.server.bus import COMMANDS, command
from v2.server.domain import match  # noqa: F401  (대결 명령 · 조각을 등록한다)
from v2.server.domain import players as pl
from v2.server.domain import show as sh
from v2.tests.test_flow import Base

T0 = 1_800_000_000.0          # 가짜 시계 시작(초) — ms 로 바꿔도 딱 떨어지게 정수 · 0.5 단위로만 움직인다
TIMER0 = {'running': False, 'end_ms': 0, 'left_ms': 180000, 'restart_ms': 180000, 'held': False, 'ended_at': 0}


@command('t.mx_roulette')
def _t_roulette(ctx, data):
    """룰렛이 대결 위에 잠깐 올라왔다 내려간다(show 의 잠깐 무대) — 검사용."""
    if data.get('end'):
        sh.end_temp(ctx, 'roulette')
    else:
        sh.set_stage(ctx, 'roulette', temp=True)


def _after(fn):
    """bus.AFTER 가 생기기 전까지 — 보고서에 적은 모양 그대로(명령 처리 뒤 · 같은 장부 안에서) 흉내 낸다."""
    def run(ctx, data):
        fn(ctx, data)
        match.follow_reaction(ctx)
    return run


class MatchBase(Base):
    def setUp(self):
        self.t = T0
        p = mock.patch.object(busmod, 'time', types.SimpleNamespace(time=lambda: self.t))
        p.start()
        self.addCleanup(p.stop)
        if not hasattr(busmod, 'AFTER'):
            q = mock.patch.dict(COMMANDS, {k: (_after(fn), a) for k, (fn, a) in COMMANDS.items()})
            q.start()
            self.addCleanup(q.stop)
        super().setUp()                                  # 하율 · 서아 · 채원 으로 방송 시작

    # ── 도구 ──
    def ok(self, t, **data):
        c, r = self.cmd(t, **data)
        self.assertEqual(c, 200, (t, r))
        return r

    def pub(self, t, **data):
        """방송판(로그인 없음)이 보내는 명령."""
        r = self.c.post('/api/cmd', json={'type': t, 'data': data})
        return r.status_code, r.json()

    def m(self, s=None):
        return (s or self.st())['match']

    def team(self, tid, s=None):
        return next(x for x in self.m(s)['teams'] if x['id'] == tid)

    def score(self, tid):
        return self.team(tid)['score']

    def timer(self):
        return self.m()['timer']

    def ms(self):
        return int(self.t * 1000)

    def tick(self, sec):
        self.t += sec

    def two(self, link=None):
        self.ok('match.open')
        a = self.ok('match.add_team', name='A')['id']
        b = self.ok('match.add_team', name='B')['id']
        if link:
            self.ok('match.link', mode=link)
        return a, b

    def sig_don(self, name, tx):
        """2만 원 후원 → 시그니처 '뿅뿅' 이 대기줄에 들어간다(리액션 시작)."""
        c, r = self.don(name, 20000, tx)
        self.assertEqual(c, 200, r)

    def head_done(self):
        q = self.st()['queue']['items']
        c, r = self.pub('reaction.done', id=q[0]['id'])
        self.assertEqual(c, 200, r)


class Open(MatchBase):
    def test_defaults_and_public(self):
        m = self.m()
        self.assertEqual((m['active'], m['teams'], m['link'], m['fire'], m['timer']), (False, [], 'off', False, TIMER0))
        pub = self.st(auth=False)
        self.assertIn('match', pub)                                       # 방송판이 그린다
        self.assertNotIn('match_logs', pub)                               # 기록은 조종실만

    def test_open_close_stage(self):
        self.ok('match.open', title='  라이벌   전 ')
        s = self.st()
        self.assertEqual((s['match']['active'], s['match']['title'], s['show']['stage']), (True, '라이벌 전', 'match'))
        self.ok('show.stage', stage='dicegame')                           # 무대를 바꿔도 대결은 안 끝난다
        self.assertTrue(self.m()['active'])
        self.ok('match.open')
        self.assertEqual(self.st()['show']['stage'], 'match')
        # 룰렛이 대결 위에 잠깐 — 그 사이 대결을 끄면, 룰렛이 끝나도 대결로 안 돌아간다
        self.ok('t.mx_roulette')
        self.assertEqual((self.st()['show']['stage'], self.st()['show']['ret']), ('roulette', 'match'))
        self.ok('match.close')
        s = self.st()
        self.assertEqual((s['match']['active'], s['show']['stage'], s['show']['ret']), (False, 'roulette', None))
        self.ok('t.mx_roulette', end=True)
        self.assertIsNone(self.st()['show']['stage'])
        self.ok('match.open')
        self.ok('match.close')
        self.assertIsNone(self.st()['show']['stage'])
        self.assertTrue(self.ok('match.close').get('already'))

    def test_close_freezes_clock(self):
        self.ok('match.open')
        self.ok('match.start')
        self.tick(30)
        self.ok('match.close')
        self.assertEqual((self.timer()['running'], self.timer()['left_ms']), (False, 150000))
        self.tick(100)
        self.ok('match.open')                                             # 다시 켜도 멈춘 그대로 — '시간종료' 가 안 터진다
        self.assertEqual((self.timer()['running'], self.timer()['left_ms']), (False, 150000))

    def test_title_fire(self):
        self.ok('match.title', title='가' * 50)
        self.assertEqual(self.m()['title'], '가' * 40)
        self.ok('match.fire', on=True)
        self.assertTrue(self.m()['fire'])
        self.ok('match.fire')
        self.assertFalse(self.m()['fire'])


class Teams(MatchBase):
    def test_add_limit_rename_remove(self):
        self.ok('match.open')
        ids = [self.ok('match.add_team')['id'] for _ in range(4)]
        self.assertEqual([t['name'] for t in self.m()['teams']], ['Player'] * 4)
        self.assertEqual(self.cmd('match.add_team')[0], 400)              # 4명(팀)까지
        self.ok('match.rename_team', id=ids[0], to='  팀   A ')
        self.assertEqual(self.team(ids[0])['name'], '팀 A')
        self.assertEqual(self.cmd('match.rename_team', id=ids[0], to='  ')[0], 400)
        self.assertEqual(self.cmd('match.score', name='Player', delta=1)[0], 409)   # 'Player' 가 셋 — 이름으로는 못 고른다
        self.ok('match.score', name='팀 A', delta=1)
        self.ok('match.remove_team', id=ids[3])
        self.assertEqual(len(self.m()['teams']), 3)
        self.assertEqual(self.cmd('match.remove_team', id='nope')[0], 404)

    def test_rename_keeps_score_and_members(self):
        a, b = self.two('team')
        self.ok('match.member', id=a, member='하율')
        self.ok('match.score', id=a, delta=5)
        self.ok('match.rename_team', id=a, to='B팀')                       # 옛 '개명 짐작' 없이도 점수 · 팀원 그대로
        t = self.team(a)
        self.assertEqual((t['name'], t['score'], t['members']), ('B팀', 5, ['하율']))

    def test_member_unknown_changes_nothing(self):
        a, b = self.two('team')
        before = self.st()
        self.assertEqual(self.cmd('match.member', id=a, member='없는사람')[0], 404)
        self.assertEqual(self.cmd('match.member', id=a, member=' ')[0], 400)
        self.assertEqual(self.st()['match'], before['match'])


class Score(MatchBase):
    def test_manual_score_log_popup_undo(self):
        a, b = self.two()
        r = self.ok('match.score', id=a, delta=3)
        self.assertTrue(r['ref'].startswith('mx_'))
        s = self.st()
        self.assertEqual(self.team(a, s)['score'], 3)
        row = s['match_logs'][0]
        self.assertEqual({k: row[k] for k in ('team', 'name', 'val', 'before', 'after', 'kind')},
                         {'team': a, 'name': 'A', 'val': 3, 'before': 0, 'after': 3, 'kind': 'manual'})
        self.assertEqual(s['popup']['score'], {'name': 'A', 'diff': 3, 'at': self.ms()})   # 올리면 점수 팝업
        at = self.ms()
        self.tick(1)
        self.ok('match.score', id=b, delta=-2)                            # 빼기는 팝업 없음
        self.ok('match.score', name='A', delta='4', popup=False)
        s = self.st()
        self.assertEqual((self.team(a, s)['score'], self.team(b, s)['score']), (7, -2))
        self.assertEqual(s['popup']['score']['at'], at)
        self.assertEqual(s['players']['list'][0]['score'], 0)             # 점수판(후원판)과는 별개
        self.ok('match.undo')                                             # 마지막 손 점수(A +4)
        self.assertEqual(self.score(a), 3)
        self.ok('match.undo', ref=r['ref'])                               # 골라서(A +3)
        self.assertEqual(self.score(a), 0)
        self.ok('match.undo')                                             # B −2
        self.assertEqual(self.score(b), 0)
        self.assertEqual(self.cmd('match.undo')[0], 404)
        self.assertEqual(self.cmd('match.undo', ref=r['ref'])[0], 404)
        self.assertEqual(self.st()['match_logs'], [])

    def test_bad_score_changes_nothing(self):
        a, b = self.two()
        self.ok('match.score', id=a, delta=2)
        before = self.st()
        for bad in (0, 1.5, 'abc', '3점', '١٢', True, None):
            self.assertEqual(self.cmd('match.score', id=a, delta=bad)[0], 400, bad)
        self.assertEqual(self.cmd('match.score', id='nope', delta=1)[0], 404)
        s = self.st()
        self.assertEqual((s['match'], s['match_logs']), (before['match'], before['match_logs']))
        self.ok('match.score', id=a, delta=' 1,000 ')                    # 쉼표는 받는다(옛 칸과 같다)
        self.assertEqual(self.score(a), 1002)

    def test_reset_new_round(self):
        a, b = self.two('team')
        self.ok('match.member', id=a, member='하율')
        self.ok('match.score', id=a, delta=5)
        self.ok('match.score', id=b, delta=2)
        self.ok('match.reset')
        s = self.st()
        m = s['match']
        self.assertEqual([(t['name'], t['score'], t['members']) for t in m['teams']], [('A', 0, ['하율']), ('B', 0, [])])
        self.assertEqual((m['lead'], m['gap'], m['flash'], s['match_logs']), ([], None, None, []))


class Timer(MatchBase):
    def test_start_pause_resume(self):
        self.ok('match.open')
        T = self.ms()
        self.ok('match.start')
        self.assertEqual(self.timer(), dict(TIMER0, running=True, end_ms=T + 180000))
        self.assertTrue(self.ok('match.start').get('already'))            # 두 번 눌러도 한 번
        self.tick(30)
        self.ok('match.pause')
        self.assertEqual((self.timer()['running'], self.timer()['left_ms']), (False, 150000))
        self.assertTrue(self.ok('match.pause').get('already'))
        self.tick(100)                                                    # 멈춘 동안은 안 흐른다
        self.ok('match.start')
        self.assertEqual(self.timer()['end_ms'], self.ms() + 150000)

    def test_add_time(self):
        self.ok('match.open')
        T = self.ms()
        self.ok('match.start')
        self.ok('match.add_time', sec=60)
        self.assertEqual(self.timer()['end_ms'], T + 240000)              # 도는 중 → 끝 시각을 민다
        self.ok('match.add_time', sec='-30')
        self.assertEqual(self.timer()['end_ms'], T + 210000)
        self.tick(10)
        self.ok('match.pause')
        self.assertEqual(self.timer()['left_ms'], 200000)
        self.ok('match.add_time', sec=-60)                                # 멈춤 → 남은 시간 · 다음 시작 시간
        self.assertEqual((self.timer()['left_ms'], self.timer()['restart_ms']), (140000, 140000))
        self.ok('match.add_time', sec=-600)                               # 0 밑으로 안 간다 · 다음 시작 시간은 그대로
        self.assertEqual((self.timer()['left_ms'], self.timer()['restart_ms']), (0, 140000))
        self.ok('match.start')
        self.assertEqual(self.timer()['end_ms'], self.ms() + 140000)
        for bad in (0, 1.5, 'x'):
            self.assertEqual(self.cmd('match.add_time', sec=bad)[0], 400, bad)

    def test_set_time(self):
        self.ok('match.open')
        self.ok('match.set_time', min=2, sec=90)                          # 초 칸 60 이상은 분으로 — 3분 30초
        self.assertEqual(self.timer(), dict(TIMER0, left_ms=210000, restart_ms=210000))
        self.ok('match.set_time', sec=45)                                 # 빈 칸은 0
        self.assertEqual(self.timer()['left_ms'], 45000)
        self.ok('match.start')
        self.tick(5)
        self.ok('match.set_time', min=1)                                  # 도는 중 → 그 시간부터 이어서
        self.assertEqual((self.timer()['running'], self.timer()['end_ms'], self.timer()['restart_ms']),
                         (True, self.ms() + 60000, 60000))
        self.ok('match.set_time', min=180)                                # 세 시간까지
        self.assertEqual(self.timer()['restart_ms'], 10800000)
        for bad in ({'min': 180, 'sec': 1}, {'min': 0, 'sec': 0}, {'min': '', 'sec': ''}, {'sec': -1}, {'min': 'x'}, {'min': 1.5}):
            self.assertEqual(self.cmd('match.set_time', **bad)[0], 400, bad)

    def test_reset_time(self):
        self.ok('match.open')
        self.ok('match.set_time', min=5)
        self.ok('match.start')
        self.tick(10)
        self.ok('match.reset_time')                                       # 멈추고 3분(맞춘 5분이 아니라)
        self.assertEqual(self.timer(), TIMER0)

    def test_command_after_end_time_ends_round(self):
        self.ok('match.open')
        T = self.ms()
        self.ok('match.start')
        self.tick(180.5)
        self.assertTrue(self.timer()['running'])                          # 아무도 안 물었으면 아직 '도는 중'(화면이 셈)
        self.ok('match.title', title='결승')                               # 끝 시각 뒤에 온 명령 → 서버가 판을 끝낸다
        self.assertEqual(self.timer(), dict(TIMER0, end_ms=T + 180000, left_ms=0, ended_at=T + 180000))
        self.ok('match.start')                                            # 다시 시작 → 마지막으로 맞춘 시간부터
        self.assertEqual((self.timer()['end_ms'], self.timer()['ended_at']), (self.ms() + 180000, 0))

    def test_timeup_from_overlay(self):
        self.ok('match.open')
        T = self.ms()
        self.ok('match.start')
        self.tick(170)
        c, r = self.pub('match.timeup')                                   # 10초나 이르다 → 거절, 아무것도 안 바뀐다
        self.assertEqual(c, 409, r)
        self.assertEqual((self.timer()['running'], self.timer()['end_ms']), (True, T + 180000))
        self.tick(8)                                                      # 2초 이른 것은 시계 차이로 본다(3초까지)
        c, r = self.pub('match.timeup')
        self.assertEqual(c, 200, r)
        self.assertEqual(self.timer(), dict(TIMER0, end_ms=T + 180000, left_ms=0, ended_at=T + 178000))
        self.assertTrue(self.pub('match.timeup')[1].get('ignored'))       # 이미 끝났다
        self.assertEqual(self.pub('match.end')[0], 401)                   # 방송판은 timeup 말고는 못 한다
        self.assertEqual(self.pub('match.start')[0], 401)

    def test_timeup_ignored_when_closed(self):
        self.ok('match.start')                                            # 대결을 안 열고 시계만 돌린 것
        self.tick(181)
        self.assertTrue(self.pub('match.timeup')[1].get('ignored'))

    def test_end_now(self):
        self.ok('match.open')
        T = self.ms()
        self.ok('match.start')
        self.tick(10)
        self.ok('match.end')
        self.assertEqual(self.timer(), dict(TIMER0, end_ms=T + 180000, left_ms=0, ended_at=T + 10000))
        self.assertTrue(self.ok('match.end').get('already'))

    def test_minus_time_past_end_ends_round(self):
        self.ok('match.open')
        T = self.ms()
        self.ok('match.start')
        self.tick(150)                                                    # 30초 남았는데 −1분
        self.ok('match.add_time', sec=-60)
        self.assertEqual(self.timer(), dict(TIMER0, end_ms=T + 120000, left_ms=0, ended_at=T + 150000))


class Link(MatchBase):
    def assign(self, amount, tx, **who):
        self.don('별빛', amount, tx)
        pid = self.st()['pending'][-1]['id']
        self.ok('pending.assign', id=pid, **who)
        return pid

    def test_team_link_follows_points(self):
        a, b = self.two('team')
        self.ok('match.member', id=a, member='하율')
        self.ok('match.member', id=a, member='서아')
        self.ok('match.member', id=b, member='채원')
        self.assign(50000, 'toon_l1', name='서아')                         # 5점 → A 팀 +5
        self.assertEqual((self.score(a), self.score(b)), (5, 0))
        pid = self.assign(30000, 'toon_l2', names=['하율', '채원'])        # 나눠 주기 [2, 1]
        self.assertEqual((self.score(a), self.score(b)), (7, 1))
        rows = [r for r in self.st()['match_logs'] if r['ref'] == pid]
        self.assertEqual(sorted((r['kind'], r['member'], r['val']) for r in rows), [('link', '채원', 1), ('link', '하율', 2)])
        self.assertTrue(all(isinstance(r['src'], int) for r in rows))
        self.ok('score.add', name='하율', delta=-1)                        # 빼기도 따라간다
        self.ok('score.add', name='채원', delta=0, contrib=7)               # 기여도만 → 안 따라간다
        self.ok('score.add', target='bottom', delta=4)                    # 운영비 → 안 따라간다
        self.assertEqual((self.score(a), self.score(b)), (6, 1))

    def test_undo_takes_from_team_at_the_time(self):
        a, b = self.two('team')
        self.ok('match.member', id=a, member='하율')
        self.ok('match.member', id=b, member='채원')
        pid = self.assign(30000, 'toon_u1', name='채원')
        self.assertEqual(self.score(b), 3)
        self.ok('match.member', id=a, member='채원')                       # 채원을 A 팀으로 옮긴다
        self.assertEqual((self.team(a)['members'], self.team(b)['members']), (['하율', '채원'], []))
        self.ok('score.undo')                                             # B 에서 빠져야 한다(09-30 재현: A 에서 빠졌다)
        s = self.st()
        self.assertEqual((self.team(a, s)['score'], self.team(b, s)['score']), (0, 0))
        self.assertEqual([x['id'] for x in s['pending']], [pid])          # 후원은 대기함으로
        self.assertEqual([r for r in s['match_logs'] if r['ref'] == pid], [])
        self.ok('pending.assign', id=pid, name='채원')                     # 다시 주면 지금 소속(A)으로
        self.assertEqual((self.score(a), self.score(b)), (3, 0))

    def test_no_follow_when_off_or_closed(self):
        a, b = self.two('team')
        self.ok('match.member', id=a, member='하율')
        self.ok('match.link', mode='off')
        self.ok('score.add', name='하율', delta=5)
        self.assertEqual(self.score(a), 0)
        self.ok('match.link', mode='team')
        self.ok('match.close')
        self.ok('score.add', name='하율', delta=5)
        self.assertEqual(self.score(a), 0)
        self.ok('match.open')
        self.ok('score.add', name='하율', delta=2)
        self.assertEqual(self.score(a), 2)
        self.assertEqual(self.cmd('match.link', mode='both')[0], 400)

    def test_extra_board_follows(self):
        a, b = self.two('team')
        self.ok('match.member', id=a, member='서아')
        self.ok('extra.start')
        self.assign(20000, 'toon_e1', name='서아')                         # 번외 판에 들어간 점수도 따라간다
        s = self.st()
        self.assertEqual(self.player('서아', s)['score'], 0)
        self.assertEqual(self.team(a, s)['score'], 2)

    def test_solo_rules(self):
        self.ok('match.open')
        self.ok('match.link', mode='solo')
        a = self.ok('match.add_team')['id']
        b = self.ok('match.add_team')['id']
        self.ok('match.member', id=a, member='하율')                       # 'Player' → 고른 사람 이름
        self.assertEqual((self.team(a)['name'], self.team(a)['members']), ('하율', ['하율']))
        self.ok('match.member', id=a, member='서아')                       # 한 명만 · 전 사람 이름 그대로였으면 바꾼다
        self.assertEqual((self.team(a)['name'], self.team(a)['members']), ('서아', ['서아']))
        self.ok('match.rename_team', id=a, to='라이벌')
        self.ok('match.member', id=a, member='채원')                       # 손으로 지은 이름은 안 바꾼다
        self.assertEqual((self.team(a)['name'], self.team(a)['members']), ('라이벌', ['채원']))
        self.ok('match.member', id=b, member='채원')                       # 다른 대결자에게 → 옮긴다
        self.assertEqual((self.team(a)['members'], self.team(b)['name'], self.team(b)['members']), ([], '채원', ['채원']))
        self.ok('match.member', id=b, member='채원', on=False)
        self.assertEqual(self.team(b)['members'], [])
        self.ok('match.link', mode='team')
        self.ok('match.member', id=a, member='하율')
        self.ok('match.member', id=a, member='서아')
        self.ok('match.member', id=a, member='하율')                       # 뒤집기 → 뺀다
        self.ok('match.member', id=a, member='하율')
        self.assertEqual(self.team(a)['members'], ['서아', '하율'])
        self.ok('match.link', mode='solo')                                # 팀전 → 개인전: 맨 앞 한 명만
        self.assertEqual(self.team(a)['members'], ['서아'])


class Reaction(MatchBase):
    def test_signature_freezes_and_resumes(self):
        self.ok('match.open')
        self.ok('match.start')
        self.tick(20)
        self.sig_don('별빛', 'toon_r1')                                    # 시그 시작 → 160초 남기고 얼린다
        self.assertEqual({k: self.timer()[k] for k in ('running', 'left_ms', 'held')},
                         {'running': False, 'left_ms': 160000, 'held': True})
        self.tick(9)
        self.head_done()                                                  # 방송판이 다 틀었다 → 대기줄이 비었다 → 이어서
        self.assertEqual({k: self.timer()[k] for k in ('running', 'end_ms', 'held')},
                         {'running': True, 'end_ms': self.ms() + 160000, 'held': False})

    def test_manual_pause_is_not_resumed(self):
        self.ok('match.open')
        self.ok('match.start')
        self.sig_don('별빛', 'toon_r2')
        self.ok('match.pause')                                            # 시그 중에 손으로 멈춤 → 끝나도 안 돈다
        self.head_done()
        self.assertEqual((self.timer()['running'], self.timer()['held']), (False, False))
        self.ok('match.start')
        self.ok('match.pause')                                            # 손으로 멈춘 시계는 시그가 와도 · 가도 그대로
        self.sig_don('별빛', 'toon_r3')
        self.head_done()
        self.assertEqual((self.timer()['running'], self.timer()['held']), (False, False))

    def test_start_during_signature_keeps_running(self):
        self.ok('match.open')
        self.sig_don('별빛', 'toon_r4')                                    # 시계가 멈춰 있을 때 시그 시작
        T = self.ms()
        self.ok('match.start')                                            # 시그 중에 손으로 시작 → 그대로 돈다
        self.tick(5)
        self.sig_don('달빛', 'toon_r5')                                    # 대기줄은 이미 차 있었다 — 바뀐 게 아니다
        self.assertTrue(self.timer()['running'])
        self.head_done()
        self.head_done()                                                  # 비었다 — 시그 때문에 멈춘 게 아니니 할 일 없음
        self.assertEqual((self.timer()['running'], self.timer()['end_ms'], self.timer()['held']), (True, T + 180000, False))

    def test_signature_after_time_up_ends_round(self):
        self.ok('match.open')
        T = self.ms()
        self.ok('match.start')
        self.tick(181)
        self.sig_don('별빛', 'toon_r6')                                    # 이미 시간이 지났다 → 얼리지 않고 끝낸다
        self.assertEqual(self.timer(), dict(TIMER0, end_ms=T + 180000, left_ms=0, ended_at=T + 180000))
        self.head_done()
        self.assertFalse(self.timer()['running'])                         # 옛 것은 여기서 3분부터 다시 돌았다

    def test_reset_time_cancels_hold(self):
        self.ok('match.open')
        self.ok('match.start')
        self.tick(10)
        self.sig_don('별빛', 'toon_r7')
        self.ok('match.reset_time')
        self.head_done()
        self.assertEqual(self.timer(), TIMER0)

    def test_time_taken_away_while_held(self):
        self.ok('match.open')
        self.ok('match.start')
        self.tick(150)
        self.sig_don('별빛', 'toon_r8')                                    # 30초 남기고 얼림
        self.ok('match.add_time', sec=-60)                                # 얼린 사이 −1분 → 0
        self.head_done()
        self.assertEqual((self.timer()['running'], self.timer()['left_ms'], self.timer()['held']), (False, 0, False))


class Board(MatchBase):
    def test_lead_gap_flash(self):
        a, b = self.two()
        m = self.m()
        self.assertEqual((m['lead'], m['gap'], m['flash']), ([], None, None))
        self.ok('match.score', id=a, delta=5)
        m = self.m()
        self.assertEqual((m['lead'], m['gap'], m['leader'], m['flash']), ([a], 5, a, None))   # 첫 1등은 '역전' 아님
        self.tick(1)
        self.ok('match.score', id=b, delta=5)
        m = self.m()
        self.assertEqual((m['lead'], m['gap'], m['flash']), ([a, b], 0, {'text': '동점!', 'at': self.ms()}))
        self.tick(1)
        self.ok('match.score', id=b, delta=1)
        m = self.m()
        self.assertEqual((m['lead'], m['gap'], m['leader'], m['flash']), ([b], 1, b, {'text': '역전!', 'at': self.ms()}))
        self.tick(1)
        self.ok('match.score', id=a, delta=1)
        self.assertEqual(self.m()['flash'], {'text': '동점!', 'at': self.ms()})
        self.tick(1)
        self.ok('match.score', id=a, delta=2)
        m = self.m()
        self.assertEqual((m['lead'], m['gap'], m['flash']), ([a], 2, {'text': '역전!', 'at': self.ms()}))

    def test_tie_broken_by_same_leader_is_not_a_flip(self):
        a, b = self.two()
        self.ok('match.score', id=a, delta=5)
        self.tick(1)
        self.ok('match.score', id=b, delta=5)
        tie = self.m()['flash']
        self.tick(1)
        self.ok('match.score', id=a, delta=1)                             # 동점 전 1등이 다시 앞섰다 → 역전 아님
        m = self.m()
        self.assertEqual((m['lead'], m['gap'], m['flash']), ([a], 1, tie))

    def test_three_teams_and_remove(self):
        self.ok('match.open')
        a, b, c = (self.ok('match.add_team', name=n)['id'] for n in ('A', 'B', 'C'))
        self.ok('match.score', id=a, delta=5)
        self.ok('match.score', id=b, delta=3)
        self.ok('match.score', id=c, delta=4)
        self.assertEqual((self.m()['lead'], self.m()['gap']), ([a], 1))      # 1위 − 2위
        self.tick(1)
        self.ok('match.score', id=c, delta=2)
        flip = {'text': '역전!', 'at': self.ms()}
        self.assertEqual((self.m()['lead'], self.m()['gap'], self.m()['flash']), ([c], 1, flip))
        self.tick(1)
        self.ok('match.remove_team', id=c)                                # 대결자가 줄었다 → 기억을 버린다(가짜 역전 없음)
        m = self.m()
        self.assertEqual((m['lead'], m['gap'], m['leader'], m['flash']), ([a], 2, a, flip))

    def test_negative_only_has_no_leader(self):
        a, b = self.two()
        self.ok('match.score', id=a, delta=-3)
        self.assertEqual((self.m()['lead'], self.m()['gap']), ([], None))


class Session(MatchBase):
    def test_session_end_and_start_reset(self):
        a, b = self.two('team')
        self.ok('match.member', id=a, member='하율')
        self.ok('match.score', id=a, delta=3)
        self.ok('match.start')
        self.ok('session.end')
        s = self.st()
        self.assertEqual((s['match'], s['match_logs'], s['show']['stage']), (match._default(), [], None))
        self.ok('session.start', names=['가', '나'])
        self.assertEqual(self.m(), match._default())


class Wiring(MatchBase):
    def test_hooks_registered(self):
        self.assertIn(match.follow_scores, pl.AFTER_SCORE)
        self.assertIn(match.undo_link, pl.ON_UNDO)

    @unittest.skipUnless(hasattr(busmod, 'AFTER'),
                         'bus.AFTER 고리가 아직 없다 — 운영에선 시그가 돌아도 대결 시계가 안 멈춘다(위 검사는 흉내로 돌렸다)')
    def test_after_hook_registered(self):
        self.assertIn(match.follow_reaction, busmod.AFTER)


if __name__ == '__main__':
    unittest.main()
