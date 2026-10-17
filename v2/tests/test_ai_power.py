# -*- coding: utf-8 -*-
"""🤖 AI 권한 넓히기(10-17) — ① 말로 조종(카드 · [실행]) ② 안전한 건 바로(상한 · 되돌리기) ③ AI 배정(자동 진행 켬)
   + ⏸ 애매하면 보류(대표님 "금액은 조금이라도 애매하면 보류로 놓고 나를 호출").

⚠️ 진짜 Claude · NVIDIA 는 절대 부르지 않는다 — 바깥으로 나가는 곳(ai._claude_call · ai._claude_tools_call · ai._http_post)을
   '부르면 실패' 로 막고, AI 를 쓰는 검사만 ai.ai_tools · ai.nim_post 를 가짜로 바꾼다. 키도 가짜(ai.claude_key · ai.nim_key).
돌리기(저장소 루트에서): python -m unittest v2.tests.test_ai_power
"""
import time
import unittest
from unittest import mock

from v2.server.domain import ai
from v2.server.domain import ai_cmd as ac
from v2.server.domain import autopilot as apm
from v2.tests.test_ai import FakeNim, FakeResp, _no_network
from v2.tests.test_autopilot import AutoBase
from v2.tests.test_flow import Base, H

FAKE = 'test-key-not-real'
REAL_TOOLS = ai._claude_tools_call          # 바깥으로 나가는 곳 — 가짜 클라이언트로만 부른다


def _block(case, claude='', nim=''):
    for p in (mock.patch.object(ai, '_http_post', _no_network),
              mock.patch.object(ai, '_claude_call', _no_network),
              mock.patch.object(ai, '_claude_tools_call', _no_network),
              mock.patch.object(ai, 'claude_key', lambda: claude),
              mock.patch.object(ai, 'nim_key', lambda: nim),
              mock.patch.object(ai, 'NIM_HEALTH', {'ok': None, 'ms': 0, 'at': 0.0, 'model': '', 'code': 0}),
              mock.patch.object(ai, '_nim_calls', [])):
        p.start()
        case.addCleanup(p.stop)
    ac._direct_at.clear()
    case.addCleanup(ac._direct_at.clear)
    ai._SUGGEST_CACHE.clear()
    case.addCleanup(ai._SUGGEST_CACHE.clear)


