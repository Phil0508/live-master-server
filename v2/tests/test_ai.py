# -*- coding: utf-8 -*-
"""AI 서포트 — 사실표 · 즉답 · 상황판 · 후원자 기억 · 배정 제안 · 채팅. 옛 features/ai.py · ai_facts.py · donor_memory.py 와 같은 셈인지.

⚠️ 진짜 NVIDIA 는 절대 부르지 않는다 — 바깥으로 나가는 ai._http_post 를 '부르면 실패' 로 막고, ai.nim_post 를 가짜로 바꾼다.
   키도 가짜(ai.nim_key)다. 돌리기: python -m unittest discover -s v2/tests -t .
"""
import asyncio
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from v2.server.domain import ai_facts as af       # noqa: E402  (모듈을 먼저 불러야 주소 · 고리가 걸린다)
from v2.server.domain import donor_memory as dm
from v2.server.domain import ai
from v2.server.app import create_app
from v2.server.store import Store

PW, SECRET = 'testpw', 'testsecret-0123456789'
H = {'Authorization': 'Bearer ' + SECRET}
SIGS = [{'id': 1, 'amount': 10000, 'title': '사쿠란보', 'image_url': 'a.png', 'sound_url': 'a.mp3', 'duration': 8},
        {'id': 3, 'amount': 50000, 'title': '대박', 'image_url': 'c.png', 'sound_url': 'c.mp3', 'duration': 12}]
FAKE_KEY = 'test-key-not-real'
REAL_NIM_KEY = ai.nim_key


def _no_network(*a, **k):
    raise AssertionError('검사에서 진짜 NVIDIA 를 부르려 했다')


class FakeResp:
    def __init__(self, code=200, content='', reasoning=''):
        self.status_code = code
        self._c, self._r = content, reasoning

    def json(self):
        return {'choices': [{'message': {'content': self._c, 'reasoning_content': self._r}}]}


class FakeNim:
    """ai.nim_post 대신 — 부른 기록을 남기고 정해 둔 답을 차례로 돌려준다."""

    def __init__(self, *answers, delay=0.0):
        self.answers = list(answers)
        self.calls = []
        self.delay = delay

    def __call__(self, models, body, timeout):
        self.calls.append({'models': list(models), 'body': body, 'timeout': timeout})
        if self.delay:
            time.sleep(self.delay)
        a = self.answers.pop(0) if self.answers else (None, 503, models[-1])
        return a


def _guard(case, key=FAKE_KEY):
    """모든 검사 앞에 — 바깥 호출 막기 · 가짜 키 · 기억(캐시) · 한도 · 상태 비우기."""
    for p in (mock.patch.object(ai, '_http_post', _no_network),
              mock.patch.object(ai, 'nim_key', lambda: key),
              mock.patch.object(ai, 'NIM_HEALTH', {'ok': None, 'ms': 0, 'at': 0.0, 'model': '', 'code': 0}),
              mock.patch.object(ai, '_nim_calls', [])):
        p.start()
        case.addCleanup(p.stop)
    ai._SUGGEST_CACHE.clear()
    case.addCleanup(ai._SUGGEST_CACHE.clear)


def S(**over):
    """사실표 시험용 조각 묶음."""
    s = {
        'session': {'live': True, 'id': 's1'},
        'players': {'list': [{'name': '하율', 'score': 10, 'contribution': 12},
                             {'name': '서아', 'score': 8, 'contribution': 15},
                             {'name': '채원', 'score': 3, 'contribution': 3}],
                    'extra': [], 'extra_active': False, 'bottom': {'name': '운영비', 'score': 5}},
        'goal': {'target': 0, 'offset': 0},
        'popup': {'donation': None, 'score': None, 'takeover': None},
        'pending': [], 'logs': [], 'match': {'active': False, 'teams': [], 'timer': {}},
        'home': {'on': False, 'goals': {}, 'notified': []},
        'hell': {'on': False, 'started_at': 0, 'base': {}, 'goals': {}, 'escaped': []},
        'tallies': {'donors': {}, 'best': None, 'notice_donors': [], 'sigs': {}},
        'queue': {'items': []}, 'show': {'stage': None, 'ret': None},
        'slot': {'phase': 'idle'}, 'roulette': {'phase': 'idle', 'stop': None}, 'siggame': {'cards': []},
    }
    s.update(over)
    return s


