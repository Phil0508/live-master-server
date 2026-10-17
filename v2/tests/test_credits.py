# -*- coding: utf-8 -*-
"""🎬 엔딩 크레딧(10-17 credits) — 명단 셈 · 빼는 규칙 · 얼리기 · 흐름 · 공개 조각에 비공개 값 없음 · 순서표 · 조종실 단추.

방송판 흐름(1080×1920 · 끝에서 멈춤)은 node 로 진짜 위젯 셈(widgets/credits/flow.js)을 부른다 — 베끼지 않는다.
"""
import json
import os
import shutil
import subprocess
import unittest

from v2.server.domain import credits as cr
from v2.tests.test_flow import Base, H

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(ROOT, 'v2', 'web')


def _read(*p):
    with open(os.path.join(WEB, *p), encoding='utf-8') as f:
        return f.read()


class Compute(unittest.TestCase):
    """순수 셈 — 장부 줄 · 점수 기록 줄을 손으로 만들어 넣는다."""

    def d(self, i, name, amount, at, source='toonation', status='assigned'):
        return {'id': 'don_%d' % i, 'at': at, 'name': name, 'amount': amount, 'source': source, 'status': status}

    def s(self, i, player, delta, lst='list', field='score'):
        return {'ref': 'don_%d' % i, 'player': player, 'field': field, 'list': lst, 'delta': delta}

    def test_member_groups_order_and_merge(self):
        dons = [self.d(1, '별빛', 30000, 1), self.d(2, '별빛님', 50000, 2), self.d(3, '달빛', 100000, 3),
                self.d(4, ' 별빛 ', 10000, 4), self.d(5, '구름', 20000, 5)]
        scs = [self.s(1, '서아', 3), self.s(2, '서아', 5), self.s(3, '하율', 10), self.s(4, '하율', 1), self.s(5, '서아', 2)]
        r = cr.compute(dons, scs, roster=['하율', '서아', '채원'])
        self.assertEqual([g['title'] for g in r['groups']], ['하율', '서아'])          # 멤버 순위 순서 · 받은 게 없는 채원은 없음
        seo = r['groups'][1]['names']
        self.assertEqual(seo, [{'name': '별빛', 'total': 80000}, {'name': '구름', 'total': 20000}])   # '님' · 띄어쓰기 한 줄로
        self.assertEqual([x['name'] for x in r['groups'][0]['names']], ['달빛', '별빛'])            # 큰 순
        self.assertEqual(r['count'], 3)

    def test_split_jar_all_and_etc(self):
        dons = [self.d(1, '나눔', 100000, 1), self.d(2, '모금', 30000, 2), self.d(3, '전원', 30000, 3),
                self.d(4, '대기', 20000, 4, status='pending'), self.d(5, '무시', 20000, 5, status='ignored'),
                self.d(6, '소액', 3000, 6, source='display', status='display'), self.d(7, '나눔', 5000, 7, status='pending')]
        scs = [self.s(1, '하율', 6), self.s(1, '서아', 4), self.s(2, '모금함', 30000, lst='jar'),
               self.s(3, '하율', 1), self.s(3, '서아', 1), self.s(3, '채원', 1)]
        r = cr.compute(dons, scs, roster=['하율', '서아', '채원'])
        by = {g['title']: g for g in r['groups']}
        self.assertEqual(by['하율']['names'], [{'name': '나눔', 'total': 60000}])        # 나눠 주기 — 준 점수 비율로
        self.assertEqual(by['서아']['names'], [{'name': '나눔', 'total': 40000}])
        self.assertEqual([x['name'] for x in by['모두에게']['names']], ['모금', '전원'])  # 모금함 · 전원에게 나눔
        etc = by[cr.TITLE_ETC]
        self.assertEqual([x['name'] for x in etc['names']], ['대기', '무시', '소액'])    # '나눔' 은 위에 있어 또 안 씀
        self.assertEqual([g['kind'] for g in r['groups']], ['member', 'member', 'all', 'etc'])

    def test_exclusions(self):
        dons = [self.d(1, '진짜', 10000, 1),
                self.d(2, '테스트', 50000, 2, source='toonation_test', status='pending'),
                self.d(3, '다시보기', 50000, 3, source='toonation_replay', status='display'),
                self.d(4, '대시보드', 50000, 4, source='toonation_dashtest', status='display'),
                self.d(5, '진짜', 50000, 5, source='replay', status='display'),
                self.d(6, '익명', 20000, 6, status='pending'), self.d(7, '', 20000, 7, status='pending'),
                self.d(8, '직원', 20000, 8, status='pending'), self.d(9, '공짜', 0, 9, status='pending')]
        r = cr.compute(dons, [self.s(1, '하율', 1)], roster=['하율'], excluded=['직원'])
        names = [x['name'] for g in r['groups'] for x in g['names']]
        self.assertEqual(names, ['진짜'])
        self.assertEqual(r['groups'][0]['names'][0]['total'], 10000)                   # 다시 송출 줄은 금액에도 안 낀다
        self.assertEqual(r['anon'], 2)
        self.assertEqual(r['skipped'], {'anon': 2, 'excluded': 1, 'test': 1, 'replay': 3})

    def test_removed_member_and_extra(self):
        dons = [self.d(1, 'A', 10000, 1), self.d(2, 'B', 50000, 2), self.d(3, 'C', 20000, 3)]
        scs = [self.s(1, '하율', 1), self.s(2, '떠난이', 5), self.s(3, '번외', 2, lst='extra')]
        r = cr.compute(dons, scs, roster=['하율'], extra=['번외'])
        self.assertEqual([g['title'] for g in r['groups']], ['하율', '번외', '떠난이'])

    def test_contribution_only_card_and_negative_ignored(self):
        dons = [self.d(1, 'A', 10000, 1)]
        scs = [self.s(1, '하율', 3, field='contribution'), self.s(1, '서아', -1)]
        r = cr.compute(dons, scs, roster=['하율', '서아'])
        self.assertEqual([g['title'] for g in r['groups']], ['하율'])

    def test_public_groups_amount_switch(self):
        g = [{'kind': 'member', 'title': '하율', 'names': [{'name': 'A', 'total': 10000}]}]
        self.assertEqual(cr.public_groups(g, False)[0]['names'], [{'name': 'A'}])
        self.assertEqual(cr.public_groups(g, True)[0]['names'], [{'name': 'A', 'total': 10000}])

    def test_names_cap(self):
        dons = [self.d(i, 'n%d' % i, 1000 + i, i, status='pending') for i in range(cr.NAMES_MAX + 50)]
        r = cr.compute(dons, [], roster=['하율'])
        self.assertEqual(sum(len(g['names']) for g in r['groups']), cr.NAMES_MAX)
        self.assertEqual(r['groups'][0]['names'][0]['name'], 'n%d' % (cr.NAMES_MAX + 49))   # 큰 금액이 남는다


