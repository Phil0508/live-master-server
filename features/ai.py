# -*- coding: utf-8 -*-
"""🤖 AI 도우미 — NVIDIA NIM 으로 '이 후원은 누구 점수인가' 제안(기입 검증)과 조종실 AI 채팅.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import json
import os
import re
import threading
import time
from flask import jsonify, request
from server import (
    BASE_DIR, _vip_live, alias_lookup, app, db_query, donor_history, file_lock,
    get_db_connection, load_data, requests,
)


# ==========================================
# 🤖 NVIDIA NIM (AI 기입 검증 도우미)
#   후원 메시지를 읽고 "누구를 지목한 후원인지" 추정해, 운영자의 배정 실수를 잡아준다.
#   ⚠️ 절대 자동으로 점수를 바꾸지 않는다. 추천/경고만 제공하는 서포트 전용 기능이다.
# ==========================================
def load_nvidia_key():
    key = (os.environ.get('NVIDIA_API_KEY') or '').strip()
    if not key:
        cred_path = os.path.join(BASE_DIR, 'NVIDIA_CREDENTIALS.txt')  # git 제외 파일
        if os.path.exists(cred_path):
            try:
                with open(cred_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#') or '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        if k.strip() == 'NVIDIA_API_KEY':
                            key = v.split('#')[0].strip()
                            break
            except Exception as e:
                print(f"[NVIDIA 키 읽기 오류] {e}")
    return key

NVIDIA_API_KEY = load_nvidia_key()
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# ⚠️ 모델 이름은 환경변수로 바꿀 수 있게 둔다.
#    2026-08-26 에 쓰던 모델 둘이 같은 날 서비스 종료(410)돼 AI 기능이 방송 중에 통째로
#    멈췄다. 코드에 박혀 있으면 그때마다 고쳐서 배포해야 한다 — 방송 중에는 못 할 일이다.
#    서버 설정(NIM_MODEL / NIM_CHAT_MODEL)만 바꾸고 재시작하면 넘어갈 수 있게 한다.
# 2026-08-31 실측 (NVIDIA API 에 직접 물어본 값):
#     nvidia/nemotron-3-nano-30b-a3b        410 GONE  ← 여기 있던 모델. 죽었다
#     nvidia/nemotron-3-super-120b-a12b     503 잦음. 가끔 200
#     nvidia/nemotron-3.5-lightning-30b-a3b 200. 기입검증 0.61s · 채팅 1.26s
#     nvidia/nemotron-nano-3-30b-a3b        404 (목록에는 있는데 안 열림)
#     nvidia/nemotron-3-ultra-550b-a55b     60초 넘게 무응답
# 주 모델은 '지금 확실히 열려 있는 것' 으로 둔다.
# 자주 막히는 것을 주 모델로 두면 매번 예비로 넘어가느라 늦어진다 — 배정 제안은 8초,
# 채팅은 30초를 헛기다린 뒤에야 예비가 답한다.
# ⚠️ 2026-09-02 방송 4시간 전 점검: lightning-30b 가 90초 안에 한 번도 답하지 않았다
#    (4/4 타임아웃, 목록에는 있음). super-120b 는 바로 답했다. 그래서 다시 맞바꿨다.
#    8/31 에는 정반대였다(super 가 죽고 lightning 이 살아 있었다). 이 둘은 번갈아 죽는다 —
#    방송 전마다 실제로 호출해서 살아 있는 쪽을 주 모델로 둘 것.
NIM_MODEL = (os.environ.get('NIM_MODEL') or "nvidia/nemotron-3-super-120b-a12b").strip()
NIM_CHAT_MODEL = (os.environ.get('NIM_CHAT_MODEL') or "nvidia/nemotron-3-super-120b-a12b").strip()

# nemotron 3 계열은 생각을 먼저 늘어놓고 답한다. 기입검증은 JSON 한 줄만 필요하고
# 후원이 들어온 순간 바로 답해야 하므로 추론을 끈다.
#   실측(정답 4/4 · JSON 4/4): 추론 켠 채 1.10초 → 끄면 0.26초.
#   (예전 모델은 0.7초였으니 더 빨라졌다)
NIM_NO_THINK = {"chat_template_kwargs": {"thinking": False}}
NIM_CHAT_PREFIX = ""  # 채팅은 추론을 켜 둔다 — 설명이 필요한 자리라 그게 낫다.

# 🔁 붐빌 때 넘어갈 예비 모델.
#    503 은 고장이 아니라 "그 모델이 지금 몰렸다" 는 뜻이다. 몇 분 뒤면 풀리지만
#    방송 중에 몇 분은 길다. 한쪽이 막히면 다른 쪽으로 넘어가 AI 가 통째로 멈추지 않게 한다.
#    (실측: 같은 모델이 어떤 때는 6/6 되고 어떤 때는 overloaded 를 뱉는다. 큰 모델일수록 잦다)
NIM_MODEL_BACKUP = (os.environ.get('NIM_MODEL_BACKUP')
                    or "nvidia/nemotron-3.5-lightning-30b-a3b").strip()
# ⚠️ 여기에 죽은 모델(nano-30b, 410)이 들어 있었다. 주 모델이 503 으로 막히면
#    예비로 넘어갔다가 410 을 맞고, 그게 "모델이 종료됐다" 로 화면에 떴다.
#    예비도 반드시 살아 있는 것으로 둬야 한다.
NIM_CHAT_BACKUP = (os.environ.get('NIM_CHAT_BACKUP')
                   or "nvidia/nemotron-3.5-lightning-30b-a3b").strip()

# 다시 해보면 될 만한 응답. 410(모델이 없어짐)·401(키)은 다시 해도 같으므로 넣지 않는다.
NIM_RETRYABLE = (429, 500, 502, 503, 504)


def nim_post(models, body, timeout):
    """모델을 차례로 시도한다. 붐비면(503 등) 다음 모델로 넘어간다.

       돌려주는 값: (응답 or None, 마지막 상태코드, 실제로 답한 모델)
    """
    last = 0
    tried = [m for m in models if m]
    for i, m in enumerate(tried):
        one = dict(body)
        one["model"] = m
        try:
            r = requests.post(NIM_URL, headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                              json=one, timeout=timeout)
        except Exception:
            last = 0
            continue
        if r.status_code == 200:
            if i > 0:
                print("🔁 [AI 예비 모델] %s 이(가) 막혀 %s 로 넘어갔습니다."
                      % (tried[0], m), flush=True)
            return r, 200, m
        last = r.status_code
        if r.status_code not in NIM_RETRYABLE:
            return r, r.status_code, m      # 다시 해도 같은 오류 — 그대로 알린다
        more = " — 예비 모델로 넘어갑니다" if i + 1 < len(tried) else ""
        print("⚠️ [AI 붐빔] %s 응답 %s%s" % (m, r.status_code, more), flush=True)
    return None, last, (tried[-1] if tried else "")

# 분당 호출 한도. 넘으면 검증을 조용히 건너뛴다.
# 35 로 뒀을 때 부하 테스트에서 45건을 밀어넣으니 우리 리미터는 11건만 막았고
# 1건은 NVIDIA 쪽에서 그대로 429 를 맞았다. 즉 35 는 실제 허용치에 붙어 있었다.
NIM_RATE_LIMIT = 30
_nim_calls = []                 # 최근 호출 시각(초) 슬라이딩 윈도우
_nim_lock = threading.Lock()

def _nim_allowed():
    """분당 한도 안이면 True(그리고 이번 호출을 기록). 초과면 False."""
    now = time.time()
    with _nim_lock:
        while _nim_calls and now - _nim_calls[0] > 60:
            _nim_calls.pop(0)
        if len(_nim_calls) >= NIM_RATE_LIMIT:
            return False
        _nim_calls.append(now)
        return True

def nim_suggest_target(name, amount, message, players, history=None, context=None):
    """후원 메시지가 지목하는 플레이어를 추정한다.
       반환: {"target": 이름 또는 None, "confidence": 0.0~1.0}
       키 없음/한도 초과/오류/타임아웃 시에는 target=None 으로 조용히 실패한다(예외를 던지지 않는다)."""
    names = [(p.get('name') if isinstance(p, dict) else str(p)) for p in (players or [])]
    names = [n for n in names if n]
    if not NVIDIA_API_KEY or not requests or not (message or '').strip() or not names:
        return {"target": None, "confidence": 0.0, "skipped": True}
    if not _nim_allowed():
        return {"target": None, "confidence": 0.0, "skipped": True, "reason": "rate"}
    # ⚠️ 메시지 글자만 주면 'ㄱㅇㅈ' 같은 건 영영 못 푼다.
    #    이 후원자가 예전에 누구에게 갔는지, 지금 화면에서 뭐가 벌어지는지를 같이 준다.
    extra = ""
    if history:
        extra += ("\n이 후원자의 과거 배정: "
                  + ", ".join(f"{p} {c}번" for p, c in history[:4]))
    if context:
        extra += "\n지금 방송 상황: " + " / ".join(context)
    sys_prompt = (
        "너는 라이브 후원 방송의 기입 검증 도우미다. 후원 메시지를 읽고 "
        "그 후원이 아래 플레이어 중 누구를 지목/응원하는지 판단한다.\n"
        "플레이어: " + ", ".join(names) + extra + "\n"
        "규칙: 이름/별명/맥락으로 특정 플레이어를 지목하면 그 이름을, "
        "지목이 전혀 없으면 target 을 null 로 둔다. 반드시 목록에 있는 정확한 이름만 사용한다.\n"
        "과거 배정은 참고만 한다 — 메시지가 다른 사람을 가리키면 메시지를 따른다.\n"
        'JSON만 출력: {"target": "이름 또는 null", "confidence": 0.0~1.0}'
    )
    body = {
        "model": NIM_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"닉:{name}/금액:{amount}/메시지:{message}"},
        ],
        "temperature": 0.1,
        # ⚠️ 추론을 켜 두면 생각을 먼저 쓰다가 길이 제한에 잘려 JSON 이 아예 안 나온다.
        #    (실제로 그래서 답을 못 읽었다) 넉넉히 주되 추론은 끈다.
        "max_tokens": 200,
    }
    body.update(NIM_NO_THINK)
    try:
        # 붐비면 예비 모델로 넘어간다. 후원이 들어온 순간이라 기다릴 수 없다.
        r, _code, _used = nim_post([NIM_MODEL, NIM_MODEL_BACKUP], body, 8)
        if r is None:
            return {"target": None, "confidence": 0.0, "error": _code or "no-response"}
        if r.status_code != 200:
            # ⚠️ 410/404 는 서버 고장이 아니라 "그 모델이 없어졌다" 는 뜻이다.
            #    NVIDIA 는 모델을 예고 후 내린다. 운영자가 무엇을 해야 하는지 알 수 있게
            #    다른 오류와 구분해서 알려준다.
            if r.status_code in (404, 410):
                print(f"❌ [AI 모델 없음] '{NIM_MODEL}' 이(가) 응답 {r.status_code}. "
                      f"NVIDIA 에서 내려간 모델일 수 있습니다. "
                      f"서버 설정 NIM_MODEL 을 살아 있는 모델로 바꿔주세요.", flush=True)
                return {"target": None, "confidence": 0.0, "error": r.status_code, "gone": True}
            return {"target": None, "confidence": 0.0, "error": r.status_code}
        content = r.json()["choices"][0]["message"]["content"].strip()
        i, j = content.find('{'), content.rfind('}')   # JSON 블록만 추출
        if i == -1 or j == -1:
            return {"target": None, "confidence": 0.0}
        parsed = json.loads(content[i:j + 1])
        target = parsed.get("target")
        if isinstance(target, str):
            target = target.strip()
            if target.lower() in ('null', 'none', ''):
                target = None
        if target not in names:      # 환각 방지: 실제 플레이어 이름과 일치할 때만 인정
            target = None
        try:
            conf = float(parsed.get("confidence", 0))
        except Exception:
            conf = 0.0
        return {"target": target, "confidence": conf}
    except Exception as e:
        return {"target": None, "confidence": 0.0, "error": str(e)[:80]}

# ---- AI 서포트 채팅: 현재 방송 상태 스냅샷 + 시스템 프롬프트 ----
AI_SYSTEM_PROMPT = (
    "너는 '엔젤컴퍼니' 라이브 방송 운영 시스템의 AI 서포트 어시스턴트다.\n\n"
    "[이 프로그램이 무엇인가]\n"
    "- 시청자 후원(투네이션)을 받아 방송 화면(오버레이)에 리액션·연출을 띄우고, "
    "플레이어(출연자)들의 점수·기여도 랭킹을 관리하는 라이브 방송 운영 도구다.\n"
    "- 운영자(사람)가 '컨트롤러' 화면에서 조작한다. 너는 그 운영자를 돕는다.\n\n"
    "[핵심 흐름]\n"
    "- 후원이 들어오면 '승인 대기함'에 쌓인다. 운영자가 각 후원을 특정 플레이어에게 배정하면 "
    "그 플레이어의 점수·기여도가 오른다(대개 금액/10000 만큼).\n"
    "- 후원 금액대에 맞는 '시그니처'(효과음+이미지 연출)가 자동으로 화면에 재생된다.\n"
    "- 위젯: 플레이어 랭킹판, 후원 게이지, 계좌, 대결(match) 위젯, 퇴근빵(개인별 목표 레이스), "
    "슬롯머신/룰렛 게임 등.\n\n"
    "[너의 역할 = 서포트만]\n"
    "- 현재 상황을 파악해 질문에 답한다. 예: '지금 1등 누구야?', '대결 몇 점 차이야?', "
    "'대기함에 밀린 후원 있어?', '누가 역전당했어?'.\n"
    "- 상황 요약, 실수 방지 조언, 우선순위 제안을 한다.\n"
    "- ⚠️ 너는 직접 점수를 바꾸거나 조작을 실행하지 않는다. 정보 제공과 조언만 한다. "
    "실제 실행은 운영자가 버튼으로 직접 한다.\n\n"
    "[답변 규칙]\n"
    "- 제공된 '현재 방송 상태(JSON)'를 근거로 답한다. 직접 안 적혀 있어도 데이터로 계산·추론할 수 있으면 "
    "끝까지 계산해서 답한다. 예: 점수 차이는 두 점수를 빼서, 역전 여부·급상승은 최근 점수 로그와 현재 순위를 "
    "비교해서 알아낸다. 성급하게 '모른다'고 하지 말 것.\n"
    "- 한두 줄로 끝내지 말고, 운영자가 상황을 판단하는 데 도움이 되게 충분히 설명한다. 관련 숫자(점수·차이·순위·"
    "대기 건수·남은 시간 등)를 구체적으로 제시하고, 도움이 되면 다음에 뭘 하면 좋을지 짧은 제안도 덧붙인다.\n"
    "- 그래도 데이터에 정말 없는 항목이면, 없다고 말한 뒤 어디서 확인하면 되는지(어떤 위젯·기능을 켜거나 봐야 하는지)"
    " 알려준다. 숫자를 지어내지는 않는다.\n"
    "- 후원 건수·합계를 물으면 '오늘_후원' 을 그대로 쓴다. 점수 로그를 세어 짐작하지 않는다 — "
    "그건 배정 기록이라 후원 건수와 다르다(하나를 나눠주면 여러 줄이 된다).\n"
    "- 한국어로. 핵심을 먼저, 세부는 뒤에. 방송 중이라 읽기 쉽게 정리한다."
)

def _top_donors(d, n=8):
    """시그니처 1건의 신청자별 횟수 중 상위 n명. 스냅샷 토큰을 아끼려고 자른다.
       잘린 경우 '…그 외'를 남겨서, AI가 일부만 보고 전체인 양 답하지 않게 한다."""
    if not isinstance(d, dict) or not d:
        return None
    items = sorted(d.items(), key=lambda kv: kv[1], reverse=True)
    out = {k: v for k, v in items[:n]}
    if len(items) > n:
        out["…그 외"] = f"{len(items) - n}명"
    return out


def _goal_waiting(state):
    """목표를 넘었는데 아직 연출을 송출하지 않았는가."""
    tgt = int(state.get('target_goal') or 0)
    if tgt <= 0 or state.get('goal_event_approved'):
        return False
    # ⚠️ 막대와 같은 셈이어야 한다 — 점수 + 운영비 + 보정. 예전에는 기여도 합을 써서
    #    (기여도 = 점수 + 게임 보너스) 막대가 다 차기 전에 '넘었다' 고 했다.
    total = int((state.get('bottom_fixed') or {}).get('score') or 0)
    total += sum(int(b.get('score') or 0) for b in (state.get('bjs') or []))
    total += int(state.get('goal_offset') or 0)
    return total >= tgt


def _today_donations():
    """이번 방송에 들어온 후원 건수·합계·상위 후원자.

       ⚠️ AI 에게 세라고 시키면 틀린다. 점수 로그는 20건만 넘기는 데다 배정 기록이라
          후원 건수와 다르다(반반으로 나누면 한 후원이 여러 줄이 된다).
          장부에서 서버가 직접 센다.
       ⚠️ donation_history 는 방송 시작/종료 때 비워지므로 자연히 '이번 방송' 이 된다.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("SELECT COUNT(*), SUM(amount) FROM donation_history"))
            row = cur.fetchone() or (0, 0)
            cnt, total = int(row[0] or 0), int(row[1] or 0)
            cur.execute(db_query(
                "SELECT name, COUNT(*), SUM(amount) FROM donation_history"
                " GROUP BY name ORDER BY SUM(amount) DESC LIMIT 5"))
            top = [{"이름": r[0], "횟수": int(r[1] or 0), "금액합": int(r[2] or 0)}
                   for r in cur.fetchall()]
        return {"건수": cnt, "합계금액": total, "많이_쏜_사람": top}
    except Exception as e:
        print(f"⚠️ [AI 스냅샷] 오늘 후원 집계 실패 — 그 항목만 빠집니다: {e}", flush=True)
        return None


