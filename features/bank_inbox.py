# -*- coding: utf-8 -*-
"""🏦 계좌 입금 추천 — 은행 확장(나중엔 폰 앱)이 잡은 입금을 후원 콘솔 '추천' 칸에 띄운다 (2026-10-13).

송출하지 않는다. 대표님이 [채우기] → 고치기 → [송출] 해야 지금과 같은 길(/api/donation)로 간다.
  대표님 10-13: "바로바로 다 송출해버리면 누가 누구인지 · 누구 플러스인지 모른다".
  배정도 지금처럼 대기함에서 한다 — 여기서는 '밍밍 ＋?' 예상만 붙인다(features/ai.suggest_target).

  POST /api/bank/deposit            은행 확장이 보낸다(로그인 없음 · X-Bank-Key). deposits 가 비면 '살아 있음' 신호
  GET  /api/bank/inbox              후원 콘솔(로그인) — 아직 안 쓴 입금 · 숨긴 입금 · 확장 연결 상태
  POST /api/bank/inbox/<id>/<act>   used(송출함) · dismiss(숨김) · restore(되살림)
  GET  /api/bank/key                확장에 붙여 넣을 열쇠(로그인 · 없으면 만든다) · POST /api/bank/key/reset

⚠️ 입금자 실명이 들어 있다. 상태(load_data)에 넣지 않고 서버 폴더의 bank_inbox.json(.gitignore)에만 둔다
   → 방송판 SSE 로 새어 나갈 길이 없다. 읽는 길은 로그인한 후원 콘솔뿐이다.
⚠️ 열쇠가 새어도 할 수 있는 일은 '추천 카드 만들기' 뿐이다 — 송출 · 장부 · 점수는 대표님이 눌러야 간다.
"""
import collections
import json
import os
import re
import secrets
import threading
import time
from flask import jsonify, request, send_file
from server import BASE_DIR, app, db_query, file_lock, get_db_connection, load_data
from features.bank_memo import ai_split_ok, clean, split_memo

BANK_INBOX_FILE = os.path.join(BASE_DIR, 'bank_inbox.json')
BANK_KEY_FILE = os.path.join(BASE_DIR, 'bank_key.json')
KEEP_SEC = 36 * 3600          # 방송 하루치보다 넉넉히 — 그보다 오래된 입금은 지운다
KEEP_MAX = 300
HIDDEN_SHOW = 10              # 숨긴 입금은 최근 이만큼만 돌려준다(되살리기용)
AMOUNT_MAX = 100_000_000
POSTS_PER_MIN = 60            # 확장은 30초마다 한 번 — 이보다 많으면 고장이거나 장난이다
DONOR_TTL = 600

_lock = threading.Lock()
_box = None
_posts = collections.deque()
_donors = {'t': 0.0, 'set': set()}
# 메모 칸 · 실명 칸 알아보기 — 은행 화면의 머리글
_HOLDER_RE = re.compile(r'예금주|성명|실명')
_MEMO_RE = re.compile(r'통장표시|표시내용|내용|적요|기재|메모|비고|보낸|입금자|입금인|의뢰인|받는')


# ── 파일 ─────────────────────────────────────────────


def _read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _write_json(path, obj):
    data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    try:
        os.chmod(tmp, 0o600)          # 실명 · 열쇠가 든 파일 — 서버 사용자만 읽게
    except Exception:
        pass
    os.replace(tmp, path)


def _load():
    global _box
    if _box is None:
        b = _read_json(BANK_INBOX_FILE)
        items = b.get('items') if isinstance(b.get('items'), list) else []
        seen = b.get('seen') if isinstance(b.get('seen'), dict) else {}
        _box = {'items': [i for i in items if isinstance(i, dict) and i.get('id')], 'seen': seen}
    return _box


def _save(box):
    now = time.time()
    items = [i for i in box['items'] if now - float(i.get('at') or 0) < KEEP_SEC]
    box['items'] = items[-KEEP_MAX:]
    _write_json(BANK_INBOX_FILE, box)