# ══ ① 사실표 · 즉답 · 상황판 (순수) ══
class Facts(unittest.TestCase):
    NOW = 1_800_000_000.0

    def test_rank_by_contribution_and_gaps(self):
        f = af.build_facts(S(), now=self.NOW)
        self.assertEqual([r['이름'] for r in f['순위']], ['서아', '하율', '채원'])
        self.assertEqual(f['순위'][1]['윗순위와_기여도차'], 3)
        self.assertEqual(f['순위'][1]['윗순위와_점수차'], -2)
        self.assertEqual((f['방송'], f['판']), ('진행 중', '본게임'))
        ans = af.quick_answer('rank', f)
        self.assertTrue(ans.startswith('1등은 **서아** — 기여도 15 (점수 8)'))
        self.assertIn('- 2등 하율 12 (점수 10) · 윗순위와 3 차', ans)

    def test_extra_board_ranks_but_goal_uses_main(self):
        p = S()['players']
        p.update(extra_active=True, extra=[{'name': '하율', 'score': 1, 'contribution': 1},
                                           {'name': '채원', 'score': 4, 'contribution': 4}])
        f = af.build_facts(S(players=p, goal={'target': 100, 'offset': 2}), now=self.NOW)
        self.assertEqual(f['판'], '임시게임(엑스트라)')
        self.assertEqual([r['이름'] for r in f['순위']], ['채원', '하율'])          # 순위는 번외 판
        self.assertEqual(f['목표']['현재점수'], 5 + 10 + 8 + 3 + 2)                # 목표는 운영비 + 본판 + 보정
        self.assertEqual(af.current_names(S(players=p)), ['하율', '채원'])

    def test_goal_and_celebrate_approval(self):
        f = af.build_facts(S(goal={'target': 20, 'offset': 0}), now=self.NOW)
        g = f['목표']
        self.assertEqual((g['현재점수'], g['남은점수'], g['달성'], g['달성률']), (26, 0, True, '130%'))
        self.assertTrue(g['연출_승인_대기'])
        f2 = af.build_facts(S(goal={'target': 20, 'offset': 0},
                              popup={'goal': {'at': 1, 'target': 20}}), now=self.NOW)
        self.assertFalse(f2['목표']['연출_승인_대기'])                            # goal.celebrate 를 눌렀다
        f3 = af.build_facts(S(goal={'target': 50, 'offset': 0}), now=self.NOW)
        self.assertEqual(f3['목표']['남은점수'], 24)
        self.assertIn('목표까지 **24점** 남았어요 (24만 원)', af.quick_answer('goal', f3))
        self.assertEqual(af.build_facts(S(), now=self.NOW)['목표'], '목표 없음')

    def test_pending_points_wait_and_cached_suggestion(self):
        ms = int((self.NOW - 4 * 60) * 1000)
        pend = [{'id': 'don_%d_ab12' % ms, 'name': '별빛', 'amount': 35000, 'message': '하율 화이팅', 'at': ms},
                {'id': 'dg_1_x', 'name': '🎲 주사위', 'amount': 0, 'message': '', 'kind': 'contrib', 'contrib': 5},
                {'id': 'off_1', 'type': 'off_work', 'name': '하율', 'amount': 0, 'message': '퇴근 성공'}]
        seen = []

        def look(d):
            seen.append(d['id'])
            return {'target': '하율', 'tier': 'auto', 'confidence': 0.97}
        f = af.build_facts(S(pending=pend), suggest=look, now=self.NOW)
        self.assertEqual(len(f['대기함']), 2)                                      # 퇴근 카드는 빠진다
        e = f['대기함'][0]
        self.assertEqual((e['점수'], e['기다린_분'], e['추천']['target']), (3, 4, '하율'))   # 3.5만 원 → 3점(5천 원대는 내림)
        self.assertEqual(f['대기함'][1]['종류'], '기여도 알림(후원 아님)')
        self.assertEqual(seen, [pend[0]['id']])                                     # 기여도 카드는 안 묻는다
        self.assertEqual(f['대기함_합계'], {'건수': 2, '금액': 35000, '점수': 3})
        ans = af.quick_answer('pending', f)
        self.assertIn('- 별빛 35,000원(3점) "하율 화이팅" · 4분째 → 하율', ans)
        tiles = af.board_tiles(f)
        self.assertEqual([t['intent'] for t in tiles], ['pending', 'match', 'goal', 'race'])
        self.assertEqual((tiles[0]['v'], tiles[0]['hot']), ('1건 · 3점', True))     # 3분 넘게 기다림 → 주황
        g = af.facts_for_ai(f)
        self.assertEqual(g['대기함'][0]['누구_것'], '하율')
        self.assertEqual(g['대기함_합계'], '2건 · 35,000원 · 3점')

    def test_match_running_paused_and_tile(self):
        m = {'active': True, 'teams': [{'id': 'a', 'name': 'A팀', 'score': 7, 'members': ['하율']},
                                       {'id': 'b', 'name': 'B팀', 'score': 4, 'members': []}],
             'timer': {'running': True, 'end_ms': int(self.NOW * 1000) + 90500, 'left_ms': 0}}
        f = af.build_facts(S(match=m), now=self.NOW)
        self.assertEqual(f['대결']['상태'], '진행 중 · 1:30 남음')
        self.assertEqual((f['대결']['앞선_쪽'], f['대결']['차이']), ('A팀', 3))
        self.assertIn('**A팀**이 3점 앞서요 — A팀 7 : B팀 4', af.quick_answer('match', f))
        t = af.board_tiles(f)[1]
        self.assertEqual((t['k'], t['v']), ('⚔️ 대결 · 1:30', 'A팀 +3'))
        m['timer'] = {'running': False, 'left_ms': 40000, 'held': True}
        f = af.build_facts(S(match=m), now=self.NOW)
        self.assertEqual(f['대결']['상태'], '멈춤 · 0:40 남음 (시그 끝나면 이어서)')
        self.assertEqual(af.board_tiles(f)[1]['k'], '⚔️ 대결 · 멈춤')
        m['timer'] = {'running': False, 'left_ms': 0}
        self.assertEqual(af.build_facts(S(match=m), now=self.NOW)['대결']['상태'], '멈춤(시간 끝)')
        m['teams'][1]['score'] = 7
        self.assertEqual(af.board_tiles(af.build_facts(S(match=m), now=self.NOW))[1]['v'], '동점')
        self.assertEqual(af.build_facts(S(), now=self.NOW)['대결'], '대결 안 함')

    def test_home_race_and_hell(self):
        f = af.build_facts(S(home={'on': True, 'goals': {'하율': 12, '서아': 8, '없는': 5}}), now=self.NOW)
        r = f['퇴근빵']
        self.assertEqual(r['이름'], '퇴근빵')
        self.assertEqual([(x['이름'], x['남은점수'], x['달성']) for x in r['선수별']], [('하율', 2, False), ('서아', 0, True)])
        self.assertEqual(r['가장_가까운_미달성'], '하율')
        self.assertEqual(af.board_tiles(f)[3]['v'], '하율 2점 남음')
        hell = {'on': True, 'base': {'하율': 6, '서아': 0}, 'goals': {'하율': 5, '서아': 20}}
        f = af.build_facts(S(hell=hell), now=self.NOW)
        self.assertEqual(f['퇴근빵']['이름'], '지옥탈출')
        self.assertEqual([(x['이름'], x['현재']) for x in f['퇴근빵']['선수별']], [('하율', 4), ('서아', 8)])  # 시작 뒤 받은 점수만
        self.assertNotIn('퇴근빵', af.build_facts(S(), now=self.NOW))
        self.assertEqual(af.quick_answer('race', af.build_facts(S(), now=self.NOW)), '퇴근빵 목표가 없어요.')

    def test_flow_window_and_contrib_excluded(self):
        logs = [{'at': self.NOW - 30, 'name': '하율', 'val': 3},
                {'at': self.NOW - 60, 'name': '서아', 'val': 0, 'cval': 5, 'kind': 'contrib'},
                {'at': self.NOW - 120, 'name': '서아', 'val': 2},
                {'at': self.NOW - 200, 'name': '하율', 'val': 1},
                {'at': self.NOW - 3600, 'name': '채원', 'val': 9}]
        f = af.build_facts(S(logs=logs), now=self.NOW)
        fl = f['최근_흐름']
        self.assertTrue(fl['기간'].startswith('최근 15분 ('))
        self.assertEqual(fl['사람별_점수합'], {'하율': 4, '서아': 2})
        self.assertIn('가장 많이 오른 사람: **하율** +4점', af.quick_answer('flow', f))
        f = af.build_facts(S(logs=logs[-1:]), now=self.NOW)                         # 15분 안이 없으면 최근 20건
        self.assertTrue(f['최근_흐름']['기간'].startswith('최근 1건'))

    def test_sigs_queue_games_vip_today(self):
        tallies = {'sigs': {'1': {'title': '사쿠란보', 'amount': 10000, 'count': 3, 'donors': {'별빛': 2, '달빛': 1}},
                            '3': {'title': '대박', 'amount': 50000, 'count': 1, 'donors': {'달빛': 1}}},
                   'vip': {'달빛': {'name': '달빛', 'rank': 1, 'grade': 'VVIP', 'badge': '🏆', 'total': 60000},
                           '별빛': {'name': '별빛', 'rank': 2, 'grade': 'VIP', 'badge': '👑', 'total': 20000}}}
        q = {'items': [{'title': '대박', 'count': 2}] + [{'title': 't%d' % i} for i in range(5)]}
        rows = [{'name': '홍길동', 'amount': 30000, 'status': 'assigned'},
                {'name': '홍길동님', 'amount': 20000, 'status': 'pending'},
                {'name': '쵸코', 'amount': 1000, 'status': 'display'},           # 화면에만 — 안 센다
                {'name': '달빛', 'amount': 10000, 'status': 'ignored'}]
        today = af.today_summary(rows)
        self.assertEqual((today['건수'], today['합계금액']), (3, 60000))
        self.assertEqual(today['많이_쏜_사람'][0], {'이름': '홍길동', '횟수': 2, '금액합': 50000})
        vip = af.vip_list(tallies)
        self.assertEqual([v['이름'] for v in vip], ['달빛', '별빛'])
        f = af.build_facts(S(tallies=tallies, queue=q, show={'stage': 'slot'},
                             roulette={'phase': 'spinning', 'stop': None}), today=today, vip=vip, now=self.NOW)
        self.assertEqual(f['시그니처']['횟수_순'][0], {'이름': '별빛', '횟수': 2, '금액합': 20000})
        self.assertEqual(f['시그니처']['금액_순'][0]['이름'], '달빛')
        sig = af.quick_answer('sig', f)
        self.assertIn('시그 제일 많이 쏜 사람: **별빛** 2번', sig)
        self.assertIn('- 금액으로는 달빛 6만 원', sig)
        self.assertEqual(f['리액션_대기줄'][0], '대박 ×2')
        self.assertEqual(f['리액션_대기줄'][-1], '…그 외 1개')
        self.assertEqual(f['게임'], ['슬롯 켜짐', '룰렛 켜짐'])
        self.assertEqual(f['VIP'][0]['등급'], 'VVIP')
        self.assertIn('오늘 후원 **3건** · 6만 원', af.quick_answer('today', f))
        f = af.build_facts(S(show={'stage': 'roulette'}, roulette={'phase': 'done', 'stop': {'name': '벌칙 2'}}), now=self.NOW)
        self.assertEqual(f['게임'], ['룰렛 켜짐 · 당첨 벌칙 2'])

    def test_game_context(self):
        sl = S(show={'stage': 'siggame', 'ret': None},
               siggame={'cards': [{'state': 'REVEALED', 'amount': 30000, 'flippedAt': 1, 'doneAt': None},
                                  {'state': 'REVEALED', 'amount': 50000, 'flippedAt': 1, 'doneAt': 2},
                                  {'state': 'HIDDEN'}]},
               match={'active': True, 'teams': [{'name': 'A', 'members': ['하율', '서아']}, {'name': 'B', 'members': []}]},
               home={'on': True}, hell={'on': True})
        ctx = af.game_context(sl)
        self.assertEqual(ctx, ['시그뒤집기 진행 중 — 아직 못 받은 목표 금액: 30,000원', '대결 진행 중 — A(하율·서아) vs B',
                               '퇴근전쟁 진행 중', '지옥탈출 진행 중'])
        self.assertEqual(af.game_context(S()), [])

    def test_intents_prompts_and_cleaning(self):
        for q, want in (('1등 누구야', 'rank'), ('대기함 뭐 있어', 'pending'), ('목표까지 얼마', 'goal'),
                        ('대결 누가 이겨', 'match'), ('퇴근 누가 가까워', 'race'), ('오늘 후원 합계', 'today'),
                        ('시그 많이 쏜 사람', 'sig'), ('요즘 치고 올라온 사람', 'flow'), ('안녕', None)):
            self.assertEqual(af.detect_intent(q), want, q)
        f = af.build_facts(S(), now=self.NOW)
        p = af.chat_system_prompt(f, '1등 누구야')
        self.assertIn('[사실표]', p)
        self.assertIn('[이 질문에 맞는 계산 결과', p)
        self.assertIn('1등은 **서아**', p)
        self.assertNotIn('[이 질문에 맞는 계산 결과', af.chat_system_prompt(f, '안녕'))
        self.assertEqual(af.clean_reply('## 답\n残り 하율이 1등이에요\n\n\n\n- 끝'), '답\n 하율이 1등이에요\n\n- 끝')
        self.assertTrue(af.looks_broken('재시 가장의 ( :1{" TEXT [[[H0[[[0'))
        self.assertTrue(af.looks_broken('Okay, let me count the entries'))
        self.assertFalse(af.looks_broken('1등은 **하율** 이에요'))
        sp = af.assign_system_prompt(['하율', '서아'], hints={'하율': "'하' 는 …"}, history=[('하율', 3)], context=['대결 진행 중'])
        self.assertIn('선수: 하율, 서아', sp)
        self.assertIn('이 후원자의 과거 배정(참고만): 하율 3번', sp)
        self.assertEqual(af.assign_user_prompt('별빛', 30000, '가자'), '후원자: 별빛 / 금액: 30,000원 / 메시지: 가자')

    def test_small_helpers(self):
        self.assertEqual([af.won(x) for x in (30000, 4870000, 12500, 120000000)],
                         ['3만 원', '487만 원', '12,500원', '1억 2,000만 원'])
        self.assertEqual([af.ga(x) for x in ('하율', '서아', 'Bob')], ['이', '가', '이(가)'])
        self.assertEqual(af.mmss(90500), '1:30')

    def test_names_in_message_and_hints(self):
        names = ['철수', '밍밍', '행복한걸', '예지랑']
        self.assertEqual(af.names_in_message('철수형 화이팅', names), ({'철수'}, set()))
        self.assertEqual(af.names_in_message('철수했다가 다시 왔어요', names), (set(), {'철수'}))
        self.assertEqual(af.names_in_message('밍밍화이팅', names), (set(), {'밍밍'}))
        h = af.nickname_hints('행걸 지랑이 ㅎㅂㅎㄱ', names)
        self.assertIn('줄임', h['행복한걸'])
        self.assertIn('뒷부분', h['예지랑'])
        self.assertIn('초성', af.nickname_hints('ㅎㅂㅎㄱ', names)['행복한걸'])
        self.assertIn('앞부분', af.nickname_hints('행복이 최고', names)['행복한걸'])