def build_ai_snapshot(state):
    """AI 서포트가 상황을 파악할 수 있게 현재 상태의 핵심만 추려 컴팩트한 dict로 만든다.
       (레이아웃·에디터·미디어 데이터 등 방송 판단과 무관한 큰 값은 제외해 토큰을 아낀다.)"""
    extra = bool(state.get("extra_game_active"))
    src = "extra_bjs" if extra else "bjs"
    ranking = sorted(
        [{"이름": b.get("name"), "점수": b.get("score", 0), "기여도": b.get("contribution", 0)}
         for b in state.get(src, [])],
        key=lambda x: x["기여도"], reverse=True,
    )
    pend = [{"이름": d.get("name"), "금액": d.get("amount"), "메시지": d.get("message")}
            for d in state.get("pending_donations", []) if d.get("type") != "off_work"]
    recent_logs = [{"시각": l.get("time"), "대상": l.get("name"), "점수변화": l.get("val")}
                   for l in (state.get("logs") or [])[:20]]   # 최신순 상위 20건
    tally = state.get("sig_tally") or {}
    sig_tally_list = sorted(
        [{"제목": v.get("title"), "신청수": v.get("count"), "금액": v.get("amount"),
          "신청자": _top_donors(v.get("donors"))} for v in tally.values()],
        key=lambda x: (x["신청수"] or 0), reverse=True)
    # 시그니처를 많이 쏜 사람 순위. 8b 모델은 여러 항목을 가로질러 합산하는 걸 자주 틀리므로
    # "오늘 시그 제일 많이 쏜 사람?" 에 바로 답할 수 있게 서버에서 미리 합쳐준다.
    donor_total = {}
    for v in tally.values():
        amt = v.get("amount") or 0
        for nm, cnt in (v.get("donors") or {}).items():
            row = donor_total.setdefault(nm, {"횟수": 0, "금액합": 0})
            row["횟수"] += int(cnt or 0)
            row["금액합"] += int(cnt or 0) * amt
    sig_donor_rank = sorted(
        [{"이름": k, "횟수": v["횟수"], "금액합": v["금액합"]} for k, v in donor_total.items()],
        key=lambda x: x["금액합"], reverse=True)[:10]
    roul = state.get("roulette") or {}
    return {
        "방송중": bool(state.get("broadcast_active")),
        "임시게임_진행중": extra,
        "플레이어_랭킹": ranking,
        "승인_대기_후원": pend,
        "승인_대기_건수": len(pend),
        "리액션_대기열_수": len(state.get("reaction_queue", [])),
        "최근_점수_로그": recent_logs,
        # ⚠️ 점수 로그는 '배정' 기록이라 후원 건수와 다르다. 후원 건수를 물으면 여기를 봐야 한다.
        "오늘_후원": _today_donations(),
        "최근_후원": state.get("latest_donation"),
        "방송_목표금액": state.get("target_goal"),
        "대결": state.get("match_data"),
        "퇴근빵_켜짐": bool(state.get("home_race_enabled")),
        "퇴근빵_목표": state.get("home_goals"),
        "계좌": state.get("account"),
        "운영비": state.get("bottom_fixed"),
        "시그니처_신청집계": sig_tally_list,
        "시그니처_후원자_순위": sig_donor_rank,
        # ⚠️ goal_event_pending 은 true 가 되는 코드가 없어서 늘 거짓이었다.
        #    조종실이 승인 버튼을 띄우는 기준(기여도 합계가 목표를 넘었는가)과 같게 맞춘다.
        "목표연출_승인대기": bool(_goal_waiting(state)),
        "슬롯": {"켜짐": bool(state.get("slot_enabled")), "후보수": len(state.get("slot_pool") or [])},
        "룰렛": {"켜짐": bool(state.get("roulette_enabled")), "당첨자": roul.get("winner_name"), "돌리는중": bool(roul.get("is_spinning"))},
        "티커_문구": state.get("ticker_text"),
    }