class Server(Base):
    def give(self, name, amount, tx, who):
        self.don(name, amount, tx, msg='비밀 메시지 %s' % tx)
        pid = next(p['id'] for p in self.st()['pending'] if p['name'] == name)
        if isinstance(who, list):
            return self.cmd('pending.assign', id=pid, names=who)
        return self.cmd('pending.assign', id=pid, name=who)

    def test_build_show_freeze_and_public_slice(self):
        self.give('별빛', 70000, 'toon_c1', '서아')
        self.give('달빛', 30000, 'toon_c2', '하율')
        self.give('별빛님', 20000, 'toon_c3', '하율')
        self.don('익명', 10000, 'toon_c4')
        self.don('테스트', 40000, 'toon_t2_c5')
        self.don('작은손', 3000, 'toon_c6', display_only=True)
        c, r = self.cmd('credits.show')
        self.assertEqual(c, 200, r)
        s = self.st()
        cp = s['credits']
        self.assertTrue(cp['on'])
        self.assertEqual([g['title'] for g in cp['groups']], ['서아', '하율', cr.TITLE_ETC])   # 서아 7점 > 하율 5점
        self.assertEqual([x['name'] for x in cp['groups'][1]['names']], ['달빛', '별빛'])
        self.assertEqual([x['name'] for x in cp['groups'][2]['names']], ['작은손'])
        self.assertEqual((cp['count'], cp['anon']), (3, 1))
        self.assertNotIn('total', cp['groups'][0]['names'][0])                    # 기본 — 이름만
        # 방송판(로그인 없이)이 받는 것: credits 는 있고 credits_ops 는 없다 · 메시지 · 장부 번호 · 금액 없음
        pub = self.st(auth=False)
        self.assertIn('credits', pub)
        self.assertNotIn('credits_ops', pub)
        blob = json.dumps(pub['credits'], ensure_ascii=False)
        for bad in ('비밀 메시지', 'toon_', 'don_', '70000', '30000', '"no"', '테스트'):
            self.assertNotIn(bad, blob, bad)
        # 얼림 — 띄운 뒤 들어온 후원은 명단에 안 들어가고, 조종실에 '바뀐 것 있음'
        self.give('새손님', 10000, 'toon_c7', '채원')
        s = self.st()
        self.assertNotIn('채원', [g['title'] for g in s['credits']['groups']])
        self.assertTrue(s['credits_ops']['stale'])
        self.cmd('credits.hide')
        self.cmd('credits.show')                                                   # 다시 띄워도 얼린 명단 그대로
        self.assertNotIn('채원', [g['title'] for g in self.st()['credits']['groups']])
        self.cmd('credits.build')
        s = self.st()
        self.assertIn('채원', [g['title'] for g in s['credits']['groups']])
        self.assertFalse(s['credits_ops']['stale'])

    def test_amount_switch_and_text(self):
        self.give('별빛', 50000, 'toon_d1', '서아')
        self.cmd('credits.build', title='  고마워요  여러분 ', outro='')
        s = self.st()['credits']
        self.assertEqual((s['title'], s['outro']), ('고마워요 여러분', cr.DEFAULT_OUTRO))
        self.cmd('credits.set', show_amount=True)
        self.assertEqual(self.st(auth=False)['credits']['groups'][0]['names'][0]['total'], 50000)
        self.cmd('credits.set', show_amount=False)
        self.assertNotIn('total', self.st(auth=False)['credits']['groups'][0]['names'][0])
        c, r = self.cmd('credits.set', speed='warp')
        self.assertEqual(c, 400, r)

    def test_flow_pause_speed_restart(self):
        self.give('별빛', 50000, 'toon_e1', '서아')
        c, r = self.cmd('credits.pause')
        self.assertEqual(c, 409, r)                                                # 안 떠 있으면 멈출 것도 없다
        self.cmd('credits.show')
        run0 = self.st()['credits']['run']
        self.cmd('credits.pause', paused=True)
        s = self.st()['credits']
        self.assertTrue(s['paused'])
        self.assertGreaterEqual(s['offset'], 0)
        self.cmd('credits.set', speed='fast')
        self.assertEqual(self.st()['credits']['speed'], 'fast')
        self.cmd('credits.pause')
        self.assertFalse(self.st()['credits']['paused'])
        self.cmd('credits.restart')
        s = self.st()['credits']
        self.assertEqual((s['offset'], s['paused'], s['run']), (0, False, run0 + 1))
        self.cmd('credits.hide')
        self.assertFalse(self.st()['credits']['on'])

    def test_pos_math(self):
        c = {'on': True, 'paused': False, 'speed': 'normal', 'at': 1000, 'offset': 100}
        self.assertEqual(cr._pos(c, 3000), 100 + 2 * cr.SPEEDS['normal'])
        c['paused'] = True
        self.assertEqual(cr._pos(c, 3000), 100)

    def test_after_end_same_session_and_new_session_clears(self):
        self.give('별빛', 50000, 'toon_f1', '서아')
        self.cmd('session.end')
        c, r = self.cmd('credits.show')                                            # 방송을 끝낸 뒤에도 그 회차 명단
        self.assertEqual(c, 200, r)
        self.assertEqual(self.st()['credits']['groups'][0]['title'], '서아')
        self.cmd('credits.set', show_amount=True, title='또 봐요')
        self.cmd('session.start', names=['가', '나'])
        s = self.st()
        self.assertFalse(s['credits']['on'])
        self.assertEqual(s['credits']['groups'], [])
        self.assertEqual((s['credits']['title'], s['credits']['show_amount']), ('또 봐요', True))   # 설정은 남는다
        self.assertFalse(s['credits_ops']['built'])

    def test_undo_moves_back_to_etc_after_rebuild(self):
        self.give('별빛', 50000, 'toon_g1', '서아')
        self.cmd('score.undo')
        self.cmd('credits.build')
        g = self.st()['credits']['groups']
        self.assertEqual([x['title'] for x in g], [cr.TITLE_ETC])                  # 되돌린 점수는 안 센다

    def test_excluded_name(self):
        self.give('직원', 50000, 'toon_h1', '서아')
        self.cmd('credits.build')
        self.assertFalse(self.st()['credits_ops']['stale'])
        self.cmd('donor.exclude', name='직원')
        self.assertTrue(self.st()['credits_ops']['stale'])                         # 만든 뒤 뺀 이름 → '다시 만들기' 안내
        self.cmd('credits.build')
        self.assertEqual(self.st()['credits']['groups'], [])
        self.assertEqual(self.st()['credits_ops']['skipped']['excluded'], 1)
        self.assertFalse(self.st()['credits_ops']['stale'])
        self.cmd('donor.include', name='직원')
        self.assertTrue(self.st()['credits_ops']['stale'])                         # 다시 넣어도 마찬가지

    def test_unauthed_cannot_run(self):
        r = self.c.post('/api/cmd', json={'type': 'credits.show', 'data': {}})
        self.assertEqual(r.status_code, 401)

    def test_cue_step(self):
        self.give('별빛', 50000, 'toon_i1', '서아')
        self.cmd('preset.save', name='평소')
        self.cmd('credits.show')
        self.cmd('preset.save', name='크레딧')
        ps = self.st()['presets']['list']
        self.assertEqual([p.get('credits') for p in ps], [False, True])
        self.cmd('credits.hide')
        self.cmd('show.cue', dir='next')                                           # 1단계(평소) — 크레딧 없음
        self.assertFalse(self.st()['credits']['on'])
        self.cmd('show.cue', dir='next')                                           # 2단계 — 크레딧 띄움
        self.assertTrue(self.st()['credits']['on'])
        self.cmd('show.cue', dir='prev')
        self.assertFalse(self.st()['credits']['on'])
        # 이 기능 전에 저장한 단계(credits 칸 없음)는 크레딧을 안 건드린다
        from v2.server.domain import settings2
        self.assertIn(cr._snap, settings2.SNAP_EXTRA)
        self.assertIn(cr._apply, settings2.APPLY_EXTRA)

        class NoTouch:                                                             # 조각을 읽거나 고치면 바로 넘어진다
            def __getattr__(self, k):
                raise AssertionError('옛 단계인데 크레딧을 건드렸다: ' + k)
        cr._apply(NoTouch(), {'name': '옛 단계', 'stage': None})


