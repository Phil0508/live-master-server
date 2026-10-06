# -*- coding: utf-8 -*-
"""v2 운영 더하기 — ✂️ 클립 · 🎛️ 스트림덱 · 📊 클릭 기록 · 🗓️ 월별 순위(옛 features/clip · streamdeck · uistats · archive 규칙).

돌리기(저장소 루트에서): python -m unittest v2.tests.test_more
"""
import datetime
import io
import os
import shutil
import tempfile
import time
import unittest
import zipfile

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain import monthly as mo
from v2.server.domain import uistats as ui

PW, SECRET = 'testpw', 'testsecret-0123456789'
H = {'Authorization': 'Bearer ' + SECRET}
SIGS = ([{'id': 100 + i, 'amount': 10000 + i * 1000, 'title': '카드%02d' % i, 'image_url': 'c%02d.png' % i,
          'sound_url': 'c%02d.mp3' % i, 'duration': 8} for i in range(1, 21)]
        + [{'id': 900, 'amount': 100000, 'title': '대박', 'image_url': 'big.png', 'sound_url': 'big.mp3', 'duration': 12}])
KST = datetime.timezone(datetime.timedelta(hours=9))


def kst(*a):
    return datetime.datetime(*a, tzinfo=KST).timestamp()


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2more_')
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET,
                                       sig_fetch=lambda: SIGS))
        self.cmd('session.start', names=['하율', '서아'])

    def tearDown(self):
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def cmd(self, t, **data):
        r = self.c.post('/api/cmd', json={'type': t, 'data': data}, headers=H)
        return r.status_code, r.json()

    def st(self, auth=True):
        return self.c.get('/api/state', headers=H if auth else {}).json()['slices']

    def don(self, name, amount, tx):
        r = self.c.post('/api/donation', json={'name': name, 'amount': amount, 'message': '', 'tx_id': tx}, headers=H)
        return r.status_code, r.json()

    def log(self):
        return self.st()['clip_log']['log']

    def hello(self, **b):
        return self.c.post('/api/clip/hello', json=b).json()