def _ai_vip_list():
    """AI 스냅샷용 VIP 목록 — 이번 방송 순위 등급 + 직접 준 등급. 실패해도 빈 리스트."""
    out = []
    try:
        live = _vip_live(load_data())
        out = [{"이름": v['name'], "등급": v['grade'], "뱃지": v['badge'], "순위": v['rank']}
               for v in sorted(live.values(), key=lambda v: v['rank'])]
    except Exception:
        pass
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("SELECT name, grade, badge FROM vip_donators ORDER BY name ASC"))
            out += [{"이름": r[0], "등급": r[1], "뱃지": r[2], "비고": "직접 준 등급"} for r in cur.fetchall()]
    except Exception:
        pass
    return out

# ══ 🎯 배정 대상 판단 ══
#
# 예전에는 AI 에게 메시지 글자만 던지고 끝이었다. 그래서 'ㄱㅇㅈ' 처럼 글자만으로는
# 풀 수 없는 것이 전부 '모름' 으로 떨어졌고, 자리를 비운 사이 대기함만 쌓였다.
#
# 이제 네 가지를 순서대로 본다. 앞의 것이 확실하면 AI 를 아예 부르지 않는다
# (분당 한도를 아끼고, 무엇보다 즉시 답이 나온다).
#   ① 메시지에 플레이어 이름이 그대로 있는가
#   ② 그 말이 늘 특정 플레이어로 이어져 왔는가 (별명 기억)
#   ③ 이 후원자가 늘 같은 사람에게 갔는가 (후원자 이력)
#   ④ 그래도 애매하면 AI 에게 — 위 세 가지를 근거로 함께 넘긴다
#
# ⚠️ 확신은 하나의 문턱이 아니라 세 단계다. 예전에는 0.85 하나로 잘라서,
#    0.84 는 아무 표시 없이 조용히 묻혔다. 이제 자동/추천/모름 으로 나눠
#    '모름' 도 눈에 보이게 한다 — 사람이 봐야 할 것을 숨기지 않는 게 핵심이다.
CONF_AUTO = 0.90      # 이 위는 오토파일럿이 스스로 배정한다
CONF_SUGGEST = 0.60   # 이 위는 추천만 한다(사람이 누른다)


