# -*- coding: utf-8 -*-
"""🙈 메시지 금칙어 · [가리기](10-17 안전 꾸러미 mask).

① 규칙: 전화번호 · 계좌번호 꼴 숫자 · 인터넷 주소 · 금칙어 → ●●● / 금액 · 날짜 · 띄어 쓴 다른 말은 그대로
② 방송판(로그인 없음 · 로그인한 방송판 종류)은 통째 · 쪽지 어디에도 원문이 없다 — 조종실 · 장부 · 대기함은 원문 그대로
③ [가리기] 즉시 반영(팝업 · 시그니처 대기줄 · 묶음 차례 · 다시 송출) · [보이기] 로 되돌림
④ 이름(닉네임)은 건드리지 않는다 · mask 조각은 방송판에 안 간다 · 새 방송이면 가린 목록만 비운다
⑤ 조종실 새 파일에 confirm() · alert() · 소리 없음
"""
import json
import os
import re
import unittest

from v2.server.domain import mask as mk
from v2.tests.test_flow import Base, H, SECRET

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PHONE = '010-1234-5678'
MSG = '하율 화이팅 연락줘 ' + PHONE


def msg_texts(obj):
    """사전 · 목록을 끝까지 뒤져 message · msgs 글자를 모두."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ('message', 'msg') and isinstance(v, str):
                out.append(v)
            elif k == 'msgs' and isinstance(v, list):
                out += [x for x in v if isinstance(x, str)]
            else:
                out += msg_texts(v)
    elif isinstance(obj, list):
        for v in obj:
            out += msg_texts(v)
    return out


# ── ① 규칙 ──────────────────────────────────────────────
class Rules(unittest.TestCase):
    M = {'words': ['시발', '병신'], 'rules': {}}

    def t(self, text):
        return mk.check(text, self.M)

    def test_phone(self):
        for s in ('010-1234-5678', '010 1234 5678', '010.1234.5678', '01012345678', '+82 10-1234-5678', '02-123-4567', '031-123-4567',
                  '070 1234 5678'):
            got, hits = self.t('연락 ' + s + ' 줘')
            self.assertEqual(got, '연락 ●●● 줘', s)
            self.assertEqual(hits, ('phone',), s)

    def test_account(self):
        for s in ('123456-78-901234', '352-1234-5678-93', '3333011234567', '110 123 456789', '1002-123-456789'):
            got, hits = self.t('국민 ' + s + ' 로')
            self.assertEqual(got, '국민 ●●● 로', s)
            self.assertIn('account', hits, s)

    def test_url_and_mail(self):
        for s in ('www.abc.com', 'https://x.y/z?q=1', 'http://naver.me/abc', 'open.kakao.com/o/abc', 'abc@naver.com', 't.me/xyz',
                  'abc.co.kr', 'abc 닷컴', 'ABC.COM'):
            got, hits = self.t('여기 ' + s + ' 와')
            self.assertEqual(got, '여기 ●●● 와', s)
            self.assertEqual(hits, ('url',), s)

    def test_words_with_gaps(self):
        self.assertEqual(self.t('시1발 너무 좋아')[0], '●●● 너무 좋아')
        self.assertEqual(self.t('시.발')[0], '●●●')
        self.assertEqual(self.t('병신같이')[0], '●●●같이')
        self.assertEqual(self.t('시발')[1], ('word',))

    def test_left_alone(self):
        for s in ('100,000원 후원', '2025-10-17 21:03 방송', '5만원', '오늘 21시 30분', 'BJ123 화이팅', '하율.사랑해', '010',
                  '이 시 발표', '병 신', '1,000,000,000원', ''):
            self.assertEqual(self.t(s), (s, ()), s)

    def test_rules_can_be_turned_off(self):
        m = {'words': [], 'rules': {'phone': False, 'account': False, 'url': True}}
        self.assertEqual(mk.check('010-1234-5678', m)[0], '010-1234-5678')
        self.assertEqual(mk.check('www.a.com', m)[0], '●●●')

    def test_default_has_no_words(self):
        self.assertEqual(mk.check('시발', None), ('시발', ()))
        self.assertTrue(len(mk.RECOMMENDED) >= 5)


# ── ②③④ 서버 ──────────────────────────────────────────────
class T(Base):
    def setUp(self):
        super().setUp()
        self.ok('mask.word.add', word='시발')

    def ok(self, t, **data):
        c, r = self.cmd(t, **data)
        self.assertEqual(c, 200, r)
        self.assertTrue(r.get('ok'), r)
        return r

    def pub(self):
        return self.c.get('/api/state').json()['slices']

    def collect(self, ws, fn):
        """fn 을 하고 → 다시 달라고 해서 통째가 올 때까지 받은 쪽지 · 통째를 모두."""
        fn()
        ws.send_json({'t': 'resync'})
        got = []
        while True:
            m = ws.receive_json()
            got.append(m)
            if m.get('t') == 'snapshot':
                return got

    def don_id(self, name):
        return next(r['id'] for r in self.c.get('/api/ledger?limit=200', headers=H).json()['rows'] if r['name'] == name)


class Broadcast(T):
    def test_public_snapshot_masked_private_raw(self):
        self.don('별빛', 10300, 'toon_m1', msg=MSG + ' 시발')               # 1만 원 시그(sig 1) — 팝업 + 대기줄
        p = self.pub()
        self.assertNotIn('mask', p)                                          # 금칙어 목록 · 가린 목록은 방송판에 안 간다
        self.assertEqual(p['popup']['donation']['message'], '하율 화이팅 연락줘 ●●● ●●●')
        self.assertEqual(p['queue']['items'][0]['message'], '하율 화이팅 연락줘 ●●● ●●●')
        self.assertNotIn('don_ids', p['queue']['items'][0])
        blob = json.dumps(p, ensure_ascii=False)
        self.assertNotIn('5678', blob)
        self.assertNotIn('시발', blob)
        s = self.st()                                                        # 조종실 — 원문 그대로
        self.assertEqual(s['popup']['donation']['message'], MSG + ' 시발')
        self.assertEqual(s['queue']['items'][0]['message'], MSG + ' 시발')
        self.assertEqual(s['pending'][0]['message'], MSG + ' 시발')
        self.assertEqual(s['pending'][0]['mask']['hits'], ['phone', 'word'])
        self.assertEqual(s['pending'][0]['mask']['text'], '하율 화이팅 연락줘 ●●● ●●●')
        rows = self.c.get('/api/ledger?limit=200', headers=H).json()['rows']
        self.assertEqual(rows[0]['message'], MSG + ' 시발')                  # 장부 원문
        self.assertEqual(rows[0]['mask']['hits'], ['phone', 'word'])

    def test_overlay_never_receives_raw(self):
        """로그인 없는 방송판 · 로그인한 방송판(같은 브라우저) 모두 — 통째든 쪽지든 원문이 한 번도 안 온다. 조종실은 원문."""
        with self.c.websocket_connect('/ws?kind=overlay') as ov, \
                self.c.websocket_connect('/ws?kind=sigdisp&token=' + SECRET) as sd, \
                self.c.websocket_connect('/ws?kind=controller&token=' + SECRET) as ct:
            seen = {}
            for name, ws in (('ov', ov), ('sd', sd), ('ct', ct)):
                seen[name] = [ws.receive_json()]
            self.don('별빛', 10300, 'toon_w1', msg=MSG)
            self.don('달빛', 5000, 'toon_w2', msg='소액 ' + PHONE, display_only=True)       # 소액 띠
            self.don('해빛', 30000, 'manual_w3', msg='손 송출 www.abc.com', trusted=True)   # 손 송출
            self.ok('cast.fx', kinds=['banner'], name='별빛', amount=1000, message='연락 ' + PHONE)
            for name, ws in (('ov', ov), ('sd', sd), ('ct', ct)):
                ws.send_json({'t': 'resync'})
                while True:
                    m = ws.receive_json()
                    seen[name].append(m)
                    if m.get('t') == 'snapshot':
                        break
            self.assertNotIn('pending', seen['sd'][0]['slices'])                   # 로그인한 방송판도 비공개 조각은 안 받는다
            for name in ('ov', 'sd'):
                texts = [t for m in seen[name] for t in msg_texts(m.get('slices') or {})]
                self.assertTrue(any('●●●' in t for t in texts), name)
                blob = json.dumps(seen[name], ensure_ascii=False)
                self.assertNotIn('5678', blob, name)
                self.assertNotIn('abc.com', blob, name)
                self.assertGreater(len(seen[name]), 4, '쪽지를 못 봤다(검사가 헛돈다)')
            ct_blob = json.dumps(seen['ct'], ensure_ascii=False)
            self.assertIn(PHONE, ct_blob)                                         # 조종실은 원문
            self.assertIn('www.abc.com', ct_blob)

    def test_name_untouched(self):
        self.don('시발맨010', 10300, 'toon_n1', msg='안녕')
        p = self.pub()
        self.assertEqual(p['popup']['donation']['name'], '시발맨010')
        self.assertEqual(p['queue']['items'][0]['donator'], '시발맨010')

    def test_words_change_resends_popup(self):
        self.don('별빛', 50000, 'toon_r1', msg='나쁜말 쓰지마')
        self.assertEqual(self.pub()['popup']['donation']['message'], '나쁜말 쓰지마')
        with self.c.websocket_connect('/ws?kind=overlay') as ov:
            ov.receive_json()
            got = self.collect(ov, lambda: self.ok('mask.word.add', word='나쁜말'))
            patch = next(m for m in got if m.get('t') == 'patch')
            self.assertEqual(patch['slices']['popup']['donation']['message'], '●●● 쓰지마')
            self.assertNotIn('mask', patch['slices'])
        self.ok('mask.word.remove', word='나쁜말')
        self.assertEqual(self.pub()['popup']['donation']['message'], '나쁜말 쓰지마')

    def test_word_commands(self):
        r = self.ok('mask.word.add', word='가, 나 ,가')
        self.assertEqual(r['added'], ['가', '나'])
        r = self.ok('mask.word.recommend')
        self.assertIn('씨발', r['added'])
        self.assertNotIn('시발', r['added'])                                 # 이미 있던 것은 건너뛴다
        self.assertEqual(self.cmd('mask.word.remove', word='없는말')[0], 404)
        self.ok('mask.word.clear')
        self.assertEqual(self.st()['mask']['words'], [])
        self.assertEqual(self.cmd('mask.rule', key='nope', on=False)[0], 400)
        self.ok('mask.rule', key='phone', on=False)
        self.don('별빛', 50000, 'toon_c1', msg=PHONE)
        self.assertEqual(self.st()['pending'][-1]['mask']['hits'], ['account'])   # 전화 거르기 끔 → 계좌 꼴 숫자로는 잡힌다
        self.assertEqual(self.c.post('/api/cmd', json={'type': 'mask.word.add', 'data': {'word': 'x'}}).status_code, 401)

    def test_preview(self):
        r = self.c.post('/api/mask/preview', json={'text': '시발 ' + PHONE}, headers=H).json()
        self.assertEqual((r['text'], sorted(r['hits'])), ('●●● ●●●', ['phone', 'word']))
        self.assertEqual(self.c.post('/api/mask/preview', json={'text': 'x'}).status_code, 401)


class Hide(T):
    def test_hide_popup_and_queue_now(self):
        self.don('별빛', 10300, 'toon_h1', msg='고마워요 하율')
        did = self.don_id('별빛')
        with self.c.websocket_connect('/ws?kind=overlay') as ov:
            ov.receive_json()
            got = self.collect(ov, lambda: self.ok('mask.hide', id=did))
            patch = next(m for m in got if m.get('t') == 'patch')
            self.assertEqual(patch['slices']['popup']['donation']['message'], '')       # 떠 있는 팝업에서 바로
            self.assertEqual(patch['slices']['queue']['items'][0]['message'], '')      # 시그니처 카드 · 대기줄 · 전광판에서 바로
        s = self.st()
        self.assertEqual(s['pending'][0]['message'], '고마워요 하율')                    # 대기함은 그대로
        self.assertIn(did, s['mask']['hidden'])
        self.ok('mask.hide', id=did, on=False)
        self.assertEqual(self.pub()['popup']['donation']['message'], '고마워요 하율')

    def test_hide_one_of_bundle(self):
        self.don('별빛', 10300, 'toon_b1', msg='첫째')
        self.don('별빛', 10300, 'toon_b2', msg='둘째 www.x.com')
        it = self.pub()['queue']['items'][0]
        self.assertEqual(it['count'], 2)
        self.assertEqual(it['msgs'], ['첫째', '둘째 ●●●'])
        rows = self.c.get('/api/ledger?limit=200', headers=H).json()['rows']
        second = next(r['id'] for r in rows if r['message'].startswith('둘째'))
        self.ok('mask.hide', id=second)
        it = self.pub()['queue']['items'][0]
        self.assertEqual(it['msgs'], ['첫째', ''])                                     # 그 후원 차례만
        self.assertEqual(it['message'], '첫째')

    def test_hidden_replay_stays_hidden(self):
        self.don('별빛', 10300, 'toon_e1', msg='다시 봐도 비밀')
        did = self.don_id('별빛')
        self.ok('mask.hide', id=did)
        r = self.c.post('/api/donation/replay', json={'id': did}, headers=H)
        self.assertEqual(r.status_code, 200, r.json())
        p = self.pub()
        self.assertTrue(p['popup']['donation']['encore'])
        self.assertEqual(p['popup']['donation']['message'], '')
        self.assertNotIn('src', p['popup']['donation'])
        self.assertTrue(all(x['message'] == '' for x in p['queue']['items']))

    def test_hide_console_play_by_queue_id(self):
        """후원 콘솔 '바로 틀기'(장부 없음)도 대기줄 줄 id 로 가린다."""
        r = self.c.post('/api/signature/play', json={'name': '콘솔', 'amount': 10300, 'message': '바로 ' + PHONE}, headers=H)
        self.assertEqual(r.status_code, 200, r.json())
        it = self.pub()['queue']['items'][-1]
        self.assertEqual(it['message'], '바로 ●●●')
        self.ok('mask.hide', id=it['id'])
        self.assertEqual(self.pub()['queue']['items'][-1]['message'], '')

    def test_bank_send_masked_and_hideable(self):
        """계좌 송출(tx manual_bank_) — 같은 장부 id 로 가린다."""
        self.don('입금자', 30000, 'manual_bank_77', msg='계좌 메모 ' + PHONE, trusted=True)
        self.assertEqual(self.pub()['popup']['donation']['message'], '계좌 메모 ●●●')
        self.ok('mask.hide', id=self.don_id('입금자'))
        self.assertEqual(self.pub()['popup']['donation']['message'], '')

    def test_new_session_clears_hidden_only(self):
        self.don('별빛', 10300, 'toon_s1', msg='x')
        self.ok('mask.hide', id=self.don_id('별빛'))
        self.ok('session.end')
        self.ok('session.start', names=['하율'])
        m = self.st()['mask']
        self.assertEqual(m['hidden'], [])
        self.assertEqual(m['words'], ['시발'])

    def test_hide_touches_no_money_score_or_ledger(self):
        """[가리기] · 금칙어는 보여 주는 글만 — 점수 · 합계 · 장부 · 대기함 · 대기줄 개수는 그대로."""
        self.don('별빛', 10300, 'toon_m9', msg='돈은 그대로 ' + PHONE)
        did = self.don_id('별빛')

        def money():
            s = self.st()
            led = self.c.get('/api/ledger?limit=200', headers=H).json()
            return json.dumps([s['tallies'], s['players'], s['fundjar'], len(s['pending']), len(s['queue']['items']),
                               led['total'], led['count'], [(r['id'], r['amount'], r['status'], r['message']) for r in led['rows']]],
                              ensure_ascii=False, sort_keys=True)
        before = money()
        self.ok('mask.hide', id=did)
        self.ok('mask.word.add', word='그대로')
        self.ok('mask.rule', key='phone', on=False)
        self.ok('mask.hide', id=did, on=False)
        self.assertEqual(money(), before)

    def test_ai_cannot_mask(self):
        """🤖 AI(Ctrl+K)는 가리기 · 금칙어를 못 건드린다 — 사람이 단추로만."""
        from v2.server.domain import ai_cmd
        self.assertFalse([t for t in ai_cmd.ALLOW if t.startswith('mask.')])

    def test_bad_hide(self):
        self.assertEqual(self.cmd('mask.hide', id='')[0], 400)
        self.assertEqual(self.c.post('/api/cmd', json={'type': 'mask.hide', 'data': {'id': 'don_1'}}).status_code, 401)


class Views(unittest.TestCase):
    def test_screen_deep_and_blank_fallback(self):
        """끝 화면(엔딩 크레딧이 메시지를 실을 때)도 message · msgs 를 거른다 · 거르다 넘어지면 비운 사본."""
        m = {'words': ['시발'], 'hidden': ['don_9']}
        v = {'mode': 'end', 'snap': {'credits': [{'name': '시발맨', 'message': '시발 ' + PHONE},
                                                 {'id': 'don_9', 'message': '숨김'}, {'msgs': ['a.com', 'ok']}]}}
        got = mk.view('screen', v, {'mask': m}, True)
        self.assertEqual(got['snap']['credits'][0], {'name': '시발맨', 'message': '●●● ●●●'})
        self.assertEqual(got['snap']['credits'][1]['message'], '')
        self.assertEqual(got['snap']['credits'][2]['msgs'], ['●●●', 'ok'])
        self.assertEqual(v['snap']['credits'][0]['message'], '시발 ' + PHONE)          # 원본은 그대로
        self.assertIsNone(mk.view('screen', v, {'mask': m}, False))                  # 조종실은 원문
        bad = {'donation': {'id': 'x', 'message': PHONE}, 'score': None}
        self.assertEqual(mk._blank('popup', bad)['donation']['message'], '')


class Guards(unittest.TestCase):
    def test_long_message_is_fast_and_capped(self):
        """아주 긴 메시지(몇천 자)도 방송을 멈칫하게 하지 않는다 — 앞 SCAN_MAX 자만 거르고 '…'."""
        import time
        mk._check.cache_clear()
        t0 = time.time()
        got, hits = mk.check('a' * 20000 + ' ' + PHONE, {'words': list(mk.RECOMMENDED)})
        self.assertLess(time.time() - t0, 0.5)
        self.assertEqual(len(got), mk.SCAN_MAX + 1)
        self.assertTrue(got.endswith('…'))
        self.assertNotIn('5678', got)
        got, hits = mk.check(PHONE + ' ' + 'b' * 5000)
        self.assertTrue(got.startswith('●●● b'))
        self.assertEqual(hits, ('phone',))

    def test_screen_failure_blanks_not_raw(self):
        """끝 화면을 거르다 넘어지면 원본(원문)이 아니라 메시지를 비운 사본이 나간다."""
        v = {'mode': 'end', 'title': '오늘', 'snap': {'credits': [{'name': 'a', 'message': '연락 ' + PHONE}]}}
        real = mk.masked

        def boom(*a, **k):
            raise ValueError('x')
        mk.masked = boom
        try:
            got = mk.view('screen', v, {'mask': {}}, True)
        finally:
            mk.masked = real
        self.assertIsNotNone(got)
        self.assertEqual(got['snap']['credits'][0]['message'], '')
        self.assertEqual(got['title'], '오늘')
        self.assertNotIn('5678', json.dumps(got, ensure_ascii=False))


class Frontend(unittest.TestCase):
    FILES = ('v2/web/controller/js/mask.js', 'v2/web/controller/js/panels/ops/mask.js')

    def test_no_confirm_alert_or_sound(self):
        for f in self.FILES:
            with open(os.path.join(ROOT, f), encoding='utf-8') as fh:
                src = fh.read()
            code = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
            for bad in (r'(?<![.\w])confirm\(', r'\balert\(', r'\bAudio\b', r'\.play\(', r'vibrate', r'Notification'):
                self.assertIsNone(re.search(bad, code), (f, bad))

    def test_panel_registered(self):
        def read(p):
            with open(os.path.join(ROOT, p), encoding='utf-8') as fh:
                return fh.read()
        ops, menu = read('v2/web/controller/js/panels/tools_ops.js'), read('v2/web/controller/js/panels/settings_menu.js')
        html = read('v2/web/controller/index.html')
        self.assertIn("id: 'ops-mask'", ops)
        self.assertIn("'ops-mask'", menu)
        self.assertIn('./css/mask.css', html)


if __name__ == '__main__':
    unittest.main()
