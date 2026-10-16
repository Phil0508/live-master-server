# -*- coding: utf-8 -*-
"""📐 옛 위젯 자리 → v2 자리(oldlayout.py) · 🏺 모금함 깃발 왼쪽/오른쪽(fundjar.side).

바꾸는 식: 옛 칸은 전부 왼쪽 위 기준(left = x_px · top = y_px · 배율은 왼쪽 위를 붙박고). v2 는 칸마다 기준점(layers.js anchor).
  tl: x = 옛 x · tr: x = 옛 x + 폭 × 배율 · tc: x = 옛 x + 폭 × 배율 ÷ 2 · y 는 그대로 — v2 칸의 왼쪽 위 모서리가 옛 자리와 같아진다.
"""
import json
import os
import re
import shutil
import subprocess
import unittest

from v2.server.domain import oldlayout as ol
from v2.tests.test_flow import Base

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OVERLAY = os.path.join(ROOT, 'v2', 'web', 'overlay')


def _layers():
    """방송판 층 표(layers.js · groups/*.js)의 칸 {id: {x, y, anchor, scale}} — 서버 표(ANCHOR)와 맞대 보려고 읽는다."""
    out = {}
    files = [os.path.join(OVERLAY, 'layers.js')] + [os.path.join(OVERLAY, 'groups', f) for f in sorted(os.listdir(os.path.join(OVERLAY, 'groups')))]
    for p in files:
        with open(p, encoding='utf-8') as f:
            src = f.read()
        for m in re.finditer(r"\{\s*id:\s*'(\w+)'([^}]*)\}", src):
            body = m.group(2)
            row = {'anchor': 'tl', 'scale': 1.0}
            for k in ('x', 'y', 'scale'):
                mm = re.search(r'\b%s:\s*(-?[\d.]+)' % k, body)
                if mm:
                    row[k] = float(mm.group(1))
            mm = re.search(r"anchor:\s*'(\w+)'", body)
            if mm:
                row['anchor'] = mm.group(1)
            out[m.group(1)] = row
    return out


