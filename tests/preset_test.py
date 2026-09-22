# -*- coding: utf-8 -*-
"""💾 세이브 슬롯 — 누르면 저장한 그대로 바뀌는가.

왜 만들었나
  대표님 2026-09-22: "말 그대로 세이브 파일을 원하는 거야. 모드 1번에 룰렛을 켜고 엑셀판을
  밑으로 내린 세팅을 저장해 놨다면, 1번 누르면 룰렛이 켜지고 엑셀판이 밑으로 내려가는 것".
  (그 전에 만든 '모드별 배치'는 게임을 켜면 자리가 따라 바뀌는 반대 방향이라 걷었다)

여기서 지키는 것
  ① 저장하면 자리 · 켜고 끈 위젯 · 떠 있는 게임판이 담긴다
  ② 불러오면 셋이 저장한 그대로 돌아온다 (다른 게임판은 내려간다)
  ③ 지옥탈출 · 퇴근빵 · 대결은 건드리지 않는다 (진행 기록이 날아가면 안 된다)
  ④ 조종실이 상태를 통째로 보내도 슬롯이 안 지워진다
  ⑤ 이름 바꾸기 · 순서 · 지우기 · 없는 슬롯
  ⑥ 옛 '모드별 배치'(__scenes)는 슬롯으로 옮겨지고 파일에서 사라진다
  ⑦ 방송판에 자동 전환이 남아 있지 않다 · 편집기와 조종실에 단추가 있다

⚠️ pausetest 서버(5199)가 필요하다 — runall 이 띄운다.
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
PROJ = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
PT = os.environ.get('LM_SANDBOX_PT')
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:120]) if detail else ''))


def req(path, obj=None, method=None):
    data = json.dumps(obj).encode() if obj is not None else None
    r = urllib.request.Request(B + path, data, H, method=method or ('POST' if data is not None else 'GET'))
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def state():
    return req('/api/data')[1]


def put_state(**kv):
    st = state()
    st.update(kv)
    return req('/api/data', st)


def layout():
    return req('/api/layout')[1]


def board_of(st):
    on = [k for k in ('siggame', 'dicegame', 'pinball') if (st.get(k) or {}).get('enabled')]
    if st.get('roulette_enabled'):
        on.append('roulette')
    if st.get('slot_enabled') is True:
        on.append('slot')
    return on


L0 = layout()
S0 = state()
made = []
try:
    print('=' * 74); print('① 저장하면 셋이 담긴다'); print('=' * 74)
    ly = dict(L0); ly['ranking'] = {'x_px': 48, 'y_px': 520, 'scale': 1.0}; ly['__v'] = 2
    req('/api/layout', ly)
    req('/api/pinball/enable', {'enabled': True})
    put_state(donor_rank_enabled=True, notice_enabled=False)
    c, d = req('/api/presets/save', {'name': '핀볼 타임'})
    a = d.get('preset') or {}
    made.append(a.get('id'))
    chk('저장된다', c == 200 and a.get('id'), c)
    chk('이름이 붙는다', a.get('name') == '핀볼 타임')
    chk('자리가 담긴다', (a.get('layout') or {}).get('ranking', {}).get('y_px') == 520)
    chk('떠 있는 게임판이 담긴다', a.get('board') == 'pinball', a.get('board'))
    chk('켜고 끈 위젯이 담긴다', (a.get('switches') or {}).get('donor_rank_enabled') is True
        and (a.get('switches') or {}).get('notice_enabled') is False)

    # 둘째 슬롯 — 다른 상태
    ly = layout(); ly['ranking'] = {'x_px': 48, 'y_px': 960, 'scale': 0.8}
    req('/api/layout', ly)
    req('/api/dicegame/enable', {'on': True})
    put_state(donor_rank_enabled=False, notice_enabled=True)
    c, d = req('/api/presets/save', {'name': ''})
    b = d.get('preset') or {}
    made.append(b.get('id'))
    chk('이름을 비우면 번호로 붙는다', (b.get('name') or '').startswith('슬롯 '), b.get('name'))
    chk('주사위를 켜면 핀볼이 내려간 상태가 담긴다', b.get('board') == 'dicegame', b.get('board'))

    print(); print('=' * 74); print('② 불러오면 그대로 돌아온다'); print('=' * 74)
    rev0 = state().get('layout_rev') or 0
    c, d = req('/api/presets/apply', {'id': a.get('id')})
    st = state(); lyn = layout()
    chk('불러와진다', c == 200, c)
    chk('자리가 돌아온다 (엑셀판 y 520)', lyn.get('ranking', {}).get('y_px') == 520, lyn.get('ranking'))
    chk('게임판이 핀볼 하나만', board_of(st) == ['pinball'], board_of(st))
    chk('켜고 끈 위젯이 돌아온다', st.get('donor_rank_enabled') is True and st.get('notice_enabled') is False)
    chk('열린 편집기가 알 수 있게 번호가 오른다', (st.get('layout_rev') or 0) == rev0 + 1)
    chk('옛 모드 칸이 파일에 없다', '__scenes' not in lyn)
    c, d = req('/api/presets/apply', {'id': b.get('id')})
    st = state(); lyn = layout()
    chk('다른 슬롯도 — 크기까지', lyn.get('ranking', {}).get('y_px') == 960 and abs(lyn['ranking'].get('scale', 1) - .8) < 1e-6)
    chk('다른 슬롯도 — 게임판', board_of(st) == ['dicegame'], board_of(st))
    # 게임판 없는 슬롯 → 전부 내린다
    req('/api/dicegame/enable', {'on': False})
    c, d = req('/api/presets/save', {'name': '빈 판'})
    e = d.get('preset') or {}
    made.append(e.get('id'))
    req('/api/presets/apply', {'id': a.get('id')})
    req('/api/presets/apply', {'id': e.get('id')})
    chk('게임판 없는 슬롯은 떠 있던 판을 내린다', board_of(state()) == [], board_of(state()))

    print(); print('=' * 74); print('③ 진행 기록이 있는 것은 안 건드린다'); print('=' * 74)
    st = state()
    before = json.dumps([st.get('hell'), st.get('home_race_enabled'), (st.get('match_data') or {}).get('active')], sort_keys=True)
    req('/api/presets/apply', {'id': a.get('id')})
    st = state()
    after = json.dumps([st.get('hell'), st.get('home_race_enabled'), (st.get('match_data') or {}).get('active')], sort_keys=True)
    chk('지옥탈출 · 퇴근빵 · 대결이 그대로', before == after)
    SRC = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8').read()
    _ap = SRC[SRC.find('def api_presets_apply('):SRC.find('return jsonify', SRC.find('def api_presets_apply('))]
    chk('불러오기 코드가 그 셋을 안 만진다', 'hell' not in _ap and 'home_race' not in _ap and 'match_data' not in _ap)

    print(); print('=' * 74); print('④ 조종실이 통째로 보내도 안 지워진다'); print('=' * 74)
    st = state(); n = len(st.get('layout_presets') or [])
    st['layout_presets'] = []
    req('/api/data', st)
    chk('통째 저장으로 못 지운다', len(state().get('layout_presets') or []) == n)
    c, _ = req('/api/settings/patch', {'layout_presets': []})
    chk('설정 패치로도 못 지운다', len(state().get('layout_presets') or []) == n, c)

    print(); print('=' * 74); print('⑤ 이름 · 순서 · 지우기'); print('=' * 74)
    c, d = req('/api/presets/rename', {'id': b.get('id'), 'name': '주사위 타임'})
    chk('이름을 바꾼다', c == 200 and any(p.get('name') == '주사위 타임' for p in d.get('presets') or []))
    chk('빈 이름은 거절', req('/api/presets/rename', {'id': b.get('id'), 'name': ' '})[0] == 400)
    ids = [p['id'] for p in state().get('layout_presets')]
    i = ids.index(b.get('id'))
    req('/api/presets/move', {'id': b.get('id'), 'dir': -1})
    ids2 = [p['id'] for p in state().get('layout_presets')]
    chk('위로 옮긴다', ids2.index(b.get('id')) == max(0, i - 1))
    chk('없는 슬롯은 404', req('/api/presets/apply', {'id': 'nope'})[0] == 404
        and req('/api/presets/delete', {'id': 'nope'})[0] == 404)
    c, d = req('/api/presets/delete', {'id': e.get('id')})
    chk('지운다', c == 200 and all(p.get('id') != e.get('id') for p in d.get('presets') or []))
    made.remove(e.get('id'))

    print(); print('=' * 74); print('⑥ 옛 모드별 배치를 슬롯으로 옮긴다'); print('=' * 74)
    if PT and os.path.isdir(PT):
        lf = os.path.join(PT, 'layout.json')
        cur = layout()
        cur['__scenes'] = {'roulette': {'ranking': {'x_px': 48, 'y_px': 1200, 'scale': 1.0}}}
        io.open(lf, 'w', encoding='utf-8').write(json.dumps(cur, ensure_ascii=False))
        c, d = req('/api/presets')
        got = [p for p in d.get('presets') or [] if '(옮겨 옴)' in (p.get('name') or '')]
        for p in got:
            made.append(p.get('id'))
        chk('룰렛 모드가 슬롯이 된다', len(got) == 1 and got[0].get('board') == 'roulette', [p.get('name') for p in got])
        chk('그 모드 자리가 슬롯에 들어간다', got and got[0]['layout'].get('ranking', {}).get('y_px') == 1200)
        chk('파일에서 옛 칸이 사라진다 (두 번 안 옮긴다)', '__scenes' not in layout())
        c, d = req('/api/presets')
        chk('다시 열어도 또 안 생긴다', len([p for p in d.get('presets') or [] if '(옮겨 옴)' in (p.get('name') or '')]) == 1)
    else:
        chk('샌드박스 폴더를 안다 (LM_SANDBOX_PT)', False, PT)

    print(); print('=' * 74); print('⑦ 화면 쪽'); print('=' * 74)
    OV = io.open(os.path.join(PROJ, 'overlay.html'), encoding='utf-8').read()
    AD = io.open(os.path.join(PROJ, 'admin.html'), encoding='utf-8').read()
    CTL = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8').read()
    chk('방송판: 게임을 켰다고 자리가 저절로 안 바뀐다', 'layoutSceneOf' not in OV and 'layoutWithScene' not in OV)
    chk('편집기: 슬롯 칸이 있다', 'id="ps-list"' in AD and 'presetSaveNew()' in AD)
    chk('편집기: 옛 모드 편집이 없다', 'edScene' not in AD and 'scene-pick' not in AD)
    # ⚠️ 불러온 뒤 편집기가 옛 자리를 쥐고 있으면 다음에 끌 때 옛 배치를 통째로 되써 버린다
    chk('편집기: 불러오면 자리를 새로 쥔다', 'function presetUseLayout(' in AD and 'layout = ly;' in AD)
    chk('편집기: 조종실에서 불러와도 자리를 새로 읽는다', 'rev !== psLastRev' in AD)
    chk('편집기: 변수는 var (TDZ 로 멈추지 않게)', 'var psLastRev' in AD)
    chk('조종실: 슬롯 단추', 'id="ps-btns"' in CTL and 'psApply(' in CTL and 'psRender();' in CTL)
    chk('조종실: 이름을 안전하게 넣는다', "escapeHTML(p.name)" in CTL)
finally:
    for pid in made:
        if pid:
            req('/api/presets/delete', {'id': pid})
    L0.pop('__scenes', None)
    req('/api/layout', L0)
    req('/api/pinball/enable', {'enabled': False})
    req('/api/dicegame/enable', {'on': False})
    put_state(donor_rank_enabled=S0.get('donor_rank_enabled', False), notice_enabled=S0.get('notice_enabled', False))

print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
sys.exit(1 if BAD else 0)
