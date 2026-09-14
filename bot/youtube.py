# -*- coding: utf-8 -*-
"""유튜브 라이브 채팅에 한 줄 올리는 부분. (진행봇 2단계)

announce.py 는 --live 일 때만 이 파일을 불러온다. 입 막고 돌릴 때는 아예 안 쓴다.

⚠️ 구글 클라이언트 라이브러리를 쓰지 않는다. 표준 라이브러리로 충분하고,
   새 의존성은 방송 컴퓨터에서 문제가 생길 자리를 하나 더 만든다.

필요한 값 — 환경변수 또는 bot/token.json (⚠️ token.json 은 저장소에 올리지 않는다):
    YT_CLIENT_ID · YT_CLIENT_SECRET · YT_REFRESH_TOKEN
받는 법은 README.md 참고.
"""
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# ⏳ 동의 화면이 '테스트' 상태면 갱신 토큰이 **7일마다** 만료된다(구글 규칙).
#    그러면 봇이 일주일마다 조용히 멈춘다 — 원인을 짐작하게 두지 않는다.
EXPIRED_HINT = ("갱신 토큰이 만료된 것일 수 있습니다. 구글 클라우드 "
                "'OAuth 동의 화면'이 '테스트' 상태면 7일마다 만료됩니다 — "
                "'프로덕션으로 게시'로 바꾸고 python bot/link.py 를 다시 돌려주세요.")
TOKEN_URL = 'https://oauth2.googleapis.com/token'
API = 'https://www.googleapis.com/youtube/v3'


def _post(url, data, headers=None, form=False):
    body = (urllib.parse.urlencode(data).encode() if form
            else json.dumps(data, ensure_ascii=False).encode('utf-8'))
    h = {'Content-Type': 'application/x-www-form-urlencoded' if form else 'application/json'}
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h, method='POST')
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


class YouTube:
    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.chat_id = (self.cfg.get('live_chat_id') or '').strip() or None
        self._access, self._exp = None, 0
        self.creds = self._load_creds()

    def _load_creds(self):
        c = {k: os.environ.get('YT_' + k.upper(), '')
             for k in ('client_id', 'client_secret', 'refresh_token')}
        if not all(c.values()):
            try:
                with io.open(os.path.join(HERE, 'token.json'), encoding='utf-8') as f:
                    j = json.load(f)
                for k in c:
                    c[k] = c[k] or str(j.get(k) or '')
            except Exception:
                pass
        return c

    def ready(self):
        missing = [k for k, v in self.creds.items() if not v]
        if missing:
            return False, '없는 값: ' + ', '.join(missing)
        try:
            self._token()
        except Exception as e:
            # ⏳ 제일 흔한 원인이 '7일 만료' 다. 짐작하게 두지 말고 이유를 찍어준다.
            # 구글은 만료된 갱신 토큰에 401 을 돌려준다(400 이 아니다 — 실제로 쏴서 확인했다)
            _e = str(e)
            hint = ('  ← ' + EXPIRED_HINT) if ('401' in _e or '400' in _e or 'invalid_grant' in _e) else ''
            return False, f'토큰을 못 받았습니다 ({e}){hint}'
        try:
            self._chat()
        except Exception as e:
            return False, f'라이브 채팅을 못 찾았습니다 ({e})'
        return True, ''

    # ── 접근 토큰. 만료 1분 전에 미리 바꾼다 ──
    def _token(self):
        if self._access and time.time() < self._exp - 60:
            return self._access
        j = _post(TOKEN_URL, {'client_id': self.creds['client_id'],
                              'client_secret': self.creds['client_secret'],
                              'refresh_token': self.creds['refresh_token'],
                              'grant_type': 'refresh_token'}, form=True)
        self._access = j['access_token']
        self._exp = time.time() + int(j.get('expires_in') or 3600)
        return self._access

    def _auth(self):
        return {'Authorization': 'Bearer ' + self._token()}

    # ── 어느 채팅방에 칠 것인가 ──
    def _chat(self):
        """① 설정에 적어둔 값 → ② 영상 id 로 조회 → ③ 지금 켜져 있는 내 라이브 자동 찾기.
        ③ 이 있어서 방송마다 주소를 붙여넣지 않아도 된다."""
        if self.chat_id:
            return self.chat_id
        vid = (self.cfg.get('video_id') or '').strip()
        if vid:
            j = _get(f'{API}/videos?part=liveStreamingDetails&id={urllib.parse.quote(vid)}',
                     self._auth())
            items = j.get('items') or []
            if items:
                self.chat_id = ((items[0].get('liveStreamingDetails') or {})
                                .get('activeLiveChatId'))
        if not self.chat_id:
            j = _get(f'{API}/liveBroadcasts?part=snippet&broadcastStatus=active'
                     f'&broadcastType=all&mine=true', self._auth())
            for it in (j.get('items') or []):
                cid = (it.get('snippet') or {}).get('liveChatId')
                if cid:
                    self.chat_id = cid
                    break
        if not self.chat_id:
            raise RuntimeError('켜져 있는 라이브가 없습니다')
        return self.chat_id

    def post(self, text):
        """한 줄 올린다. (성공?, 실패 사유) 를 돌려준다 — 봇은 실패해도 계속 돈다.

        ⚠️ 200자는 **추측이다.** 유튜브 문서에 글자 수 제한이 안 적혀 있다(찾아봤다).
           채팅창이 실제로 200자에서 막히길래 그 값을 썼다. 첫 실제 전송 때
           길게 한 번 보내서 확인할 것 — 잘리거나 거부당하면 이 숫자를 고친다.
        """
        try:
            body = {'snippet': {'liveChatId': self._chat(),
                                'type': 'textMessageEvent',
                                'textMessageDetails': {'messageText': text[:200]}}}
            _post(f'{API}/liveChatMessages?part=snippet', body, self._auth())
            return True, ''
        except urllib.error.HTTPError as e:
            detail = (e.read() or b'').decode('utf-8', 'replace')[:300]
            # 방송이 끝나 채팅방이 닫혔으면 다음번에 다시 찾게 비운다
            if 'liveChatEnded' in detail or 'liveChatNotFound' in detail:
                self.chat_id = None
            return False, f'{e.code} {detail}'
        except Exception as e:
            return False, str(e)