def _tier(conf):
    if conf >= CONF_AUTO:
        return 'auto'
    if conf >= CONF_SUGGEST:
        return 'suggest'
    return 'unknown'


def game_context(state):
    """지금 화면에서 벌어지는 일. AI 가 금액·이름을 문맥으로 읽게 해준다."""
    out = []
    try:
        g = state.get('siggame') or {}
        goals = [c for c in (g.get('cards') or []) if c.get('flippedAt') and not c.get('doneAt')]
        if g.get('enabled') and goals:
            out.append('시그뒤집기 진행 중 — 아직 못 받은 목표 금액: '
                       + ', '.join(f"{int(c.get('amount') or 0):,}원" for c in goals))
        md = state.get('match_data') or {}
        if md.get('active'):
            teams = []
            for p in (md.get('players') or []):
                mem = [str(m).strip() for m in (p.get('members') or []) if str(m or '').strip()]
                teams.append(f"{p.get('name')}({'·'.join(mem)})" if mem else str(p.get('name')))
            if teams:
                out.append('대결 진행 중 — ' + ' vs '.join(teams))
        if state.get('home_race_enabled'):
            out.append('퇴근전쟁 진행 중')
        if (state.get('hell') or {}).get('on'):
            out.append('지옥탈출 진행 중')
    except Exception:
        pass
    return out


