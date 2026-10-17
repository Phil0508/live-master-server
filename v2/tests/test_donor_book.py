# -*- coding: utf-8 -*-
"""📒 후원자 장부 — 카드 · 묶기/풀기 · 제안 · 딱지 경계 · 고리(배정 → 정답지 · 되돌리기 · 다시 주기) · 실패해도 점수 · 비공개 · 실명 없음.

돌리기(저장소 루트에서): python -m unittest v2.tests.test_donor_book
"""
import json
import sqlite3
import time
import unittest
from unittest import mock

from v2.server.domain import bank_learn as bl
from v2.server.domain import donor_book as book
from v2.server.domain import donor_memory as dm
from v2.server.state import is_public
from v2.tests.test_autopilot import AutoBase
from v2.tests.test_flow import Base, H

KEY_A = '0123456789abcdef'
KEY_B = 'fedcba9876543210'


class BookBase(Base):
    def db(self):
        return self.c.app.state.store.db

    def give(self, name, amount=10000, tx=None, msg='', **kw):
        c, r = self.don(name, amount, tx or 'toon_%d' % time.time_ns(), msg, **kw)
        self.assertEqual(c, 200, r)
        return r.get('id')

    def assign(self, did, name):
        c, r = self.cmd('pending.assign', id=did, name=name)
        self.assertEqual(c, 200, r)
        self.assertTrue(r['ok'], r)
        return r

    def pid(self, name):
        return book.pid_of(self.db(), name)

    def ans(self, ref):
        r = self.db().execute('SELECT * FROM answer_log WHERE ref = ?', (ref,)).fetchone()
        return dict(r) if r else None

    def remember(self, donor, player, times):
        store = self.c.app.state.store
        for i in range(times):
            dm.remember_assignment(store, donor, player, 1, '', ref='t_%s_%d' % (player, i), at=1000 + i)

    def get(self, path):
        r = self.c.get(path, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


# ══ 카드 · 묶기 · 풀기 · 제안 ══
class Cards(BookBase):
    def test_new_donation_makes_card_once(self):
        self.give('별빛님')
        self.give('별빛')
        pid = self.pid('별빛')
        self.assertTrue(pid and pid.startswith('p_'))
        self.assertEqual(self.db().execute('SELECT n FROM donor_alias WHERE name = ?', ('별빛',)).fetchone()[0], 2)
        self.assertEqual(self.st()['donor_tags']['별빛']['tag'], 'new')

    def test_no_card_for_anonymous_test_or_score_fix(self):
        self.give('익명')
        self.give('1111')
        self.give('Player 1')
        self.give('달빛', tx='toon_t2_x1')                    # 시험 후원
        self.give('해빛', amount=0)
        for n in ('익명', 'Player 1', '달빛', '해빛'):
            self.assertIsNone(self.pid(n), n)
        # 숫자만 이름은 카드를 만든다 — 진짜 큰돈일 수 있다('12' = 431만 원). 화면엔 '시험 의심' 으로만(10-17 합치며)
        self.assertIsNotNone(self.pid('1111'))

    def test_same_key_suggests_but_never_merges(self):
        self.give('영원', donor_key=KEY_A)
        self.give('존잘영원', donor_key=KEY_A)
        self.give('남남', donor_key=KEY_B)
        a, b = self.pid('영원'), self.pid('존잘영원')
        self.assertNotEqual(a, b)                             # 자동으로 안 묶는다(대표님)
        rows = self.get('/api/donors/suggest')['rows']
        self.assertEqual([(r['why'], {r['a'], r['b']}) for r in rows], [('key', {a, b})])
        self.assertNotIn(self.pid('남남'), {rows[0]['a'], rows[0]['b']})

    def test_merge_then_split(self):
        self.give('영원', donor_key=KEY_A)
        self.give('존잘영원', donor_key=KEY_A)
        a, b = self.pid('영원'), self.pid('존잘영원')
        c, r = self.cmd('donor.merge', a=a, b=b)
        self.assertEqual(c, 200, r)
        self.assertEqual((self.pid('영원'), self.pid('존잘영원')), (a, a))
        self.assertEqual(self.get('/api/donors/suggest')['count'], 0)       # 그 제안은 merged
        p = self.get('/api/donors/person/' + a)
        self.assertEqual(sorted(x['name'] for x in p['names']), ['영원', '존잘영원'])
        self.assertEqual(self.st()['donor_tags']['존잘영원']['pid'], a)
        c, r = self.cmd('donor.split', name='존잘영원')
        self.assertEqual(c, 200, r)
        new = r['pid']
        self.assertNotEqual(new, a)
        self.assertEqual(self.pid('존잘영원'), new)
        self.assertEqual(self.st()['donor_tags']['존잘영원']['pid'], new)
        c, r = self.cmd('donor.split', name='영원')                         # 혼자 남은 카드는 못 뗀다
        self.assertEqual(c, 409, r)
        # 다시 채우기를 해도 푼 짝을 또 제안하지 않는다
        self.cmd('donor.rebuild')
        self.assertEqual(self.get('/api/donors/suggest')['count'], 0)

    def test_reject_suggestion_stays_rejected(self):
        self.give('영원', donor_key=KEY_A)
        self.give('존잘영원', donor_key=KEY_A)
        sid = self.get('/api/donors/suggest')['rows'][0]['id']
        c, r = self.cmd('donor.suggest_reject', id=sid)
        self.assertEqual(c, 200, r)
        self.assertEqual(self.get('/api/donors/suggest')['count'], 0)
        self.assertEqual(self.cmd('donor.suggest_reject', id=sid)[0], 409)
        self.give('영원', donor_key=KEY_A)                                   # 같은 번호표가 또 와도
        self.cmd('donor.rebuild')
        self.assertEqual(self.get('/api/donors/suggest')['count'], 0)
        self.assertNotEqual(self.pid('영원'), self.pid('존잘영원'))

    def test_merge_moves_other_suggestions(self):
        self.give('가나', donor_key=KEY_A)
        self.give('다라', donor_key=KEY_A)
        self.give('마바', donor_key=KEY_A)
        a, b, c3 = self.pid('가나'), self.pid('다라'), self.pid('마바')
        self.cmd('donor.merge', a=a, b=b)
        rows = self.get('/api/donors/suggest')['rows']
        self.assertTrue(all(b not in (r['a'], r['b']) for r in rows))
        self.assertIn(frozenset((a, c3)), {frozenset((r['a'], r['b'])) for r in rows})

    def test_pin_off_by_default(self):
        self.give('별빛')
        self.assertFalse(book.PIN_ON)
        c, r = self.cmd('donor.pin', pid=self.pid('별빛'), player='서아')
        self.assertEqual(c, 409, r)
        with mock.patch.object(book, 'PIN_ON', True):
            c, r = self.cmd('donor.pin', pid=self.pid('별빛'), player='서아')
            self.assertEqual(c, 200, r)
            self.assertEqual(self.st()['donor_tags']['별빛'][ 'tag'], 'pin')
            self.assertTrue(self.get('/api/donors/book')['pin_on'])

    def test_mark_test_hides_card(self):
        self.give('별빛')
        pid = self.pid('별빛')
        self.cmd('donor.mark_test', pid=pid, test=True)
        self.assertNotIn('별빛', self.st()['donor_tags'])
        self.assertNotIn(pid, [p['pid'] for p in self.get('/api/donors/book')['persons']])
        self.assertIn(pid, [p['pid'] for p in self.get('/api/donors/book?all=1')['persons']])
        self.cmd('donor.note', pid=pid, note='대표님 친구')
        self.assertEqual(self.get('/api/donors/person/' + pid)['note'], '대표님 친구')

    def test_routes_need_login(self):
        for p in ('/api/donors/book', '/api/donors/suggest', '/api/donors/person/p_0000000000'):
            self.assertEqual(self.c.get(p).status_code, 401, p)
        self.assertEqual(self.c.get('/api/donors/person/p_nope', headers=H).status_code, 404)


# ══ 딱지 경계 ══
class Tags(BookBase):
    def test_tag_of_boundaries(self):
        self.assertEqual(book.tag_of({'A': 90, 'B': 10})[0], 'main')       # 90%
        self.assertEqual(book.tag_of({'A': 89, 'B': 11})[0], 'lean')       # 89%
        self.assertEqual(book.tag_of({'A': 5})[0], 'main')                  # 5번 100%
        self.assertEqual(book.tag_of({'A': 4})[0], 'lean')                  # 4번 100% — 3~4번이면 lean
        self.assertEqual(book.tag_of({'A': 2})[0], 'new')
        self.assertEqual(book.tag_of({'A': 3, 'B': 2})[0], 'lean')          # 60%
        self.assertEqual(book.tag_of({'A': 2, 'B': 2})[0], 'multi')
        self.assertEqual(book.tag_of({})[0], 'new')

    def test_card_tags_from_memory_and_roster(self):
        self.give('별빛')
        self.remember('별빛', '서아', 4)
        self.cmd('donor.rebuild')
        self.assertEqual(self.st()['donor_tags']['별빛']['tag'], 'lean')    # 4번
        self.remember('별빛', '서아', 1)
        self.cmd('donor.rebuild')
        t = self.st()['donor_tags']['별빛']
        self.assertEqual((t['tag'], t['player'], t['n'], t['share']), ('main', '서아', 5, 1.0))
        self.remember('별빛', '고수달', 9)                                   # 명단에 없는 선수(기억 5번 넘어도 이번 판 밖) …
        self.remember('별빛', 'Player 2', 9)                                # 시험 이름 선수는 언제나 뺀다
        st = self.st()
        roster = book.roster(self.db(), st['players'])
        self.assertNotIn('Player 2', roster)
        self.cmd('donor.rebuild')
        t = self.st()['donor_tags']['별빛']
        self.assertEqual(t['n'], 14)                                         # 고수달 9번은 기록으로 선수가 됐다(5번 넘음)
        self.assertEqual(t['tag'], 'lean')

    def test_ninety_percent_by_merge(self):
        self.give('가')
        self.give('나')
        self.remember('가', '서아', 9)
        self.remember('나', '하율', 1)
        self.cmd('donor.rebuild')
        self.assertEqual(self.st()['donor_tags']['가']['tag'], 'main')
        self.cmd('donor.merge', a=self.pid('가'), b=self.pid('나'))
        t = self.st()['donor_tags']['나']
        self.assertEqual((t['tag'], t['share'], t['n']), ('main', 0.9, 10))  # 9/10 = 90% → 전담
        self.remember('가', '하율', 1)                                        # 9/11 = 82%
        self.cmd('donor.rebuild')
        self.assertEqual(self.st()['donor_tags']['가']['tag'], 'lean')

    def test_club_confirmed_only(self):
        self.give('밍플단영트트')
        self.give('제이7싸단')
        self.remember('제이7싸단', '서아', 5)
        self.cmd('donor.rebuild')
        st = self.st()
        self.assertEqual(st['donor_tags']['밍플단영트트']['club'], '밍밍')
        self.assertIsNone(st['donor_tags']['제이7싸단']['club'])             # 추정은 딱지에 안 쓴다
        c = st['donor_clubs']['제이7싸단']
        self.assertEqual((c['player'], c['confirmed']), ('서아', False))
        self.cmd('donor.club_set', word='제이7싸단', player='서아', confirmed=True)
        self.assertEqual(self.st()['donor_tags']['제이7싸단']['club'], '서아')
        self.cmd('donor.rebuild')                                             # 다시 채워도 확정은 그대로
        self.assertTrue(self.st()['donor_clubs']['제이7싸단']['confirmed'])


# ══ 고리 ══
class Hooks(BookBase):
    def test_assign_undo_reassign(self):
        did = self.give('별빛', 30000, msg='응원')
        self.assign(did, '서아')
        a = self.ans(did)
        self.assertEqual((json.loads(a['final']), a['how'], a['undone'], a['amount'], a['name']), (['서아'], 'human', 0, 30000, '별빛'))
        self.assertIsNone(a['guess'])
        self.assertIsNone(a['changed'])
        self.assertEqual(self.st()['donor_tags']['별빛']['n'], 1)
        c, r = self.cmd('score.undo')
        self.assertEqual(c, 200, r)
        self.assertEqual(self.ans(did)['undone'], 1)
        self.assertEqual(self.st()['donor_tags']['별빛']['n'], 0)             # 기억도 잊었다 → 딱지도
        self.assign(did, '하율')
        a = self.ans(did)
        self.assertEqual((json.loads(a['final']), a['undone']), (['하율'], 0))   # 그 줄을 새로 덮어쓴다
        self.assertEqual(self.db().execute('SELECT COUNT(*) FROM answer_log').fetchone()[0], 1)

    def test_split_assign_order(self):
        did = self.give('별빛', 40000)
        c, r = self.cmd('pending.assign', id=did, names=['채원', '하율'])
        self.assertEqual(c, 200, r)
        self.assertEqual(json.loads(self.ans(did)['final']), ['채원', '하율'])

    def test_write_failure_keeps_score(self):
        did = self.give('별빛', 30000)
        boom = sqlite3.OperationalError('disk')
        with mock.patch.object(book, 'ensure', side_effect=boom):
            self.assign(did, '서아')
        self.assertEqual(self.player('서아')['score'], 3)                     # 점수는 들어갔다
        self.assertIsNone(self.ans(did))                                      # 정답지만 못 적었다
        self.assertEqual(dm.donor_history(self.c.app.state.store, '별빛'), [('서아', 1)])   # 후원자 기억은 그대로
        self.assertEqual(self.st()['pending'], [])

    def test_donation_hook_failure_keeps_donation(self):
        with mock.patch.object(book, 'ensure_card', side_effect=sqlite3.OperationalError('x')):
            did = self.give('별빛', 30000)
        self.assertTrue(did)
        self.assertEqual(len(self.st()['pending']), 1)
        self.assertIsNone(self.pid('별빛'))

    def test_hook_crash_outside_savepoint_never_blocks(self):
        """검토 10-17: 고리가 SAVEPOINT 밖(딱지 고치기 · 추천 읽기)에서 넘어져도 후원 · 배정 · 되돌리기는 그대로 간다."""
        boom = RuntimeError('x')
        with mock.patch.object(book, 'refresh_names', side_effect=boom), \
                mock.patch.object(book, 'refresh_all', side_effect=boom):
            did = self.give('별빛', 30000)
            self.assertEqual(len(self.st()['pending']), 1)
            self.assign(did, '서아')
            self.assertEqual(self.player('서아')['score'], 3)
            self.assertEqual(self.cmd('score.undo')[0], 200)
            self.assertEqual(self.player('서아')['score'], 0)
            self.assertEqual(self.cmd('session.end')[0], 200)
        did = self.give('달빛', 30000)
        with mock.patch.object(book, '_final', side_effect=boom):            # 정답지 고리 맨 앞에서 넘어져도
            self.cmd('session.start', names=['서아'])
            self.assign(did, '서아')
        self.assertEqual(self.st()['pending'], [])

    def test_placeholder_names_make_no_card(self):
        self.give('수동송출')
        self.give('수동송출님')
        self.assertIsNone(self.pid('수동송출'))
        self.cmd('donor.rebuild')                                             # 다시 채워도
        self.assertIsNone(self.pid('수동송출'))

    def test_browser_autopilot_assign_fills_guess(self):
        did = self.give('별빛', 30000)
        c, r = self.cmd('pending.assign', id=did, name='서아', via='ap')
        self.assertEqual(c, 200, r)
        a = self.ans(did)
        self.assertEqual((a['how'], a['guess'], a['guess_how'], a['changed']), ('auto', '서아', 'auto', 0))

    def test_person_recent_reads_all_spellings(self):
        d1 = self.give('별빛님', 10000)
        d2 = self.give(' 별빛 ', 20000)
        self.give('달빛', 30000)
        p = self.get('/api/donors/person/' + self.pid('별빛'))
        self.assertEqual(sorted(x['ref'] for x in p['recent']), sorted([d1, d2]))

    def test_session_start_end_rebuilds_tags(self):
        self.give('별빛')
        self.remember('별빛', '서아', 5)                                      # 명령 밖에서 적힌 기억(옛 기억 잇기 등)
        self.assertEqual(self.st()['donor_tags']['별빛']['tag'], 'new')
        self.cmd('session.end')
        self.assertEqual(self.st()['donor_tags']['별빛']['tag'], 'main')      # 끝 — 선수 명단이 비어도 기록으로 센다
        self.cmd('session.start', names=['서아'])
        self.assertEqual(self.st()['donor_tags']['별빛']['player'], '서아')


class Guess(AutoBase):
    """기계 추천은 대기 카드의 auto(autopilot 이 붙인 것)에서 — 그림자면 사람이 준 것과 견준다."""
    MODE = 'shadow'

    def test_human_vs_guess(self):
        pid = self.give('별빛', 30000, '서아 화이팅')
        self.drain()
        self.assertEqual(self.item(pid)['auto']['target'], '서아')
        self.cmd('pending.assign', id=pid, name='하율')
        a = dict(self.c.app.state.store.db.execute('SELECT * FROM answer_log WHERE ref = ?', (pid,)).fetchone())
        self.assertEqual((a['guess'], a['guess_how'], a['how'], a['changed']), ('서아', 'rule', 'human', 1))
        self.assertGreaterEqual(a['guess_conf'], 0.9)

    def test_human_same_as_guess(self):
        pid = self.give('별빛', 30000, '서아 화이팅')
        self.drain()
        self.cmd('pending.assign', id=pid, name='서아')
        a = self.c.app.state.store.db.execute('SELECT changed FROM answer_log WHERE ref = ?', (pid,)).fetchone()
        self.assertEqual(a[0], 0)


class GuessOn(AutoBase):
    MODE = 'on'

    def test_autopilot_assign_is_auto(self):
        pid = self.give('별빛', 30000, '서아 화이팅')
        self.drain()
        self.assertEqual(self.player('서아')['score'], 3)
        a = dict(self.c.app.state.store.db.execute('SELECT * FROM answer_log WHERE ref = ?', (pid,)).fetchone())
        self.assertEqual((a['how'], a['guess'], a['changed'], json.loads(a['final'])), ('auto', '서아', 0, ['서아']))


# ══ 비공개 · 실명 ══
class Privacy(BookBase):
    def test_private_slices_never_public(self):
        self.give('밍플단영트트')
        self.cmd('donor.rebuild')
        self.assertFalse(is_public('donor_tags'))
        self.assertFalse(is_public('donor_clubs'))
        pub = self.st(auth=False)
        self.assertNotIn('donor_tags', pub)
        self.assertNotIn('donor_clubs', pub)
        self.assertIn('밍플단영트트', self.st()['donor_tags'])                # 조종실은 받는다
        with self.c.websocket_connect('/ws') as ws:                           # 로그인 없는 화면(방송판)
            first = ws.receive_json()
            self.assertNotIn('donor_tags', json.dumps(first, ensure_ascii=False))

    def test_depositor_real_name_nowhere(self):
        from v2.server.domain import bank
        store = self.c.app.state.store
        db = bank._db(store)
        REAL = '김진짜실명'
        db.execute("INSERT INTO bank_inbox(id, ref, source, amount, at, holder) VALUES('b0123456789ab', 'r1', 'ext', 30000, 1, ?)", (REAL,))
        db.execute("INSERT INTO bank_inbox(id, ref, source, amount, at, holder) VALUES('b0123456789ac', 'r2', 'ext', 30000, 2, ?)", (REAL,))
        self.give('달빛', 30000, tx='manual_bank_b0123456789ab', trusted=True)      # 첫 입금 — 송출하며 배운다(route)
        self.assertEqual(bl.lookup(db, REAL), '달빛')
        self.give('별빛', 30000, tx='manual_bank_b0123456789ac', trusted=True)      # 같은 통장 · 다른 닉네임
        rows = self.get('/api/donors/suggest')['rows']
        self.assertEqual([r['why'] for r in rows], ['bank'])
        self.cmd('donor.rebuild')
        # 장부의 모든 표(입금 카드 원본 bank_inbox 빼고) · 조각 · 답에 실명이 없다
        blob = []
        for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name != 'bank_inbox'").fetchall():
            for r in db.execute('SELECT * FROM "%s"' % t):
                blob.append(json.dumps([str(x) for x in tuple(r)], ensure_ascii=False))
        blob.append(json.dumps(self.st(), ensure_ascii=False))
        blob.append(json.dumps(self.get('/api/donors/book'), ensure_ascii=False))
        blob.append(json.dumps(self.get('/api/donors/suggest'), ensure_ascii=False))
        for p in self.get('/api/donors/book')['persons']:
            blob.append(json.dumps(self.get('/api/donors/person/' + p['pid']), ensure_ascii=False))
        self.assertNotIn(REAL, '\n'.join(blob))

    def test_person_message_is_masked(self):
        did = self.give('별빛', 30000, msg='연락 010-1234-5678 주세요')
        p = self.get('/api/donors/person/' + self.pid('별빛'))
        self.assertNotIn('1234-5678', p['recent'][0]['message'])
        self.assertEqual(p['recent'][0]['ref'], did)
        self.cmd('mask.hide', id=did, on=True)
        p = self.get('/api/donors/person/' + self.pid('별빛'))
        self.assertEqual(p['recent'][0]['message'], '')


# ══ 처음 채우기 도구 ══
class Tool(unittest.TestCase):
    def _db(self):
        import os
        import tempfile
        d = tempfile.mkdtemp(prefix='lm2book_')
        self.addCleanup(__import__('shutil').rmtree, d, True)
        path = os.path.join(d, 'x.db')
        from v2.server.store import Store
        s = Store(path)
        dm.ensure(s)
        for i, (nm, src, msg, amt) in enumerate((('별빛', 'toonation', '', 10000), ('별빛님', 'toonation', '', 20000),
                                                ('밍밍', 'mobile', '수동 점수 조작', 50000), ('달빛', 'toonation_test', '', 1000))):
            s.add_donation({'id': 'old_a%d' % i, 'tx_id': None, 'at': 100 + i, 'name': nm, 'amount': amt, 'message': msg,
                            'source': src, 'status': 'archived', 'player': None, 'session': ''})
        for i in range(5):
            dm.remember_assignment(s, '별빛', '서아', 1, '', ref='old:%d' % i, at=50 + i)
        s.close()
        return path

    def test_view_only_then_write_idempotent(self):
        from v2.tools import build_donor_book as tool
        path = self._db()
        st = tool.run(path)
        self.assertEqual((st['persons'], st['tags']['main']), (1, 1))          # 손 점수 · 시험 후원은 카드가 안 된다
        con = sqlite3.connect(path)
        self.assertIsNone(con.execute("SELECT 1 FROM sqlite_master WHERE name = 'donor_person'").fetchone())   # 보기만 — 안 썼다
        con.close()
        a = tool.run(path, write=True)
        b = tool.run(path, write=True)
        self.assertEqual((a['made'], b['made']), (1, 0))
        self.assertEqual({k: v for k, v in a.items() if k not in ('made', 'opened')},
                         {k: v for k, v in b.items() if k not in ('made', 'opened')})
        con = sqlite3.connect(path)
        tags = json.loads(con.execute("SELECT value FROM slices WHERE name = 'donor_tags'").fetchone()[0])
        con.close()
        self.assertEqual(tags['별빛']['tag'], 'main')


if __name__ == '__main__':
    unittest.main()