class Formula(unittest.TestCase):
    def test_production_ranking(self):
        """운영 배치 점수판 왼쪽 10 · 위 263 · 0.88배 → v2 점수판(오른쪽 위 기준) 10 + 878 × 0.88 = 782.64."""
        w, info = ol.convert({'__v': 2, '__free': True, 'ranking': {'x_px': 10, 'y_px': 263, 'scale': 0.88}})
        self.assertEqual(w, {'ranking': {'x': 782.64, 'y': 263.0, 'scale': 0.88}})
        self.assertEqual(w['ranking']['x'] - 878 * 0.88, 10.0)        # 왼쪽 끝이 옛 자리 그대로
        self.assertEqual(info, {'skipped': [], 'approx': []})

    def test_each_anchor(self):
        old = {'__v': 2, '__free': True,
               'gauge': {'x_px': 1000, 'y_px': 200, 'scale': 1.2},          # tl — 그대로
               'popup': {'x_px': 300, 'y_px': 500, 'scale': 1.5},           # tc — 폭 396
               'takeover': {'x_px': 100, 'y_px': 600, 'scale': 1},          # tc — 폭 424
               'home-race': {'x_px': 50, 'y_px': 170, 'scale': 0.9},        # tr — 퇴근빵 946 · 지옥탈출 950
               'account': {'x_px': 20, 'y_px': 430, 'scale': 1.1},          # tr(판 아래) + tl(머리 줄) 둘 다 같은 자리
               'roulette': {'x_px': 234, 'y_px': 311, 'scale': 1.123}}      # 배율은 옛 것도 안 읽었다(0.87 고정)
        w, info = ol.convert(old)
        self.assertEqual(w['gauge'], {'x': 1000.0, 'y': 200.0, 'scale': 1.2})
        self.assertEqual(w['scorePopup'], {'x': 300 + 396 * 1.5 / 2, 'y': 500.0, 'scale': 1.5})
        self.assertEqual(w['takeover'], {'x': 312.0, 'y': 600.0, 'scale': 1.0})
        self.assertEqual(w['homeRace'], {'x': round(50 + 946 * 0.9, 2), 'y': 170.0, 'scale': 0.9})
        self.assertEqual(w['hell'], {'x': round(50 + 950 * 0.9, 2), 'y': 170.0, 'scale': 0.9})
        self.assertEqual(w['account'], {'x': round(20 + 636 * 1.1, 2), 'y': 430.0, 'scale': 1.1})
        self.assertEqual(w['accountHead'], {'x': 20.0, 'y': 430.0, 'scale': 1.1})
        self.assertEqual(w['roulette'], {'x': 234.0, 'y': 311.0})
        self.assertEqual(sorted(info['approx']), ['account', 'hell', 'homeRace'])       # 글자 · 내용으로 폭이 바뀌는 칸

    def test_measured_width(self):
        """편집기가 잰 폭이 오면(계좌 글자 길이) 그걸 쓴다 — 점수판 · 팝업처럼 믿지 않는 칸은 무시."""
        old = {'__v': 2, '__free': True, 'account': {'x_px': 20, 'y_px': 430, 'scale': 1},
               'ranking': {'x_px': 10, 'y_px': 263, 'scale': 1}}
        w, info = ol.convert(old, sizes={'account': {'w': 512}, 'ranking': {'w': 5}})
        self.assertEqual(w['account']['x'], 532.0)
        self.assertEqual(w['ranking']['x'], 888.0)
        self.assertEqual(info['approx'], [])

    def test_dice_width(self):
        """주사위판 폭 = v2 dice.js build 와 같은 식 — 10-17 헤드리스 크롬으로 잰 값과 맞댄다."""
        for (c, r), want in {(7, 5): 1029, (8, 5): 1030, (6, 4): 1010, (10, 8): 924, (4, 3): 678}.items():
            self.assertEqual(ol.dice_width(c, r), want, (c, r))
        w, _ = ol.convert({'__v': 2, '__free': True, 'dicegame': {'x_px': 6, 'y_px': 307, 'scale': 1}}, dice=(8, 5))
        self.assertEqual(w['dicegame'], {'x': 521.0, 'y': 307.0, 'scale': 1.0})          # 6 + 1030 / 2

    def test_old_fit_clamp(self):
        """__free 가 아니면 옛 방송판처럼 붙잡은 뒤 바꾼다(가로 0~1080 · 위아래 115~954)."""
        old = {'__v': 2, 'gauge': {'x_px': -40, 'y_px': 1598, 'scale': 1}, 'best': {'x_px': 2000, 'y_px': 20, 'scale': 1}}
        w, _ = ol.convert(old)
        self.assertEqual((w['gauge']['x'], w['gauge']['y']), (0.0, 954.0))
        self.assertEqual((w['best']['x'], w['best']['y']), (1080.0, 115.0))
        w, _ = ol.convert(dict(old, __free=True))
        self.assertEqual((w['gauge']['x'], w['gauge']['y']), (-40.0, 1598.0))

    def test_old_rules(self):
        with self.assertRaises(ValueError):
            ol.convert({'ranking': {'x_px': 1, 'y_px': 2, 'scale': 1}})                      # __v 없음 — 옛 방송판도 무시
        with self.assertRaises(ValueError):
            ol.convert({'__v': 2})                                                           # 자리가 하나도 없다
        with self.assertRaises(ValueError):
            ol.convert([1, 2])
        w, info = ol.convert({'__v': 2, '__free': True, 'notice': {'x_px': 6, 'y_px': 115, 'scale': 2.78},
                              'ticker_top': {'x_px': 0, 'y_px': 93, 'scale': 1},
                              'dgscore': {'x_px': 6, 'y_px': 191, 'scale': 1},
                              'slot': {'x_px': 'abc', 'y_px': None, 'scale': -3}})
        self.assertEqual(w, {'slot': {'x': 0.0, 'y': 0.0, 'scale': 1.0}})                  # 이상한 값은 0 · 배율 1
        self.assertEqual([t[0] for t in info['skipped']], ['dgscore', 'notice', 'ticker_top'])
        # 배율이 터무니없으면 layout.set 과 같은 울타리
        w, _ = ol.convert({'__v': 2, '__free': True, 'best': {'x_px': 5000, 'y_px': -5000, 'scale': 9}})
        self.assertEqual(w['best'], {'x': 1620, 'y': -960, 'scale': 4.0})

    def test_anchor_table_matches_overlay(self):
        """서버의 기준점 표가 방송판 층 표와 같다 — 누가 layers.js 의 anchor 를 바꾸면 여기서 걸린다."""
        L = _layers()
        for vid in ol.V2_IDS:
            self.assertIn(vid, L, vid)
            self.assertEqual(ol.ANCHOR.get(vid, 'tl'), L[vid]['anchor'], vid)
        self.assertEqual((L['ranking']['x'], L['ranking']['y']), ol.RANK_DEFAULT[:2])

    def test_old_defaults_land_on_v2_defaults(self):
        """옛 기본 자리(overlay.html 컨테이너 style)를 옮기면 v2 기본 자리(층 표)에 그대로 선다."""
        L = _layers()
        old_default = {'ranking': (1080 - 42 - 878, 167), 'gauge': (1046, 115), 'popup': (342, 536), 'takeover': (328, 639),
                       'fundjar': (40, 167), 'pinball': (50, 300), 'slot': (191, 452), 'roulette': (234, 311), 'match': (288, 795),
                       'siggame': (171, 340), 'donor-rank': (658, 387), 'sig-tally': (800, 315), 'best': (40, 400),
                       'karaoke': (40, 560), 'home-race': (1080 - 42 - 946, 167)}
        old = {'__v': 2, '__free': True}
        old.update({k: {'x_px': x, 'y_px': y, 'scale': 1} for k, (x, y) in old_default.items()})
        w, _ = ol.convert(old)
        for vid in ('ranking', 'gauge', 'scorePopup', 'takeover', 'fundjar', 'pinball', 'slot', 'roulette', 'match', 'siggame',
                    'donorRank', 'sigTally', 'best', 'karaoke', 'homeRace'):
            self.assertEqual((w[vid]['x'], w[vid]['y']), (L[vid]['x'], L[vid]['y']), vid)


