# -*- coding: utf-8 -*-
"""⏸️ VIP 등급 끔 — 대표님 2026-10-13 "다시 말할 때까지 없애자, 너무 헷갈린다".

서버 사본을 새 임시 폴더에 복사해 프로세스 안(test_client)에서 확인한다. 시그니처 조회(Supabase)는 가짜로 바꾼다.
  · 후원이 쌓여 순위가 생겨도 등급(vip_live)은 비어 있다 — 방송판(무인증) · 조종실(로그인) 둘 다
  · 직접 준 등급 목록(/api/vips)도 비고, 새로 등록하면 이유를 말하고 막는다(409)
  · 순위 자체(조종실 순위 · 순위에서 빼기)는 그대로 돈다 — 등급만 빈다
  · AI 도 등급을 말하지 않는다
  · 검사 서버만 LM_VIP_ON=1 로 켤 수 있다(vip_test 가 등급 계산을 계속 보게)
  · 조종실 VIP 칸에 '꺼져 있음' 안내
"""
import os
import re
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
os.environ.pop('NVIDIA_API_KEY', None)
sys.path.insert(0, os.getcwd())
import server
server.init_db()
SIG = {'id': 777, 'amount': 10000, 'title': '시험시그', 'image_url': '/x.png', 'sound_url': '/x.mp3', 'duration': 5}
server.supabase_match_signature = lambda amount: dict(SIG)
server.supabase_list_signatures = lambda: [dict(SIG)]
server.supabase_get_signature = lambda sid: dict(SIG)
server._supabase_ready = lambda: True
c = server.app.test_client()
H = {'Authorization': 'Bearer sandboxsecret123456'}
WANT_ON = os.environ.get('LM_VIP_ON') == '1'
def say(ok, name, detail=''):
    print(('OK ' if ok else 'BAD ') + name + ((' -- ' + str(detail)[:200]) if detail else ''), flush=True)

for i, (nm, amt) in enumerate([('구름빵', 500000), ('별빛', 300000), ('영원', 100000), ('바람', 50000)]):
    r = c.post('/api/donation', json={'name': nm, 'amount': amt, 'message': '', 'tx_id': 'toon_vipoff_%d' % i})
    assert r.status_code == 200, r.get_json()

import features.vip as fv
if WANT_ON:
    say(fv.VIP_ON is True, '검사 서버(LM_VIP_ON=1)에서는 켜진다')
    live = c.get('/api/data').get_json().get('vip_live') or {}
    say(len(live) == 4 and any(v.get('grade') == 'VVIP' for v in live.values()), '켜면 등급이 다시 계산된다(1위 VVIP …)', live)
    raise SystemExit(0)

say(fv.VIP_ON is False, '운영 기본값은 꺼짐')
pub = c.get('/api/data').get_json()
say(pub.get('vip_live') == {} and pub.get('vip_on') is False, '방송판(무인증 상태): 등급 없음 · vip_on false', (pub.get('vip_live'), pub.get('vip_on')))
say(len(pub.get('donor_tally') or {}) == 4, '후원 순위(donor_tally)는 그대로 쌓인다', list((pub.get('donor_tally') or {}).keys()))
au = c.get('/api/data', headers=H).get_json()
say(au.get('vip_live') == {} and au.get('vip_on') is False, '조종실(로그인 상태): 등급 없음 · vip_on false')
r = c.get('/api/vips').get_json()
say(r.get('vips') == [] and r.get('off') is True, '직접 준 등급 목록도 빈다(방송판이 읽는 /api/vips)', r)
r = c.post('/api/vips', json={'name': '구름빵', 'grade': 'VVIP'}, headers=H)
say(r.status_code == 409 and r.get_json().get('off') and '꺼져' in r.get_json().get('message', ''),
    '꺼져 있는 동안 새로 등록하면 이유를 말하고 막는다', (r.status_code, r.get_json()))
r = c.get('/api/vips/candidates', headers=H).get_json()
rows = r.get('rows') or []
say(r.get('vip_on') is False and [x['name'] for x in rows] == ['구름빵', '별빛', '영원', '바람'] and all(not x['grade'] for x in rows),
    '조종실 순위는 그대로 · 등급 칸만 빈다', rows)
import features.ai as fa
say(fa._ai_vip_list() == [], 'AI 도 등급을 말하지 않는다')
'''

print('=' * 74)
print('⏸️ VIP 등급 끔')
print('=' * 74)
VSRC = open(os.path.join(ROOT, 'features', 'vip.py'), encoding='utf-8').read()
chk('스위치 한 줄: VIP_ON = False', re.search(r'^VIP_ON = False$', VSRC, re.M) is not None)
CTL = open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
chk("조종실 VIP 칸에 '꺼져 있음' 안내 · 등급 칸 숨김",
    'id="vip-off-note"' in CTL and "const vipOff = gd.vip_on === false;" in CTL
    and "tiersEl.style.display = vipOff ? 'none' : 'flex'" in CTL)
OV = open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8', errors='replace').read()
chk('방송판 VIP 판정은 vip_live · /api/vips 두 곳에서만 온다(둘 다 비면 등급 없음)',
    'const lv = window.vipLive || {};' in OV and "fetch('/api/vips')" in OV and OV.count('window.vipLive =') == 1)

tmp = tempfile.mkdtemp(prefix='vipoff_')
try:
    for f in ('server.py', 'show.py'):
        shutil.copy(os.path.join(ROOT, f), tmp)
    shutil.copytree(os.path.join(ROOT, 'features'), os.path.join(tmp, 'features'),
                    ignore=shutil.ignore_patterns('__pycache__'))
    with open(os.path.join(tmp, '_inproc.py'), 'w', encoding='utf-8') as fh:
        fh.write(INPROC)
    for on in (False, True):
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        for k in ('DATABASE_URL', 'NVIDIA_API_KEY', 'DONATION_KEY', 'LM_VIP_ON'):
            env.pop(k, None)
        if on:
            env['LM_VIP_ON'] = '1'
        for db in ('live_master.db', 'live_master.db-wal', 'live_master.db-shm'):
            try:
                os.remove(os.path.join(tmp, db))
            except OSError:
                pass
        p = subprocess.run([sys.executable, '_inproc.py'], cwd=tmp, capture_output=True, timeout=300, env=env)
        out = p.stdout.decode('utf-8', 'replace')
        for ln in out.splitlines():
            if ln.startswith('OK '):
                chk(ln[3:].split(' -- ')[0], True)
            elif ln.startswith('BAD '):
                chk(ln[4:].split(' -- ')[0], False, ln.split(' -- ', 1)[1] if ' -- ' in ln else '')
        if p.returncode != 0 or not any(ln.startswith(('OK ', 'BAD ')) for ln in out.splitlines()):
            chk('프로세스 안 검사가 끝까지 돌았다(%s)' % ('켬' if on else '끔'), False, p.stderr.decode('utf-8', 'replace')[-1200:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
