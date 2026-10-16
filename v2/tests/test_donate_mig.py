# -*- coding: utf-8 -*-
"""10-17 이사 1차 — donate 갈래(후원 받기 · 장부 바로잡기). 옛 프로그램 동작이 정답이다.

① 투네이션 '다시 보기'(replay) · 대시보드 '후원 테스트'(test) → 방송 화면에만(옛 features/donation.py 369-392, 176db46)
   — 투네이션 신호엔 고유 번호가 없어 리스너가 tx_id 를 매번 새로 만든다 → tx_id 중복 거르기로는 못 막는다(실제 리스너 함수로 보여 준다)
② VIP 등급 꺼 둠(옛 features/vip.py VIP_ON=False, b51bcc1)
③ 묶음(×N) 메시지 모으기(옛 server.py enqueue_signature msgs, 5d179b0)
④ 순위에서 빼기 · 다시 넣기로 '한 방 최고' 를 다시 고를 때 at 0 — '최고 기록 갱신!' 이 안 터진다(옛 features/excluded.py)
⑤ 칭호 · 레벨 · 투네이션 VIP · 번호표(옛 _donor_extras · donor_keys, 176db46 · 27ee92a) + 옛 장부 옮기기(donor_keys)
⑥ '투네' 딱지 via:'toon'(옛 97cbc4c)
⑦ 시그니처 중 모금함 깃발 숨김(층 표 hideInReaction, 옛 77a3aba) — node 로 층 표를 읽는다
⑧ 이미 빠진 묶음을 [N번 다 틀기]로 남은 만큼 이어 틀기(옛 features/reaction.py _RECENT_DONE)
⑨ 방송판 도구(donate_kit.js) 순수 함수 — node
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.domain import ai_facts as af
from v2.server.domain import donation as dn
from v2.server.domain import donor_extras as dx
from v2.server.domain import donors as dmod
from v2.server.domain import reaction as rx
from v2.tests.test_flow import Base, H, PW, SECRET, SIGS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
TITLE_BLACK = {'name': '블랙 다이아', 'type': 105, 'color': '#123456'}
KEY = '0123456789abcdef'


def counted(rows):
    return [r for r in rows if r['status'] in ('pending', 'assigned', 'ignored', 'archived')]


class Mig(Base):
    def ledger(self):
        return self.c.get('/api/ledger?limit=2000', headers=H).json()

    def monthly_total(self):
        return self.c.get('/api/ranking/monthly', headers=H).json()['total']

    def memory_rows(self):
        db = self.c.app.state.store.db
        try:
            return db.execute('SELECT COUNT(*) FROM donor_memory').fetchone()[0]
        except sqlite3.OperationalError:
            return 0


# ── ① 다시 보기 · 후원 테스트 ────────────────────────────────
class ShowOnly(Mig):
    def listener_payloads(self, **content):
        """실제 리스너(toon_listener.to_donation)가 만드는 모양 그대로 — 같은 후원을 두 번 '다시 보기'"""
        import toon_listener as tl
        tl._recent.clear()
        pkt = {'code': 101, 'replay': 1, 'content': dict({'name': '큰손', 'amount': 800000, 'message': '축하해요'}, **content)}
        p1, _, _ = tl.to_donation(pkt)
        time.sleep(0.002)
        p2, _, _ = tl.to_donation(pkt)
        return p1, p2

    def test_listener_tx_is_new_every_time_so_tx_dedup_cannot_stop_replays(self):
        p1, p2 = self.listener_payloads()
        self.assertTrue(p1['tx_id'].startswith('toon_') and p2['tx_id'].startswith('toon_'))
        self.assertNotEqual(p1['tx_id'], p2['tx_id'])                 # 고유 번호가 없어 매번 새 tx_id
        self.assertIs(p1['replay'], True)
        # 표시를 버리면(10-17 전 v2) 두 번 다 진짜 후원으로 들어간다 — tx_id 거르기가 못 막는다
        for p in (p1, p2):
            self.don(**{k: v for k, v in p.items() if k != 'replay'})
        self.assertEqual(len(self.st()['pending']), 2)
        self.assertEqual(self.ledger()['total'], 1600000)

    def test_replay_is_screen_only(self):
        self.don('별빛', 30000, 'toon_real1', msg='진짜')
        base_ledger, base_month = self.ledger()['total'], self.monthly_total()
        before = self.st()
        seen = []
        dn.AFTER_DONATION.append(lambda ctx, name, amount: seen.append(name))     # 자동 진행 · 등급 고리
        try:
            p1, p2 = self.listener_payloads()
            c, r = self.don(**p1)
            c2, r2 = self.don(**p2)
        finally:
            dn.AFTER_DONATION.pop()
        self.assertEqual((c, r), (200, {'status': 'success', 'show_only': 'replay'}))      # 옛 답 모양
        self.assertEqual(r2.get('show_only'), 'replay')
        self.assertEqual(seen, [])
        s = self.st()
        self.assertEqual(s['pending'], before['pending'])                                 # 대기함 그대로
        self.assertEqual(s['tallies']['donors'], before['tallies']['donors'])             # 후원 순위 그대로
        self.assertEqual(s['tallies']['best'], before['tallies']['best'])                 # 한 방 최고 그대로(80만 아님)
        self.assertEqual(s['tallies']['sigs'], before['tallies']['sigs'])                 # 시그 집계 그대로
        self.assertEqual(self.ledger()['total'], base_ledger)                             # 정산 합계 그대로
        self.assertEqual(self.monthly_total(), base_month)                                # 월별 순위 그대로
        self.assertEqual(self.memory_rows(), 0)                                           # AI 기억 없음
        rows = [x for x in self.ledger()['rows'] if x['name'] == '큰손']
        self.assertEqual([(x['status'], x['source']) for x in rows], [('display', 'toonation_replay')] * 2)   # 화면만 줄(합계 밖)
        # 화면에는 나온다 — 팝업 · 시그니처(묶음 · 시그 순위엔 안 낌)
        pop = s['popup']['donation']
        self.assertEqual((pop['name'], pop['amount'], pop['show_only']), ('큰손', 800000, 'replay'))
        q = [x for x in s['queue']['items'] if x['donator'] == '큰손']
        self.assertEqual([(x['title'], x['count']) for x in q], [('대박', 1), ('대박', 1)])
        self.assertEqual(q[0]['via'], 'toon')
        # 같은 tx_id 재전송(리스너 대기줄)은 한 번으로
        c, r = self.don(**p1)
        self.assertEqual(r.get('message'), 'Duplicate donation ignored.')

    def test_dashboard_test_flag_and_small_replay(self):
        c, r = self.don('시험', 20000, 'toon_dt1', test=True)
        self.assertEqual(r.get('show_only'), 'test')
        self.assertEqual(self.st()['pending'], [])
        self.assertEqual([x['source'] for x in self.ledger()['rows']], ['toonation_dashtest'])
        # 1만 원 미만 다시 보기 — 시그 없이 맨 위 띠로(display_only)
        c, r = self.don('작은손', 3000, 'toon_dt2', replay=True)
        self.assertTrue(self.st()['popup']['donation']['display_only'])
        self.assertEqual(self.st()['pending'], [])

    def test_replay_carries_title_but_not_key(self):
        """다시 보기에도 칭호 · Lv 는 화면에 싣고(옛 _latest.update(_pub)), 번호표는 화면 · 번호표 표 어디에도 안 남긴다(옛 것은 적기 전에 return)."""
        c, r = self.don('다시손', 50000, 'toon_rk1', replay=True, title=TITLE_BLACK, level=7, vip='골드', donor_key=KEY)
        self.assertEqual(r.get('show_only'), 'replay')
        pub = self.st(auth=False)
        self.assertEqual((pub['popup']['donation']['donor_title']['name'], pub['popup']['donation']['donor_level']), ('블랙 다이아', 7))
        q = [x for x in pub['queue']['items'] if x['donator'] == '다시손']
        self.assertEqual((q[0]['donor_title']['name'], q[0]['via']), ('블랙 다이아', 'toon'))
        dump = json.dumps(self.st(auth=True), ensure_ascii=False)
        self.assertNotIn(KEY, dump)                                             # 대기함에도 안 들어가니 어디에도 없다
        self.assertNotIn('toon_vip', dump)
        self.assertEqual(dx.keys_for(self.c.app.state.store, KEY), [])          # 번호표 표에도 안 적는다(옛 것과 같다)

    def test_only_listener_may_ask_for_screen_only(self):
        c, r = self.don('콘솔', 20000, 'manual_x1', replay=True, test=True)        # 조종실 · 바깥이 붙여도 평소대로
        self.assertIn('id', r)
        self.assertEqual(len(self.st()['pending']), 1)
        c, r = self.don('문자', 20000, 'toon_x2', replay='1')                      # 옛 것처럼 정확히 True 일 때만
        self.assertIn('id', r)


# ── ② VIP 끔 ─────────────────────────────────────────────────
class VipOff(Mig):
    def test_vip_off_everywhere(self):
        self.assertFalse(dmod.VIP_ON)                                             # 기본 꺼짐(대표님 10-13)
        for i, (n, a) in enumerate((('가', 50000), ('나', 30000))):
            self.don(n, a, 'toon_vo%d' % i)
        for auth in (False, True):
            t = self.st(auth=auth)['tallies']
            self.assertEqual((t['vip'], t['vip_on']), ({}, False))
        c, r = self.cmd('vip.set', name='단골', grade='VIP')
        self.assertEqual(c, 409)
        self.assertIn('꺼져', r['error'])
        t = self.st()['tallies']
        self.assertEqual(af.vip_list(t), [])
        self.assertNotIn('VIP', af.build_facts(self.c.app.state.bus.state.slices, vip=af.vip_list(t)))
        # 옛 등급이 조각에 남아 있어도(10-17 전 v2 시험판 DB) 아무 명령 하나 뒤면 비워진다
        st = self.c.app.state.bus.state
        st.slices['tallies'] = dict(st.slices['tallies'], vip={'가': {'rank': 1, 'grade': 'VVIP'}}, vip_on=True)
        self.cmd('reaction.pause', paused=False)
        self.assertEqual(self.st(auth=False)['tallies']['vip'], {})

    def test_stale_vip_list_ignored_by_ai(self):
        self.assertEqual(af.vip_list({'vip_on': False, 'vip': {'가': {'name': '가', 'rank': 1, 'grade': 'VVIP'}}}), [])


# ── ③ 묶음 메시지 ─────────────────────────────────────────────
class ComboMsgs(Mig):
    def test_msgs_collected_in_order(self):
        for i, m in enumerate(('아버지', '어머니', '', '삼촌')):
            self.don('홍길동', 20000, 'toon_cm%d' % i, msg=m)
        self.don('달빛', 20000, 'toon_cmx', msg='혼자')
        q = self.st()['queue']['items']
        self.assertEqual((q[0]['count'], q[0]['message'], q[0]['msgs']), (4, '아버지', ['아버지', '어머니', '', '삼촌']))   # 빈 것도 자리
        self.assertNotIn('msgs', q[1])                                          # 혼자인 줄은 message 하나

    def test_msgs_cap(self):
        for i in range(rx.REACTION_MSGS_MAX + 3):
            self.don('홍길동', 20000, 'toon_cap%d' % i, msg='m%d' % i)
        it = self.st()['queue']['items'][0]
        self.assertEqual((it['count'], len(it['msgs'])), (rx.REACTION_MSGS_MAX + 3, rx.REACTION_MSGS_MAX))


# ── ④ 한 방 최고 다시 고르기 ─────────────────────────────────
class BestRepick(Mig):
    def test_exclude_include_do_not_fire_new_record(self):
        self.don('운영자', 100000, 'toon_b1')
        self.don('별빛', 30000, 'toon_b2')
        self.assertTrue(self.st()['tallies']['best']['at'])                     # 진짜 갱신은 시각이 있다
        self.cmd('donor.exclude', name='운영자')
        b = self.st()['tallies']['best']
        self.assertEqual((b['name'], b['amount'], b['at']), ('별빛', 30000, 0))   # 다시 고른 것 — 갱신 아님
        self.don('운영자', 200000, 'toon_b3')                                     # 뺀 사람이 또 보내도 최고는 그대로
        b = self.st()['tallies']['best']
        self.assertEqual((b['name'], b['at']), ('별빛', 0))
        self.cmd('donor.include', name='운영자')
        b = self.st()['tallies']['best']
        self.assertEqual((b['name'], b['amount'], b['at']), ('운영자', 200000, 0))
        self.don('새손', 300000, 'toon_b4')                                       # 다음 진짜 갱신은 다시 터진다
        self.assertTrue(self.st()['tallies']['best']['at'])

    def test_include_smaller_keeps_record(self):
        self.don('작은손', 20000, 'toon_s1')
        self.cmd('donor.exclude', name='작은손')
        self.don('큰손', 50000, 'toon_s2')
        before = self.st()['tallies']['best']
        self.cmd('donor.include', name='작은손')
        self.assertEqual(self.st()['tallies']['best'], before)                  # 작으면 그대로(옛 '클 때만')


# ── ⑤⑥ 칭호 · 레벨 · 번호표 · 투네 딱지 ──────────────────────
class Extras(Mig):
    def test_clean_rules(self):
        pub, priv = dx.clean({'title': TITLE_BLACK, 'level': 12, 'vip': ' 골드  VIP ', 'donor_key': KEY})
        self.assertEqual(pub, {'donor_title': {'name': '블랙 다이아', 'color': '#3A3A44'}, 'donor_level': 12})   # 색은 이름으로
        self.assertEqual(priv, {'toon_vip': '골드 VIP', 'donor_key': KEY})
        self.assertEqual(dx.clean({'title': {'name': '밍밍 팬', 'type': 301}})[0], {})                       # 크리에이터 칭호
        self.assertEqual(dx.clean({'title': {'name': '다이아', 'type': 350}})[0], {})                        # 301~ 은 이름이 다이아여도
        self.assertEqual(dx.clean({'title': {'name': '노블레스'}})[0]['donor_title']['name'], '노블레스')     # type 없음 → 이름으로
        self.assertEqual(dx.clean({'title': {'name': '특별', 'type': 150, 'color': 'red'}})[0]['donor_title'], {'name': '특별'})
        self.assertEqual(dx.clean({'level': 0, 'donor_key': 'ABCDEF0123456789'}), ({}, {}))                  # 대문자 · 0 레벨 버림
        self.assertEqual(dx.clean({'level': 1000, 'donor_key': 'me@mail.com'}), ({}, {}))

    def test_listener_extras_flow(self):
        c, r = self.don('다이아손', 50000, 'toon_e1', title=TITLE_BLACK, level=12, vip='골드', donor_key=KEY)
        s = self.st()
        p = s['pending'][0]
        self.assertEqual((p['donor_title']['name'], p['donor_level'], p['toon_vip'], p['donor_key']), ('블랙 다이아', 12, '골드', KEY))
        pop = s['popup']['donation']
        self.assertEqual((pop['donor_title']['color'], pop['donor_level']), ('#3A3A44', 12))
        q = s['queue']['items'][0]
        self.assertEqual((q['donor_title']['name'], q['donor_level'], q['via']), ('블랙 다이아', 12, 'toon'))
        pub = json.dumps(self.st(auth=False), ensure_ascii=False)
        self.assertNotIn(KEY, pub)                                              # ⚠️ 번호표는 방송판으로 절대 안 나간다
        self.assertNotIn('toon_vip', pub)
        self.assertEqual(dx.keys_for(self.c.app.state.store, KEY), ['toon_e1'])
        row = self.c.app.state.store.db.execute('SELECT level, title, vip FROM donor_keys').fetchone()
        self.assertEqual(tuple(row), (12, '블랙 다이아', '골드'))
        # 리스너가 아닌 곳이 붙여 보낸 칭호는 안 믿는다 · 딱지도 없다
        self.cmd('reaction.stop')
        self.don('계좌손', 50000, 'manual_e2', title=TITLE_BLACK, level=5, donor_key=KEY)
        s = self.st()
        self.assertNotIn('donor_title', s['pending'][-1])
        self.assertNotIn('donor_title', s['popup']['donation'])
        self.assertNotIn('via', s['queue']['items'][0])
        self.assertEqual(dx.keys_for(self.c.app.state.store, KEY), ['toon_e1'])

    def test_via_paths(self):
        self.don('테스트계정', 20000, 'toon_t2_v1')                                # 🧪 테스트 계정도 투네이션
        self.don('다시보기', 20000, 'toon_v2', replay=True)
        self.c.post('/api/signature/play', json={'amount': 20000, 'name': '콘솔'}, headers=H)   # 후원 콘솔 바로 틀기 — 없다
        q = {x['donator']: x.get('via') for x in self.st()['queue']['items']}
        self.assertEqual(q, {'테스트계정': 'toon', '다시보기': 'toon', '콘솔': None})

    def test_small_band_carries_title(self):
        self.don('띠손', 3000, 'toon_sb1', display_only=True, title={'name': '금수저', 'type': 120}, donor_key=KEY)
        pop = self.st(auth=False)['popup']['donation']
        self.assertEqual((pop['display_only'], pop['donor_title']['name']), (True, '금수저'))
        self.assertNotIn(KEY, json.dumps(pop))


class ImportKeys(unittest.TestCase):
    """옛 장부의 donor_keys 표도 옮긴다(v2/tools/import_old_db.py)."""

    def test_import_donor_keys(self):
        from v2.tools import import_old_db as imp
        d = tempfile.mkdtemp(prefix='lm2dk_')
        try:
            old, v2db = os.path.join(d, 'old.db'), os.path.join(d, 'v2.db')
            db = sqlite3.connect(old)
            db.executescript("""
            CREATE TABLE donation_history (id INTEGER PRIMARY KEY, timestamp TEXT, name TEXT, amount INTEGER, current_total INTEGER,
                message TEXT, source TEXT, tx_id TEXT);
            CREATE TABLE donor_keys (tx_id TEXT PRIMARY KEY, donor_key TEXT NOT NULL, level INTEGER, title TEXT, vip TEXT, at TEXT);
            """)
            db.execute("INSERT INTO donation_history (timestamp, name, amount, message, source, tx_id) VALUES ('2026-10-08 12:00:00', '큰손', 50000, '', 'toonation', 'toon_k1')")
            db.executemany('INSERT INTO donor_keys VALUES (?,?,?,?,?,?)', [
                ('toon_k1', KEY, 12, '블랙 다이아', '골드', '2026-10-08 12:00:00'),
                ('toon_k2', 'not-a-key', 1, None, None, '2026-10-08 12:00:00'),          # 번호표 모양이 아니면 안 옮긴다
            ])
            db.commit()
            db.close()
            args = ['--sqlite', old, '--v2-db', v2db, '--check-url', 'http://127.0.0.1:9/none', '--write']
            self.assertEqual(imp.main(args), 0)
            self.assertEqual(imp.main(args), 0)                                    # 두 번 돌려도 한 번
            v = sqlite3.connect(v2db)
            rows = v.execute('SELECT tx_id, donor_key, level, title, vip FROM donor_keys').fetchall()
            v.close()
            self.assertEqual(rows, [('toon_k1', KEY, 12, '블랙 다이아', '골드')])
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ── ⑧ 끝난 묶음 이어 틀기 ────────────────────────────────────
class PlayAllAgain(Mig):
    def done(self, it, rp=None):
        data = {'id': it['id']}
        if rp is not None:
            data['replay'] = rp
        return self.c.post('/api/cmd', json={'type': 'reaction.done', 'data': data}).json()

    def test_continue_after_group_left_queue(self):
        for i, m in enumerate(('아버지', '어머니', '삼촌')):
            self.don('홍길동', 20000, 'toon_pa%d' % i, msg=m)
        self.don('달빛', 50000, 'toon_pax')
        q = self.st()['queue']['items']
        g = q[0]
        self.done(g)                                                            # 한 번만 틀고 빠졌다(×3)
        rec = self.st()['reaction_done_recent']['items']
        self.assertEqual([(x['id'], x['played'], x['total']) for x in rec], [(g['id'], 1, 3)])
        self.assertNotIn('reaction_done_recent', self.st(auth=False))           # 방송판엔 안 간다
        c, r = self.cmd('reaction.playall', id=g['id'], on=True)
        self.assertEqual((c, r['again'], r['count'], r['seq_base'], r['seq_total']), (200, True, 2, 1, 3))
        q = self.st()['queue']['items']
        nw = q[1]                                                               # 지금 나오는 것(달빛) 바로 다음
        self.assertEqual(q[0]['donator'], '달빛')
        self.assertEqual((nw['again_of'], nw['count'], nw['play_all'], nw['skip_popup'], nw['seq_base'], nw['seq_total']),
                         (g['id'], 2, True, True, 1, 3))
        self.assertEqual(nw['msgs'], ['아버지', '어머니', '삼촌'])                # 메시지도 들고 간다 → 어머니 · 삼촌 차례
        self.assertEqual(nw['via'], 'toon')
        c, r = self.cmd('reaction.playall', id=g['id'], on=True)                # 두 번 눌러 두 번 이어 틀지 않게
        self.assertEqual(c, 404)
        # 이어 틀기 줄을 끝까지 틀면 더 이을 것이 없다
        self.done(q[0])
        self.done(nw, 0)
        self.done(nw, 1)
        self.assertEqual(self.st()['queue']['items'], [])
        last = self.st()['reaction_done_recent']['items'][-1]
        self.assertEqual((last['played'], last['total']), (3, 3))
        c, r = self.cmd('reaction.playall', id=nw['id'], on=True)
        self.assertEqual(c, 409)
        self.assertIn('이미 3번', r['error'])

    def test_skip_is_remembered_and_session_end_clears(self):
        self.don('홍길동', 20000, 'toon_sk1')
        self.don('홍길동', 20000, 'toon_sk2')
        g = self.st()['queue']['items'][0]
        self.cmd('reaction.skip')
        self.assertEqual(self.st()['reaction_done_recent']['items'][0]['id'], g['id'])
        c, r = self.cmd('reaction.playall', id=g['id'], on=False)               # 끄기는 할 일이 없다
        self.assertEqual((c, r['play_all']), (200, False))
        self.cmd('session.end')
        self.assertEqual(self.st()['reaction_done_recent']['items'], [])
        self.assertEqual(self.cmd('reaction.playall', id=g['id'])[0], 404)

    def test_single_is_not_remembered(self):
        self.don('혼자', 20000, 'toon_one')
        self.done(self.st()['queue']['items'][0])
        self.assertEqual(self.st()['reaction_done_recent']['items'], [])


# ── ⑦⑨ 방송판 · 조종실 JS(node) ──────────────────────────────
NODE_SCRIPT = r"""
import { pathToFileURL } from 'node:url';
const root = process.argv[1];
const imp = p => import(pathToFileURL(root + '/' + p).href);
const k = await imp('v2/web/overlay/donate_kit.js');
const { LAYERS } = await imp('v2/web/overlay/layers.js');
const ct = await imp('v2/web/controller/js/donate_tags.js').catch(e => ({ err: String(e) }));
// 아주 작은 가짜 document — 알약을 만들어 짜임만 본다
function el(tag) {
  return { tag, className: '', textContent: '', children: [], attrs: {}, style: { props: {}, setProperty(k, v) { this.props[k] = v; } },
    appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; },
    prepend(c) { this.children.unshift(c); } };
}
const doc = { createElement: el, createElementNS: (ns, t) => el(t) };
const tag = k.donorTag({ name: '블랙 노블레스' }, doc);
const flat = n => [n.className || n.tag, ...(n.children || []).flatMap(flat)];
const out = {
  layer_fundjar: LAYERS.find(l => l.id === 'fundjar'),
  layer_ranking_hide: LAYERS.find(l => l.id === 'ranking').hideInReaction,
  msg_single: k.sigMsgFor({ message: '혼자' }),
  msg_manual: k.sigMsgFor({ message: '수동 후원 송출' }),
  msg_all_turns: [0, 1, 2].map(r => k.sigMsgFor({ msgs: ['아버지', '어머니', '삼촌'], play_all: true, replay: r })),
  msg_again: [0, 1].map(r => k.sigMsgFor({ msgs: ['아버지', '어머니', '삼촌'], play_all: true, seq_base: 1, replay: r })),
  msg_once: k.sigMsgFor({ msgs: ['아버지', '', '어머니', '수동 후원 송출'], play_all: false }),
  msg_many: k.sigMsgFor({ msgs: ['1', '2', '3', '4', '5', '6'] }),
  msg_over: k.sigMsgFor({ msgs: ['a', 'b'], play_all: true, replay: 5 }),
  combo_plain: k.comboOf({ count: 3 }),
  combo_all: k.comboOf({ count: 2, replay: 1, play_all: true }),
  combo_again: k.comboOf({ count: 2, seq_base: 1, play_all: true }),
  tier_black_noblesse: k.donorTier({ name: '블랙 노블레스' }),
  tier_unknown_dia: k.donorTier({ name: '핑크다이아' }),
  tier_unknown: k.donorTier({ name: '특별', color: '#112233' }),
  tier_badcolor: k.donorTier({ name: '특별', color: 'red' }),
  spec_gold: k.donorTagSpec({ name: '금수저' }),
  spec_none: k.donorTagSpec(null),
  tag_parts: flat(tag),
  tag_text: tag.children.find(c => c.className === 'dt-lbl').children.find(c => c.className === 'dt-txt').textContent,
  lv: [k.donorLvText(12), k.donorLvText(0), k.donorLvText('x')],
  ink_dark: ct.titleInk ? ct.titleInk('#3A3A44') : ct.err,
  ink_light: ct.titleInk ? ct.titleInk('#9EE7FF') : ct.err,
  color_bad: ct.titleColor ? ct.titleColor({ color: 'javascript:1' }) : ct.err,
};
console.log(JSON.stringify(out));
"""


class OverlayJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node = shutil.which('node')
        if not node:
            raise unittest.SkipTest('node 가 없다 — 방송판 JS 검사는 건너뛴다')
        r = subprocess.run([node, '--input-type=module', '-e', NODE_SCRIPT, ROOT.replace('\\', '/')],
                           capture_output=True, text=True, encoding='utf-8', timeout=60)
        if r.returncode != 0:
            raise AssertionError('node 실패: ' + r.stderr[-2000:])
        cls.o = json.loads(r.stdout.strip().splitlines()[-1])

    def test_fundjar_hides_during_signature(self):
        self.assertTrue(self.o['layer_fundjar']['hideInReaction'])              # 옛 77a3aba — 점수판 · 게이지와 함께
        self.assertTrue(self.o['layer_ranking_hide'])

    def test_combo_messages(self):
        o = self.o
        self.assertEqual((o['msg_single'], o['msg_manual']), ('혼자', ''))
        self.assertEqual(o['msg_all_turns'], ['아버지', '어머니', '삼촌'])        # 틀 때마다 그 차례
        self.assertEqual(o['msg_again'], ['어머니', '삼촌'])                     # 이어 틀기는 앞에서 튼 만큼 건너뛴다
        self.assertEqual(o['msg_once'], '아버지\n어머니')                        # 한 번만 틀면 다 같이(빈 것 · 수동 문구 빼고)
        self.assertEqual(o['msg_many'], '1\n2\n3\n4\n… 외 2개')
        self.assertEqual(o['msg_over'], '')

    def test_combo_numbers(self):
        self.assertEqual(self.o['combo_plain'], {'total': 3, 'nth': 1, 'count': 3, 'all': False})
        self.assertEqual(self.o['combo_all'], {'total': 3, 'nth': 2, 'count': 2, 'all': True})
        self.assertEqual(self.o['combo_again'], {'total': 3, 'nth': 2, 'count': 2, 'all': True})   # '2 / 3' 부터

    def test_title_pill(self):
        o = self.o
        self.assertEqual(o['tier_black_noblesse'], {'c1': '#8D90A8', 'c2': '#07070B', 'lv': 6, 'prism': True})
        self.assertEqual(o['tier_unknown_dia']['lv'], 1)                         # 표에 없으면 이름(다이아)으로
        self.assertEqual(o['tier_unknown'], {'c1': '#112233', 'c2': '#112233', 'lv': 0, 'prism': False})
        self.assertEqual(o['tier_badcolor']['c1'], '#E2B64B')                    # #RRGGBB 가 아니면 기본 금색
        self.assertEqual((o['spec_gold']['cls'], o['spec_gold']['ink']), ('dtag', '#1b1404'))
        self.assertIsNone(o['spec_none'])
        parts = o['tag_parts']
        for want in ('dt-ray', 'dt-fill', 'dt-lbl', 'dt-txt', 'svg', 'dt-st', 'dt-orb'):     # svg = 왕관(노블레스부터)
            self.assertIn(want, parts)
        self.assertTrue(parts[0].startswith('dtag dt-g dt-sh dt-gl dt-spk dt-cr dt-bd dt-orb dt-rb dt-ray'))
        self.assertEqual(parts.count('dt-st'), 4)
        self.assertEqual(o['tag_text'], '블랙 노블레스')
        self.assertEqual(o['lv'], ['Lv.12', '', ''])

    def test_controller_chip_colors(self):
        self.assertEqual((self.o['ink_dark'], self.o['ink_light'], self.o['color_bad']), ('#ffffff', '#1b1404', '#E2B64B'))


if __name__ == '__main__':
    unittest.main()
