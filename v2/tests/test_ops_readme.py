# -*- coding: utf-8 -*-
"""📋 갈아타는 날 점검표(v2/deploy/README.md) — 순서 · 빠진 단계 · 없는 파일을 가리키는 줄을 막는다.

사람이 방송 전에 위에서부터 따라 하는 글이라, 단계 순서가 바뀌거나 지운 파일(10-07 의 v2.conf 덧붙임)을 깔라고 하면 사고가 난다.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
README = os.path.join(REPO, 'v2', 'deploy', 'README.md')


def read():
    with open(README, encoding='utf-8') as f:
        return f.read()


def section(text, head, nxt):
    a = text.index(head)
    b = text.index(nxt, a + 1)
    return text[a:b]


class SwitchDay(unittest.TestCase):
    def setUp(self):
        self.t = read()
        self.day = section(self.t, '## 5. 갈아타는 날', '## 6.')
        self.back = section(self.t, '## 되돌리는 길', '## 백업 되살리기')

    def test_steps_in_order(self):
        heads = re.findall(r'^### (\S)', self.day, re.M)
        self.assertEqual(heads, list('⓪①②③④⑤⑥⑦⑧⑨'))

    def test_broadcast_window_and_deadline(self):
        self.assertIn('수 17:00 ~ 목 03:00', self.day)
        self.assertIn('2시간 전', self.day)

    def test_each_step_has_its_command(self):
        want = [
            ('①', ['systemctl stop livemaster-v2', 'import_old_db --v2-db v2/data/lm2.db', '--write', 'systemctl start livemaster-v2']),
            ('②', ['[옛 설정 옮기기]']),
            ('③', ['trial.conf', 'LM2_TRIAL']),
            ('④', ['v2/deploy/toon-listener.service /etc/systemd/system/toon-listener.service', "grep '^DONATION_URL'"]),
            ('⑤', ['disable --now livemaster-bot\n', 'enable --now livemaster-bot-v2']),
            ('⑥', ['caddy_switch.py apply', 'sudo -u caddy -H caddy validate', '/api/bank/app']),
            ('⑦', ['STANDBY=1', 'livemaster.service.d/standby.conf']),
            ('⑧', [':8443/overlay/', '고급 접근 권한', ':8443/controller/', '도우미 받기', 'streamdeck', '은행 확장 · 폰 앱은 그대로']),
        ]
        for mark, needles in want:
            body = re.search(r'^### %s.*?(?=^### |\Z)' % mark, self.day, re.M | re.S).group(0)
            for n in needles:
                self.assertIn(n, body, (mark, n))
        # 단계 안의 순서: 세어 보기 → --write, 옛 봇 끄기 → v2 봇 켜기, 장부 옮기기는 v2 를 멈춘 뒤
        one = re.search(r'^### ①.*?(?=^### )', self.day, re.M | re.S).group(0)
        self.assertLess(one.index('systemctl stop livemaster-v2'), one.index('import_old_db'))
        self.assertLess(one.index('--v2-db v2/data/lm2.db  '), one.index('--write'))
        self.assertLess(one.index('--write'), one.index('systemctl start livemaster-v2'))
        five = re.search(r'^### ⑤.*?(?=^### )', self.day, re.M | re.S).group(0)
        self.assertLess(five.index('disable --now livemaster-bot\n'), five.index('enable --now livemaster-bot-v2'))

    def test_no_root_validate_and_no_dropin_install(self):
        for line in self.t.splitlines():
            s = line.strip()
            if s.startswith('sudo caddy validate'):
                self.fail('root 로 validate 하라는 줄: ' + s)
            if 'v2.conf' in s and s.startswith('sudo cp'):
                self.fail('지운 덧붙임 파일을 깔라는 줄: ' + s)

    def test_rollback_order(self):
        steps = re.findall(r'^(\d)\. \*\*(.+?)\*\*', self.back, re.M)
        names = [n for _i, n in steps]
        self.assertTrue(names[0].startswith('옛 서버 STANDBY 풀기'), names)
        self.assertTrue(names[1].startswith('리스너를 옛 서버로'), names)
        self.assertTrue(names[2].startswith('진행봇'), names)
        self.assertIn('deploy/toon-listener.service', self.back)
        self.assertIn('caddy_switch.py revert', self.back)
        self.assertIn('Caddyfile.bak-before-switch', self.back)
        self.assertLess(self.back.index('disable --now livemaster-bot-v2'), self.back.index('enable --now livemaster-bot`'))

    def test_referenced_repo_files_exist(self):
        for rel in set(re.findall(r'/opt/livemaster/((?:v2/)?(?:deploy|tools)/[\w./-]+\.(?:py|service|timer|sh))', self.t)):
            self.assertTrue(os.path.isfile(os.path.join(REPO, rel)), rel)
        for rel in set(re.findall(r'`(v2/deploy/[\w./-]+)`', self.t)):
            self.assertTrue(os.path.exists(os.path.join(REPO, rel)), rel)

    def test_backup_upload_guide(self):
        body = section(self.t, '## 💾 장부 바깥 백업', '## 되돌리는 길')
        self.assertIn('LM2_BACKUP_UPLOAD=1', body)
        self.assertIn('비공개', body)
        with open(os.path.join(REPO, 'v2', 'deploy', 'livemaster-v2-backup.service'), encoding='utf-8') as f:
            self.assertIn('Environment=LM2_BACKUP_UPLOAD=0', f.read())     # 기본은 꺼짐


if __name__ == '__main__':
    unittest.main()