# 이름 뒤에 흔히 붙는 조사·호칭. '철수형' → '철수' 로 되돌리려고 쓴다.
_NAME_TAILS = ('에게', '한테', '이랑', '님께', '님', '씨', '형', '누나', '오빠', '언니',
               '쨩', '찡', '아', '야', '이', '가', '은', '는', '을', '를', '와', '과',
               '랑', '도', '만', '께')


def _name_forms(word):
    """낱말 하나에서 '이름일 수 있는 모양'들을 만든다(조사·호칭을 두 번까지 뗀다)."""
    out = {word}
    cur = word
    for _ in range(2):
        for t in _NAME_TAILS:
            if len(cur) > len(t) and cur.endswith(t):
                cur = cur[:-len(t)]
                out.add(cur)
                break
        else:
            break
    return out


def names_in_message(msg, names):
    """메시지가 지목하는 이름을 두 갈래로 나눠 돌려준다.

       exact — 낱말이 딱 떨어진다('철수', '철수형', '철수에게'). 믿을 만하다.
       loose — 글자만 겹친다('철수했다가', '밍밍화이팅'). 참고는 되지만 확실하지 않다.

       ⚠️ 예전에는 이 둘을 구분하지 않고 '글자가 들어 있으면' 전부 확실한 것으로 봤다.
          그래서 '철수했다가 다시 왔어요' 가 철수에게 자동 배정됐다.
       """
    txt = str(msg or '')
    exact, loose = set(), set()
    if not txt:
        return exact, loose
    for w in re.split(r'[\s,./!?~\-()\[\]"\'·:;]+', txt):
        w = w.strip()
        if not w:
            continue
        forms = _name_forms(w)
        # 여러 이름이 걸리면 가장 긴 것을 쓴다('수아' 와 '수' 가 같이 있을 때)
        best = None
        for n in names:
            if n in forms and (best is None or len(n) > len(best)):
                best = n
        if best:
            exact.add(best)
    for n in names:
        if n and n not in exact and n in txt:
            loose.add(n)
    return exact, loose


