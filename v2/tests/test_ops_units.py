# -*- coding: utf-8 -*-
"""🎧 리스너 서비스 파일(v2 판) — 옛 서버에 안 묶이고 v2 로 보낸다. 나머지는 옛 판과 한 글자도 같다.

systemd 를 이 PC 에서 돌릴 수 없어서 파일을 읽어 맞대 본다.
  - 옛 판(deploy/toon-listener.service)과 [Service] · [Install] 이 같다(보내는 곳 한 줄만 더했다)
  - [Unit] 에 livemaster.service 가 어디에도 없다(Requires · After · Wants · BindsTo · PartOf …)
  - v2 에는 Wants= 로만(Requires= 가 없어야 v2 를 잠깐 멈춰도 리스너가 산다)
  - 의존을 '빈 값' 으로 비우려는 덧붙임(효과 없음)이 v2/deploy 어디에도 없다
버전 되돌리기(versions.py)가 v2 자신을 맨 끝에 다시 켜고, 꺼 둔 것은 안 깨운다.
"""
import os
import unittest
from unittest import mock

from v2.server.domain import versions as vs

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEP_KEYS = ('Requires', 'Requisite', 'Wants', 'BindsTo', 'PartOf', 'Upholds', 'After', 'Before', 'Conflicts')


def parse_unit(path):
    """[섹션] → [(키, 값)] — 주석 · 빈 줄은 뺀다. 줄바꿈(CRLF)은 상관없다."""
    out, sec = {}, None
    with open(path, encoding='utf-8') as f:
        for raw in f.read().splitlines():
            line = raw.strip()
            if not line or line.startswith(('#', ';')):
                continue
            if line.startswith('[') and line.endswith(']'):
                sec = line[1:-1]
                out.setdefault(sec, [])
                continue
            k, _, v = line.partition('=')
            out.setdefault(sec, []).append((k.strip(), v.strip()))
    return out


class ListenerUnit(unittest.TestCase):
    def setUp(self):
        self.old = parse_unit(os.path.join(REPO, 'deploy', 'toon-listener.service'))
        self.new = parse_unit(os.path.join(REPO, 'v2', 'deploy', 'toon-listener.service'))

    def test_service_and_install_same_as_old_plus_url(self):
        added = [kv for kv in self.new['Service'] if kv not in self.old['Service']]
        removed = [kv for kv in self.old['Service'] if kv not in self.new['Service']]
        self.assertEqual(added, [('Environment', 'DONATION_URL=http://127.0.0.1:5300/api/donation')])
        self.assertEqual(removed, [])
        self.assertEqual(self.new['Install'], self.old['Install'])

    def test_not_bound_to_old_server(self):
        self.assertTrue(any('livemaster.service' in v for k, v in self.old['Unit'] if k == 'Requires'))   # 옛 판은 묶여 있었다
        for k, v in self.new['Unit']:
            if k in DEP_KEYS:
                self.assertNotIn('livemaster.service', v.split(), (k, v))

    def test_only_wants_v2(self):
        unit = dict()
        for k, v in self.new['Unit']:
            unit.setdefault(k, []).extend(v.split())
        self.assertIn('livemaster-v2.service', unit.get('After', []))
        self.assertIn('livemaster-v2.service', unit.get('Wants', []))
        for k in ('Requires', 'Requisite', 'BindsTo', 'PartOf'):
            self.assertNotIn(k, unit, '%s= 면 v2 를 멈출 때 리스너도 멈춘다' % k)

    def test_url_matches_v2_port(self):
        v2 = dict(kv for kv in parse_unit(os.path.join(REPO, 'v2', 'deploy', 'livemaster-v2.service'))['Service']
                  if kv[0] == 'Environment' and kv[1].startswith('LM2_PORT='))
        self.assertEqual(v2.get('Environment'), 'LM2_PORT=5300')

    def test_no_empty_dependency_dropins(self):
        """의존을 빈 값으로 비우는 덧붙임은 systemd 가 무시한다 — 그런 파일을 두면 '끊었다' 고 착각하게 된다."""
        self.assertFalse(os.path.exists(os.path.join(REPO, 'v2', 'deploy', 'toon-listener.service.d', 'v2.conf')))
        for root, _dirs, files in os.walk(os.path.join(REPO, 'v2', 'deploy')):
            for fn in files:
                if fn.endswith(('.conf', '.service')):
                    for k, v in parse_unit(os.path.join(root, fn)).get('Unit', []):
                        self.assertFalse(k in DEP_KEYS and v == '', (fn, k))


class VersionRestartOrder(unittest.TestCase):
    def run_restart(self, active, units=None):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            rc = 0
            if cmd[:2] == ['systemctl', 'is-active']:
                rc = 0 if cmd[-1] in active else 3
            return mock.Mock(returncode=rc, stdout='', stderr='')
        env = {} if units is None else {'LM2_RESTART_UNITS': units}
        with mock.patch.object(vs.subprocess, 'run', fake_run), mock.patch.dict(os.environ, env, clear=False):
            if units is None:
                os.environ.pop('LM2_RESTART_UNITS', None)
            vs._restart_services()
        return [c[-1] for c in calls if c[:4] == ['sudo', '-n', 'systemctl', 'restart']]

    def test_self_last_listener_first(self):
        got = self.run_restart({'toon-listener', 'livemaster-bot-v2', 'livemaster-v2'})
        self.assertEqual(got, ['toon-listener', 'livemaster-bot-v2', 'livemaster-v2'])

    def test_stopped_units_not_woken(self):
        got = self.run_restart({'toon-listener', 'livemaster-v2'})            # v2 진행봇 꺼 둠(옛 봇이 도는 중)
        self.assertEqual(got, ['toon-listener', 'livemaster-v2'])

    def test_self_moved_last_even_if_listed_first(self):
        got = self.run_restart({'toon-listener', 'livemaster-v2'}, units='livemaster-v2 toon-listener')
        self.assertEqual(got, ['toon-listener', 'livemaster-v2'])


if __name__ == '__main__':
    unittest.main()