# ══ ② 후원자 기억 · 규칙 단계 ══
class Memory(unittest.TestCase):
    NAMES = ['하율', '서아', '채원']

    def setUp(self):
        self.s = Store(':memory:')
        self.addCleanup(self.s.close)

    def test_alias_tokens(self):
        self.assertEqual(dm.alias_tokens('하뉴님 화이팅! 오늘도 2026 ㅋ 하뉴야'), ['하뉴', '오늘도', '하뉴'])
        self.assertEqual(dm.alias_tokens(''), [])

    def test_remember_history_alias_forget(self):
        self.assertTrue(dm.remember_assignment(self.s, '별빛님', '하율', 3, '하뉴 최고', ref='don_1', at=1))
        self.assertTrue(dm.remember_assignment(self.s, '별빛', '하율', 1, '하뉴 최고', ref='don_2', at=2))
        self.assertTrue(dm.remember_assignment(self.s, '별빛', '서아', 1, '서아짱', ref='don_3', at=3))
        self.assertFalse(dm.remember_assignment(self.s, '익명', '하율', 1, '하뉴'))      # 익명은 안 배운다
        self.assertFalse(dm.remember_assignment(self.s, '별빛', '', 1, '하뉴'))
        self.assertEqual(dm.donor_history(self.s, '별빛'), [('하율', 2), ('서아', 1)])    # '별빛님' 과 같은 사람
        self.assertEqual(dm.alias_lookup(self.s, '하뉴 가자', self.NAMES)[:2], ('하율', 2))
        self.assertIsNone(dm.alias_lookup(self.s, '하뉴 가자', ['서아']))                 # 지금 선수가 아니면 안 쓴다
        dm.remember_assignment(self.s, '달빛', '서아', 1, '최고', ref='don_4')           # '최고' 가 두 사람으로 이어졌다
        self.assertEqual(dm.alias_lookup(self.s, '최고', self.NAMES), None)
        self.assertEqual(dm.forget_assignment(self.s, 'don_2'), 1)
        self.assertEqual(dm.donor_history(self.s, '별빛'), [('서아', 1), ('하율', 1)])     # 같으면 최근 것이 앞
        self.assertEqual(dm.alias_lookup(self.s, '하뉴', self.NAMES)[:2], ('하율', 1))
        dm.forget_assignment(self.s, 'don_1')
        self.assertIsNone(dm.alias_lookup(self.s, '하뉴', self.NAMES))                  # 0 이 되면 지운다

    def _sug(self, donor, msg, ai=None, names=None):
        return dm.suggest_target(self.s, donor, msg, names or self.NAMES, ask_ai=(lambda pre: ai) if ai else None)

    def test_stage1_names(self):
        r = self._sug('별빛', '하율에게 힘을')
        self.assertEqual((r['target'], r['confidence'], r['tier'], r['source']), ('하율', 0.97, 'auto', '이름'))
        r = self._sug('별빛', '하율 서아 둘 다')
        self.assertEqual((r['target'], r['tier']), (None, 'unknown'))
        self.assertIn('여러 사람을 부름', r['why'])
        r = self._sug('별빛', '하율화이팅')
        self.assertEqual((r['target'], r['confidence'], r['tier']), ('하율', 0.75, 'suggest'))
        r = self._sug('별빛', '하율화이팅 서아최고')
        self.assertEqual((r['target'], r['tier']), (None, 'unknown'))

    def test_stage2_alias(self):
        for i in range(2):
            dm.remember_assignment(self.s, '별빛%d' % i, '서아', 1, '쏘냐 가자', ref='don_%d' % i)
        r = self._sug('달빛', '쏘냐!')
        self.assertEqual((r['target'], r['confidence'], r['tier'], r['source']), ('서아', 0.8, 'suggest', '별명'))
        for i in range(2, 4):
            dm.remember_assignment(self.s, '별빛%d' % i, '서아', 1, '쏘냐', ref='don_%d' % i)
        r = self._sug('달빛', '쏘냐!')
        self.assertEqual((r['confidence'], r['tier']), (0.95, 'auto'))
        r = self._sug('달빛', '쏘냐 하율화이팅')                                       # 다른 이름 글자가 붙어 있다
        self.assertEqual((r['target'], r['tier'], r['confidence']), ('서아', 'suggest', 0.85))
        self.assertIn("메시지에 '하율' 글자가 있어 확인 필요", r['why'])

    def test_stage3_history(self):
        for i in range(2):
            dm.remember_assignment(self.s, '별빛', '채원', 1, '', ref='don_%d' % i)
        r = self._sug('별빛', '')
        self.assertEqual((r['target'], r['confidence'], r['tier'], r['source']), ('채원', 0.8, 'suggest', '이력'))
        self.assertEqual(r['history'], [{'name': '채원', 'count': 2}])
        for i in range(2, 4):
            dm.remember_assignment(self.s, '별빛', '채원', 1, '', ref='don_%d' % i)
        self.assertEqual(self._sug('별빛', '')['tier'], 'auto')                      # 4번 → 0.93
        self.assertEqual(self._sug('별빛', '')['confidence'], 0.93)
        dm.remember_assignment(self.s, '별빛', '하율', 1, '', ref='don_9')
        r = self._sug('별빛', '')
        self.assertEqual((r['target'], r['confidence'], r['tier']), ('채원', 0.7, 'suggest'))   # 4번 / 그 외 1번

    def test_stage4_ai_and_reasons(self):
        r = self._sug('별빛', '오늘도 응원', ai={'target': '서아', 'confidence': 0.99})
        self.assertEqual((r['target'], r['confidence'], r['tier'], r['source']), ('서아', 0.88, 'suggest', 'AI'))
        cases = [({'skipped': True, 'reason': 'rate', 'retry': True}, 'AI 호출이 잠시 몰려'),
                 ({'skipped': True}, 'AI 가 꺼져 있음'),
                 ({'error': 503, 'retry': True}, 'AI 서버가 붐빕니다'),
                 ({'error': 410, 'gone': True}, 'AI 모델이 종료됐습니다'),
                 ({'error': 'no-response', 'retry': True}, 'AI 오류로 못 물어봄'),
                 ({'target': None, 'confidence': 0.0}, '처음 보는 후원자')]
        for ai_ans, why in cases:
            r = self._sug('별빛', '오늘도 응원', ai=dict({'target': None, 'confidence': 0.0}, **ai_ans))
            self.assertEqual((r['target'], r['tier']), (None, 'unknown'))
            self.assertIn(why, r['why'])
            self.assertEqual(bool(r.get('retry')), bool(ai_ans.get('retry')))
        # 글자가 겹치는 선수가 하나뿐이고 AI 가 못 답하면 0.72 '확인 필요'
        r = self._sug('별빛', '행걸 가자', ai={'target': None, 'confidence': 0.0, 'error': 503, 'retry': True},
                      names=['하율', '행복한걸'])
        self.assertEqual((r['target'], r['confidence'], r['tier'], r['source']), ('행복한걸', 0.72, 'suggest', '별명'))
        self.assertTrue(r['retry'])
        self.assertIn('AI 없이 글자로만 봄', r['why'])