class Clip(Base):
    def test_slices_public_private(self):
        pub = self.st(auth=False)
        self.assertIn('clip', pub)                                   # 방송판은 설정 · 조종실 신호만 본다
        self.assertNotIn('clip_log', pub)
        self.assertNotIn('clip_key', pub)
        self.assertNotIn('clip_key', self.st())                      # 숨김 — 조종실에도 안 간다
        self.assertEqual((pub['clip']['auto'], pub['clip']['auto_min'], pub['clip']['ask']), (True, 100000, None))

    def test_now_logs_and_asks(self):
        c, r = self.cmd('clip.now')
        self.assertEqual(c, 200)
        self.assertFalse(r['obs']['alive'])                           # 방송판이 아직 안 알렸다
        s = self.st()
        self.assertEqual(s['clip']['ask']['id'], r['id'])
        self.assertEqual(s['clip']['ask']['delay_ms'], 0)
        row = s['clip_log']['log'][-1]
        self.assertEqual((row['kind'], row['label'], row['ref'], row['saved_at']), ('manual', '✂ 직접 누름', r['id'], 0))
        c, r2 = self.cmd('clip.now', label='  첫  골\n', delay_ms=999999)
        self.assertEqual(self.st()['clip']['ask']['delay_ms'], 60000)   # 60초까지
        self.assertEqual(self.log()[-1]['label'], '첫 골')
        self.assertEqual(self.c.post('/api/cmd', json={'type': 'clip.now', 'data': {}}).status_code, 401)

    def test_log_max_60(self):
        for i in range(65):
            self.cmd('clip.now', label='n%d' % i)
        log = self.log()
        self.assertEqual(len(log), 60)
        self.assertEqual(log[0]['label'], 'n5')

    def test_big_sig_logged_once(self):
        self.don('별빛', 100000, 'toon_b1')
        q = self.st()['queue']['items']
        log = self.log()
        self.assertEqual(len(log), 1)
        self.assertEqual((log[0]['kind'], log[0]['ref']), ('auto', q[-1]['id']))
        self.assertEqual(log[0]['label'], '별빛 100,000원 대박')
        self.don('별빛', 100000, 'toon_b2')                             # 같은 사람 · 같은 시그 → ×2 로 묶임 → 한 줄로 충분
        self.assertEqual(self.st()['queue']['items'][-1]['count'], 2)
        self.assertEqual(len(self.log()), 1)
        self.don('달빛', 50000, 'toon_b3')                              # 기준 미만
        self.assertEqual(len(self.log()), 1)
        self.cmd('reaction.skip')                                        # 대기줄에서 빠지는 것은 순간이 아니다
        self.assertEqual(len(self.log()), 1)

    def test_auto_off_and_threshold(self):
        self.cmd('clip.settings', auto=False)
        self.don('별빛', 100000, 'toon_c1')
        self.assertEqual(self.log(), [])
        self.cmd('clip.settings', auto=True, auto_min=50000)
        self.don('달빛', 50000, 'toon_c2')
        self.assertEqual(len(self.log()), 1)
        self.cmd('clip.settings', auto_min='abc')                        # 이상한 값 → 기본 10만
        self.assertEqual(self.st()['clip']['auto_min'], 100000)
        self.cmd('clip.settings', auto_min=-5)
        self.assertEqual(self.st()['clip']['auto_min'], 0)
        self.cmd('clip.settings', auto_min=0)
        self.don('해빛', 900000, 'toon_c3')                              # 기준 0 = 저절로 안 함(방송판도 같다)
        self.assertEqual(len(self.log()), 1)

    def test_allclear_logged(self):
        self.assertEqual(self.c.post('/api/siggame/picks', json={'picks': [s['id'] for s in SIGS[:16]]}, headers=H).status_code, 200)
        self.assertEqual(self.cmd('sig.deal', minutes=10, target=5)[0], 200)
        for cid in (1, 2, 3, 4, 5):
            self.cmd('sig.flip', id=cid)
        self.assertEqual(self.cmd('sig.allclear')[0], 200)
        ts = self.st()['siggame']['action']['ts']
        row = self.log()[-1]
        self.assertEqual((row['kind'], row['ref'], row['label']), ('auto', 'allclear:%d' % ts, '시그뒤집기 올클리어 (5장)'))
        self.cmd('clip.settings', auto=False)
        n = len(self.log())
        self.cmd('sig.allclear')
        self.assertEqual(len(self.log()), n)

    def test_settings_rename_clear(self):
        _, r = self.cmd('clip.now')
        self.cmd('clip.settings', name_fmt='{번호} {제목}\n')
        self.assertEqual(self.st()['clip_log']['name_fmt'], '{번호} {제목}')
        self.cmd('clip.settings', name_fmt='   ')
        self.assertEqual(self.st()['clip_log']['name_fmt'], '{날짜} {시각} {제목}')
        self.assertEqual(self.cmd('clip.rename', id=r['id'], name='  밍밍\n VIP ')[0], 200)
        self.assertEqual(self.log()[-1]['name'], '밍밍 VIP')
        self.assertEqual(self.cmd('clip.rename', id='nope', name='x')[0], 404)
        self.cmd('clip.settings', clear=True)
        self.assertEqual(self.log(), [])

    def test_hello_and_saved(self):
        self.assertEqual(self.c.get('/api/clip').status_code, 401)
        _, r = self.cmd('clip.now')
        self.don('별빛', 100000, 'toon_h1')
        qid = self.st()['queue']['items'][-1]['id']
        # 권한 낮은 방송판의 '저장됨' 은 안 믿는다
        self.hello(level=2, rb=True, saved=True, refs=[r['id']])
        self.assertTrue(all(not x['saved_at'] for x in self.log()))
        # 권한 있는 방송판 — 열쇠가 맞는 줄만 · 없는 열쇠는 무시
        self.hello(level=4, rb=True, saved=True, refs=[r['id'], 'nope', {'x': 1}])
        log = self.log()
        self.assertTrue(log[0]['saved_at'] > 0)
        self.assertEqual(log[1]['saved_at'], 0)
        first = log[0]['saved_at']
        self.hello(level=4, rb=True, saved=True, refs=[qid, r['id']])     # 대기줄 id(ref) 로도 · 이미 적힌 줄은 그대로
        log = self.log()
        self.assertTrue(log[1]['saved_at'] > 0)
        self.assertEqual(log[0]['saved_at'], first)
        o = self.c.get('/api/clip', headers=H).json()['obs']
        self.assertEqual((o['alive'], o['level'], o['rb']), (True, 4, True))
        self.assertIsNotNone(o['saved_ago'])
        # 90초 안에 권한 낮은 방송판이 알려 와도 높은 쪽을 그대로 믿는다
        self.assertTrue(self.hello(level=0, rb=False).get('kept'))
        self.assertEqual(self.c.get('/api/clip', headers=H).json()['obs']['level'], 4)
        # 맞는 줄이 없는 '저장됨' 은 장부(events)에 아무것도 안 남긴다(로그인 없는 길)
        seq = self.c.get('/api/state', headers=H).json()['seq']
        self.hello(level=4, rb=True, saved=True, refs=['nope', r['id']])           # r['id'] 는 이미 적혀 있다
        self.assertEqual(self.c.get('/api/state', headers=H).json()['seq'], seq)
        # 이상한 몸통도 터지지 않는다
        self.assertEqual(self.c.post('/api/clip/hello', content=b'not json').status_code, 200)
        self.assertEqual(self.c.post('/api/clip/hello', json=[1, 2]).status_code, 200)

    def test_feed_and_helper_zip(self):
        self.cmd('clip.now', label='첫 골')
        self.assertEqual(self.c.get('/api/clip/feed').status_code, 401)
        self.assertEqual(self.c.get('/api/clip/feed?k=wrong').status_code, 401)
        self.assertEqual(self.c.get('/api/clip/helper.zip').status_code, 401)
        r = self.c.get('/api/clip/helper.zip', headers=dict(H, Host='127.0.0.1:5300'))     # 이 PC 주소면 http 그대로
        self.assertEqual(r.status_code, 200)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = sorted(z.namelist())
        self.assertIn('shorts_clip_helper/clip_helper.ps1', names)
        self.assertIn('shorts_clip_helper/start_clip_helper.bat', names)
        ps = z.read('shorts_clip_helper/clip_helper.ps1')
        self.assertTrue(ps.startswith(b'\xef\xbb\xbf'))                        # PowerShell 5.1 은 BOM 이 있어야 한글을 읽는다
        txt = ps.decode('utf-8-sig')
        self.assertNotIn('__SERVER__', txt)
        self.assertNotIn('__FEEDKEY__', txt)
        self.assertNotIn(SECRET, txt)                                           # 관리자 열쇠는 절대 안 박는다
        self.assertIn("$Server = 'http://127.0.0.1:5300'", txt)
        self.assertNotIn('\n', txt.replace('\r\n', ''))                         # 줄 끝은 CRLF
        key = txt.split("$FeedKey = '", 1)[1].split("'", 1)[0]
        self.assertGreater(len(key), 16)
        f = self.c.get('/api/clip/feed?k=' + key).json()
        self.assertEqual(f['clip']['log'][-1]['label'], '첫 골')
        self.assertNotIn('ref', f['clip']['log'][-1])
        self.assertIn('server_time', f)
        self.assertEqual(f['clip']['name_fmt'], '{날짜} {시각} {제목}')
        # 다시 받아도 열쇠는 그대로(켜 둔 도우미가 안 끊긴다) · 새로 만들면 옛 열쇠는 안 먹는다
        z2 = zipfile.ZipFile(io.BytesIO(self.c.get('/api/clip/helper.zip', headers=H).content))
        self.assertIn(key, z2.read('shorts_clip_helper/clip_helper.ps1').decode('utf-8-sig'))
        self.cmd('clip.feed_key', renew=True)
        self.assertEqual(self.c.get('/api/clip/feed?k=' + key).status_code, 401)
        # 바깥 주소로 받으면 https
        r = self.c.get('/api/clip/helper.zip', headers=dict(H, **{'X-Forwarded-Host': 'live.example.com', 'X-Forwarded-Proto': 'http'}))
        txt = zipfile.ZipFile(io.BytesIO(r.content)).read('shorts_clip_helper/clip_helper.ps1').decode('utf-8-sig')
        self.assertIn("$Server = 'https://live.example.com'", txt)


