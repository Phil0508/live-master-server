# -*- coding: utf-8 -*-
"""전체 검증 러너.

검사마다 서버를 깨끗하게 다시 띄운다. 이전 검사가 남긴 상태(방송 중 여부,
점수, 큐)가 다음 검사의 판정을 뒤집는 일이 실제로 여러 번 있었다.
"""
import os, subprocess, sys, time, shutil, socket, json, re, signal, tempfile

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
def _find_root():
    """저장소 폴더를 찾는다 — 윈도우·맥 어디서 돌려도 되게."""
    env = os.environ.get('LM_PROJECT_ROOT')
    if env and os.path.exists(os.path.join(env, 'server.py')):
        return env
    d = HERE
    for _ in range(5):
        if os.path.exists(os.path.join(d, 'server.py')):
            return d
        d = os.path.dirname(d)
    # ⚠️ 못 찾으면 여기서 멈춘다. 그냥 두면 검사 40개가 전부 'rc=2' 로
    #    우수수 실패해서 원인을 알아보기 어렵다.
    print('❌ 저장소를 못 찾았습니다 (server.py 가 있는 폴더).')
    print('   저장소에서  python tests/runall.py  로 돌리거나,')
    print('   다른 곳에서 돌린다면 LM_PROJECT_ROOT 를 지정하세요.')
    sys.exit(2)


PROJ = _find_root()
# ⚠️ 샌드박스는 저장소 밖에 둔다.
#    안 그러면 — ① edgebox/·qbox/ 같은 폴더가 저장소에 쌓이고,
#    ② 샌드박스가 git 안에 들어가 'git 이 없는 서버' 를 전제로 하는
#       검사(t12)가 깨진다. 저장소에서 바로 `python tests/runall.py` 를 돌리는 것이
#       맥에서 클론하고 처음 하는 일이라 반드시 되어야 한다.
_SBOX = os.environ.get('LM_SANDBOX') or os.path.join(tempfile.gettempdir(), 'livemaster-sandbox')
LT2 = os.path.join(_SBOX, 'lt2')
PT = os.path.join(_SBOX, 'pausetest')
PY = sys.executable

RESULTS = []


def sh(cmd, cwd=None, env=None, timeout=900):
    e = dict(os.environ); e['PYTHONIOENCODING'] = 'utf-8'; e['PYTHONUNBUFFERED'] = '1'
    # ⚠️ 검사들은 저장소 밖(스크래치패드)으로 복사돼 돌아간다. 자기 위치로는 저장소를
    #    못 찾으므로 여기서 물려준다. 예전에는 검사마다 C:\Users\... 를 박아 뒀는데,
    #    맥에서는 그 경로가 없어 검사가 통째로 어긋난다.
    e['LM_PROJECT_ROOT'] = PROJ
    # 검사가 샌드박스 DB 를 짐작하지 않게 실제 경로를 알려준다
    e['LM_SANDBOX_PT'] = PT
    if env: e.update(env)
    try:
        r = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=timeout)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except subprocess.TimeoutExpired:
        return 124, '(시간 초과)'


# ⚠️ netstat·taskkill 은 윈도우에만 있다. 맥에서도 작업하므로 갈라 놓는다 —
#    포트를 못 끄면 앞 검사의 서버가 남아 다음 검사가 통째로 어긋난다.
IS_WIN = (os.name == 'nt')


def port_pid(port):
    if IS_WIN:
        out = subprocess.run(['netstat', '-ano'], capture_output=True, text=True).stdout
        for ln in out.splitlines():
            # 서버는 0.0.0.0 에 붙는다 — 주소를 가리지 말고 포트로만 찾는다
            f = ln.split()
            if len(f) > 1 and f[1].endswith(':%d' % port) and 'LISTENING' in ln:
                return int(ln.split()[-1])
        return None
    # 맥·리눅스
    out = subprocess.run(['lsof', '-ti', 'tcp:%d' % port, '-sTCP:LISTEN'],
                         capture_output=True, text=True).stdout.strip()
    return int(out.splitlines()[0]) if out else None