class Web(unittest.TestCase):
    """방송판 · 조종실 파일 — 층 · 단추 · 금지 사항."""

    def test_overlay_layer_and_css(self):
        grp = _read('overlay', 'groups', 'credits.js')
        self.assertIn("widget: 'credits/credits'", grp)
        self.assertIn('CREDITS', _read('overlay', 'layers.js'))
        self.assertIn('/overlay/css/credits.css', _read('overlay', 'index.html'))

    def test_controller_buttons(self):
        src = _read('controller', 'js', 'panels', 'ops', 'credits.js')
        for t in ("'credits.show'", "'credits.pause'", "'credits.restart'", "'credits.hide'", "'credits.build'", "'credits.set'"):
            self.assertIn(t, src)
        for bid in ('cr-show', 'cr-pause', 'cr-restart', 'cr-hide'):
            self.assertIn(bid, src)
        self.assertIn('mountCredits', _read('controller', 'js', 'panels', 'ops', 'screen.js'))
        for p in (('controller', 'js', 'panels', 'ops', 'credits.js'), ('overlay', 'widgets', 'credits', 'credits.js'),
                  ('overlay', 'widgets', 'credits', 'flow.js')):
            s = _read(*p)
            for bad in ('confirm(', 'alert(', 'new Audio', 'AudioContext', 'vibrate', 'Notification'):
                self.assertNotIn(bad, s, '%s 에 %s' % ('/'.join(p), bad))

    def test_flow_js_matches_server_speeds(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node 없음')
        prog = r"""
import { pathToFileURL } from 'node:url';
const m = await import(pathToFileURL(process.argv[1]).href);
const out = { speeds: m.SPEEDS };
// 1080×1920 — 내용 4000px · 마무리 글 가운데 3900 → 멈추는 자리
const stop = m.stopAt(4000, 3900);
out.stop = stop;
out.p0 = m.posAt({ on: true, paused: false, speed: 'normal', at: 0, offset: 0 }, 0, stop);
out.p10 = m.posAt({ on: true, paused: false, speed: 'normal', at: 0, offset: 0 }, 10000, stop);
out.pEnd = m.posAt({ on: true, paused: false, speed: 'fast', at: 0, offset: 0 }, 10000000, stop);
out.pPause = m.posAt({ on: true, paused: true, speed: 'fast', at: 0, offset: 300 }, 10000000, stop);
out.y0 = m.shiftY(0); out.yEnd = m.shiftY(stop);
out.atEnd = m.posAt({ on: true, paused: false, speed: 'fast', at: 0, offset: 0 }, 10000000, stop) >= stop;
console.log(JSON.stringify(out));
"""
        r = subprocess.run([node, '--input-type=module', '-e', prog, os.path.join(WEB, 'overlay', 'widgets', 'credits', 'flow.js')],
                           capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(o['speeds'], cr.SPEEDS)                                  # 서버 셈과 같은 속도
        self.assertEqual(o['p0'], 0)
        self.assertEqual(o['p10'], 10 * cr.SPEEDS['normal'])
        self.assertEqual(o['pEnd'], o['stop'])                                     # 끝까지 가면 멈춘다
        self.assertEqual(o['pPause'], 300)
        self.assertEqual(o['y0'], 1920)                                            # 처음엔 화면 아래에서
        # 멈춘 자리: 마무리 글 가운데(3900)가 안전지대 가운데(115~954 → 534.5)에 온다
        self.assertAlmostEqual(o['yEnd'] + 3900, (115 + 954) / 2, delta=1)


if __name__ == '__main__':
    unittest.main()