class Command(Base):
    def test_import_old_layout(self):
        self.cmd('layout.set', id='quiz', x=5, y=800)               # v2 에만 있는 칸 — 안 건드린다
        self.cmd('layout.set', id='best', x=99, y=99)               # 옛 파일에 없는 옛 칸 — 기본 자리로
        old = {'__v': 2, '__free': True, 'ranking': {'x_px': 10, 'y_px': 263, 'scale': 0.88},
               'fundjar': {'x_px': 820, 'y_px': 1532, 'scale': 0.687}, 'notice': {'x_px': 1, 'y_px': 1, 'scale': 2}}
        c, r = self.cmd('layout.import_old', layout=old, sizes={'account': {'w': 600}})
        self.assertEqual(c, 200, r)
        self.assertEqual(r['moved'], ['fundjar', 'ranking'])
        self.assertTrue(any(x.startswith('notice') for x in r['skipped']))
        w = self.st()['layout']['widgets']
        self.assertEqual(w, {'quiz': {'x': 5.0, 'y': 800.0}, 'ranking': {'x': 782.64, 'y': 263.0, 'scale': 0.88},
                             'fundjar': {'x': 820.0, 'y': 1532.0, 'scale': 0.687}})
        self.assertIn('layout', self.st(auth=False))                # 방송판(로그인 없음)도 받는다

    def test_import_rejects(self):
        c, r = self.cmd('layout.import_old', layout={'ranking': {'x_px': 1, 'y_px': 1}})
        self.assertEqual(c, 400)
        self.assertIn('__v', r['error'])
        c, r = self.cmd('layout.import_old', layout='x')
        self.assertEqual(c, 400)
        c, r = self.cmd('layout.import_old', layout={'__v': 2, 'notice': {'x_px': 1, 'y_px': 1}})
        self.assertEqual(c, 400)                                    # 옮길 칸이 없다
        self.assertEqual(self.st()['layout']['widgets'], {})

    def test_backup_with_layout(self):
        """옛 [💾 백업] 상태에 layout 이 담겨 있으면 admin.import_old 가 같이 옮긴다 — 주사위판 폭은 옮겨 온 판 크기로."""
        old = {'target_goal': 300, 'dicegame': {'cols': 8, 'rows': 5},
               'layout': {'__v': 2, '__free': True, 'dicegame': {'x_px': 6, 'y_px': 307, 'scale': 1}}}
        c, r = self.cmd('admin.import_old', state=old)
        self.assertEqual(c, 200, r)
        self.assertIn('위젯 자리 1칸', r['imported'])
        self.assertEqual(self.st()['layout']['widgets']['dicegame'], {'x': 521.0, 'y': 307.0, 'scale': 1.0})


