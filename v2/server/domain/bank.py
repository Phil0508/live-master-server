# -*- coding: utf-8 -*-
"""🏦 계좌 입금 추천 — 은행 확장 · 폰 앱이 잡은 입금을 후원 콘솔 '추천' 카드로 (옛 features/bank_inbox.py 를 옮겼다, 10-17).

⚠️ 송출하지 않는다. 대표님이 [채우기] → 고치기 → [송출] 해야 지금과 같은 길(/api/donation)로 간다.
   대표님 10-13: "바로바로 다 송출해버리면 누가 누구인지 · 누구 플러스인지 모른다".
   배정도 지금처럼 대기함에서 한다 — 여기서는 '밍밍 ＋?' 예상만 붙인다(ai.suggest — 규칙 먼저, 애매하면 AI).

주소(옛 것과 **같은 주소 · 같은 모양 · 같은 답** — 은행 확장 · 폰 앱을 안 고친다. 갈아타는 날 Caddy 가 /api/bank/* 를 v2 로 넘긴다)
  POST /api/bank/deposit            은행 확장 · 폰 앱(로그인 없음 · X-Bank-Key). deposits 가 비면 '살아 있음' 신호.
                                    답 {status, added, cmds} — cmds 는 조종실이 넣어 둔 명령(한 번만 넘긴다)
  GET  /api/bank/inbox              (로그인) 아직 안 쓴 입금 · 숨긴 입금(최근 10) · 확장 연결 상태 · key_set
  POST /api/bank/inbox/{id}/{act}   (로그인) used(송출함 · {name}) · dismiss(숨김) · restore(되살림)
  GET  /api/bank/key                (로그인) 확장 · 폰 앱에 붙여 넣을 열쇠(없으면 만든다) · POST /api/bank/key/reset 새 열쇠
  GET  /api/bank/ext                (로그인) 🪞 조종실 거울 — 확장이 마지막 신호에 실어 보낸 상자 · 기다리는 명령 · 미처리 수 · 가장 새 카드
  POST /api/bank/ext/cmd            (로그인) 조종실 → 확장 명령 {t: enable(on) · interval(sec 20/30/60) · rebase · press, source?}
  GET  /download/bankphone.apk      (로그인 없음) 📱 폰 입금알림 앱 — 공기계로 QR 찍어 바로 받는다(앱 안에 비밀값 없음)
  GET  /api/bank/app                (로그인) 앱 판 번호 · 크기

어디에 두나
  표 bank_inbox (이 모듈이 만든다 — 같은 SQLite 장부 파일 안) — 입금 카드(실명 holder · 메모 원문 포함). 36시간 · 300건까지.
  표 bank_meta  — 확장 · 폰의 마지막 신호(seen: 시각 · 메모 · 상자 내용)와 기다리는 명령(cmds).
  조각 bank (비공개 · 이름 · 금액 없음) — {ver, new, hidden, newest} : 바뀔 때마다 ver 가 오른다.
      조종실은 ver 가 바뀌면 /api/bank/inbox 를 다시 읽고, new 로 탭 배지 · 머리줄 칩 숫자를, newest(카드 번호)가
      바뀌면 초록 띠를 띄운다. ⚠️ 비공개 조각이라 방송판(로그인 없음)에는 가지 않는다(옛 _notify_authed 와 같은 뜻).
  열쇠 — 옛 서버와 **같은 파일** 저장소 루트 bank_key.json(git 제외 · 권한 600)을 같이 쓴다 → 확장 · 폰을 다시 설정하지 않는다.
      LM2_BANK_KEY 환경변수가 있으면 그것이 먼저다(그때는 여기서 새 열쇠를 못 만든다). LM2_BANK_KEY_FILE 로 파일 자리를 바꾼다.
      🧪 시험판(LM2_TRIAL=1)에서는 열쇠를 새로 만들지 않는다 — 옛 프로그램이 같이 쓰는 열쇠라서.
⚠️ 입금자 실명(holder)이 들어 있다. 명령 기록(events) · 조각에는 넣지 않는다 — 입금 받기 · 송출함 · 숨김은 명령 줄(bus)을
   거치지 않고 표에 바로 적는다(uistats 와 같은 길). 명령 줄에는 '바뀌었다'(bank.sync, 내용 없음)만 지나간다.
   그래서 25초마다 오는 '살아 있음' 신호가 모든 화면에 빈 쪽지를 만들지도 않는다.
⚠️ 열쇠는 기록 · 답에 남기지 않는다(열쇠를 달라는 /api/bank/key 만 통째로 — 다른 답 · 서버 기록은 끝 네 글자까지).
⚠️ 열쇠가 새어도 할 수 있는 일은 '추천 카드 만들기' 뿐이다 — 송출 · 장부 · 점수는 대표님이 눌러야 간다.
"""
import asyncio
import collections
import hmac
import json
import os
import re
import secrets
import time

