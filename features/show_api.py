# -*- coding: utf-8 -*-
"""📺 방송 화면 주소(/api/show)와 💾 세이브 슬롯(순서표 단계). 규칙 자체는 show.py 에 있다.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import show as showmod
import time
import uuid
from flask import jsonify, request
from server import (
    BOARD_NAMES, _hell_state, _layout_read, _layout_write, _stage_log, app, broadcast_event,
    file_lock, load_data, save_data,
)


# ==========================================
# 💾 세이브 슬롯 (대표님 2026-09-22)
#    "모드 1번에 룰렛 켜고 엑셀판 밑으로 내린 걸 저장해 두면, 1번 누르면 그대로 바뀌는 것".
#    담는 것: 위젯 자리·크기 + 위젯 켜기/끄기 + 떠 있던 게임판(하나).
#    ⚠️ 안 담는 것: 게임 속 내용(룰렛 칸·핀볼 명단)·점수·테마.
#    ⚠️ 지옥탈출·퇴근빵·대결은 진행 기록이 있어 불러와도 건드리지 않는다.
# ==========================================
# ⚠️ 켜고 끈 위젯 목록(예전 PRESET_FLAGS)은 이제 show.py 의 고정 자리(HUD_KEYS)다.
PRESET_MAX = 60                  # 제한 없이 — 다만 실수로 끝없이 쌓이지 않게 넉넉한 뚜껑만
PRESET_NAME_MAX = 30
_SCENE_LABEL = {'roulette': '🎡 룰렛', 'slot': '🎰 슬롯머신', 'siggame': '🃏 시그뒤집기',
                'dicegame': '🎲 주사위', 'pinball': '🎱 핀볼', 'match': '⚔️ 대결',
                'race': '🔥 지옥탈출 · 퇴근빵', 'extra': '🎮 번외 게임판'}


def _preset_board_now(state):
    """지금 무대(옛 이름 board 로도 남긴다 — 옛 조종실·편집기가 읽는다)."""
    return showmod.cue_from_state(state)['stage'] or ''


def _preset_switches_now(state):
    """옛 모양 switches — 옛 조종실·편집기 표시용. 진짜 값은 hud 다."""
    hud = showmod.ensure(state)['hud']
    sw = {lk: hud[k] for k, lk in showmod.HUD_LEGACY.items()}
    sw['fundjar'] = hud['fundjar']
    return sw


def _preset_layout_of(ly):
    """배치에서 위젯 자리만 떠 낸다(옛 모드 칸·다른 표시는 뺀다)."""
    out = {'__v': 2, '__free': bool(ly.get('__free', True))}
    for k, v in ly.items():
        if k.startswith('__'):
            continue
        if isinstance(v, dict) and 'x_px' in v:
            out[k] = {'x_px': v.get('x_px', 0), 'y_px': v.get('y_px', 0), 'scale': v.get('scale', 1.0)}
    return out


def _presets(state):
    ps = state.get('layout_presets')
    if not isinstance(ps, list):
        ps = []
    state['layout_presets'] = [p for p in ps if isinstance(p, dict) and p.get('id')]
    return state['layout_presets']


def _preset_new_id():
    return 'p' + uuid.uuid4().hex[:10]


def _presets_migrate(state):
    """옛 '모드별 배치'(배치 파일의 __scenes)를 슬롯으로 옮긴다 — 한 번만(옮긴 뒤 파일에서 지운다).
       ⚠️ 지운 뒤 쓰기는 file_lock 안에서 부른다."""
    ly = _layout_read()
    sc = ly.get('__scenes')
    if not isinstance(sc, dict) or not sc:
        if '__scenes' in ly:
            ly.pop('__scenes', None); _layout_write(ly)
        return False
    ps = _presets(state)
    base = _preset_layout_of(ly)
    for key, over in sc.items():
        if not isinstance(over, dict) or not over or len(ps) >= PRESET_MAX:
            continue
        merged = dict(base)
        for wid, pos in over.items():
            if isinstance(pos, dict) and 'x_px' in pos:
                merged[wid] = {'x_px': pos.get('x_px', 0), 'y_px': pos.get('y_px', 0), 'scale': pos.get('scale', 1.0)}
        ps.append({'id': _preset_new_id(), 'name': _SCENE_LABEL.get(key, key) + ' (옮겨 옴)',
                   'layout': merged, 'switches': _preset_switches_now(state),
                   'board': key if key in BOARD_NAMES else '', 'saved_at': int(time.time())})
    ly.pop('__scenes', None)
    _layout_write(ly)
    print('  💾 [세이브 슬롯] 옛 모드별 배치 %d개를 슬롯으로 옮겼습니다' % len(sc), flush=True)
    return True


def _keep_cue(state, before_ids):
    """단계를 옮기거나 지운 뒤에도 '지금 단계'(cue_at, 자리 번호)가 같은 단계를 가리키게 한다.
    지금 단계를 지웠으면 그 바로 앞을 가리킨다 — 그래야 [다음 ▶]이 지운 단계 다음 것으로 간다."""
    s = showmod.ensure(state)
    at = s['cue_at']
    if not (0 <= at < len(before_ids)):
        return
    ids = [x.get('id') for x in (state.get('layout_presets') or [])]
    cur = before_ids[at]
    s['cue_at'] = ids.index(cur) if cur in ids else min(at, len(ids)) - 1


def _presets_save_state(state):
    save_data(state)
    broadcast_event('update', state)


@app.route('/api/presets', methods=['GET'])
def api_presets():
    with file_lock:
        state = load_data()
        if _presets_migrate(state):
            _presets_save_state(state)
        return jsonify({'status': 'success', 'presets': _presets(state)})


@app.route('/api/presets/save', methods=['POST'])
def api_presets_save():
    """지금 상태를 슬롯에 적는다. id 가 있으면 그 칸을 덮고, 없으면 새 칸."""
    body = request.get_json(silent=True) or {}
    pid = str(body.get('id') or '')
    name = str(body.get('name') or '').strip()[:PRESET_NAME_MAX]
    with file_lock:
        state = load_data()
        _presets_migrate(state)
        ps = _presets(state)
        _cue = showmod.cue_from_state(state)
        snap = {'layout': _preset_layout_of(_layout_read()),
                'hud': _cue['hud'], 'stage': _cue['stage'],
                'switches': _preset_switches_now(state),      # 옛 화면 표시용(읽기만)
                'board': _preset_board_now(state),
                'saved_at': int(time.time())}
        hit = next((x for x in ps if x.get('id') == pid), None) if pid else None
        if hit:
            hit.update(snap)
            if name:
                hit['name'] = name
        else:
            if len(ps) >= PRESET_MAX:
                return jsonify({'status': 'error', 'message': '슬롯이 너무 많습니다(%d개). 안 쓰는 걸 지워 주세요' % PRESET_MAX}), 400
            hit = dict(snap, id=_preset_new_id(), name=name or ('슬롯 %d' % (len(ps) + 1)))
            ps.append(hit)
        _presets_save_state(state)
    return jsonify({'status': 'success', 'preset': hit, 'presets': ps})


@app.route('/api/presets/rename', methods=['POST'])
def api_presets_rename():
    body = request.get_json(silent=True) or {}
    pid = str(body.get('id') or '')
    name = str(body.get('name') or '').strip()[:PRESET_NAME_MAX]
    if not name:
        return jsonify({'status': 'error', 'message': '이름을 적어 주세요'}), 400
    with file_lock:
        state = load_data()
        ps = _presets(state)
        hit = next((x for x in ps if x.get('id') == pid), None)
        if not hit:
            return jsonify({'status': 'error', 'message': '없는 슬롯입니다'}), 404
        hit['name'] = name
        _presets_save_state(state)
    return jsonify({'status': 'success', 'presets': ps})


@app.route('/api/presets/move', methods=['POST'])
def api_presets_move():
    """순서 바꾸기 — dir -1 이면 앞으로, +1 이면 뒤로."""
    body = request.get_json(silent=True) or {}
    pid = str(body.get('id') or '')
    try:
        d = -1 if int(body.get('dir')) < 0 else 1
    except (TypeError, ValueError):
        d = 1
    with file_lock:
        state = load_data()
        ps = _presets(state)
        i = next((k for k, x in enumerate(ps) if x.get('id') == pid), -1)
        j = i + d
        if i >= 0 and 0 <= j < len(ps):
            before = [x.get('id') for x in ps]
            ps[i], ps[j] = ps[j], ps[i]
            _keep_cue(state, before)
            _presets_save_state(state)
    return jsonify({'status': 'success', 'presets': ps, 'show': showmod.view(state)})


@app.route('/api/presets/delete', methods=['POST'])
def api_presets_delete():
    body = request.get_json(silent=True) or {}
    pid = str(body.get('id') or '')
    with file_lock:
        state = load_data()
        ps = _presets(state)
        n = len(ps)
        before = [x.get('id') for x in ps]
        state['layout_presets'] = [x for x in ps if x.get('id') != pid]
        if len(state['layout_presets']) == n:
            return jsonify({'status': 'error', 'message': '없는 슬롯입니다'}), 404
        _keep_cue(state, before)
        _presets_save_state(state)
    return jsonify({'status': 'success', 'presets': state['layout_presets'], 'show': showmod.view(state)})


def _cue_apply(state, hit):
    """순서표 한 단계(세이브 슬롯)를 불러온다 — 배치 · 고정 자리 · 무대. file_lock 안에서 부른다."""
    ly = _layout_read()
    ly.pop('__scenes', None)
    for k, v in (hit.get('layout') or {}).items():
        ly[k] = v
    ly['__v'] = 2
    _layout_write(ly)
    prev = showmod.ensure(state)['stage']
    showmod.apply_cue(state, hit)
    _stage_log(prev, state['show']['stage'])
    ps = _presets(state)
    state['show']['cue_at'] = next((i for i, x in enumerate(ps) if x.get('id') == hit.get('id')), -1)
    try:
        state['layout_rev'] = int(state.get('layout_rev') or 0) + 1
    except (TypeError, ValueError):
        state['layout_rev'] = 1
    return ly


@app.route('/api/presets/apply', methods=['POST'])
def api_presets_apply():
    """슬롯을 불러온다 — 자리 · 켜기/끄기 · 게임판을 저장한 그대로."""
    body = request.get_json(silent=True) or {}
    pid = str(body.get('id') or '')
    with file_lock:
        state = load_data()
        _presets_migrate(state)
        ps = _presets(state)
        hit = next((x for x in ps if x.get('id') == pid), None)
        if not hit:
            return jsonify({'status': 'error', 'message': '없는 슬롯입니다'}), 404
        # 자리(슬롯에 없는 위젯은 지금 자리 그대로) · 고정 자리 · 무대 — _cue_apply 한 곳에서
        ly = _cue_apply(state, hit)
        _presets_save_state(state)
        print('  💾 [순서표] "%s" 불러옴 — %s' % (hit.get('name'), showmod.summary(state)), flush=True)
    return jsonify({'status': 'success', 'preset': hit, 'layout': ly, 'show': showmod.view(state)})

# ==========================================
# 📺 방송 화면 — 무대 · 고정 자리 · 알림 · 순서표 (2026-09-29 개편)
#    화면을 바꾸는 단 하나의 길. 규칙은 show.py 에 있다.
#    예전의 roulette_enabled · sig_tally_enabled 같은 스위치는 이제 여기서만 바뀐다(show 가 계산해 적는다).
# ==========================================
def _show_cues(state):
    """순서표 = 세이브 슬롯 목록(순서 그대로). 조종실이 그릴 만큼만."""
    out = []
    for p in _presets(state):
        out.append({'id': p.get('id'), 'name': p.get('name') or '',
                    'stage': showmod.cue_stage(p), 'hud': showmod.cue_hud(p)})
    return out


@app.route('/api/show', methods=['GET'])
def api_show_get():
    state = load_data()
    return jsonify({'status': 'success', 'show': showmod.view(state), 'cues': _show_cues(state)})


@app.route('/api/show', methods=['POST'])
def api_show_set():
    """body 에 든 것만 바꾼다.
         {stage: 'pinball' | null, temp: false}      무대(하나만). null 이면 비운다
         {hud: {notice: true, best: false}}           고정 자리
         {alerts: {popup: false}}                     알림
         {cue: 'next' | 'prev' | 'go', id: '...'}      순서표(세이브 슬롯) 단계 넘기기
    """
    body = request.get_json(silent=True) or {}
    with file_lock:
        state = load_data()
        prev = showmod.ensure(state)['stage']
        if 'stage' in body:
            st = body.get('stage') or None
            if st is not None and st not in showmod.STAGES:
                return jsonify({'status': 'error', 'message': '없는 무대입니다: %s' % st}), 400
            if st == 'hell':
                h = _hell_state(state)
                if not h.get('started_at'):
                    return jsonify({'status': 'error', 'message': '지옥탈출은 먼저 [시작] 을 눌러 주세요'}), 409
                h['on'] = True            # 다시 올리면 다시 센다(기록은 그대로)
            showmod.set_stage(state, st, temp=bool(body.get('temp')))
        for k, v in ((body.get('hud') or {}) if isinstance(body.get('hud'), dict) else {}).items():
            if not showmod.set_hud(state, k, v):
                return jsonify({'status': 'error', 'message': '없는 고정 자리입니다: %s' % k}), 400
        for k, v in ((body.get('alerts') or {}) if isinstance(body.get('alerts'), dict) else {}).items():
            if not showmod.set_alert(state, k, v):
                return jsonify({'status': 'error', 'message': '없는 알림입니다: %s' % k}), 400
        cue = body.get('cue')
        if cue:
            ps = _presets(state)
            at = showmod.ensure(state)['cue_at']
            if cue == 'next':
                idx = at + 1
            elif cue == 'prev':
                idx = at - 1
            elif cue == 'go':
                idx = next((i for i, x in enumerate(ps) if x.get('id') == str(body.get('id') or '')), -1)
            else:
                return jsonify({'status': 'error', 'message': '모르는 순서표 명령입니다'}), 400
            if not (0 <= idx < len(ps)):
                return jsonify({'status': 'error',
                                'message': '순서표 끝이에요' if ps else '순서표가 비어 있어요 — 지금 화면을 단계로 저장해 주세요'}), 409
            _cue_apply(state, ps[idx])
            print('  📺 [순서표] %d/%d "%s"' % (idx + 1, len(ps), ps[idx].get('name')), flush=True)
        _stage_log(prev, state['show']['stage'])
        save_data(state)
        broadcast_event('update', state)
        v = showmod.view(state)
        cues = _show_cues(state)
    return jsonify({'status': 'success', 'show': v, 'cues': cues})
