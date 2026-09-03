# -*- coding: utf-8 -*-
"""서버가 500 으로 터지는 길이 남았는지 전수 점검.

모든 POST 엔드포인트에 ① 빈 몸통 ② 이상한 타입 ③ 극단값 을 넣어보고
500(서버가 예외로 넘어진 것)이 나오는 곳을 찾는다.
400/404 는 '곱게 거절한 것'이라 정상이다.
"""
import io, json, os, re, sys, urllib.request, urllib.error
sys.stdout.reconfigure(encoding='utf-8')

B = 'http://127.0.0.1:5199'
TOK = 'sandboxsecret123456'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOK}
# ⚠️ 샌드박스 자리를 짐작하지 않는다 — 임시 폴더로 옮기면서 통째로 죽었다.
#    여기서 필요한 것은 '서버의 POST 길 목록' 뿐이라 저장소 원본을 읽으면 된다.
_ROOT = (os.environ.get('LM_PROJECT_ROOT')
         or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
SRC = io.open(os.path.join(_ROOT, 'server.py'), encoding='utf-8').read()

routes = re.findall(r"@app\.route\('([^']+)'(?:,\s*methods=\[([^\]]+)\])?\)", SRC)
posts = [u for u, m in routes if m and 'POST' in m]

# 경로 변수는 그럴듯한 값으로 채운다
def fill(u):
    u = re.sub(r'<int:[^>]+>', '1', u)
    u = re.sub(r'<string:[^>]+>', 'zzz', u)
    u = re.sub(r'<path:[^>]+>', 'zzz', u)
    u = re.sub(r'<[^>]+>', 'zzz', u)
    return u

WEIRD = [
    ('빈 몸통', {}),
    ('전부 None', {'id': None, 'name': None, 'amount': None, 'delta': None, 'message': None,
                   'players': None, 'picks': None, 'ids': None, 'scope': None, 'action': None,
                   'minutes': None, 'enabled': None, 'done': None, 'cols': None, 'target': None,
                   'tier': None, 'items': None, 'winner': None, 'text': None, 'color': None}),
    ('타입 뒤집기', {'id': [], 'name': {}, 'amount': 'abc', 'delta': {}, 'message': 123,
                     'players': 'x', 'picks': 'x', 'ids': 5, 'scope': 9, 'action': [],
                     'minutes': 'x', 'enabled': 'yes', 'done': 'no', 'cols': -1, 'target': -5,
                     'items': 'x', 'winner': [], 'text': None, 'color': 7}),
    ('극단값', {'id': 10**18, 'name': '가' * 5000, 'amount': -10**18, 'delta': 10**15,
                'message': '나' * 20000, 'players': ['x'] * 500, 'picks': list(range(500)),
                'ids': list(range(500)), 'scope': 'rank', 'minutes': 10**9, 'cols': 10**6,
                'target': 10**6, 'items': [{'name': 'x', 'delta': 'y'}] * 50}),
]

crashes, tested = [], 0
for u in posts:
    url = B + fill(u)
    for label, body in WEIRD:
        tested += 1
        try:
            r = urllib.request.urlopen(
                urllib.request.Request(url, json.dumps(body).encode(), H), timeout=25)
            code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
            msg = e.read()[:150].decode('utf-8', 'replace')
        except Exception as e:
            crashes.append((u, label, '연결끊김 ' + str(e)[:50]))
            continue
        if code == 500:
            crashes.append((u, label, msg if 'msg' in dir() else ''))

# 깨진 JSON / 빈 본문 / 잘못된 Content-Type
for u in posts[:12]:
    url = B + fill(u)
    for label, raw, ct in [('깨진 JSON', b'{"a":', 'application/json'),
                           ('빈 본문', b'', 'application/json'),
                           ('JSON 아님', b'hello', 'text/plain')]:
        tested += 1
        try:
            urllib.request.urlopen(urllib.request.Request(
                url, raw, {'Content-Type': ct, 'Authorization': 'Bearer ' + TOK}), timeout=20)
        except urllib.error.HTTPError as e:
            if e.code == 500:
                crashes.append((u, label, e.read()[:120].decode('utf-8', 'replace')))
        except Exception as e:
            crashes.append((u, label, '연결끊김 ' + str(e)[:40]))

print('=' * 74)
print('POST 엔드포인트 %d개 × 이상한 입력 → 요청 %d건' % (len(posts), tested))
print('=' * 74)
if crashes:
    print('서버가 500 으로 넘어진 곳 %d건:' % len(crashes))
    seen = set()
    for u, label, msg in crashes:
        k = (u, label)
        if k in seen:
            continue
        seen.add(k)
        print('  [%s] %s' % (u, label))
        print('        %s' % str(msg).replace('\n', ' ')[:130])
else:
    print('500 으로 넘어진 곳 없음 ✅')

# 폭격 뒤에도 살아 있는가
try:
    r = urllib.request.urlopen(urllib.request.Request(B + '/api/server/status', headers=H), timeout=20)
    print('\n폭격 뒤 서버 응답: %d ✅' % r.status)
except Exception as e:
    print('\n폭격 뒤 서버가 죽었다: %s' % e)
print('=' * 74)
