# -*- coding: utf-8 -*-
"""🗂️ 방송판 층 순서 검사 (sturdy 10-17) — 10-06 사고 재발 방지.

10-06: 옛 방송판의 닫는 </div> 하나가 판 6개를 후원 팝업 위로 올렸다. v2 는 층 순서를 layers.js 한 표에서만 정하지만,
누가 숫자를 잘못 고쳐도 잡아 줄 검사가 없었다. 여기서 **진짜 표**(layers.js 가 groups/*.js 를 이어 붙이고 같은 id 는
뒤엣것이 이기는 그 결과)를 node 로 불러 규칙을 본다 — 표를 베껴 읽지 않는다(검사 도구는 실물과 같아야 한다).

규칙(layers.js 머리말: 후원 알림 · 시그니처 > 점수 팝업 > 게이지 > 판)
  1. 시그니처는 맨 위(점검용 칸 빼고 아무것도 시그니처를 못 덮는다)
  2. 후원 카드 · 소액 띠 · 시그니처는 게임판(games_a · games_b 의 칸 전부)보다 위
  3. 후원 카드 위에 올라갈 수 있는 칸은 정해 둔 것뿐(소액 띠 · 시그니처 · 조명 연출) — 새 칸을 그 위에 두려면 여기 목록에 일부러 적는다
  4. 후원 카드 > 점수 팝업 · 1등 탈환 > 게이지 > 자리를 차지하는 판(solid) · 게임판
  5. z 는 양의 정수, id 는 하나씩
  6. 층 번호는 main.js 한 곳에서만 넣고(.layer 는 position:absolute → 칸마다 따로 쌓인다), CSS 의 z-index 는 칸 안의 작은 숫자만
  7. 위젯이 자기 칸을 벗어나 body 에 붙지 않는다(옛 방송판 폭죽만 예외 — 아래 ESCAPE_OK)
"""
import json
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OVERLAY = os.path.join(ROOT, 'v2', 'web', 'overlay')

# 후원 카드(40) 위에 있어도 되는 칸 — 이유와 함께. 여기에 없는 칸이 후원 카드 이상으로 올라가면 검사가 멈춘다.
ABOVE_DONATION_OK = {
    'smallDon': '소액 후원 띠 — 맨 위 한 줄(옛 #small-don 100006 > 후원 카드 100005)',
    'signature': '시그니처 카드 · OO업 배너 — 옛 순서 그대로 맨 위',
    'fxAudi': '💡 아우디 조명 — 방송 중 · 시그니처가 나올 때만 화면 테두리',
    'fxNeon': '💡 네온 조명 — 같은 곳',
    'fxBurst': '✨ 테마 폭죽 — 잠깐',
    'connection': '점검용(?debug=1 일 때만)',
}
# 자기 칸을 벗어나 화면 전체에 그리는 곳 — 옛 방송판과 같은 것만
ESCAPE_OK = {
    os.path.join('games', 'slot-roulette-kit.js'): '룰렛 · 슬롯 · 핀볼 우승 폭죽(canvas-confetti 전역, 옛 방송판과 같이 잠깐 모든 층 위)',
}

NODE_PROG = r"""
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const dir = process.argv[1];
const load = async f => (await import(pathToFileURL(path.join(dir, f)).href));
const all = (await load('layers.js')).LAYERS;
const grp = {};
for (const g of ['basics2', 'games_a', 'games_b', 'fx']) grp[g] = (await load(path.join('groups', g + '.js'))).LAYERS.map(L => L.id);
console.log(JSON.stringify({ layers: all, groups: grp }));
"""


def _node():
    return shutil.which('node')


def _read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