class FakeTools:
    """ai.ai_tools 대신 — 정해 둔 도구 입력을 돌려준다(부른 기록을 남긴다)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, system, messages, tools, tool_choice=None, max_tokens=600, timeout=12):
        self.calls.append({'system': system, 'messages': messages, 'tools': tools, 'tool_choice': tool_choice})
        return self.answers.pop(0) if self.answers else ([], '', 529)


def use(*cmds, reply=''):
    return ([(ac.TOOL_NAME, {'commands': list(cmds), 'reply': reply})], '', 200)


# ══ ① · ② 말로 조종 ══
class Speak(Base):
    def setUp(self):
        _block(self, claude=FAKE)
        super().setUp()

    def say(self, text, **kw):
        r = self.c.post('/api/ai/command', json=dict({'text': text}, **kw), headers=H)
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_needs_login(self):
        r = self.c.post('/api/ai/command', json={'text': '공지: 안녕'})
        self.assertEqual(r.status_code, 401)

    def test_question_goes_to_chat_without_ai(self):
        with mock.patch.object(ai, 'ai_tools', FakeTools()) as f:
            r = self.say('하율 몇 점이야?')
        self.assertEqual(r['kind'], 'question')
        self.assertEqual(f.calls, [])

    def test_score_is_never_run_without_click(self):
        """AI 가 점수 명령을 내도 서버는 절대 안 한다 — 카드만([실행]). 스위치가 켜져 있어도."""
        before = self.player('하율')['score']
        ft = FakeTools(use({'type': 'score.add', 'data': {'name': '하율', 'delta': 5}},
                           {'type': 'pending.ignore', 'data': {'id': 'nope'}}))
        with mock.patch.object(ai, 'ai_tools', ft):
            r = self.say('하율이 다섯점 주라')
        self.assertEqual(r['kind'], 'command')
        self.assertEqual(r['source'], 'ai')
        self.assertEqual([(c['type'], c['state'], c['safe']) for c in r['cards']], [('score.add', 'ask', False)])
        self.assertEqual(r['cards'][0]['data'], {'name': '하율', 'list': 'list', 'delta': 5})
        self.assertIn('하율에게 +5점', r['cards'][0]['text'])
        self.assertEqual(r['dropped'][0]['type'], 'pending.ignore')                # 없는 대기함 id 는 버린다
        self.assertEqual(self.player('하율')['score'], before)                       # ⭐ 점수 그대로
        self.assertIn('하율', ft.calls[0]['system'])                                  # 명단을 알려 준다
        self.assertEqual(ft.calls[0]['tool_choice'], {'type': 'tool', 'name': ac.TOOL_NAME})
        # 사람이 [실행] → 조종실이 /api/cmd 로 보낸다(같은 데이터 그대로)
        c, res = self.cmd(r['cards'][0]['type'], **r['cards'][0]['data'])
        self.assertEqual(c, 200, res)
        self.assertEqual(self.player('하율')['score'], before + 5)

    def test_bad_tool_input_is_dropped(self):
        bad = [
            {'type': 'session.end', 'data': {}},                                        # 허용 목록 밖
            {'type': 'score.undo', 'data': {}},                                         # 되돌리기는 사람만
            {'type': 'score.add', 'data': {'name': '없는사람', 'delta': 3}},             # 지금 명단에 없음
            {'type': 'score.add', 'data': {'name': '하율', 'delta': 500}},               # 범위 밖
            {'type': 'score.add', 'data': {'name': '하율', 'delta': True}},              # 참거짓은 숫자가 아님
            {'type': 'score.add', 'data': {'name': '하율', 'delta': 3, 'list': 'bottom'}},  # 모르는 칸
            {'type': 'cast.say', 'data': {'text': '   '}},                              # 빈 글
            {'type': 'show.stage', 'data': {'stage': 'hell'}},                          # 판 스위치(무대 아님)
            {'type': 'lights.color', 'data': {'color': 'javascript:alert(1)'}},
            {'type': 'match.set_time', 'data': {'min': 999}},
            {'type': 'goal.set', 'data': {'target': -1}},
            {'type': 'notice.edit', 'data': {'index': 7, 'text': 'x'}},                 # 없는 공지
            'not-a-dict',
            {'type': None, 'data': None},
        ]
        for i in range(0, len(bad), ac.PROPOSE_MAX):                                    # 한 번에 6줄까지만 본다
            chunk = bad[i:i + ac.PROPOSE_MAX]
            with mock.patch.object(ai, 'ai_tools', FakeTools(use(*chunk))):
                r = self.say('이것저것 해줘')
            self.assertEqual(r['cards'], [])
            self.assertEqual(r['kind'], 'reply')
            self.assertEqual(len(r['dropped']), len(chunk), r['dropped'])
        with mock.patch.object(ai, 'ai_tools', FakeTools(use(*([{'type': 'cast.say', 'data': {'text': '아홉'}}] * 9)))):
            r = self.say('아홉 번 해줘')
        self.assertEqual(len(r['cards']), ac.PROPOSE_MAX)                             # 넘치는 줄은 안 본다
        # 모르는 도구 이름 · 사전이 아닌 입력은 통째로 버린다
        weird = ([('rm_rf', {'commands': [{'type': 'cast.say', 'data': {'text': 'x'}}]}), (ac.TOOL_NAME, 'oops')], '', 200)
        with mock.patch.object(ai, 'ai_tools', FakeTools(weird)):
            r = self.say('뭔가 해줘')
        self.assertEqual((r['kind'], r['cards']), ('none', []))
        self.assertEqual(self.st()['cast']['say']['text'], '아홉')                      # 'x' 는 안 나갔다

    def test_safe_runs_directly_with_undo(self):
        st = self.st()
        old = st['notice']['msgs'][0]
        r = self.say('공지 바꿔: 오늘은 10시까지!')                                     # 서버 규칙 — AI 안 부름
        self.assertEqual(r['source'], 'rule')
        c = r['cards'][0]
        self.assertEqual((c['type'], c['state']), ('notice.edit', 'ran'))
        self.assertEqual(self.st()['notice']['msgs'][0], '오늘은 10시까지!')
        self.assertEqual(c['undo'], {'type': 'notice.edit', 'data': {'index': 0, 'text': old}, 'text': '공지 1번을 전 글로'})
        code, res = self.cmd(c['undo']['type'], **c['undo']['data'])                  # [되돌리기]
        self.assertEqual(code, 200, res)
        self.assertEqual(self.st()['notice']['msgs'][0], old)
        r = self.say('룰렛판 띄워')
        self.assertEqual(self.st()['show']['stage'], 'roulette')
        u = r['cards'][0]['undo']
        self.cmd(u['type'], **u['data'])
        self.assertIsNone(self.st()['show']['stage'])
        r = self.say('조명 빨강으로 바꿔')
        self.assertEqual(self.st()['lights']['color'], '#ff0000')
        self.assertEqual(r['cards'][0]['undo']['type'], 'lights.set')
        ev = self.c.app.state.store.db.execute("SELECT by FROM events WHERE type = 'lights.color'").fetchone()
        self.assertEqual(ev['by'], 'ai')                                              # 장부에 'AI 가 함'

    def test_switch_off_means_cards(self):
        self.cmd('ai.set', direct=False)
        r = self.say('한마디: 안녕하세요')
        self.assertEqual(r['cards'][0]['state'], 'ask')
        self.assertIsNone(self.st()['cast'].get('say'))
        self.assertEqual(self.cmd('ai.set', direct='yes')[0], 400)

    def test_direct_limits(self):
        many = [{'type': 'cast.say', 'data': {'text': '하나 %d' % i}} for i in range(5)]
        with mock.patch.object(ai, 'ai_tools', FakeTools(use(*many))):
            r = self.say('다섯 번 말해줘')
        self.assertEqual([c['state'] for c in r['cards']], ['ran', 'ran', 'ran', 'ask', 'ask'])   # 한 번 말에 3개
        self.assertIn('3개까지', r['note'])
        for i in range(7):                                                            # 1분에 10개
            self.say('한마디: 또 %d' % i)
        r = self.say('한마디: 열한 번째')
        self.assertEqual(r['cards'][0]['state'], 'ask')
        self.assertIn('1분에 10개', r['note'])

    def test_client_bgm_and_match_rule(self):
        r = self.say('BGM 다음 곡')
        self.assertEqual((r['cards'][0]['type'], r['cards'][0]['state']), ('bgm.next', 'client'))
        r = self.say('대결 3분 시작')
        self.assertEqual([(c['type'], c['state']) for c in r['cards']], [('match.set_time', 'ask'), ('match.start', 'ask')])
        self.assertFalse(self.st()['match']['timer']['running'])                      # 게임은 사람이 [실행]
        r = self.say('서아랑 기여도 3')
        self.assertEqual(r['cards'][0]['data'], {'name': '서아', 'list': 'list', 'delta': 0, 'contrib': 3})

    def test_pending_assign_card_checks_roster(self):
        self.don('별빛', 30000, 'toon_pa1', '응원')
        pid = self.st()['pending'][0]['id']
        ft = FakeTools(use({'type': 'pending.assign', 'data': {'id': pid, 'name': '서아'}},
                           {'type': 'pending.assign', 'data': {'id': pid, 'name': '철수'}}))
        with mock.patch.object(ai, 'ai_tools', ft):
            r = self.say('별빛 후원 서아 줘')
        self.assertEqual([c['state'] for c in r['cards']], ['ask'])
        self.assertIn("'별빛 3만 원' → 서아", r['cards'][0]['text'])
        self.assertIn('철수', r['dropped'][0]['why'])
        self.assertEqual(len(self.st()['pending']), 1)                                # 사람이 누르기 전엔 그대로

    def test_ai_off_or_busy_falls_back_quietly(self):
        with mock.patch.object(ai, 'claude_key', lambda: ''):
            r = self.say('뭔가 바꿔줘')
        self.assertEqual(r['kind'], 'none')
        with mock.patch.object(ai, 'ai_tools', FakeTools(([], '', 529))):
            r = self.say('뭔가 바꿔줘')
        self.assertEqual(r['kind'], 'none')
        r = self.say('공지 바꿔: 키 없어도 됨')                                         # 서버 규칙은 AI 없이
        self.assertEqual(r['cards'][0]['state'], 'ran')

    def test_only_safe_list_can_run_directly(self):
        self.assertFalse(set(ac.SAFE) & set(ac.ASK))
        for t in ac.SAFE:
            self.assertNotIn(t.split('.')[0], ('score', 'pending', 'session', 'fundjar', 'donation', 'match', 'dice'))
        for big in ('session.start', 'session.end', 'score.undo', 'admin.import_old', 'sigadmin.drop', 'layout.import_old',
                    'preset.delete', 'signature.play', 'donation.add', 'fundjar.reset'):
            self.assertNotIn(big, ac.ALLOW)


class ToolsCall(unittest.TestCase):
    """ai.ai_tools — 키 없으면 안 부르고, 붐비면 한 번 더, SDK 에 temperature 를 안 보낸다(가짜 클라이언트)."""

    def setUp(self):
        _block(self, claude=FAKE)

    def test_no_key(self):
        with mock.patch.object(ai, 'claude_key', lambda: ''):
            self.assertEqual(ai.ai_tools('s', [], []), ([], '', 'nokey'))

    def test_retry_once(self):
        seq = [([], '', 529), ([('x', {})], '', 200)]
        with mock.patch.object(ai, '_claude_tools_call', lambda *a: seq.pop(0)), mock.patch.object(ai.time, 'sleep', lambda s: None):
            self.assertEqual(ai.ai_tools('s', [], [])[2], 200)

    def test_sdk_shape(self):
        import types
        seen = {}

        class Msgs:
            def create(self, **kw):
                seen.update(kw)
                return types.SimpleNamespace(content=[types.SimpleNamespace(type='tool_use', name=ac.TOOL_NAME, input={'commands': []}),
                                                      types.SimpleNamespace(type='text', text='ok')])

        class Client:
            def with_options(self, **o):
                return types.SimpleNamespace(messages=Msgs())
        with mock.patch.object(ai, '_claude_client', lambda: Client()):
            uses, text, code = REAL_TOOLS('sys', [{'role': 'user', 'content': 'x'}], [ac.tool_def()], {'type': 'any'}, 100, 5)
        self.assertEqual((uses, text, code), ([(ac.TOOL_NAME, {'commands': []})], 'ok', 200))
        self.assertNotIn('temperature', seen)
        self.assertEqual(seen['tool_choice'], {'type': 'any'})
        self.assertEqual(seen['tools'][0]['name'], ac.TOOL_NAME)


# ══ ⏸ 애매하면 보류 — 규칙 'auto' 도 안 준다 ══
class Hold(AutoBase):
    MODE = 'on'

    def check(self, pid):
        it = self.item(pid)
        self.assertIsNotNone(it, '기계가 줬다')
        a = it['auto']
        self.assertEqual(a['held'], 'check')
        self.assertTrue(a['hold'])
        return a['hold']

    def test_every_ambiguity_holds(self):
        cases = [
            ('a1', 30000, '하율 서아 둘 다 화이팅', '선수가 둘 이상'),
            ('a2', 30000, '하율 반반 나눠서', '나눔 말'),
            ('a3', 30000, '하율 5만원 보냅니다', '메시지 금액 5만 원 ≠ 실제 3만 원'),
            ('a4', 30000, '하율 5점', '메시지 5점'),
            ('a5', 15000, '하율 화이팅', '만 원 단위 경계'),
            ('a6', 100000, '하율 화이팅', '금액 상한'),
        ]
        ids = {}
        for nm, amt, msg, _ in cases:
            ids[nm] = self.give(nm, amt, msg)
        self.drain()
        for nm, amt, msg, want in cases:
            self.assertTrue(any(want in w for w in self.check(ids[nm])), (nm, self.item(ids[nm])['auto']['hold']))
        self.assertEqual(self.player('하율')['score'], 0)
        self.assertEqual(self.stats()['auto_done'], 0)

    def test_bundle_bank_and_history(self):
        d1 = self.give('반복', 10000, '하율 화이팅')
        d2 = self.give('반복', 10000, '하율 화이팅')                                 # 같은 사람 연속(대기함에 여럿 · ×N)
        self.drain()
        self.assertTrue(any('같은 사람' in w for w in self.check(d1)))
        self.assertTrue(any('같은 사람' in w for w in self.check(d2)))
        c, r = self.don('입금자', 30000, 'manual_bank_b0123456789ab', '하율 화이팅')
        self.assertEqual(c, 200, r)
        self.drain()
        self.assertTrue(any('계좌 입금' in w for w in self.check(r['id'])))
        # 이력이 여러 선수로 갈림
        store = self.c.app.state.store
        from v2.server.domain import donor_memory as dm
        dm.remember_assignment(store, '갈림', '하율', 10000, '', ref='x1')
        dm.remember_assignment(store, '갈림', '서아', 10000, '', ref='x2')
        pid = self.give('갈림', 30000, '하율 화이팅')
        self.drain()
        self.assertTrue(any('이력이 여러 선수' in w for w in self.check(pid)))

    def test_clean_one_still_auto(self):
        pid = self.give('깔끔', 30000, '하율 화이팅')
        self.drain()
        self.assertIsNone(self.item(pid))
        self.assertEqual(self.player('하율')['score'], 3)

    def test_shadow_counts_held(self):
        self.cmd('auto.set', mode='shadow')
        pid = self.give('그림자', 15000, '하율 화이팅')
        self.drain()
        a = self.item(pid)['auto']
        self.assertTrue(a['check'])
        self.assertFalse(a['act'])
        self.cmd('pending.assign', id=pid, name='하율')
        self.assertEqual(self.row(pid)['outcome'], 'held')
        self.assertEqual(self.stats()['held'], 1)
        self.cmd('score.undo', ref=pid)                                               # 되돌리면 숫자도 뺀다
        self.assertEqual(self.stats()['held'], 0)


# ══ ③ AI 배정 ══
def ai_says(target, conf):
    return FakeNim((FakeResp(200, '{"target": "%s", "confidence": %s}' % (target, conf)), 200, 'm'))


class AiAssign(AutoBase):
    MODE = 'on'
    KEY = FAKE

    def setUp(self):
        super().setUp()
        self.cmd('auto.set', use_ai_assign=True)

    def test_sure_ai_assigns(self):
        with mock.patch.object(ai, 'nim_post', ai_says('채원', 0.95)) as f:
            pid = self.give('별빛', 20000, '오늘도 응원해요')
            self.drain()
        self.assertEqual(len(f.calls), 1)
        self.assertIsNone(self.item(pid))
        self.assertEqual(self.player('채원')['score'], 2)
        row = self.row(pid)
        self.assertEqual((row['outcome'], row['by'], row['ai']['confidence']), ('auto', 'autopilot-ai', 0.95))
        s = self.st()
        self.assertEqual(s['logs'][0]['by'], 'autopilot-ai')                          # 점수 기록 줄에 '🤖 AI 가 줌'
        self.assertEqual((self.stats()['ai_done'], self.stats()['auto_done']), (1, 1))
        # 잘못 갔으면 되돌리기 — 대기함으로 돌아오고 다시는 자동으로 안 준다
        self.cmd('score.undo', ref=pid)
        it = self.item(pid)
        self.assertEqual((it['auto']['held'], it['auto'].get('was_ai')), ('returned', True))
        self.assertEqual(self.player('채원')['score'], 0)
        self.assertEqual(self.stats()['ai_undone'], 1)

    def test_low_conf_late_or_off_holds(self):
        with mock.patch.object(ai, 'nim_post', ai_says('채원', 0.89)):
            p1 = self.give('a', 20000, '오늘도 응원해요')
            self.drain()
        a = self.item(p1)['auto']
        self.assertEqual(a['held'], 'unsure')
        self.assertTrue(any('0.9 미만' in w for w in a['hold']))
        with mock.patch.object(ai, 'nim_post', ai_says('철수', 0.99)):                # 지금 판에 없는 이름
            p2 = self.give('b', 20000, '좋은 밤')
            self.drain()
        self.assertIsNotNone(self.item(p2))
        with mock.patch.object(ai, 'nim_post', ai_says('채원', 0.99)), mock.patch.object(apm, 'AI_DEADLINE_SEC', -1):
            p3 = self.give('c', 20000, '반가워요')                                      # 10초 넘긴 답
            self.drain()
        self.assertTrue(any('늦음' in w for w in self.item(p3)['auto']['hold']))
        with mock.patch.object(ai, 'nim_post', FakeNim((None, 503, 'm'))) as f:      # 막힘 → 다시 물어도 그 답으로는 안 준다
            p4 = self.give('d', 20000, '좋은 하루')
            self.drain(keep=('auto.decide',))
            self.timers.clear()
        self.assertIsNotNone(self.item(p4))
        self.cmd('auto.set', use_ai_assign=False)                                     # 스위치 끔 — AI 를 안 묻는다
        with mock.patch.object(ai, 'nim_post', ai_says('채원', 0.99)) as f:
            p5 = self.give('e', 20000, '안녕하세요 여러분', tx='toon_e5')
            self.drain()
        self.assertIsNotNone(self.item(p5))
        self.assertEqual(self.player('채원')['score'], 0)

    def test_ambiguous_never_ai_assigned(self):
        with mock.patch.object(ai, 'nim_post', ai_says('채원', 0.99)):
            pid = self.give('a', 15000, '오늘도 응원해요')                               # 만 원 경계 — AI 가 확신해도 안 준다
            self.drain()
        a = self.item(pid)['auto']
        self.assertEqual(a['held'], 'check')
        self.assertFalse(a['ai']['act'])
        self.assertEqual(self.player('채원')['score'], 0)
        with mock.patch.object(ai, 'nim_post', FakeNim()) as f:                      # 규칙 답이 있는데 애매 — AI 를 아예 안 부른다
            pid = self.give('b', 15000, '서아화이팅이에요')
            self.drain()
        self.assertEqual(f.calls, [])
        self.assertEqual(self.item(pid)['auto']['held'], 'check')

    def test_suggest_tier_rule_then_ai(self):
        """규칙이 'suggest'(글자만 겹침 0.75) — AI 에게 한 번 더 묻고, 확신이 높으면 AI 가 준다. 같은 후원은 두 번 안 묻는다."""
        with mock.patch.object(ai, 'nim_post', ai_says('서아', 0.97)) as f:
            pid = self.give('햇빛', 20000, '서아화이팅이에요')
            ran = self.drain()
            self.assertEqual([t for t, _ in ran], ['auto.decide', 'auto.ai'])
            self.assertEqual(len(f.calls), 1)
            r = self.c.post('/api/audit/suggest', json={'id': pid}, headers=H).json()
        self.assertTrue(r.get('gone'))                                                # 이미 줬다
        self.assertEqual(self.player('서아')['score'], 2)


class AiShadow(AutoBase):
    MODE = 'shadow'
    KEY = FAKE

    def test_ai_is_scored_separately(self):
        two = FakeNim(*[(FakeResp(200, '{"target": "채원", "confidence": 0.95}'), 200, 'm')] * 2)
        with mock.patch.object(ai, 'nim_post', two):
            p1 = self.give('a', 20000, '오늘도 응원해요')
            p2 = self.give('b', 20000, '좋은 밤이에요')
            self.drain()
        with mock.patch.object(ai, 'nim_post', ai_says('하율', 0.5)):
            p3 = self.give('c', 20000, '반가워요')
            self.drain()
        self.assertEqual(self.item(p1)['auto']['ai']['act'], True)                   # AI 라면 줬을 것(그림자 — 안 줌)
        self.assertEqual(self.player('채원')['score'], 0)
        self.cmd('pending.assign', id=p1, name='채원')                               # AI 맞힘
        self.cmd('pending.assign', id=p2, name='하율')                               # AI 틀림
        self.cmd('pending.assign', id=p3, name='하율')                               # AI 는 보류였음
        st = self.stats()
        self.assertEqual((st['ai_agree'], st['ai_disagree'], st['ai_held']), (1, 1, 1))
        self.assertEqual(st['unknown'], 3)                                            # 규칙 채점은 따로(규칙은 셋 다 몰라서 보류)

    def test_settings_validation(self):
        self.assertEqual(self.cmd('auto.set', use_ai_assign='on')[0], 400)
        self.assertEqual(self.cmd('auto.set', assign_max=500)[0], 400)
        c, r = self.cmd('auto.set', assign_max='50,000')
        self.assertEqual((c, r['assign_max']), (200, 50000))
        self.assertFalse(self.ap()['use_ai_assign'])                                  # 기본 끔


class Money(unittest.TestCase):
    def test_money_in_message(self):
        self.assertEqual(apm.money_in_message('밍밍 5만원!', ['밍밍']), ([50000], []))
        self.assertEqual(apm.money_in_message('3만 원 보내요 3점', []), ([30000], [3]))
        self.assertEqual(apm.money_in_message('오만원 밍밍', ['밍밍']), ([50000], []))
        self.assertEqual(apm.money_in_message('1.5만원', []), ([15000], []))
        self.assertEqual(apm.money_in_message('30,000원 쏩니다', []), ([30000], []))
        self.assertEqual(apm.money_in_message('밍밍2 화이팅', ['밍밍2']), ([], []))   # 이름 속 숫자는 금액이 아니다
        self.assertEqual(apm.money_in_message('20000', []), ([20000], []))


if __name__ == '__main__':
    unittest.main()
