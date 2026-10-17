# -*- coding: utf-8 -*-
"""🏷️ 장부 줄 번호 · ↻ 다시 송출(대표님 10-17 '후원 한 건 한 건마다 번호를 붙여서 재송출도 가능하게').

대표님 보충: 번호는 '장부가 헷갈리지 않게 붙이는 임의의 숫자' — 겹치지만 않으면 된다(회차마다 1부터일 필요 없음).
번호로 부르는 기능(Ctrl+K · AI '12번 다시')은 없다. 재송출은 조종실 단추 → 확인 상자 → 방송 화면에만.

① 번호: 들어오는 순간 서버가 붙인다 · 겹치지 않고 이어진다(서버를 다시 켜도) · 같은 tx 재전송 · 12초 중복은 새 번호 없음
   · 예전 줄(칸이 생기기 전)은 켜질 때 들어온 순서대로 매긴다 · 방송판(로그인 없음) 스냅샷엔 번호가 없다
② 다시 송출: 팝업 · 시그니처(encore)만 — 장부 합계 · 대기함 · 점수 · 순위 · 한 방 최고 · 시그 집계 · 월별 · AI 기억 · 자동 진행 고리 그대로
   · 장부엔 'display' 줄 '↻ #N 다시 송출' · 없는 id · 다른 회차 404 · 다시 송출 줄 409 · 로그인 없으면 401
③ 덤: 계좌 카드 [채우기] 안내 글이 실제 단추 글자 '장부에 넣고 송출' 과 같다
"""
import json
import os
import re
import sqlite3
import unittest

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain import ai_cmd
from v2.server.domain import donation as dn
from v2.server.store import Store
from v2.tests.test_flow import Base, H, PW, SECRET, SIGS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def keys_named(obj, key):
    """사전 · 목록을 끝까지 뒤져 그 이름의 칸이 몇 개인지."""
    n = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            n += (k == key) + keys_named(v, key)
    elif isinstance(obj, list):
        for v in obj:
            n += keys_named(v, key)
    return n


class T(Base):
    def rows(self, session='current'):
        return self.c.get('/api/ledger?limit=2000&session=' + session, headers=H).json()

    def replay(self, did, auth=True):
        r = self.c.post('/api/donation/replay', json={'id': did}, headers=H if auth else {})
        return r.status_code, r.json()

    def restart(self):
        path = self.c.app.state.store.path
        self.c.app.state.store.close()
        self.c = TestClient(create_app(db_path=path, password=PW, secret=SECRET, sig_fetch=lambda: SIGS))


