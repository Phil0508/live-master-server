# -*- coding: utf-8 -*-
"""🔌 진행봇 2단계 — 유튜브로 내보내는 길을 **가짜 구글**에 대고 끝까지 돌려본다.

왜 이렇게 하나:
  진짜 유튜브에 붙이려면 사장님 계정과 자격증명이 있어야 한다. 그게 준비되기 전에도
  '주소가 맞는가 · 본문 모양이 맞는가 · 토큰을 제때 바꾸는가 · 방송이 끝났을 때
  다시 찾는가 · 실패해도 안 죽는가' 는 지금 확인할 수 있다.
  여기서 걸러내면, 진짜로 붙일 때 남는 건 "구글이 받아주느냐" 하나뿐이다.

⚠️ 여기서 통과해도 **진짜 유튜브에 올려본 것은 아니다.** 하루 호출 한도와 글자 수
   제한은 문서에 없어서, 첫 실제 전송 때 구글 콘솔에서 재야 한다.
"""
import io
import json
import os
import re
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
sys.path.insert(0, os.path.join(ROOT, 'bot'))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:120]) if detail else ''))


# ── 가짜 구글 ──────────────────────────────────────────────────────────────
G = {
    'tokens': 0,            # 토큰을 몇 번 받아갔나
    'posts': [],            # 올린 채팅 [(경로, 헤더, 본문)]
    'chat_lookups': 0,      # 채팅방을 몇 번 찾았나
    'chat_id': 'CHAT-1',    # 지금 켜져 있는 라이브의 채팅방
    'post_status': 200,     # 다음 전송에 돌려줄 응답
    'post_body': '{}',
    'expires_in': 3600,
}


class Fake(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n).decode('utf-8')
        path = urllib.parse.urlparse(self.path).path
        if path.endswith('/token'):
            q = dict(urllib.parse.parse_qsl(raw))
            if q.get('grant_type') != 'refresh_token' or not q.get('refresh_token'):
                return self._send(400, {'error': 'invalid_grant'})
            G['tokens'] += 1
            return self._send(200, {'access_token': 'AT-%d' % G['tokens'],
                                    'expires_in': G['expires_in']})
        if '/liveChat/messages' in path:
            G['posts'].append((self.path, dict(self.headers), raw))
            if G['post_status'] != 200:
                b = G['post_body'].encode()
                self.send_response(G['post_status'])
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            return self._send(200, {'id': 'MSG-1'})
        return self._send(404, {'error': 'nope'})

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if '/liveBroadcasts' in u.path:
            G['chat_lookups'] += 1
            if not G['chat_id']:
                return self._send(200, {'items': []})
            return self._send(200, {'items': [{'snippet': {'liveChatId': G['chat_id']}}]})
        if '/videos' in u.path:
            G['chat_lookups'] += 1
            return self._send(200, {'items': [{'liveStreamingDetails':
                                               {'activeLiveChatId': 'CHAT-FROM-VIDEO'}}]})
        if '/channels' in u.path:
            return self._send(200, {'items': [{'id': 'UC-BOT',
                                               'snippet': {'title': '엔젤컴퍼니 진행봇'}}]})
        return self._send(404, {'error': 'nope'})

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
BASE = 'http://127.0.0.1:%d' % srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

import youtube as Y   # noqa: E402
Y.TOKEN_URL = BASE + '/token'
Y.API = BASE + '/youtube/v3'
CREDS = {'client_id': 'CID', 'client_secret': 'SEC', 'refresh_token': 'RT'}


def newyt(cfg=None):
    y = Y.YouTube(cfg or {})
    y.creds = dict(CREDS)
    return y


print('=' * 74)
print('① 준비 — 자격증명이 없으면 조용히 알려준다')
print('=' * 74)
y0 = Y.YouTube({})
y0.creds = {'client_id': '', 'client_secret': '', 'refresh_token': ''}
ok, why = y0.ready()
chk('없는 값을 알려준다 (그냥 죽지 않는다)', ok is False and 'client_id' in why, why)
bad = newyt(); bad.creds['refresh_token'] = ''
ok, why = bad.ready()
chk('하나만 비어도 잡는다', ok is False, why)

