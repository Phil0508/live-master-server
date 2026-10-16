# -*- coding: utf-8 -*-
"""☁️ 장부 백업의 바깥 올리기 — 가짜 Supabase 보관소(이 PC 안 127.0.0.1 의 작은 HTTP 서버)로 진짜 길을 그대로 탄다.

  - 스위치: --upload 또는 LM2_BACKUP_UPLOAD=1 일 때만 올린다(기본은 꺼짐 — 아무 요청도 안 나간다)
  - 올리기 전에 backups 버킷을 묻는다: 없으면 '비공개로 만드세요' · **공개면 안 올린다** · 확인이 안 되면 안 올린다
  - 올린 것 = 서버 안에 뜬 그 .db.gz 와 바이트가 같다 · 덮어쓰기(x-upsert) · 열쇠는 머리에만(화면에 안 찍는다)
  - 보관소가 실패하면 끝 번호 1(서비스 '실패') — 서버 안 백업은 남는다
진짜 Supabase 는 부르지 않는다(SUPABASE_URL 을 가짜 서버로 바꿔 끼운다).
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from v2.server.store import Store
from v2.tools import backup_db as bk

KEY = 'test-secret-key-xyz'


class FakeStorage:
    def __init__(self):
        self.bucket = (200, {'id': 'backups', 'name': 'backups', 'public': False})
        self.put_status = 200
        self.calls, self.objects = [], {}
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                raw = json.dumps(body).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                fake.calls.append(('GET', self.path, dict(self.headers)))
                if self.path == '/storage/v1/bucket/backups':
                    return self._send(*fake.bucket)
                self._send(404, {'error': 'nope'})

            def do_POST(self):
                n = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(n)
                fake.calls.append(('POST', self.path, dict(self.headers)))
                if fake.put_status == 200:
                    fake.objects[self.path] = body
                self._send(fake.put_status, {'Key': self.path} if fake.put_status == 200 else {'error': 'boom'})

        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = 'http://127.0.0.1:%d' % self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class BackupUpload(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2bkup_t_')
        self.db = os.path.join(self.dir, 'lm2.db')
        self.out = os.path.join(self.dir, 'bk')
        self.st = Store(self.db)
        self.st.db.execute("INSERT INTO donations (id, tx_id, at, name, amount, status) VALUES ('d1', 't1', 1, '별빛', 50000, 'pending')")
        self.fake = FakeStorage()
        self.env = mock.patch.dict(os.environ, {'SUPABASE_URL': self.fake.url, 'SUPABASE_SECRET_KEY': KEY})
        self.env.start()
        os.environ.pop(bk.UPLOAD_ENV, None)

    def tearDown(self):
        self.env.stop()
        self.fake.close()
        self.st.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def main(self, *extra, env=None):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env or {}), contextlib.redirect_stdout(buf):
            rc = bk.main(['--db', self.db, '--out', self.out] + list(extra))
        return rc, buf.getvalue()

    def test_off_by_default(self):
        rc, out = self.main()
        self.assertEqual(rc, 0)
        self.assertEqual(self.fake.calls, [])                                    # 바깥으로 한 번도 안 나간다
        self.assertEqual(len(os.listdir(self.out)), 1)
        for v in ('0', '', 'no'):
            rc, out = self.main(env={bk.UPLOAD_ENV: v})
            self.assertEqual(self.fake.calls, [], v)

    def test_env_switch_uploads_same_bytes(self):
        rc, out = self.main(env={bk.UPLOAD_ENV: '1'})
        self.assertEqual(rc, 0, out)
        local = os.path.join(self.out, os.listdir(self.out)[0])
        path = '/storage/v1/object/backups/v2/' + os.path.basename(local)
        with open(local, 'rb') as f:
            self.assertEqual(self.fake.objects.get(path), f.read())
        self.assertEqual([c[:2] for c in self.fake.calls], [('GET', '/storage/v1/bucket/backups'), ('POST', path)])
        hdr = {k.lower(): v for k, v in self.fake.calls[-1][2].items()}
        self.assertEqual((hdr['apikey'], hdr['authorization'], hdr['x-upsert'], hdr['content-type']),
                         (KEY, 'Bearer ' + KEY, 'true', 'application/gzip'))
        self.assertIn('☁️', out)
        self.assertNotIn(KEY, out)                                               # 열쇠는 화면에 안 찍는다

    def test_flag_still_works(self):
        rc, out = self.main('--upload')
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.fake.objects), 1)

    def test_missing_bucket_says_make_private(self):
        self.fake.bucket = (400, {'statusCode': '404', 'error': 'Bucket not found', 'message': 'Bucket not found'})
        rc, out = self.main(env={bk.UPLOAD_ENV: '1'})
        self.assertEqual(rc, 1)
        self.assertIn('비공개', out)
        self.assertEqual(self.fake.objects, {})
        self.assertEqual(len(os.listdir(self.out)), 1)                           # 서버 안 백업은 남는다

    def test_public_bucket_refused(self):
        self.fake.bucket = (200, {'id': 'backups', 'name': 'backups', 'public': True})
        rc, out = self.main(env={bk.UPLOAD_ENV: '1'})
        self.assertEqual(rc, 1)
        self.assertIn('공개', out)
        self.assertFalse([c for c in self.fake.calls if c[0] == 'POST'])

    def test_unknown_bucket_answer_refused(self):
        for ans in ((200, {'id': 'backups'}), (500, {'error': 'x'}), (200, ['odd'])):
            with self.subTest(ans=ans):
                self.fake.bucket, self.fake.calls = ans, []
                rc, out = self.main(env={bk.UPLOAD_ENV: 'on'})
                self.assertEqual(rc, 1)
                self.assertFalse([c for c in self.fake.calls if c[0] == 'POST'])

    def test_upload_failure_is_exit_1(self):
        self.fake.put_status = 500
        rc, out = self.main(env={bk.UPLOAD_ENV: 'true'})
        self.assertEqual(rc, 1)
        self.assertIn('실패', out)

    def test_service_file_default_off(self):
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(here, 'v2', 'deploy', 'livemaster-v2-backup.service'), encoding='utf-8') as f:
            unit = f.read()
        self.assertIn('Environment=LM2_BACKUP_UPLOAD=0', unit)
        self.assertIn('EnvironmentFile=/etc/livemaster.env', unit)          # env 파일의 1 이 0 을 이긴다
        self.assertNotIn('--upload', [l for l in unit.splitlines() if l.startswith('ExecStart')][0])


if __name__ == '__main__':
    unittest.main()
