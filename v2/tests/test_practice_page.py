# -*- coding: utf-8 -*-
"""🧪🎓 테스트 · 연습 페이지(v2/web/practice/practice.js) · 조종실 연습 띠(practiceband.js) 순수 함수 — node."""
import json
import os
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
NODE = r"""
import { pathToFileURL } from 'node:url';
const root = process.argv[1];
const p = await import(pathToFileURL(root + '/v2/web/practice/practice.js').href);
const band = await import(pathToFileURL(root + '/v2/web/controller/js/practiceband.js').href).catch(e => ({ err: String(e) }));
const sig = p.PRESETS.find(x => x.key === 'sig');
console.log(JSON.stringify({
  keys: p.PRESETS.map(x => x.key),
  sigBody: p.presetBody(sig, 54000),
  smallBody: p.presetBody(p.PRESETS[0], 54000),
  plan: p.burstPlan(50, 0.1, 30000).map(x => [x.body.amount, x.wait]),
  plan3: p.burstPlan(3, 2, 30000).map(x => x.body.name),
  sum: p.summaryLines({ cards: 5, given: 3, ignored: 1, jar: 1, checked: 3, correct: 2, avg_sec: 4.2, minutes: 3.5,
                        misses: [{ name: '별빛', amount: 10000, expect: '하율', got: ['서아'] }] }),
  names: p.parseNames('밍밍, 행복한걸  예지랑,밍밍 · 앙앙'),
  bandOff: band.practiceBands ? band.practiceBands({ practice: { on: false } }) : band.err,
  bandOn: band.practiceBands ? band.practiceBands({ practice: { on: true, cards: [1, 2], real: 1 } }) : band.err,
}));
"""


class PracticePage(unittest.TestCase):
    def run_node(self):
        out = subprocess.run(['node', '--input-type=module', '-e', NODE, ROOT], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_presets_and_plans(self):
        r = self.run_node()
        self.assertIn('small', r['keys'])
        self.assertEqual(r['sigBody']['amount'], 54000)                 # 고른 시그 금액
        self.assertEqual(r['smallBody']['amount'], 5000)                # 시그 아닌 단추는 그대로
        self.assertEqual(len(r['plan']), 20)                            # 몰아치기 20건까지
        self.assertTrue(all(w == 500 for _, w in r['plan']))            # 간격 0.5초 밑으로 안 간다
        self.assertEqual(len(set(r['plan3'])), 3)                       # 이름이 겹치지 않게(묶이지 않게)
        self.assertEqual(r['names'], ['밍밍', '행복한걸', '예지랑', '앙앙'])

    def test_summary_text(self):
        r = self.run_node()
        tiles = {t['k']: t['v'] for t in r['sum']['tiles']}
        self.assertEqual(tiles['정답(기록과 같음)'], '2 / 3')
        self.assertEqual(tiles['모금함'], '1건')
        self.assertIn('기록은 하율', r['sum']['misses'][0])

    def test_controller_band(self):
        r = self.run_node()
        self.assertEqual(r['bandOff'], {'main': None, 'real': None})
        self.assertIn('2건', r['bandOn']['main']['sub'])
        self.assertEqual(r['bandOn']['real']['level'], 'bad')

    def test_page_has_no_inner_html_and_settings_tile(self):
        with open(os.path.join(ROOT, 'v2', 'web', 'practice', 'index.html'), encoding='utf-8') as f:
            s = f.read()
        self.assertNotIn('innerHTML', s)
        self.assertNotIn('confirm(', s)                                 # 확인은 페이지 안 상자로
        with open(os.path.join(ROOT, 'v2', 'web', 'controller', 'js', 'panels', 'settings_menu.js'), encoding='utf-8') as f:
            self.assertIn("'@practice'", f.read())


if __name__ == '__main__':
    unittest.main()
