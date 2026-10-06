# -*- coding: utf-8 -*-
"""🕹️ 버전 되돌리기 / 올리기 · 패치노트 — 옛 features/versions.py 그대로(규칙 · 숫자 · 말을 안 바꿨다).

GET  /api/version/list    (로그인) 고를 수 있는 최근 20개 · 지금 버전 · 고정 여부 · 재시작이 덜 됐는지
POST /api/version/switch  (로그인) {sha} — 목록에 있는 것만. 고정 표시(DEPLOY_PIN)를 남기고 옮긴 뒤 재시작
POST /api/version/latest  (로그인) 고정을 풀고 최신(main)으로
GET  /api/patchnotes      (로그인) PATCHNOTES.md 를 '## 날짜' · '- [분류] 내용' 으로 읽는다

옛 규칙 그대로
  - 자동 배포(2분마다 reset --hard origin/main)와 싸우지 않게 DEPLOY_PIN 파일로 '이 버전에 고정' 을 알린다.
  - 고를 수 있는 것은 저장소에 이미 올라간 최근 커밋뿐(아무 번호나 받으면 남의 갈래 코드를 서버에서 돌릴 수 있다).
  - 응답을 먼저 보내고 1초 뒤 재시작한다(재시작이 지금 이 프로세스를 죽인다). 권한이 없으면 자동 배포에 맡긴다.
  - 'V번호' = 그 커밋까지 쌓인 커밋 수.
v2 에서 다른 것
  - 재시작할 서비스: LM2_RESTART_UNITS(빈칸으로 나눔) — 기본 'livemaster-v2 toon-listener livemaster-bot-v2'.
  - '이 버전에도 버전 화면이 있나' 는 v2 쪽 파일(v2/server/domain/versions.py)에서 찾는다.
    ⚠️ v2 가 없던 옛 버전으로 되돌리면 v2 서비스가 못 뜬다 — 그런 버전은 has_ui=False 로 미리 알린다.
  - git 은 명령 줄(bus) 밖에서(asyncio.to_thread) 부른다 — 느린 fetch 가 방송 명령을 막지 않게.
"""
import asyncio
import os
import subprocess
import threading

from fastapi.responses import JSONResponse

from .legacy import route
from .preflight import REPO

DEPLOY_PIN_FILE = os.path.join(REPO, 'DEPLOY_PIN')
VERSION_LIST_MAX = 20
UI_FILE = 'v2/server/domain/versions.py'


def _units():
    raw = os.environ.get('LM2_RESTART_UNITS')
    return [u for u in (raw if raw is not None else 'livemaster-v2 toon-listener livemaster-bot-v2').split() if u]


def _git(*args, timeout=25):
    """저장소 폴더에서 git — (stdout, 성공여부). ⚠️ encoding 을 못박는다(한글 커밋 메시지가 윈도우에서 깨져 빈 값이 됐다)."""
    try:
        r = subprocess.run(('git',) + args, cwd=REPO, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout)
        return (r.stdout or '').strip(), r.returncode == 0
    except Exception as e:
        print('⚠️ [git 실패] %s → %s' % (' '.join(args), e), flush=True)
        return '', False