from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from ..bus import command
from ..state import slice_
from . import ai
from . import ai_facts as af
from . import donor_memory as dm
from .bank_memo import ai_split_ok, clean, split_memo
from .legacy import route, trial_on

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
KEY_FILE = os.environ.get('LM2_BANK_KEY_FILE') or os.path.join(REPO, 'bank_key.json')
APP_APK = os.path.join(REPO, 'bank-phone', 'dist', 'angel-bankphone.apk')
APP_VER = os.path.join(REPO, 'bank-phone', 'dist', 'version.txt')

KEEP_SEC = 36 * 3600          # 방송 하루치보다 넉넉히 — 그보다 오래된 입금은 지운다(옛 것과 같다)
KEEP_MAX = 300
HIDDEN_SHOW = 10              # 숨긴 입금은 최근 이만큼만 돌려준다(되살리기용)
AMOUNT_MAX = 100_000_000
POSTS_PER_MIN = 60            # 확장은 25~30초마다 한 번 — 이보다 많으면 고장이거나 장난이다
DEPOSITS_MAX = 30             # 한 번에 받는 입금 수
DONOR_TTL = 600               # 예전 닉네임 목록은 10분 기억
AI_SPLIT_DEADLINE = 20.0      # 메모 나누기 AI 전체 시한(한 번 부를 때 8초)
# 🪞 조종실 거울 · 원격 조작(10-16): 확장이 신호마다 상자 내용(state)을 실어 보내고, 답으로 조종실이 넣어 둔 명령을 받아 간다.
EXT_CMDS = ('enable', 'interval', 'rebase', 'press')
EXT_INTERVALS = (20, 30, 60)
EXT_CMD_MAX = 8
SOURCES = ('web', 'phone')

# 메모 칸 · 실명 칸 알아보기 — 은행 화면의 머리글(옛 것과 같다)
_HOLDER_RE = re.compile(r'예금주|성명|실명')
_MEMO_RE = re.compile(r'통장표시|표시내용|내용|적요|기재|메모|비고|보낸|입금자|입금인|의뢰인|받는')

VIEW_KEYS = ('id', 'source', 'amount', 'when', 'at', 'memo', 'holder', 'name', 'message', 'how', 'sure',
             'target', 'target_conf', 'target_why', 'ai', 'status')

# 비공개 조각 — 이름 · 금액 없이 '몇 건 · 무엇이 바뀌었나' 만. 조종실(로그인)만 받는다.
slice_('bank', False, lambda: {'ver': 0, 'new': 0, 'hidden': 0, 'newest': ''})

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS bank_inbox ("
    " id TEXT PRIMARY KEY, ref TEXT NOT NULL UNIQUE, source TEXT NOT NULL, amount INTEGER NOT NULL,"
    " when_txt TEXT NOT NULL DEFAULT '', at REAL NOT NULL, memo TEXT NOT NULL DEFAULT '', holder TEXT NOT NULL DEFAULT '',"
    " fields TEXT NOT NULL DEFAULT '[]', name TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT '',"
    " how TEXT NOT NULL DEFAULT '', sure INTEGER NOT NULL DEFAULT 0, target TEXT, target_conf REAL NOT NULL DEFAULT 0,"
    " target_why TEXT NOT NULL DEFAULT '', ai TEXT NOT NULL DEFAULT 'done', status TEXT NOT NULL DEFAULT 'new',"
    " done_at REAL, seq INTEGER NOT NULL DEFAULT 0)",
    "CREATE INDEX IF NOT EXISTS bank_inbox_status ON bank_inbox(status, at)",
    "CREATE TABLE IF NOT EXISTS bank_meta (k TEXT PRIMARY KEY, v TEXT NOT NULL, at REAL NOT NULL)",
)


