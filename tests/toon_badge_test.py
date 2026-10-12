# -*- coding: utf-8 -*-
"""💙 투네이션 후원 '투네' 딱지 — 리스너(tx_id toon_)가 보낸 후원의 시그니처 카드에만 via:'toon' 이 실린다(2026-10-13).

서버 사본을 새 임시 폴더에 복사해 프로세스 안(test_client)에서 확인한다. 시그니처 조회(Supabase)는 가짜로 바꾼다.
  · 투네이션 리스너 후원 → 대기줄 항목에 via:'toon'
  · 투네이션 테스트 계정(toon_t2_) · 다시 보기(replay)도 투네이션이라 붙는다
  · 계좌 추천에서 보낸 것(manual_bank_) · 후원 콘솔 수동 송출(manual_) · 수동 재생은 안 붙는다
  · 방송판: 사진 상자 안 왼쪽 위 딱지 · 투네이션 파랑 #519CFF · 흰 글자 · 흰 테두리 · 재생할 때 via 로 켜고 끈다
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
def say(ok, name, detail=''):
    print(('OK ' if ok else 'BAD ') + name + ((' -- ' + str(detail)[:200]) if detail else ''), flush=True)
def last_item(name):
    with server.file_lock:
        q = server.load_data().get('reaction_queue') or []
    return next((x for x in reversed(q) if x.get('donator') == name), None)
def don(body, headers=None):
    r = c.post('/api/donation', json=body, headers=headers or {})
    return r.status_code, r.get_json()

st, j = don({'name': '별빛', 'amount': 10000, 'message': '밍밍 화이팅', 'tx_id': 'toon_abc1'})
it = last_item('별빛')
say(st == 200 and it and it.get('via') == 'toon', '투네이션 리스너 후원 → via toon', (st, j, it and it.get('via')))
st, j = don({'name': '테스터', 'amount': 10000, 'message': '', 'tx_id': 'toon_t2_abc2'})
it = last_item('테스터')
say(it and it.get('via') == 'toon', '투네이션 테스트 계정도 투네이션', it and it.get('via'))
st, j = don({'name': '다시봄', 'amount': 10000, 'message': '', 'tx_id': 'toon_abc3', 'replay': True})
it = last_item('다시봄')
say(it and it.get('via') == 'toon', '대시보드 다시 보기(화면에만)도 투네이션', it and it.get('via'))
st, j = don({'name': '영원', 'amount': 10000, 'message': '밍밍', 'tx_id': 'manual_bank_b123'}, H)
it = last_item('영원')
say(it is not None and 'via' not in it, '계좌 추천에서 보낸 후원은 안 붙는다', it and it.get('via'))
st, j = don({'name': '바람', 'amount': 10000, 'message': '', 'tx_id': 'manual_1791'}, H)
it = last_item('바람')
say(it is not None and 'via' not in it, '후원 콘솔 수동 송출은 안 붙는다', it and it.get('via'))
r = c.post('/api/signature/play', json={'sig_id': 777, 'name': '수동재생'}, headers=H)
it = last_item('수동재생')
say(it is not None and 'via' not in it, '수동 재생(장부 없이)은 안 붙는다', (r.status_code, it and it.get('via')))
pub = c.get('/api/data').get_json()
say(any(x.get('via') == 'toon' for x in (pub.get('reaction_queue') or [])), '방송판(무인증 상태)에도 via 가 간다 — 딱지를 켜야 하니까')
'''

print('=' * 74)
print("💙 투네이션 후원 '투네' 딱지")
print('=' * 74)
OV = open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8', errors='replace').read()
box = OV[OV.find('<div id="reaction-img-box"'):]
box = box[:box.find('</div>\n        <div id="reaction-donator-info"')]
chk('딱지는 사진 상자 안(사진 옆)에 있다', '<div id="reaction-via" aria-hidden="true">투네</div>' in box)
css = re.search(r'#reaction-via \{([^}]*)\}', OV)
css = css.group(1) if css else ''
chk('투네이션 대표 파랑 #519CFF 바탕 · 흰 글자 · 흰 테두리 · 조금 둥근 네모',
    'background: #519CFF' in css and 'color: #fff' in css and 'border: 3px solid #fff' in css and 'border-radius: 12px' in css, css[:160])
chk('왼쪽 위(오른쪽 위는 ×N 연속 딱지 자리)', 'left: -16px' in css and 'top: -16px' in css)
chk('평소엔 숨기고 .on 일 때만', 'display: none' in css and '#reaction-via.on { display: block; }' in OV)
chk("재생할 때 via 가 'toon' 이면 켜고 아니면 끈다", "_viaEl.classList.toggle('on', data.via === 'toon')" in OV)

tmp = tempfile.mkdtemp(prefix='toonbadge_')
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
        chk('프로세스 안 검사가 끝까지 돌았다', False, p.stderr.decode('utf-8', 'replace')[-1200:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