class StreamDeck(Base):
    def test_auth(self):
        for a in ('clip', 'skip', 'pause', 'save', 'neon'):
            self.assertEqual(self.c.get('/api/streamdeck/' + a).status_code, 401, a)

    def test_actions(self):
        r = self.c.get('/api/streamdeck/clip?token=' + SECRET)                   # 스트림덱 'Website' 단추 — 주소에 열쇠
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'success')
        self.assertEqual(self.st()['clip_log']['log'][-1]['label'], '🎛 스트림덱')
        self.assertEqual(self.c.get('/api/streamdeck/clip?label=골!', headers=H).status_code, 200)
        self.assertEqual(self.st()['clip_log']['log'][-1]['label'], '골!')
        r = self.c.get('/api/streamdeck/skip', headers=H)                         # 틀 것이 없다
        self.assertEqual((r.status_code, r.json()['status']), (404, 'error'))
        self.don('별빛', 50000, 'toon_s1')
        self.assertEqual(len(self.st()['queue']['items']), 1)
        self.assertEqual(self.c.get('/api/streamdeck/skip', headers=H).status_code, 200)
        self.assertEqual(self.st()['queue']['items'], [])
        r = self.c.get('/api/streamdeck/pause', headers=H).json()                 # 뒤집기
        self.assertTrue(self.st()['queue']['paused'])
        self.assertIn('멈췄', r['message'])
        self.c.get('/api/streamdeck/pause?on=1', headers=H)
        self.assertTrue(self.st()['queue']['paused'])
        r = self.c.get('/api/streamdeck/pause?on=0', headers=H).json()
        self.assertFalse(self.st()['queue']['paused'])
        self.assertIn('다시', r['message'])
        for a in ('save',):                                                      # 💡 neon 은 이제 조명(test_lights)
            r = self.c.get('/api/streamdeck/%s?color=RAINBOW' % a, headers=H)
            self.assertEqual(r.status_code, 410)
            self.assertTrue(r.json()['message'])

    def test_page(self):
        r = self.c.get('/streamdeck/')
        self.assertEqual(r.status_code, 200)
        self.assertIn("'/api/streamdeck/'", r.text)
        self.assertIn('data-act="clip"', r.text)