class Layers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node = _node()
        if not node:
            raise unittest.SkipTest('node 가 없어 방송판 층 표를 못 읽습니다(검사 PC 에는 node 를 깔아 둘 것)')
        r = subprocess.run([node, '--input-type=module', '-e', NODE_PROG, OVERLAY], capture_output=True,
                           text=True, encoding='utf-8', timeout=60)
        if r.returncode != 0:
            raise AssertionError('layers.js 를 못 불렀습니다 — 문법 오류?\n' + r.stderr[-2000:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        cls.layers = out['layers']
        cls.by = {L['id']: L for L in cls.layers}
        cls.groups = out['groups']
        cls.games = [cls.by[i] for g in ('games_a', 'games_b') for i in cls.groups[g] if i in cls.by]

    def z(self, lid):
        self.assertIn(lid, self.by, '층 표에 %s 칸이 없습니다' % lid)
        return self.by[lid]['z']

    def test_z_are_positive_ints_and_ids_unique(self):
        ids = [L['id'] for L in self.layers]
        self.assertEqual(len(ids), len(set(ids)))
        for L in self.layers:
            self.assertIsInstance(L['z'], int, '%s 의 z 가 정수가 아닙니다: %r' % (L['id'], L['z']))
            self.assertGreater(L['z'], 0, L['id'])
        for g, gids in self.groups.items():
            self.assertEqual(len(gids), len(set(gids)), '%s 안에 같은 id 가 두 번 있습니다' % g)

    def test_signature_on_top(self):
        sig = self.z('signature')
        over = [(L['id'], L['z']) for L in self.layers if L['id'] != 'signature' and not L.get('debugOnly') and L['z'] >= sig]
        self.assertEqual(over, [], '시그니처(%d)를 덮는 칸이 있습니다' % sig)

    def test_donation_and_signature_above_every_game_board(self):
        self.assertTrue(self.games, '게임판 칸을 하나도 못 찾았습니다(groups/games_*.js)')
        top = max(self.games, key=lambda L: L['z'])
        for lid in ('donation', 'smallDon', 'signature'):
            self.assertGreater(self.z(lid), top['z'], '%s(%d) 가 게임판 %s(%d) 보다 아래입니다 — 10-06 사고와 같은 모양'
                               % (lid, self.z(lid), top['id'], top['z']))

    def test_only_listed_layers_above_donation(self):
        don = self.z('donation')
        bad = [(L['id'], L['z']) for L in self.layers if L['id'] != 'donation' and L['z'] >= don and L['id'] not in ABOVE_DONATION_OK]
        self.assertEqual(bad, [], '후원 카드(%d) 위에 올라간 칸 — 일부러면 ABOVE_DONATION_OK 에 까닭과 함께 적을 것' % don)

    def test_alert_order(self):
        """후원 카드 > 점수 팝업 · 1등 탈환 > 게이지 > 판(solid) · 게임판"""
        gauge = self.z('gauge')
        for lid in ('scorePopup', 'takeover'):
            self.assertGreater(self.z('donation'), self.z(lid), lid)
            self.assertGreater(self.z(lid), gauge, lid)
        boards = [L for L in self.layers if L.get('solid')] + self.games
        hi = max(boards, key=lambda L: L['z'])
        self.assertGreater(gauge, hi['z'], '게이지(%d) 가 판 %s(%d) 보다 아래입니다' % (gauge, hi['id'], hi['z']))

    def test_z_only_from_table(self):
        main = _read(os.path.join(OVERLAY, 'main.js'))
        self.assertIn('el.style.zIndex = String(L.z)', main, 'main.js 가 층 표의 z 를 칸에 넣는 줄이 바뀌었습니다')
        css = _read(os.path.join(OVERLAY, 'overlay.css'))
        m = re.search(r'(^|\n)\.layer\s*\{([^}]*)\}', css)
        self.assertTrue(m and re.search(r'position\s*:\s*absolute', m.group(2)), '.layer 가 position:absolute 가 아니면 칸마다 따로 쌓이지 않습니다')
        # 칸 안의 z-index(카드 100 등)는 그 칸 안에서만 쌓인다 — 칸(.layer)이 z 를 가진 absolute 라서.
        # 그러니 CSS 가 칸 자체의 z 를 덮는 것만 막는다: !important z-index · .layer-<id> / [data-layer] 에 z-index
        files = [os.path.join(OVERLAY, 'overlay.css')] + [os.path.join(OVERLAY, 'css', f) for f in os.listdir(os.path.join(OVERLAY, 'css'))
                                                           if f.endswith('.css')]
        bad = []
        for p in files:
            src = _read(p)
            if re.search(r'z-index\s*:[^;}]*!important', src):
                bad.append((os.path.basename(p), '!important'))
            for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', src):
                if re.search(r'\.layer(-[\w-]+)?\b|\[data-layer', sel) and 'z-index' in body:
                    bad.append((os.path.basename(p), sel.strip()[:60]))
        self.assertEqual(bad, [], 'CSS 가 칸의 층 번호를 덮습니다 — 층 순서는 layers.js 표에서만 정한다')

    def test_widgets_stay_in_their_layer(self):
        wdir = os.path.join(OVERLAY, 'widgets')
        pat = re.compile(r'document\.(body|documentElement)\.(append|appendChild|prepend|insertBefore|insertAdjacentElement|insertAdjacentHTML)\s*\('
                         r'|getElementById\(\s*[\'"]canvas[\'"]\s*\)\s*\.(append|appendChild|prepend|insertBefore)'
                         r'|window\.confetti\s*\(')
        bad = []
        for root_, _dirs, files in os.walk(wdir):
            for f in files:
                if not f.endswith('.js'):
                    continue
                p = os.path.join(root_, f)
                rel = os.path.relpath(p, wdir)
                if rel in ESCAPE_OK:
                    continue
                for i, line in enumerate(_read(p).splitlines(), 1):
                    if pat.search(line):
                        bad.append('%s:%d' % (rel.replace(os.sep, '/'), i))
        self.assertEqual(bad, [], '위젯이 자기 칸 밖(body · 캔버스)에 붙습니다 — 층 표를 우회합니다')


if __name__ == '__main__':
    unittest.main()
