# -*- coding: utf-8 -*-
"""v2/web 의 모든 .js 가 브라우저 모듈로 읽히는가 — node 로 .mjs 처럼 문법만 본다.

10-17 games 갈래: 조종실 [옛 설정 옮기기] 확인 글에 따옴표 안 맨 줄바꿈이 들어가 migrate.js 가 안 읽혔고,
그 파일을 부르는 tools_ops.js → tools.js → main.js 까지 줄줄이 막혀 조종실이 '서버에 연결하는 중…' 에서 멈췄다.
node --check 는 .js 를 CommonJS 로도 읽어 보고 넘어갈 때가 있어, 꼭 .mjs 로 복사해서 본다(브라우저와 같은 모듈 문법).
"""
import json
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

    def test_every_import_resolves(self):
        """import { a } from './b.js' 의 a 가 b.js 에 정말 있는가 · 그 파일이 있는가 — 문법 검사(--check)로는 안 잡힌다.
        이름 하나만 틀려도 브라우저는 그 파일과 그 파일을 부르는 모든 파일을 통째로 안 돌린다
        (조종실이면 main.js 까지 막혀 '서버에 연결하는 중…' 에서 멈춘다). 실행은 안 하고 잇기(link)만 한다."""
        node = shutil.which('node')
        if not node:
            raise unittest.SkipTest('node 없음')
        r = subprocess.run([node, '--experimental-vm-modules', '--no-warnings', '--input-type=module', '-e', _LINK_JS, WEB],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        got = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertGreater(got['n'], 50)
        self.assertEqual(got['bad'], [], '\n'.join(got['bad']))


# node: v2/web 의 모듈(vendor 빼고)을 vm.SourceTextModule 로 읽어 잇기만 한다 — 없는 이름 · 없는 파일이면 link 가 던진다.
#   '/overlay/layers.js' 처럼 / 로 시작하는 것은 v2/web 기준. import · export 가 없는 옛 스크립트는 건너뛴다.
_LINK_JS = r"""
import vm from 'node:vm'; import fs from 'node:fs'; import path from 'node:path';
const WEB = process.argv[1];
const files = [];
(function walk(d) { for (const n of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, n.name);
    if (n.isDirectory()) { if (n.name !== 'vendor') walk(p); } else if (n.name.endsWith('.js')) files.push(p); } })(WEB);
const cache = new Map(), ctx = vm.createContext({});
const load = p => { if (!cache.has(p)) cache.set(p, new vm.SourceTextModule(fs.readFileSync(p, 'utf8'), { identifier: p, context: ctx })); return cache.get(p); };
const bad = [];
for (const f of files) {
    if (!/^\s*(import|export)\s/m.test(fs.readFileSync(f, 'utf8'))) continue;
    try {
        const m = load(f);
        if (m.status !== 'unlinked') continue;
        await m.link((spec, ref) => {
            const p = spec.startsWith('/') ? path.join(WEB, spec) : path.resolve(path.dirname(ref.identifier), spec);
            if (!fs.existsSync(p)) throw new Error('없는 파일 ' + spec);
            return load(p);
        });
    } catch (e) { bad.push(path.relative(WEB, f) + ': ' + e.message); }
}
console.log(JSON.stringify({ n: files.length, bad }));
"""


if __name__ == '__main__':
    unittest.main()
