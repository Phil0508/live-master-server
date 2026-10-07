# -*- coding: utf-8 -*-
"""🤖 Claude 를 먼저 부르는 길(ai.ai_post) — 키가 있으면 Claude, 막히면 NVIDIA 예비, 키 · 모델이 틀리면 다시 안 묻는다.

⚠️ 진짜 Claude · NVIDIA 는 절대 부르지 않는다 — ai._claude_call(바깥으로 나가는 곳)과 ai.nim_post 를 가짜로 바꾼다.
   SDK 를 제대로 부르는지는 ai._claude_client 를 가짜 클라이언트로 바꿔 본다(네트워크 없음).
"""
import os
import time
import types
import unittest
from unittest import mock

from v2.server.domain import ai
from v2.tests.test_ai import Base, FakeNim, FakeResp, H, _guard

NAMES = ['하율', '서아', '채원']


class FakeClaude:
    """ai._claude_call 대신 — 부른 기록을 남기고 정해 둔 (글자, 코드)를 차례로 돌려준다."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, system, messages, max_tokens, temperature, timeout):
        self.calls.append({'system': system, 'messages': messages, 'max_tokens': max_tokens,
                           'temperature': temperature, 'timeout': timeout})
        return self.answers.pop(0) if self.answers else (None, 529)


def _keys(case, claude='claude-test-key-not-real', nim=''):
    for p in (mock.patch.object(ai, 'claude_key', lambda: claude), mock.patch.object(ai, 'nim_key', lambda: nim)):
        p.start()
        case.addCleanup(p.stop)


class ClaudePath(unittest.TestCase):
    def setUp(self):
        _guard(self)

    def test_claude_first_for_suggest(self):
        _keys(self, nim='nim-test-key')
        fc = FakeClaude(('음 {"target": "채원", "confidence": 0.9} 끝', 200))
        with mock.patch.object(ai, '_claude_call', fc), mock.patch.object(ai, 'nim_post', FakeNim()) as fn:
            r = ai.nim_suggest_target('별빛', 20000, '오늘도 응원해요', NAMES)
        self.assertEqual((r['target'], r['confidence']), ('채원', 0.9))
        self.assertEqual(fn.calls, [])                                   # NVIDIA 는 안 불렀다
        c = fc.calls[0]
        self.assertIn('채원', c['system'])                                 # 선수 명단이 system 으로
        self.assertEqual([m['role'] for m in c['messages']], ['user'])
        self.assertEqual((c['max_tokens'], c['timeout']), (200, ai.SUGGEST_TIMEOUT))
        self.assertEqual(ai.NIM_HEALTH['model'], ai.CLAUDE_MODEL)
        self.assertTrue(ai.ai_health()['text'].startswith('Claude 연결됨'))

    def test_busy_falls_back_to_nvidia_once(self):
        _keys(self, nim='nim-test-key')
        fc = FakeClaude((None, 529))
        fn = FakeNim((FakeResp(200, '{"target": "서아", "confidence": 0.8}'), 200, ai.NIM_MODEL))
        with mock.patch.object(ai, '_claude_call', fc), mock.patch.object(ai, 'nim_post', fn):
            r = ai.nim_suggest_target('별빛', 20000, '응원해요', NAMES)
        self.assertEqual(r['target'], '서아')
        self.assertEqual(len(fc.calls), 1)                               # 예비가 있으면 Claude 는 한 번만
        self.assertEqual(fn.calls[0]['models'], [ai.NIM_MODEL, ai.NIM_MODEL, ai.NIM_MODEL_BACKUP])

    def test_no_backup_tries_twice_then_retry_later(self):
        _keys(self)
        fc = FakeClaude((None, 529), (None, 0))
        with mock.patch.object(ai, '_claude_call', fc), mock.patch.object(ai, 'nim_post', FakeNim()) as fn:
            r = ai.nim_suggest_target('별빛', 20000, '응원해요', NAMES)
        self.assertEqual(len(fc.calls), 2)
        self.assertEqual(fn.calls, [])
        self.assertTrue(r['retry'])                                      # 조금 뒤 다시(배지 · 자동 진행이 20초 × n)

    def test_wrong_key_or_model_is_not_retried(self):
        _keys(self)
        for code in (401, 404):
            fc = FakeClaude((None, code))
            with mock.patch.object(ai, '_claude_call', fc):
                r = ai.nim_suggest_target('별빛', 20000, '응원해요', NAMES)
            self.assertEqual(len(fc.calls), 1, code)
            self.assertFalse(r.get('retry'), code)
        self.assertTrue(r.get('gone'))                                   # 404 = 모델이 없어졌다(CLAUDE_MODEL 을 바꿀 것)
        self.assertEqual(ai.model_setting(ai.CLAUDE_MODEL), 'CLAUDE_MODEL')

    def test_no_keys_means_off(self):
        _keys(self, claude='', nim='')
        self.assertFalse(ai.ai_on())
        self.assertTrue(ai.nim_suggest_target('별빛', 20000, '응원해요', NAMES)['skipped'])
        self.assertEqual(ai.ai_health()['state'], 'off')

    def test_messages_shape(self):
        system, rest = ai._claude_messages([
            {'role': 'system', 'content': '규칙 1'}, {'role': 'assistant', 'content': '먼저 한 말'},
            {'role': 'user', 'content': '  '}, {'role': 'system', 'content': '규칙 2'},
            {'role': 'user', 'content': '목표 얼마?'}, {'role': 'assistant', 'content': '3만 원'},
            {'role': 'user', 'content': '고마워'}])
        self.assertEqual(system, '규칙 1\n\n규칙 2')
        self.assertEqual([m['role'] for m in rest], ['user', 'assistant', 'user'])   # 첫 말은 사용자 · 빈 말은 뺀다

    def test_ai_off_switch_ignores_claude_key(self):
        with mock.patch.dict(os.environ, {'LM2_AI_OFF': '1', 'ANTHROPIC_API_KEY': 'fake-should-not-be-used'}):
            self.assertEqual(ai._load_claude_key(), '')
        with mock.patch.dict(os.environ, {'LM2_AI_OFF': '', 'ANTHROPIC_API_KEY': ' k-env '}):
            self.assertEqual(ai._load_claude_key(), 'k-env')


class ClaudeSdk(unittest.TestCase):
    """_claude_call 이 SDK 를 문서대로 부르고, SDK 오류를 상태 코드로 바꾸는지 — 가짜 클라이언트로(네트워크 없음)."""

    def _client(self, result=None, exc=None):
        seen = {}

        class Msgs:
            def create(self, **kw):
                seen['kw'] = kw
                if exc is not None:
                    raise exc
                return result

        class Client:
            def with_options(self, **o):
                seen['opts'] = o
                return types.SimpleNamespace(messages=Msgs())
        return Client(), seen

    def test_request_shape_and_text(self):
        msg = types.SimpleNamespace(content=[types.SimpleNamespace(type='text', text=' 하율 '),
                                             types.SimpleNamespace(type='text', text='이에요 ')])
        cl, seen = self._client(result=msg)
        with mock.patch.object(ai, '_claude_client', lambda: cl):
            text, code = ai._claude_call('시스템', [{'role': 'user', 'content': '누구?'}], 200, 0.1, 8)
        self.assertEqual((text, code), ('하율 이에요', 200))
        self.assertEqual(seen['opts'], {'timeout': 8})
        kw = seen['kw']
        self.assertEqual((kw['model'], kw['max_tokens'], kw['temperature'], kw['system']), ('claude-haiku-4-5', 200, 0.1, '시스템'))
        cl, seen = self._client(result=msg)
        with mock.patch.object(ai, '_claude_client', lambda: cl):
            ai._claude_call('', [{'role': 'user', 'content': '누구?'}], 200, 0.1, 8)
        self.assertNotIn('system', seen['kw'])                           # 빈 system 은 안 보낸다

    def test_errors_become_codes(self):
        import anthropic
        import httpx2
        req = httpx2.Request('POST', 'https://api.anthropic.com/v1/messages')
        cases = [(anthropic.RateLimitError('rl', response=httpx2.Response(429, request=req), body=None), 429),
                 (anthropic.APIStatusError('overloaded', response=httpx2.Response(529, request=req), body=None), 529),
                 (anthropic.AuthenticationError('key', response=httpx2.Response(401, request=req), body=None), 401),
                 (anthropic.APITimeoutError(request=req), 0),
                 (anthropic.APIConnectionError(request=req), 0)]
        for exc, want in cases:
            cl, _ = self._client(exc=exc)
            with mock.patch.object(ai, '_claude_client', lambda: cl):
                self.assertEqual(ai._claude_call('', [{'role': 'user', 'content': 'x'}], 10, 0.1, 1), (None, want))

    def test_missing_sdk_falls_back(self):
        def boom():
            raise ImportError('anthropic')
        with mock.patch.object(ai, '_claude_client', boom):
            self.assertEqual(ai._claude_call('', [{'role': 'user', 'content': 'x'}], 10, 0.1, 1), (None, 0))


class ClaudeChat(Base):
    def test_chat_uses_claude_and_bad_key_message(self):
        _keys(self)
        fc = FakeClaude(('**하율**이 1등이에요.', 200), (None, 401))
        with mock.patch.object(ai, '_claude_call', fc), mock.patch.object(ai, 'nim_post', FakeNim()) as fn:
            r = self.c.post('/api/ai/chat', json={'question': '누가 1등이야?',
                                                   'messages': [{'role': 'assistant', 'content': '안녕하세요'}]}, headers=H).json()
            self.assertEqual((r['source'], r['reply']), ('ai', '**하율**이 1등이에요.'))
            self.assertEqual(fc.calls[0]['messages'][-1], {'role': 'user', 'content': '누가 1등이야?'})
            self.assertEqual(fc.calls[0]['messages'][0]['role'], 'user')  # 앞선 assistant 말은 뺐다
            r = self.c.post('/api/ai/chat', json={'question': '목표 얼마 남았어'}, headers=H).json()
            self.assertIn('ANTHROPIC_API_KEY', r['reply'])                # 키가 틀렸다 — 무엇을 고칠지
            self.assertEqual(fn.calls, [])


if __name__ == '__main__':
    unittest.main()
