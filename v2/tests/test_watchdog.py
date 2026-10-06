# -*- coding: utf-8 -*-
"""🩹 감시 장치 — 진짜 systemctl · 네트워크 없이(가짜로 바꿔 끼운다). 죽은 것만 · 1시간 3번까지 · 알림."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('watchdog', os.path.join(os.path.dirname(HERE), 'deploy', 'watchdog.py'))
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2wd_')
        wd.STATE_DIR = os.path.join(self.dir, 'state')
        wd.STATUS_FILE = os.path.join(self.dir, 'status.json')
        self.up = {wd.OLD_URL: True, wd.V2_URL: True}
        self.enabled = {'toon-listener': True, 'livemaster-v2': True}
        self.restarts, self.notes = [], []
        wd.http_ok = lambda url, timeout=5: self.up.get(url, False)
        wd.unit_enabled = lambda u: self.enabled.get(u, False)
        wd.restart = lambda u: (self.restarts.append(u) or (0, ''))
        wd.notify = lambda text, kind='': self.notes.append(text)
        wd.disk_free_gb = lambda path='/': 10.0
        wd.close_wait_8080 = lambda: 0
        self.status(updated=1000, state='connected')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def status(self, updated, state):
        with open(wd.STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'updated': updated, 'accounts': {'main': {'state': state}}}, f)

    def events(self):
        p = os.path.join(wd.STATE_DIR, 'events.jsonl')
        if not os.path.exists(p):
            return []
        with open(p, encoding='utf-8') as f:
            return [json.loads(l) for l in f if l.strip()]


class Watchdog(_Base):
    def test_all_good_does_nothing(self):
        for t in range(5):
            wd.main(now=1000 + t * 60)
            self.status(updated=1000 + t * 60, state='connected')
        self.assertEqual(self.restarts, [])
        self.assertEqual(self.events(), [])

    def test_old_server_restart_after_three_minutes(self):
        self.up[wd.OLD_URL] = False
        for t in range(2):
            self.status(updated=1000 + t * 60, state='connected')
            wd.main(now=1000 + t * 60)
        self.assertEqual(self.restarts, [])                     # 1 · 2분째는 기다린다(잠깐 바쁜 것일 수 있다)
        self.status(updated=1120, state='connected')
        wd.main(now=1120)
        self.assertEqual(self.restarts, ['livemaster'])
        self.assertIn('다시 켰어요', self.notes[-1])
        self.up[wd.OLD_URL] = True
        self.status(updated=1180, state='connected')
        wd.main(now=1180)
        self.assertEqual(self.restarts, ['livemaster'])          # 살아났으면 더 안 켠다

    def test_at_most_three_restarts_per_hour_then_ask_human(self):
        self.up[wd.V2_URL] = False
        now = 1000
        for _ in range(20):
            self.status(updated=now, state='connected')
            wd.main(now=now)
            now += 60
        self.assertEqual(self.restarts.count('livemaster-v2'), 3)
        self.assertTrue(any('사람이 봐야' in n for n in self.notes))
        self.assertEqual(sum('사람이 봐야' in n for n in self.notes), 1)   # 같은 말을 1시간에 한 번만

    def test_v2_not_enabled_is_ignored(self):
        self.enabled['livemaster-v2'] = False
        self.up[wd.V2_URL] = False
        for t in range(5):
            self.status(updated=1000 + t * 60, state='connected')
            wd.main(now=1000 + t * 60)
        self.assertNotIn('livemaster-v2', self.restarts)

    def test_listener_frozen(self):
        self.status(updated=1000, state='connected')
        wd.main(now=1000 + 200)                                  # 3분 넘게 상태를 안 적음 → 멈춤
        self.assertEqual(self.restarts, ['toon-listener'])

    def test_listener_disconnected_ten_minutes(self):
        now = 1000
        for _ in range(10):
            self.status(updated=now, state='connecting')
            wd.main(now=now)
            now += 60
        self.assertEqual(self.restarts, [])                      # 10분까지는 리스너가 스스로 다시 붙게 둔다
        self.status(updated=now + 60, state='connecting')
        wd.main(now=now + 60)
        self.assertEqual(self.restarts, ['toon-listener'])

    def test_warnings_only_notify(self):
        wd.disk_free_gb = lambda path='/': 0.4
        wd.close_wait_8080 = lambda: 150
        wd.main(now=1000)
        wd.main(now=1060)
        self.assertEqual(self.restarts, [])
        self.assertEqual(len([n for n in self.notes if '디스크' in n]), 1)
        self.assertEqual(len([n for n in self.notes if '반쯤 끊긴' in n]), 1)


if __name__ == '__main__':
    unittest.main()


class Summaries(_Base):
    def test_wed_16_and_thu_04_once(self):
        import calendar
        wed16 = calendar.timegm((2026, 10, 7, 7, 5, 0)) * 1.0      # 10-07(수) 16:05 KST = 07:05 UTC
        thu04 = calendar.timegm((2026, 10, 7, 19, 2, 0)) * 1.0     # 10-08(목) 04:02 KST
        for now in (wed16, wed16 + 60):
            self.status(updated=now, state='connected')
            wd.main(now=now)
        pre = [n for n in self.notes if '방송 전 점검' in n]
        self.assertEqual(len(pre), 1)                               # 한 번만
        self.assertIn('투네이션 ✅', pre[0])
        self.status(updated=thu04, state='connected')
        wd.main(now=thu04)
        post = [n for n in self.notes if '방송 끝 정리' in n]
        self.assertEqual(len(post), 1)
        self.assertIn('밤사이 다시 켠 일 없음', post[0])