# ── 표 ──────────────────────────────────────────────
def _db(store):
    """표가 없으면 만든다. ⚠️ executescript 는 열린 장부(BEGIN)를 몰래 COMMIT 하므로 쓰지 않는다 — 한 줄씩."""
    if not getattr(store, '_lm_bank_ready', False):
        for q in _SCHEMA:
            store.db.execute(q)
        if not store.db.in_transaction:
            store._lm_bank_ready = True
    return store.db


def _tx(store, fn):
    """여러 줄을 한 번에 — ⚠️ 이 안에서는 기다리지(await) 않는다. 명령(BEGIN … COMMIT)과 같은 갈래라 사이에 끼어들 수 없다."""
    db = _db(store)
    db.execute('BEGIN')
    try:
        out = fn(db)
        db.execute('COMMIT')
        return out
    except Exception:
        try:
            db.execute('ROLLBACK')
        except Exception:
            pass
        raise


def _row_view(r):
    d = dict(r)
    return {'id': d['id'], 'source': d['source'], 'amount': int(d['amount']), 'when': d['when_txt'], 'at': float(d['at']),
            'memo': d['memo'], 'holder': d['holder'], 'name': d['name'], 'message': d['message'], 'how': d['how'],
            'sure': bool(d['sure']), 'target': d['target'], 'target_conf': float(d['target_conf'] or 0),
            'target_why': d['target_why'], 'ai': d['ai'], 'status': d['status']}


def _item(store, iid):
    r = _db(store).execute('SELECT * FROM bank_inbox WHERE id = ?', (str(iid),)).fetchone()
    return _row_view(r) if r else None


def _items(store, status, limit=None, newest_first=True):
    q = 'SELECT * FROM bank_inbox WHERE status = ? ORDER BY at %s, seq %s' % (('DESC',) * 2 if newest_first else ('ASC',) * 2)
    args = [status]
    if limit:
        q += ' LIMIT ?'
        args.append(int(limit))
    return [_row_view(r) for r in _db(store).execute(q, args)]


def _prune(db, now):
    db.execute('DELETE FROM bank_inbox WHERE at < ?', (now - KEEP_SEC,))
    db.execute('DELETE FROM bank_inbox WHERE id NOT IN (SELECT id FROM bank_inbox ORDER BY at DESC, seq DESC LIMIT ?)', (KEEP_MAX,))


def _meta(store, k, default):
    r = _db(store).execute('SELECT v FROM bank_meta WHERE k = ?', (k,)).fetchone()
    if not r:
        return default
    try:
        v = json.loads(r['v'])
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


def _meta_put(db, k, v):
    db.execute('INSERT INTO bank_meta(k, v, at) VALUES(?, ?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v, at = excluded.at',
               (k, json.dumps(v, ensure_ascii=False), time.time()))


# ── 메모리(서버마다 따로 — 검사마다 서버가 따로라 섞이지 않게 bus 에 붙인다) ──
def _rt(bus):
    rt = getattr(bus, 'bank_rt', None)
    if rt is None:
        rt = {'posts': collections.deque(), 'donors': {'t': 0.0, 'set': set()}}
        bus.bank_rt = rt
    return rt


# ── 열쇠 ─────────────────────────────────────────────
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
        os.chmod(tmp, 0o600)          # 열쇠가 든 파일 — 서버 사용자만 읽게
    except Exception:
        pass
    os.replace(tmp, path)


def _env_key():
    return (os.environ.get('LM2_BANK_KEY') or '').strip()


def key_now():
    """지금 열쇠 — 환경변수 LM2_BANK_KEY 가 먼저, 없으면 옛 서버와 같이 쓰는 bank_key.json. 없으면 ''."""
    return _env_key() or str(_read_json(KEY_FILE).get('key') or '').strip()


