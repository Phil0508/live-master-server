# -*- coding: utf-8 -*-
"""🧩 퀴즈판 — 초성 · 사자성어 (대표님 2026-10-06 "일단 만들어봐 써보고 설명해줄게").

방송판에는 **네모칸만** 뜬다(대표님: 바탕 · "초성 퀴즈" · 몇 번째 · 분류 · 남은 초 · 정답자 다 빼고 "그냥 네모칸만").
점수도 없다. 진행은 조종실 퀴즈 탭: [다음 문제] · [힌트 한 글자] · [정답 공개] · [퀴즈판 내리기].

📋 순서(order) — 대표님 2026-10-06 "순서를 내가 볼 수 있게, 그것도 수정 가능하게".
   종류마다 그날 낼 문제를 미리 줄 세운다(처음엔 섞어서). [다음 문제]는 맨 앞을 낸다.
   조종실에서 ▲ ▼ · 맨 위로 · 빼기 · 지금 띄우기 · 섞기로 고친다(/api/quiz/order).
⚡ 지금 바로 띄우기(/api/quiz/now) — "지금 당장 띄울 초성을 적을 수 있게". 정답을 적으면 초성으로 나가고
   힌트 · 정답 공개도 된다. 초성(ㄱ~ㅎ)만 적으면 그대로 나가지만 정답을 모르니 열 수는 없다.

칸(tiles) 한 칸 = {'c': 보일 글자, 's': 상태}
    's' — 'q' 초성(문제)   'g' 처음부터 보여 주는 글자(사자성어 앞 두 글자 · 한글 아닌 글자)
          'b' 빈칸          'h' 힌트로 연 글자        'o' 정답 공개로 연 글자
⚠️ 정답(cur) · 순서(order) · 내 문제는 조종실에만 간다. 방송판(로그인 없는 화면)으로는 칸만 나간다 —
   server.strip_private_state 가 tiles · revealed 말고는 다 뺀다. 칸에도 빈칸 · 초성 자리엔 정답 글자를 안 싣는다.
⚠️ 무대는 하나 — show.py 의 STAGES 에 'quiz' 가 있다. 문제를 띄우면 퀴즈가 무대에 오르고 다른 게임판은 내려간다.
"""
import random
import show as showmod
from flask import jsonify, request
from server import _stage_log, app, broadcast_event, file_lock, load_data, save_data
from features.quiz_bank import CHOSUNG, IDIOMS

KINDS = ('chosung', 'idiom')
KIND_LABEL = {'chosung': '초성', 'idiom': '사자성어'}
CUSTOM_MAX = 500          # 종류마다 내 문제 최대 개수
NOW_MAX = 12              # 지금 바로 띄우기 — 칸 수 한도(방송판 폭 1080 에 120 칸이 여덟 개쯤)
_INITIALS = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'


def _is_syllable(ch):
    return '가' <= ch <= '힣'


def _is_jamo(ch):
    return 'ㄱ' <= ch <= 'ㅣ'          # 한글 낱자(ㄱ~ㅎ · ㅏ~ㅣ)


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
    # ⚠️ 칸 · 순서 · 내 문제는 하나하나 모양을 본다 — 옛 백업을 되살리거나 조종실이 다른 모양(문제 수 등)을
    #    섞어 보내도 퀴즈 단추가 500 으로 죽지 않게(10-06 점검)
    g['tiles'] = [{'c': str(t.get('c') or '')[:2], 's': t.get('s') if t.get('s') in ('q', 'g', 'b', 'h', 'o') else 'b'}
                  for t in (g.get('tiles') if isinstance(g.get('tiles'), list) else []) if isinstance(t, dict)]
    g['revealed'] = bool(g.get('revealed'))

    def _lst(v, k):
        x = v.get(k) if isinstance(v, dict) else None
        return x if isinstance(x, list) else []
    for key in ('used', 'order'):
        v = g.get(key)
        g[key] = {k: [x for x in _lst(v, k) if isinstance(x, str)] for k in KINDS}
    v = g.get('custom')
    g['custom'] = {k: [[x[0], str(x[1] or '')[:60]] for x in _lst(v, k)
                       if isinstance(x, (list, tuple)) and len(x) == 2 and isinstance(x[0], str) and x[0]] for k in KINDS}
    return g


