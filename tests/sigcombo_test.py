# -*- coding: utf-8 -*-
"""🔁 같은 사람 · 같은 시그니처 연속 — 한 번 틀고 ×N, 조종실 [N번 다 틀기] (2026-09-29).

왜 만들었나
  대표님: "2만원짜리 7개가 나오면 2만원이 계속 나와야 하잖아" — 7번을 연달아 틀면 1분 반 동안 같은 장면이다.
  정한 것(C안): 같은 사람이 같은 시그니처를 연달아 보내면 대기줄에서 하나로 묶어 한 번 틀고 ×N.
  BJ가 N번 해야 하는 날엔 조종실 대기줄의 [N번 다 틀기]로 N번 다 튼다(방송판에 '2 / 7').
  ⚠️ 트는 건 언제나 그 금액의 시그니처다. 금액을 합쳐 다른 시그니처로 바꾸지 않는다(대표님이 짚은 것).

여기서 지키는 것
  ① 같은 사람 · 같은 시그니처가 연달아 오면 한 줄(count)로 묶인다 — 시그니처는 그대로
  ② 다른 사람이면 따로 · 사이에 다른 후원이 끼면 순서를 지키려고 새로 줄 선다
  ③ 시그 순위 집계는 후원마다 그대로 센다
  ④ [N번 다 틀기] 주소 — 켜기 · 끄기 · 없는 것 · 로그인 필요
  ⑤ 방송판 · 조종실 글자

⚠️ pausetest 서버(5199)가 필요하다 — runall 이 띄운다(가짜 시그니처 40장, 방송판은 안 떠 있어 대기줄이 줄지 않는다).
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
PROJ = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:160]) if detail else ''))


def req(path, obj=None, method=None, auth=True):
    data = json.dumps(obj).encode() if obj is not None else None
    r = urllib.request.Request(B + path, data, H if auth else {'Content-Type': 'application/json'},
                               method=method or ('POST' if data is not None else 'GET'))
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def don(name, amount, msg=''):
    # 리스너(투네이션)에서 온 것처럼 — 같은 내용이 연달아 와도 진짜 후원으로 받는다
    return req('/api/donation', {'name': name, 'amount': amount, 'message': msg, 'tx_id': 'toon_' + uuid.uuid4().hex[:12]})


def queue():
    return req('/api/data')[1].get('reaction_queue') or []


req('/api/server/start_broadcast', {'names': ['가', '나']})
req('/api/reaction/stop', {})

print('=' * 74); print('① 같은 사람 · 같은 시그니처는 한 줄로'); print('=' * 74)
for _ in range(3):
    don('민수', 12000, '하율 가자!!')
q = queue()
chk('3번 보내면 대기줄에 한 줄 · ×3', len(q) == 1 and q[0].get('count') == 3, [(x.get('donator'), x.get('count')) for x in q])
chk('트는 시그니처는 그 금액 그대로(합쳐서 다른 시그니처로 안 바뀐다)', q and q[0].get('amount') == 12000
    and len({x.get('item_id') for x in q}) == 1, q[0].get('title') if q else None)
chk('처음엔 한 번만 틀기(play_all 꺼짐)', q and q[0].get('play_all') is False)

print(); print('=' * 74); print('② 다른 사람 · 끼어든 후원'); print('=' * 74)
don('지훈', 12000, '나도')
don('민수', 12000, '또')
q = queue()
chk('다른 사람은 따로 줄 선다', [(x.get('donator'), x.get('count')) for x in q][:2] == [('민수', 3), ('지훈', 1)], [(x.get('donator'), x.get('count')) for x in q])
chk('사이에 다른 후원이 끼면 순서를 지키려고 새로 줄 선다', len(q) == 3 and q[2].get('donator') == '민수' and q[2].get('count') == 1)
don('민수', 12000, '연달아')
chk('줄 끝이 같은 사람이면 다시 묶인다', queue()[-1].get('count') == 2)
don('민수', 30000, '다른 시그')
q = queue()
chk('같은 사람이어도 금액(시그니처)이 다르면 따로', len(q) == 4 and q[-1].get('amount') == 30000 and q[-1].get('count') == 1,
    [(x.get('donator'), x.get('amount'), x.get('count')) for x in q])

print(); print('=' * 74); print('③ 시그 순위 집계는 후원마다'); print('=' * 74)
tally = req('/api/data')[1].get('sig_tally') or {}
tot = {}
for v in tally.values():
    for who, n in (v.get('donors') or {}).items():
        tot[who] = tot.get(who, 0) + n
chk('민수 6번 · 지훈 1번 그대로 센다', tot.get('민수', 0) >= 6 and tot.get('지훈', 0) >= 1, tot)

print(); print('=' * 74); print('④ [N번 다 틀기]'); print('=' * 74)
rid = queue()[0]['id']
c, r = req('/api/reaction/queue/playall/' + rid, {'on': True})
chk('켜면 play_all', c == 200 and r.get('play_all') is True and r.get('count') == 3 and queue()[0].get('play_all') is True, (c, r))
c, r = req('/api/reaction/queue/playall/' + rid, {'on': False})
chk('끄면 다시 한 번 + ×N', c == 200 and queue()[0].get('play_all') is False, (c, r))
c, r = req('/api/reaction/queue/playall/rq_nothing_here', {'on': True})
chk('없는 것은 알려준다', c == 404 and '대기줄' in (r.get('message') or ''), (c, r))
c, r = req('/api/reaction/queue/playall/' + rid, {'on': True}, auth=False)
chk('로그인 없이는 못 바꾼다', c in (401, 403), c)
req('/api/reaction/stop', {})

print(); print('=' * 74); print('⑥ 계좌 후원 직접 송출 — × 몇 번 · 같은 내용 필터'); print('=' * 74)
req('/api/reaction/stop', {})
c, r = req('/api/signature/play', {'name': '계좌손님', 'amount': 12000, 'message': '계좌', 'count': 3})
q = queue()
chk('재생만(장부 없이) ×3 → 대기줄 한 줄 ×3 · 같은 시그니처', c == 200 and r.get('count') == 3 and len(q) == 1
    and q[0].get('count') == 3 and q[0].get('amount') == 12000, (c, [(x.get('donator'), x.get('count')) for x in q]))
req('/api/reaction/stop', {})
pend0 = len(req('/api/data')[1].get('pending_donations') or [])
T = uuid.uuid4().hex[:8]
for i in range(3):
    c, r = req('/api/donation', {'name': '계좌민수', 'amount': 12000, 'message': '같은 메시지', 'tx_id': 'manual_%s_%d' % (T, i + 1)})
d = req('/api/data')[1]
pend = [x for x in (d.get('pending_donations') or []) if x.get('name') == '계좌민수']
q = d.get('reaction_queue') or []
chk('장부 ×3 — 같은 사람 · 같은 금액 · 같은 메시지 3건이 전부 들어간다(12초 필터를 안 탄다)', len(pend) == 3, len(pend))
chk('장부 ×3 — 시그니처는 대기줄 한 줄 ×3 으로 묶인다', len(q) == 1 and q[0].get('count') == 3, [(x.get('donator'), x.get('count')) for x in q])
c1, r1 = req('/api/donation', {'name': '스크립트', 'amount': 5000, 'message': '같은', 'tx_id': 'tm_%s_a' % T})
c2, r2 = req('/api/donation', {'name': '스크립트', 'amount': 5000, 'message': '같은', 'tx_id': 'tm_%s_b' % T})
chk('운영자 수동 송출이 아닌 곳은 여전히 12초 필터로 거른다(예전 템퍼몽키 재전송 방지)',
    c1 == 200 and 'Duplicate' not in (r1.get('message') or '') and 'Duplicate' in (r2.get('message') or ''), (r1, r2))
c, r = req('/api/donation', {'name': '로그인안함', 'amount': 5000, 'message': 'x', 'tx_id': 'manual_%s_z' % T}, auth=False)
chk('로그인 안 한 manual_ 는 예외가 아니다(주소만 흉내 내도 필터를 못 피한다)', 'from_manual = str(tx_id or \'\').startswith(\'manual_\') and request_is_authed()'
    in io.open(os.path.join(PROJ, 'features', 'donation.py'), encoding='utf-8').read())
for x in (req('/api/data')[1].get('pending_donations') or []):
    req('/api/pending/remove/' + x['id'], {})
req('/api/reaction/stop', {})

print(); print('=' * 74); print('⑤ 방송판 · 조종실'); print('=' * 74)
OV = io.open(os.path.join(PROJ, 'overlay.html'), 'rb').read().replace(b'\x00', b'').decode('utf-8')
CT = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8').read()
SV = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8').read()
chk('그림 모서리에 ×N 자리', '<div id="reaction-combo" aria-hidden="true"></div>' in OV and '#reaction-combo.burst' in OV)
chk('처음 뜰 때 ×1 → ×N 으로 올라가고, 틀던 중 늘면 바로 올린다', 'let k = 1; bump(1);' in OV and 'bump(cnt);' in OV)
chk('[N번 다 틀기]면 몇 번째인지(2 / 7)', "el.innerHTML = '<b>' + n + '</b> / ' + cnt;" in OV)
chk('[N번 다 틀기]면 끝날 때 남은 만큼 같은 시그니처를 다시 튼다(큐는 안 넘김)',
    '_rh.play_all && rxRep.id === popId && rxRep.n < (Number(_rh.count) || 1)' in OV and 'playReaction(_rh, true);' in OV)
chk('다시 틀 때는 후원 팝업을 또 띄우지 않는다', 'if (data.skip_popup || queueBacklog || bigDonation || isRepeat) {' in OV)
chk('업데이트마다 표시를 맞춘다', 'try { rxComboSync(); } catch (e) {}\n            if (isDonationPopupShowing) return;' in OV)
chk('슬롯 당첨 · 재생전용 · 주사위 대기는 묶지 않는다', 'if (count_tally and not skip_popup and not play_after_ms and _last is not None' in SV)
chk('조종실 대기줄에 ×N 과 [N번 다 틀기]', "cnt + '번 다 틀기'" in CT and "railPost('/api/reaction/queue/playall/'" in CT
    and 'x.count, x.play_all' in CT)
MS = io.open(os.path.join(PROJ, 'manual_send.html'), encoding='utf-8').read()
chk('조종실 시그니처 송출 칸에 × 몇 번', 'id="rs-count"' in CT and ": [{ name: name, amount: a, message: msg, count: cnt }];" in CT
    and "tx_id: 'manual_' + stamp + (cnt > 1 ? '_' + (i + 1) : '')" in CT)
chk('후원 콘솔에도 × 몇 번', 'id="in-count"' in MS and ": [{ name, amount, message, count:cnt }];" in MS)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