def _key(create=False):
    k = str(_read_json(BANK_KEY_FILE).get('key') or '')
    if not k and create:
        k = secrets.token_hex(16)
        _write_json(BANK_KEY_FILE, {'key': k, 'created': int(time.time())})
    return k


# ── 판단 재료 ──────────────────────────────────────────


def _players():
    with file_lock:
        st = load_data()
        src = 'extra_bjs' if st.get('extra_game_active') else 'bjs'
        return [b.get('name') for b in st.get(src, []) if isinstance(b, dict) and b.get('name')], st


def _known_donors():
    """예전에 후원한 닉네임 — 메모에서 닉네임을 찾는 기준. 10분 기억한다."""
    now = time.time()
    if now - _donors['t'] < DONOR_TTL:
        return _donors['set']
    names = set(_donors['set'])
    for q in ("SELECT DISTINCT donor FROM donor_memory", "SELECT DISTINCT name FROM donation_history"):
        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute(db_query(q))
                names.update(str(r[0]) for r in cur.fetchall() if r and r[0])
        except Exception:
            pass
    _donors.update(t=now, set=names)
    return names


def _fields(raw):
    """[[머리글, 값], …] 또는 {머리글: 값} → [(머리글, 값)] 최대 8칸."""
    pairs = raw.items() if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    out = []
    for p in pairs:
        if isinstance(p, (list, tuple)) and len(p) == 2:
            lab, val = ' '.join(str(p[0] or '').split())[:20], ' '.join(str(p[1] or '').split())[:60]
            if val:
                out.append((lab, val))
        if len(out) >= 8:
            break
    return out


def pick_memo(fields):
    """은행 표 칸들 → (메모, 실명). 실명 칸(예금주)이 따로 있으면 메모와 나눠 둔다."""
    holder = next((v for l, v in fields if _HOLDER_RE.search(l)), '')
    rest = [(l, v) for l, v in fields if not _HOLDER_RE.search(l)]
    memo = next((v for l, v in rest if _MEMO_RE.search(l)), '') or (rest[0][1] if rest else '')
    return clean(memo), clean(holder)


def _make_item(d, source, players, donors):
    if not isinstance(d, dict):
        return None
    try:
        amount = int(d.get('amount'))
    except (TypeError, ValueError):
        return None
    if not 0 < amount <= AMOUNT_MAX:
        return None
    ref = ' '.join(str(d.get('ref') or '').split())[:80]
    if not ref:
        return None
    fields = _fields(d.get('fields'))
    memo, holder = pick_memo(fields)
    # 메모 없이 보내면 메모 칸에 실명이 찍힌다 → 나누지 않고 금액 · 입금자명만(대표님 10-13)
    no_memo = (not memo and bool(holder)) or (bool(holder) and memo.replace(' ', '') == holder.replace(' ', ''))
    if no_memo:
        sp = {'name': holder, 'message': '', 'how': 'no_memo', 'sure': False}
    else:
        sp = split_memo(memo, players, donors)
    return {
        'id': 'b' + secrets.token_hex(6), 'ref': source + ':' + ref, 'source': source,
        'amount': amount, 'when': ' '.join(str(d.get('when') or '').split())[:32], 'at': time.time(),
        'memo': memo, 'holder': holder, 'fields': [list(f) for f in fields],
        'name': sp['name'], 'message': sp['message'], 'how': sp['how'], 'sure': sp['sure'],
        'target': None, 'target_conf': 0.0, 'target_why': '', 'ai': 'pending' if sp['message'] or not sp['sure'] else 'done',
        'status': 'new',
    }


# ── AI (배정 예상 · 애매한 메모 나누기) — 요청 밖에서 ─────────────


