# -*- coding: utf-8 -*-
"""🚀 서버 처음 세우기(deploy/setup.sh)의 v2 선택 단계 — 안 켜면 **예전과 똑같다**.

진짜 apt-get · systemctl · iptables · visudo 대신 가짜(기록만 하는 작은 스크립트)를 PATH 맨 앞에 두고,
/etc · /opt · /var · /usr/share 를 임시 폴더 아래로 옮긴 사본을 bash 로 그대로 돌린다.
  ① --with-v2 없이: 고치기 전 판(ops_fixtures/setup.before-v2.sh — 10-17 main 그대로)과 새 판이 기록 · 화면 · 끝 번호 · 만든 파일까지 같다
  ② --with-v2: v2 꾸러미 · 서비스 6개 깔기 · v2 · 백업 · 감시 켜 두기(진행봇 v2 는 안 켬) · Caddy :8443 한 번만 ·
     기록 파일 caddy 것 · 방화벽 8443 · sudoers 는 문법 확인을 통과해야만 440 으로 · v2 코드가 없으면 건너뜀
bash 가 없으면 건너뛴다(윈도우는 Git 의 bash).
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from v2.tests.test_ops_autodeploy import _write, find_bash, posix

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
NEW = os.path.join(REPO, 'deploy', 'setup.sh')
OLD = os.path.join(HERE, 'ops_fixtures', 'setup.before-v2.sh')
BASH = find_bash()
ROOTED = ('/etc/', '/opt/', '/var/', '/usr/share/')

REC = '#!/usr/bin/env bash\necho "%s $*" >> "$FAKE_LOG"\n'
FAKES = {name: REC % name + 'exit 0\n' for name in (
    'apt-get', 'gpg', 'useradd', 'chown', 'netfilter-persistent', 'caddy')}
FAKES.update({
    'id': REC % 'id' + 'exit 0\n' + '',   # id -u → 0 은 아래에서
    'git': REC % 'git' + 'exit 0\n',
    'python3': REC % 'python3' + 'exit 0\n',
    'curl': REC % 'curl' + 'exit 0\n',
    'systemctl': REC % 'systemctl' + 'exit 0\n',
    'iptables': REC % 'iptables' + '[ "$1" = "-C" ] && exit 1\nexit 0\n',
    'visudo': REC % 'visudo' + 'exit "${FAKE_VISUDO_RC:-0}"\n',
    'mktemp': REC % 'mktemp' + 'mkdir -p "$FAKE_ROOT/tmp"; : > "$FAKE_ROOT/tmp/mktemp.1"; echo "$FAKE_ROOT/tmp/mktemp.1"\n',
    # install -m MODE SRC DST — 기록하고 진짜로 복사(뒤 단계가 그 파일을 읽는다)
    'install': REC % 'install' + 'src="${@: -2:1}"; dst="${@: -1}"; mkdir -p "$(dirname "$dst")"; cp "$src" "$dst"\n',
})
FAKES['id'] = REC % 'id' + 'if [ "$1" = "-u" ] && [ $# -eq 1 ]; then echo 0; fi\nexit 0\n'
PIP = REC % 'pip' + 'exit 0\n'


def run_setup(script_path, args=(), env=None, env_file=None, has_v2=True, root=None, keep=False):
    """→ (끝 번호, 화면, 기록 줄들, {만든 파일: 내용}, 오류 출력)."""
    with open(script_path, encoding='utf-8') as f:
        src = f.read()
    tmp = root or tempfile.mkdtemp(prefix='lm2_setup_')
    try:
        r = posix(tmp)
        fake = os.path.join(tmp, 'bin')
        for name, body in FAKES.items():
            _write(os.path.join(fake, name), body)
        app = os.path.join(tmp, 'opt', 'livemaster')
        os.makedirs(os.path.join(app, '.git'), exist_ok=True)
        _write(os.path.join(app, '.venv', 'bin', 'pip'), PIP)
        for f in ('livemaster.service', 'Caddyfile', 'toon-listener.service', 'auto-deploy.service', 'auto-deploy.timer'):
            shutil.copy(os.path.join(REPO, 'deploy', f), os.path.join(_mk(app, 'deploy'), f))
        if has_v2:
            dep = _mk(app, 'v2', 'deploy')
            for f in os.listdir(os.path.join(REPO, 'v2', 'deploy')):
                full = os.path.join(REPO, 'v2', 'deploy', f)
                if os.path.isfile(full):
                    shutil.copy(full, os.path.join(dep, f))
            shutil.copy(os.path.join(REPO, 'v2', 'requirements.txt'), os.path.join(app, 'v2', 'requirements.txt'))
        for d in (('etc', 'systemd', 'system'), ('etc', 'caddy'), ('etc', 'sudoers.d'), ('var', 'log')):
            _mk(tmp, *d)
        if env_file is not None:
            _write(os.path.join(tmp, 'etc', 'livemaster.env'), env_file, 0o600)
        for pre in ROOTED:
            src = src.replace(pre, r + pre)
        script = os.path.join(tmp, 'setup.sh')
        _write(script, src)
        log = os.path.join(tmp, 'log.txt')
        open(log, 'w').close()
        e = {k: v for k, v in os.environ.items() if not k.startswith('FAKE_') and k != 'WITH_V2'}
        e.update({'FAKE_LOG': posix(log), 'FAKE_BIN': posix(fake), 'FAKE_ROOT': r})
        e.update(env or {})
        wrapper = 'export PATH="$FAKE_BIN:$PATH"; exec bash "$0" "$@"'
        p = subprocess.run([BASH, '-c', wrapper, posix(script)] + list(args), env=e, capture_output=True, timeout=120)
        out = p.stdout.decode('utf-8', 'replace').replace(r, '')
        with open(log, encoding='utf-8', errors='replace') as f:
            lines = [l.replace(r, '') for l in f.read().splitlines() if l.strip()]
        files = {}
        for base in ('etc', os.path.join('var', 'log')):
            for dp, _dn, fns in os.walk(os.path.join(tmp, base)):
                for fn in fns:
                    full = os.path.join(dp, fn)
                    with open(full, encoding='utf-8', errors='replace') as f:
                        files[os.path.relpath(full, tmp).replace(os.sep, '/')] = f.read().replace(r, '')
        return p.returncode, out, lines, files, p.stderr.decode('utf-8', 'replace')
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


def _mk(*parts):
    d = os.path.join(*parts)
    os.makedirs(d, exist_ok=True)
    return d


@unittest.skipUnless(BASH, 'bash 가 없어 설치 스크립트를 못 돌린다')
class Syntax(unittest.TestCase):
    def test_bash_n_and_lf(self):
        for p in (NEW, OLD):
            r = subprocess.run([BASH, '-n', posix(p)], capture_output=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr.decode('utf-8', 'replace'))
            with open(p, 'rb') as f:
                self.assertNotIn(b'\r', f.read(), p)

    def test_old_lines_all_kept(self):
        """고친 것은 '더하기' 뿐 — 옛 판의 줄이 하나도 빠지거나 바뀌지 않았다(순서도 그대로)."""
        with open(OLD, encoding='utf-8') as f:
            old = f.read().splitlines()
        with open(NEW, encoding='utf-8') as f:
            new = f.read().splitlines()
        it = iter(new)
        self.assertEqual([l for l in old if not any(l == n for n in it)], [])


@unittest.skipUnless(BASH, 'bash 가 없어 설치 스크립트를 못 돌린다')
class DefaultSameAsBefore(unittest.TestCase):
    CASES = {
        '처음 깔기(env 없음)': {'env_file': None},
        '다시 깔기 · 리스너 주소 있음': {'env_file': 'ALERTBOX_URL=https://toon.at/widget/alertbox/x\n'},
        '다시 깔기 · 리스너 주소 비어 있음': {'env_file': 'ALERTBOX_URL=\n'},
        '다른 인자는 무시(예전처럼)': {'env_file': None, 'args': ['--something']},
        'WITH_V2=0': {'env_file': None, 'env': {'WITH_V2': '0'}},
    }

    def test_identical(self):
        for name, kw in self.CASES.items():
            with self.subTest(name):
                r_old = run_setup(OLD, **kw)
                r_new = run_setup(NEW, **kw)
                self.assertEqual(r_old[0], 0, r_old[4])
                self.assertTrue(r_old[2], '가짜 명령이 불리지 않았다 — 진짜 명령이 돌았을 수 있다: %s' % r_old[4])
                self.assertEqual(r_new[0], r_old[0], r_new[4])
                self.assertEqual(r_new[1], r_old[1])
                self.assertEqual(r_new[2], r_old[2])
                self.assertEqual(r_new[3], r_old[3])
                self.assertFalse([l for l in r_new[2] if 'v2' in l or '8443' in l or 'visudo' in l])


@unittest.skipUnless(BASH, 'bash 가 없어 설치 스크립트를 못 돌린다')
class WithV2(unittest.TestCase):
    UNITS = ('livemaster-v2.service', 'livemaster-v2-backup.service', 'livemaster-v2-backup.timer',
             'livemaster-watchdog.service', 'livemaster-watchdog.timer', 'livemaster-bot-v2.service')

    def test_flag_and_env_same(self):
        a = run_setup(NEW, args=['--with-v2'])
        b = run_setup(NEW, env={'WITH_V2': '1'})
        self.assertEqual(a[0], 0, a[4])
        self.assertEqual(a[1:4], b[1:4])

    def test_installs_v2(self):
        rc, out, log, files, err = run_setup(NEW, args=['--with-v2'])
        self.assertEqual(rc, 0, err)
        old_rc, _o, old_log, old_files, _e = run_setup(OLD)
        # 옛 단계는 그대로 먼저 다 돈다(앞부분 기록이 같다)
        first_v2 = next(i for i, l in enumerate(log) if 'v2/requirements.txt' in l)
        self.assertEqual(log[:first_v2], old_log[:first_v2])
        self.assertIn('pip install --quiet -r /opt/livemaster/v2/requirements.txt', log)
        for u in self.UNITS:
            self.assertIn('install -m 644 /opt/livemaster/v2/deploy/%s /etc/systemd/system/%s' % (u, u), log)
            self.assertIn('etc/systemd/system/' + u, files)
        self.assertIn('systemctl enable --quiet livemaster-v2 livemaster-v2-backup.timer livemaster-watchdog.timer', log)
        # 진행봇 v2 는 켜지 않는다 · 아무것도 --now 로 켜지 않는다(비밀값을 채운 뒤 사람이)
        v2_part = log[first_v2:]
        self.assertFalse([l for l in v2_part if l.startswith('systemctl') and 'bot-v2' in l], v2_part)
        self.assertFalse([l for l in v2_part if '--now' in l or ' start ' in l or ' restart ' in l], v2_part)
        # 리스너 v2 판은 갈아타는 날 — 여기서 안 깐다
        self.assertEqual(files['etc/systemd/system/toon-listener.service'], old_files['etc/systemd/system/toon-listener.service'])
        # Caddy: 옛 덩어리 + :8443 덩어리 하나
        caddy = files['etc/caddy/Caddyfile']
        self.assertTrue(caddy.startswith(old_files['etc/caddy/Caddyfile']))
        self.assertEqual(caddy.count(':8443 {'), 1)
        self.assertIn('var/log/caddy/livemaster-v2.log', files)
        self.assertIn('chown caddy:caddy /var/log/caddy/livemaster-v2.log', log)
        self.assertIn('iptables -I INPUT 1 -p tcp --dport 8443 -j ACCEPT', log)
        # sudoers: 문법 확인 → 440 으로 깔기 · 재시작 세 가지만
        vis = [i for i, l in enumerate(log) if l.startswith('visudo -cqf')]
        ins = [i for i, l in enumerate(log) if l.startswith('install -m 440') and l.endswith('/etc/sudoers.d/livemaster-v2-restart')]
        self.assertTrue(vis and ins and vis[0] < ins[0], log)
        sud = files['etc/sudoers.d/livemaster-v2-restart']
        body = sud.split('NOPASSWD:', 1)[1].replace('\\\n', ' ')
        self.assertEqual(body.strip().count('\n'), 0, sud)                  # 이어 쓰기(\) 말고는 한 줄
        cmds = sorted(c.strip() for c in body.split(','))
        self.assertEqual(cmds, sorted('%s/systemctl restart %s' % (b, u) for b in ('/usr/bin', '/bin')
                                      for u in ('livemaster-v2', 'livemaster-bot-v2', 'toon-listener')))
        self.assertTrue(sud.startswith('livemaster ALL=(root) NOPASSWD:'))
        self.assertNotIn('etc/sudoers.d/livemaster-restart', files)          # 옛 sudoers 파일은 안 만든다 · 안 건드린다
        self.assertIn('livemaster-v2', out)
        self.assertIn('caddy validate', out)

    def test_bad_sudoers_not_installed(self):
        rc, out, log, files, err = run_setup(NEW, args=['--with-v2'], env={'FAKE_VISUDO_RC': '1'})
        self.assertEqual(rc, 0, err)
        self.assertNotIn('etc/sudoers.d/livemaster-v2-restart', files)
        self.assertIn('sudoers 문법 확인 실패', out)

    def test_twice_one_caddy_block(self):
        tmp = tempfile.mkdtemp(prefix='lm2_setup_')
        try:
            run_setup(NEW, args=['--with-v2'], root=tmp, keep=True)
            rc, _out, _log, files, err = run_setup(NEW, args=['--with-v2'], root=tmp, keep=True)
            self.assertEqual(rc, 0, err)
            self.assertEqual(files['etc/caddy/Caddyfile'].count(':8443 {'), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_v2_code_skips(self):
        rc, out, log, files, err = run_setup(NEW, args=['--with-v2'], has_v2=False)
        r_old = run_setup(OLD, has_v2=False)
        self.assertEqual(rc, 0, err)
        self.assertEqual(log, r_old[2])
        self.assertEqual(files, r_old[3])
        self.assertIn('v2 가 없습니다', out)
        self.assertNotIn('v2 도 깔았습니다', out)


if __name__ == '__main__':
    unittest.main()