# ── ① 번호 ──────────────────────────────────────────────
class Numbers(T):
    def test_numbers_unique_and_continue_after_restart(self):
        self.don('가', 30000, 'toon_n1')
        self.don('나', 5000, 'toon_n2', display_only=True)            # 화면에만 소액도 번호
        self.don('다', 20000, 'manual_n3', trusted=True)                # 손 송출
        self.restart()                                                   # 서버를 다시 켜도
        self.don('라', 10300, 'toon_n4')
        nos = sorted(r['no'] for r in self.rows()['rows'])
        self.assertEqual(nos, [1, 2, 3, 4])                              # 겹치지 않고 이어진다
        db = self.c.app.state.store.db
        with self.assertRaises(sqlite3.IntegrityError):                  # 겹치면 장부가 막는다(UNIQUE)
            db.execute("UPDATE donations SET no = 1 WHERE no = 2")

    def test_duplicates_get_no_new_number(self):
        self.don('가', 30000, 'toon_d1')
        c, r = self.don('가', 30000, 'toon_d1')                          # 같은 tx 재전송
        self.assertEqual(r.get('message'), 'Duplicate donation ignored.')
        self.c.post('/api/donation', json={'name': '나', 'amount': 10000, 'message': '', 'tx_id': ''}, headers=H)
        self.c.post('/api/donation', json={'name': '나', 'amount': 10000, 'message': '', 'tx_id': ''}, headers=H)   # 12초 중복
        self.don('다', 20000, 'toon_d3')
        self.assertEqual(sorted(r['no'] for r in self.rows()['rows']), [1, 2, 3])

    def test_manual_send_answer_has_number_listener_answer_unchanged(self):
        self.don('가', 30000, 'toon_a1')
        c, r = self.don('나', 20000, 'manual_bank_77')
        self.assertEqual((c, r.get('no')), (200, 2))                     # 후원 콘솔 토스트 '#2 로 들어갔어요'
        c, r = self.c.post('/api/donation', json={'name': '다', 'amount': 20000, 'tx_id': 'toon_a3'}).json(), None
        self.assertNotIn('no', c)                                        # 리스너(로그인 없음) 답은 옛 모양 그대로

    def test_broadcast_snapshot_has_no_numbers(self):
        self.don('가', 50000, 'toon_b1')
        self.don('나', 3000, 'toon_b2', display_only=True)
        did = self.rows()['rows'][-1]['id']
        self.replay(did)
        pub = self.st(auth=False)
        self.assertEqual(keys_named(pub, 'no'), 0)
        self.assertEqual(keys_named(pub, 'of_no'), 0)
        dump = json.dumps(pub, ensure_ascii=False)
        self.assertNotIn('다시 송출', dump)                               # 장부 메모('↻ #1 다시 송출')도 안 나간다
        self.assertNotIn('pending', pub)

    def test_old_rows_numbered_in_order_on_open(self):
        path = os.path.join(self.dir, 'old.db')
        db = sqlite3.connect(path)
        db.executescript("""CREATE TABLE donations (id TEXT PRIMARY KEY, tx_id TEXT UNIQUE, at REAL NOT NULL, name TEXT NOT NULL,
            amount INTEGER NOT NULL, message TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
            player TEXT, session TEXT NOT NULL DEFAULT '');""")
        db.executemany('INSERT INTO donations VALUES (?,?,?,?,?,?,?,?,?,?)',
                       [('b', None, 20.0, '둘', 1, '', '', 'archived', None, 's1'), ('a', None, 10.0, '하나', 1, '', '', 'archived', None, 's1')])
        db.commit()
        db.close()
        st = Store(path)
        try:
            self.assertEqual([(r['id'], r['no']) for r in st.db.execute('SELECT id, no FROM donations ORDER BY no')], [('a', 1), ('b', 2)])
            no = st.add_donation({'id': 'c', 'tx_id': None, 'at': 30.0, 'name': '셋', 'amount': 1, 'message': '', 'source': '',
                                  'status': 'pending', 'player': None, 'session': 's2'})
            self.assertEqual(no, 3)
        finally:
            st.close()
        st = Store(path)                                                 # 다시 열어도 그대로
        try:
            self.assertEqual([r['no'] for r in st.db.execute('SELECT no FROM donations ORDER BY no')], [1, 2, 3])
        finally:
            st.close()