def _hold_if_message_points_elsewhere(res, loose):
    """메시지가 다른 이름을 가리키고 있으면 자동 배정을 막는다.

       ⚠️ 이력·별명은 '이 사람은 늘 밍밍에게 줬다' 는 통계일 뿐이다.
          그런데 그 후원의 메시지에 '철수' 글자가 들어 있다면, 통계보다 지금 쓴 말이
          우선이어야 한다. 낱말이 딱 떨어지면 ① 에서 이미 잡히고, 여기 걸리는 것은
          '철수화이팅' 처럼 붙여 쓴 애매한 경우다 — 애매하면 사람이 봐야 한다.
    """
    tgt = res.get('target')
    if not tgt or not loose or tgt in loose:
        return res
    if res.get('tier') != 'auto':
        return res
    other = ', '.join(sorted(loose))
    return dict(res, tier='suggest', confidence=min(res.get('confidence') or 0, 0.85),
                why=(res.get('why') or '') + f" — 다만 메시지에 '{other}' 글자가 있어 확인 필요")


def suggest_target(donor, amount, message, players, state=None):
    """이 후원이 누구를 지목하는지 판단한다.
       반환: {target, confidence, tier, source, why, history}"""
    names = [str(p.get('name') if isinstance(p, dict) else p or '').strip() for p in (players or [])]
    names = [n for n in names if n]
    msg = str(message or '')
    hist = donor_history(donor)
    base = {'target': None, 'confidence': 0.0, 'tier': 'unknown',
            'source': None, 'why': None,
            'history': [{'name': p, 'count': c} for p, c in hist]}
    if not names:
        return base

    # ① 메시지에 이름이 그대로 — 가장 확실하다.
    #    단 '낱말이 딱 떨어질 때'만이다. 글자만 겹치는 것은 아래에서 추천으로 낮춘다.
    exact, loose = names_in_message(msg, names)
    if len(exact) == 1:
        one = next(iter(exact))
        return dict(base, target=one, confidence=0.97, tier='auto',
                    source='이름', why=f'메시지에 \'{one}\' 이 있음')
    if len(exact) > 1:
        # 두 사람 이상을 부른 후원은 반반일 수 있다. 사람이 봐야 한다.
        return dict(base, target=None, confidence=0.0, tier='unknown',
                    source='이름', why='여러 사람을 부름: ' + ', '.join(sorted(exact)))

    # ② 별명 기억
    # ⚠️ 한 번만 본 말은 쓰지 않는다. '오늘도' 같은 흔한 말이 우연히 한 번
    #    특정 플레이어로 이어진 것까지 추천으로 올리면 잡음만 된다.
    #    두 번 이상 같은 사람으로 이어졌을 때부터가 '별명'이라 부를 만하다.
    al = alias_lookup(msg, names)
    if al and al[1] >= 2:
        player, hits, tok = al
        conf = min(0.95, 0.62 + 0.09 * hits)
        return _hold_if_message_points_elsewhere(
            dict(base, target=player, confidence=round(conf, 2), tier=_tier(conf),
                 source='별명', why=f'\'{tok}\' 은 지금까지 {hits}번 모두 {player} 였음'), loose)

    # ③ 후원자 이력 — 늘 같은 사람에게 갔는가
    known = [(p, c) for p, c in hist if p in names]
    if known:
        top_p, top_c = known[0]
        others = sum(c for p, c in known[1:])
        if others == 0 and top_c >= 2:
            conf = min(0.93, 0.66 + 0.07 * top_c)
            return _hold_if_message_points_elsewhere(
                dict(base, target=top_p, confidence=round(conf, 2), tier=_tier(conf),
                     source='이력', why=f'이 후원자는 지금까지 {top_c}번 모두 {top_p} 였음'), loose)
        if top_c >= 3 * max(1, others):
            conf = 0.7
            return _hold_if_message_points_elsewhere(
                dict(base, target=top_p, confidence=conf, tier=_tier(conf),
                     source='이력', why=f'{top_c}번 {top_p} / 그 외 {others}번'), loose)

    # ③-b 글자만 겹치는 이름 — 버리지 않고 '추천'으로만 올린다.
    #    '밍밍화이팅' 처럼 붙여 쓴 진짜 지목을 놓치지 않으면서,
    #    '철수했다가' 같은 우연한 겹침으로 돈이 자동으로 가지는 않게 한다.
    if len(loose) == 1:
        one = next(iter(loose))
        return dict(base, target=one, confidence=0.75, tier=_tier(0.75),
                    source='이름', why=f'메시지에 \'{one}\' 글자가 있음 (낱말이 딱 떨어지진 않음)')
    if len(loose) > 1:
        return dict(base, target=None, confidence=0.0, tier='unknown',
                    source='이름', why='여러 이름 글자가 섞임: ' + ', '.join(sorted(loose)))

    # ④ 여기까지 못 풀면 AI 에게. 위에서 모은 것을 근거로 같이 넘긴다.
    ctx = game_context(state) if state else []
    ai = nim_suggest_target(donor, amount, msg, names,
                            history=known, context=ctx)
    conf = float(ai.get('confidence') or 0)
    if not ai.get('target'):
        # ⚠️ 왜 모르는지를 사람 말로 돌려준다. 'rate' 같은 낱말은 화면에 그대로 뜨면
        #    운영자가 무슨 뜻인지 알 수 없고, 그러면 그 표시를 아예 안 믿게 된다.
        if ai.get('reason') == 'rate':
            why = 'AI 호출이 잠시 몰려 못 물어봄 (조금 뒤 다시 봄)'
        elif ai.get('skipped'):
            why = 'AI 가 꺼져 있음 — 이름·별명·이력으로는 못 찾음'
        elif ai.get('error') in NIM_RETRYABLE:
            # 붐빈 것뿐이라 저절로 풀린다. '오류' 라고 하면 고칠 게 있는 줄 알고
            # 방송 중에 서버를 건드리게 된다.
            why = 'AI 서버가 붐빕니다 — 잠시 뒤 저절로 됩니다'
        elif ai.get('gone'):
            why = 'AI 모델이 종료됐습니다 — 서버 설정에서 모델을 바꿔주세요'
        elif ai.get('error'):
            why = 'AI 오류로 못 물어봄'
        elif hist:
            why = '메시지로도 이력으로도 특정이 안 됨'
        else:
            why = '처음 보는 후원자이고 메시지에 단서가 없음'
        return dict(base, target=None, confidence=0.0, tier='unknown', source='AI', why=why)
    # AI 는 이력·별명만큼 믿지 않는다. 위쪽 단계에서 걸리지 않은 건은 애매한 것이다.
    conf = min(conf, 0.88)
    return _hold_if_message_points_elsewhere(
        dict(base, target=ai['target'], confidence=round(conf, 2), tier=_tier(conf),
             source='AI', why='메시지 내용으로 추정'), loose)


