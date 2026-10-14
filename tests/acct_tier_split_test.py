# -*- coding: utf-8 -*-
"""🎞️ 계좌 고액후원 영상 — 60~70만 구간을 60만 · 70만 으로 나눔(대표님 2026-10-14 "70만원 영상 만들었는데 칸이 없다").

서버 사본을 임시 폴더에서 실제 load_data 로 돌린다(합치는 고리를 베끼지 않는다).
  · 옛 저장본(60~70만 칸에 영상)이 그대로 60만 칸으로 남는다 — 영상 주소는 금액(min)으로 붙어 있다
  · 70만 칸이 새로 생기고 비어 있다(조종실에서 영상을 넣으면 된다)
  · 다른 칸 영상(80~90만)도 그대로
  · 구간 번호로 트는 /api/account/play 가 새 순서로 맞게 튼다(60만 → 옛 영상, 70만 → 아직 없음)
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
os.environ.update(HEADLESS='1', ADMIN_PASSWORD='sandboxpw', SESSION_SECRET='sandboxsecret123456', SELF_PING='off')
sys.path.insert(0, os.getcwd())
import server
server.init_db()
def say(ok, name, detail=''):
    print(('OK ' if ok else 'BAD ') + name + ((' -- ' + str(detail)[:200]) if detail else ''), flush=True)

# 옛 저장본 — 60~70만 칸(600000)에 영상, 80~90만 칸에도 영상
OLD = [{"min": 200000, "label": "20만", "video": ""}, {"min": 300000, "label": "30만", "video": ""},
       {"min": 400000, "label": "40만", "video": ""}, {"min": 500000, "label": "50만", "video": ""},
       {"min": 600000, "label": "60~70만", "video": "https://x.invalid/acct_600000.mp4?v=1"},
       {"min": 800000, "label": "80~90만", "video": "yt80abcdefg"},
       {"min": 1000000, "label": "100만", "video": ""}, {"min": 2000000, "label": "200만", "video": ""},
       {"min": 3000000, "label": "300만", "video": ""}, {"min": 5000000, "label": "500만", "video": ""}]
st = server.load_data()
st['account_video_tiers'] = OLD
server.save_data(st, sync=True)

server.MEMORY_STATE = None          # 서버를 다시 켠 것처럼 저장본에서 다시 읽는다
st = server.load_data()
T = st['account_video_tiers']
by = {t['min']: t for t in T}
say(len(T) == 11, '구간이 11개(60~70만 → 60만 · 70만)', [t['label'] for t in T])
say(by.get(600000, {}).get('label') == '60만' and by[600000]['video'] == 'https://x.invalid/acct_600000.mp4?v=1',
    '옛 60~70만 영상은 60만 칸에 그대로', by.get(600000))
say(by.get(700000, {}).get('label') == '70만' and by[700000]['video'] == '', '70만 칸이 새로 생기고 비어 있다', by.get(700000))
say(by.get(800000, {}).get('video') == 'yt80abcdefg', '80~90만 영상도 그대로', by.get(800000))
say([t['min'] for t in T] == sorted(t['min'] for t in T), '금액 순서대로')

c = server.app.test_client()
H = {'Authorization': 'Bearer sandboxsecret123456'}
i60 = [t['min'] for t in T].index(600000)
i70 = [t['min'] for t in T].index(700000)
r = c.post('/api/account/play', json={'tier': i60}, headers=H).get_json()
say(r.get('played') is True and r.get('label') == '60만', '60만 칸을 누르면 옛 영상이 나온다', r)
r = c.post('/api/account/play', json={'tier': i70}, headers=H).get_json()
say(r.get('played') is False and r.get('reason') == 'no_video' and r.get('label') == '70만', '70만 칸은 영상을 넣기 전까지 안 튼다', r)
'''

tmp = tempfile.mkdtemp(prefix='acctsplit_')
try:
    for f in ('server.py', 'show.py'):
        shutil.copy(os.path.join(ROOT, f), tmp)
    shutil.copytree(os.path.join(ROOT, 'features'), os.path.join(tmp, 'features'),
                    ignore=shutil.ignore_patterns('__pycache__'))
    with open(os.path.join(tmp, '_inproc.py'), 'w', encoding='utf-8') as fh:
        fh.write(INPROC)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    for k in ('DATABASE_URL', 'NVIDIA_API_KEY', 'DONATION_KEY'):
        env.pop(k, None)
    p = subprocess.run([sys.executable, '_inproc.py'], cwd=tmp, capture_output=True, timeout=300, env=env)
    out = p.stdout.decode('utf-8', 'replace')
    for ln in out.splitlines():
        if ln.startswith('OK '):
            chk(ln[3:].split(' -- ')[0], True)
        elif ln.startswith('BAD '):
            chk(ln[4:].split(' -- ')[0], False, ln.split(' -- ', 1)[1] if ' -- ' in ln else '')
    if p.returncode != 0 or not any(ln.startswith(('OK ', 'BAD ')) for ln in out.splitlines()):
        chk('프로세스 안 검사가 끝까지 돌았다', False, p.stderr.decode('utf-8', 'replace')[-1500:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
