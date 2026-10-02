# -*- coding: utf-8 -*-
"""🔢 화면 숫자·표시 고침 여섯 가지 (2026-09-30 점검에서 재현된 것).

여기서 지키는 것
  ① 목표가 0(= 목표 없음)이면 방송판 막대가 비어 있고 '달성' 반짝임이 안 뜬다
     (예전엔 `target_goal || 1` 이라 1점만 있어도 막대가 꽉 차고 반짝였다)
  ② 끝 화면 '후원해 주신 분' — 조종실에서 '익명 포함' 을 켜면 익명도 나온다(후원 순위판과 같다).
     [순위에서 빼기] 한 이름은 후원자 줄에도 · 한 방 최고에도 안 나온다
  ③ AI 사실표 — 번외 중에도 목표 · 퇴근빵은 본게임 명단(bjs)으로 센다(방송판 막대와 같다)
  ④ AI 사실표 단위 설명 — '6천 원부터 올림'(실제 man_won 과 같다)
  ⑤ 대결 위젯 — 1등이 동점이면 어느 카드도 빛나지 않는다(격차 '동점' 표시는 그대로)
  ⑥ 주사위 점수판 — 동점 이름 차례가 서버(파이썬 문자열 비교)와 같다

pt 서버가 필요하다(LM_PT_PORT, 기본 5199). 크롬이 없으면 브라우저 부분은 건너뛴다.
⚠️ 크롬은 이 검사가 띄운 것 하나만 끈다 — 이름으로 찾아 죽이면 앱 브라우저까지 죽는다.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = (os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(HERE, '..')))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:160]) if detail else ''))


def head(s):
    print()
    print('=' * 74)
    print(s)
    print('=' * 74)


def call(method, path, obj=None):
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(B + path, data, H, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def post(path, obj=None):
    return call('POST', path, obj or {})


def get():
    return call('GET', '/api/data')[1]


def _find(name):
    """features/ai_facts.py — 검사 사본 위치(tests 가 한 단계 아래)든 저장소든 찾는다."""
    d = HERE
    for _ in range(4):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
        d = os.path.dirname(d)
    return os.path.join(ROOT, name)


# ────────────────────────────────────────────────────────────
head('③ ④ AI 사실표 — 번외 중에도 목표·퇴근빵은 본게임 · 단위 설명')
spec = importlib.util.spec_from_file_location('ai_facts', _find(os.path.join('features', 'ai_facts.py')))
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
MAIN = [{'name': '하율', 'score': 300, 'contribution': 400}, {'name': '서아', 'score': 100, 'contribution': 120}]
ST = {'bjs': MAIN, 'bottom_fixed': {'name': '운영비', 'score': 50}, 'goal_offset': 7, 'target_goal': 1000,
      'home_race_enabled': True, 'home_goals': {'하율': 310, '서아': 150},
      'extra_game_active': True, 'extra_bjs': [{'name': '임시A', 'score': 2, 'contribution': 2}]}
fx = F.build_facts(ST, now=1790648760)
chk('번외 중 순위는 번외 판으로', [r['이름'] for r in fx['순위']] == ['임시A'], fx['순위'])
chk('⭐ 번외 중 목표 현재점수 = 본게임 점수 + 운영비 + 보정 (400+50+7=457)',
    isinstance(fx['목표'], dict) and fx['목표']['현재점수'] == 457 and fx['목표']['남은점수'] == 543, fx['목표'])
race = fx.get('퇴근빵') or {}
chk('⭐ 번외 중 퇴근빵도 본게임 선수로 (하율 10점 남음)',
    {x['이름'] for x in race.get('선수별', [])} == {'하율', '서아'} and race.get('가장_가까운_미달성') == '하율', race)
hs = dict(ST, home_race_enabled=False, hell={'on': True, 'base': {'하율': 290}, 'goals': {'하율': 20}})
hf = F.build_facts(hs, now=1790648760).get('퇴근빵') or {}
chk('번외 중 지옥탈출도 본게임 점수 − 시작점 (300−290=10)',
    hf.get('이름') == '지옥탈출' and (hf.get('선수별') or [{}])[0].get('현재') == 10, hf)
chk('⭐ 단위 설명이 실제 셈과 같다 (6천 원부터 올림 · 4천 아님)',
    '6천 원부터 올림' in fx['단위'] and '4천' not in fx['단위'], fx['단위'])
chk('man_won 5,999 → 0 · 6,000 → 1 (설명과 같은 셈)', F.man_won(5999) == 0 and F.man_won(6000) == 1)

# ────────────────────────────────────────────────────────────
head('② 끝 화면 — 익명은 익명 포함 설정이 정한다 · 뺀 이름은 안 나온다')
try:
    alive = call('GET', '/api/data')[0] == 200
except Exception:
    alive = False
if not alive:
    chk('pt 서버(%s)가 떠 있다' % B, False)
else:
    EXN = '시험빼기맨'
    post('/api/donors/excluded', {'name': EXN, 'memo': 'fix_display_test'})

    def tally(**kw):
        base = {'별빛': 30000, '익명': 70000, EXN: 90000, '솜사탕': 10000}
        base.update(kw)
        return {n: {'name': n, 'total': t, 'count': 1} for n, t in base.items()}

    def end_live(anon, best):
        # ⚠️ 뺀 이름이 기록에 남아 있는 경우를 흉내 낸다(빼기 전에 들어온 후원 · 옛 저장본)
        post('/api/restore', {'broadcast_active': True, 'reaction_queue': [],
                              'bjs': [{'name': '하율', 'score': 1, 'contribution': 1}],
                              'donor_tally': tally(), 'donor_rank_anon': anon, 'donor_rank_amount': True,
                              'best_single': best})
        post('/api/screen', {'mode': 'end', 'title': 'fix_display_test'})
        return get().get('stage_live') or {}

    lv = end_live(True, {'name': EXN, 'amount': 90000, 'at': 1, 'id': 'x', 'member': ''})
    names = [r.get('name') for r in lv.get('donors') or []]
    chk('⭐ 익명 포함을 켜면 끝 화면에도 익명이 나온다', '익명' in names, names)
    chk('⭐ 뺀 이름은 후원자 줄에 안 나온다', EXN not in names, names)
    chk('⭐ 한 방 최고가 뺀 이름이면 안 띄운다', lv.get('best') is None, lv.get('best'))
    chk('후원자 수도 뺀 이름 빼고 센다 (별빛 · 익명 · 솜사탕 = 3)', lv.get('donor_count') == 3, lv.get('donor_count'))
    lv2 = end_live(False, {'name': '익명', 'amount': 70000, 'at': 1, 'id': 'y', 'member': ''})
    names2 = [r.get('name') for r in lv2.get('donors') or []]
    chk('익명 포함이 꺼져 있으면 익명은 안 나온다 (예전과 같다)', '익명' not in names2 and '별빛' in names2, names2)
    chk('익명 한 방 최고는 그대로 띄운다', (lv2.get('best') or {}).get('name') == '익명', lv2.get('best'))
    post('/api/screen', {'mode': 'off'})
    call('DELETE', '/api/donors/excluded?name=' + urllib.parse.quote(EXN))


# ────────────────────────────────────────────────────────────
def chrome_path():
    for p in (os.environ.get('LM_CHROME') or '',
              r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
              '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
              shutil.which('google-chrome') or '', shutil.which('chromium') or ''):
        if p and os.path.exists(p):
            return p
    return None


try:
    import websocket
except Exception:
    websocket = None
CHROME = chrome_path()
if not alive or not CHROME or websocket is None:
    print('\n⚠️ 서버 · 크롬 · websocket-client 중 없는 것이 있어 방송판(브라우저) 검사를 건너뜁니다')
else:
    PORT = 9000 + int(time.time()) % 700
    PROF = tempfile.mkdtemp(prefix='fixdisp_')
    proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                             '--user-data-dir=' + PROF, '--remote-debugging-port=%d' % PORT,
                             '--remote-allow-origins=*', 'about:blank'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    try:
        tabs = None
        for _ in range(60):
            try:
                tabs = json.loads(urllib.request.urlopen('http://127.0.0.1:%d/json' % PORT, timeout=2).read())
                break
            except Exception:
                time.sleep(0.3)
        ws = websocket.create_connection(next(t for t in tabs if t.get('type') == 'page')['webSocketDebuggerUrl'],
                                         timeout=60)
        st = {'id': 0}

        def send(method, **params):
            st['id'] += 1
            ws.send(json.dumps({'id': st['id'], 'method': method, 'params': params}))
            while True:
                m = json.loads(ws.recv())
                if m.get('id') == st['id']:
                    return m.get('result', {})

        def ev(expr):
            r = send('Runtime.evaluate', expression=expr, returnByValue=True, awaitPromise=True)
            return (r.get('result') or {}).get('value')

        send('Page.enable')
        send('Runtime.enable')
        send('Emulation.setDeviceMetricsOverride', width=1080, height=1920, deviceScaleFactor=1, mobile=False)

        def gauge(target):
            post('/api/restore', {'broadcast_active': True, 'reaction_queue': [], 'target_goal': target,
                                  'goal_offset': 0, 'bottom_fixed': {'name': '운영비', 'score': 0},
                                  'bjs': [{'name': '하율', 'score': 30, 'contribution': 30},
                                          {'name': '서아', 'score': 13, 'contribution': 13}]})
            send('Page.navigate', url=B + '/overlay.html')
            for _ in range(60):
                time.sleep(0.25)
                if ev("!!(window.globalData && document.getElementById('goal-chunk'))"):
                    break
            time.sleep(2.0)   # 막대가 차오르는 움직임이 끝난 뒤에 잰다
            # ⚠️ style.height 글자는 크롬이 calc 를 다시 써서(예: calc(43% - 2.58px)) 비교가 흔들린다 → 실제 높이 비율로 잰다
            return json.loads(ev("""JSON.stringify({
                r: (() => { const c = document.getElementById('goal-chunk'); const p = c.parentElement;
                            return Math.round(c.getBoundingClientRect().height / Math.max(1, p.clientHeight - 6) * 100) / 100; })(),
                flash: document.getElementById('goal-box-ui').classList.contains('goal-flash'),
                tot: document.getElementById('ui-total-score').innerText })""") or '{}')

        head('① 목표 0 = 목표 없음 — 막대가 비고 반짝이지 않는다')
        g0 = gauge(0)
        chk('⭐ 목표 0 이면 막대가 비어 있다 (0%)', g0.get('r') == 0, g0)
        chk('⭐ 목표 0 이면 달성 반짝임이 없다', g0.get('flash') is False, g0)
        chk('합계 숫자는 그대로 나온다 (43)', g0.get('tot') == '43', g0)
        g1 = gauge(100)
        chk('목표 100 · 합계 43 → 막대 43%', abs((g1.get('r') or 0) - 0.43) <= 0.02 and g1.get('flash') is False, g1)
        g2 = gauge(40)
        chk('목표 40 · 합계 43 → 꽉 차고 반짝인다 (목표 있는 쪽은 예전 그대로)',
            (g2.get('r') or 0) >= 0.98 and g2.get('flash') is True, g2)

        head('⑤ 대결 — 1등 동점이면 아무 카드도 안 빛난다')
        MATCH = """(function(ps){ renderMatchWidget({players: ps});
            return JSON.stringify({ lead: [...document.querySelectorAll('#m-players-area .m-card')].map(e => e.classList.contains('lead')),
                                    seg: [...document.querySelectorAll('#m-gauge .m-seg')].map(e => e.classList.contains('lead')),
                                    num: document.getElementById('m-front-num').textContent,   // 대결이 숨어 있으면 innerText 는 빈 글자다
                                    on: document.getElementById('m-front').classList.contains('on') }); })(%s)"""
        t = json.loads(ev(MATCH % json.dumps([{'name': 'A', 'score': 5}, {'name': 'B', 'score': 5}])) or '{}')
        chk('⭐ 5:5 동점 — 카드 빛 없음', t.get('lead') == [False, False] and t.get('seg') == [False, False], t)
        chk('동점이어도 격차 칸은 켜져 있고 "동점" 이라 쓴다', t.get('on') is True and t.get('num') == '동점', t)
        t3 = json.loads(ev(MATCH % json.dumps([{'name': 'A', 'score': 2}, {'name': 'B', 'score': 7},
                                               {'name': 'C', 'score': 7}])) or '{}')
        chk('⭐ 셋 중 두 명이 공동 1등 — 빛 없음', t3.get('lead') == [False, False, False], t3)
        t2 = json.loads(ev(MATCH % json.dumps([{'name': 'A', 'score': 5}, {'name': 'B', 'score': 8}])) or '{}')
        chk('혼자 1등이면 그 카드만 빛난다 · 격차 3', t2.get('lead') == [False, True] and t2.get('num') == '3', t2)

        head('⑥ 주사위 점수판 — 동점 이름 차례가 서버와 같다')
        board = [{'name': n, 'pts': 3} for n in ('b', 'C', 'a', '하율', 'Z')] + [{'name': '서아', 'pts': 9}]
        order = json.loads(ev("""(function(b){ renderDiceBoard({board: b});
            const L = [...document.querySelectorAll('#dg-strip .dgs-chip[id] .dgs-name')].map(e => e.textContent);
            return JSON.stringify(L); })(%s)""" % json.dumps(board)) or '[]')
        want = [r['name'] for r in sorted(board, key=lambda r: (-r['pts'], r['name']))]   # 서버 _dicegame_ranked 와 같은 열쇠
        chk('⭐ 방송판 순서 = 서버 순서 %s' % want, order == want, order)
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            pass
        shutil.rmtree(PROF, ignore_errors=True)

print()
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('  ✗ ' + n)
sys.exit(1 if BAD else 0)
