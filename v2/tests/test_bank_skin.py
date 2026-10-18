# -*- coding: utf-8 -*-
"""🏦 계좌 띠 은행 옷 — 기업은행이면 마크 + 파란 포인트(10-19 대표님 시안 C), 다른 은행은 금색 그대로."""
import json
import os
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

NODE = r"""
import { pathToFileURL } from 'node:url';
const root = process.argv[1];
const a = await import(pathToFileURL(root + '/v2/web/overlay/widgets/basics2/account.js').href);
const names = ['기업은행', 'IBK기업은행', ' 기업 은행 ', 'ibk', '기업', '국민은행', '신한', '', null, '중소기업은행같은가짜아님'];
console.log(JSON.stringify(names.map(n => a.bankSkin(n))));
"""


class BankSkin(unittest.TestCase):
    def test_skin_by_bank_name(self):
        out = subprocess.run(['node', '--input-type=module', '-e', NODE, ROOT], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(got[:5], ['ibk'] * 5)
        self.assertEqual(got[5:9], [''] * 4)                  # 다른 은행 · 빈 칸은 금색 그대로

    def test_css_and_mark(self):
        with open(os.path.join(ROOT, 'v2', 'web', 'overlay', 'css', 'basics2.css'), encoding='utf-8') as f:
            css = f.read()
        self.assertIn('.acc-box-v2.bank-ibk .acc-ico', css)
        self.assertIn('/vendor/bank/ibk-symbol.png', css)
        with open(os.path.join(ROOT, 'vendor', 'bank', 'ibk-symbol.png'), 'rb') as f:
            self.assertEqual(f.read(8), b'\x89PNG\r\n\x1a\n')


if __name__ == '__main__':
    unittest.main()
