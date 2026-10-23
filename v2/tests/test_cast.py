# -*- coding: utf-8 -*-
"""💬 조종 연출(cast.py) — 화면에 한마디 · UP 자막 · 👑 조종실 후원 연출(이펙트 탭) · 🎲 주사위 시그 칸 글씨.

옛 것: features/say.py /api/say · gd.up_trigger · features/effects.py /api/effect/fire · /api/effect/clear · overlay.html opFxFire.
방송판 쪽 글자 셈(opfx.texts · say 글자 크기 · 새로 쏜 것만 그리기)은 node 로 진짜 파일을 돌려 맞대 본다.
"""
import json
import os
import shutil
import subprocess
import unittest

from v2.tests.test_flow import Base, H

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAST = os.path.join(ROOT, 'v2', 'web', 'overlay', 'widgets', 'cast')


def _node(js):
    node = shutil.which('node')
    if not node:
        raise unittest.SkipTest('node 없음')
    out = subprocess.run([node, '--input-type=module', '-e', js], capture_output=True, text=True, encoding='utf-8', timeout=60)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout.strip().splitlines()[-1])


def _url(*parts):
    return json.dumps('file:///' + os.path.join(*parts).replace('\\', '/'))


class Commands(Base):
    def test_say(self):
        c, r = self.cmd('cast.say', text='  안녕\n\n  하세요   여러분 ')
        self.assertEqual(c, 200, r)
        s = self.st(auth=False)['cast']                                            # 방송판(로그인 없음)이 받는다
        self.assertEqual(s['say']['text'], '안녕 하세요 여러분')                   # 줄바꿈 · 겹친 띄어쓰기는 한 칸(옛 것 그대로)
        self.assertEqual(r['say']['id'], s['say']['id'])
        self.assertEqual(self.cmd('cast.say', text='가' * 80)[1]['say']['text'], '가' * 60)    # 60자까지
        self.assertEqual(self.cmd('cast.say', text='   ')[0], 400)
        r = self.c.post('/api/cmd', json={'type': 'cast.say', 'data': {'text': 'x'}})
        self.assertEqual(r.status_code, 401)                                       # 주소만 아는 사람은 못 띄운다

    def test_up(self):
        c, r = self.cmd('cast.up', text='하율 UP!')
        self.assertEqual((c, r['up']['text']), (200, '하율 UP!'))
        self.assertEqual(self.cmd('cast.up', text='')[0], 400)

    def test_ids_rise_per_shot(self):
        """쏠 때마다 id 가 오른다 — 같은 글을 두 번 쏴도 방송판이 두 번 그린다. 다른 칸은 그대로."""
        a = self.cmd('cast.say', text='하나')[1]['say']['id']
        b = self.cmd('cast.say', text='하나')[1]['say']['id']
        u = self.cmd('cast.up', text='UP')[1]['up']['id']
        self.assertTrue(a < b < u)
        s = self.st()['cast']
        self.assertEqual((s['say']['id'], s['up']['id'], s['fx']), (b, u, None))

    def test_fx(self):
        c, r = self.cmd('cast.fx', kinds=['warn', 'banner', 'nope', 'banner'], name=' 홍길동 ', amount='30000', message='감사해요')
        self.assertEqual(c, 200, r)
        fx = self.st(auth=False)['cast']['fx']
        self.assertEqual((fx['kinds'], fx['name'], fx['amount'], fx['message']), (['banner', 'warn'], '홍길동', 30000, '감사해요'))
        self.assertEqual(self.cmd('cast.fx', kinds=['nope'])[0], 400)              # 그릴 줄 아는 것만 — 없으면 거절
        self.assertEqual(self.cmd('cast.fx', kinds=[])[0], 400)
        self.assertEqual(self.cmd('cast.fx', kinds='card', amount='abc')[1]['fx']['amount'], 0)   # 이상한 금액은 0(옛 것과 같다)
        self.assertEqual(self.cmd('cast.fx', kinds=['card'], amount=-5)[1]['fx']['amount'], 0)
        c, r = self.cmd('cast.fx_clear')
        self.assertEqual(c, 200)
        s = self.st()['cast']
        self.assertGreater(s['fx_clear']['id'], s['fx']['id'])
        self.assertEqual(self.st()['players']['list'][0]['score'], 0)              # 점수 · 장부는 안 바뀐다

    def test_video(self):
        """🐉 대형 연출 영상(10-23) — 아는 이름만 틀고, 멈추기는 stop 으로 같은 칸을 덮는다. 파일도 있어야 한다."""
        c, r = self.cmd('cast.video', name='dragon')
        self.assertEqual(c, 200, r)
        v = self.st(auth=False)['cast']['video']                                   # 방송판(로그인 없음)이 받는다
        self.assertEqual((v['name'], v.get('stop')), ('dragon', None))
        self.assertEqual(self.cmd('cast.video', name='nope')[0], 400)
        self.assertEqual(self.cmd('cast.video')[0], 400)
        r = self.c.post('/api/cmd', json={'type': 'cast.video', 'data': {'name': 'dragon'}})
        self.assertEqual(r.status_code, 401)                                       # 주소만 아는 사람은 못 튼다
        c, r = self.cmd('cast.video_stop')
        self.assertEqual(c, 200)
        v2 = self.st()['cast']['video']
        self.assertTrue(v2['stop'])
        self.assertGreater(v2['id'], v['id'])
        from v2.server.domain import cast
        for name in cast.VIDEO_FX:
            self.assertTrue(os.path.exists(os.path.join(ROOT, 'v2', 'web', 'overlay', 'fxvideos', name + '.webm')), name)