def _body():
    """요청 본문 — 사전(JSON 객체)이 아니면 빈 것으로 본다."""
    b = request.get_json(silent=True)
    return b if isinstance(b, dict) else {}


def quiz_reset_session(state):
    """방송 시작 · 종료 때(server.reset_session_keys) — 지금 문제 · 칸 · 그날 나온 문제 · 순서를 비운다. 내 문제는 남긴다."""
    g = state.get('quiz')
    if isinstance(g, dict):
        g.update({'cur': None, 'tiles': [], 'revealed': False,
                  'used': {k: [] for k in KINDS}, 'order': {k: [] for k in KINDS}})


def _bank(g, kind):
    """기본 문제 + 내 문제. [(정답, 분류 또는 뜻), …] — 정답이 같으면 하나만."""
    base = CHOSUNG if kind == 'chosung' else IDIOMS
    out, seen = [], set()
    for a, b in list(base) + [tuple(x) for x in g['custom'][kind] if isinstance(x, list) and len(x) == 2]:
        if a not in seen:
            seen.add(a)
            out.append((a, b))
    return out


def _order(g, kind, wrap=False):
    """그날 낼 순서(남은 것만). 문제집에 없거나 이미 나온 것은 걸러 낸다.
       비어 있으면 아직 안 나온 문제를 섞어 새로 세운다. wrap=True 면 다 나왔을 때 처음부터(나온 목록을 비운다).
       돌려받는 값: (순서 목록, 처음부터 다시 세웠는가)"""
    names = [a for a, _ in _bank(g, kind)]
    have, used = set(names), set(g['used'][kind])
    o, seen = [], set()
    for a in g['order'][kind]:
        if isinstance(a, str) and a in have and a not in used and a not in seen:
            seen.add(a)
            o.append(a)
    wrapped = False
    if not o:
        rest = [a for a in names if a not in used]
        if not rest and wrap and names:
            g['used'][kind] = []
            rest = list(names)
            wrapped = True
        random.shuffle(rest)
        o = rest
    g['order'][kind] = o
    return o, wrapped


def _tiles_for(kind, answer):
    chars = [c for c in str(answer) if not c.isspace()]
    if kind == 'idiom':
        return [{'c': c, 's': 'g'} if i < 2 else {'c': '', 's': 'b'} for i, c in enumerate(chars)]
    return [{'c': _chosung(c), 's': 'q'} if _is_syllable(c) else {'c': c, 's': 'g'} for c in chars]


def _public(g):
    """조종실이 받는 퀴즈 상태(정답 · 순서 포함). 방송판은 server.strip_private_state 가 칸만 남긴 것을 받는다."""
    notes = {k: dict(_bank(g, k)) for k in KINDS}
    return {'kind': g['kind'], 'cur': g['cur'], 'tiles': g['tiles'], 'revealed': g['revealed'],
            'counts': {k: len(notes[k]) for k in KINDS},
            'left': {k: len(g['order'][k]) for k in KINDS},
            'order': {k: [[a, notes[k].get(a, '')] for a in g['order'][k]] for k in KINDS},
            'custom': {k: len(g['custom'][k]) for k in KINDS}}


def _save(state, g):
    for k in KINDS:
        _order(g, k)                # 순서를 저장 전에 세운다(돌려줄 때 섞으면 저장본과 달라진다)
    save_data(state)
    broadcast_event('update', state)
    return _public(g)


def _put(state, g, kind, answer, note):
    """문제 하나를 방송에 띄운다 — 칸을 만들고 무대에 올린다. 순서 · 나온 목록에서도 정리한다."""
    if answer:
        if answer in g['order'][kind]:
            g['order'][kind].remove(answer)
        if answer not in g['used'][kind] and answer in dict(_bank(g, kind)):
            g['used'][kind].append(answer)
    g['kind'] = kind
    g['revealed'] = False
    prev = showmod.ensure(state)['stage']
    showmod.set_stage(state, 'quiz')
    _stage_log(prev, 'quiz')
    print('  🧩 [퀴즈] %s — %s' % (KIND_LABEL[kind], answer or (g['cur'] or {}).get('q', '')), flush=True)


