# -*- coding: utf-8 -*-
"""📊 조종실 클릭 기록 — 방송별로 '무엇을 몇 번' 이 제대로 쌓이는가.

왜 만들었나
  대표님 2026-09-22: 탭 정리를 짐작이 아니라 실제로 누른 기록으로 정하기로 했다(추석 방송부터 쌓는다).

여기서 지키는 것
  ① 같은 것을 여러 번 보내면 더해진다 (덮어쓰지 않는다)
  ② 방송 중이면 '그 방송 시작 시각' 으로, 아니면 '방송 밖' 으로 나뉜다
  ③ 로그인 없이는 쓰지도 읽지도 못한다
  ④ 이상한 값(음수 · 빈 이름 · 너무 많은 칸)은 걸러낸다
  ⑤ 조종실이 실제로 세고 보낸다 · 보는 페이지가 있다

⚠️ pausetest 서버(5199)가 필요하다 — runall 이 띄운다.
"""
import io
import json
import os
import sys
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
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:120]) if detail else ''))


def req(method, path, obj=None, headers=H):
    data = json.dumps(obj).encode() if obj is not None else None
    r = urllib.request.Request(B + path, data, headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def rows_of(session):
    c, d = req('GET', '/api/uistats?session=' + urllib.request.quote(session))
    return {r['key']: r for r in (d.get('rows') or [])}


print('=' * 74)
print('① 더해진다 · ② 방송별로 나뉜다')
print('=' * 74)
c, d = req('POST', '/api/server/start_broadcast', {'names': ['하율', '서아']})
chk('방송 시작', c == 200, (c, d))
c, d = req('POST', '/api/uistats', {'counts': [{'key': 'openTab:tab-roulette', 'label': '탭: 룰렛', 'tab': 'top', 'n': 3},
                                              {'key': 'assignPending', 'label': '후원 배정 (멤버 버튼)', 'tab': 'top', 'n': 5}]})
sess = d.get('session', '')
chk('받는다', c == 200 and d.get('saved') == 2, (c, d))
chk('방송 중이면 시작 시각으로 묶인다', sess.endswith(' 방송') and '방송 밖' not in sess, sess)
req('POST', '/api/uistats', {'counts': [{'key': 'openTab:tab-roulette', 'label': '탭: 룰렛', 'tab': 'top', 'n': 2}]})
r = rows_of(sess)
chk('두 번 보내면 더해진다 (3 + 2 = 5)', r.get('openTab:tab-roulette', {}).get('n') == 5, r.get('openTab:tab-roulette'))
chk('많이 누른 순서로 준다', list(r)[:2] == ['assignPending', 'openTab:tab-roulette'] or r['assignPending']['n'] >= r['openTab:tab-roulette']['n'], list(r))
c, d = req('GET', '/api/uistats')
chk('방송 목록에 뜬다', c == 200 and any(s['session'] == sess and s['total'] == 10 for s in d.get('sessions') or []), d)
req('POST', '/api/server/end_broadcast', {})
c, d = req('POST', '/api/uistats', {'counts': [{'key': 'openTab:tab-system', 'label': '탭: 시스템', 'tab': 'top', 'n': 1}]})
chk("방송이 끝나면 '방송 밖' 으로", '방송 밖' in d.get('session', ''), d)
chk('끝난 방송 기록은 그대로', rows_of(sess).get('openTab:tab-roulette', {}).get('n') == 5)

print()
print('=' * 74)
print('③ 로그인 필요 · ④ 걸러내기')
print('=' * 74)
NOAUTH = {'Content-Type': 'application/json'}
c, _ = req('POST', '/api/uistats', {'counts': [{'key': 'x', 'n': 1}]}, NOAUTH)
chk('로그인 없이 못 쓴다', c in (401, 403), c)
c, _ = req('GET', '/api/uistats', None, NOAUTH)
chk('로그인 없이 못 읽는다', c in (401, 403, 302), c)
c, d = req('POST', '/api/uistats', {'counts': [{'key': '', 'n': 3}, {'key': 'neg', 'n': -4}, {'key': 'zero', 'n': 0}, 'junk']})
chk('빈 이름 · 음수 · 0 · 이상한 값은 안 적는다', c == 200 and d.get('saved') == 0, d)
c, d = req('POST', '/api/uistats', {'counts': [{'key': 'k%d' % i, 'n': 1} for i in range(500)]})
chk('한 번에 받는 양을 자른다 (200칸)', c == 200 and d.get('saved') == 200, d.get('saved'))
c, d = req('POST', '/api/uistats', {'counts': 'nope'})
chk('모양이 틀리면 400', c == 400, c)

print()
print('=' * 74)
print('⑤ 조종실 · 보는 페이지')
print('=' * 74)
rd = lambda f: io.open(os.path.join(PROJ, f), encoding='utf-8', errors='replace').read()
CTL = rd('controller.html')
chk('조종실이 눌린 것을 센다 (지켜보기만)', "document.addEventListener('click'" in CTL and '{ capture: true, passive: true }' in CTL and "fetch('/api/uistats'" in CTL)
chk('탭 이름까지 나눠 센다 (openTab:tab-…)', "m[2].match(/['\"]([A-Za-z_\\-]{2,30})['\"]/)" in CTL)
chk('멤버 이름 버튼은 하나로 묶는다', "assignPending: '후원 배정 (멤버 버튼)'" in CTL)
chk('창을 닫을 때도 보낸다', 'navigator.sendBeacon' in CTL)
chk('로그 탭에서 보는 페이지를 연다', 'href="/uistats.html"' in CTL and os.path.exists(os.path.join(PROJ, 'uistats.html')))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