class BankFx(Base):
    """🏦🐉 계좌 입금 대형 연출(10-24 대표님) — 후원 콘솔이 계좌 카드를 보낼 때만, 첫 건의 합계(bank_total)로 고른다.
       50만 원↑ 용(+ 시그니처 동안 테두리) · 100만 원↑ 엔젤 방패. 투네이션 · 손 송출 · 기준 미만은 안 붙는다."""

    def last(self):
        return self.st()['queue']['items'][-1]

    def test_tiers(self):
        from v2.server.domain import cast
        self.assertEqual(cast.bank_fx(499999), {})
        self.assertEqual(cast.bank_fx(500000), {'fx_video': 'dragon', 'fx_frame': True})
        self.assertEqual(cast.bank_fx(999999)['fx_video'], 'dragon')
        self.assertEqual(cast.bank_fx(1000000), {'fx_video': 'emblem', 'fx_frame': False})
        self.assertEqual((cast.bank_fx(None), cast.bank_fx('abc')), ({}, {}))
        for _, name, _ in cast.BANK_FX:
            self.assertIn(name, cast.VIDEO_FX)

    def test_bank_send_gets_effect(self):
        c, r = self.don('입금자', 500000, 'manual_bank_b1', bank_total=500000)
        self.assertEqual(c, 200, r)
        it = self.last()
        self.assertEqual((it.get('fx_video'), it.get('fx_frame')), ('dragon', True))
        self.don('큰손', 1000000, 'manual_bank_b2', bank_total=1000000)
        it = self.last()
        self.assertEqual((it.get('fx_video'), it.get('fx_frame')), ('emblem', False))
        self.assertIn('fx_video', self.st(auth=False)['queue']['items'][-1])          # 방송판(로그인 없음)이 받는다

    def test_no_effect(self):
        self.don('작은손', 300000, 'manual_bank_b3', bank_total=300000)                 # 기준 미만
        self.assertNotIn('fx_video', self.last())
        self.don('투네', 500000, 'toon_x1', bank_total=500000)                          # 투네이션은 안 붙는다
        self.assertNotIn('fx_video', self.last())
        self.don('손', 500000, 'manual_123')                                           # 손 송출(계좌 카드 아님)
        self.assertNotIn('fx_video', self.last())
        r = self.c.post('/api/donation', json={'name': '남', 'amount': 500000, 'tx_id': 'manual_bank_b9', 'bank_total': 500000})
        if r.status_code == 200:                                                       # 로그인 없이 들어온 길이면 연출은 안 붙는다
            self.assertNotIn('fx_video', self.last())

    def test_split_send_counts_total(self):
        """10만 원 × 5건으로 보낸 50만 원 입금 — 첫 건의 합계로 용, 나머지 건은 같은 줄 ×N 으로 묶인다."""
        self.don('나눠', 100000, 'manual_bank_b4_1', bank_total=500000)
        for i in range(2, 6):
            self.don('나눠', 100000, 'manual_bank_b4_%d' % i)
        items = self.st()['queue']['items']
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]['fx_video'], items[0]['count']), ('dragon', 5))

    def test_effect_line_not_merged_into_earlier(self):
        self.don('같은분', 500000, 'toon_y1')
        self.don('같은분', 500000, 'manual_bank_b5', bank_total=500000)
        items = self.st()['queue']['items']
        self.assertEqual(len(items), 2)                                                # 앞줄에 묶이면 연출이 사라진다
        self.assertNotIn('fx_video', items[0])
        self.assertEqual(items[1]['fx_video'], 'dragon')

    def test_signature_only_path(self):
        r = self.c.post('/api/signature/play', json={'amount': 500000, 'name': '시그만', 'count': 2, 'bank': 1, 'bank_total': 1000000}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        it = self.last()
        self.assertEqual((it.get('fx_video'), it.get('count')), ('emblem', 2))
        self.c.post('/api/signature/play', json={'amount': 500000, 'name': '그냥', 'bank_total': 1000000}, headers=H)
        self.assertNotIn('fx_video', self.last())                                     # 계좌 카드에서 보낸 게 아니면(bank 없음) 안 붙는다


class OverlayJs(unittest.TestCase):
    def test_opfx_texts(self):
        """옛 opFxFire 의 글자 셈 그대로(배너 아랫줄 · 카드 · 글리치 · 경보 · 전광판)."""
        cases = [{'name': '홍길동', 'amount': 30000, 'message': '감사해요'}, {'name': '', 'amount': 0, 'message': ''},
                 {'name': '하율', 'amount': 0, 'message': ''}, {'name': '', 'amount': 1234567, 'message': '대박'}]
        got = _node("import(%s).then(m => console.log(JSON.stringify(%s.map(d => m.texts(d)))))" % (_url(CAST, 'opfx.js'), json.dumps(cases)))
        self.assertEqual(got[0], {'bannerName': '홍길동', 'bannerSub': '30,000원  ·  감사해요', 'cardName': '홍길동', 'cardAmount': '30,000원',
                                  'cardMsg': '감사해요', 'glitch': '홍길동', 'warnSub': '감사해요', 'ticker': '감사해요'})
        self.assertEqual(got[1], {'bannerName': '감사합니다', 'bannerSub': '', 'cardName': '감사합니다', 'cardAmount': '', 'cardMsg': '',
                                  'glitch': 'DONATION', 'warnSub': '고액 후원 감지', 'ticker': '후원 감사합니다!'})
        self.assertEqual((got[2]['warnSub'], got[2]['ticker']), ('하율', '하율님 후원 감사합니다!'))
        self.assertEqual((got[3]['bannerSub'], got[3]['glitch'], got[3]['warnSub']), ('1,234,567원  ·  대박', '대박', '대박'))

    def test_say_font_and_fresh(self):
        """한마디 글자 크기(10 · 18 · 30자) · 새로 쏜 것만 그리기(다른 칸 · 같은 id · 다시 붙은 통째의 지난 것은 안 그림)."""
        js = """
const say = await import(%s), fr = await import(%s);
const sizes = ['가'.repeat(10), '가'.repeat(11), '가'.repeat(18), '가'.repeat(19), '가'.repeat(30), '가'.repeat(31)].map(say.sayFontPx);
let fn = null, now = 100000, streaming = false; const shot = [];
const lm = { on: (k, f) => { fn = f; }, serverNow: () => now };
const opts = { isFresh: at => streaming || (Date.now() - at < 30000) };
fr.watchCast(lm, opts, 'say', row => shot.push(row.text));
fn({ say: { id: 3, text: '옛 것', at: now - 10000 } });          // 다시 붙은 통째 — 10초 전 것은 안 그린다
streaming = true;
fn({ say: { id: 3, text: '옛 것', at: now - 10000 }, up: { id: 4 } });   // 다른 칸만 바뀜 — 안 그린다
fn({ say: { id: 5, text: '새 것', at: now } });                 // 새로 쏨
fn({ say: { id: 5, text: '새 것', at: now } });                 // 같은 id — 한 번만
now += 500; fn({ say: { id: 6, text: '또', at: now } });
console.log(JSON.stringify({ sizes, shot }));
""" % (_url(CAST, 'say.js'), _url(CAST, 'fresh.js'))
        got = _node(js)
        self.assertEqual(got['sizes'], [120, 100, 100, 80, 80, 62])
        self.assertEqual(got['shot'], ['새 것', '또'])


class Wiring(unittest.TestCase):
    """층 표 · 조종실 · 주사위 글씨 — 파일이 서로 이어져 있는가."""

    def _src(self, *p):
        with open(os.path.join(ROOT, *p), encoding='utf-8') as f:
            return f.read()

    def test_layers_and_pages(self):
        lay = self._src('v2', 'web', 'overlay', 'layers.js')
        self.assertIn("from './groups/cast.js'", lay)
        self.assertIn('...CAST', lay)
        grp = self._src('v2', 'web', 'overlay', 'groups', 'cast.js')
        for wid in ('cast/up', 'cast/say', 'cast/opfx', 'cast/video'):
            self.assertIn("'%s'" % wid, grp)
            self.assertTrue(os.path.exists(os.path.join(ROOT, 'v2', 'web', 'overlay', 'widgets', wid + '.js')), wid)
        self.assertIn('/overlay/css/cast.css', self._src('v2', 'web', 'overlay', 'index.html'))
        self.assertIn('./css/tools_cast.css', self._src('v2', 'web', 'controller', 'index.html'))
        self.assertIn('mountCastBox', self._src('v2', 'web', 'controller', 'js', 'main.js'))
        self.assertIn("mountOpFx", self._src('v2', 'web', 'controller', 'js', 'panels', 'tools_ops.js'))

    def test_dice_banner_text(self):
        """🎲 주사위가 시그 칸에 닿으면 가운데 큰 글씨가 '밍밍 · 시그 칸 도착'(서버가 banner 에 싣는다) — 시그니처 이름이 아니다."""
        # 합친 뒤(10-17) 배너 글은 sigfx 의 rules.bannerText 한 곳에서 만든다 — signature.js 는 그걸 부른다
        sig = self._src('v2', 'web', 'overlay', 'widgets', 'signature.js')
        self.assertIn('bannerText(it,', sig)
        rules = self._src('v2', 'web', 'overlay', 'widgets', 'sigfx', 'rules.js')
        self.assertIn("item.source === 'dice'", rules)
        self.assertIn("String(item.banner || ((item.donator || '') + ' · 시그 칸 도착')).trim()", rules)


if __name__ == '__main__':
    unittest.main()