def _ai_split(memo, players):
    """띄어쓰기 · 순서가 애매한 메모를 AI 에게 나눠 달라고 한다. 지어낸 글자가 있으면 버린다."""
    import features.ai as fa
    if not fa.NVIDIA_API_KEY or not fa.requests or not fa._nim_allowed():
        return None
    sys_prompt = (
        "너는 계좌 후원 메모를 나누는 도우미다. 메모에는 '후원자 닉네임'과 '할 말'이 섞여 있다.\n"
        "닉네임은 메모의 맨 앞이나 맨 뒤에 있는 한 토막이다. 닉네임이 없으면 빈칸으로 둔다.\n"
        "오늘 선수 이름: " + ', '.join(players) + " — 선수 이름은 닉네임이 아니라 할 말에 들어간다.\n"
        "글자를 바꾸거나 더하지 말고 JSON 한 줄만 답한다: {\"name\": \"닉네임\", \"message\": \"할 말\"}")
    body = {"messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": memo}],
            "temperature": 0.0, "max_tokens": 120}
    body.update(fa.NIM_NO_THINK)
    try:
        r, code, _m = fa.nim_post([fa.NIM_MODEL, fa.NIM_MODEL_BACKUP], body, 8)
        if r is None or code != 200:
            return None
        txt = (r.json()["choices"][0]["message"].get("content") or "").strip()
        i, j = txt.find('{'), txt.rfind('}')
        got = json.loads(txt[i:j + 1]) if i != -1 and j != -1 else {}
    except Exception:
        return None
    nm = ' '.join(str(got.get('name') or '').split())
    msg = ' '.join(str(got.get('message') or '').split())
    if nm in players or not ai_split_ok(memo, nm, msg):
        return None
    return nm, msg


def _enrich(ids):
    players, st = _players()
    for iid in ids:
        with _lock:
            it = next((i for i in _load()['items'] if i['id'] == iid), None)
            if not it:
                continue
            memo, name, message, how, sure, amount = (it['memo'], it['name'], it['message'],
                                                      it['how'], it['sure'], it['amount'])
        upd = {'ai': 'done'}
        if how in ('first', 'message') and not sure and memo:
            got = _ai_split(memo, players)
            if got and got != (name, message):
                name, message = got
                upd.update(name=name, message=message, how='ai')
        if message:
            try:
                import features.ai as fa
                res = fa.suggest_target(name or '익명', amount, message, players, st)
                if res.get('target'):
                    upd.update(target=res['target'], target_conf=float(res.get('confidence') or 0),
                               target_why=str(res.get('why') or res.get('source') or '')[:60])
            except Exception as e:
                print("⚠️ [계좌 추천] 배정 예상 실패: %s" % str(e)[:80], flush=True)
        with _lock:
            box = _load()
            it = next((i for i in box['items'] if i['id'] == iid), None)
            if it:
                it.update(upd)
                _save(box)


# ── 길 ─────────────────────────────────────────────


def _view(it):
    keep = ('id', 'source', 'amount', 'when', 'at', 'memo', 'holder', 'name', 'message', 'how', 'sure',
            'target', 'target_conf', 'target_why', 'ai', 'status')
    return {k: it.get(k) for k in keep}


@app.route('/api/bank/deposit', methods=['POST'])
def api_bank_deposit():
    key = _key()
    sent = (request.headers.get('X-Bank-Key') or '').strip()
    if not key or not sent or not secrets.compare_digest(sent, key):
        return jsonify({'status': 'error', 'bad_key': True,
                        'message': '열쇠가 맞지 않아요 — 후원 콘솔의 [은행 확장 연결]에서 열쇠를 다시 복사해 붙여 주세요'}), 401
    now = time.time()
    while _posts and now - _posts[0] > 60:
        _posts.popleft()
    if len(_posts) >= POSTS_PER_MIN:
        return jsonify({'status': 'error', 'message': '너무 자주 보냈어요 — 잠시 뒤 다시'}), 429
    _posts.append(now)
    body = request.get_json(silent=True) or {}
    source = 'phone' if body.get('source') == 'phone' else 'web'
    deps = body.get('deposits') or []
    if not isinstance(deps, list) or len(deps) > 30:
        return jsonify({'status': 'error', 'message': '입금 목록 모양이 이상해요'}), 400
    players, donors = ([], set())
    if deps:
        players, _st = _players()
        donors = _known_donors()
    added = []
    with _lock:
        box = _load()
        box['seen'][source] = {'at': now, 'note': ' '.join(str(body.get('note') or '').split())[:60]}
        refs = {i.get('ref') for i in box['items']}
        for d in deps:
            it = _make_item(d, source, players, donors)
            if it and it['ref'] not in refs:
                box['items'].append(it)
                refs.add(it['ref'])
                added.append(it['id'])
        _save(box)
    if added:
        print("🏦 [계좌 입금 감지] %d건 — 후원 콘솔 추천 칸에 올렸습니다(%s)" % (len(added), source), flush=True)
        threading.Thread(target=_enrich, args=(added,), daemon=True).start()
    return jsonify({'status': 'success', 'added': len(added)})