# ══ ③ 서버에 붙여서 — 배정하면 기억 · 되돌리면 잊기 · 주소 ══
class Base(unittest.TestCase):
    NAMES = ['하율', '서아', '채원']

    def setUp(self):
        _guard(self)
        self.dir = tempfile.mkdtemp(prefix='lm2ai_')
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET,
                                       sig_fetch=lambda: SIGS))
        self.cmd('session.start', names=self.NAMES)

    def tearDown(self):
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    @property
    def store(self):
        return self.c.app.state.store

    def cmd(self, t, **data):
        r = self.c.post('/api/cmd', json={'type': t, 'data': data}, headers=H)
        return r.status_code, r.json()

    def st(self):
        return self.c.get('/api/state', headers=H).json()['slices']

    def don(self, name, amount, tx, msg=''):
        r = self.c.post('/api/donation', json={'name': name, 'amount': amount, 'message': msg, 'tx_id': tx}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json().get('id')

    def mem(self):
        dm.ensure(self.store)
        return [dict(r) for r in self.store.db.execute('SELECT donor, player, amount, message, ref FROM donor_memory ORDER BY id')]

    def ask(self, **body):
        r = self.c.post('/api/audit/suggest', json=body, headers=H)
        return r.status_code, r.json()


class Hooks(Base):
    def test_assign_remembers_and_undo_forgets(self):
        pid = self.don('별빛님', 30000, 'toon_h1', '하뉴 최고')
        c, r = self.cmd('pending.assign', id=pid, name='하율')
        self.assertEqual(c, 200, r)
        self.assertEqual(self.mem(), [{'donor': '별빛', 'player': '하율', 'amount': 3, 'message': '하뉴 최고', 'ref': pid}])
        self.assertEqual(dm.alias_lookup(self.store, '하뉴', self.NAMES)[:2], ('하율', 1))
        c, r = self.cmd('score.undo', ref=pid)
        self.assertEqual(c, 200, r)
        self.assertEqual(self.mem(), [])                                            # 되돌리면 잊는다
        self.assertIsNone(dm.alias_lookup(self.store, '하뉴', self.NAMES))
        self.assertEqual([x['id'] for x in self.st()['pending']], [pid])              # 후원은 대기함으로
        self.cmd('pending.assign', id=pid, name='서아')                                # 다시 주면 다시 배운다
        self.assertEqual([m['player'] for m in self.mem()], ['서아'])

    def test_split_manual_and_test_donations(self):
        pid = self.don('달빛', 50000, 'toon_h2', '')
        self.cmd('pending.assign', id=pid, names=['하율', '서아', '채원'])
        self.assertEqual([(m['player'], m['amount']) for m in self.mem()], [('하율', 2), ('서아', 2), ('채원', 1)])
        self.cmd('score.add', name='하율', delta=5)                                   # 손 점수는 안 배운다
        self.assertEqual(len(self.mem()), 3)
        tid = self.don('테스트', 20000, 'toon_t2_x', '')                               # 리스너 시험 후원은 안 배운다
        self.cmd('pending.assign', id=tid, name='채원')
        self.assertEqual(len(self.mem()), 3)

    def test_memory_failure_never_blocks_assignment(self):
        pid = self.don('별빛', 20000, 'toon_h3', '')
        with mock.patch.object(dm, 'remember_assignment', side_effect=RuntimeError('boom')):
            c, r = self.cmd('pending.assign', id=pid, name='채원')
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertEqual(next(p for p in s['players']['list'] if p['name'] == '채원')['score'], 2)
        self.assertEqual(s['pending'], [])
        self.assertEqual(self.mem(), [])


class Routes(Base):
    def test_login_required(self):
        for method, url in (('post', '/api/audit/suggest'), ('get', '/api/ai/board'), ('post', '/api/ai/chat')):
            r = getattr(self.c, method)(url, **({'json': {}} if method == 'post' else {}))
            self.assertEqual(r.status_code, 401, url)

    def test_suggest_by_id_name_rule_no_ai(self):
        fake = FakeNim()
        with mock.patch.object(ai, 'nim_post', fake):
            pid = self.don('별빛', 30000, 'toon_r1', '서아 화이팅')
            c, r = self.ask(id=pid)
        self.assertEqual(c, 200, r)
        self.assertEqual((r['id'], r['target'], r['tier'], r['confidence'], r['source']), (pid, '서아', 'auto', 0.97, '이름'))
        self.assertEqual(fake.calls, [])                                               # 규칙으로 풀리면 AI 를 안 부른다
        c, r = self.ask(id='don_없음')
        self.assertEqual((c, r['status'], r.get('gone')), (404, 'error', True))

    def test_suggest_calls_ai_outside_and_caches(self):
        fake = FakeNim((FakeResp(200, '음 {"target": "채원", "confidence": 0.97} 끝'), 200, ai.NIM_MODEL))
        with mock.patch.object(ai, 'nim_post', fake):
            pid = self.don('별빛', 20000, 'toon_r2', '오늘도 응원해요')
            c, r = self.ask(id=pid)
            self.assertEqual((r['target'], r['tier'], r['confidence'], r['source']), ('채원', 'suggest', 0.88, 'AI'))
            self.assertEqual(len(fake.calls), 1)
            call = fake.calls[0]
            self.assertEqual(call['models'], [ai.NIM_MODEL, ai.NIM_MODEL, ai.NIM_MODEL_BACKUP])
            self.assertEqual(call['timeout'], ai.SUGGEST_TIMEOUT)
            self.assertEqual(call['body']['chat_template_kwargs'], {'thinking': False})
            self.assertIn('선수: 하율, 서아, 채원', call['body']['messages'][0]['content'])
            c, r2 = self.ask(id=pid)                                                   # 두 번째는 기억에서
            self.assertTrue(r2.get('cached'))
            self.assertEqual(len(fake.calls), 1)
            # 상황판 · 채팅 사실표는 그 기억을 쓴다(AI 를 또 안 부른다)
            r = self.c.post('/api/ai/chat', json={'intent': 'pending'}, headers=H).json()
            self.assertIn('→ 채원(확인 필요)', r['reply'])
            self.assertEqual(len(fake.calls), 1)

    def test_suggest_hallucinated_name_is_dropped(self):
        fake = FakeNim((FakeResp(200, '{"target": "없는사람", "confidence": 0.99}'), 200, ai.NIM_MODEL))
        with mock.patch.object(ai, 'nim_post', fake):
            pid = self.don('별빛', 20000, 'toon_r3', '오늘도 응원해요')
            c, r = self.ask(id=pid)
        self.assertEqual((r['target'], r['tier']), (None, 'unknown'))

    def test_suggest_model_down_retries_and_not_cached(self):
        fake = FakeNim((None, 503, ai.NIM_MODEL_BACKUP), (None, 503, ai.NIM_MODEL_BACKUP))
        with mock.patch.object(ai, 'nim_post', fake):
            pid = self.don('별빛', 20000, 'toon_r4', '오늘도 응원해요')
            c, r = self.ask(id=pid)
            self.assertEqual((c, r['status'], r['target'], r['tier'], r.get('retry')), (200, 'success', None, 'unknown', True))
            self.assertIn('AI 서버가 붐빕니다', r['why'])
            self.ask(id=pid)
            self.assertEqual(len(fake.calls), 2)                                       # 잠깐 막힌 답은 기억하지 않는다
        fake = FakeNim((FakeResp(410), 410, ai.NIM_MODEL))
        with mock.patch.object(ai, 'nim_post', fake):
            c, r = self.ask(id=pid)
        self.assertIn('AI 모델이 종료됐습니다', r['why'])
        self.assertFalse(r.get('retry'))

    def test_suggest_deadline(self):
        fake = FakeNim((FakeResp(200, '{"target": "채원", "confidence": 0.9}'), 200, ai.NIM_MODEL), delay=0.4)
        with mock.patch.object(ai, 'nim_post', fake), mock.patch.object(ai, 'SUGGEST_DEADLINE', 0.05):
            pid = self.don('별빛', 20000, 'toon_r5', '오늘도 응원해요')
            c, r = self.ask(id=pid)
        # ⚠️ 걸린 시간은 여기서 못 잰다 — 검사용 TestClient 는 요청마다 루프를 닫으며 남은 갈래를 기다린다(운영 uvicorn 은 안 기다린다).
        #    시간은 NimPost.test_suggest_deadline_timing 이 루프 안에서 잰다.
        self.assertEqual((r['target'], r.get('retry')), (None, True))
        self.assertIn('AI 오류로 못 물어봄', r['why'])

    def test_suggest_without_key_uses_hint(self):
        p = mock.patch.object(ai, 'nim_key', lambda: '')
        p.start()
        self.addCleanup(p.stop)
        self.cmd('players.add', name='행복한걸')
        fake = FakeNim()
        with mock.patch.object(ai, 'nim_post', fake):
            pid = self.don('별빛', 20000, 'toon_r6', '행걸 가자')
            c, r = self.ask(id=pid)
            self.assertEqual((r['target'], r['confidence'], r['tier']), ('행복한걸', 0.72, 'suggest'))
            c, r = self.ask(name='달빛', amount=10000, message='좋은 밤', players=['하율', {'name': '서아'}])   # 옛 모양
            self.assertEqual((r['target'], r['tier']), (None, 'unknown'))
            self.assertIn('AI 가 꺼져 있음', r['why'])
        self.assertEqual(fake.calls, [])
        b = self.c.get('/api/ai/board', headers=H).json()
        self.assertEqual(b['ai']['state'], 'off')

    def test_suggest_skips_cards(self):
        self.c.app.state.bus.state.slices['pending'].append(
            {'id': 'dg_1_aa', 'name': '🎲', 'amount': 0, 'message': '', 'kind': 'contrib', 'contrib': 3})
        c, r = self.ask(id='dg_1_aa')
        self.assertEqual((c, r['target'], r['skipped']), (200, None, True))

    def test_board_and_today(self):
        self.cmd('goal.set', target=10)
        self.don('별빛', 30000, 'toon_b1', '')
        self.don('별빛님', 20000, 'toon_b2', '')
        b = self.c.get('/api/ai/board?today=1', headers=H).json()
        self.assertEqual(b['status'], 'success')
        self.assertEqual([t['intent'] for t in b['tiles']], ['pending', 'match', 'goal', 'race'])
        self.assertEqual(b['tiles'][0]['v'], '2건 · 5점')
        self.assertEqual(b['tiles'][2]['pct'], 0)
        self.assertEqual(b['ai']['state'], 'idle')
        self.assertEqual(b['intents']['rank'], '📊 순위')
        self.assertEqual((b['today']['건수'], b['today']['합계금액']), (2, 50000))
        self.assertEqual(b['today']['많이_쏜_사람'][0]['횟수'], 2)
        self.assertNotIn('today', self.c.get('/api/ai/board', headers=H).json())

    def test_chat_intent_is_calc(self):
        fake = FakeNim()
        with mock.patch.object(ai, 'nim_post', fake):
            self.cmd('score.add', name='서아', delta=4)
            r = self.c.post('/api/ai/chat', json={'intent': 'rank'}, headers=H).json()
            self.assertEqual(r['source'], 'calc')
            self.assertTrue(r['reply'].startswith('1등은 **서아**'))
            r = self.c.post('/api/ai/chat', json={'intent': '모름'}, headers=H).json()
            self.assertEqual(r['source'], 'calc')
            r = self.c.post('/api/ai/chat', json={}, headers=H).json()
            self.assertEqual((r['source'], r['reply']), ('none', '무엇을 도와드릴까요?'))
        self.assertEqual(fake.calls, [])

    def test_chat_ai_ok(self):
        fake = FakeNim((FakeResp(200, '## 1등은 **서아**예요\n- 2등 하율'), 200, ai.NIM_CHAT_MODEL))
        hist = [{'role': 'user', 'content': 'q%d' % i} for i in range(8)] + [{'role': 'system', 'content': 'x'}, 'bad']
        with mock.patch.object(ai, 'nim_post', fake):
            self.cmd('score.add', name='서아', delta=4)
            r = self.c.post('/api/ai/chat', json={'question': '1등 누구야?', 'messages': hist}, headers=H).json()
        self.assertEqual((r['source'], r['reply']), ('ai', '1등은 **서아**예요\n- 2등 하율'))
        call = fake.calls[0]
        self.assertEqual(call['models'], [ai.NIM_CHAT_MODEL, ai.NIM_CHAT_MODEL, ai.NIM_CHAT_BACKUP])
        msgs = call['body']['messages']
        self.assertIn('[사실표]', msgs[0]['content'])
        self.assertIn('1등은 **서아** — 기여도 4', msgs[0]['content'])                # 서버가 계산한 답을 쥐여 준다
        self.assertEqual([m['content'] for m in msgs[1:]], ['q4', 'q5', 'q6', 'q7', '1등 누구야?'])   # 마지막 6개 중 쓸 것만
        self.assertEqual(call['body']['max_tokens'], af.CHAT_MAX_TOKENS)

    def test_chat_fallbacks_when_model_down(self):
        cases = [
            ((None, 503, ai.NIM_CHAT_BACKUP), 'calc', '서버 계산으로 답했어요'),
            ((FakeResp(500), 500, ai.NIM_CHAT_MODEL), 'calc', 'AI 오류 500'),
            ((FakeResp(200, '재시 가장의 ( :1{" TEXT [[[H0'), 200, ai.NIM_CHAT_MODEL), 'calc', 'AI 답이 깨져서'),
            ((FakeResp(200, '', reasoning='Okay, let me think'), 200, ai.NIM_CHAT_MODEL), 'calc', '생각만 하다'),
        ]
        for ans, src, text in cases:
            with mock.patch.object(ai, 'nim_post', FakeNim(ans)):
                r = self.c.post('/api/ai/chat', json={'question': '1등 누구야'}, headers=H).json()
            self.assertEqual(r['source'], src, text)
            self.assertIn(text, r['reply'])
            self.assertTrue(r['reply'].startswith('1등은'), r['reply'])                 # 계산한 답이 먼저
            self.assertNotIn('Okay', r['reply'])
        with mock.patch.object(ai, 'nim_post', FakeNim((None, 503, ai.NIM_CHAT_BACKUP))):
            r = self.c.post('/api/ai/chat', json={'question': '안녕'}, headers=H).json()
        self.assertEqual(r['source'], 'none')                                          # 계산할 거리가 없는 질문
        self.assertIn('AI 서버가 붐벼서', r['reply'])
        with mock.patch.object(ai, 'nim_post', FakeNim((FakeResp(410), 410, ai.NIM_CHAT_BACKUP))):
            r = self.c.post('/api/ai/chat', json={'question': '안녕'}, headers=H).json()
        self.assertIn('NIM_CHAT_BACKUP', r['reply'])                                   # 실제로 답한 모델의 설정을 댄다

    def test_chat_without_key_and_rate_limit(self):
        with mock.patch.object(ai, 'nim_key', lambda: ''), mock.patch.object(ai, 'nim_post', FakeNim()) as f:
            r = self.c.post('/api/ai/chat', json={'question': '목표 얼마 남았어'}, headers=H).json()
            self.assertEqual(r['source'], 'calc')
            self.assertIn('AI 키가 설정되지 않았어요', r['reply'])
            self.assertEqual(f.calls, [])
        with mock.patch.object(ai, '_nim_calls', [time.time()] * ai.NIM_RATE_LIMIT), \
                mock.patch.object(ai, 'nim_post', FakeNim()) as f:
            r = self.c.post('/api/ai/chat', json={'question': '안녕'}, headers=H).json()
            self.assertIn('AI 호출이 몰려서', r['reply'])
            self.assertEqual(f.calls, [])

    def test_key_never_in_answers(self):
        with mock.patch.object(ai, 'nim_post', FakeNim((FakeResp(401), 401, ai.NIM_CHAT_MODEL))):
            texts = [self.c.post('/api/ai/chat', json={'question': '안녕'}, headers=H).text,
                     self.c.get('/api/ai/board?today=1', headers=H).text]
        for t in texts:
            self.assertNotIn(FAKE_KEY, t)


# ══ ④ NIM 호출 틀(가짜 바깥) ══
class NimPost(unittest.TestCase):
    def setUp(self):
        _guard(self)

    def test_fallback_order_health_and_no_retry_on_gone(self):
        seq = [FakeResp(503), FakeResp(503), FakeResp(200, '{}')]
        sent = []

        def http(url, headers, body, timeout):
            sent.append((url, body['model'], headers['Authorization'] == 'Bearer ' + FAKE_KEY))
            return seq.pop(0)
        with mock.patch.object(ai, '_http_post', http), mock.patch.object(ai.time, 'sleep', lambda s: None):
            r, code, used = ai.nim_post(['m1', 'm1', 'm2'], {'x': 1}, 5)
        self.assertEqual((code, used), (200, 'm2'))
        self.assertEqual([s[1] for s in sent], ['m1', 'm1', 'm2'])
        self.assertTrue(all(s[0] == ai.NIM_URL and s[2] for s in sent))
        self.assertEqual((ai.NIM_HEALTH['ok'], ai.NIM_HEALTH['model']), (True, 'm2'))
        self.assertEqual(ai.ai_health()['state'], 'ok')
        seq[:] = [FakeResp(410)]
        sent.clear()
        with mock.patch.object(ai, '_http_post', http):
            r, code, used = ai.nim_post(['m1', 'm1', 'm2'], {}, 5)
        self.assertEqual((code, used, len(sent)), (410, 'm1', 1))                       # 410 은 다시 해도 같다
        self.assertEqual(ai.ai_health()['state'], 'busy')

        def boom(*a, **k):
            raise TimeoutError('slow')
        with mock.patch.object(ai, '_http_post', boom):
            self.assertEqual(ai.nim_post(['m1', 'm2'], {}, 5), (None, 0, 'm2'))

    def test_suggest_target_parsing(self):
        with mock.patch.object(ai, 'nim_post', FakeNim((FakeResp(200, '답: {"target": "null", "confidence": 0.4}'), 200, 'm'))):
            self.assertEqual(ai.nim_suggest_target('a', 1, '가자', ['하율']), {'target': None, 'confidence': 0.4})
        with mock.patch.object(ai, 'nim_post', FakeNim((FakeResp(200, '모르겠어요'), 200, 'm'))):
            self.assertEqual(ai.nim_suggest_target('a', 1, '가자', ['하율'])['target'], None)
        self.assertTrue(ai.nim_suggest_target('a', 1, '   ', ['하율'])['skipped'])         # 메시지 없으면 안 묻는다

    def test_rate_limit(self):
        for _ in range(ai.NIM_RATE_LIMIT):
            self.assertTrue(ai.nim_allowed())
        self.assertFalse(ai.nim_allowed())
        r = ai.nim_suggest_target('a', 1, '가자', ['하율'])
        self.assertEqual((r.get('reason'), r.get('retry')), ('rate', True))

    def test_key_from_env_then_file(self):
        tmp = tempfile.mkdtemp(prefix='lm2key_')
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(os.path.join(tmp, 'NVIDIA_CREDENTIALS.txt'), 'w', encoding='utf-8') as f:
            f.write('# 주석\nOTHER=1\nNVIDIA_API_KEY = file-key-x # 메모\n')
        env = {k: v for k, v in os.environ.items() if k != 'NVIDIA_API_KEY'}
        with mock.patch.object(ai, '_KEY', None), mock.patch.object(ai, 'REPO', tmp), mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(REAL_NIM_KEY(), 'file-key-x')
        with mock.patch.object(ai, '_KEY', None), mock.patch.dict(os.environ, {'NVIDIA_API_KEY': ' env-key-y '}):
            self.assertEqual(REAL_NIM_KEY(), 'env-key-y')
        with mock.patch.object(ai, '_KEY', None), mock.patch.object(ai, 'REPO', tmp + '_없음'), \
                mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(REAL_NIM_KEY(), '')

    def test_suggest_coroutine_runs_ai_in_thread(self):
        """suggest 는 AI 를 다른 갈래에서 부른다 — 부른 갈래가 이벤트 루프 갈래가 아니다."""
        import threading
        seen = {}

        def fake(models, body, timeout):
            seen['thread'] = threading.current_thread() is threading.main_thread()
            return FakeResp(200, '{"target": "서아", "confidence": 0.7}'), 200, models[0]
        s = Store(':memory:')
        self.addCleanup(s.close)

        class B:
            store = s
            state = type('St', (), {'slices': S()})()
        with mock.patch.object(ai, 'nim_post', fake):
            r = asyncio.run(ai.suggest(B(), '별빛', 10000, '좋은 밤', ['하율', '서아']))
        self.assertEqual((r['target'], r['confidence']), ('서아', 0.7))
        self.assertFalse(seen['thread'])


    def test_suggest_deadline_timing(self):
        """AI 가 시한을 넘기면 기다리지 않고 '모름 · 다시' 로 답한다(잰 시간은 루프 안에서)."""
        s = Store(':memory:')
        self.addCleanup(s.close)

        class B:
            store = s
            state = type('St', (), {'slices': S()})()

        async def go():
            t0 = time.time()
            r = await ai.suggest(B(), '별빛', 10000, '좋은 밤', ['하율', '서아'])
            return r, time.time() - t0
        fake = FakeNim((FakeResp(200, '{"target": "서아", "confidence": 0.9}'), 200, 'm'), delay=0.5)
        with mock.patch.object(ai, 'nim_post', fake), mock.patch.object(ai, 'SUGGEST_DEADLINE', 0.05):
            r, took = asyncio.run(go())
        self.assertLess(took, 0.3)
        self.assertEqual((r['target'], r.get('retry')), (None, True))

if __name__ == '__main__':
    unittest.main()


class AiSwitches(unittest.TestCase):
    """시험 서버 스위치 · 되돌리면 배정 판단도 잊는다."""

    def test_ai_off_switch(self):
        import os
        from unittest import mock
        from v2.server.domain import ai
        with mock.patch.dict(os.environ, {'LM2_AI_OFF': '1', 'NVIDIA_API_KEY': 'fake-should-not-be-used'}):
            self.assertEqual(ai._load_key(), '')

    def test_undo_forgets_cached_suggestion(self):
        from v2.server.domain import ai
        from v2.tests.test_flow import Base
        b = Base()
        b.setUp()
        try:
            b.don('별빛', 30000, 'toon_fs1', msg='응원')
            pid = b.st()['pending'][0]['id']
            names = ('하율', '서아', '채원')
            ai._SUGGEST_CACHE[('별빛', 30000, '응원', names)] = (9e12, {'target': '하율'})
            ai._SUGGEST_CACHE[('딴사람', 30000, '응원', names)] = (9e12, {'target': '서아'})
            b.cmd('pending.assign', id=pid, name='하율')
            b.cmd('score.undo')
            self.assertNotIn(('별빛', 30000, '응원', names), ai._SUGGEST_CACHE)
            self.assertIn(('딴사람', 30000, '응원', names), ai._SUGGEST_CACHE)   # 다른 후원 것은 그대로
        finally:
            ai._SUGGEST_CACHE.clear()
            b.tearDown()