def kill_port(port):
    for _ in range(6):
        p = port_pid(port)
        if not p: return
        if IS_WIN:
            subprocess.run(['taskkill', '/PID', str(p), '/F'], capture_output=True)
        else:
            try:
                os.kill(p, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(0.6)


def copy_into(src, dst):
    """src 를 dst 로 복사한다. 같은 파일이면 건너뛴다.

    ⚠️ 저장소 tests/ 에서 그대로 돌리면 원본과 목적지가 같은 파일이라
       shutil 이 SameFileError 를 던져 검사가 통째로 죽는다. 맥에서 클론하고
       처음 하는 일이 `python tests/runall.py` 라 반드시 되어야 한다.
    """
    try:
        if os.path.abspath(src) == os.path.abspath(dst):
            return
    except Exception:
        pass
    shutil.copyfile(src, dst)


def wipe(d):
    for f in ('live_master.db', 'live_master.db-wal', 'live_master.db-shm',
              'game_data.json', 'donation_spool.jsonl'):
        p = os.path.join(d, f)
        if os.path.exists(p):
            try: os.remove(p)
            except Exception: pass


def boot(kind):
    """kind: 'lt2' (5177) / 'pt' (5199). 깨끗한 DB 로 새로 띄운다."""
    port = 5177 if kind == 'lt2' else 5199
    d = LT2 if kind == 'lt2' else PT
    kill_port(port); wipe(d)
    if kind == 'lt2':
        rc, out = sh([PY, 'boot.py', str(port)], cwd=d, timeout=180)
        ok = port_pid(port) is not None
    else:
        env = {'HEADLESS': '1', 'PORT': '5199', 'ADMIN_PASSWORD': 'sandboxpw',
               'SESSION_SECRET': 'sandboxsecret123456', 'SELF_PING': 'off'}
        e = dict(os.environ); e.update(env)
        e['PYTHONIOENCODING'] = 'utf-8'; e['PYTHONUNBUFFERED'] = '1'
        log = open(os.path.join(d, 'run.log'), 'w', encoding='utf-8', errors='replace')
        subprocess.Popen([PY, 'boot_sig.py'], cwd=d, env=e, stdout=log, stderr=subprocess.STDOUT)
        ok = False
        for _ in range(80):
            time.sleep(0.5)
            if port_pid(port): ok = True; break
    return ok


def tally(out):
    """출력에서 통과/실패 수를 뽑는다."""
    p = f = None
    for m in re.finditer(r'통과\s*(\d+)\s*[/·]\s*실패\s*(\d+)', out):
        p, f = int(m.group(1)), int(m.group(2))
    return p, f


def run(name, cmd, cwd, kind=None, timeout=900):
    print('\n' + '=' * 72)
    print('▶ %s' % name, flush=True)
    if kind:
        if not boot(kind):
            RESULTS.append((name, '기동실패', '', ''))
            print('   서버 기동 실패'); return
    t0 = time.time()
    rc, out = sh(cmd, cwd=cwd, timeout=timeout)
    dt = time.time() - t0
    p, f = tally(out)
    if p is not None:
        verdict = '통과' if f == 0 else '실패'
        detail = '%d통과 / %d실패' % (p, f)
    else:
        verdict = '완료' if rc == 0 else ('시간초과' if rc == 124 else '오류(rc=%d)' % rc)
        detail = ''
    RESULTS.append((name, verdict, detail, '%.0f초' % dt))
    tail = [l for l in out.splitlines() if l.strip()][-14:]
    print('\n'.join(tail))
    print('   → %s %s (%.0f초)' % (verdict, detail, dt), flush=True)


# ── 최신 코드를 두 샌드박스에 복사 ──
# ⚠️ 원칙은 저장소 밖(스크래치패드) 사본으로 돌리는 것이다. 저장소에서 그냥 돌리면
#    tests/lt2/ · tests/pausetest/ 안에 서버 사본이 생겨 저장소가 더러워진다.
#    그래도 터지지는 않게 폴더는 만들어 둔다 (.gitignore 가 커밋은 막는다).
for _d in (LT2, PT):
    os.makedirs(_d, exist_ok=True)
for f in ('server.py', 'overlay.html', 'admin.html', 'controller.html', 'mobile.html'):
    src = os.path.join(PROJ, f)
    if os.path.exists(src):
        for d in (LT2, PT):
            copy_into(src, os.path.join(d, f))
# ── 검사 원본은 저장소 tests/ 다. 스크래치패드는 시스템이 언제든 비울 수 있어서
#    실제로 검사 두 개가 증발한 적이 있다. 매 실행마다 저장소에서 새로 받아온다.
TESTS = os.path.join(PROJ, 'tests')
if os.path.isdir(TESTS):
    for f in os.listdir(TESTS):
        src = os.path.join(TESTS, f)
        if f.endswith(('.py', '.js')) and os.path.isfile(src):
            dst = HERE if f != 'boot_sig.py' else PT
            if f != 'runall.py':
                copy_into(src, os.path.join(dst, f))
    lt2src = os.path.join(TESTS, 'lt2')
    if os.path.isdir(lt2src):
        for f in os.listdir(lt2src):
            if f.endswith('.py'):
                copy_into(os.path.join(lt2src, f), os.path.join(LT2, f))
    print('저장소 tests/ 에서 검사 동기화 완료', flush=True)

print('샌드박스에 최신 코드 복사 완료', flush=True)

# ── ① 정적 검사 ──
print('\n' + '=' * 72); print('▶ 정적 — 파이썬 컴파일')
bad = []
for f in ('server.py', 'toon_listener.py'):
    p = os.path.join(PROJ, f)
    if os.path.exists(p):
        rc, out = sh([PY, '-c',
                      'import py_compile,sys;py_compile.compile(sys.argv[1],doraise=True)', p])
        print('   %-18s %s' % (f, '문법 OK' if rc == 0 else out[-300:]))
        if rc: bad.append(f)
RESULTS.append(('파이썬 컴파일', '통과' if not bad else '실패', '', ''))

print('\n' + '=' * 72); print('▶ 정적 — 화면 자바스크립트 문법')
rc, out = sh(['node', os.path.join(HERE, 'jscheck.js'), PROJ])
print(out.strip()[-500:])
RESULTS.append(('JS 문법', '통과' if rc == 0 and '오류 0개' in out else '실패', '', ''))

# ── ② 서버 없이 도는 검사 ──
run('t6 시그니처 큐(내부)', [PY, 't6_queue.py'], LT2)
run('t8 오토파일럿 경계(내부)', [PY, 't8_edge.py'], LT2)

# ── ③ 스스로 서버를 띄우는 검사 ──
kill_port(5177); kill_port(5199)
run('t9 후원 유실 방지', [PY, 't9_spool.py'], LT2)
run('t10 리스너가 굶기는가', [PY, 't10_starve.py'], LT2)

# ── ④ lt2 서버(5177) 가 필요한 검사 ──
run('t1 무결성·인증', [PY, 't1_integrity.py'], LT2, kind='lt2')
run('t2b 동시 편집 추돌', [PY, 't2b_conflict_real.py'], LT2, kind='lt2')
run('t3 부하', [PY, 't3_load.py'], LT2, kind='lt2')
run('t4 상한·방어선', [PY, 't4_limits.py'], LT2, kind='lt2')
run('t11 고친 것 확인', [PY, 't11_verify_fixes.py'], LT2, kind='lt2')
run('t12 마지막 셋', [PY, 't12_final3.py'], LT2, kind='lt2')

# ── ⑤ pausetest 서버(5199) 가 필요한 검사 ──
run('시그뒤집기', [PY, 'sg_test.py'], HERE, kind='pt')
run('주사위게임', [PY, 'dice_test.py'], HERE, kind='pt')
run('기여도만 지급', [PY, 'contrib_test.py'], HERE, kind='pt')
run('시그니처 재생', [PY, 'sig_test.py'], HERE, kind='pt')
run('대결 팀전', [PY, 'team_test.py'], HERE, kind='pt')
run('500 터지는 길 전수', [PY, 'crash_sweep.py'], HERE, kind='pt')
run('이중배정·집계 보호', [PY, 'guard_test.py'], HERE, kind='pt')
run('점수 정확성', [PY, 'score_test.py'], HERE, kind='pt')
run('모니터 모드(폰 미리보기)', [PY, 'monitor_test.py'], HERE)
run('지난 방송 후원내역', [PY, 'archive_test.py'], HERE, kind='pt')
run('안내 전광판', [PY, 'notice_test.py'], HERE, kind='pt')
run('배치 왕복', [PY, 'layout_test.py'], HERE, kind='pt')
run('시그니처 연출', ['node', 'sigfx_test.js'], HERE)
run('룰렛 상시부담', ['node', 'roulette_test.js'], HERE)
run('룰렛 닫힘', [PY, 'roulette_close_test.py'], HERE, kind='pt')
run('주사위 기본판', [PY, 'dice_preset_test.py'], HERE)
run('안전지대 HUD', [PY, 'hud_test.py'], HERE)
run('빛·입자 레이어', [PY, 'siggl_test.py'], HERE)
run('폰 가독성', [PY, 'readable_test.py'], HERE)
run('편집기 동기화', [PY, 'editor_sync_test.py'], HERE)
run('나눠주기 계산', [PY, 'split_test.py'], HERE)
run('만원 반올림', [PY, 'rounding_test.py'], HERE)
run('AI 모델 설정', [PY, 'nim_test.py'], HERE)
run('월별 후원 순위', [PY, 'monthly_test.py'], HERE, kind='pt')
run('특별 후원자 등급', [PY, 'vip_test.py'], HERE, kind='pt')
run('순위에서 뺄 이름', [PY, 'exclude_test.py'], HERE, kind='pt')
run('퇴근빵 — 실제 번 돈', [PY, 'homerace_test.py'], HERE, kind='pt')
run('게이지 보정', [PY, 'goal_offset_test.py'], HERE, kind='pt')
run('로그 시각(한국시간)', [PY, 'clock_test.py'], HERE)
run('반쪽 화면 조종실', [PY, 'halfscreen_test.py'], HERE)
run('효과음·걷어낸 것', [PY, 'sfx_test.py'], HERE)
run('점검에서 나온 것들', [PY, 'fixes_test.py'], HERE, kind='pt')

kill_port(5177); kill_port(5199)

print('\n\n' + '=' * 72)
print('전체 결과')
print('=' * 72)
for n, v, d, t in RESULTS:
    mark = 'OK ' if v in ('통과', '완료') else '>> '
    print('%s%-24s %-8s %-16s %s' % (mark, n, v, d, t))
bad = [r for r in RESULTS if r[1] not in ('통과', '완료')]
print('=' * 72)
print('문제 있는 항목: %d개' % len(bad))
for n, v, d, t in bad:
    print('   - %s : %s %s' % (n, v, d))