@app.route('/api/bank/inbox', methods=['GET'])
def api_bank_inbox():
    now = time.time()
    with _lock:
        box = _load()
        items = [_view(i) for i in box['items'] if i.get('status') == 'new']
        hidden = [_view(i) for i in box['items'] if i.get('status') == 'dismissed'][-HIDDEN_SHOW:]
        seen = dict(box['seen'])
    link = {}
    for src, v in seen.items():
        if isinstance(v, dict):
            link[src] = {'age_sec': int(now - float(v.get('at') or 0)), 'note': v.get('note') or ''}
    items.sort(key=lambda i: i['at'], reverse=True)
    hidden.reverse()
    return jsonify({'status': 'success', 'items': items, 'hidden': hidden, 'link': link, 'key_set': bool(_key())})


@app.route('/api/bank/inbox/<iid>/<act>', methods=['POST'])
def api_bank_inbox_act(iid, act):
    if act not in ('used', 'dismiss', 'restore'):
        return jsonify({'status': 'error', 'message': '모르는 동작이에요'}), 400
    with _lock:
        box = _load()
        it = next((i for i in box['items'] if i['id'] == iid), None)
        if not it:
            return jsonify({'status': 'error', 'message': '그 입금을 못 찾았어요(오래돼서 지워졌을 수 있어요)'}), 404
        it['status'] = {'used': 'used', 'dismiss': 'dismissed', 'restore': 'new'}[act]
        it['done_at'] = time.time()
        _save(box)
    if act == 'used':
        nm = ' '.join(str((request.get_json(silent=True) or {}).get('name') or '').split())
        if len(nm) >= 2 and nm not in ('익명', '수동송출'):
            _donors['set'].add(nm)      # 같은 방송에서 다시 보내면 바로 알아본다(대기함 배정 전이라도)
    return jsonify({'status': 'success'})


APP_APK = os.path.join(BASE_DIR, 'bank-phone', 'dist', 'angel-bankphone.apk')
APP_VER = os.path.join(BASE_DIR, 'bank-phone', 'dist', 'version.txt')


def _app_version():
    try:
        return open(APP_VER, encoding='utf-8').read().strip()[:20]
    except Exception:
        return ''


@app.route('/download/bankphone.apk', methods=['GET'])
def download_bankphone():
    """📱 폰 입금알림 앱 — 로그인 없이 받는다(공기계 브라우저로 QR 찍어 바로). 앱 안에 비밀값은 없다(열쇠는 앱에서 넣는다)."""
    if not os.path.exists(APP_APK):
        return jsonify({'status': 'error', 'message': '아직 올라온 앱 파일이 없어요'}), 404
    ver = _app_version() or 'latest'
    return send_file(APP_APK, mimetype='application/vnd.android.package-archive', as_attachment=True,
                     download_name='angel-bankphone-%s.apk' % ver, max_age=0)


@app.route('/api/bank/app', methods=['GET'])
def api_bank_app():
    """조종실 · 후원 콘솔이 앱 판 번호 · 크기를 보여준다(로그인)."""
    ok = os.path.exists(APP_APK)
    return jsonify({'status': 'success', 'ready': ok, 'version': _app_version() if ok else '',
                    'size': os.path.getsize(APP_APK) if ok else 0, 'url': '/download/bankphone.apk'})


@app.route('/api/bank/key', methods=['GET'])
def api_bank_key():
    return jsonify({'status': 'success', 'key': _key(create=True)})


@app.route('/api/bank/key/reset', methods=['POST'])
def api_bank_key_reset():
    _write_json(BANK_KEY_FILE, {'key': secrets.token_hex(16), 'created': int(time.time())})
    return jsonify({'status': 'success', 'key': _key()})