_SUGGEST_CACHE = {}   # (이름, 금액, 메시지, 플레이어들) → (물은 시각, 답)


@app.route('/api/audit/suggest', methods=['POST'])
def api_audit_suggest():
    """[AI 기입 검증] 후원 메시지가 지목하는 플레이어를 추정해 돌려준다.
       컨트롤러가 대기함 후원 1건당 1회 호출해 '추천 배지 / 오배정 경고'에만 쓴다.
       실패해도 항상 200 + target=None 으로 응답해 컨트롤러가 멈추지 않게 한다."""
    try:
        body = request.get_json(silent=True) or {}
        name = str(body.get('name', ''))
        amount = body.get('amount', 0)
        message = str(body.get('message', ''))
        players = body.get('players')
        if not players:   # 클라이언트가 안 보냈으면 서버 상태에서 현재 플레이어를 읽는다
            with file_lock:
                state = load_data()
                src = 'extra_bjs' if state.get('extra_game_active') else 'bjs'
                players = [b.get('name') for b in state.get(src, [])]
        # 🧠 폰 조종실과 PC 조종실이 같은 후원을 각각 물어본다 → NIM 이 두 번 간다(분당 30회 한도).
        #    같은 (이름·금액·메시지·플레이어) 답은 10분 동안 기억해 한 번만 묻는다.
        _ck = (name, int(amount or 0), message, tuple(players or []))
        _now = time.time()
        _hit = _SUGGEST_CACHE.get(_ck)
        if _hit and _now - _hit[0] < 600:
            return jsonify({"status": "success", **_hit[1], "cached": True})
        with file_lock:
            st = load_data()
        result = suggest_target(name, amount, message, players, st)
        if len(_SUGGEST_CACHE) > 500:
            _SUGGEST_CACHE.clear()          # 무한히 크지 않게 — 방송 한 회차 후원 수보다 훨씬 크다
        _SUGGEST_CACHE[_ck] = (_now, result)
        return jsonify({"status": "success", **result})
    except Exception as e:
        return jsonify({"status": "success", "target": None, "confidence": 0.0, "error": str(e)[:80]})