def key_tail(k):
    return ('••••' + k[-4:]) if k else ''


def _new_key():
    k = secrets.token_hex(16)
    _write_json(KEY_FILE, {'key': k, 'created': int(time.time())})
    print('🔑 [계좌 입금] 은행 확장 열쇠를 새로 만들었습니다 (끝 %s)' % k[-4:], flush=True)
    return k


# ── 🪞 확장 상자 거울 ─────────────────────────────────
def ext_state(raw):
    """확장이 신호에 실어 보낸 상자 내용 → 조종실 거울이 그릴 만큼만, 글자 수를 잘라 둔다(옛 _ext_state 그대로).
       (메모엔 실명이 섞일 수 있어 40자 · 기록 6줄 · 찾은 입금 8건까지. 모르는 칸은 버린다)"""
    if not isinstance(raw, dict):
        return {}

    def s(v, n):
        return ' '.join(str(v or '').split())[:n]

    def i(v):
        return int(v) if isinstance(v, (int, float)) and -1e13 < v < 1e13 else 0

    out = {
        'v': s(raw.get('v'), 10), 'enabled': bool(raw.get('enabled')), 'interval': i(raw.get('interval')),
        'clicks': i(raw.get('clicks')), 'lastOkAt': i(raw.get('lastOkAt')), 'startedAt': i(raw.get('startedAt')),
        'dateOk': raw.get('dateOk') if raw.get('dateOk') in (True, False) else None,
        'status': s(raw.get('status'), 120), 'cls': s(raw.get('cls'), 8), 'dead': bool(raw.get('dead')),
        'loggedOut': bool(raw.get('loggedOut')), 'rows': i(raw.get('rows')), 'diag': s(raw.get('diag'), 160),
    }
    found = []
    for f in (raw.get('found') if isinstance(raw.get('found'), list) else [])[:8]:
        if isinstance(f, dict):
            found.append({'at': i(f.get('at')), 'when': s(f.get('when'), 24), 'dep': i(f.get('dep')), 'memo': s(f.get('memo'), 40)})
    out['found'] = found
    out['log'] = [s(x, 80) for x in (raw.get('log') if isinstance(raw.get('log'), list) else [])[:6] if isinstance(x, str)]
    return out


# ── 판단 재료 ──────────────────────────────────────────
def players_now(bus):
    """지금 판 선수 이름(번외 판이 켜져 있으면 번외 판) — 옛 _players 와 같다."""
    return af.current_names(bus.state.slices)


def known_donors(bus):
    """예전에 후원한 닉네임 — 메모에서 닉네임을 찾는 기준. 10분 기억한다(옛 것: donor_memory · donation_history)."""
    rt = _rt(bus)['donors']
    now = time.time()
    if now - rt['t'] < DONOR_TTL:
        return rt['set']
    names = set(rt['set'])
    store = bus.store
    try:
        dm.ensure(store)
        names.update(str(r[0]) for r in store.db.execute('SELECT DISTINCT donor FROM donor_memory') if r and r[0])
    except Exception:
        pass
    try:
        names.update(str(r[0]) for r in store.db.execute('SELECT DISTINCT name FROM donations') if r and r[0])
    except Exception:
        pass
    rt.update(t=now, set=names)
    return names


def fields_of(raw):
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


def make_item(d, source, players, donors, now=None):
    """확장 · 폰이 보낸 입금 한 줄 → 카드(옛 _make_item 그대로). 이상하면 None."""
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
    fields = fields_of(d.get('fields'))
    memo, holder = pick_memo(fields)
    # 메모 없이 보내면 메모 칸에 실명이 찍힌다 → 나누지 않고 금액 · 입금자명만(대표님 10-13)
    no_memo = (not memo and bool(holder)) or (bool(holder) and memo.replace(' ', '') == holder.replace(' ', ''))
    if no_memo:
        sp = {'name': holder, 'message': '', 'how': 'no_memo', 'sure': False}
    else:
        sp = split_memo(memo, players, donors)
    return {
        'id': 'b' + secrets.token_hex(6), 'ref': source + ':' + ref, 'source': source,
        'amount': amount, 'when': ' '.join(str(d.get('when') or '').split())[:32], 'at': time.time() if now is None else now,
        'memo': memo, 'holder': holder, 'fields': [list(f) for f in fields],
        'name': sp['name'], 'message': sp['message'], 'how': sp['how'], 'sure': sp['sure'],
        'target': None, 'target_conf': 0.0, 'target_why': '', 'ai': 'pending' if sp['message'] or not sp['sure'] else 'done',
        'status': 'new',
    }