print()
print('=' * 74)
print('② 연동 — 토큰을 받고 켜져 있는 라이브를 찾는다')
print('=' * 74)
G['tokens'] = 0; G['chat_lookups'] = 0
y = newyt()
ok, why = y.ready()
chk('준비됐다고 답한다', ok is True, why)
chk('토큰을 한 번 받았다', G['tokens'] == 1, G['tokens'])
chk('켜져 있는 라이브를 스스로 찾았다 (주소를 안 붙여넣어도 된다)',
    y.chat_id == 'CHAT-1', y.chat_id)

G['chat_lookups'] = 0
y2 = newyt({'video_id': 'VID123'})
y2.ready()
chk('영상 주소를 적어두면 그쪽을 쓴다', y2.chat_id == 'CHAT-FROM-VIDEO', y2.chat_id)

y3 = newyt({'live_chat_id': 'CHAT-FIXED'})
G['chat_lookups'] = 0
y3.ready()
chk('채팅방을 직접 적어두면 찾지도 않는다',
    y3.chat_id == 'CHAT-FIXED' and G['chat_lookups'] == 0, G['chat_lookups'])

G['chat_id'] = ''
y4 = newyt()
ok, why = y4.ready()
chk('켜져 있는 라이브가 없으면 알려준다', ok is False and '라이브' in why, why)
G['chat_id'] = 'CHAT-1'

print()
print('=' * 74)
print('③ 전송 — 무엇을 어디로 보내는가')
print('=' * 74)
G['posts'] = []; G['tokens'] = 0
y = newyt()
sent, err = y.post('구름이님 5,000원 후원 감사합니다! 🙏')
chk('보냈다고 답한다', sent is True and err == '', (sent, err))
chk('한 번만 보냈다', len(G['posts']) == 1, len(G['posts']))
path, hdr, body = G['posts'][0]
j = json.loads(body)
# ⚠️ 자원 이름은 liveChatMessages 인데 **주소는 liveChat/messages** 다.
#    여기를 liveChatMessages 로 적었다가 진짜 구글에서 빈 404 를 맞았다(2026-09-14).
chk('주소가 맞다 (liveChat/messages · part=snippet)',
    '/youtube/v3/liveChat/messages' in path and 'part=snippet' in path, path)
chk('옛 주소로 되돌아가지 않았다', '/youtube/v3/liveChatMessages' not in path, path)
chk('출입증을 들고 간다', hdr.get('Authorization', '').startswith('Bearer AT-'),
    hdr.get('Authorization'))
chk('보내는 모양이 맞다',
    j.get('snippet', {}).get('type') == 'textMessageEvent'
    and j['snippet'].get('liveChatId') == 'CHAT-1'
    and '감사합니다' in j['snippet'].get('textMessageDetails', {}).get('messageText', ''), j)
chk('한글·이모지가 안 깨진다', '🙏' in j['snippet']['textMessageDetails']['messageText'])

y.post('두 번째')
chk('토큰을 다시 안 받는다 (아직 안 만료)', G['tokens'] == 1, G['tokens'])
y._exp = 0                      # 만료됐다고 치면
y.post('세 번째')
chk('만료되면 스스로 다시 받는다', G['tokens'] == 2, G['tokens'])

long_txt = '가' * 500
y.post(long_txt)
sent_len = len(json.loads(G['posts'][-1][2])['snippet']['textMessageDetails']['messageText'])
# ⚠️ 유튜브 문서에 글자 수 제한이 안 적혀 있다. 200자는 **추측**이라 첫 실제 전송 때 확인해야 한다.
chk('너무 긴 글은 잘라 보낸다 (200자 — 문서에 없어 추측한 값)', sent_len == 200, sent_len)

print()
print('=' * 74)
print('④ 실패 — 봇이 죽지 않고, 다음을 위해 스스로 정리한다')
print('=' * 74)
G['post_status'] = 403
G['post_body'] = json.dumps({'error': {'errors': [{'reason': 'liveChatEnded'}]}})
before = y.chat_id
sent, err = y.post('방송 끝난 뒤')
chk('실패를 그대로 알려준다 (예외로 터지지 않는다)', sent is False and '403' in err, (sent, err))
chk('방송이 끝나면 채팅방을 비운다 (다음에 새로 찾게)',
    before and y.chat_id is None, (before, y.chat_id))