@app.route('/api/quiz/next', methods=['POST'])
def api_quiz_next():
    body = _body()
    with file_lock:
        state = load_data()
        g = _quiz_state(state)
        if body.get('kind') in KINDS:
            g['kind'] = body['kind']
        kind = g['kind']
        o, wrapped = _order(g, kind, wrap=True)    # 한 바퀴 다 돌았으면 처음부터(그날 같은 문제가 또 나오는 건 이때뿐)
        if not o:
            return jsonify({'status': 'error', 'message': '문제가 없습니다'}), 400
        answer = o[0]
        g['cur'] = {'kind': kind, 'answer': answer, 'note': dict(_bank(g, kind)).get(answer, '')}
        g['tiles'] = _tiles_for(kind, answer)
        _put(state, g, kind, answer, g['cur']['note'])
        out = _save(state, g)
    return jsonify({'status': 'success', 'quiz': out, 'wrapped': wrapped})


@app.route('/api/quiz/state', methods=['GET'])
def api_quiz_state():
    """조종실이 퀴즈 탭을 열 때 — 순서 · 분류/뜻 · 문제 수(실시간 상태에는 분류 · 뜻이 없다)."""
    with file_lock:
        state = load_data()
        g = _quiz_state(state)
        before = {k: list(g['order'][k]) for k in KINDS}
        for k in KINDS:
            _order(g, k)
        if any(g['order'][k] != before[k] for k in KINDS):
            out = _save(state, g)          # 순서를 처음 세웠으면 저장해 둔다(안 그러면 열 때마다 다르게 섞인다)
        else:
            out = _public(g)               # ⚠️ 바뀐 게 없으면 저장 · 방송 알림을 안 한다(한 종류를 다 냈을 때 열 때마다 저장하던 것)
    return jsonify({'status': 'success', 'quiz': out})


@app.route('/api/quiz/order', methods=['POST'])
def api_quiz_order():
    """순서 고치기. action: up · down · top · remove(오늘은 빼기) · play(지금 띄우기) · shuffle(섞기)."""
    body = _body()
    kind = body.get('kind')
    action = body.get('action')
    answer = str(body.get('answer') or '')
    if kind not in KINDS or action not in ('up', 'down', 'top', 'remove', 'play', 'shuffle'):
        return jsonify({'status': 'error', 'message': '종류 · 할 일을 다시 골라 주세요'}), 400
    with file_lock:
        state = load_data()
        g = _quiz_state(state)
        o, _ = _order(g, kind)
        if action == 'shuffle':
            random.shuffle(o)
        else:
            if answer not in o:
                return jsonify({'status': 'error', 'message': "'%s' 은(는) 순서에 없습니다 — 화면을 새로 고쳐 주세요" % answer[:20]}), 404
            i = o.index(answer)
            if action == 'up' and i > 0:
                o[i - 1], o[i] = o[i], o[i - 1]
            elif action == 'down' and i < len(o) - 1:
                o[i + 1], o[i] = o[i], o[i + 1]
            elif action == 'top':
                o.insert(0, o.pop(i))
            elif action == 'remove':
                o.pop(i)
                g['used'][kind].append(answer)          # 오늘은 안 낸다(내일 방송엔 다시 들어온다)
            elif action == 'play':
                g['cur'] = {'kind': kind, 'answer': answer, 'note': dict(_bank(g, kind)).get(answer, '')}
                g['tiles'] = _tiles_for(kind, answer)
                _put(state, g, kind, answer, g['cur']['note'])
        out = _save(state, g)
    return jsonify({'status': 'success', 'quiz': out})


