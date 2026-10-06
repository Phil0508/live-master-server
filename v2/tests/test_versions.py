# -*- coding: utf-8 -*-
"""v2 버전 되돌리기 — git 은 가짜로 바꿔 끼운다(진짜 저장소를 옮기지 않는다)."""
import unittest
from unittest import mock

from v2.server.domain import versions as vs
from v2.tests.test_flow import Base, H

SHAS = ['c' * 40, 'b' * 40, 'a' * 40]


def fake_git(*args, timeout=25):
    a = list(args)
    if a[:1] == ['rev-parse']:
        return (SHAS[0] if a[1] in ('HEAD', 'origin/main') else ''), True
    if a[:1] == ['log'] and '-1' in a:
        return ('2026-10-07 09:00' if any('date' in x for x in a) else '테스트 커밋'), True
    if a[:1] == ['log']:
        return '\n'.join('%s\x1f%s\x1f2026-10-0%d 09:00\x1f커밋 %d' % (s, s[:7], 7 - i, i) for i, s in enumerate(SHAS)), True
    if a[:1] == ['rev-list']:
        return str({SHAS[0]: 300, SHAS[1]: 299, SHAS[2]: 298}.get(a[2], 0)), True
    if a[:1] == ['grep']:
        return '%s:%s' % (SHAS[0], vs.UI_FILE), True
    if a[:1] == ['fetch']:
        return '', True
    if a[:1] == ['checkout']:
        return '', True
    return '', False


class Versions(Base):
    def setUp(self):
        super().setUp()
        self.p = [mock.patch.object(vs, '_git', fake_git), mock.patch.object(vs, '_write_pin', lambda s: True),
                  mock.patch.object(vs, '_restart_services', lambda: None), mock.patch.object(vs, 'RUNNING_SHA', SHAS[0])]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        super().tearDown()

    def test_list(self):
        r = self.c.get('/api/version/list', headers=H).json()
        self.assertEqual(r['current']['label'], 'V300')
        self.assertEqual([c['label'] for c in r['commits']], ['V300', 'V299', 'V298'])
        self.assertEqual([c['has_ui'] for c in r['commits']], [True, False, False])   # v2 가 없던 버전은 미리 알린다
        self.assertFalse(r['needs_restart'])
        self.assertEqual(self.c.get('/api/version/list').status_code, 401)

    def test_switch_rules(self):
        r = self.c.post('/api/version/switch', json={'sha': 'f' * 40}, headers=H)
        self.assertEqual(r.status_code, 409)                          # 방송 중 — 한 번 더 묻는다
        self.assertTrue(r.json()['need_confirm'])
        r = self.c.post('/api/version/switch', json={'sha': 'f' * 40, 'during_live': True}, headers=H)
        self.assertEqual(r.status_code, 400)                          # 목록에 없는 번호는 안 받는다
        self.cmd('session.end')
        with mock.patch('threading.Timer') as T:
            r = self.c.post('/api/version/switch', json={'sha': SHAS[1]}, headers=H).json()
        self.assertTrue(r['restarting'])
        self.assertEqual(r['label'], 'V299')
        T.assert_called_once()
        r = self.c.post('/api/version/switch', json={'sha': SHAS[0]}, headers=H).json()
        self.assertFalse(r['restarting'])                             # 이미 그 버전

    def test_latest_and_notes(self):
        r = self.c.post('/api/version/latest', headers=H).json()
        self.assertEqual(r['message'], '이미 최신입니다')
        self.assertEqual(self.c.get('/api/patchnotes').status_code, 401)


if __name__ == '__main__':
    unittest.main()
