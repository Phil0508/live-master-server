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
c, _ = post('/api/settings/patch', {'notice_enabled': True, 'notice_period': 120,
                                    'notice_speed': 130, 'notice_msgs': MSGS})
d = get()
chk('켜짐·주기·속도·문구가 저장된다',
    c == 200 and d.get('notice_enabled') is True and d.get('notice_period') == 120
    and d.get('notice_speed') == 130 and len(d.get('notice_msgs') or []) == 3,
    (d.get('notice_period'), d.get('notice_speed'), len(d.get('notice_msgs') or [])))

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
chk('화면이 서버 시계를 쓴다', 'Date.now() + serverTimeOffset' in ov)
chk('문구는 구간 번호로 돌아간다', 'Math.floor(now / period) % msgs.length' in ov)
chk('뜨는 시간은 글자 길이와 속도가 정한다',
    'const dur = (viewW + noticeWCache[t]) / speed * 1000;' in ov
    and 'return Math.max(3000, Math.min(dur, period - 1000));' in ov)
chk('폭은 안 보이는 자칸에서 재고 기억해둔다',
    "noticeWCache[t] = mel.scrollWidth || 1;" in ov
    and '.notice-measure { visibility: hidden;' in ov)
# ⚠️ 예전에는 '지금 띄우기' 신호가 2분간 살아 그동안 자동 전광판이 한 번도 안 떴다
chk('수동으로 띄운 것도 한 바퀴면 끝난다 — 그 뒤엔 자동에 자리를 내준다',
    'mEl < noticeDur(String(msgs[mIdx]), viewW, speed, period)' in ov
    and 'mEl < 120000' not in ov)

js = """
// 화면의 식 그대로: 한 바퀴 = (칸 폭 + 글자 폭) / 속도
const period = 120000, speed = 130, viewW = 1002, n = 3;
function durOf(textW) {
  const dur = (viewW + textW) / speed * 1000;
  return Math.max(3000, Math.min(dur, period - 1000));
}
function run(textW) {
  const dur = durOf(textW);
  const seen = [];
  let onCount = 0;
  for (let s = 0; s < 360; s++) {
    const now = s * 1000;
    const idx = Math.floor(now / period) %% n;
    const elapsed = now %% period;
    if (elapsed < dur) { onCount++; if (!seen.includes(idx)) seen.push(idx); }
  }
  return {dur: Math.round(dur), onCount, seen};
}
// 수동으로 띄운 뒤 자동이 되살아나는가 (수동 ts=5s, 한 바퀴 10.8s → 16s 뒤엔 자동 차례)
const dm = durOf(400);
const after = [];
for (const t of [6000, 20000, 121000]) {
  const mEl = t - 5000;
  after.push(mEl >= 0 && mEl < dm ? 'M' : 'auto');
}
console.log(JSON.stringify({short: run(400), long: run(2400), huge: run(999999), after}));
"""
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
    f.write(js.replace('%%', '%'))
    tmp = f.name
try:
    out = subprocess.run(['node', tmp], capture_output=True, text=True, encoding='utf-8')
    j = json.loads(out.stdout) if out.returncode == 0 else {}
finally:
    os.unlink(tmp)
sh, lo, hu = j.get('short') or {}, j.get('long') or {}, j.get('huge') or {}
chk('짧은 문구는 짧게 지나간다 (약 11초)', 10000 < sh.get('dur', 0) < 12000, sh.get('dur'))
chk('긴 문구는 오래 떠 있다 — 읽을 시간이 는다', lo.get('dur', 0) > sh.get('dur', 0) * 2,
    (sh.get('dur'), lo.get('dur')))
chk('아무리 길어도 다음 회차를 밀지 않는다', hu.get('dur') == 119000, hu.get('dur'))
chk('문구 3개가 차례로 돌아간다', sh.get('seen') == [0, 1, 2], sh.get('seen'))
chk('수동으로 띄운 뒤 자동이 되살아난다', j.get('after') == ['M', 'auto', 'auto'],
    j.get('after'))
print('     짧은 문구 %sms · 긴 문구 %sms' % (sh.get('dur'), lo.get('dur')))

print()
print('=' * 74)
print('④-2 오른쪽에서 왼쪽으로 흐르는가')
print('=' * 74)
chk('글자가 칸 오른쪽 밖에서 시작한다', 'position: absolute; top: 50%; left: 100%;' in ov)
chk('칸 폭 + 글자 폭 만큼 왼쪽으로 민다',
    '@keyframes noticeFlow' in ov and 'translate(calc(-100% - var(--nw, 1000px)), -50%)' in ov)
chk('넘친 글자는 칸 밖으로 안 보인다', '.notice-view { position: relative; flex: 1; overflow: hidden; }' in ov)
chk('화면마다 같은 자리를 흐르도록 음수 지연을 쓴다',
    "'ms linear -'" in ov and 'Math.round(elapsed)' in ov)
chk('칸 폭을 재서 넘겨준다', "txt.style.setProperty('--nw', viewW + 'px')" in ov)

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