@app.route('/api/quiz/now', methods=['POST'])
def api_quiz_now():
    """지금 바로 띄우기 — 조종실 입력칸에 적은 것.
       · 정답(한글 낱말)을 적으면: 초성으로 나간다. 사자성어를 고른 채 한글 네 글자면 앞 두 글자 + 빈칸 둘.
       · 초성(ㄱ~ㅎ)만 적으면: 그대로 나간다 — 정답을 모르니 힌트 · 정답 공개는 안 된다."""
    body = _body()
    text = ''.join(str(body.get('text') or '').split())
    kind = body.get('kind') if body.get('kind') in KINDS else 'chosung'
    note = str(body.get('note') or '').strip()[:60]
    if not text:
        return jsonify({'status': 'error', 'message': '띄울 글자를 적어 주세요'}), 400
    if len(text) > NOW_MAX:
        return jsonify({'status': 'error', 'message': '%d글자까지만 됩니다(방송 화면 폭)' % NOW_MAX}), 400
    jamo_only = all(_is_jamo(c) for c in text)
    if not jamo_only and not any(_is_syllable(c) for c in text):
        return jsonify({'status': 'error', 'message': '한글 정답이나 초성(ㄱ~ㅎ)을 적어 주세요'}), 400
    with file_lock:
        state = load_data()
        g = _quiz_state(state)
        if jamo_only:
            g['cur'] = {'kind': 'chosung', 'answer': '', 'note': note, 'q': text}
            g['tiles'] = [{'c': c, 's': 'q'} for c in text]
            _put(state, g, 'chosung', '', note)
        else:
            k = 'idiom' if kind == 'idiom' and len(text) == 4 and all(_is_syllable(c) for c in text) else 'chosung'
            g['cur'] = {'kind': k, 'answer': text, 'note': note or dict(_bank(g, k)).get(text, '')}
            g['tiles'] = _tiles_for(k, text)
            _put(state, g, k, text, g['cur']['note'])
        out = _save(state, g)
    return jsonify({'status': 'success', 'quiz': out, 'jamo_only': jamo_only})


@app.route('/api/quiz/hint', methods=['POST'])
def api_quiz_hint():
    with file_lock:
        state = load_data()
        g = _quiz_state(state)
        cur = g['cur']
        if not cur or g['revealed']:
            return jsonify({'status': 'error', 'message': '열 글자가 없습니다 — [다음 문제]부터 눌러 주세요'}), 400
        if not cur.get('answer'):
            return jsonify({'status': 'error', 'message': '초성만 적어 띄운 문제라 정답을 몰라요 — 열 수 없습니다'}), 400
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
        if not cur.get('answer'):
            return jsonify({'status': 'error', 'message': '초성만 적어 띄운 문제라 정답을 몰라요 — 열 수 없습니다'}), 400
        chars = [c for c in str(cur.get('answer') or '') if not c.isspace()]
        g['tiles'] = [{'c': chars[i], 's': 'g' if t.get('s') == 'g' else 'o'} if i < len(chars) else t
                      for i, t in enumerate(g['tiles'])]
        g['revealed'] = True
        out = _save(state, g)
    return jsonify({'status': 'success', 'quiz': out})


@app.route('/api/quiz/show', methods=['POST'])
def api_quiz_show():
    """방송에 띄우기 / 내리기. 띄울 문제가 없으면 띄우기 전에 [다음 문제]가 필요하다."""
    body = _body()
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
    """내 문제 더하기 — 한 줄에 하나 "정답 | 분류(초성) · 뜻(사자성어)". mode='clear' 면 그 종류 내 문제를 비운다.
       더한 문제는 순서 맨 끝에 붙는다(바로 내고 싶으면 [맨 위로])."""
    body = _body()
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
            out = _save(state, g)          # 순서에서도 빠진다(_order 가 문제집에 없는 것을 걸러 낸다)
            return jsonify({'status': 'success', 'quiz': out, 'cleared': n})
        _order(g, kind)
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
            g['order'][kind].append(a)      # 순서 맨 끝
            have.add(a)
            added += 1
        out = _save(state, g)
    return jsonify({'status': 'success', 'quiz': out, 'added': added, 'bad': bad[:10]})
