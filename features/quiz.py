# -*- coding: utf-8 -*-
"""🧩 퀴즈판 — 초성 · 사자성어 (대표님 2026-10-06 "일단 만들어봐 써보고 설명해줄게").

방송판에는 **네모칸만** 뜬다(대표님: 바탕 · "초성 퀴즈" · 몇 번째 · 분류 · 남은 초 · 정답자 다 빼고 "그냥 네모칸만").
점수도 없다. 진행은 조종실 퀴즈 탭: [다음 문제] · [힌트 한 글자] · [정답 공개] · [퀴즈판 내리기].

칸(tiles) 한 칸 = {'c': 보일 글자, 's': 상태}
    's' — 'q' 초성(문제)   'g' 처음부터 보여 주는 글자(사자성어 앞 두 글자 · 한글 아닌 글자)
          'b' 빈칸          'h' 힌트로 연 글자        'o' 정답 공개로 연 글자
⚠️ 정답(cur)은 조종실에만 간다. 방송판(로그인 없는 화면)으로는 칸만 나간다 — server.strip_private_state 가 cur 를 뺀다.
   칸에도 빈칸 · 초성 자리에는 정답 글자를 안 싣는다(열린 칸만 글자가 있다).
⚠️ 무대는 하나 — show.py 의 STAGES 에 'quiz' 가 있다. 다음 문제를 누르면 퀴즈가 무대에 오르고 다른 게임판은 내려간다.
"""
import random
import show as showmod
from flask import jsonify, request
from server import _stage_log, app, broadcast_event, file_lock, load_data, save_data
from features.quiz_bank import CHOSUNG, IDIOMS

KINDS = ('chosung', 'idiom')
KIND_LABEL = {'chosung': '초성', 'idiom': '사자성어'}
CUSTOM_MAX = 500          # 종류마다 내 문제 최대 개수
_INITIALS = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'


def _is_syllable(ch):
    return '가' <= ch <= '힣'


