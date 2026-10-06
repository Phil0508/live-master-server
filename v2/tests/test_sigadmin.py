# -*- coding: utf-8 -*-
"""v2 🎵 시그니처 관리 — 등록 · 고치기 · 지우기(행만) · 되살리기 · 되돌리기 · 같은 금액 묻기 · 목록 새로 받기.

⚠️ 진짜 Supabase 는 절대 부르지 않는다 — sigadmin 의 바깥 함수(sb_* · storage_upload)를 전부 가짜 보관소로 바꾸고,
   혹시 빠뜨려도 어디에도 닿지 않게 SUPABASE_URL 을 닫힌 주소로 돌려 둔다.
"""
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain import sigadmin as sa
from v2.tests.test_flow import PW, SECRET, H

FAKE = 'http://fake-sb.invalid'


class FakeSB:
    """가짜 보관소 — 표(signatures) 하나 · 파일 상자(media) 하나."""

    def __init__(self, rows):
        self.rows = {r['id']: dict(r) for r in rows}
        self.next_id = max(self.rows) + 1
        self.files = {}
        self.fail_upload = False
        self.fail_delete = False
        self.id_insert_ok = True
        self.calls = []

    def list(self):
        return sorted((dict(r) for r in self.rows.values()), key=lambda r: r['amount'])

    def get(self, sid):
        self.calls.append(('get', sid))
        r = self.rows.get(int(sid))
        return dict(r) if r else None

    def insert(self, fields):
        self.calls.append(('insert', dict(fields)))
        f = dict(fields)
        if 'id' in f:
            if not self.id_insert_ok or f['id'] in self.rows:
                raise RuntimeError('보관소가 거절했습니다 (HTTP 409)')
        else:
            f['id'] = self.next_id
            self.next_id += 1
        row = {k: f.get(k) for k in sa.ROW_KEYS}
        self.rows[row['id']] = row
        return dict(row)

    def update(self, sid, fields):
        self.calls.append(('update', sid, dict(fields)))
        self.rows[int(sid)].update(fields)
        return dict(self.rows[int(sid)])

    def delete(self, sid):
        self.calls.append(('delete', sid))
        if self.fail_delete:
            raise RuntimeError('보관소가 거절했습니다 (HTTP 500)')
        self.rows.pop(int(sid), None)
        return True

    def upload(self, path, raw, ctype):
        self.calls.append(('upload', path, ctype))
        if self.fail_upload:
            raise RuntimeError('보관소에 파일을 올리지 못했습니다 (500): 가짜')
        self.files[path] = (raw, ctype)
        return '%s/storage/v1/object/public/media/%s' % (FAKE, path)


def png(w=40, h=20, color=(255, 0, 0)):
    from PIL import Image
    b = io.BytesIO()
    Image.new('RGB', (w, h), color).save(b, format='PNG')
    return b.getvalue()