# ── AI (애매한 메모 나누기 · 배정 예상) — 답을 보낸 뒤(요청 밖)에서 ─────────────
def ai_split(memo, players):
    """띄어쓰기 · 순서가 애매한 메모를 AI 에게 나눠 달라고 한다. 지어낸 글자가 있으면 버린다.
       ⚠️ 막히는 호출 — 다른 갈래(asyncio.to_thread)에서만 부른다. 열쇠가 없거나(LM2_AI_OFF) 분당 한도면 None."""
    if not ai.ai_on() or not ai.nim_allowed():
        return None
    sys_prompt = (
        "너는 계좌 후원 메모를 나누는 도우미다. 메모에는 '후원자 닉네임'과 '할 말'이 섞여 있다.\n"
        "닉네임은 메모의 맨 앞이나 맨 뒤에 있는 한 토막이다. 닉네임이 없으면 빈칸으로 둔다.\n"
        "오늘 선수 이름: " + ', '.join(players) + " — 선수 이름은 닉네임이 아니라 할 말에 들어간다.\n"
        "글자를 바꾸거나 더하지 말고 JSON 한 줄만 답한다: {\"name\": \"닉네임\", \"message\": \"할 말\"}")
    body = {"messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": memo}],
            "temperature": 0.0, "max_tokens": 120}
    body.update(ai.NIM_NO_THINK)
    try:
        r, code, _m = ai.ai_post([ai.NIM_MODEL, ai.NIM_MODEL_BACKUP], body, 8)
        if r is None or code != 200:
            return None
        txt = (r.json()["choices"][0]["message"].get("content") or "").strip()
        i, j = txt.find('{'), txt.rfind('}')
        got = json.loads(txt[i:j + 1]) if i != -1 and j != -1 else {}
    except Exception:
        return None
    if not isinstance(got, dict):
        return None
    nm = ' '.join(str(got.get('name') or '').split())
    msg = ' '.join(str(got.get('message') or '').split())
    if nm in players or not ai_split_ok(memo, nm, msg):
        return None
    return nm, msg


async def enrich(bus, ids):
    """새 카드에 AI 나누기(애매할 때만) · 배정 예상('밍밍 ＋?')을 붙인다 — 확장에 답을 보낸 **뒤** 돈다(BackgroundTask).
       ⚠️ 표 읽기 · 쓰기는 이 갈래(이벤트 루프)에서만, AI 는 다른 갈래 + 시한. 넘어져도 카드는 'done' 이 된다."""
    players = players_now(bus)
    store = bus.store
    for iid in ids:
        it = _item(store, iid)
        if not it:
            continue
        name, message, how, sure, memo, amount = it['name'], it['message'], it['how'], it['sure'], it['memo'], it['amount']
        upd = {'ai': 'done'}
        try:
            if how in ('first', 'message') and not sure and memo:
                try:
                    got = await asyncio.wait_for(asyncio.to_thread(ai_split, memo, players), AI_SPLIT_DEADLINE)
                except asyncio.TimeoutError:
                    got = None
                if got and got != (name, message):
                    name, message = got
                    upd.update(name=name, message=message, how='ai')
            if message:
                res = await ai.suggest(bus, name or '익명', amount, message, players)
                if res.get('target'):
                    upd.update(target=res['target'], target_conf=float(res.get('confidence') or 0),
                               target_why=str(res.get('why') or res.get('source') or '')[:60])
        except Exception as e:
            print("⚠️ [계좌 추천] 배정 예상 실패: %s" % type(e).__name__, flush=True)
        cols = ', '.join('%s = ?' % k for k in upd)
        _db(store).execute('UPDATE bank_inbox SET %s WHERE id = ?' % cols, list(upd.values()) + [iid])
    await bus.run('bank.sync', {}, by='bank', authed=True)


