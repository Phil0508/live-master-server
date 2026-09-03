# -*- coding: utf-8 -*-
"""지난 방송 후원내역 + 퇴근빵 접기.

■ 후원내역
  방송을 종료할 때마다 회차가 쌓이고, 그 회차만 꺼내 볼 수 있고, 엑셀로 받을 수 있어야 한다.
  후원자 이름과 금액이 담기므로 로그인 없이는 절대 열리면 안 된다.

■ 퇴근빵
  한 상자에 접기가 둘 걸리면 서로 반대로 움직여 영영 안 열린다. 그런 상자가 없는지 본다.
"""
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


def post(path, obj=None):
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), H)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}


def get(path, authed=True):
    hdr = {'Authorization': H['Authorization']} if authed else {}
    try:
        r = urllib.request.urlopen(urllib.request.Request(B + path, headers=hdr), timeout=30)
        return r.status, r
    except urllib.error.HTTPError as e:
        return e.code, e


def donate(nm, amt, tx, msg=''):
    urllib.request.urlopen(urllib.request.Request(
        B + '/api/donation',
        json.dumps({'tx_id': tx, 'name': nm, 'amount': amt, 'message': msg, 'time': '20:00'}).encode(),
        {'Content-Type': 'application/json'}), timeout=20)
    time.sleep(0.2)


print('=' * 74)
print('① 방송을 끝내면 그 회차가 쌓이는가')
print('=' * 74)
stamp = str(int(time.time()))[-6:]
post('/api/restore', {'broadcast_active': True, 'bjs': [{'name': '가', 'score': 0, 'contribution': 0}],
                      'pending_donations': [], 'logs': []})
donate('별빛', 50000, 'toon_ar1_' + stamp, '화이팅')
donate('노을', 30000, 'toon_ar2_' + stamp, '=수식처럼보이는메시지')
before = len(json.load(get('/api/archive/sessions')[1])['sessions'])
c, _ = post('/api/server/end_broadcast')
time.sleep(1.0)
sess = json.load(get('/api/archive/sessions')[1])['sessions']
chk('방송 종료가 정상 처리된다', c == 200, c)
chk('회차가 하나 늘었다', len(sess) == before + 1, '%d → %d' % (before, len(sess)))
newest = sess[0] if sess else {}
chk('그 회차에 2건 · 80,000원', newest.get('count') == 2 and newest.get('total') == 80000, newest)

print()
print('=' * 74)
print('② 회차 내역을 꺼내 볼 수 있는가')
print('=' * 74)
lab = newest.get('label', '')
s, r = get('/api/archive/rows?label=' + urllib.parse.quote(lab))
d = json.load(r)
rows = d.get('rows', [])
chk('내역 2건이 나온다', len(rows) == 2, len(rows))
chk('합계가 맞다', d.get('total') == 80000, d.get('total'))
chk('후원자·금액·메시지가 담긴다',
    rows and rows[0].get('name') == '별빛' and rows[0].get('amount') == 50000,
    rows[0] if rows else None)
s2, _ = get('/api/archive/rows')
chk('회차를 안 고르면 400', s2 == 400, s2)
s3, r3 = get('/api/archive/rows?label=' + urllib.parse.quote('없는회차'))
chk('없는 회차는 빈 목록(에러 아님)', s3 == 200 and json.load(r3).get('rows') == [], s3)

print()
print('=' * 74)
print('③ 엑셀로 받기')
print('=' * 74)
s, r = get('/api/archive/csv?label=' + urllib.parse.quote(lab))
raw = r.read()
txt = raw.decode('utf-8-sig')
chk('내려받기 파일로 온다', 'attachment' in (r.headers.get('Content-Disposition') or ''),
    r.headers.get('Content-Disposition'))
chk('형식이 CSV 하나로만 적힌다',
    (r.headers.get('Content-Type') or '').count('charset') == 1, r.headers.get('Content-Type'))
chk('앞에 BOM 이 있다 (엑셀 한글 안 깨짐)', raw[:3] == b'\xef\xbb\xbf')
chk('머리줄이 있다', txt.startswith('회차,시각,후원자,금액,메시지,경로'), txt[:40])
chk('2건이 담긴다', len(txt.strip().split('\r\n')) == 3, len(txt.strip().split('\r\n')))
# 수식 주입 방어
chk("'=' 로 시작하는 메시지는 따옴표로 막는다", '"\'=수식처럼보이는메시지"' in txt,
    [l for l in txt.split('\r\n') if '수식' in l][:1])
s, r = get('/api/archive/csv')
chk('전체 받기도 된다', s == 200 and len(r.read()) > 0, s)

print()
print('=' * 74)
print('④ 로그인 없이는 열리면 안 된다  ← 후원자 이름·금액이 담긴다')
print('=' * 74)
for p in ('/api/archive/sessions', '/api/archive/rows?label=x', '/api/archive/csv'):
    s, _ = get(p, authed=False)
    chk('%s → 막힘' % p.split('?')[0], s == 401, s)

print()
print('=' * 74)
print('⑤ 한 상자에 접기가 둘이면 영영 안 열린다')
print('=' * 74)
c = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8', errors='replace').read()
chk('제목에 자기 onclick 이 있으면 공통 접기를 안 건다',
    "if (t.getAttribute('onclick')) return;" in c)
# 실제로 그런 상자가 몇 개인지 — 있어도 위 가드가 막아주지만, 개수를 눈에 보이게 남긴다
own = re.findall(r'class="group-title"[^>]*onclick="([a-zA-Z]+)', c)
print('     자기 여닫기를 가진 상자: %s' % (', '.join(sorted(set(own))) or '없음'))
chk('퇴근빵 상자가 그대로 있다', 'id="home-race-box"' in c)
chk('퇴근빵 설정칸이 그대로 있다', 'id="home-race-panel-body"' in c)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