def _chosung(ch):
    return _INITIALS[(ord(ch) - 0xAC00) // 588] if _is_syllable(ch) else ch


def _quiz_state(state):
    """늘 온전한 모양으로(옛 저장본에는 없다)."""
    g = state.get('quiz')
    if not isinstance(g, dict):
        g = {}
        state['quiz'] = g
    if g.get('kind') not in KINDS:
        g['kind'] = 'chosung'
    if not isinstance(g.get('cur'), dict):
        g['cur'] = None
    if not isinstance(g.get('tiles'), list):
        g['tiles'] = []
    g['revealed'] = bool(g.get('revealed'))
    for key in ('used', 'custom'):
        v = g.get(key) if isinstance(g.get(key), dict) else {}
        g[key] = {k: [x for x in (v.get(k) or []) if isinstance(x, (str, list))] for k in KINDS}
    return g


def quiz_reset_session(state):
    """방송 시작 · 종료 때(server.reset_session_keys) — 지금 문제 · 칸 · 그날 나온 문제를 비운다. 내 문제는 남긴다."""
    g = state.get('quiz')
    if isinstance(g, dict):
        g.update({'cur': None, 'tiles': [], 'revealed': False, 'used': {k: [] for k in KINDS}})


def _bank(g, kind):
    """기본 문제 + 내 문제. [(정답, 분류 또는 뜻), …] — 정답이 같으면 하나만."""
    base = CHOSUNG if kind == 'chosung' else IDIOMS
    out, seen = [], set()
    for a, b in list(base) + [tuple(x) for x in g['custom'][kind] if isinstance(x, list) and len(x) == 2]:
        if a not in seen:
            seen.add(a)
            out.append((a, b))
    return out


def _tiles_for(kind, answer):
    chars = [c for c in str(answer) if not c.isspace()]
    if kind == 'idiom':
        return [{'c': c, 's': 'g'} if i < 2 else {'c': '', 's': 'b'} for i, c in enumerate(chars)]
    return [{'c': _chosung(c), 's': 'q'} if _is_syllable(c) else {'c': c, 's': 'g'} for c in chars]


def _public(g):
    """조종실이 받는 퀴즈 상태(정답 포함). 방송판은 server.strip_private_state 가 cur 를 뺀 것을 받는다."""
    return {'kind': g['kind'], 'cur': g['cur'], 'tiles': g['tiles'], 'revealed': g['revealed'],
            'counts': {k: len(_bank(g, k)) for k in KINDS},
            'left': {k: len([1 for a, _ in _bank(g, k) if a not in g['used'][k]]) for k in KINDS},
            'custom': {k: len(g['custom'][k]) for k in KINDS}}


def _save(state, g):
    save_data(state)
    broadcast_event('update', state)
    return _public(g)


def _on_stage(state):
    prev = showmod.ensure(state)['stage']
    showmod.set_stage(state, 'quiz')
    _stage_log(prev, 'quiz')


@app.route('/api/quiz/next', methods=['POST'])
def api_quiz_next():
    body = request.get_json(silent=True) or {}
    with file_lock:
        state = load_data()
        g = _quiz_state(state)
        if body.get('kind') in KINDS:
            g['kind'] = body['kind']
        kind = g['kind']
        bank = _bank(g, kind)
        if not bank:
            return jsonify({'status': 'error', 'message': '문제가 없습니다'}), 400
        used = g['used'][kind]
        left = [x for x in bank if x[0] not in used]
        wrapped = False
        if not left:                      # 한 바퀴 다 돌았다 — 처음부터(그날 방송에서 같은 문제가 또 나오는 건 이때뿐)
            used.clear()
            left = list(bank)
            wrapped = True
        cur = g['cur'] or {}
        if len(left) > 1 and cur.get('answer'):
            left = [x for x in left if x[0] != cur.get('answer')] or left   # 방금 것 바로 다시 안 나오게
        answer, note = random.choice(left)
        used.append(answer)
        g['cur'] = {'kind': kind, 'answer': answer, 'note': note}
        g['tiles'] = _tiles_for(kind, answer)
        g['revealed'] = False
        _on_stage(state)
        out = _save(state, g)
    print('  🧩 [퀴즈] %s — %s' % (KIND_LABEL[kind], answer), flush=True)
    return jsonify({'status': 'success', 'quiz': out, 'wrapped': wrapped})


@app.route('/api/quiz/hint', methods=['POST'])
def api_quiz_hint():
    with file_lock:
        state = load_data()
        g = _quiz_state(state)
        cur = g['cur']
        if not cur or g['revealed']:
            return jsonify({'status': 'error', 'message': '열 글자가 없습니다 — [다음 문제]부터 눌러 주세요'}), 400
        chars = [c for c in str(cur.get('answer') or '') if not c.isspace()]
        for i, t in enumerate(g['tiles']):
            if t.get('s') in ('q', 'b') and i < len(chars):
                g['tiles'][i] = {'c': chars[i], 's': 'h'}
                break
        else:
            return jsonify({'status': 'error', 'message': '이미 다 열었습니다 — [정답 공개]를 눌러 주세요'}), 400
        out = _save(state, g)
    return jsonify({'status': 'success', 'quiz': out})


@app.route('/api/quiz/reveal', methods=['POST'])
def api_quiz_reveal():
    with file_lock:
        state = load_data()
        g = _quiz_state(state)
        cur = g['cur']
        if not cur:
            return jsonify({'status': 'error', 'message': '아직 문제가 없습니다'}), 400
        chars = [c for c in str(cur.get('answer') or '') if not c.isspace()]
        g['tiles'] = [{'c': chars[i], 's': 'g' if t.get('s') == 'g' else 'o'} if i < len(chars) else t
                      for i, t in enumerate(g['tiles'])]
        g['revealed'] = True
        out = _save(state, g)
    return jsonify({'status': 'success', 'quiz': out})


@app.route('/api/quiz/show', methods=['POST'])
def api_quiz_show():
    """방송에 띄우기 / 내리기. 띄울 문제가 없으면 띄우기 전에 [다음 문제]가 필요하다."""
    body = request.get_json(silent=True) or {}
    on = bool(body.get('on'))
    with file_lock:
        state = load_data()
        g = _quiz_state(state)
        prev = showmod.ensure(state)['stage']
        if on:
            if not g['tiles']:
                return jsonify({'status': 'error', 'message': '띄울 문제가 없습니다 — [다음 문제]를 눌러 주세요'}), 400
            showmod.set_stage(state, 'quiz')
        else:
            showmod.clear_stage(state, 'quiz')
        _stage_log(prev, state['show']['stage'])
        out = _save(state, g)
    return jsonify({'status': 'success', 'quiz': out, 'on': state['show']['stage'] == 'quiz'})


@app.route('/api/quiz/custom', methods=['POST'])
def api_quiz_custom():
    """내 문제 더하기 — 한 줄에 하나 "정답 | 분류(초성) · 뜻(사자성어)". mode='clear' 면 그 종류 내 문제를 비운다."""
    body = request.get_json(silent=True) or {}
    kind = body.get('kind')
    if kind not in KINDS:
        return jsonify({'status': 'error', 'message': '종류(초성 · 사자성어)를 골라 주세요'}), 400
    with file_lock:
        state = load_data()
        g = _quiz_state(state)
        mine = g['custom'][kind]
        if body.get('mode') == 'clear':
            n = len(mine)
            mine.clear()
            out = _save(state, g)
            return jsonify({'status': 'success', 'quiz': out, 'cleared': n})
        added, bad = 0, []
        have = {a for a, _ in _bank(g, kind)}
        for raw in str(body.get('text') or '').splitlines():
            line = raw.strip()
            if not line:
                continue
            a, _, b = line.partition('|')
            a = ''.join(a.split())          # 정답 안 띄어쓰기는 뺀다(칸 수가 글자 수다)
            b = b.strip()[:60]
            ok = 2 <= len(a) <= 10 and any(_is_syllable(c) for c in a)
            if kind == 'idiom':
                ok = len(a) == 4 and all(_is_syllable(c) for c in a)
            if not ok:
                bad.append(line[:30])
                continue
            if a in have:
                continue
            if len(mine) >= CUSTOM_MAX:
                bad.append(line[:30] + ' (가득 참)')
                continue
            mine.append([a, b])
            have.add(a)
            added += 1
        out = _save(state, g)
    return jsonify({'status': 'success', 'quiz': out, 'added': added, 'bad': bad[:10]})
