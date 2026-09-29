# -*- coding: utf-8 -*-
"""🧪 투네이션 두 계정 · 1만 원 미만 '화면에만' 후원 (2026-09-29).

왜 만들었나
  대표님: "투네이션 2개에서 받게" — 두 번째 계정은 테스트용, 수 · 목(방송하는 날)은 빼고 쓴다.
  그리고 1천~9천 원 후원을 방송판 맨 위 띠로 띄우기로 했는데, 리스너가 8월부터 1만 원 미만을
  버리고 있어서 띠가 한 번도 뜰 수 없었다. '화면에만' 보내서 대기함 · 점수 · 장부는 예전과 같게 둔다.

여기서 지키는 것
  ① 서버 — 리스너가 보낸 1만 원 미만 display_only 는 띠(latest_donation)만. 대기함 · 장부 · 순위는 그대로
  ② 서버 — 같은 tx_id 재전송은 거른다, 리스너가 아닌 곳 · 1만 원 이상은 평소대로
  ③ 서버 — 테스트 계정(tx_id toon_t2_) 후원은 대기함에 '테스트 계정' 표시
  ④ /api/toon/accounts — 주소 확인 · 열쇠는 끝 네 글자만 돌려준다 · 끄기 · 지우기
  ⑤ 리스너 — 수 · 목은 쉰다(한국 시간), 계정마다 tx_id 머리 · 재전송 방어가 따로, 1만 원 미만은 display_only
  ⑥ 조종실 — 시스템 탭 '투네이션 연결' 칸, 주소는 가려지는 칸, 대기함 '🧪 테스트 계정' 표시

⚠️ pausetest 서버(5199)가 필요하다 — runall 이 띄운다.
"""
import calendar
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

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


def st():
    return req('/api/data')[1]


def hist():
    return req('/api/server/status')[1].get('history_count')


def pend():
    return st().get('pending_donations') or []


T0 = int(time.time() * 1000)
print('=' * 74); print('① 1만 원 미만 — 화면에만'); print('=' * 74)
req('/api/server/start_broadcast', {'names': ['가', '나', '다']})
p0, h0 = len(pend()), hist()
tally0 = json.dumps(st().get('donor_tally') or {}, sort_keys=True)
c, r = req('/api/donation', {'name': '초코우유', 'amount': 3000, 'message': '목소리 좋아요', 'tx_id': 'toon_t%d_a' % T0, 'display_only': True})
d = st()
ld = d.get('latest_donation') or {}
chk('리스너가 보낸 3,000원 display_only 는 받는다', c == 200 and r.get('display_only') is True, (c, r))
chk('방송판 띠용 latest_donation 에 실린다', ld.get('name') == '초코우유' and ld.get('amount') == 3000 and ld.get('display_only') is True, ld)
chk('대기함에는 안 들어간다', len(d.get('pending_donations') or []) == p0, (p0, len(d.get('pending_donations') or [])))
chk('정산 장부에도 안 적는다', hist() == h0, (h0, hist()))
chk('후원 순위(이번 방송)도 그대로', json.dumps(d.get('donor_tally') or {}, sort_keys=True) == tally0)

print(); print('=' * 74); print('② 재전송 · 다른 곳 · 1만 원 이상'); print('=' * 74)
t_before = ld.get('time')
c, r = req('/api/donation', {'name': '초코우유', 'amount': 3000, 'message': '목소리 좋아요', 'tx_id': 'toon_t%d_a' % T0, 'display_only': True})
chk('같은 tx_id 로 다시 오면 거른다(띠가 두 번 안 뜬다)', c == 200 and 'Duplicate' in (r.get('message') or '')
    and (st().get('latest_donation') or {}).get('time') == t_before, r)
c, r = req('/api/donation', {'name': '밖에서', 'amount': 3000, 'message': '', 'tx_id': 'tm_%d' % T0, 'display_only': True})
chk('리스너가 아닌 곳이 display_only 를 붙이면 평소대로(대기함)', c == 200 and not r.get('display_only')
    and any(x.get('name') == '밖에서' for x in pend()), r)
c, r = req('/api/donation', {'name': '큰손', 'amount': 20000, 'message': '', 'tx_id': 'toon_t%d_b' % T0, 'display_only': True})
chk('1만 원 이상은 display_only 여도 평소대로(대기함)', c == 200 and not r.get('display_only')
    and any(x.get('name') == '큰손' for x in pend()), r)

print(); print('=' * 74); print('③ 테스트 계정 후원 표시'); print('=' * 74)
h1 = hist()
c, r = req('/api/donation', {'name': '테스터', 'amount': 15000, 'message': '테스트 계정', 'tx_id': 'toon_t2_%d' % T0})
row = next((x for x in pend() if x.get('name') == '테스터'), None)
chk('테스트 계정(toon_t2_) 후원은 대기함에 test_acct', c == 200 and row is not None and row.get('test_acct') is True, row)
chk('본 계정 후원엔 표시가 없다', not (next((x for x in pend() if x.get('name') == '큰손'), {}) or {}).get('test_acct'))
logs = req('/api/server/status')[1].get('logs') or []
chk('장부 출처가 toonation_test 로 남는다', any(l.get('name') == '테스터' and l.get('source') == 'toonation_test' for l in logs)
    and hist() == h1 + 1, [(l.get('name'), l.get('source')) for l in logs[:3]])
for x in pend():
    req('/api/pending/remove/' + x['id'], {})