def _pinned_sha():
    try:
        with open(DEPLOY_PIN_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip() or None
    except Exception:
        return None


def _write_pin(sha):
    try:
        if sha:
            with open(DEPLOY_PIN_FILE, 'w', encoding='utf-8') as f:
                f.write(sha)
        elif os.path.exists(DEPLOY_PIN_FILE):
            os.remove(DEPLOY_PIN_FILE)
        return True
    except Exception as e:
        print('⚠️ [고정 표시 기록 실패] %s' % e, flush=True)
        return False


def _version_num(sha):
    out, ok = _git('rev-list', '--count', sha, timeout=15)
    try:
        return int(out) if ok else 0
    except ValueError:
        return 0


def _version_nums(shas):
    """맨 위 · 맨 아래만 세 보고 차이가 딱 맞으면 사이는 빼기로(옛 것 — 20번 부르지 않게)."""
    if not shas:
        return {}
    top, bot = _version_num(shas[0]), _version_num(shas[-1])
    if top and bot and (top - bot) == (len(shas) - 1):
        return {sha: top - i for i, sha in enumerate(shas)}
    return {sha: _version_num(sha) for sha in shas}


def _commits_with_ui(shas):
    """준 버전들 중 v2 버전 화면이 들어 있는 것. 모르면 None. ⚠️ 찾을 글자는 쪼개 만든다(이 파일 자신이 걸리지 않게)."""
    if not shas:
        return set()
    marker = '/api/' + 'version/switch'
    out, ok = _git('grep', '-l', marker, *shas, '--', UI_FILE, timeout=40)
    if not ok and not out:
        return None          # 못 봤으면 표시하지 않는다(틀린 표시보다 낫다 — 옛 것 그대로)
    got = set()
    for line in (out or '').splitlines():
        head = line.split(':', 1)[0].strip()
        if head:
            got.add(head)
    return got


def _recent_commits(limit=VERSION_LIST_MAX):
    out, ok = _git('log', '-%d' % int(limit), '--date=format:%Y-%m-%d %H:%M', '--pretty=%H\x1f%h\x1f%ad\x1f%s', 'origin/main')
    if not ok:
        out, ok = _git('log', '-%d' % int(limit), '--date=format:%Y-%m-%d %H:%M', '--pretty=%H\x1f%h\x1f%ad\x1f%s')
    rows = []
    for line in (out or '').splitlines():
        p = line.split('\x1f')
        if len(p) == 4:
            rows.append({'sha': p[0], 'short': p[1], 'date': p[2], 'subject': p[3]})
    shas = [r['sha'] for r in rows]
    ui = _commits_with_ui(shas)
    nums = _version_nums(shas)
    for r in rows:
        r['num'] = nums.get(r['sha'], 0)
        r['label'] = ('V%d' % r['num']) if r['num'] else r['short']
        r['has_ui'] = (r['sha'] in ui) if ui is not None else None
    return rows


def _restart_services():
    for unit in _units():
        try:
            r = subprocess.run(['sudo', '-n', 'systemctl', 'restart', unit], capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=30)
            print(('🔄 [버전 전환] %s 재시작' if r.returncode == 0 else
                   '⚠️ [버전 전환] %s 재시작 권한 없음 — 자동배포가 2분 안에 처리합니다') % unit, flush=True)
        except Exception as e:
            print('⚠️ [버전 전환] %s 재시작 실패: %s — 자동배포에 맡깁니다' % (unit, e), flush=True)


# 켜질 때의 버전 — 파일만 바뀌고 재시작이 안 됐으면 HEAD 와 달라진다('아직 안 바뀌었다' 를 알린다)
RUNNING_SHA = _git('rev-parse', 'HEAD')[0] or ''


def _err(msg, code):
    return JSONResponse({'status': 'error', 'message': msg}, status_code=code)


def _list():
    head, ok = _git('rev-parse', 'HEAD')
    if not ok:
        return None
    _git('fetch', '--quiet', 'origin', 'main', timeout=20)
    subj, _ = _git('log', '-1', '--pretty=%s')
    date, _ = _git('log', '-1', '--date=format:%Y-%m-%d %H:%M', '--pretty=%ad')
    num = _version_num(head)
    run_num = _version_num(RUNNING_SHA) if RUNNING_SHA else 0
    return {'status': 'success',
            'current': {'sha': head, 'short': head[:8], 'subject': subj, 'date': date, 'num': num,
                        'label': ('V%d' % num) if num else head[:8]},
            'running_sha': RUNNING_SHA, 'running_label': ('V%d' % run_num) if run_num else RUNNING_SHA[:8],
            'needs_restart': bool(RUNNING_SHA and head and RUNNING_SHA != head),
            'pinned': _pinned_sha(), 'commits': _recent_commits()}


def _switch(want):
    _git('fetch', '--quiet', 'origin', 'main', timeout=25)
    if want not in {c['sha'] for c in _recent_commits()}:
        return _err('목록에 없는 버전입니다 (최근 %d개 중에서만 고를 수 있습니다)' % VERSION_LIST_MAX, 400)
    head, _ = _git('rev-parse', 'HEAD')
    if head == want:
        _write_pin(want)
        return {'status': 'success', 'message': '이미 그 버전으로 돌고 있습니다', 'restarting': False}
    _write_pin(want)
    # ⚠️ --force — 서버에서 손댄 파일이 있으면 그냥 checkout 은 거부한다(자동 배포도 reset --hard 라 같은 규칙)
    _, ok = _git('checkout', '--quiet', '--force', '--detach', want, timeout=40)
    if not ok:
        _write_pin(None)
        return _err('버전을 옮기지 못했습니다. 서버 상태를 확인해주세요', 500)
    subj, _ = _git('log', '-1', '--pretty=%s')
    print('🕹️ [버전 전환] %s → %s · %s' % (head[:8], want[:8], subj), flush=True)
    threading.Timer(1.0, _restart_services).start()
    n = _version_num(want)
    lbl = ('V%d' % n) if n else want[:8]
    return {'status': 'success', 'restarting': True, 'sha': want, 'short': want[:8], 'subject': subj, 'label': lbl,
            'message': '%s 로 옮겼습니다. 곧 다시 시작합니다' % lbl}


def _latest():
    _git('fetch', '--quiet', 'origin', 'main', timeout=25)
    remote, ok = _git('rev-parse', 'origin/main')
    if not ok:
        # 500 이 아니라 400 — 고장이 아니라 '여기서는 못 쓴다'(git 으로 배포된 서버가 아님)
        return _err('이 서버는 git 으로 배포된 것이 아니라 버전을 바꿀 수 없습니다', 400)
    _write_pin(None)
    head, _ = _git('rev-parse', 'HEAD')
    if head == remote:
        return {'status': 'success', 'message': '이미 최신입니다', 'restarting': False}
    _, ok = _git('checkout', '--quiet', '--force', '-B', 'main', 'origin/main', timeout=40)
    if not ok:
        return _err('최신으로 되돌리지 못했습니다. 서버 상태를 확인해주세요', 500)
    print('🕹️ [버전 전환] 최신으로 복귀 → %s' % remote[:8], flush=True)
    threading.Timer(1.0, _restart_services).start()
    return {'status': 'success', 'restarting': True, 'sha': remote, 'short': remote[:8],
            'message': '최신으로 되돌렸습니다. 곧 다시 시작합니다'}


def patchnotes():
    try:
        with open(os.path.join(REPO, 'PATCHNOTES.md'), 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        return _err('패치노트를 읽지 못했습니다: %s' % e, 500)
    releases, cur = [], None
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith('## '):
            cur = {'date': line[3:].strip(), 'items': []}
            releases.append(cur)
        elif line.startswith('- ') and cur is not None:
            body, kind = line[2:].strip(), ''
            if body.startswith('['):
                end = body.find(']')
                if end > 0:
                    kind, body = body[1:end].strip(), body[end + 1:].strip()
            cur['items'].append({'kind': kind, 'text': body})
    return {'status': 'success', 'releases': releases}


@route('/api/version/list', methods=('GET',))
async def version_list(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    out = await asyncio.to_thread(_list)
    return out if out is not None else _err('이 서버는 git 으로 배포된 것이 아니라 버전을 바꿀 수 없습니다', 400)


@route('/api/version/switch', methods=('POST',))
async def version_switch(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    try:
        body = await req.json()
    except Exception:
        body = {}
    want = str((body or {}).get('sha') or '').strip()
    if not want:
        return _err('버전을 골라주세요', 400)
    if bus.state.get('session').get('live') and not (body or {}).get('during_live'):
        # v2 에서 더한 것: 방송 중엔 한 번 더 묻는다(조종실이 during_live:true 로 다시 보낸다) — 옛 것은 바로 옮겼다
        return JSONResponse({'status': 'error', 'need_confirm': True,
                             'message': '방송 중입니다 — 옮기면 몇 초 동안 화면 · 후원 받기가 끊깁니다. 그래도 옮길까요?'}, status_code=409)
    return await asyncio.to_thread(_switch, want)


@route('/api/version/latest', methods=('POST',))
async def version_latest(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    return await asyncio.to_thread(_latest)


@route('/api/patchnotes', methods=('GET',))
async def patchnotes_route(req, bus, authed, answer):
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    return patchnotes()