# ── ② 다시 송출 ───────────────────────────────────────────
class Replay(T):
    def ledger_total(self):
        return self.rows()['total']

    def monthly_total(self):
        return self.c.get('/api/ranking/monthly', headers=H).json()['total']

    def test_replay_is_screen_only(self):
        self.don('영원', 50000, 'toon_r1', msg='밍밍화이팅')
        did = self.rows()['rows'][0]['id']
        self.cmd('pending.assign', id=self.st()['pending'][0]['id'], name='하율')
        before = self.st()
        base_total, base_month = self.ledger_total(), self.monthly_total()
        seen = []
        dn.AFTER_DONATION.append(lambda ctx, name, amount: seen.append(name))
        dn.ON_ASSIGN.append(lambda *a: seen.append('assign'))
        try:
            c, r = self.replay(did)
        finally:
            dn.AFTER_DONATION.pop()
            dn.ON_ASSIGN.pop()
        self.assertEqual(c, 200, r)
        self.assertEqual((r['of_no'], r['no'], r['title']), (1, 2, '대박'))
        self.assertEqual(seen, [])                                       # 등급 · 자동 진행 · 기억 고리 안 탐
        s = self.st()
        self.assertEqual(s['pending'], before['pending'])                # 대기함 그대로
        self.assertEqual(s['players'], before['players'])                # 점수 그대로
        self.assertEqual(s['tallies']['donors'], before['tallies']['donors'])   # 후원 순위
        self.assertEqual(s['tallies']['best'], before['tallies']['best'])       # 한 방 최고
        self.assertEqual(s['tallies']['sigs'], before['tallies']['sigs'])       # 시그 집계
        self.assertEqual(self.ledger_total(), base_total)                # 정산 합계
        self.assertEqual(self.monthly_total(), base_month)               # 월별 순위
        # 화면 신호만 — 팝업 · 시그니처 대기줄(encore, 묶이지 않음)
        pop = s['popup']['donation']
        self.assertEqual((pop['name'], pop['amount'], pop['message'], pop.get('encore')), ('영원', 50000, '밍밍화이팅', True))
        q = [x for x in s['queue']['items'] if x.get('encore')]
        self.assertEqual([(x['title'], x['donator'], x['count']) for x in q], [('대박', '영원', 1)])
        # 장부엔 화면만 줄 하나
        row = next(x for x in self.rows()['rows'] if x['no'] == 2)
        self.assertEqual((row['status'], row['source'], row['message'], row['player']), ('display', 'replay', '↻ #1 다시 송출', None))
        settle = self.c.get('/api/ledger/settle', headers=H).json()['settle']
        self.assertEqual(settle['real'], 50000)                          # 정산 차액에도 안 든다

    def test_replay_twice_does_not_bundle(self):
        self.don('영원', 50000, 'toon_r2')
        did = self.rows()['rows'][0]['id']
        self.replay(did)
        self.replay(did)
        q = [x for x in self.st()['queue']['items'] if x.get('encore')]
        self.assertEqual([x['count'] for x in q], [1, 1])

    def test_small_replay_goes_to_strip(self):
        self.don('작은손', 3000, 'toon_s1', display_only=True)
        did = self.rows()['rows'][0]['id']
        c, r = self.replay(did)
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertTrue(s['popup']['donation']['display_only'])
        self.assertFalse(any(x.get('encore') for x in s['queue']['items']))

    def test_reject_unknown_other_session_replay_row_and_unauthed(self):
        c, r = self.replay('don_nope')
        self.assertEqual(c, 404)
        self.assertIn('그런 후원이 없어요', r['message'])
        self.don('지난', 30000, 'toon_o1')
        old = self.rows()['rows'][0]['id']
        self.cmd('session.end')
        self.cmd('session.start', names=['하율'])
        c, r = self.replay(old)                                          # 다른 회차
        self.assertEqual(c, 404)
        self.don('이번', 30000, 'toon_o2')
        cur = self.rows()['rows'][0]['id']
        c, r = self.replay(cur, auth=False)
        self.assertEqual(c, 401)
        c, r = self.c.post('/api/cmd', json={'type': 'donation.replay', 'data': {'id': cur}}).status_code, None
        self.assertEqual(c, 401)
        c, r = self.replay(cur)
        rep = next(x for x in self.rows()['rows'] if x['source'] == 'replay')['id']
        c, r = self.replay(rep)                                          # 다시 송출한 줄을 또 다시 송출
        self.assertEqual(c, 409)

    def test_replay_without_signature_list_still_shows_popup(self):
        self.don('영원', 50000, 'toon_p1')
        did = self.rows()['rows'][0]['id']
        c, r = self.cmd('donation.replay', id=did)                       # 시그니처 없이(명령 바로) — 팝업만
        self.assertEqual(c, 200, r)
        self.assertTrue(self.st()['popup']['donation']['encore'])

    def test_not_callable_by_number_through_ai(self):
        """대표님 보충: 번호로 부르는 기능은 없다 — AI 허용 목록에도 없다."""
        self.assertNotIn('donation.replay', ai_cmd.ALLOW)


# ── ③ 덤 · 조종실 파일 ─────────────────────────────────────
class Controller(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
            return f.read()

    def test_bank_fill_hint_matches_button(self):
        src = self.read('v2/web/controller/js/panels/ops/bank.js')
        self.assertFalse("'채웠어요 — 확인하고 [시그니처 송출]'" in src, '단추 글자와 다른 옛 안내 글')
        self.assertTrue("form.ledger.checked ? '장부에 넣고 송출' : '시그니처 송출'" in src)
        con = self.read('v2/web/controller/js/panels/ops/console.js')
        self.assertTrue("'장부에 넣고 송출'" in con)                     # 실제 단추 글자

    def test_no_confirm_builtin_in_replay(self):
        src = self.read('v2/web/controller/js/replay.js')
        self.assertIsNone(re.search(r'(?<![.\w])confirm\(|window\.confirm', src.split('*/', 1)[1]))   # 머리 설명 글은 빼고 본다
        self.assertIn('ctx.confirm(', src)
        self.assertIn('/api/donation/replay', src)


if __name__ == '__main__':
    unittest.main()
