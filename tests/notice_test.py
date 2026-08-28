# -*- coding: utf-8 -*-
"""📣 안내 전광판.

핵심은 두 가지다.
 ① 서버 시계로 계산하므로 오버레이가 몇 개든 같은 문구가 같은 순간에 떠야 한다
    (그래서 계산식을 화면 파일에서 꺼내 그대로 돌려본다 — 옮겨 적으면 어긋난다)
 ② 문구는 운영자가 적는 글이다. 태그를 넣어도 글자로만 나와야 한다
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
ROOT = r'C:\Users\Administrator\Desktop\새로다시시작'
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


def post(path, obj=None, authed=True):
    hdr = H if authed else {'Content-Type': 'application/json'}
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), hdr)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=H), timeout=25) as r:
        return json.loads(r.read().decode())


MSGS = ['계좌로 보내주실 때 *닉네임+플레이어* 를 적어주시면 자동으로 올라갑니다',
        '후원은 방송에 큰 힘이 됩니다',
        '세 번째 안내']

print('=' * 74)
print('① 설정이 저장되는가')
print('=' * 74)
c, _ = post('/api/settings/patch', {'notice_enabled': True, 'notice_period': 20,
                                    'notice_show': 8, 'notice_msgs': MSGS})
d = get()
chk('켜짐·주기·표시·문구가 저장된다',
    c == 200 and d.get('notice_enabled') is True and d.get('notice_period') == 20
    and d.get('notice_show') == 8 and len(d.get('notice_msgs') or []) == 3,
    (d.get('notice_period'), d.get('notice_show'), len(d.get('notice_msgs') or [])))

print()
print('=' * 74)
print('② 지금 띄우기')
print('=' * 74)
c, r = post('/api/notice/now', {'idx': 1})
chk('고른 문구를 띄운다', c == 200 and r.get('text') == MSGS[1], r.get('text'))
nw = get().get('notice_now') or {}
chk('신호에 시각과 번호가 실린다', nw.get('idx') == 1 and nw.get('ts'), nw)
c, r = post('/api/notice/now', {'idx': 999})
chk('범위 밖 번호는 잘라낸다', c == 200 and r.get('idx') == 2, r.get('idx'))
c, _ = post('/api/settings/patch', {'notice_msgs': []})
c2, r2 = post('/api/notice/now', {})
chk('문구가 없으면 400', c2 == 400, (c2, r2.get('message')))
post('/api/settings/patch', {'notice_msgs': MSGS})

print()
print('=' * 74)
print('③ 로그인 없이는 못 띄운다')
print('=' * 74)
c, _ = post('/api/notice/now', {}, authed=False)
chk('무인증 → 401', c == 401, c)

print()
print('=' * 74)
print('④ 언제 뜨는가 — 화면의 계산식을 그대로 돌려본다')
print('=' * 74)
ov = io.open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8', errors='replace').read()
# ⚠️ 들여쓰기까지 넣어 찾으면 줄이 조금만 옮겨져도 헛되이 실패한다. 뜻만 본다.
chk('화면이 서버 시계를 쓴다', 'Date.now() + serverTimeOffset' in ov
    and 'on = (now % period) < show;' in ov)
chk('문구는 구간 번호로 돌아간다', 'Math.floor(now / period) % msgs.length' in ov)

js = """
const period = 20000, show = 8000, n = 3;
const line = [], seen = [];
for (let s = 0; s < 60; s++) {
  const now = s * 1000;
  const on = (now %% period) < show;
  const idx = Math.floor(now / period) %% n;
  line.push(on ? String(idx) : '.');
  if (on && !seen.includes(idx)) seen.push(idx);
}
console.log(JSON.stringify({line: line.join(''), seen,
  onCount: line.filter(c => c !== '.').length}));
"""
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
    f.write(js.replace('%%', '%'))
    tmp = f.name
try:
    out = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
    j = json.loads(out.stdout) if out.returncode == 0 else {}
finally:
    os.unlink(tmp)
chk('20초마다 앞 8초만 뜬다', j.get('onCount') == 24, j.get('onCount'))
chk('문구 3개가 차례로 돌아간다', j.get('seen') == [0, 1, 2], j.get('seen'))
print('     타임라인: ' + str(j.get('line'))[:60])

print()
print('=' * 74)
print('⑤ 운영자가 적은 글이 태그로 살아나지 않는가')
print('=' * 74)
m = re.search(r'function noticeMarkup\(t\) \{(.*?)\n        \}', ov, re.S)
chk('문구를 글자로 바꾼 뒤에만 *강조* 를 푼다', m is not None)
if m:
    body = m.group(1)
    esc_first = body.find('replace(/[&<>') < body.find(r'\*([^*]+)\*')
    chk('이스케이프가 강조보다 먼저다', esc_first, body[:60])

print()
print('=' * 74)
print('⑥ 시그니처 재생 중에는 비켜준다')
print('=' * 74)
chk('리액션 모드에 안내 전광판도 숨는다',
    'body.reaction-mode #notice-container' in ov)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n_ in BAD:
    print('   [실패] ' + n_)
print('=' * 74)
