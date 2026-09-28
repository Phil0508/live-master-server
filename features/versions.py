# -*- coding: utf-8 -*-
"""🕹️ 버전 되돌리기 / 올리기 · 패치노트.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import os
import subprocess
import threading
from flask import jsonify, request
from server import (
    BASE_DIR, BUNDLE_DIR, app,
)


# ==========================================
# 🕹️ 버전 되돌리기 / 올리기
# ==========================================
#
# 방송 중에 뭔가 이상하면 조종실에서 바로 이전 버전으로 되돌릴 수 있게 한다.
#
# ⚠️ 자동배포와 싸우지 않게 하는 것이 핵심이다. auto-deploy 는 2분마다
#    `git reset --hard origin/main` 을 하므로, 그냥 옛 커밋으로 옮겨두면
#    2분 안에 최신으로 도로 끌려 올라간다. 그래서 '지금은 이 버전에 고정'
#    이라는 표시(DEPLOY_PIN 파일)를 남기고, auto-deploy 가 그걸 먼저 읽게 했다.
#
# ⚠️ 고를 수 있는 것은 '저장소에 이미 올라간 최근 커밋'뿐이다. 아무 번호나 받으면
#    남의 갈래(fork)에 있는 코드를 서버에서 돌리게 만들 수 있다.

DEPLOY_PIN_FILE = os.path.join(BASE_DIR, 'DEPLOY_PIN')
VERSION_LIST_MAX = 20      # 조종실에 보여주고 고를 수 있는 개수


def _git(*args, timeout=25):
    """저장소 폴더에서 git 을 부른다. (stdout, 성공여부)"""
    try:
        # ⚠️ encoding 을 못박아야 한다. 안 그러면 파이썬이 '이 컴퓨터의 기본 인코딩'으로
        #    해독하는데, 커밋 메시지가 한글(UTF-8)이라 윈도우에서 통째로 깨져 빈 값이 된다
        #    (예외가 읽기 갈래 안에서 조용히 삼켜져서, 오류 없이 목록만 비어 보였다).
        r = subprocess.run(('git',) + args, cwd=BASE_DIR, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=timeout)
        return (r.stdout or '').strip(), r.returncode == 0
    except Exception as e:
        print(f'⚠️ [git 실패] {" ".join(args)} → {e}')
        return '', False


def _pinned_sha():
    """지금 고정해둔 버전. 없으면 None(= 최신을 따라간다)."""
    try:
        with open(DEPLOY_PIN_FILE, 'r', encoding='utf-8') as f:
            v = f.read().strip()
        return v or None
    except Exception:
        return None


def _write_pin(sha):
    """고정 표시를 남긴다(sha 가 None 이면 지운다). 이 파일 하나로 자동배포와 약속한다."""
    try:
        if sha:
            with open(DEPLOY_PIN_FILE, 'w', encoding='utf-8') as f:
                f.write(sha)
        elif os.path.exists(DEPLOY_PIN_FILE):
            os.remove(DEPLOY_PIN_FILE)
        return True
    except Exception as e:
        print(f'⚠️ [고정 표시 기록 실패] {e}')
        return False


def _recent_commits(limit=VERSION_LIST_MAX):
    """origin/main 의 최근 커밋 목록. [{sha, short, date, subject}]"""
    out, ok = _git('log', f'-{int(limit)}', '--date=format:%Y-%m-%d %H:%M',
                   '--pretty=%H\x1f%h\x1f%ad\x1f%s', 'origin/main')
    if not ok:
        # origin/main 을 모르는 환경(로컬 개발 등)에서는 현재 갈래로 대신 본다
        out, ok = _git('log', f'-{int(limit)}', '--date=format:%Y-%m-%d %H:%M',
                       '--pretty=%H\x1f%h\x1f%ad\x1f%s')
    rows = []
    for line in (out or '').splitlines():
        parts = line.split('\x1f')
        if len(parts) == 4:
            rows.append({'sha': parts[0], 'short': parts[1],
                         'date': parts[2], 'subject': parts[3]})
    shas = [r['sha'] for r in rows]
    ui = _commits_with_version_ui(shas)
    nums = _version_nums(shas)
    for r in rows:
        r['num'] = nums.get(r['sha'], 0)
        r['label'] = ('V%d' % r['num']) if r['num'] else r['short']
        r['has_ui'] = (r['sha'] in ui) if ui is not None else None
    return rows


def _version_nums(shas):
    """여러 버전의 번호를 한꺼번에. {sha: 번호}

       ⚠️ 커밋마다 세면 20번을 부른다. 맨 위와 맨 아래만 세보고 차이가 딱 맞으면
          (= 그 구간이 한 줄로 이어져 있으면) 사이는 빼기로 채운다. 2번이면 끝난다.
          갈라졌다 합쳐진 구간이면 딱 안 맞으므로, 그때만 하나씩 센다.
    """
    if not shas:
        return {}
    top = _version_num(shas[0])
    bot = _version_num(shas[-1])
    if top and bot and (top - bot) == (len(shas) - 1):
        return {sha: top - i for i, sha in enumerate(shas)}
    return {sha: _version_num(sha) for sha in shas}


def _version_num(sha):
    """그 커밋까지 쌓인 커밋 수 = V번호. 자동으로 매겨지고 다시 안 바뀐다."""
    out, ok = _git('rev-list', '--count', sha, timeout=15)
    try:
        return int(out) if ok else 0
    except ValueError:
        return 0


def _commits_with_version_ui(shas):
    """준 버전들 중 이 '버전' 화면이 들어 있는 것들. 모르면 None.

       ⚠️ 없는 버전으로 되돌리면 조종실에서 돌아올 방법이 사라진다
          (서버에 직접 들어가 고정 파일을 지워야 한다). 미리 알려주려고 본다.

       ⚠️ 찾을 글자는 반드시 쪼개서 만든다. 통째로 적으면 '이 함수 자신'이 걸려서
          어떤 버전이든 '있음'으로 나온다(실제로 그렇게 틀렸다).

       ⚠️ '처음 들어온 커밋 뒤는 전부 있다'로 보면 안 된다 — 뺐다가 다시 넣은
          이력이 있으면 틀린다. git grep 은 여러 버전을 한 번에 받으므로
          한 번 불러서 정확하게 가른다.
    """
    if not shas:
        return set()
    marker = '/api/' + 'version/switch'
    out, ok = _git('grep', '-l', marker, *shas, '--', 'server.py', timeout=40)
    if not ok and not out:
        return None          # 못 봤으면 표시하지 않는다(틀린 표시보다 낫다)
    got = set()
    for line in (out or '').splitlines():
        # 'e288b1e...:server.py' 모양으로 온다
        head = line.split(':', 1)[0].strip()
        if head:
            got.add(head)
    return got


def _restart_services():
    """서비스를 재시작한다. 권한이 없으면 조용히 실패하고 자동배포에 맡긴다.

       ⚠️ 이 명령이 지금 이 프로세스를 죽인다. 그래서 응답을 먼저 보낸 뒤
          딴 갈래에서 잠깐 있다가 부른다.
    """
    for unit in ('livemaster', 'toon-listener', 'livemaster-bot'):
        try:
            r = subprocess.run(['sudo', '-n', 'systemctl', 'restart', unit],
                               capture_output=True, text=True, encoding='utf-8',
                               errors='replace', timeout=30)
            if r.returncode == 0:
                print(f'🔄 [버전 전환] {unit} 재시작', flush=True)
            else:
                print(f'⚠️ [버전 전환] {unit} 재시작 권한 없음 — 자동배포가 2분 안에 처리합니다',
                      flush=True)
        except Exception as e:
            print(f'⚠️ [버전 전환] {unit} 재시작 실패: {e} — 자동배포에 맡깁니다', flush=True)


# 이 프로세스가 켜질 때 어떤 버전이었는지. 파일은 바뀌었는데 재시작이 안 됐으면
# 이 값과 현재 HEAD 가 달라진다 — 그때 화면에 '아직 안 바뀌었다'고 알려야 한다.
RUNNING_SHA = _git('rev-parse', 'HEAD')[0] or ''


@app.route('/api/version/list', methods=['GET'])
def api_version_list():
    """고를 수 있는 버전 목록과 지금 돌고 있는 버전."""
    head, ok = _git('rev-parse', 'HEAD')
    if not ok:
        return jsonify({'status': 'error',
                        'message': '이 서버는 git 으로 배포된 것이 아니라 버전을 바꿀 수 없습니다'}), 400
    _git('fetch', '--quiet', 'origin', 'main', timeout=20)
    subj, _ = _git('log', '-1', '--pretty=%s')
    date, _ = _git('log', '-1', '--date=format:%Y-%m-%d %H:%M', '--pretty=%ad')
    num = _version_num(head)
    run_num = _version_num(RUNNING_SHA) if RUNNING_SHA else 0
    # ⚠️ '파일이 이 버전' 과 '지금 돌고 있는 코드가 이 버전' 은 다르다.
    #    재시작이 안 됐으면 파일만 바뀌고 옛 코드가 계속 돈다.
    return jsonify({'status': 'success',
                    'current': {'sha': head, 'short': head[:8], 'subject': subj, 'date': date,
                                'num': num, 'label': ('V%d' % num) if num else head[:8]},
                    'running_sha': RUNNING_SHA,
                    'running_label': ('V%d' % run_num) if run_num else RUNNING_SHA[:8],
                    'needs_restart': bool(RUNNING_SHA and head and RUNNING_SHA != head),
                    'pinned': _pinned_sha(),
                    'commits': _recent_commits()})


@app.route('/api/version/switch', methods=['POST'])
def api_version_switch():
    """고른 버전으로 옮기고 재시작한다."""
    body = request.get_json(silent=True) or {}
    want = str(body.get('sha') or '').strip()
    if not want:
        return jsonify({'status': 'error', 'message': '버전을 골라주세요'}), 400

    _git('fetch', '--quiet', 'origin', 'main', timeout=25)
    # ⚠️ 목록에 있는 것만 허용한다. 아무 번호나 받으면 남의 갈래 코드를 돌릴 수 있다.
    allowed = {c['sha'] for c in _recent_commits()}
    if want not in allowed:
        return jsonify({'status': 'error',
                        'message': '목록에 없는 버전입니다 (최근 %d개 중에서만 고를 수 있습니다)'
                                   % VERSION_LIST_MAX}), 400

    head, _ = _git('rev-parse', 'HEAD')
    if head == want:
        _write_pin(want)
        return jsonify({'status': 'success', 'message': '이미 그 버전으로 돌고 있습니다',
                        'restarting': False})

    # 옮기기는 여기서 바로 한다(빠르고, 실패하면 재시작도 하지 않는다)
    _write_pin(want)
    # ⚠️ --force 가 필요하다. 서버에서 파일이 하나라도 손대져 있으면 그냥 checkout 은
    #    거부한다. 어차피 자동배포도 매번 reset --hard 로 밀어버리므로(= 서버의 손댄 내용은
    #    보존되지 않는 것이 이 서버의 규칙이다) 같은 규칙으로 맞춘다.
    out, ok = _git('checkout', '--quiet', '--force', '--detach', want, timeout=40)
    if not ok:
        _write_pin(None)
        return jsonify({'status': 'error',
                        'message': '버전을 옮기지 못했습니다. 서버 상태를 확인해주세요'}), 500

    subj, _ = _git('log', '-1', '--pretty=%s')
    print(f'🕹️ [버전 전환] {head[:8]} → {want[:8]} · {subj}', flush=True)

    # 응답을 먼저 보내고 재시작한다 — 재시작이 지금 이 프로세스를 죽이기 때문이다.
    threading.Timer(1.0, _restart_services).start()
    lbl = 'V%d' % _version_num(want) if _version_num(want) else want[:8]
    return jsonify({'status': 'success', 'restarting': True,
                    'sha': want, 'short': want[:8], 'subject': subj, 'label': lbl,
                    'message': f'{lbl} 로 옮겼습니다. 곧 다시 시작합니다'})


@app.route('/api/version/latest', methods=['POST'])
def api_version_latest():
    """고정을 풀고 최신(main)으로 돌아간다."""
    _git('fetch', '--quiet', 'origin', 'main', timeout=25)
    remote, ok = _git('rev-parse', 'origin/main')
    if not ok:
        # ⚠️ 500 이 아니라 400 이다. 서버가 고장난 게 아니라 '여기서는 이 기능을 쓸 수
        #    없다'는 상황이다(git 으로 배포된 서버가 아님). 500 을 주면 조종실이
        #    '서버 이상'으로 보고 재시도한다.
        return jsonify({'status': 'error',
                        'message': '이 서버는 git 으로 배포된 것이 아니라 버전을 바꿀 수 없습니다'}), 400
    _write_pin(None)
    head, _ = _git('rev-parse', 'HEAD')
    if head == remote:
        return jsonify({'status': 'success', 'message': '이미 최신입니다', 'restarting': False})
    out, ok = _git('checkout', '--quiet', '--force', '-B', 'main', 'origin/main', timeout=40)
    if not ok:
        return jsonify({'status': 'error',
                        'message': '최신으로 되돌리지 못했습니다. 서버 상태를 확인해주세요'}), 500
    print(f'🕹️ [버전 전환] 최신으로 복귀 → {remote[:8]}', flush=True)
    threading.Timer(1.0, _restart_services).start()
    return jsonify({'status': 'success', 'restarting': True,
                    'sha': remote, 'short': remote[:8],
                    'message': '최신으로 되돌렸습니다. 곧 다시 시작합니다'})


@app.route('/api/patchnotes', methods=['GET'])
def api_patchnotes():
    """저장소의 PATCHNOTES.md 를 읽어 조종실 시스템 탭에 보여준다.

    파일을 그대로 읽으므로 배포하면 곧바로 최신 내용이 뜬다(따로 DB에 넣지 않는다).
    파싱은 '## 날짜' 아래 '- [분류] 내용' 만 본다.
    """
    path = os.path.join(BASE_DIR, 'PATCHNOTES.md')
    if not os.path.exists(path):
        path = os.path.join(BUNDLE_DIR, 'PATCHNOTES.md')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        return jsonify({"status": "error", "message": f"패치노트를 읽지 못했습니다: {e}"}), 500

    releases, cur = [], None
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith('## '):
            cur = {"date": line[3:].strip(), "items": []}
            releases.append(cur)
        elif line.startswith('- ') and cur is not None:
            body = line[2:].strip()
            kind = ''
            if body.startswith('['):
                end = body.find(']')
                if end > 0:
                    kind = body[1:end].strip()
                    body = body[end + 1:].strip()
            cur['items'].append({"kind": kind, "text": body})
    return jsonify({"status": "success", "releases": releases})
