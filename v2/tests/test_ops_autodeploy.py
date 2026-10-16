# -*- coding: utf-8 -*-
"""🔄 자동 배포(deploy/auto-deploy.sh)가 v2 를 안다 — 그리고 v2 가 없는 서버에서는 **예전과 똑같다**.

운영 서버에서 2분마다 실제로 도는 파일이라 아주 조심한다. 진짜 systemctl · git · sudo · curl · pip 대신
가짜(한 줄씩 기록만 하는 작은 스크립트)를 PATH 맨 앞에 두고, 스크립트를 bash 로 그대로 돌린다.
  ① v2 가 없는 서버: 고치기 전 판(ops_fixtures/auto-deploy.before-v2.sh — 10-17 그대로 떠 둔 것)과 새 판을
     같은 상황 9가지로 나란히 돌려, 기록 · 화면 출력 · 끝 번호가 같은지 본다(새 판이 v2 있는지 묻는 한 줄만 뺀다).
  ② v2 를 켜 둔 서버: 방송 중(409)이면 아무것도 안 건드리고 끝 · 그 밖의 답 · 못 닿음은 배포 · v2 꾸러미 ·
     v2 재시작은 옛 서비스 다음 · 돌고 있을 때만(try-restart) · 꾸러미 실패면 v2 는 그대로 · 고정 버전 길.
bash 가 없으면(윈도우인데 Git 이 없음) 건너뛴다. 윈도우는 Git 의 bash 를 쓴다(System32 의 WSL bash 는 안 쓴다).
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
NEW = os.path.join(REPO, 'deploy', 'auto-deploy.sh')
OLD = os.path.join(HERE, 'ops_fixtures', 'auto-deploy.before-v2.sh')
PROBE = 'systemctl is-enabled --quiet livemaster-v2'
A, B = 'a' * 40, 'b' * 40


def find_bash():
    if os.name != 'nt':
        for p in ('/bin/bash', '/usr/bin/bash'):
            if os.path.exists(p):
                return p
        return shutil.which('bash')
    git = shutil.which('git')
    d = os.path.dirname(git) if git else ''
    for _ in range(3):                                   # …\Git\cmd\git.exe · …\Git\mingw64\bin\git.exe
        for c in (os.path.join(d, 'bin', 'bash.exe'), os.path.join(d, 'usr', 'bin', 'bash.exe')):
            if d and os.path.exists(c):
                return c
        d = os.path.dirname(d)
    c = r'C:\Program Files\Git\bin\bash.exe'
    return c if os.path.exists(c) else None


def posix(p):
    """bash 에 넘길 경로 — 윈도우는 /c/Users/… 모양으로."""
    if os.name != 'nt':
        return p
    drive, rest = os.path.splitdrive(os.path.abspath(p))
    return '/' + drive[0].lower() + rest.replace('\\', '/')


FAKES = {
    'sudo': '''#!/usr/bin/env bash
if [ "$1" = "-u" ]; then export FAKE_AS="$2"; shift 2; fi
exec "$@"
''',
    'git': '''#!/usr/bin/env bash
echo "git $* (as ${FAKE_AS:-root})" >> "$FAKE_LOG"
case "$1" in
  rev-parse) if [ "$2" = "HEAD" ]; then echo "$FAKE_HEAD"; else echo "$FAKE_REMOTE"; fi ;;
  diff) for p in $FAKE_CHANGED; do [ "${@: -1}" = "$p" ] && exit 1; done; exit 0 ;;
  checkout)
    if [ "${FAKE_CHECKOUT_FAIL:-0}" = "1" ]; then exit 1; fi
    if [ -n "${FAKE_CHECKOUT_RM:-}" ]; then rm -f "$FAKE_CHECKOUT_RM"; fi ;;
esac
exit 0
''',
    'systemctl': '''#!/usr/bin/env bash
echo "systemctl $*" >> "$FAKE_LOG"
u="${@: -1}"
case "$1" in
  is-enabled) for e in $FAKE_ENABLED; do [ "$e" = "$u" ] && exit 0; done; exit 1 ;;
  restart|try-restart) for f in ${FAKE_FAIL_UNITS:-}; do [ "$f" = "$u" ] && exit 1; done; exit 0 ;;
esac
exit 0
''',
    'curl': '''#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
printf '%s' "${FAKE_CURL_CODE:-200}"
exit "${FAKE_CURL_RC:-0}"
''',
}
PIP = '''#!/usr/bin/env bash
echo "pip $* (as ${FAKE_AS:-root})" >> "$FAKE_LOG"
exit "${FAKE_PIP_RC:-0}"
'''


def _write(path, text, mode=0o755):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    os.chmod(path, mode)


class Harness:
    def __init__(self, bash, script_path):
        self.bash = bash
        with open(script_path, encoding='utf-8') as f:
            self.src = f.read()

    def run(self, env=None, pin=None, has_v2_code=True):
        tmp = tempfile.mkdtemp(prefix='lm2_autodeploy_')
        try:
            app, fake = os.path.join(tmp, 'app'), os.path.join(tmp, 'bin')
            for name, body in FAKES.items():
                _write(os.path.join(fake, name), body)
            _write(os.path.join(app, '.venv', 'bin', 'pip'), PIP)
            if has_v2_code:
                _write(os.path.join(app, 'v2', 'server', 'app.py'), '# v2\n', 0o644)
            if pin is not None:
                _write(os.path.join(app, 'DEPLOY_PIN'), pin + '\n', 0o644)
            line = 'APP_DIR=/opt/livemaster\n'
            self.assert_one = self.src.count(line) == 1
            script = os.path.join(tmp, 'auto-deploy.sh')
            _write(script, self.src.replace(line, 'APP_DIR=%s\n' % posix(app)))
            log = os.path.join(tmp, 'log.txt')
            open(log, 'w').close()
            e = dict(os.environ)
            for k in list(e):
                if k.startswith('FAKE_'):
                    del e[k]
            e.update({'FAKE_LOG': posix(log), 'FAKE_BIN': posix(fake), 'FAKE_HEAD': A, 'FAKE_REMOTE': A,
                      'FAKE_ENABLED': 'toon-listener livemaster-bot', 'FAKE_CHANGED': ''})
            if (env or {}).get('FAKE_CHECKOUT_RM') == 'v2app':
                env = dict(env, FAKE_CHECKOUT_RM=posix(os.path.join(app, 'v2', 'server', 'app.py')))
            e.update(env or {})
            # ⚠️ PATH 는 bash 안에서 맨 앞에 붙인다 — 윈도우 Git bash 는 켜질 때 자기 폴더(진짜 git)를 앞에 넣는다
            wrapper = 'export PATH="$FAKE_BIN:$PATH"; exec bash "$0"'
            p = subprocess.run([self.bash, '-c', wrapper, posix(script)], env=e, capture_output=True, timeout=60)
            out = p.stdout.decode('utf-8', 'replace')
            with open(log, encoding='utf-8', errors='replace') as f:
                raw = f.read()
            lines = [l.replace(posix(app), '/opt/livemaster') for l in raw.splitlines() if l.strip()]
            return p.returncode, out.replace(posix(app), '/opt/livemaster'), lines, p.stderr.decode('utf-8', 'replace')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


BASH = find_bash()


@unittest.skipUnless(BASH, 'bash 가 없어 자동 배포 스크립트를 못 돌린다')
class Syntax(unittest.TestCase):
    def test_bash_n(self):
        for p in (NEW, OLD):
            r = subprocess.run([BASH, '-n', posix(p)], capture_output=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr.decode('utf-8', 'replace'))

    def test_lf_only(self):
        for p in (NEW, OLD):
            with open(p, 'rb') as f:
                self.assertNotIn(b'\r', f.read(), p)              # CRLF 면 우분투에서 'bash\r' 로 통째 실패

    def test_old_lines_all_kept(self):
        """고친 것은 '더하기' 뿐 — 옛 판의 줄이 하나도 빠지거나 바뀌지 않았다(순서도 그대로)."""
        with open(OLD, encoding='utf-8') as f:
            old = f.read().splitlines()
        with open(NEW, encoding='utf-8') as f:
            new = f.read().splitlines()
        it = iter(new)
        missing = [l for l in old if not any(l == n for n in it)]
        self.assertEqual(missing, [])


@unittest.skipUnless(BASH, 'bash 가 없어 자동 배포 스크립트를 못 돌린다')
class NoV2SameAsBefore(unittest.TestCase):
    """v2 를 안 켠 서버 — 새 판이 옛 판과 똑같이 움직인다."""

    CASES = {
        '변경 없음': {},
        '새 커밋': {'FAKE_REMOTE': B},
        '새 커밋 · requirements 바뀜': {'FAKE_REMOTE': B, 'FAKE_CHANGED': 'requirements.txt'},
        '새 커밋 · v2 꾸러미만 바뀜(v2 안 씀)': {'FAKE_REMOTE': B, 'FAKE_CHANGED': 'v2/requirements.txt'},
        '새 커밋 · 리스너 · 봇 꺼 둠': {'FAKE_REMOTE': B, 'FAKE_ENABLED': ''},
        '새 커밋 · 방송 중이라는 답이 와도(v2 없음)': {'FAKE_REMOTE': B, 'FAKE_CURL_CODE': '409'},
        '고정 버전으로 맞춤': {'_pin': B},
        '고정 버전 · 옮기기 실패': {'_pin': B, 'FAKE_CHECKOUT_FAIL': '1'},
        '고정 버전 · 이미 그 버전': {'_pin': A},
    }

    def test_identical(self):
        old, new = Harness(BASH, OLD), Harness(BASH, NEW)
        for name, env in self.CASES.items():
            with self.subTest(name):
                env = dict(env)
                pin = env.pop('_pin', None)
                r_old = old.run(env, pin=pin)
                r_new = new.run(env, pin=pin)
                self.assertTrue(old.assert_one and new.assert_one)
                self.assertTrue(r_old[2], '가짜 명령이 불리지 않았다 — 진짜 명령이 돌았을 수 있다: %s' % r_old[3])
                self.assertEqual(r_new[0], r_old[0], (r_new, r_old))
                self.assertEqual(r_new[1], r_old[1])
                self.assertEqual([l for l in r_new[2] if l != PROBE], r_old[2])
                self.assertFalse([l for l in r_new[2] if 'v2' in l and l != PROBE], r_new[2])   # v2 는 한 번도 안 건드림
                self.assertFalse([l for l in r_new[2] if l.startswith('curl')])


@unittest.skipUnless(BASH, 'bash 가 없어 자동 배포 스크립트를 못 돌린다')
class WithV2(unittest.TestCase):
    ON = 'toon-listener livemaster-bot livemaster-v2 livemaster-bot-v2'

    def run_new(self, pin=None, has_v2_code=True, **env):
        env.setdefault('FAKE_ENABLED', self.ON)
        return Harness(BASH, NEW).run(env, pin=pin, has_v2_code=has_v2_code)

    def test_on_air_waits_and_touches_nothing(self):
        rc, out, log, err = self.run_new(FAKE_REMOTE=B, FAKE_CURL_CODE='409', FAKE_CHANGED='requirements.txt v2/requirements.txt')
        self.assertEqual(rc, 0, err)
        self.assertIn('방송 중이라 배포를 미룹니다', out)
        self.assertTrue(any(l.startswith('curl') and '127.0.0.1:5300/api/deploy/ok' in l for l in log), log)
        for bad in ('checkout', 'reset', 'restart', 'pip', 'diff'):
            self.assertFalse([l for l in log if bad in l], (bad, log))

    def test_not_409_deploys(self):
        for code, rc_curl in (('200', '0'), ('000', '7'), ('500', '0')):     # 괜찮음 · v2 꺼짐(못 닿음) · v2 오류
            with self.subTest(code=code):
                rc, out, log, err = self.run_new(FAKE_REMOTE=B, FAKE_CURL_CODE=code, FAKE_CURL_RC=rc_curl)
                self.assertEqual(rc, 0, err)
                self.assertIn('배포 완료', out)
                self.assertIn('git reset --hard --quiet origin/main (as livemaster)', log)

    def test_order_old_first_then_v2_try_restart(self):
        rc, out, log, err = self.run_new(FAKE_REMOTE=B)
        self.assertEqual(rc, 0, err)
        i = log.index
        self.assertLess(i('systemctl restart livemaster'), i('systemctl restart toon-listener'))
        self.assertLess(i('systemctl restart livemaster-bot'), i('systemctl try-restart livemaster-v2'))
        self.assertLess(i('systemctl try-restart livemaster-v2'), i('systemctl try-restart livemaster-bot-v2'))
        self.assertFalse([l for l in log if l in ('systemctl restart livemaster-v2', 'systemctl start livemaster-v2')])
        self.assertFalse([l for l in log if l.startswith('pip')])               # 꾸러미가 안 바뀌면 안 깐다

    def test_v2_bot_only_if_enabled(self):
        rc, out, log, err = self.run_new(FAKE_REMOTE=B, FAKE_ENABLED='toon-listener livemaster-bot livemaster-v2')
        self.assertIn('systemctl try-restart livemaster-v2', log)
        self.assertNotIn('systemctl try-restart livemaster-bot-v2', log)

    def test_v2_requirements_pip_before_v2_restart(self):
        rc, out, log, err = self.run_new(FAKE_REMOTE=B, FAKE_CHANGED='v2/requirements.txt')
        self.assertEqual(rc, 0, err)
        pip = [l for l in log if l.startswith('pip')]
        self.assertEqual(pip, ['pip install --quiet -r /opt/livemaster/v2/requirements.txt (as livemaster)'])
        self.assertLess(log.index('systemctl restart livemaster-bot'), log.index(pip[0]))
        self.assertLess(log.index(pip[0]), log.index('systemctl try-restart livemaster-v2'))

    def test_both_requirements(self):
        rc, out, log, err = self.run_new(FAKE_REMOTE=B, FAKE_CHANGED='requirements.txt v2/requirements.txt')
        pip = [l for l in log if l.startswith('pip')]
        self.assertEqual(pip, ['pip install --quiet -r /opt/livemaster/requirements.txt (as livemaster)',
                               'pip install --quiet -r /opt/livemaster/v2/requirements.txt (as livemaster)'])
        self.assertLess(log.index(pip[0]), log.index('systemctl restart livemaster'))

    def test_v2_pip_fail_keeps_v2_running(self):
        rc, out, log, err = self.run_new(FAKE_REMOTE=B, FAKE_CHANGED='v2/requirements.txt', FAKE_PIP_RC='1')
        self.assertEqual(rc, 0, err)                                            # 옛 배포는 끝까지 됐다
        self.assertIn('systemctl restart livemaster', log)
        self.assertIn('v2 패키지 설치 실패', out)
        self.assertFalse([l for l in log if 'try-restart' in l], log)
        self.assertIn('배포 완료', out)

    def test_v2_restart_failure_does_not_abort(self):
        rc, out, log, err = self.run_new(FAKE_REMOTE=B, FAKE_FAIL_UNITS='livemaster-v2')
        self.assertEqual(rc, 0, err)
        self.assertIn('v2 다시 켜기 실패', out)
        self.assertIn('배포 완료', out)

    def test_no_change_does_not_ask_v2(self):
        rc, out, log, err = self.run_new()
        self.assertEqual((rc, out), (0, ''))
        self.assertFalse([l for l in log if l.startswith('curl') or 'restart' in l], log)

    def test_pin_restarts_v2_without_lock(self):
        rc, out, log, err = self.run_new(pin=B, FAKE_CURL_CODE='409')
        self.assertEqual(rc, 0, err)
        self.assertIn('고정 버전 적용', out)
        self.assertFalse([l for l in log if l.startswith('curl')])             # 비상 단추 — 방송 중에도 된다
        self.assertLess(log.index('systemctl restart livemaster-bot'), log.index('systemctl try-restart livemaster-v2'))

    def test_pin_to_version_without_v2(self):
        rc, out, log, err = self.run_new(pin=B, FAKE_CHECKOUT_RM='v2app')
        self.assertEqual(rc, 0, err)
        self.assertIn('이 버전에는 v2 가 없어', out)
        self.assertFalse([l for l in log if 'livemaster-v2' in l and l != PROBE], log)

    def test_disabled_v2_is_left_alone(self):
        """v2 서비스가 깔려 있어도 꺼 둔(disabled) 서버면 옛 동작 그대로 — curl 도 안 부른다."""
        rc, out, log, err = self.run_new(FAKE_REMOTE=B, FAKE_CURL_CODE='409', FAKE_ENABLED='toon-listener livemaster-bot')
        self.assertIn('배포 완료', out)
        self.assertFalse([l for l in log if l.startswith('curl') or 'try-restart' in l], log)


if __name__ == '__main__':
    unittest.main()