def gif_anim():
    from PIL import Image
    b = io.BytesIO()
    frames = [Image.new('RGB', (10, 10), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    frames[0].save(b, format='GIF', save_all=True, append_images=frames[1:], duration=100, loop=0)
    return b.getvalue()


class SigAdmin(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {'SUPABASE_URL': 'http://127.0.0.1:9', 'SUPABASE_SECRET_KEY': 'x'})
        self.env.start()
        self.sb = FakeSB([{'id': 1, 'amount': 10300, 'title': '사쿠란보', 'image_url': FAKE + '/a.webp', 'sound_url': FAKE + '/a.mp3', 'duration': 8},
                          {'id': 2, 'amount': 20005, 'title': '뿅뿅', 'image_url': FAKE + '/b.webp', 'sound_url': FAKE + '/b.mp3', 'duration': 9},
                          {'id': 3, 'amount': 50000, 'title': '대박', 'image_url': FAKE + '/c.webp', 'sound_url': FAKE + '/c.mp3', 'duration': 12}])
        self.patches = [mock.patch.object(sa, 'sb_ready', lambda: True),
                        mock.patch.object(sa, 'sb_get', self.sb.get),
                        mock.patch.object(sa, 'sb_insert', self.sb.insert),
                        mock.patch.object(sa, 'sb_update', self.sb.update),
                        mock.patch.object(sa, 'sb_delete', self.sb.delete),
                        mock.patch.object(sa, 'storage_upload', self.sb.upload)]
        for p in self.patches:
            p.start()
        self.dir = tempfile.mkdtemp(prefix='lm2sig_')
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET, sig_fetch=self.sb.list))
        self.c.post('/api/cmd', json={'type': 'session.start', 'data': {'names': ['하율', '서아']}}, headers=H)

    def tearDown(self):
        self.c.app.state.store.close()
        for p in self.patches:
            p.stop()
        self.env.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    # ── 도구 ──
    def add(self, auth=True, **form):
        files = {}
        for k in ('image', 'sound'):
            if k in form:
                files[k] = form.pop(k)
        return self.c.post('/api/signatures/add', data={k: str(v) for k, v in form.items()}, files=files or None,
                           headers=H if auth else {})

    def update(self, sid, **form):
        files = {k: form.pop(k) for k in ('image', 'sound') if k in form}
        return self.c.post('/api/signatures/update/%s' % sid, data={k: str(v) for k, v in form.items()}, files=files or None, headers=H)

    def post(self, path, body):
        return self.c.post(path, json=body, headers=H)

    def log(self):
        return self.c.get('/api/state', headers=H).json()['slices']['sig_admin']

    def listed(self):
        return {r['id']: r for r in self.c.get('/api/signatures', headers=H).json()['signatures']}

    # ── 등록 ──
    def test_add_checks(self):
        self.assertEqual(self.add(auth=False, amount=12000, sound=('a.mp3', b'ID3', 'audio/mpeg')).status_code, 401)
        r = self.add(amount=0, sound=('a.mp3', b'ID3', 'audio/mpeg'))
        self.assertEqual((r.status_code, r.json()['message']), (400, '후원 금액을 입력해주세요.'))
        self.assertEqual(self.add(amount='만원', sound=('a.mp3', b'ID3', 'audio/mpeg')).status_code, 400)
        r = self.add(amount=12000, title='제목')
        self.assertEqual((r.status_code, r.json()['message']), (400, '사진이나 음원 중 하나는 등록해주세요.'))
        self.assertEqual(self.add(amount=12000, sound=('virus.exe', b'MZ', 'application/octet-stream')).status_code, 400)
        self.assertEqual(self.add(amount=12000, image=('note.txt', b'hello', 'text/plain')).status_code, 400)
        self.assertEqual(self.add(amount=12000, duration=0, sound=('a.mp3', b'ID3', 'audio/mpeg')).status_code, 400)
        self.assertEqual(len(self.sb.rows), 3)                                  # 거절은 바깥에 아무것도 안 만든다
        self.assertFalse(any(c[0] in ('insert', 'upload') for c in self.sb.calls))

    def test_add_uploads_and_refreshes_matching(self):
        before = self.log()['ver']
        r = self.add(amount='12,000', image=('p.png', png(3000, 1000), 'image/png'), sound=('s.mp3', b'ID3data', 'application/octet-stream'))
        self.assertEqual(r.status_code, 200, r.text)
        row = r.json()['signature']
        sid = row['id']
        self.assertEqual((row['amount'], row['title'], row['duration']), (12000, '12,000원 시그니처', 10))   # 옛 기본값
        self.assertIn('/media/images/%d.webp?v=' % sid, row['image_url'])                                  # 사진은 WebP
        self.assertIn('/media/sounds/%d.mp3?v=' % sid, row['sound_url'])
        self.assertEqual(self.sb.files['sounds/%d.mp3' % sid][1], 'audio/mpeg')                             # 형식은 확장자로
        from PIL import Image
        im = Image.open(io.BytesIO(self.sb.files['images/%d.webp' % sid][0]))
        self.assertEqual((im.format, max(im.size)), ('WEBP', 1280))                                         # 긴 변 1280
        self.assertIn(sid, self.listed())                                                                   # 서버 목록이 바로 새것
        self.c.post('/api/donation', json={'name': '별빛', 'amount': 11000, 'tx_id': 'toon_x1'}, headers=H)
        q = self.c.get('/api/state', headers=H).json()['slices']['queue']['items']
        self.assertEqual(q[-1]['sig_id'], sid)                                                               # 1.1만 → 1.2만 새 시그
        lg = self.log()
        self.assertEqual((lg['ver'], lg['log'][0]['act'], lg['log'][0]['id']), (before + 1, 'add', sid))

    def test_add_keeps_animated_gif(self):
        r = self.add(amount=15000, title='움짤', image=('m.gif', gif_anim(), 'image/gif'))
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.json()['signature']['id']
        self.assertEqual(self.sb.files['images/%d.gif' % sid][1], 'image/gif')                               # 줄이지 않고 그대로

    def test_add_same_amount_asks(self):
        r = self.add(amount=20005, title='또 뿅', sound=('s.mp3', b'ID3', 'audio/mpeg'))
        self.assertEqual((r.status_code, r.json()['code']), (409, 'dup'))
        self.assertEqual(r.json()['dup'][0]['id'], 2)
        self.assertEqual(len(self.sb.rows), 3)
        r = self.add(amount=20005, title='또 뿅', allow_dup=1, sound=('s.mp3', b'ID3', 'audio/mpeg'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.sb.rows), 4)

    def test_add_upload_fail_removes_row(self):
        self.sb.fail_upload = True
        r = self.add(amount=12000, sound=('s.mp3', b'ID3', 'audio/mpeg'))
        self.assertEqual(r.status_code, 502)
        self.assertEqual(len(self.sb.rows), 3)                                  # 빈 행이 남지 않는다
        self.assertEqual(self.log()['log'], [])

    def test_not_configured(self):
        with mock.patch.object(sa, 'sb_ready', lambda: False):
            self.assertEqual(self.add(amount=12000, sound=('s.mp3', b'ID3', 'audio/mpeg')).status_code, 503)
            self.assertFalse(self.c.get('/api/sigadmin/list', headers=H).json()['configured'])

    def test_too_big(self):
        with mock.patch.object(sa, 'MAX_REQUEST_MB', 0):
            self.assertEqual(self.add(amount=12000, sound=('s.mp3', b'ID3', 'audio/mpeg')).status_code, 413)

    # ── 목록 ──
    def test_list_is_fresh(self):
        self.c.get('/api/signatures', headers=H)                                # 기억해 둔다(10분)
        self.sb.rows[9] = {'id': 9, 'amount': 7000, 'title': '밖에서 넣음', 'image_url': '', 'sound_url': '', 'duration': 10}
        self.assertNotIn(9, self.listed())                                       # 옛 주소는 기억한 목록
        j = self.c.get('/api/sigadmin/list', headers=H).json()
        self.assertTrue(j['configured'])
        self.assertIn(9, [r['id'] for r in j['signatures']])                     # 관리 목록은 새로 받는다
        self.assertEqual(j['floor'], 7000)
        self.assertEqual(self.c.get('/api/sigadmin/list').status_code, 401)

    # ── 고치기 · 되돌리기 ──
    def test_update_and_revert(self):
        old_img = self.sb.rows[2]['image_url']
        r = self.update(2, title='  뿅뿅뿅  ', amount='21,000', image=('n.png', png(), 'image/png'))
        self.assertEqual(r.status_code, 200, r.text)
        row = self.sb.rows[2]
        self.assertEqual((row['title'], row['amount']), ('뿅뿅뿅', 21000))
        self.assertRegex(row['image_url'], r'/media/images/2_v\d+\.webp\?v=')   # 새 이름 — 옛 파일을 덮지 않는다
        self.assertEqual(self.listed()[2]['amount'], 21000)
        e = self.log()['log'][0]
        self.assertEqual((e['act'], e['before']['amount'], e['after']['amount']), ('edit', 20005, 21000))
        r = self.post('/api/sigadmin/revert', {'lid': e['lid']})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((self.sb.rows[2]['title'], self.sb.rows[2]['amount'], self.sb.rows[2]['image_url']), ('뿅뿅', 20005, old_img))
        self.assertEqual(self.listed()[2]['amount'], 20005)
        self.assertEqual(self.post('/api/sigadmin/revert', {'lid': e['lid']}).status_code, 409)       # 두 번은 안 된다
        self.assertEqual(self.log()['log'][0]['act'], 'revert')

    def test_update_checks(self):
        self.assertEqual(self.update(99, title='x').status_code, 404)
        self.assertEqual(self.update(2, amount=-5).status_code, 400)
        r = self.update(2, title='뿅뿅', amount=20005)
        self.assertEqual((r.status_code, r.json()['message']), (200, '변경 사항이 없습니다.'))
        self.assertFalse(any(c[0] == 'update' for c in self.sb.calls))
        r = self.update(2, amount=50000)
        self.assertEqual((r.status_code, r.json()['code']), (409, 'dup'))
        self.assertEqual(self.update(2, amount=50000, allow_dup=1).status_code, 200)

    # ── 지우기 · 되살리기 ──
    def test_delete_keeps_files_and_restores(self):
        r = self.c.post('/api/signatures/delete/2', headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn(2, self.sb.rows)
        self.assertFalse(any(c[0] == 'upload' for c in self.sb.calls))
        self.assertNotIn(2, self.listed())
        e = self.log()['log'][0]
        self.assertEqual((e['act'], e['row']['title'], e['row']['sound_url']), ('delete', '뿅뿅', FAKE + '/b.mp3'))   # 지운 행 전체를 보관
        # 지운 동안 2만 원 후원은 5만 원 시그로 올림
        self.c.post('/api/donation', json={'name': '별빛', 'amount': 20000, 'tx_id': 'toon_d1'}, headers=H)
        self.assertEqual(self.c.get('/api/state', headers=H).json()['slices']['queue']['items'][-1]['sig_id'], 3)
        r = self.post('/api/sigadmin/restore', {'lid': e['lid']})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.sb.rows[2]['title'], '뿅뿅')                       # 같은 번호로
        self.assertEqual(self.sb.rows[2]['sound_url'], FAKE + '/b.mp3')
        self.assertIn(2, self.listed())
        self.assertEqual(self.post('/api/sigadmin/restore', {'lid': e['lid']}).status_code, 409)
        lg = self.log()['log']
        self.assertEqual(lg[0]['act'], 'restore')
        self.assertEqual(next(x for x in lg if x['lid'] == e['lid'])['restored'], 2)

    def test_restore_new_id_when_id_refused(self):
        self.c.post('/api/signatures/delete/3', headers=H)
        self.sb.id_insert_ok = False
        lid = self.log()['log'][0]['lid']
        r = self.post('/api/sigadmin/restore', {'lid': lid})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn('새 번호', r.json()['message'])
        self.assertEqual(sum(1 for x in self.sb.rows.values() if x['title'] == '대박'), 1)        # 두 번 들어가지 않는다

    def test_delete_fail_keeps_row_and_drops_backup(self):
        self.sb.fail_delete = True
        self.assertEqual(self.c.post('/api/signatures/delete/1', headers=H).status_code, 502)
        self.assertIn(1, self.sb.rows)
        self.assertEqual(self.log()['log'], [])
        self.assertEqual(self.c.post('/api/signatures/delete/77', headers=H).status_code, 404)
        self.assertEqual(self.c.post('/api/signatures/delete/1').status_code, 401)

    def test_trash_outlives_log(self):
        self.c.post('/api/signatures/delete/1', headers=H)
        for i in range(sa.LOG_KEEP + 5):
            self.update(3, title='대박 %d' % i)
        lg = self.log()['log']
        self.assertEqual(len(lg), sa.LOG_KEEP + 1)                               # 지운 것은 오래돼도 남는다(되살릴 길)
        self.assertEqual(lg[-1]['act'], 'delete')

    # ── 옛 주소 ──
    def test_old_addresses(self):
        r = self.c.get('/mobile?token=abc', follow_redirects=False)
        self.assertEqual((r.status_code, r.headers['location']), (302, '/controller/'))       # 열쇠를 주소에 남기지 않는다
        r = self.c.get('/upload', follow_redirects=False)
        self.assertEqual((r.status_code, r.headers['location']), (302, '/controller/sig.html'))
        self.assertEqual(self.c.get('/controller/sig.html').status_code, 200)

    def test_log_is_private(self):
        self.c.post('/api/signatures/delete/1', headers=H)
        self.assertNotIn('sig_admin', self.c.get('/api/state').json()['slices'])  # 방송판(로그인 없음)에는 안 간다


if __name__ == '__main__':
    unittest.main()
