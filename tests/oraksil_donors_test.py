# -*- coding: utf-8 -*-
"""🏆 엔젤오락실 후원 순위(공개) GET /api/oraksil/donors — 크루 사이트 랭킹이 읽는다(2026-10-11)

서버 사본을 새 임시 폴더에 복사해, 깨끗한 SQLite 에 시각을 정해 둔 후원 줄을 넣고
프로세스 안(test_client)에서 확인한다. 운영 · 샌드박스 서버는 건드리지 않는다.

  · 로그인 없이 GET 이 열린다 / POST 는 안 열린다
  · 수요일 방송 시간(_bc_window) 안 것만, day = 그 방송이 시작한 수요일
  · _norm_donor 로 묶고(홍길동님 = 홍길동) 보여줄 이름은 원래 이름(새손님 → '새손님')
  · 익명 · 빼둔 이름 · 테스트용 두 번째 투네이션은 뺀다
  · 금액 · 이름 · 건수 · 날만 — 메시지 · 시각은 안 나간다
  · 1분 기억, 못 읽으면 지난 답 · 처음부터 못 읽으면 502
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(HERE, '..'))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:200]) if detail else ''))


INPROC = r'''
import os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
# ⚠️ 운영 서버처럼 DB 시각은 UTC 로 적히고, 읽을 때 9시간 옮긴다
os.environ.update(HEADLESS='1', ADMIN_PASSWORD='sandboxpw', SESSION_SECRET='sandboxsecret123456',
                  SELF_PING='off', BROADCAST_TZ_SHIFT='9')
sys.path.insert(0, os.getcwd())
import server
server.init_db()
c = server.app.test_client()
H = {'Authorization': 'Bearer sandboxsecret123456'}
def say(ok, name, detail=''):
    print(('OK ' if ok else 'BAD ') + name + ((' -- ' + str(detail)[:200]) if detail else ''), flush=True)

def put(tbl, rows):
    with server.get_db_connection() as conn:
        cur = conn.cursor()
        for ts, nm, amt, src in rows:
            if tbl == 'donation_archive':
                cur.execute("INSERT INTO donation_archive (archived_at, session_label, timestamp, name, amount, "
                            "current_total, message, source, tx_id) VALUES ('x', 'x', ?, ?, ?, 0, ?, ?, '')",
                            (ts, nm, amt, '비밀메시지', src))
            else:
                cur.execute("INSERT INTO donation_history (timestamp, name, amount, current_total, message, "
                            "source, tx_id) VALUES (?, ?, ?, 0, ?, ?, '')", (ts, nm, amt, '비밀메시지', src))
        conn.commit()

# 시각은 UTC — KST 는 +9
put('donation_archive', [
    ('2026-10-07 09:00:00', '구름빵',   500000, 'toonation'),   # 수 18:00 KST → 10-07
    ('2026-10-07 17:30:00', '구름빵님', 200000, 'toonation'),   # 목 02:30 KST → 10-07 (같은 사람)
    ('2026-10-07 18:00:00', '구름빵',     1000, 'toonation'),   # 목 03:00 KST → 창 밖(정각은 끝)
    ('2026-10-07 08:00:00', '바람',      30000, 'manual'),      # 수 17:00 KST → 창 안(정각은 시작)
    ('2026-10-07 07:59:59', '바람',      99000, 'toonation'),   # 수 16:59 KST → 창 밖
    ('2026-10-07 10:00:00', '익명',      50000, 'toonation'),   # 익명 — 사람이 아니다
    ('2026-10-07 10:00:00', ' 익명님 ',  50000, 'toonation'),   # 익명(다듬으면 같다)
    ('2026-10-07 10:05:00', '빼둔이',    70000, 'toonation'),   # 사장님이 빼둔 이름
    ('2026-10-07 10:06:00', '영원',          0, 'toonation'),   # 0원 — 후원이 아니다
])
put('donation_history', [
    ('2026-10-14 09:00:00', '새손님',    30000, 'toonation'),   # 보여줄 이름은 '새손님' 그대로
    ('2026-10-14 09:10:00', '새손님',    20000, 'toonation'),
    ('2026-10-14 09:20:00', '테스터',    99999, 'toonation_test'),   # 테스트 계정 — 뺀다
    ('2026-10-14 09:30:00', '구름빵',    10000, 'toonation'),
    ('2026-10-11 09:00:00', '일요일',    10000, 'toonation'),   # 일요일 — 창 밖
])
r = c.post('/api/donors/excluded', json={'name': '빼둔이'}, headers=H)
say(r.status_code == 200, '빼둘 이름을 넣는다', r.status_code)

r = c.get('/api/oraksil/donors')
say(r.status_code == 200, '로그인 없이 읽힌다', r.status_code)
body = r.get_data(as_text=True)
d = json.loads(body)
want = [
    {'day': '2026-10-14', 'name': '새손님', 'amount': 50000, 'count': 2},
    {'day': '2026-10-14', 'name': '구름빵', 'amount': 10000, 'count': 1},
    {'day': '2026-10-07', 'name': '구름빵', 'amount': 700000, 'count': 2},
    {'day': '2026-10-07', 'name': '바람', 'amount': 30000, 'count': 1},
]
say(d.get('rows') == want, '방송 날 × 사람 합계가 맞다(최근 방송부터 · 많이 낸 순)', d.get('rows'))
say(list(d.keys()) == ['rows'], '모양은 {"rows": [...]} 하나', list(d.keys()))
say(all(sorted(x.keys()) == ['amount', 'count', 'day', 'name'] for x in d.get('rows') or []),
    '줄마다 날 · 이름 · 금액 · 건수만')
say('비밀메시지' not in body and '09:00' not in body and 'toonation' not in body,
    '메시지 · 시각 · 출처가 안 나간다')
say(not any(x['name'] in ('익명', '테스터', '빼둔이', '일요일', '영원') for x in d.get('rows') or []),
    '익명 · 테스트 계정 · 빼둔 이름 · 창 밖 · 0원은 없다')

r = c.post('/api/oraksil/donors', json={})
say(r.status_code in (401, 403, 405), '로그인 없이 POST 는 안 열린다', r.status_code)

# 1분 기억 — 새 후원이 들어와도 기억이 살아 있으면 같은 답
put('donation_history', [('2026-10-14 10:00:00', '늦게온', 40000, 'toonation')])
d2 = c.get('/api/oraksil/donors').get_json()
say(d2.get('rows') == want, '1분 안에는 같은 답(장부를 매번 안 읽는다)')
fa = sys.modules.get('features.archive')
say(fa is not None and hasattr(fa, '_donors'), '기억 칸을 찾았다')
fa._donors['t'] = 0
d3 = c.get('/api/oraksil/donors').get_json()
say({'day': '2026-10-14', 'name': '늦게온', 'amount': 40000, 'count': 1} in (d3.get('rows') or []),
    '1분이 지나면 새 후원이 들어간다')

# 💸 장부는 바뀌었을 때만 다시 읽는다(Supabase 전송량)
def raw(t):
    return (fa._donors.get('raw') or {}).get(t)
arc0, his0 = raw('donation_archive'), raw('donation_history')
fa._donors['t'] = 0
c.get('/api/oraksil/donors')
say(arc0 is not None and raw('donation_archive') is arc0 and raw('donation_history') is his0,
    '장부가 그대로면 다시 안 읽는다(지난 · 이번 방송분 둘 다)')
put('donation_archive', [('2026-09-30 09:00:00', '지난주', 60000, 'toonation')])   # 수 18:00 KST
fa._donors['t'] = 0
d4 = c.get('/api/oraksil/donors').get_json()
say(raw('donation_archive') is not arc0 and raw('donation_history') is his0
    and {'day': '2026-09-30', 'name': '지난주', 'amount': 60000, 'count': 1} in (d4.get('rows') or []),
    '지난 방송분이 늘면 그 표만 다시 읽는다')
with server.get_db_connection() as conn:
    conn.cursor().execute("DELETE FROM donation_history WHERE name = '늦게온'"); conn.commit()
fa._donors['t'] = 0
d5 = c.get('/api/oraksil/donors').get_json()
say(raw('donation_history') is not his0 and not any(x['name'] == '늦게온' for x in d5.get('rows') or []),
    '이번 방송분이 줄어도 다시 읽는다')
d3 = d5

# 못 읽으면 지난 답 · 처음부터 못 읽으면 502
real = fa.get_db_connection
def boom():
    raise RuntimeError('장부 끊김')
fa.get_db_connection = boom
fa._donors['t'] = 0
r = c.get('/api/oraksil/donors')
say(r.status_code == 200 and r.get_json().get('rows') == d3.get('rows'), '못 읽으면 지난 답을 준다', r.status_code)
fa._donors.update(t=0, rows=None)
r = c.get('/api/oraksil/donors')
say(r.status_code == 502 and r.get_json().get('rows') == [], '처음부터 못 읽으면 502 · 빈 목록', r.status_code)
fa.get_db_connection = real
'''

print('=' * 74)
print('🏆 엔젤오락실 후원 순위(공개) /api/oraksil/donors')
print('=' * 74)
SRV = open(os.path.join(ROOT, 'server.py'), encoding='utf-8').read()
chk('로그인 없이 GET 만 연다(method_exempt)', "'/api/oraksil/donors': ('GET',)" in SRV)

tmp = tempfile.mkdtemp(prefix='oraksil_')
try:
    for f in ('server.py', 'show.py'):
        shutil.copy(os.path.join(ROOT, f), tmp)
    shutil.copytree(os.path.join(ROOT, 'features'), os.path.join(tmp, 'features'),
                    ignore=shutil.ignore_patterns('__pycache__'))
    with open(os.path.join(tmp, '_inproc.py'), 'w', encoding='utf-8') as fh:
        fh.write(INPROC)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    env.pop('DATABASE_URL', None)
    p = subprocess.run([sys.executable, '_inproc.py'], cwd=tmp, capture_output=True, timeout=300, env=env)
    out = p.stdout.decode('utf-8', 'replace')
    for ln in out.splitlines():
        if ln.startswith('OK '):
            chk(ln[3:].split(' -- ')[0], True)
        elif ln.startswith('BAD '):
            chk(ln[4:].split(' -- ')[0], False, ln.split(' -- ', 1)[1] if ' -- ' in ln else '')
    if p.returncode != 0 or not any(ln.startswith(('OK ', 'BAD ')) for ln in out.splitlines()):
        chk('프로세스 안 검사가 끝까지 돌았다', False, p.stderr.decode('utf-8', 'replace')[-800:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