class UiStats(Base):
    def post(self, counts, auth=True):
        return self.c.post('/api/uistats', json={'counts': counts}, headers=H if auth else {})

    def test_add_and_read(self):
        self.assertEqual(self.post([{'key': 'a', 'n': 1}], auth=False).status_code, 401)
        self.assertEqual(self.c.get('/api/uistats').status_code, 401)
        self.assertEqual(self.c.post('/api/uistats', json={'counts': 'x'}, headers=H).status_code, 400)
        r = self.post([{'key': 'tab:ledger', 'label': '탭: 장부', 'tab': 'tabbar', 'n': 3},
                       {'key': 'pending|무시', 'label': '무시', 'tab': 'pending', 'n': 2},
                       {'key': '', 'n': 5}, {'key': 'zero', 'n': 0}, 'junk', {'key': 'big', 'n': 99999}]).json()
        self.assertEqual(r['saved'], 3)
        sid = self.st()['session']['id']
        self.assertEqual(r['session'], sid)
        self.post([{'key': 'tab:ledger', 'label': '탭: 장부', 'tab': 'tabbar', 'n': 2}])
        rows = self.c.get('/api/uistats?session=' + sid, headers=H).json()['rows']
        self.assertEqual([(x['key'], x['n']) for x in rows], [('big', 5000), ('tab:ledger', 5), ('pending|무시', 2)])
        lst = self.c.get('/api/uistats', headers=H).json()
        self.assertEqual(lst['now'], sid)
        self.assertEqual((lst['sessions'][0]['session'], lst['sessions'][0]['total'], lst['sessions'][0]['kinds']), (sid, 5007, 3))
        # 방송이 끝나면 '방송 밖 + 날짜' 로 따로 쌓인다
        self.cmd('session.end')
        r = self.post([{'key': 'x', 'n': 1}]).json()
        self.assertTrue(r['session'].startswith('off-'))
        self.assertEqual(len(self.c.get('/api/uistats', headers=H).json()['sessions']), 2)

    def test_caps(self):
        r = self.post([{'key': 'k%03d' % i, 'n': 1} for i in range(250)]).json()
        self.assertEqual(r['saved'], ui.UI_CLICK_MAX_KEYS)
        long = self.post([{'key': 'x' * 200, 'label': 'y' * 200, 'tab': 'z' * 200, 'n': 1}]).json()
        self.assertEqual(long['saved'], 1)
        rows = self.c.get('/api/uistats?session=' + self.st()['session']['id'], headers=H).json()['rows']
        hit = next(x for x in rows if x['key'].startswith('xxx'))
        self.assertEqual((len(hit['key']), len(hit['label']), len(hit['tab'])), (80, 60, 30))


