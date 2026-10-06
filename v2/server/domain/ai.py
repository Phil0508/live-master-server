# -*- coding: utf-8 -*-
"""🤖 AI 서포트 — '이 후원은 누구 것인가' 제안 · AI 에게 물어보기(채팅) · 상황판(B안). 옛 features/ai.py 를 옮겼다.

원칙(옛 것 그대로)
  - ⚠️ AI 는 절대 점수를 바꾸지 않는다. 추천 · 경고 · 답만 준다. 배정은 조종실이 pending.assign 으로 한다
    (오토파일럿도 조종실 쪽에서 tier 'auto' 만 골라 pending.assign 을 부른다).
  - 계산은 서버가 끝내고(사실표 ai_facts.build_facts) AI 는 옮겨 적기만 한다(09-29 개편).
  - 모델이 자주 죽는다 → 붐비면(503 등) 주 모델을 한 번 더, 그래도 막히면 예비 모델. 그래도 안 되면
    **서버 계산으로 대신 답한다**(채팅) · '모름 + 까닭 + 조금 뒤 다시' 로 답한다(제안). 언제나 200 으로 답한다.
v2 에서 바뀐 것
  - NVIDIA 호출은 **명령 밖** · 다른 갈래(asyncio.to_thread) + 전체 시한(asyncio.wait_for)에서만 한다.
    옛 것은 file_lock 안팎을 오가며 불렀다. 여기서는 명령(bus.run)을 아예 부르지 않는다 — 읽기만 한다.
  - 장부(SQLite) 읽기(후원자 기억 · 이번 방송 후원)는 이벤트 루프 갈래에서 바로 한다(명령도 같은 갈래라 섞이지 않는다).
  - 제안은 대기함 id 로도 물을 수 있다({id}) — 서버가 대기함에서 이름 · 금액 · 메시지를 읽는다.

설정(옛 것과 같은 이름 · 같은 기본값)
  NVIDIA_API_KEY (없으면 저장소 루트 NVIDIA_CREDENTIALS.txt 의 NVIDIA_API_KEY=… — git 제외 파일)
  NIM_MODEL · NIM_MODEL_BACKUP (제안) / NIM_CHAT_MODEL · NIM_CHAT_BACKUP (채팅) — 모델이 내려가면(410) 이것만 바꾸고 재시작.
  ⚠️ 키는 어디에도 찍지 않는다(로그 · 답 · 오류 글자).

━━ 화면 약속(조종실 AI 패널을 만들 사람에게) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
모든 주소는 로그인 필요(대기함 후원자 이름이 들어 있다) — 안 되면 401 {status:'error', message}.

1) 배정 제안 배지 — POST /api/audit/suggest
   보냄: {id: 대기함 id}  (옛 모양 {name, amount, message, players?:[이름…]} 도 받는다. players 가 없으면 지금 판 선수)
   받음: {status:'success', id?, target: 이름|null, confidence: 0~1, tier: 'auto'|'suggest'|'unknown',
          source: '이름'|'별명'|'이력'|'AI'|null, why: 사람 말 근거|null, history:[{name, count}](이 후원자의 지난 배정, 많은 순),
          retry?: true(잠깐 막힘 — 다시 물을 것), cached?: true, skipped?: true(후원이 아닌 카드)}
   · 대기함에 없는 id → 404 {status:'error', gone:true} (이미 배정 · 무시됨 — 조용히 넘긴다)
   · 대기함 항목마다 한 번 묻는다. type 'off_work'(퇴근 카드) · kind 'contrib'(기여도 카드)는 묻지 않는다.
   · retry 면 20초 × n 뒤에 다시(세 번까지) — 그 사이 대기함에서 빠졌으면 안 묻는다. 그동안 배지는 '⏳ AI 가 붐벼요'.
   · 배지: tier 'auto' → '✓ 이름 (거의 확실)' · target 있고 confidence ≥ 0.6 → '🤖 이름(으)로 보임' ·
     그 밖 → '❓ 누구 것인지 모르겠음' — why 를 늘 같이 보여 준다('모름' 도 숨기지 않는다). history 앞 3개를 '지난 배정 · 하율 3번'.
   · '지급할까요?' 토스트: confidence ≥ 0.75 · 후원 1건당 한 번 · 아직 대기함에 있을 때만. 누르면 pending.assign{id, name}.
   · 🚗 오토파일럿(조종실 쪽, 새로 고침하면 꺼진 채로 시작): tier 'auto' 이고 target 이 지금 판 선수일 때만
     pending.assign{id, name: target} — 한 번에 한 건, 같은 id 는 한 번만, 한 일은 기록해 끌 때 보여 준다.
     잘못 갔으면 score.undo{ref: 후원 id}(후원이 대기함으로 돌아오고 서버의 '후원자 기억' 도 잊는다) 뒤 다시 배정.
2) 상황판(B안) — GET /api/ai/board[?today=1]   (AI 를 안 부른다 — 패널이 열려 있을 때만 4초마다)
   받음: {status:'success', tiles:[{intent:'pending'|'match'|'goal'|'race', k: 머리글, v: 큰 글자, s: 작은 글자,
          hot: 주황 테두리, pct?: 목표 막대 0~100}], ai:{state:'off'|'idle'|'ok'|'busy', text}, intents:{intent: 단추 이름},
          today?: {건수, 합계금액, 많이_쏜_사람:[{이름, 횟수, 금액합}]}}
   · 칸 네 개는 늘 이 순서 · 이 intent. 칸을 누르면 3)의 {intent} 로 묻는다. ai.text 는 패널 머리 점 옆 글자.
   · ?today=1 — 조종실 첫 화면 '이번 방송 후원' 숫자 칸(장부에서 센 것 — 화면에만 뜬 소액은 빠진다).
3) AI 에게 물어보기 — POST /api/ai/chat
   보냄: {intent}(빠른 질문 단추 — intents 의 열쇠: rank · pending · goal · match · race · today · sig · flow)
         또는 {question, messages?:[{role:'user'|'assistant', content}](직전 대화, 서버는 마지막 6개만 쓴다)}
   받음: {status:'success', source:'calc'|'ai'|'none', reply: 글자}   — 언제나 200
   · reply 는 '**굵게**' 와 '- ' 목록만 쓴다(화면은 escape 뒤 이 둘만 살린다). source 꼬리표: calc '⚡ 서버 계산' · ai '🤖 AI'.
   · AI 가 꺼졌거나 붐비면 질문 종류를 알아본 만큼 서버 계산으로 답한다(source 'calc', 끝에 '(… — 서버 계산으로 답했어요)').
   · '철수한테 3점' · '슬롯 돌려' 같은 명령 꼴은 조종실이 AI 에게 보내지 말고 바로 명령으로(옛 aiTryCommand).
   · 대화 기록은 조종실(localStorage) 몫 — 서버는 기억하지 않는다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import asyncio
import json
import os
import threading
import time

from fastapi.responses import JSONResponse

from . import ai_facts as af
from . import donor_memory as dm
from . import players as pl
from .ai_facts import NIM_RETRYABLE
from .legacy import route

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# 시험 서버용 스위치 — LM2_AI_OFF=1 이면 열쇠를 안 읽는다(AI 꺼짐 · 서버 계산만). LM2_NIM_URL 로 가짜 AI 에 붙일 수 있다.
#   ⚠️ 저장소의 NVIDIA_CREDENTIALS.txt 를 저절로 읽으므로, 그냥 띄운 시험 서버도 진짜 AI 를 부른다 — 시험 땐 꺼 둘 것.
NIM_URL = (os.environ.get('LM2_NIM_URL') or "https://integrate.api.nvidia.com/v1/chat/completions").strip()

# ⚠️ 모델 이름은 환경변수로 바꿀 수 있게 둔다(옛 것 그대로). 2026-08-26 쓰던 모델 둘이 같은 날 종료(410)돼
#    방송 중에 AI 가 통째로 멈췄다. 주 모델 · 예비 모델은 번갈아 죽는다 — 방송 전마다 실제로 불러 살아 있는 쪽을 주 모델로.
NIM_MODEL = (os.environ.get('NIM_MODEL') or "nvidia/nemotron-3-super-120b-a12b").strip()
NIM_CHAT_MODEL = (os.environ.get('NIM_CHAT_MODEL') or "nvidia/nemotron-3-super-120b-a12b").strip()
NIM_MODEL_BACKUP = (os.environ.get('NIM_MODEL_BACKUP') or "nvidia/nemotron-3.5-lightning-30b-a3b").strip()
NIM_CHAT_BACKUP = (os.environ.get('NIM_CHAT_BACKUP') or "nvidia/nemotron-3.5-lightning-30b-a3b").strip()

# nemotron 3 계열은 생각을 먼저 늘어놓는다 — 추론을 끈다(켜 두면 길이 제한에 잘려 JSON · 답이 안 나왔다).
NIM_NO_THINK = {"chat_template_kwargs": {"thinking": False}}

SUGGEST_TIMEOUT = 8          # 한 번 부를 때(옛 것 그대로)
CHAT_TIMEOUT = 20
# 전체 시한 — 주 모델 두 번 + 예비 한 번 + 0.8초 쉼이 옛 최악(8×3 · 20×3)이다. 그 너머는 기다리지 않는다.
SUGGEST_DEADLINE = 26.0
CHAT_DEADLINE = 62.0

# 분당 호출 한도. 넘으면 조용히 건너뛴다(35 는 NVIDIA 실제 허용치에 붙어 있었다 — 옛 부하 시험).
NIM_RATE_LIMIT = 30
_nim_calls = []
_nim_lock = threading.Lock()

# 🩺 마지막 AI 호출 결과 — 상황판 머리의 'AI 연결됨 · 0.7초' / 'AI 붐빔'
NIM_HEALTH = {'ok': None, 'ms': 0, 'at': 0.0, 'model': '', 'code': 0}

SUGGEST_TTL = 600            # 같은 (이름 · 금액 · 메시지 · 선수들) 답은 10분 기억 — 폰 · PC 조종실이 같은 후원을 각각 묻는다
SUGGEST_CACHE_MAX = 500
_SUGGEST_CACHE = {}

_KEY = None


# ── 열쇠 · 호출 ─────────────────────────────────────────
def _load_key():
    if (os.environ.get('LM2_AI_OFF') or '').strip().lower() in ('1', 'on', 'true', 'yes'):
        return ''
    key = (os.environ.get('NVIDIA_API_KEY') or '').strip()
    if key:
        return key
    path = os.path.join(REPO, 'NVIDIA_CREDENTIALS.txt')      # git 제외 파일
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    if k.strip() == 'NVIDIA_API_KEY':
                        return v.split('#')[0].strip()
        except Exception as e:
            print('[NVIDIA 키 읽기 오류] %s' % type(e).__name__, flush=True)     # ⚠️ 내용은 안 찍는다
    return ''


def nim_key():
    """키(처음 한 번 읽고 기억 — 바꾸면 재시작, 옛 것과 같다). ⚠️ 이 값은 어디에도 찍지 않는다."""
    global _KEY
    if _KEY is None:
        _KEY = _load_key()
    return _KEY


def _http_post(url, headers, body, timeout):
    """바깥으로 나가는 유일한 곳(검사는 이것을 막는다)."""
    import requests
    return requests.post(url, headers=headers, json=body, timeout=timeout)


def nim_allowed():
    """분당 한도 안이면 True(그리고 이번 호출을 센다)."""
    now = time.time()
    with _nim_lock:
        while _nim_calls and now - _nim_calls[0] > 60:
            _nim_calls.pop(0)
        if len(_nim_calls) >= NIM_RATE_LIMIT:
            return False
        _nim_calls.append(now)
        return True


def nim_post(models, body, timeout):
    """모델을 차례로 시도한다. 붐비면(503 등) 다음으로. ⚠️ 다른 갈래(asyncio.to_thread)에서만 부른다 — 막히는 호출이다.
       돌려받는 값: (응답 or None, 마지막 상태 코드, 실제로 답한 모델)"""
    last = 0
    tried = [m for m in models if m]
    for i, m in enumerate(tried):
        one = dict(body)
        one["model"] = m
        t0 = time.time()
        try:
            r = _http_post(NIM_URL, {"Authorization": "Bearer " + nim_key()}, one, timeout)
        except Exception:
            last = 0
            NIM_HEALTH.update(ok=False, at=time.time(), model=m, code=0)
            continue
        NIM_HEALTH.update(ok=r.status_code == 200, ms=int((time.time() - t0) * 1000), at=time.time(),
                          model=m, code=r.status_code)
        if r.status_code == 200:
            if i > 0:
                print("🔁 [AI 예비 모델] %s 이(가) 막혀 %s 로 넘어갔습니다." % (tried[0], m), flush=True)
            return r, 200, m
        last = r.status_code
        if r.status_code not in NIM_RETRYABLE:
            return r, r.status_code, m          # 다시 해도 같은 오류 — 그대로 알린다
        again = i + 1 < len(tried) and tried[i + 1] == m
        print("⚠️ [AI 붐빔] %s 응답 %s" % (m, r.status_code), flush=True)
        if again:
            time.sleep(0.8)      # 503 은 1초 안에 풀릴 때가 많다(예비는 5~40초씩 걸려 주 모델을 한 번 더 부르는 편이 빠르다)
    return None, last, (tried[-1] if tried else "")


def nim_suggest_target(name, amount, message, names, history=None, context=None, hints=None):
    """후원 메시지가 지목하는 선수를 AI 에게 묻는다(④ 단계). 예외를 던지지 않는다.
       돌려받는 값: {target, confidence} · 못 물었으면 skipped / error / gone / reason:'rate' · 잠깐 막힘이면 retry=True"""
    names = [n for n in (names or []) if n]
    if not nim_key() or not str(message or '').strip() or not names:
        return {"target": None, "confidence": 0.0, "skipped": True}
    if not nim_allowed():
        return {"target": None, "confidence": 0.0, "skipped": True, "reason": "rate", "retry": True}
    body = {
        "messages": [
            {"role": "system", "content": af.assign_system_prompt(names, hints=hints, history=history, context=context)},
            {"role": "user", "content": af.assign_user_prompt(name, amount, message)},
        ],
        "temperature": 0.1,
        "max_tokens": 200,
    }
    body.update(NIM_NO_THINK)
    try:
        r, code, _used = nim_post([NIM_MODEL, NIM_MODEL, NIM_MODEL_BACKUP], body, SUGGEST_TIMEOUT)
        if r is None:
            return {"target": None, "confidence": 0.0, "error": code or "no-response", "retry": True}
        if r.status_code != 200:
            if r.status_code in (404, 410):      # 고장이 아니라 '그 모델이 없어졌다' — 운영자가 할 일이 다르다
                print("❌ [AI 모델 없음] '%s' 응답 %s — 서버 설정 NIM_MODEL 을 살아 있는 모델로 바꿔주세요."
                      % (NIM_MODEL, r.status_code), flush=True)
                return {"target": None, "confidence": 0.0, "error": r.status_code, "gone": True}
            return {"target": None, "confidence": 0.0, "error": r.status_code, "retry": r.status_code in NIM_RETRYABLE}
        content = (r.json()["choices"][0]["message"].get("content") or "").strip()
        i, j = content.find('{'), content.rfind('}')     # JSON 덩어리만
        if i == -1 or j == -1:
            return {"target": None, "confidence": 0.0}
        parsed = json.loads(content[i:j + 1])
        target = parsed.get("target")
        if isinstance(target, str):
            target = target.strip()
            if target.lower() in ('null', 'none', ''):
                target = None
        if target not in names:      # 환각 막기: 실제 선수 이름과 같을 때만
            target = None
        try:
            conf = float(parsed.get("confidence", 0))
        except Exception:
            conf = 0.0
        return {"target": target, "confidence": conf}
    except Exception as e:
        return {"target": None, "confidence": 0.0, "error": type(e).__name__, "retry": True}


def ai_health():
    """AI 가 지금 어떤가 — 마지막 호출 결과. 조종실 AI 패널 머리의 점 색과 글자."""
    if not nim_key():
        return {'state': 'off', 'text': 'AI 꺼짐 · 칸과 단추는 돼요'}
    h = NIM_HEALTH
    if not h['at']:
        return {'state': 'idle', 'text': 'AI 대기 중'}
    if h['ok']:
        return {'state': 'ok', 'text': 'AI 연결됨 · %.1f초' % (h['ms'] / 1000)}
    mins = int((time.time() - h['at']) // 60)
    return {'state': 'busy', 'text': 'AI 붐빔' + (' · %d분 전' % mins if mins else '')}


# ── 배정 제안 ───────────────────────────────────────────
def _ck(name, amount, message, names):
    return (str(name or ''), af._int(amount), str(message or ''), tuple(names))


def cached_lookup(slices):
    """대기 후원 하나 → 조종실이 이미 물어 둔 배정 판단(10분 기억). 채팅 · 상황판 때문에 AI 를 또 부르지 않는다."""
    names = af.current_names(slices)
    now = time.time()

    def look(d):
        hit = _SUGGEST_CACHE.get(_ck(d.get('name'), d.get('amount'), d.get('message'), names))
        return hit[1] if hit and now - hit[0] < SUGGEST_TTL else None
    return look


async def suggest(bus, name, amount, message, names, slices=None):
    """규칙(①~③-c, 장부 읽기 — 이 갈래에서 바로) → 못 풀면 AI(④, 다른 갈래 · 시한) → 마무리. 언제나 dict."""
    key = _ck(name, amount, message, names)
    now = time.time()
    hit = _SUGGEST_CACHE.get(key)
    if hit and now - hit[0] < SUGGEST_TTL:
        return dict(hit[1], cached=True)
    res, pre = dm.suggest_rules(bus.store, name, message, names)
    if res is None:
        ctx_lines = af.game_context(slices if slices is not None else bus.state.slices)
        try:
            ai = await asyncio.wait_for(asyncio.to_thread(nim_suggest_target, name, amount, message, pre['names'],
                                                          pre['known'], ctx_lines, pre['hints']), SUGGEST_DEADLINE)
        except asyncio.TimeoutError:
            ai = {'target': None, 'confidence': 0.0, 'error': 'no-response', 'retry': True}
        res = dm.suggest_after_ai(pre, ai)
    if len(_SUGGEST_CACHE) > SUGGEST_CACHE_MAX:
        _SUGGEST_CACHE.clear()          # 무한히 크지 않게 — 방송 한 회 후원 수보다 훨씬 크다
    # ⚠️ 잠깐 막힌 답(붐빔 · 한도)은 기억하지 않는다 — 예전에 '모름' 을 10분 기억해서 2주 동안 5건이 묻혔다
    if not res.get('retry'):
        _SUGGEST_CACHE[key] = (now, res)
    return res


# ── 장부 · 공용 ─────────────────────────────────────────
def _need(req, authed):
    if not authed(req):
        return JSONResponse({'status': 'error', 'message': '로그인이 필요합니다'}, status_code=401)
    return None


async def _body(req):
    try:
        b = await req.json()
    except Exception:
        return {}
    return b if isinstance(b, dict) else {}


def today(bus):
    """이번 방송(session.id) 후원 — 장부에서 센다(AI 채팅 · 첫 화면 숫자 칸이 같은 셈). 실패하면 None."""
    try:
        sid = bus.state.get('session').get('id') or ''
        return af.today_summary(bus.store.donations(session=sid, limit=100000))
    except Exception as e:
        print('⚠️ [AI 사실표] 이번 방송 후원 집계 실패 — 그 항목만 빠집니다: %s' % type(e).__name__, flush=True)
        return None


def _names(players):
    out = []
    for p in players or []:
        n = str((p.get('name') if isinstance(p, dict) else p) or '').strip()
        if n:
            out.append(n)
    return out


# ── 주소 ───────────────────────────────────────────────
@route('/api/audit/suggest')
async def audit_suggest(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    body = await _body(req)
    slices = bus.state.slices
    pid = str(body.get('id') or '')
    if pid:
        it = next((x for x in (slices.get('pending') or []) if isinstance(x, dict) and x.get('id') == pid), None)
        if it is None:
            return JSONResponse({'status': 'error', 'gone': True, 'message': '대기함에 없는 후원입니다'}, status_code=404)
        if it.get('type') == 'off_work' or it.get('kind') == 'contrib':
            return {'status': 'success', 'id': pid, 'target': None, 'confidence': 0.0, 'tier': 'unknown', 'source': None,
                    'why': '후원이 아닌 카드(기여도 · 퇴근)', 'history': [], 'skipped': True}
        name, amount, message = it.get('name'), it.get('amount'), it.get('message')
    else:
        name, amount, message = body.get('name'), body.get('amount'), body.get('message')
    names = _names(body.get('players')) or af.current_names(slices)
    try:
        res = await suggest(bus, str(name or ''), af._int(amount), str(message or ''), names, slices)
    except Exception as e:
        res = {'target': None, 'confidence': 0.0, 'tier': 'unknown', 'source': None, 'why': 'AI 오류로 못 물어봄',
               'history': [], 'error': type(e).__name__}
    out = dict({'status': 'success'}, **res)
    if pid:
        out['id'] = pid
    return out


@route('/api/ai/board', methods=('GET',))
async def ai_board(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    try:
        slices = bus.state.slices
        f = af.build_facts(slices, suggest=cached_lookup(slices))
        out = {'status': 'success', 'tiles': af.board_tiles(f), 'ai': ai_health(), 'intents': af.INTENTS}
        if req.query_params.get('today'):
            out['today'] = today(bus)
        return out
    except Exception as e:
        return {'status': 'error', 'message': type(e).__name__}


@route('/api/ai/chat')
async def ai_chat(req, bus, authed, answer):
    bad = _need(req, authed)
    if bad:
        return bad
    body = await _body(req)
    question = str(body.get('question') or '').strip()
    intent = str(body.get('intent') or '').strip()
    history = body.get('messages') if isinstance(body.get('messages'), list) else []
    try:
        slices = bus.state.slices
        facts = af.build_facts(slices, today=today(bus), vip=af.vip_list(slices.get('tallies')),
                               suggest=cached_lookup(slices))
        # ⚡ 빠른 질문 단추 — 0초 · 늘 맞다 · NVIDIA 가 붐벼도 된다
        if intent:
            ans = af.quick_answer(intent, facts)
            return {'status': 'success', 'source': 'calc', 'reply': ans or '그건 아직 바로 답할 수 없어요. 글로 물어봐 주세요.'}
        if not question:
            return {'status': 'success', 'source': 'none', 'reply': '무엇을 도와드릴까요?'}
        fallback = af.quick_answer(af.detect_intent(question), facts)     # AI 가 못 답할 때 대신 줄 답

        def no_ai(msg):
            if fallback:
                return {'status': 'success', 'source': 'calc', 'reply': fallback + '\n\n(%s — 서버 계산으로 답했어요)' % msg}
            return {'status': 'success', 'source': 'none', 'reply': msg}

        if not nim_key():
            return no_ai('AI 키가 설정되지 않았어요 (서버 환경변수 NVIDIA_API_KEY)')
        if not nim_allowed():
            return no_ai('지금 AI 호출이 몰려서 잠시 후 다시 물어봐 주세요')
        msgs = [{'role': 'system', 'content': af.chat_system_prompt(facts, question)}]
        for m in history[-6:]:      # 직전 대화 몇 개만(토큰 절약)
            if isinstance(m, dict) and m.get('role') in ('user', 'assistant') and str(m.get('content') or ''):
                msgs.append({'role': m['role'], 'content': str(m['content'])})
        msgs.append({'role': 'user', 'content': question})
        # ⚠️ 채팅도 추론을 끈다 — 켜 두면 생각에 토큰을 다 쓰고 생각하는 과정이 화면에 그대로 나갔다
        req_body = dict({'messages': msgs, 'temperature': 0.2, 'max_tokens': af.CHAT_MAX_TOKENS}, **NIM_NO_THINK)
        try:
            r, _code, used = await asyncio.wait_for(
                asyncio.to_thread(nim_post, [NIM_CHAT_MODEL, NIM_CHAT_MODEL, NIM_CHAT_BACKUP], req_body, CHAT_TIMEOUT),
                CHAT_DEADLINE)
        except asyncio.TimeoutError:
            r, used = None, ''
        if r is None:
            return no_ai('지금 AI 서버가 붐벼서 답을 못 받았어요. 잠시 뒤 다시 물어봐 주세요. (후원·점수에는 영향 없습니다)')
        if r.status_code != 200:
            if r.status_code in (404, 410):
                # ⚠️ 주 모델이 아니라 '실제로 답한 모델' 을 댄다 — 예비가 410 인데 멀쩡한 주 모델을 고치러 간 적이 있다
                which = 'NIM_CHAT_BACKUP' if used == NIM_CHAT_BACKUP else 'NIM_CHAT_MODEL'
                print("❌ [AI 모델 없음] '%s' 응답 %s (%s 를 바꿔야 합니다)" % (used, r.status_code, which), flush=True)
                return {'status': 'success', 'source': 'none',
                        'reply': "이 AI 모델('%s')이 종료됐습니다.\n서버 설정의 %s 을(를) 살아 있는 모델로 바꾸고 재시작해주세요. "
                                 "(후원·점수에는 영향 없습니다)" % (used, which)}
            return no_ai('AI 오류 %s' % r.status_code)
        msg = r.json()['choices'][0]['message']
        reply = af.clean_reply(msg.get('content') or '')
        # ⚠️ reasoning_content 는 답이 아니라 '생각' 이다 — 답으로 쓰지 않는다
        if not reply:
            return no_ai('생각만 하다 답을 못 만들었어요. 조금 더 짧게 물어봐 주세요')
        if af.looks_broken(reply):      # 실측 11번에 1번 깨진 글자
            print('⚠️ [AI 채팅] 깨진 답이 와서 버렸습니다 (모델: %s)' % used, flush=True)
            return no_ai('AI 답이 깨져서 왔어요. 한 번 더 물어봐 주세요')
        return {'status': 'success', 'source': 'ai', 'reply': reply}
    except Exception as e:
        return {'status': 'success', 'source': 'none', 'reply': '(오류) %s' % type(e).__name__}


# ── 되돌리면 그 후원의 배정 판단도 잊는다 — 안 그러면 10분 동안 옛 답(잘못 간 사람)이 배지에 다시 뜬다 ──
def _forget_suggest(ctx, ref):
    if not str(ref or '').startswith('don_') or not _SUGGEST_CACHE:
        return
    d = ctx.store.donation(ref)
    if not d:
        return
    head = (str(d['name'] or ''), af._int(d['amount']), str(d['message'] or ''))
    for k in [k for k in _SUGGEST_CACHE if k[:3] == head]:
        _SUGGEST_CACHE.pop(k, None)


pl.ON_UNDO.append(_forget_suggest)