# ── 명령 — '바뀌었다' 만(내용 없음) ───────────────────────
@command('bank.sync')
def bank_sync(ctx, data):
    """표를 세어 비공개 조각 bank 를 고친다(ver +1). 입금 받기 · 송출함 · 숨김 · 예상이 끝난 뒤 서버가 부른다.
       ⚠️ data 는 늘 비어 있다 — 명령 기록(events)에 이름 · 금액 · 실명이 남지 않게."""
    db = _db(ctx.store)
    new = db.execute("SELECT COUNT(*) AS n FROM bank_inbox WHERE status = 'new'").fetchone()['n']
    hid = db.execute("SELECT COUNT(*) AS n FROM bank_inbox WHERE status = 'dismissed'").fetchone()['n']
    top = db.execute("SELECT id FROM bank_inbox WHERE status = 'new' ORDER BY at DESC, seq DESC LIMIT 1").fetchone()
    b = ctx.edit('bank')
    b.update(ver=int(b.get('ver') or 0) + 1, new=int(new), hidden=int(hid), newest=top['id'] if top else '')


# ── 길 ─────────────────────────────────────────────
def _err(msg, code, **kw):
    return JSONResponse(dict({'status': 'error', 'message': msg}, **kw), status_code=code)


def _need(req, authed):
    return None if authed(req) else _err('로그인이 필요합니다', 401)


async def _body(req):
    try:
        b = await req.json()
    except Exception:
        return {}
    return b if isinstance(b, dict) else {}


def _src(v):
    return 'phone' if v == 'phone' else 'web'


@route('/api/bank/deposit')
async def bank_deposit(req, bus, authed, answer):
    key = key_now()
    sent = (req.headers.get('x-bank-key') or '').strip()
    if not key or not sent or not hmac.compare_digest(sent.encode('utf-8'), key.encode('utf-8')):
        return _err('열쇠가 맞지 않아요 — 후원 콘솔의 [은행 확장 연결]에서 열쇠를 다시 복사해 붙여 주세요', 401, bad_key=True)
    now = time.time()
    posts = _rt(bus)['posts']
    while posts and now - posts[0] > 60:
        posts.popleft()
    if len(posts) >= POSTS_PER_MIN:
        return _err('너무 자주 보냈어요 — 잠시 뒤 다시', 429)
    posts.append(now)
    body = await _body(req)
    source = _src(body.get('source'))
    deps = body.get('deposits') or []
    if not isinstance(deps, list) or len(deps) > DEPOSITS_MAX:
        return _err('입금 목록 모양이 이상해요', 400)
    players, donors = [], set()
    if deps:
        players = players_now(bus)
        donors = known_donors(bus)
    seen_one = {'at': now, 'note': ' '.join(str(body.get('note') or '').split())[:60], 'state': ext_state(body.get('state'))}
    items = [it for it in (make_item(d, source, players, donors, now) for d in deps) if it]

    # ⚠️ 여기서부터 COMMIT 까지 기다리지(await) 않는다
    def write(db):
        seen = _meta(bus.store, 'seen', {})
        seen[source] = seen_one
        _meta_put(db, 'seen', seen)
        cmds_all = _meta(bus.store, 'cmds', {})
        cmds = cmds_all.pop(source, [])            # 조종실이 넣어 둔 명령 — 한 번만 넘긴다
        if cmds:
            _meta_put(db, 'cmds', cmds_all)
        added = []
        for k, it in enumerate(items):
            cur = db.execute('INSERT OR IGNORE INTO bank_inbox(id, ref, source, amount, when_txt, at, memo, holder, fields, name, message,'
                             ' how, sure, target, target_conf, target_why, ai, status, seq) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             (it['id'], it['ref'], it['source'], it['amount'], it['when'], it['at'], it['memo'], it['holder'],
                              json.dumps(it['fields'], ensure_ascii=False), it['name'], it['message'], it['how'], int(it['sure']),
                              None, 0.0, '', it['ai'], 'new', k))
            if cur.rowcount:
                added.append(it['id'])
        _prune(db, now)
        return added, [c for c in cmds if isinstance(c, dict)]

    try:
        added, cmds = _tx(bus.store, write)
    except Exception as e:
        print('⚠️ [계좌 입금] 표에 못 적었습니다: %s' % type(e).__name__, flush=True)
        return _err('서버가 입금을 적지 못했어요 — 잠시 뒤 다시 보내 주세요', 500)
    if not added:
        return {'status': 'success', 'added': 0, 'cmds': cmds}
    print("🏦 [계좌 입금 감지] %d건 — 후원 콘솔 추천 칸에 올렸습니다(%s)" % (len(added), source), flush=True)
    await bus.run('bank.sync', {}, by='bank', authed=True)        # 조종실 배지 · 초록 띠 — 로그인한 화면에만
    # 배정 예상 · AI 나누기는 답을 보낸 뒤에(확장 · 폰이 AI 를 기다리지 않게)
    return JSONResponse({'status': 'success', 'added': len(added), 'cmds': cmds}, background=BackgroundTask(enrich, bus, added))