@app.route('/api/ai/chat', methods=['POST'])
def api_ai_chat():
    """[AI 서포트 채팅] 운영자가 현재 상황을 물어보면, 실시간 상태 스냅샷을 근거로 답한다.
       조작은 하지 않고 정보/조언만. 실패해도 항상 200 + 안내 문구로 응답한다."""
    try:
        body = request.get_json(silent=True) or {}
        question = str(body.get('question', '')).strip()
        history = body.get('messages') or []
        if not question:
            return jsonify({"status": "success", "reply": "무엇을 도와드릴까요?"})
        if not NVIDIA_API_KEY or not requests:
            return jsonify({"status": "success",
                            "reply": "AI 키가 설정되지 않았어요. (Render 환경변수 NVIDIA_API_KEY 확인)"})
        if not _nim_allowed():
            return jsonify({"status": "success",
                            "reply": "지금 AI 호출이 몰려서 잠시 후 다시 물어봐 주세요."})
        with file_lock:
            state = load_data()
            snap = build_ai_snapshot(state)
        snap["VIP_후원자"] = _ai_vip_list()   # 상태 밖(DB)이라 여기서 붙인다
        sys_full = NIM_CHAT_PREFIX + AI_SYSTEM_PROMPT + "\n\n[현재 방송 상태(JSON)]\n" + json.dumps(snap, ensure_ascii=False)
        msgs = [{"role": "system", "content": sys_full}]
        for m in history[-6:]:   # 직전 대화 몇 개만(토큰 절약)
            role = m.get('role'); content = str(m.get('content', ''))
            if role in ('user', 'assistant') and content:
                msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": question})
        # ⚠️ 채팅도 추론을 끈다. 켜 뒀더니 700 토큰을 생각에 다 쓰고 답을 쓰기 전에
        #    잘려서, 화면에 생각하는 과정이 그대로 나갔다
        #    ("Okay, let's see. The user is asking… Let me count the entries…").
        req_body = {"messages": msgs, "temperature": 0.3, "max_tokens": 700}
        req_body.update(NIM_NO_THINK)
        # 붐비면 예비 모델로 넘어간다 — 한쪽이 막혔다고 채팅이 통째로 죽지 않게.
        r, _code, _used = nim_post([NIM_CHAT_MODEL, NIM_CHAT_BACKUP], req_body, 30)
        if r is None:
            return jsonify({"status": "success",
                            "reply": "지금 AI 서버가 붐벼서 답을 못 받았어요. "
                                     "잠시 뒤 다시 물어봐 주세요. (후원·점수에는 영향 없습니다)"})
        if r.status_code != 200:
            if r.status_code in (404, 410):
                # ⚠️ 주 모델이 아니라 '실제로 답한 모델'(_used) 을 대야 한다.
                #    예전에는 늘 NIM_CHAT_MODEL 을 찍었다. 주 모델이 503 이라 예비로
                #    넘어가 410 을 맞은 경우, 멀쩡한 주 모델을 가리키며 "종료됐다" 고
                #    말했다 — 사장님이 엉뚱한 설정을 고치러 갔다.
                _which = 'NIM_CHAT_BACKUP' if _used == NIM_CHAT_BACKUP else 'NIM_CHAT_MODEL'
                print(f"❌ [AI 모델 없음] '{_used}' 이(가) 응답 {r.status_code}. "
                      f"({_which} 를 바꿔야 합니다)", flush=True)
                return jsonify({"status": "success",
                                "reply": f"이 AI 모델('{_used}')이 종료됐습니다.\n"
                                         f"서버 설정의 {_which} 을(를) 살아 있는 모델로 "
                                         "바꾸고 재시작해주세요. (후원·점수에는 영향 없습니다)"})
            return jsonify({"status": "success", "reply": f"(AI 오류 {r.status_code}) 잠시 후 다시 시도해주세요."})
        msg = r.json()["choices"][0]["message"]
        reply = (msg.get("content") or "").strip()
        # ⚠️ reasoning_content 는 답이 아니라 '생각' 이다. 예전에는 답이 비면 그걸 대신
        #    보여줬는데, 지금 모델은 거기에 혼잣말을 담는다. 그대로 내보내면 조종실에
        #    "Okay, let's see. The user is asking…" 같은 게 뜬다. 답으로 쓰지 않는다.
        if not reply:
            think = (msg.get("reasoning_content") or "").strip()
            if think:
                print(f"⚠️ [AI 채팅] 답이 비어 왔습니다(생각만 {len(think)}자). "
                      f"모델: {_used}", flush=True)
            reply = "생각만 하다 답을 못 만들었어요. 조금 더 짧게 물어봐 주세요."
        return jsonify({"status": "success", "reply": reply})
    except Exception as e:
        return jsonify({"status": "success", "reply": f"(오류) {str(e)[:100]}"})
