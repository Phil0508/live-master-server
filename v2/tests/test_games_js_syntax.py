# -*- coding: utf-8 -*-
"""v2/web 의 모든 .js 가 브라우저 모듈로 읽히는가 — node 로 .mjs 처럼 문법만 본다.

10-17 games 갈래: 조종실 [옛 설정 옮기기] 확인 글에 따옴표 안 맨 줄바꿈이 들어가 migrate.js 가 안 읽혔고,
그 파일을 부르는 tools_ops.js → tools.js → main.js 까지 줄줄이 막혀 조종실이 '서버에 연결하는 중…' 에서 멈췄다.
node --check 는 .js 를 CommonJS 로도 읽어 보고 넘어갈 때가 있어, 꼭 .mjs 로 복사해서 본다(브라우저와 같은 모듈 문법).
"""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(ROOT, 'v2', 'web')


class WebJsSyntax(unittest.TestCase):
    def test_every_js_parses_as_module(self):
        node = shutil.which('node')
        if not node:
            raise unittest.SkipTest('node 없음')
        files = []
        for d, _, names in os.walk(WEB):
            files += [os.path.join(d, n) for n in names if n.endswith('.js')]
        self.assertGreater(len(files), 50)
        tmp = tempfile.mkdtemp(prefix='lm2-jssyntax-')
        bad = []
        try:
            for i, f in enumerate(files):
                m = os.path.join(tmp, 'f%d.mjs' % i)
                shutil.copyfile(f, m)
                r = subprocess.run([node, '--check', m], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
                if r.returncode != 0:
                    bad.append('%s\n%s' % (os.path.relpath(f, ROOT), r.stderr.strip()[:400]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(bad, [], '\n\n'.join(bad))


if __name__ == '__main__':
    unittest.main()