def _link(store, now, with_state=False):
    out = {}
    for src, v in _meta(store, 'seen', {}).items():
        if isinstance(v, dict):
            row = {'age_sec': int(now - float(v.get('at') or 0)), 'note': v.get('note') or ''}
            if with_state:
                row['state'] = v.get('state') or {}
            out[src] = row
    return out


@route('/api/bank/inbox', methods=('GET',))
async def bank_inbox(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    now = time.time()
    k = key_now()
    return {'status': 'success', 'items': _items(bus.store, 'new'), 'hidden': _items(bus.store, 'dismissed', HIDDEN_SHOW),
            'link': _link(bus.store, now), 'key_set': bool(k), 'key_tail': key_tail(k)}


@route('/api/bank/inbox/{iid}/{act}')
async def bank_inbox_act(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    iid, act = str(req.path_params.get('iid') or ''), str(req.path_params.get('act') or '')
    if act not in ('used', 'dismiss', 'restore'):
        return _err('모르는 동작이에요', 400)
    if not _item(bus.store, iid):
        return _err('그 입금을 못 찾았어요(오래돼서 지워졌을 수 있어요)', 404)
    _db(bus.store).execute('UPDATE bank_inbox SET status = ?, done_at = ? WHERE id = ?',
                           ({'used': 'used', 'dismiss': 'dismissed', 'restore': 'new'}[act], time.time(), iid))
    if act == 'used':
        nm = ' '.join(str((await _body(req)).get('name') or '').split())
        if len(nm) >= 2 and nm not in ('익명', '수동송출'):
            _rt(bus)['donors']['set'].add(nm)      # 같은 방송에서 다시 보내면 바로 알아본다(대기함 배정 전이라도)
    await bus.run('bank.sync', {}, by='http', authed=True)
    return {'status': 'success'}


@route('/api/bank/ext', methods=('GET',))
async def bank_ext(req, bus, authed, answer):
    """🪞 조종실 거울 — 확장이 마지막 신호에 실어 보낸 상자 내용 · 기다리는 명령 · 미처리 입금 수 · 가장 새 카드(로그인)."""
    bad = _need(req, authed)
    if bad:
        return bad
    now = time.time()
    news = _items(bus.store, 'new')
    pending = {k: list(v) for k, v in _meta(bus.store, 'cmds', {}).items() if isinstance(v, list)}
    return {'status': 'success', 'link': _link(bus.store, now, with_state=True), 'pending': pending, 'new': len(news),
            'newest': news[0] if news else None, 'key_set': bool(key_now()), 'now': now}


@route('/api/bank/ext/cmd')
async def bank_ext_cmd(req, bus, authed, answer):
    """조종실 → 확장 명령 넣기(로그인). 확장이 다음 신호(25초 안)에 받아 간다.
       enable(on) · interval(sec 20/30/60) · rebase(기준 다시 잡기) · press([조회] 한 번). 같은 종류는 마지막 것만 남긴다."""
    bad = _need(req, authed)
    if bad:
        return bad
    body = await _body(req)
    t = str(body.get('t') or '')
    if t not in EXT_CMDS:
        return _err('모르는 명령이에요', 400)
    cmd = {'t': t, 'at': int(time.time())}
    if t == 'enable':
        if body.get('on') not in (True, False):
            return _err('켤지 끌지(on)를 알려 주세요', 400)
        cmd['on'] = bool(body['on'])
    if t == 'interval':
        try:
            sec = int(body.get('sec'))
        except (TypeError, ValueError):
            sec = 0
        if sec not in EXT_INTERVALS:
            return _err('간격은 20 · 30 · 60초 중 하나예요', 400)
        cmd['sec'] = sec
    source = _src(body.get('source'))

    def write(db):
        allc = _meta(bus.store, 'cmds', {})
        q = [c for c in (allc.get(source) or []) if isinstance(c, dict) and c.get('t') != t]
        q.append(cmd)
        allc[source] = q[-EXT_CMD_MAX:]
        _meta_put(db, 'cmds', allc)
        return list(allc[source])

    return {'status': 'success', 'pending': _tx(bus.store, write)}


def _app_version():
    try:
        with open(APP_VER, encoding='utf-8') as f:
            return f.read().strip()[:20]
    except Exception:
        return ''


@route('/download/bankphone.apk', methods=('GET',))
async def download_bankphone(req, bus, authed, answer):
    """📱 폰 입금알림 앱 — 로그인 없이 받는다(공기계 브라우저로 QR 찍어 바로). 앱 안에 비밀값은 없다(열쇠는 앱에서 넣는다)."""
    if not os.path.isfile(APP_APK):
        return _err('아직 올라온 앱 파일이 없어요', 404)
    ver = _app_version() or 'latest'
    return FileResponse(APP_APK, media_type='application/vnd.android.package-archive',
                        filename='angel-bankphone-%s.apk' % ver, headers={'Cache-Control': 'no-cache'})


@route('/api/bank/app', methods=('GET',))
async def bank_app(req, bus, authed, answer):
    """조종실 · 후원 콘솔이 앱 판 번호 · 크기를 보여준다(로그인)."""
    bad = _need(req, authed)
    if bad:
        return bad
    ok = os.path.isfile(APP_APK)
    return {'status': 'success', 'ready': ok, 'version': _app_version() if ok else '',
            'size': os.path.getsize(APP_APK) if ok else 0, 'url': '/download/bankphone.apk'}


_TRIAL_MSG = '🧪 시험판이라 열쇠를 새로 만들지 않아요 — 지금 방송 중인 옛 프로그램과 같은 열쇠(bank_key.json)를 같이 써요. 갈아탄 뒤에 열려요.'


@route('/api/bank/key', methods=('GET',))
async def bank_key(req, bus, authed, answer):
    """확장 · 폰 앱에 붙여 넣을 열쇠(로그인) — 없으면 만든다. ⚠️ 열쇠를 통째로 주는 곳은 여기와 새 열쇠뿐."""
    bad = _need(req, authed)
    if bad:
        return bad
    k = key_now()
    if not k:
        if trial_on():
            return _err(_TRIAL_MSG, 403, trial=True)
        try:
            k = _new_key()
        except Exception as e:
            return _err('열쇠를 만들지 못했어요: %s' % type(e).__name__, 500)
    return {'status': 'success', 'key': k, 'from': 'env' if _env_key() else 'file'}


@route('/api/bank/key/reset')
async def bank_key_reset(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    if trial_on():
        return _err(_TRIAL_MSG, 403, trial=True)
    if _env_key():
        return _err('열쇠가 서버 설정(LM2_BANK_KEY)에 박혀 있어 여기서는 못 바꿔요 — 서버 설정을 고쳐 주세요', 409)
    try:
        k = _new_key()
    except Exception as e:
        return _err('새 열쇠를 만들지 못했어요: %s' % type(e).__name__, 500)
    return {'status': 'success', 'key': k}