G['chat_lookups'] = 0
G['post_status'] = 200
y.post('새 방송')
chk('다음 전송 때 채팅방을 다시 찾는다', G['chat_lookups'] == 1 and y.chat_id == 'CHAT-1',
    (G['chat_lookups'], y.chat_id))

G['post_status'] = 403
G['post_body'] = json.dumps({'error': {'errors': [{'reason': 'rateLimitExceeded'}]}})
sent, err = y.post('너무 빨리')
chk('너무 빨리 쳤다는 것도 알려준다 (봇이 간격을 늘린다)',
    sent is False and 'rateLimit' in err, err)
chk('그건 채팅방을 안 비운다 (방송은 살아 있다)', y.chat_id == 'CHAT-1', y.chat_id)

G['post_status'] = 500
G['post_body'] = 'not json at all'
sent, err = y.post('서버 오류')
chk('구글이 이상한 답을 줘도 안 죽는다', sent is False and '500' in err, err)
G['post_status'] = 200

print()
print('=' * 74)
print('⑤ 계정 연동 — 누구로 로그인했는지 되짚는다')
print('=' * 74)
import link as LK   # noqa: E402
LK.TOKEN_URL = BASE + '/token'
LK.API = BASE + '/youtube/v3'
tok = LK.post_form(LK.TOKEN_URL, {'client_id': 'CID', 'client_secret': 'SEC',
                                  'refresh_token': 'RT', 'grant_type': 'refresh_token'})
name, cid = LK.whoami(tok['access_token'])
chk('어느 채널에 묶였는지 이름으로 알려준다 (본계정 실수 잡기)',
    name == '엔젤컴퍼니 진행봇' and cid == 'UC-BOT', (name, cid))
chk('채팅 쓰기 권한만 받는다', LK.SCOPE.endswith('youtube.force-ssl'), LK.SCOPE)
chk('갱신 토큰을 받게 돼 있다',
    "'access_type': 'offline'" in io.open(os.path.join(ROOT, 'bot', 'link.py'),
                                          encoding='utf-8').read())

print()
print('=' * 74)
print('⑥ IPv4 로만 나가는가 — 안 그러면 한 번 붙는 데 168초다')
print('=' * 74)
# ⚠️ 방송 컴퓨터는 **나갈 수 없는** IPv6 주소를 갖고 있다(fdee:… · Hamachi).
#    www.googleapis.com 은 AAAA 를 여덟 개 주므로 그대로 두면 그걸 다 기다린 뒤에야
#    IPv4 로 넘어간다 — 실측 168초, 세 번 다 똑같았다. IPv4 로만 붙으면 0.1초.
#    이게 빠지면 봇이 '멈춘 것처럼' 보인다(실제로 연동이 두 번 그렇게 보였다).
import net as NET   # noqa: E402
NETSRC = io.open(os.path.join(ROOT, 'bot', 'net.py'), encoding='utf-8').read()
chk('IPv4 고정 도우미가 있다', hasattr(NET, 'force_ipv4') and 'AF_INET' in NETSRC)
for f in ('announce.py', 'link.py', 'youtube.py'):
    s = io.open(os.path.join(ROOT, 'bot', f), encoding='utf-8').read()
    chk('%s 가 IPv4 로 고정한다' % f, 'force_ipv4()' in s)
NET.undo(); NET.force_ipv4()
chk('두 번 불러도 안전하다', True)
_fam = {a[0] for a in __import__('socket').getaddrinfo('localhost', 80)}
chk('실제로 IPv4 만 돌려준다', _fam == {__import__('socket').AF_INET}, _fam)
NET.undo()

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('⚠️ 여기까지는 **가짜 구글** 이다. 진짜 전송은 사장님이 link.py 를 돌린 뒤에 확인한다.')
print('=' * 74)
srv.shutdown()
if BAD:
    for b in BAD:
        print('  - ' + b)
    sys.exit(1)
