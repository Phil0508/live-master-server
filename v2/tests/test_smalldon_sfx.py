# -*- coding: utf-8 -*-
"""🔊 소액 띠 '띵-동' — 10-18 대표님 "소액은 좀 쓰는거같기도"(점수 알약 · 1등 탈환 소리는 안 씀 → 안 넣음)."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
OV = os.path.join(HERE, '..', 'web', 'overlay')


def read(*p):
    with open(os.path.join(OV, *p), encoding='utf-8') as f:
        return f.read()


class SmallDonSfx(unittest.TestCase):
    def test_tune_is_old_ding(self):
        s = read('widgets', 'basics2', 'sfx.js')
        self.assertIn("'donation': [[880, 0, .07, .18], [1175, 70, .13, .18]]", s)
        self.assertNotIn("'takeover'", s)                     # 1등 탈환 세 음은 안 넣는다(대표님)

    def test_band_plays_once_when_shown(self):
        s = read('widgets', 'small-don.js')
        self.assertIn("from './basics2/sfx.js'", s)
        self.assertIn('sfxInit(opts);', s)
        calls = [m.start() for m in re.finditer(r"^\s*playSfx\('donation'\);", s, re.M)]   # 코드 줄만(머리 주석 말고)
        self.assertEqual(len(calls), 1)
        self.assertLess(s.index("bar.classList.add('show');"), calls[0])

    def test_score_pill_stays_silent(self):
        self.assertNotIn('playSfx', read('widgets', 'score-popup.js'))


if __name__ == '__main__':
    unittest.main()