print(); print('=' * 74); print('④ /api/toon/accounts'); print('=' * 74)
KEY = 'AbCdEf0123456789xyzQ'
req('/api/toon/accounts', {'test_url': ''})
c, r = req('/api/toon/accounts')
chk('처음엔 주소 없음', c == 200 and r['test']['set'] is False, r.get('test'))
c, r = req('/api/toon/accounts', {'test_url': 'https://example.com/widget/alertbox/' + KEY})
chk('투네이션 알림창 주소가 아니면 거절', c == 400 and '알림창' in (r.get('message') or ''), (c, r))
c, r = req('/api/toon/accounts', {'test_url': ' https://toon.at/widget/alertbox/%s?x=1 ' % KEY})
body = json.dumps(r, ensure_ascii=False)
chk('주소를 저장하면 켜진다', c == 200 and r['test']['set'] is True and r['test']['enabled'] is True, r.get('test'))
chk('열쇠는 끝 네 글자만 돌려준다', r['test']['masked'].endswith('••••' + KEY[-4:]) and KEY not in body, r['test']['masked'])
c, r = req('/api/toon/accounts', {'enabled': False})
chk('끄기 — 주소는 그대로', c == 200 and r['test']['enabled'] is False and r['test']['set'] is True, r.get('test'))
c, r = req('/api/toon/accounts', {'test_url': ''})
chk('지우기', c == 200 and r['test']['set'] is False, r.get('test'))
c, r = req('/api/toon/accounts', auth=False)
chk('로그인 없이는 못 본다', c in (401, 403), c)
chk('리스너 상태 칸이 있다(연습 서버엔 리스너가 없어 소식 없음)', 'listener' in req('/api/toon/accounts')[1])

print(); print('=' * 74); print('⑤ 리스너'); print('=' * 74)
sys.path.insert(0, PROJ)
os.environ.setdefault('TOON_ACCOUNTS_FILE', os.path.join(os.environ.get('TEMP', '/tmp'), 'toon_accounts_test.json'))
import toon_listener as TL  # noqa: E402
kst = lambda y, m, d, h: calendar.timegm((y, m, d, h - 9, 0, 0))    # 한국 시각 → epoch
chk('수 · 목(한국 시간)은 테스트 계정이 쉰다', TL.test_resting(kst(2026, 9, 30, 12)) and TL.test_resting(kst(2026, 10, 1, 23))
    and TL.test_resting(kst(2026, 10, 1, 1)))
chk('다른 날은 붙는다(화 · 금 · 일)', not TL.test_resting(kst(2026, 9, 29, 12)) and not TL.test_resting(kst(2026, 10, 2, 12))
    and not TL.test_resting(kst(2026, 10, 4, 20)))
chk('한국 시간으로 잰다 — 수요일 새벽 1시(UTC 화요일)도 쉬는 날', TL.test_resting(kst(2026, 9, 30, 1)))
A = TL.Account('main', '투네이션', 'x', 'toon_')
T = TL.Account('test', '테스트 계정', 'y', 'toon_t2_')
msg = {'code': 101, 'content': {'name': '같은사람', 'amount': 5000, 'message': 'ㅎㅇ'}}
A.connected_at = T.connected_at = time.time()          # 둘 다 막 다시 붙은 참(재전송 방어 구간)
pa, _, sa = TL.to_donation(msg, A)
pt, _, st_ = TL.to_donation(msg, T)
chk('계정마다 tx_id 머리가 다르다', pa['tx_id'].startswith('toon_') and not pa['tx_id'].startswith('toon_t2_')
    and pt['tx_id'].startswith('toon_t2_'))
chk('두 계정에 같은 후원이 동시에 와도 서로를 재전송으로 안 버린다', sa is None and st_ is None)
pa2, _, sa2 = TL.to_donation(msg, A)
chk('같은 계정에서 재연결 직후 똑같은 게 또 오면 재전송으로 거른다', pa2 is None and sa2 == 'replay')
chk('1만 원 미만은 버리지 않고 display_only 로 보낸다(기본값)', TL.SMALL_DISPLAY is True and TL.MIN_AMOUNT == 10000)
LSRC = io.open(os.path.join(PROJ, 'toon_listener.py'), encoding='utf-8').read()
chk('리스너가 1만 원 미만에 display_only 를 붙인다', 'payload["display_only"] = True' in LSRC)
chk('계정마다 따로 붙고, 테스트 계정은 10초마다 설정 · 요일을 본다',
    'account_loop(main_acct)' in LSRC and 'await asyncio.sleep(10)' in LSRC and 'read_test_url()' in LSRC)
chk('예전 부르는 방식(deliver · spool_drain)은 그대로', callable(TL.deliver) and callable(TL.spool_drain))

print(); print('=' * 74); print('⑥ 조종실'); print('=' * 74)
CT = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8').read()
chk('시스템 탭에 투네이션 연결 칸', 'id="toon-box"' in CT and 'onclick="toonSave()"' in CT and 'id="toon-test-on"' in CT)
chk('주소 칸은 가려진다(방송에 조종실이 잡혀도 열쇠가 안 샌다)', '<input type="password" id="toon-test-url"' in CT)
chk('대기함에 🧪 테스트 계정 표시', "don.test_acct ? '<span class=\"pd-test\">🧪 테스트 계정</span> ' : ''" in CT)
chk('시스템 탭을 열면 상태를 읽는다', "loadVersions(); try { toonLoad(); } catch (e) {} }" in CT)
GI = io.open(os.path.join(PROJ, '.gitignore'), encoding='utf-8').read()
chk('열쇠 파일은 저장소에 안 올라간다', 'toon_accounts.json' in GI and 'toon_listener_status.json' in GI)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
