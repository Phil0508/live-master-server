# -*- coding: utf-8 -*-
"""📺 유튜브 재생 목록 · 반복 (2026-10-07 대표님 "유튜브기능에 무한반복이랑 리스트 기능").

 ① 제목 창구(/api/yt/info) — 로그인해야 · 영상 번호(11자)만 받는다 (진짜 유튜브는 부르지 않는다)
 ② 조종실 — 반복 세 가지 · 곡이 끝나면 다음/처음/같은 곡 · 못 트는 곡은 건너뛰기 · 목록은 이 브라우저에 기억
    · 플레이어는 한 번 만들고 곡만 바꾼다(시그니처가 BGM 을 잠깐 멈추는 코드가 ytPlayer 를 쥐고 있다)
 ③ 목록 화면은 글자로만 그린다(유튜브 제목에 태그가 있어도 실행되지 않게)
※ 실제 재생(끝나면 다음 곡 · 한 곡 반복 · 반복 끔 · 재생목록 200곡 읽기 · 막힌 영상 건너뛰기)은 2026-10-07 브라우저로 확인했다.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Authorization': 'Bearer sandboxsecret123456'}
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


def get(path, authed=True):
    req = urllib.request.Request(B + path, headers=H if authed else {})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


print('=' * 74)
print('① 제목 창구')
print('=' * 74)
c, _ = get('/api/yt/info?id=dQw4w9WgXcQ', authed=False)
chk('로그인 없이는 막힌다', c in (401, 403, 302), c)
for bad in ('', 'short', 'x' * 12, 'abc def ghi', '../../etc/p'):
    c, j = get('/api/yt/info?id=' + urllib.request.quote(bad))
    chk('영상 번호가 아니면 400: %r' % bad, c == 400, (c, j))

print('=' * 74)
print('② 조종실')
print('=' * 74)
ct = open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
js = ct[ct.index('const YTL_KEY'):ct.index('function toggleYtPlay()')]
chk('반복 세 가지(전체 · 한 곡 · 끔), 기본은 전체 반복', "all: '🔁 전체 반복', one: '🔂 한 곡 반복', off: '➡️ 반복 끔'" in js
    and "mode: 'all'" in js)
chk('곡이 끝나면(ENDED) 반복 · 다음 곡', 'if (event.data === YT.PlayerState.ENDED) ytlOnEnded();' in js)
chk('한 곡 반복은 처음으로 되감아 다시', "ytl.mode === 'one'" in js and 'ytPlayer.seekTo(0, true); ytPlayer.playVideo();' in js)
chk('마지막 곡 뒤: 전체 반복이면 처음으로 · 끔이면 멈춤', "ytlPlay(last ? 0 : ytl.idx + 1, true)" in js
    and "last && ytl.mode === 'off' && !manual" in js)
chk('못 트는 곡은 건너뛰고, 다 막혔으면 멈춘다', "'onError': onPlayerError" in js and 'ytlBadRun >= ytl.items.length' in js)
chk('플레이어는 한 번 만들고 곡만 바꾼다', 'ytPlayer.loadVideoById(id)' in js and js.count('new YT.Player(') == 2)   # 본 플레이어 + 재생목록 읽기용
chk('목록은 이 브라우저에 기억(예전 한 곡 기억도 이어받음)', "const YTL_KEY = 'yt_playlist_v1'" in js and "localStorage.getItem('last_yt_tab_id')" in js)
chk('재생목록 주소(list=)도 받는다', 'function extractYtListId' in js and 'ytlImportList(list)' in js)
chk('쇼츠 주소도 알아본다', 'shorts\\/' in js)
chk('맨 윗줄 ⏭ 다음 곡 단추', 'id="yt-next-btn"' in ct and 'onclick="ytlNext(true)"' in ct)
chk('목록 칸 · 반복 단추가 있다', 'id="yt-list"' in ct and 'id="ytl-mode"' in ct)

print('=' * 74)
print('③ 목록은 글자로만')
print('=' * 74)
render = js[js.index('function ytlRender()'):js.index('function ytlAdd(')]
chk('제목 · 채널은 textContent', 't.textContent = it.title' in render and 'a.textContent =' in render)
chk('innerHTML 은 아이콘(고정 글자)에만', all("'<i class=\"fa-solid '" in ln for ln in render.splitlines() if 'innerHTML' in ln),
    [ln.strip() for ln in render.splitlines() if 'innerHTML' in ln])
chk('썸네일 주소의 영상 번호는 11자 영숫자만(YTL_ID 로 거른 것)', 'YTL_ID.test' in js
    and re.search(r"const YTL_ID = /\^\[A-Za-z0-9_-\]\{11\}\$/", js) is not None)

print('\n' + '=' * 74)
print('결과: 통과 %d · 실패 %d' % (len(OK), len(BAD)))
for b in BAD:
    print('  ✗', b)
sys.exit(1 if BAD else 0)