class FundjarSide(Base):
    def test_production_round_trip(self):
        """운영 배치(점수판 10 · 263 · 0.88) — 오른쪽 = 깃발 792 · 왼쪽 = 깃발 10 / 점수판 114. 왕복해도 안 밀린다(옛 메모 그대로)."""
        self.cmd('layout.set', id='ranking', x=782.64, y=263, scale=0.88)
        self.cmd('layout.set', id='fundjar', x=820, y=1532, scale=0.687)
        self.assertEqual(ol.side_now(self.st()['layout']['widgets']), 'free')
        c, r = self.cmd('fundjar.side', side='right')
        self.assertEqual(c, 200, r)
        w = self.st()['layout']['widgets']
        self.assertEqual(w['fundjar'], {'x': 792.0, 'y': 263.0, 'scale': 0.88})
        self.assertAlmostEqual(w['ranking']['x'] - 878 * 0.88, 10, places=6)
        self.assertEqual(ol.side_now(w), 'right')
        self.cmd('fundjar.side', side='left')
        w = self.st()['layout']['widgets']
        self.assertEqual(w['fundjar'], {'x': 10.0, 'y': 263.0, 'scale': 0.88})
        self.assertAlmostEqual(w['ranking']['x'] - 878 * 0.88, 114, places=6)          # 점수판이 깃발 폭만큼 비켰다
        self.assertEqual(ol.side_now(w), 'left')
        for _ in range(3):
            self.cmd('fundjar.side', side='right')
            self.cmd('fundjar.side', side='left')
        w2 = self.st()['layout']['widgets']
        self.assertEqual((w2['fundjar'], w2['ranking']), (w['fundjar'], w['ranking']))
        self.cmd('fundjar.side', side='right')
        self.assertEqual(self.st()['layout']['widgets']['fundjar']['x'], 792.0)

    def test_default_layout_and_errors(self):
        """편집기에서 안 잡았으면 방송판 기본 자리(오른쪽 끝 1038 · 위 167) 기준 — 화면 밖으로 안 나가게 당긴다."""
        c, r = self.cmd('fundjar.side', side='right')
        self.assertEqual(c, 200, r)
        w = self.st()['layout']['widgets']
        self.assertEqual(w['ranking'], {'x': 78 + 878.0, 'y': 167.0, 'scale': 1.0})     # 왼쪽 끝 160 → 78(깃발 자리 만들기)
        self.assertEqual(w['fundjar'], {'x': 966.0, 'y': 167.0, 'scale': 1.0})
        self.assertEqual(self.cmd('fundjar.side', side='up')[0], 400)
        self.assertEqual(self.cmd('fundjar.side')[0], 400)

    def test_js_side_now_matches_server(self):
        """조종실 단추 불(fjside.js sideNow)이 서버 side_now 와 같은 셈인가 — node 로 진짜 파일을 돌린다."""
        node = shutil.which('node')
        if not node:
            self.skipTest('node 없음')
        cases = [{}, {'fundjar': {'x': 40, 'y': 167}},
                 {'ranking': {'x': 782.64, 'y': 263, 'scale': 0.88}, 'fundjar': {'x': 792, 'y': 263, 'scale': 0.88}},
                 {'ranking': {'x': 886.64, 'y': 263, 'scale': 0.88}, 'fundjar': {'x': 10, 'y': 263, 'scale': 0.88}},
                 {'ranking': {'x': 886.64, 'y': 263, 'scale': 0.88}, 'fundjar': {'x': 10, 'y': 400, 'scale': 0.88}},
                 {'fundjar': {'x': 966, 'y': 167}, 'ranking': {'x': 956, 'y': 167, 'scale': 1}},
                 {'fundjar': {'x': 52, 'y': 160}}, {'ranking': {'y': 200}, 'fundjar': {'x': 1100, 'y': 190}}]
        mod = 'file:///' + os.path.join(ROOT, 'v2', 'web', 'controller', 'js', 'panels', 'ops', 'fjside.js').replace('\\', '/')
        js = "import(%s).then(m => console.log(JSON.stringify(%s.map(c => m.sideNow(c)))))" % (json.dumps(mod), json.dumps(cases))
        out = subprocess.run([node, '--input-type=module', '-e', js], capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(got, [ol.side_now(c) for c in cases])
        self.assertEqual(got[2:4], ['right', 'left'])


if __name__ == '__main__':
    unittest.main()