class Monthly(Base):
    def test_window(self):
        self.assertIsNone(mo.bc_day(kst(2026, 10, 7, 16, 59, 59)))                 # 수 16:59 — 창 밖
        self.assertEqual(str(mo.bc_day(kst(2026, 10, 7, 17, 0))), '2026-10-07')    # 수 17:00 정각 — 창 안
        self.assertEqual(str(mo.bc_day(kst(2026, 10, 8, 2, 59, 59))), '2026-10-07')  # 목 새벽 → 수요일에 붙는다
        self.assertIsNone(mo.bc_day(kst(2026, 10, 8, 3, 0)))                        # 목 03:00 정각 — 창 밖
        self.assertIsNone(mo.bc_day(kst(2026, 10, 6, 21, 0)))                       # 화요일
        self.assertIsNone(mo.bc_day('x'))

    def test_month_split(self):
        rows = [(kst(2026, 9, 30, 23, 0), '홍길동', 10000),          # 수 9/30 밤
                (kst(2026, 10, 1, 1, 0), '홍길동님', 20000),         # 목 10/1 새벽 → 9월 방송
                (kst(2026, 10, 7, 20, 0), '철수', 50000),
                (kst(2026, 10, 7, 21, 0), '익명', 90000),            # 익명은 사람이 아니다
                (kst(2026, 10, 7, 22, 0), '뺀사람', 80000),
                (kst(2026, 10, 8, 12, 0), '철수', 70000)]            # 목 낮 — 창 밖
        month, out, months = mo.monthly(rows, {'뺀사람'})
        self.assertEqual((month, months), ('2026-10', ['2026-10', '2026-09']))
        self.assertEqual([(r['name'], r['total'], r['count'], r['days']) for r in out], [('철수', 50000, 1, 1)])
        month, out, _ = mo.monthly(rows, set(), '2026-09')
        self.assertEqual([(r['name'], r['total'], r['count'], r['days']) for r in out], [('홍길동', 30000, 2, 1)])
        month, out, months = mo.monthly([], set())
        self.assertEqual((out, months), ([], []))
        self.assertRegex(month, r'^\d{4}-\d{2}$')

    def test_route(self):
        self.assertEqual(self.c.get('/api/ranking/monthly').status_code, 401)
        self.assertEqual(self.c.get('/api/ranking/monthly?month=2026-13', headers=H).status_code, 400)
        db = self.c.app.state.store.db
        rows = [('d1', kst(2026, 9, 2, 20, 0), '별빛', 30000, 'assigned'),
                ('d2', kst(2026, 9, 9, 20, 0), '별빛님', 20000, 'ignored'),
                ('d3', kst(2026, 9, 9, 21, 0), '달빛', 40000, 'pending'),
                ('d4', kst(2026, 9, 9, 21, 5), '달빛', 5000, 'display'),       # 화면에만 — 장부 합계 밖
                ('d5', kst(2026, 9, 9, 21, 6), '뺀이름', 900000, 'assigned'),
                ('d6', kst(2026, 8, 5, 20, 0), '옛날', 10000, 'assigned'),
                ('d7', kst(2026, 9, 17, 1, 0), '별빛', 10000, 'archived')]     # 옛 프로그램에서 옮겨 온 장부도 센다(rules.COUNTED)
        for did, at, name, amt, st in rows:
            db.execute("INSERT INTO donations(id, tx_id, at, name, amount, message, source, status, player, session) "
                       "VALUES(?, ?, ?, ?, ?, '', 'toonation', ?, NULL, 's1')", (did, did, at, name, amt, st))
        self.cmd('donor.exclude', name='뺀이름')
        j = self.c.get('/api/ranking/monthly', headers=H).json()
        self.assertEqual((j['month'], j['months'], j['total']), ('2026-09', ['2026-09', '2026-08'], 100000))
        self.assertEqual([(r['name'], r['total'], r['count'], r['days']) for r in j['rows']],
                         [('별빛', 60000, 3, 3), ('달빛', 40000, 1, 1)])
        self.assertEqual(j['window'], '수요일 17:00 ~ 목요일 03:00')
        j = self.c.get('/api/ranking/monthly?month=2026-08', headers=H).json()
        self.assertEqual([r['name'] for r in j['rows']], ['옛날'])
        j = self.c.get('/api/ranking/monthly?month=2025-01', headers=H).json()
        self.assertEqual((j['rows'], j['total']), ([], 0))


if __name__ == '__main__':
    unittest.main()
