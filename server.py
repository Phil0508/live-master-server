import sys
import os
import io

# GUI 모드(console=False)에서 발생하는 모든 에러를 파일로 로깅하여 크래시 분석
if getattr(sys, 'frozen', False):
    try:
        exe_dir = os.path.dirname(sys.executable)
        log_file = open(os.path.join(exe_dir, 'server_error.log'), 'w', encoding='utf-8', buffering=1)
        sys.stderr = log_file
        sys.stdout = log_file
    except Exception:
        pass
else:
    # 윈도우 콘솔 UTF-8 출력 강제 (cp949 이모지 에러 방지)
    try:
        if sys.stdout is not None and hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        if sys.stderr is not None and hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

import json
import copy
import threading
import logging
import pyotp
import secrets

import time
import csv
import queue
import shutil
import socket
import sqlite3
from contextlib import contextmanager
import ssl
import urllib.request
import urllib.parse

try:
    import requests
except ImportError:
    requests = None

# Try importing psycopg2 for PostgreSQL support
try:
    import psycopg2
except ImportError:
    psycopg2 = None

DATABASE_URL = os.environ.get('DATABASE_URL')
IS_POSTGRES = bool(DATABASE_URL)

def db_query(query):
    if IS_POSTGRES:
        return query.replace('?', '%s')
    return query

# ⚡ [연결 재사용] 예전에는 DB 작업마다 새 연결을 열고 닫았다.
# Render(오레곤)에서 Supabase(서울)까지는 TLS 핸드셰이크만 왕복 여러 번이라
# 연결 생성 하나가 쿼리 10개보다 비쌌고, 점수 저장이 2초를 넘겼다.
# 스레드마다 연결을 하나씩 살려두고 재사용한다. (Flask가 스레드로 요청을 처리하므로
# 연결을 공유하면 안 되고, 스레드 로컬이어야 안전하다)
_db_local = threading.local()

def _new_db_connection():
    if IS_POSTGRES:
        if psycopg2 is None:
            raise ImportError("psycopg2 is not installed but DATABASE_URL is set.")
        db_url = DATABASE_URL
        if 'sslmode=' not in db_url.lower():
            sep = '&' if '?' in db_url else '?'
            db_url += f"{sep}sslmode=require"
        return psycopg2.connect(db_url, connect_timeout=15)
    return sqlite3.connect(DB_FILE)

def _get_live_connection():
    """스레드에 살아있는 연결을 돌려준다. 끊겼으면 새로 연다.

    ⚠️ 여기서 'SELECT 1' 같은 확인 쿼리를 보내면 안 된다.
    매 작업마다 왕복이 하나 더 붙어서 연결 재사용으로 아낀 시간을 도로 까먹는다.
    서버가 유휴 연결을 끊은 경우는 실제 쿼리에서 예외로 드러나므로,
    호출부(save_data_sync 등)에서 한 번 재시도해 자가복구한다.
    """
    conn = getattr(_db_local, 'conn', None)
    if conn is not None and IS_POSTGRES and conn.closed:
        conn = None
    if conn is None:
        conn = _new_db_connection()
        _db_local.conn = conn
    return conn

@contextmanager
def get_db_connection():
    conn = _get_live_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        # 실패한 연결은 상태가 오염됐을 수 있으므로 버리고 다음에 새로 연다
        try: conn.rollback()
        except Exception: pass
        try: conn.close()
        except Exception: pass
        _db_local.conn = None
        raise
from flask import Flask, jsonify, request, send_from_directory, redirect, url_for, session
from flask_cors import CORS
try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:
    tk = None
    messagebox = None
import webbrowser

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, '_MEIPASS', BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

DB_FILE = os.path.join(BASE_DIR, 'live_master.db')
LAYOUT_FILE = os.path.join(BASE_DIR, 'layout.json')
AUTH_CONFIG_FILE = os.path.join(BASE_DIR, 'auth_config.json')

def load_auth_config():
    config = {
        'admin_password': '0508',
        'session_secret': 'isacbin_master_key_0508',
        'totp_secret': ''
    }
    if os.path.exists(AUTH_CONFIG_FILE):
        try:
            with open(AUTH_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'admin_password' in data:
                    config['admin_password'] = data['admin_password']
                if 'session_secret' in data:
                    config['session_secret'] = data['session_secret']
                if 'totp_secret' in data:
                    config['totp_secret'] = data['totp_secret']
        except Exception as e:
            print(f"Error reading auth config: {e}")
            
    env_password = os.environ.get('ADMIN_PASSWORD')
    if env_password:
        config['admin_password'] = env_password.strip()
        
    env_session_secret = os.environ.get('SESSION_SECRET')
    if env_session_secret:
        config['session_secret'] = env_session_secret.strip()
        
    env_totp_secret = os.environ.get('TOTP_SECRET')
    if env_totp_secret:
        config['totp_secret'] = env_totp_secret.strip()
        
    if not config['totp_secret']:
        config['totp_secret'] = pyotp.random_base32()
        save_auth_config(config)
        
    return config

def save_auth_config(config):
    try:
        with open(AUTH_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error writing auth config: {e}")

# ==========================================
# 🟢 Supabase 시그니처 연동 (Storage + PostgREST)
#    - 시그니처 데이터/미디어는 Supabase 에 있고, 서버는 secret 키로 대신 조회한다.
#    - 브라우저(오버레이/컨트롤러)는 같은 서버의 /api/signatures 만 호출 → 키 노출/CORS/Mixed-Content 없음
# ==========================================
def load_supabase_config():
    cfg = {
        'url': (os.environ.get('SUPABASE_URL') or '').strip().rstrip('/'),
        'key': (os.environ.get('SUPABASE_SECRET_KEY') or '').strip(),
    }
    # 로컬 개발 편의: 환경변수가 없으면 SUPABASE_CREDENTIALS.txt 에서 읽는다 (git 제외 파일)
    if not cfg['url'] or not cfg['key']:
        cred_path = os.path.join(BASE_DIR, 'SUPABASE_CREDENTIALS.txt')
        if os.path.exists(cred_path):
            try:
                with open(cred_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#') or '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        k = k.strip(); v = v.split('#')[0].strip()
                        if k == 'SUPABASE_URL' and not cfg['url']:
                            cfg['url'] = v.rstrip('/')
                        elif k == 'SUPABASE_SECRET_KEY' and not cfg['key']:
                            cfg['key'] = v
            except Exception as e:
                print(f"[Supabase 설정 읽기 오류] {e}")
    return cfg

SUPABASE = load_supabase_config()

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
NIM_MODEL = "meta/llama-3.1-8b-instruct"   # 작고 빠름(≈0.7s). 단순 분류엔 충분.
NIM_CHAT_MODEL = "nvidia/nvidia-nemotron-nano-9b-v2"  # AI 서포트 채팅용. 8b보다 서술·추론이 좋고 ~3-4s.
NIM_CHAT_PREFIX = "/no_think "  # nemotron 계열: 추론 CoT를 끄는 지시(빠르고 빈 응답 방지). 다른 모델이면 그냥 텍스트로 무시됨.

# 분당 호출 한도. 외부 계정 한도(40/분)보다 안전하게 낮춰 잡고, 넘으면 검증을 조용히 건너뛴다.
NIM_RATE_LIMIT = 35
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

def nim_suggest_target(name, amount, message, players):
    """후원 메시지가 지목하는 플레이어를 추정한다.
       반환: {"target": 이름 또는 None, "confidence": 0.0~1.0}
       키 없음/한도 초과/오류/타임아웃 시에는 target=None 으로 조용히 실패한다(예외를 던지지 않는다)."""
    names = [(p.get('name') if isinstance(p, dict) else str(p)) for p in (players or [])]
    names = [n for n in names if n]
    if not NVIDIA_API_KEY or not requests or not (message or '').strip() or not names:
        return {"target": None, "confidence": 0.0, "skipped": True}
    if not _nim_allowed():
        return {"target": None, "confidence": 0.0, "skipped": True, "reason": "rate"}
    sys_prompt = (
        "너는 라이브 후원 방송의 기입 검증 도우미다. 후원 메시지를 읽고 "
        "그 후원이 아래 플레이어 중 누구를 지목/응원하는지 판단한다.\n"
        "플레이어: " + ", ".join(names) + "\n"
        "규칙: 이름/별명/맥락으로 특정 플레이어를 지목하면 그 이름을, "
        "지목이 전혀 없으면 target 을 null 로 둔다. 반드시 목록에 있는 정확한 이름만 사용한다.\n"
        'JSON만 출력: {"target": "이름 또는 null", "confidence": 0.0~1.0}'
    )
    body = {
        "model": NIM_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"닉:{name}/금액:{amount}/메시지:{message}"},
        ],
        "temperature": 0.1,
        "max_tokens": 60,
    }
    try:
        r = requests.post(NIM_URL, headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                          json=body, timeout=8)
        if r.status_code != 200:
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
    "너는 '드래곤쇼' 라이브 방송 운영 시스템의 AI 서포트 어시스턴트다.\n\n"
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
        "최근_후원": state.get("latest_donation"),
        "방송_목표금액": state.get("target_goal"),
        "대결": state.get("match_data"),
        "퇴근빵_켜짐": bool(state.get("home_race_enabled")),
        "퇴근빵_목표": state.get("home_goals"),
        "계좌": state.get("account"),
        "운영비": state.get("bottom_fixed"),
        "시그니처_신청집계": sig_tally_list,
        "시그니처_후원자_순위": sig_donor_rank,
        "목표연출_승인대기": bool(state.get("goal_event_pending")),
        "슬롯": {"켜짐": bool(state.get("slot_enabled")), "후보수": len(state.get("slot_pool") or [])},
        "룰렛": {"켜짐": bool(state.get("roulette_enabled")), "당첨자": roul.get("winner_name"), "돌리는중": bool(roul.get("is_spinning"))},
        "티커_문구": state.get("ticker_text"),
    }

def _ai_vip_list():
    """AI 스냅샷용 VIP(특별 후원자) 목록. 실패해도 빈 리스트."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("SELECT name, grade, badge FROM vip_donators ORDER BY name ASC"))
            return [{"이름": r[0], "등급": r[1], "뱃지": r[2]} for r in cur.fetchall()]
    except Exception:
        return []

def _supabase_ready():
    return bool(SUPABASE['url'] and SUPABASE['key'] and requests)

def _supabase_headers():
    return {'apikey': SUPABASE['key'], 'Authorization': f"Bearer {SUPABASE['key']}"}

def supabase_list_signatures():
    """전체 시그니처 목록 (금액 오름차순). 실패/미설정 시 빈 리스트."""
    if not _supabase_ready():
        return []
    url = (f"{SUPABASE['url']}/rest/v1/signatures"
           f"?select=id,amount,title,image_url,sound_url,duration&order=amount.asc")
    r = requests.get(url, headers=_supabase_headers(), timeout=10)
    r.raise_for_status()
    return r.json()

SIG_FIELDS = 'id,amount,title,image_url,sound_url,duration'

def _supabase_query(params, retries=1):
    """PostgREST GET 헬퍼. 결과 리스트 반환.
       후원 매칭은 방송 중 필수 경로라 일시적 네트워크 오류 시 1회 재시도한다."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            # 방송 중 후원 경로에서 쓰이므로 오래 기다리지 않는다.
            # 12초씩 두 번 기다리면 시그니처가 나올 때쯤엔 이미 방송 흐름이 지나가 있다.
            r = requests.get(f"{SUPABASE['url']}/rest/v1/signatures?{params}",
                             headers=_supabase_headers(), timeout=4)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt < retries:
                print(f"⚠️ [Supabase 조회 재시도] {e}")
                time.sleep(0.5)
    raise last_err

def supabase_match_signature(amount):
    """금액 매칭: ① 정확히 일치하거나, 없으면 올림(이상 중 가장 가까운)
       → ② 그래도 없으면(최고가 초과 후원) 가장 비싼 시그니처.

    ⚠️ 예전에는 '정확히 일치' 쿼리를 따로 먼저 보냈는데,
    아래 gte + 오름차순 + limit 1 이 정확히 일치하는 값을 이미 첫 번째로 돌려주므로
    같은 결과를 얻으려고 왕복을 한 번 더 쓴 셈이었다. (서울까지 왕복이라 비싸다)
    """
    if not _supabase_ready():
        return None
    amount = int(amount)
    rows = _supabase_query(f"amount=gte.{amount}&order=amount.asc&limit=1&select={SIG_FIELDS}")
    if rows:
        return rows[0]
    rows = _supabase_query(f"order=amount.desc&limit=1&select={SIG_FIELDS}")
    return rows[0] if rows else None

def supabase_get_signature(sig_id):
    """id로 시그니처 1개 조회."""
    if not _supabase_ready():
        return None
    rows = _supabase_query(f"id=eq.{int(sig_id)}&limit=1&select={SIG_FIELDS}")
    return rows[0] if rows else None

def supabase_insert_signature(fields):
    """시그니처 행 삽입 후 생성된 행(id 포함) 반환."""
    r = requests.post(f"{SUPABASE['url']}/rest/v1/signatures",
                      headers={**_supabase_headers(),
                               'Content-Type': 'application/json',
                               'Prefer': 'return=representation'},
                      json=fields, timeout=15)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None

def supabase_update_signature(sig_id, fields):
    r = requests.patch(f"{SUPABASE['url']}/rest/v1/signatures?id=eq.{int(sig_id)}",
                       headers={**_supabase_headers(),
                                'Content-Type': 'application/json',
                                'Prefer': 'return=representation'},
                       json=fields, timeout=15)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None

def supabase_delete_signature(sig_id):
    r = requests.delete(f"{SUPABASE['url']}/rest/v1/signatures?id=eq.{int(sig_id)}",
                        headers=_supabase_headers(), timeout=15)
    r.raise_for_status()
    return True

# ------- Supabase Storage (media 버킷) -------
STORAGE_BUCKET = 'media'

# 미디어 캐시 기간: 1년.
# Supabase 기본값은 1시간이라, 오버레이를 새로고침할 때마다 99개(약 70MB)를 다시 받아
# 무료 전송량 5GB를 금방 소진한다. 파일을 교체하면 URL 뒤에 ?v=타임스탬프가 새로 붙으므로
# 길게 캐시해도 변경은 즉시 반영된다.
MEDIA_CACHE_CONTROL = 'public, max-age=31536000, immutable'

def storage_upload(path, data, content_type):
    """Storage 업로드 후 공개 URL 반환."""
    r = requests.post(f"{SUPABASE['url']}/storage/v1/object/{STORAGE_BUCKET}/{path}",
                      data=data,
                      headers={**_supabase_headers(),
                               'Content-Type': content_type,
                               'Cache-Control': MEDIA_CACHE_CONTROL,
                               'x-upsert': 'true'},
                      timeout=120)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Storage 업로드 실패 {r.status_code}: {r.text[:200]}")
    return f"{SUPABASE['url']}/storage/v1/object/public/{STORAGE_BUCKET}/{path}"

def storage_delete_by_url(url):
    """공개 URL로부터 Storage 경로를 역산해 삭제 (실패는 무시)."""
    if not url:
        return
    marker = f"/storage/v1/object/public/{STORAGE_BUCKET}/"
    if marker not in url:
        return
    path = url.split(marker, 1)[1].split('?')[0]
    try:
        requests.delete(f"{SUPABASE['url']}/storage/v1/object/{STORAGE_BUCKET}/{path}",
                        headers=_supabase_headers(), timeout=30)
    except Exception as e:
        print(f"[Storage 삭제 무시] {e}")

def compress_image_to_webp(file_storage, max_dim=1280, quality=82):
    """업로드된 이미지를 WebP로 축소·압축. Pillow 없으면 원본 바이트 그대로."""
    raw = file_storage.read()
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        if im.mode in ('P', 'LA'):
            im = im.convert('RGBA')
        elif im.mode == 'CMYK':
            im = im.convert('RGB')
        w, h = im.size
        scale = min(1.0, max_dim / max(w, h))
        if scale < 1.0:
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format='WEBP', quality=quality, method=6)
        return buf.getvalue(), 'webp', 'image/webp'
    except Exception as e:
        print(f"[이미지 압축 실패 - 원본 사용] {e}")
        ext = (file_storage.filename or 'img.png').rsplit('.', 1)[-1].lower()
        return raw, ext, (file_storage.content_type or 'application/octet-stream')

# 오버레이가 안 돌고 있을 때 리액션 큐가 무한정 쌓이는 것을 막는 상한.
# 전체 큐가 매 update 마다 모든 클라이언트로 나가므로 메모리·트래픽에 직접 영향을 준다.
REACTION_QUEUE_MAX = 40


def _norm_donor(name):
    """후원자 표기 정규화. 같은 사람이 '홍길동' / '홍길동님' / ' 홍길동 ' 으로 갈라져
       집계가 쪼개지는 것을 막는다."""
    n = ' '.join(str(name or '').split())
    if n.endswith('님'):
        n = n[:-1].strip()
    return n or '익명'


def enqueue_signature(state, sig, amount, donator, message, skip_popup=False, count_tally=True):
    """시그니처를 리액션 큐에 추가 (모든 재생 경로가 이 함수를 공유).

    큐를 태우면 reaction_mode가 켜지고, 재생이 끝나 큐가 비면 자동으로 꺼진다.
    skip_popup: 슬롯 당첨처럼 이미 자체 연출을 보여준 경우 후원 팝업을 건너뛴다.
    count_tally: 시그니처 순위 집계에 셀지 여부. 실제 후원(자동/장부기록)만 True,
                 슬롯 당첨·재생전용 수동 송출은 False(집계 부풀림 방지).
    """
    reaction_uuid = f"rq_{uuid.uuid4().hex}"
    # ⚠️ 큐는 '오버레이가 재생해야만' 줄어든다. OBS 장면을 바꿔놨거나 오버레이를 닫아둔 채
    #    후원이 계속 들어오면 끝없이 쌓이고, 그 전체가 매 update 마다 모든 클라이언트에게 전송된다.
    #    게다가 오버레이가 다시 붙는 순간 밀린 것을 전부 연달아 재생해버린다.
    #    상한을 두고 가장 오래된 것부터 버린다(버린 사실은 로그로 남긴다).
    _queue = state.setdefault('reaction_queue', [])
    if len(_queue) >= REACTION_QUEUE_MAX:
        dropped = len(_queue) - REACTION_QUEUE_MAX + 1
        del _queue[:dropped]
        print(f"⚠️ [리액션 큐 상한] 밀린 시그니처 {dropped}건을 버렸습니다 (상한 {REACTION_QUEUE_MAX}건). "
              f"오버레이가 꺼져 있거나 재생이 멈춰 있는지 확인하세요.")
    _queue.append({
        "id": reaction_uuid,
        "item_id": sig.get('id'),
        "title": sig.get('title'),
        "audio_url": sig.get('sound_url') or "",
        "image_url": sig.get('image_url') or "",
        "duration": sig.get('duration') or 10,
        "amount": amount,
        "donator": donator,
        "message": message,
        "skip_popup": bool(skip_popup)
    })
    state['reaction_mode'] = True

    # 📊 시그니처별 신청 집계 (실제 후원만 센다 — 슬롯/재생전용 수동은 count_tally=False)
    if count_tally:
        try:
            key = str(sig.get('id'))
            tally = state.setdefault('sig_tally', {})
            row = tally.get(key) or {
                'title': sig.get('title'), 'image_url': sig.get('image_url') or '',
                'amount': sig.get('amount') or 0, 'count': 0
            }
            row['count'] = int(row.get('count') or 0) + 1
            row['title'] = sig.get('title') or row.get('title')
            row['image_url'] = sig.get('image_url') or row.get('image_url') or ''
            row['amount'] = sig.get('amount') or row.get('amount') or 0
            # 누가 몇 개 쐈는지도 같이 센다 ("3만원짜리 누가 몇 개 쐈어?" 에 답하려면 필요)
            # setdefault 인 이유: 이 기능 이전에 저장된 상태에는 donors 키가 없다.
            donors = row.setdefault('donors', {})
            who = _norm_donor(donator)
            donors[who] = int(donors.get(who) or 0) + 1
            tally[key] = row
        except Exception as e:
            print(f"⚠️ [시그니처 집계 실패] {e}")

    return reaction_uuid

# 🛡️ 내용 기반 후원 중복 방지 (tx_id 없는 재전송 대비)
# 투네이션이 같은 후원을 tx_id 없이 두 번 POST하면 시그니처가 두 번 재생되던 문제를 막는다.
# 이름+금액+메시지가 완전히 동일한 후원이 아주 짧은 시간(윈도우) 안에 또 오면 중복으로 간주한다.
# 서로 다른 사람이 같은 금액/메시지를 2.5초 안에 보낼 확률은 사실상 0이라 안전하다.
_recent_don_lock = threading.Lock()
_recent_don = {}
# ⚠️ 재시도 간격(3초/5초)보다 넉넉히 길어야 한다.
#    2.5초였을 때는 서버 응답이 느려 스크립트가 3초 뒤 재시도하면 창이 이미 닫혀 중복이 통과했다.
DONATION_DEDUPE_WINDOW = 12.0

def is_duplicate_donation(key):
    now = time.time()
    with _recent_don_lock:
        for k in list(_recent_don.keys()):
            if now - _recent_don[k] > DONATION_DEDUPE_WINDOW:
                del _recent_don[k]
        if key in _recent_don:
            return True
        _recent_don[key] = now
        return False

# 슬롯 릴 정지 + 당첨 배너(약 3.3초) 뒤 결과 처리까지의 대기 시간
SLOT_RESULT_DELAY_SEC = 4.0

def _slot_finish(winner):
    """슬롯 당첨 확정 처리: 슬롯 위젯을 끄고 당첨 시그니처를 리액션 큐에 넣는다."""
    try:
        title = winner.get('title') or '시그니처'
        with file_lock:
            state = load_data()
            state['slot_enabled'] = False
            enqueue_signature(state, winner, winner.get('amount') or 0,
                              '🎰 슬롯머신', f'[슬롯 당첨] {title}', skip_popup=True, count_tally=False)
            save_data(state)
            broadcast_event('update', state)
        print(f"  🎰 [슬롯 당첨 처리] '{title}' → 슬롯 위젯 OFF, 리액션 큐 투입")
    except Exception as e:
        print(f"❌ [슬롯 당첨 처리 실패] {e}")

# ==========================================
# 🤫 서버 로그 제어
# ==========================================
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
log.disabled = True 

app = Flask(__name__)
app.secret_key = load_auth_config()['session_secret']
CORS(app)
file_lock = threading.Lock()

# 🚫 [강력 차단] 웹 브라우저 및 OBS CEF 캐싱 방지 헤더 이식
@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r

# 🔒 [보안 통제] 웹 제어실 및 중요 API 접근 제한 미들웨어
@app.before_request
def require_login():
    path = request.path
    
    # 정적 자원 파일 프리패스
    if (path.endswith('.css') or path.endswith('.js') or path.endswith('.png') or 
        path.endswith('.jpg') or path.endswith('.ico') or path.endswith('.woff') or 
        path.endswith('.woff2') or path.endswith('.ttf') or path.endswith('.svg')):
        return
        
    # 세션 검증 예외 경로 리스트
    exempt_routes = [
        '/login',
        '/logout',
        '/',
        '/overlay',
        '/overlay.html',
        '/alertbox',
        '/alertbox.html',
        '/api/stream',
        '/api/ping',
        '/api/donation',
        '/api/streamdeck/neon',
        '/api/streamdeck/save',
        '/api/roulette/winner',
        '/api/match/timeup',
        '/api/signatures',
        '/api/reaction/next',
        '/api/reaction/list',
        '/toonation_tampermonkey.user.js',
        '/setup'
    ]
    
    # 메서드까지 봐야 하는 예외: 조회는 오버레이가 써야 해서 공개, 변경은 로그인 필요.
    # (경로만으로 예외를 주면 POST/DELETE까지 무인증으로 열려버린다)
    method_exempt = {
        '/api/vips': ('GET',),
        # 오버레이·알림창은 로그인 세션이 없으므로 조회는 열어둬야 한다.
        # 반면 POST 는 상태를 통째로 덮어쓰는 요청이라 반드시 인증이 필요하다.
        # (예전에는 경로만으로 예외를 줘서, URL 만 알면 누구나 점수를 지우거나
        #  전광판에 아무 문구나 띄울 수 있었다. 오버레이가 쓰던 유일한 POST 용도인
        #  '대결 타이머 종료'는 /api/match/timeup 이라는 좁은 전용 엔드포인트로 옮겼다)
        '/api/data': ('GET',),
    }
    if path in method_exempt and request.method in method_exempt[path]:
        return

    # 시그니처 등록(/upload, /노래등록)은 관리 기능이므로 로그인 필요로 변경했다.
    # (등록 API가 /api/signatures/add 로 바뀌면서 인증이 필요해졌기 때문)
    if (path in exempt_routes or
        path.startswith('/uploads/')):
        return
         
    # HTTP Authorization Bearer 토큰 및 ?token= 파라미터 검증 지원
    auth_header = request.headers.get('Authorization')
    token = None
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
    else:
        token = request.args.get('token')
        
    is_token_valid = (token and token == load_auth_config()['session_secret'])
        
    # 비인증 사용자 제약
    if not session.get('authenticated') and not is_token_valid:
        if path.startswith('/api/'):
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        if request.query_string:
            return redirect(url_for('serve_login') + '?' + request.query_string.decode('utf-8'))
        return redirect(url_for('serve_login'))

# 📡 실시간 SSE 클라이언트 관리 시스템
sse_clients = []
sse_lock = threading.Lock()
# 클라이언트 1대가 밀렸을 때 쌓아둘 최대 메시지 수.
# state 전체가 실리므로(수십 KB) 이 값이 곧 '밀린 클라 1대당 최대 메모리'다.
SSE_QUEUE_MAX = 120

def broadcast_event(event_name, data):
    if isinstance(data, dict):
        data = data.copy()
        # 🔐 /api/stream 은 무인증으로 열려 있다(오버레이·알림창이 붙어야 하므로).
        #    상태에 관리자 토큰이 섞여 있어도 절대 전파되지 않게 마지막 관문에서 지운다.
        data.pop('api_token', None)
        data['server_time'] = int(time.time() * 1000)
    with sse_lock:
        message = f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for client_q in sse_clients:
            try:
                client_q.put_nowait(message)
            except queue.Full:
                # 밀린 클라이언트(느린 네트워크·멈춘 OBS): 가장 오래된 것을 버리고 최신을 넣는다.
                # update 는 state 전체를 싣고 다니므로 중간 것을 버려도 최신 상태는 그대로 도착한다.
                # 버리지 않고 쌓아두면 그 클라이언트 큐가 서버 메모리를 계속 먹는다.
                try:
                    client_q.get_nowait()
                    client_q.put_nowait(message)
                except Exception:
                    pass

def get_or_create_totp_secret():
    return load_auth_config()['totp_secret']

def serve_html_file(filename):
    local_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(local_path):
        return send_from_directory(BASE_DIR, filename)
    return send_from_directory(BUNDLE_DIR, filename)

DEFAULT_STATE = {
    "bjs": [],
    "bottom_fixed": {"name": "운영비", "score": 0},
    "target_goal": 50000,
    "theme": "default",
    "reaction_mode": False,
    "reaction_queue": [],
    "reaction_volume": 0.5,
    # 🎬 시그니처 리액션 위젯 크기/위치/축소타이밍 (admin 에디터에서 조절, DEFAULT_STATE에 없으면 재시작 시 소실)
    "reaction_big_scale": 1.0,     # 처음 크게 보일 때 배율
    "reaction_small_scale": 0.6,   # 줄어든 뒤 배율
    "reaction_min_x": 180,         # 줄어든 뒤 위치 X(뷰포트 px, 중심 기준)
    "reaction_min_y": 600,         # 줄어든 뒤 위치 Y(뷰포트 px, 중심 기준)
    "reaction_shrink_delay": 2500, # 크게 보였다가 줄어들기까지(ms)
    # 🔥 시그니처 이름 대형 네온 배너 (화면 정중앙)
    "reaction_title_enabled": True,
    "reaction_title_size": 150,     # 글자 크기(px)
    "reaction_title_duration": 3500,# 노출 시간(ms)
    "reaction_title_suffix": "업",  # 후원자 이름 뒤에 붙는 말 ("홍길동" → "홍길동업")
    # 📊 시그니처 신청 집계 패널 (이번 방송에 어떤 시그니처가 몇 번 신청됐는지)
    "sig_tally_enabled": False,     # 기본 꺼짐 — 켜야 방송 화면에 뜬다
    "sig_tally_limit": 6,           # 화면에 표시할 개수
    "sig_tally": {},                # {item_id: {title, image_url, amount, count}} — 방송마다 초기화
    "popup_enabled": True,
    "takeover_enabled": True,
    "ticker_enabled": True,
    "ticker_speed": 70,
    "ticker_text": "📢 환영합니다! 후원은 방송에 큰 힘이 됩니다!",
    "match_data": {"active": False, "players": [], "time_left_ms": 180000, "is_running": False},
    "account": {"bank": "기업은행", "acc_num": "464-068673-04-016", "name": "드래곤엔터"},
    "pending_donations": [],
    "latest_donation": {"name": "", "amount": 0, "message": "", "time": 0},
    "extra_game_active": False,
    "extra_bjs": [],
    "roulette_enabled": False,
    # 🎤 노래방 모드: 붙여넣은 유튜브(inst) 영상을 오버레이 화면에 띄운다
    "karaoke_enabled": False,
    "karaoke_video": "",     # 유튜브 영상 ID
    # 🎰 슬롯머신
    # load_data()는 DEFAULT_STATE에 있는 키만 복원하므로, 여기 없으면 재시작 때 조용히 사라진다.
    "slot_enabled": True,
    "slot_pool": [],   # 이번 방송에 쓸 시그니처 id 목록. 비어 있으면 전체를 후보로 사용.
    # 🎯 목표 100% 달성 연출 (달성하면 pending, 운영자가 승인해야 송출)
    "goal_event_pending": False,
    "goal_event_approved": False,
    # 🏃 퇴근전쟁(퇴근빵): 켜면 랭킹판 자리에 개인별 목표 진행바가 뜬다
    "home_race_enabled": False,
    "home_goals": {},         # {플레이어 이름: 퇴근 목표 점수}
    "home_race_notified": [], # 이미 퇴근 카드를 띄운 사람 (송출 후 다시 생기는 것 방지)
    "logs": [],               # 점수/기여도 지급 로그 [{time, name, val}] — DEFAULT_STATE에 있어야 재로드 시 유지된다
    "match_logs": [],         # 대결(임시게임) 전용 지급 로그. logs 와 같은 이유로 여기 있어야 살아남는다
    "neon_speed": 1.5,        # 조명 속도 슬라이더(초). 방송 종료 시 보존 대상 목록에도 들어 있는 '설정값'이다
    "effect_trigger": None,   # 조명 상태 {time, color, infinite}. 일회성 연출이 아니라 '켜 둔 상태'라 유지해야 한다
    "broadcast_active": False,
    "saved_colors": ['#ff0055', '#00e5ff', '#ff9100', '#d500f9', '#00ff00', '#ffff00', '#ff0000', '#0000ff', '#ffffff'],
    "version": 1,
    "roulette": {
        "command": None,
        "command_time": 0,
        "weight_type": "equal",
        "select_name": "",
        "select_index": -1,
        "winner_name": None,
        "is_spinning": False,
        "item_source": "bj",
        "custom_items": ["벌칙 1", "벌칙 2", "벌칙 3", "벌칙 4", "벌칙 5"]
    }
}

MEMORY_STATE = None

# ==========================================
# 🗄️ 데이터베이스 핵심 로직
# ==========================================
def init_db():
    if not IS_POSTGRES:
        if not os.path.exists(DB_FILE) and os.path.exists(DB_FILE + '.bak'):
            try:
                shutil.copy2(DB_FILE + '.bak', DB_FILE)
                print("[DB 자동 복구] 백업 본으로 DB 복구 성공!")
            except Exception as e:
                print(f"[DB 자동 복구 실패] {e}")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        if not IS_POSTGRES:
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
        
        cursor.execute("CREATE TABLE IF NOT EXISTS kv_store (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS players (name TEXT PRIMARY KEY, score INTEGER, contribution INTEGER)")
        
        if IS_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS donation_history (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT,
                    name TEXT,
                    amount INTEGER,
                    current_total INTEGER, 
                    message TEXT,
                    source TEXT,
                    tx_id TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT,
                    state_json TEXT,
                    summary TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reaction_files (
                    id VARCHAR(64) PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type VARCHAR(128) NOT NULL,
                    file_data BYTEA NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reaction_items (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    amount INTEGER DEFAULT 0,
                    audio_file_id VARCHAR(64),
                    image_file_id VARCHAR(64),
                    is_enabled BOOLEAN DEFAULT TRUE
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS donation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    name TEXT,
                    amount INTEGER,
                    current_total INTEGER, 
                    message TEXT,
                    source TEXT,
                    tx_id TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    state_json TEXT,
                    summary TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reaction_files (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    file_data BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reaction_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    amount INTEGER DEFAULT 0,
                    audio_file_id TEXT,
                    image_file_id TEXT,
                    is_enabled INTEGER DEFAULT 1
                )
            """)
        
        # 아래 신규 테이블들이 공통으로 쓰는 자동증가 기본키 표현
        pk = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

        # 🏦 [은행 원장] 점수/기여도 변동을 통장처럼 한 줄씩 남긴다.
        # 절대값을 덮어쓰는 대신 "변동분 + 거래 후 잔액"을 쌓아두므로,
        # 잔액이 어긋나면 원장을 다시 합산해 복구할 수 있다. (append-only)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS bank_ledger (
                id {pk},
                timestamp TEXT NOT NULL,
                player_name TEXT NOT NULL,
                tx_type TEXT NOT NULL,
                score_change INTEGER NOT NULL,
                score_balance INTEGER NOT NULL,
                contrib_change INTEGER NOT NULL,
                contrib_balance INTEGER NOT NULL,
                description TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_ledger_player ON bank_ledger(player_name)")

        # 👑 [특별 후원자(VIP)] 닉네임별 등급/색상/뱃지. 방송 데이터와 무관하게 계속 유지된다.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vip_donators (
                name TEXT PRIMARY KEY,
                grade TEXT NOT NULL,
                custom_color TEXT DEFAULT '#ffd700',
                badge TEXT DEFAULT '👑'
            )
        """)

        # 📚 [영구 보관 장부] 방송 종료 시 donation_history는 초기화되지만,
        # 여기로 먼저 복사해 두므로 지난 방송 기록이 영구히 남는다. (append-only, 절대 삭제하지 않음)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS donation_archive (
                id {pk},
                archived_at TEXT,
                session_label TEXT,
                timestamp TEXT,
                name TEXT,
                amount INTEGER,
                current_total INTEGER,
                message TEXT,
                source TEXT,
                tx_id TEXT
            )
        """)

    # 💡 [스키마 마이그레이션 패치] 기존 테이블에 컬럼 동적 추가
    # ⚠️ Postgres는 트랜잭션 안에서 한 문장이 실패하면 그 트랜잭션 전체가 취소된다.
    # 예전처럼 위 CREATE TABLE들과 같은 트랜잭션에서 ALTER를 시도하면,
    # "컬럼이 이미 존재" 오류 하나 때문에 앞서 만든 테이블이 전부 롤백되어
    # 빈 DB에서는 테이블이 하나도 생기지 않는다. (SQLite에서는 발생하지 않아 발견이 늦었다)
    # 따라서 ALTER는 각각 별도 연결(트랜잭션)에서 실행한다.
    for stmt in ("ALTER TABLE snapshots ADD COLUMN summary TEXT",
                 "ALTER TABLE donation_history ADD COLUMN tx_id TEXT"):
        try:
            with get_db_connection() as conn2:
                conn2.cursor().execute(stmt)
        except Exception:
            pass  # 이미 존재하면 정상적으로 무시

def load_data():
    global MEMORY_STATE, LAST_PERSISTED
    if MEMORY_STATE is not None:
        return MEMORY_STATE
    init_db()

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT key, value FROM kv_store"))
            kv_data = {row[0]: json.loads(row[1]) for row in cursor.fetchall()}
            cursor.execute(db_query("SELECT name, score, contribution FROM players ORDER BY contribution DESC"))
            bjs = [{"name": row[0], "score": row[1], "contribution": row[2]} for row in cursor.fetchall()]
    except Exception as e:
        print(f"⚠️ [DB 로드 오류] {e}")
        # DB 로드 실패 시 데이터를 덮어써서 날려버리는 것을 막기 위해 예외를 상위로 전파합니다.
        raise e

    if not kv_data and not bjs:
        # ⚠️ 반드시 깊은 복사. 얕은 복사면 중첩 객체(bjs/account/pending_donations 등)가
        # DEFAULT_STATE와 공유되어, 이후 append/수정이 기본값 자체를 오염시킨다.
        MEMORY_STATE = copy.deepcopy(DEFAULT_STATE)
        save_data(MEMORY_STATE, is_initial=True, sync=True)
        return MEMORY_STATE

    state = {}
    for key, default_val in DEFAULT_STATE.items():
        if key == "bjs": 
            state["bjs"] = bjs
        elif key in kv_data: 
            state[key] = kv_data[key]
        else: 
            state[key] = default_val
            
    # saved_colors 보정 (6개 -> 9개로 확장 및 하위 호환 마이그레이션)
    default_colors = ['#ff0055', '#00e5ff', '#ff9100', '#d500f9', '#00ff00', '#ffff00', '#ff0000', '#0000ff', '#ffffff']
    if 'saved_colors' in state:
        if not isinstance(state['saved_colors'], list):
            state['saved_colors'] = default_colors
        elif len(state['saved_colors']) < 9:
            for i in range(len(state['saved_colors']), 9):
                state['saved_colors'].append(default_colors[i])
    else:
        state['saved_colors'] = default_colors
    
    MEMORY_STATE = state
    # DB에서 막 읽어온 값이 곧 "DB에 저장된 내용"이므로 비교 기준을 여기에 맞춘다.
    # (초기화하지 않으면 첫 저장 때 모든 점수가 '수동 점수 조작'으로 장부에 잘못 기록된다)
    LAST_PERSISTED = copy.deepcopy(state)
    return MEMORY_STATE

db_write_queue = queue.Queue()

# 마지막 DB 저장 실패 정보 (조용한 실패 방지 — /api/server/status 로 노출)
LAST_DB_ERROR = {"message": None, "time": None}

# 마지막으로 DB에 성공적으로 기록한 상태의 깊은 복사본.
# 변경분만 저장하기 위한 비교 기준이며, MEMORY_STATE와 별개여야 한다.
LAST_PERSISTED = None

def db_worker():
    while True:
        done = None
        try:
            new_data, is_initial, done = db_write_queue.get()
            if new_data is not None:          # None 은 '여기까지 처리됐다'를 알리는 표식(drain_db_writes)
                save_data_sync(new_data, is_initial)
            db_write_queue.task_done()
        except Exception as e:
            print(f"❌ [비동기 DB 저장 백그라운드 오류] {e}")
            time.sleep(1)
        finally:
            # 동기 저장을 기다리는 쪽이 영원히 멈추지 않도록 실패해도 반드시 깨운다
            if done is not None:
                done.set()

threading.Thread(target=db_worker, daemon=True).start()

def save_data_sync(new_data, is_initial=False, _retry=True):
    global LAST_PERSISTED
    # ⚠️ 반드시 "마지막으로 DB에 쓴 내용"과 비교해야 한다.
    # 예전에는 MEMORY_STATE와 비교했는데, 호출부가 load_data()가 돌려준 객체를
    # 그 자리에서 수정하므로 MEMORY_STATE와 new_data가 같은 객체가 되어
    # "변경된 키 없음"으로 판정 → kv_store에 아무것도 저장되지 않았다.
    # (플레이어 테이블은 매번 통째로 다시 쓰기 때문에 이 문제가 드러나지 않았다)
    old_data = LAST_PERSISTED if LAST_PERSISTED is not None else DEFAULT_STATE

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 점수/기여도 변동을 장부 + 은행 원장에 기록 (영수증 발급)
            if not is_initial:
                old_scores = {p["name"]: p.get("score", 0) for p in old_data.get("bjs", [])}
                old_contribs = {p["name"]: p.get("contribution", 0) for p in old_data.get("bjs", [])}
                now_str = time.strftime('%Y-%m-%d %H:%M:%S')
                hist_rows, ledger_rows = [], []
                for new_p in new_data.get("bjs", []):
                    p_name = new_p["name"]
                    p_score = int(new_p.get("score") or 0)
                    p_contrib = int(new_p.get("contribution") or 0)
                    score_diff = p_score - old_scores.get(p_name, 0)
                    contrib_diff = p_contrib - old_contribs.get(p_name, 0)

                    if score_diff != 0:
                        hist_rows.append((now_str, p_name, score_diff, p_score, "수동 점수 조작", "mobile"))
                    # 🏦 은행 원장: 변동분과 거래 후 잔액을 남겨 나중에 재정산할 수 있게 한다
                    if score_diff != 0 or contrib_diff != 0:
                        ledger_rows.append((now_str, p_name, "MANUAL_CHANGE", score_diff, p_score,
                                            contrib_diff, p_contrib,
                                            f"점수 {score_diff:+} / 기여도 {contrib_diff:+}"))

                # N분할처럼 여러 명이 한꺼번에 바뀔 때 왕복이 인원수만큼 늘지 않도록 묶어서 넣는다
                if hist_rows:
                    ph = ', '.join([('(%s, %s, %s, %s, %s, %s)' if IS_POSTGRES else '(?, ?, ?, ?, ?, ?)')] * len(hist_rows))
                    cursor.execute(
                        f"INSERT INTO donation_history (timestamp, name, amount, current_total, message, source) VALUES {ph}",
                        [v for r in hist_rows for v in r]
                    )
                if ledger_rows:
                    ph = ', '.join([('(%s, %s, %s, %s, %s, %s, %s, %s)' if IS_POSTGRES else '(?, ?, ?, ?, ?, ?, ?, ?)')] * len(ledger_rows))
                    cursor.execute(
                        f"""INSERT INTO bank_ledger
                            (timestamp, player_name, tx_type, score_change, score_balance,
                             contrib_change, contrib_balance, description) VALUES {ph}""",
                        [v for r in ledger_rows for v in r]
                    )

            # 2. 플레이어 테이블 갱신
            # ⚠️ 예전에는 DELETE 전체 후 재INSERT였다. 이제는 사라진 플레이어만 지우고
            #    나머지는 UPSERT한다 (원장과 잔액을 함께 다루므로 통째로 지우면 위험하다)
            new_bjs = new_data.get("bjs", [])
            valid_names = [bj["name"] for bj in new_bjs if bj.get("name")]
            if valid_names:
                if IS_POSTGRES:
                    cursor.execute("DELETE FROM players WHERE NOT (name = ANY(%s))", (valid_names,))
                else:
                    placeholders = ', '.join(['?'] * len(valid_names))
                    cursor.execute(f"DELETE FROM players WHERE name NOT IN ({placeholders})", valid_names)
            else:
                cursor.execute(db_query("DELETE FROM players"))

            # ⚡ 플레이어를 한 명씩 저장하면 인원수만큼 왕복이 생긴다.
            #    한 문장에 여러 행을 담아 왕복을 1회로 줄인다.
            if new_bjs:
                rows = [(bj["name"], bj.get("score", 0), bj.get("contribution", 0)) for bj in new_bjs]
                if IS_POSTGRES:
                    ph = ', '.join(['(%s, %s, %s)'] * len(rows))
                    cursor.execute(
                        f"INSERT INTO players (name, score, contribution) VALUES {ph} "
                        "ON CONFLICT (name) DO UPDATE SET score = EXCLUDED.score, contribution = EXCLUDED.contribution",
                        [v for r in rows for v in r]
                    )
                else:
                    ph = ', '.join(['(?, ?, ?)'] * len(rows))
                    cursor.execute(
                        f"INSERT INTO players (name, score, contribution) VALUES {ph} "
                        "ON CONFLICT(name) DO UPDATE SET score = excluded.score, contribution = excluded.contribution",
                        [v for r in rows for v in r]
                    )

            # 3. 설정 상태 키-값 저장 (변경된 값만) — 이것도 한 문장으로 묶어 왕복을 줄인다
            kv_rows = []
            for key, value in new_data.items():
                if key == "bjs":
                    continue
                new_val_str = json.dumps(value, ensure_ascii=False)
                old_val = old_data.get(key)
                old_val_str = json.dumps(old_val, ensure_ascii=False) if old_val is not None else None
                if is_initial or old_val_str != new_val_str:
                    kv_rows.append((key, new_val_str))

            if kv_rows:
                if IS_POSTGRES:
                    ph = ', '.join(['(%s, %s)'] * len(kv_rows))
                    cursor.execute(
                        f"INSERT INTO kv_store (key, value) VALUES {ph} "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                        [v for r in kv_rows for v in r]
                    )
                else:
                    ph = ', '.join(['(?, ?)'] * len(kv_rows))
                    cursor.execute(
                        f"INSERT OR REPLACE INTO kv_store (key, value) VALUES {ph}",
                        [v for r in kv_rows for v in r]
                    )
                            
        # 커밋 성공 후에만 비교 기준을 갱신한다 (실패 시 다음 저장에서 다시 시도되도록)
        LAST_PERSISTED = new_data
        LAST_DB_ERROR["message"] = None
    except Exception as e:
        # 재사용하던 연결을 서버가 끊어둔 경우일 수 있다.
        # get_db_connection이 이미 죽은 연결을 버렸으므로, 한 번만 새 연결로 다시 시도한다.
        if _retry:
            print(f"⚠️ [DB 저장 재시도] {e}")
            return save_data_sync(new_data, is_initial, _retry=False)
        # 조용히 넘어가면 저장된 줄 알고 방송을 계속하게 된다. 상태에 남겨 컨트롤러가 경고할 수 있게 한다.
        LAST_DB_ERROR["message"] = str(e)
        LAST_DB_ERROR["time"] = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"❌ [DB 저장 실패] {e}")
        raise

def reset_session_keys(state):
    """방송 1회분에만 유효한 상태를 초기화한다.

    ⚠️ 새 기능을 넣을 때 여기에 등록하지 않으면, 서버를 끄지 않고 방송을 두 번 할 때
    지난 방송의 흔적이 남아 오작동한다. (예: goal_event_approved 가 남아 2회차에는
    목표 달성 배너가 영영 안 뜨고, home_race_notified 에 남은 이름은 퇴근 카드를 못 받는다)
    """
    state['goal_event_pending'] = False
    state['goal_event_approved'] = False
    state['home_race_notified'] = []   # '누가 이미 퇴근 카드를 받았나'는 지난 방송의 기록이라 비운다
    state['sig_tally'] = {}            # 시그니처 신청 집계도 방송 1회분 기록이라 비운다
    # ⚠️ home_goals(퇴근빵 개인별 목표)는 여기서 지우면 안 된다.
    #    이건 '지난 방송의 흔적'이 아니라 운영자가 방송 전에 세팅해두는 '설정'이다.
    #    그런데 이 함수는 방송 종료뿐 아니라 '방송 시작'에서도 불린다.
    #    그래서 목표를 다 입력하고 시작 버튼을 누르는 순간 전부 지워졌고,
    #    퇴근빵 게이지는 목표 0 → 진행률 0% → 바가 안 차고 '남은 금액'도 0으로 보였다.
    #    (같은 이유로 방송 목표금액 target_goal 도 보존 대상 목록에 들어가 있다)
    return state

def create_snapshot(state, label):
    """복구 지점 저장 (append-only). 실패해도 방송은 계속되어야 하므로 예외를 삼킨다."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                db_query("INSERT INTO snapshots (timestamp, state_json, summary) VALUES (?, ?, ?)"),
                (time.strftime('%Y-%m-%d %H:%M:%S'), json.dumps(state, ensure_ascii=False), label)
            )
        print(f"  💾 [스냅샷 저장] {label}")
        return True
    except Exception as e:
        print(f"⚠️ [스냅샷 저장 실패] {e}")
        return False

def drain_db_writes(timeout=30):
    """큐에 밀려 있는 DB 쓰기가 전부 끝날 때까지 기다린다.

    ⚠️ 복구·재정산처럼 'DB를 진실로 삼아 메모리를 다시 읽는' 작업 직전에 반드시 호출해야 한다.
       안 그러면 복구가 끝난 뒤에 워커가 '복구 전에 큐잉된 낡은 스냅샷'을 뒤늦게 써버려
       복구를 통째로 되돌린다. 게다가 LAST_PERSISTED 까지 낡은 값이 되어, 다음 저장이
       그 낡은 값과의 차이를 '수동 변경'으로 오해하고 엉뚱한 장부 줄을 남긴다.
       (task_done 기반 join() 은 쓰기가 한 번이라도 실패하면 영영 안 끝나므로 쓰지 않는다)
    """
    ev = threading.Event()
    db_write_queue.put((None, False, ev))
    if not ev.wait(timeout=timeout):
        print("⚠️ [DB 쓰기 큐 비우기 시간 초과] 낡은 저장이 뒤늦게 반영될 수 있습니다.")


def save_data(new_data, is_initial=False, sync=False, wait=True):
    """상태 저장.

    sync=True: 후원 접수·점수 변경·방송 시작/종료처럼 잃으면 안 되는 기록은
               응답을 돌려주기 전에 DB에 직접 쓴다.
               (비동기 큐에만 넣으면 프로세스가 죽을 때 마지막 쓰기가 사라진다)
    sync=False: 슬라이더·전광판 문구 같은 잦은 UI 갱신은 기존대로 백그라운드 처리.
    """
    global MEMORY_STATE
    # 메모리 캐시는 즉시 최신화하여 조종실과 오버레이에 0ms로 반영
    MEMORY_STATE = new_data
    # ⚠️ 큐에 넣는 것은 스냅샷(깊은 복사)이어야 한다.
    # 같은 객체를 넘기면 워커가 순회하는 동안 요청 스레드가 계속 수정해 저장 내용이 섞인다.
    snapshot = copy.deepcopy(new_data)

    # ⚠️ 동기 저장도 반드시 같은 큐를 통과해야 한다.
    # 예전에는 sync=True가 큐를 건너뛰고 바로 썼는데, 그러면 먼저 대기 중이던
    # 오래된 비동기 스냅샷이 나중에 처리되면서 방금 저장한 최신 값(예: 후원 기록)을
    # 도로 덮어썼다. 큐를 거치면 순서가 보장되고, LAST_PERSISTED도 워커 스레드
    # 한 곳에서만 갱신되어 경합이 사라진다.
    done = threading.Event() if sync else None
    db_write_queue.put((snapshot, is_initial, done))
    if done is not None and wait:
        # 워커가 밀려 있어도 방송이 멈추지 않도록 상한을 둔다 (실패는 LAST_DB_ERROR에 남음)
        if not done.wait(timeout=30):
            print("⚠️ [동기 저장 시간 초과] 백그라운드에서 계속 진행됩니다.")
    # wait=False 로 부른 쪽은 이 이벤트를 받아 '락을 놓은 뒤' 기다릴 수 있다.
    return done

def time_machine_recovery():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("DELETE FROM players"))
            cursor.execute(db_query("""
                INSERT INTO players (name, score, contribution)
                SELECT name, current_total, current_total 
                FROM donation_history 
                WHERE id IN (
                    SELECT MAX(id) FROM donation_history GROUP BY name
                )
            """))
            
        global MEMORY_STATE
        drain_db_writes()   # 복구 직후 낡은 스냅샷이 덮어쓰지 않도록 먼저 큐를 비운다
        MEMORY_STATE = None
        load_data()
        return True
    except Exception as e:
        print(f"❌ [복구 실패] {e}")
        return False

# ==========================================
# 📡 실시간 SSE 라우트 및 제네레이터
# ==========================================
@app.route('/api/stream')
def sse_stream():
    # ⚠️ maxsize 를 반드시 준다. 무제한이면 끊기거나 멈춘 클라이언트의 큐에 update 가
    #    무한정 쌓여 서버 메모리를 계속 먹는다(부하 테스트: 60대 재접속만으로 +53MB).
    q = queue.Queue(maxsize=SSE_QUEUE_MAX)
    with sse_lock:
        sse_clients.append(q)

    def event_generator():
        try:
            initial_state = load_data()
            yield f"event: init\ndata: {json.dumps(initial_state, ensure_ascii=False)}\n\n"

            if os.path.exists(LAYOUT_FILE):
                try:
                    with open(LAYOUT_FILE, 'r', encoding='utf-8') as f:
                        layout_data = json.load(f)
                    yield f"event: layout\ndata: {json.dumps(layout_data, ensure_ascii=False)}\n\n"
                except Exception:
                    pass

            while True:
                try:
                    msg = q.get(timeout=15.0)
                except queue.Empty:
                    msg = "event: ping\ndata: {}\n\n"   # 무음 15초마다 연결 유지 신호
                yield msg
        finally:
            # ⚠️ 반드시 finally 여야 한다.
            #    예전에는 while 을 정상적으로 빠져나올 때만 정리했는데, ping 은 `except queue.Empty:`
            #    블록 '안에서' yield 하고 있어서 하필 그 순간 클라이언트가 끊기면
            #    GeneratorExit 가 except 를 지나쳐 밖으로 튀고 정리가 통째로 건너뛰어졌다.
            #    그러면 죽은 큐가 sse_clients 에 남아 이후 모든 broadcast 를 계속 받아 쌓았다.
            with sse_lock:
                if q in sse_clients:
                    sse_clients.remove(q)
                
    response = app.response_class(event_generator(), mimetype='text/event-stream')
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    return response

@app.route('/api/ping')
def api_ping():
    return jsonify({'status': 'pong'})

# 🟢 시그니처 목록 (Supabase 대리 조회) — 오버레이/컨트롤러/슬롯이 공통으로 사용
@app.route('/api/signatures')
def api_signatures():
    try:
        sigs = supabase_list_signatures()
        return jsonify({'status': 'success', 'signatures': sigs, 'count': len(sigs)})
    except Exception as e:
        print(f"[시그니처 목록 조회 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e), 'signatures': []}), 500

@app.route('/api/donation/ranking')
def api_donation_ranking():
    """현재 방송의 누적 후원 순위(이름별 합계·건수).
       donation_history는 방송 시작/종료 때 초기화되므로 자연히 '이번 방송' 집계가 된다."""
    try:
        rows = []
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, SUM(amount) AS total, COUNT(*) AS cnt, MAX(id) AS last_id
                FROM donation_history
                GROUP BY name
                ORDER BY total DESC, last_id DESC
            """)
            for r in cursor.fetchall():
                rows.append({'name': r[0], 'total': int(r[1] or 0), 'count': int(r[2] or 0)})
        return jsonify({'status': 'success', 'ranking': rows, 'count': len(rows)})
    except Exception as e:
        print(f"[후원 순위 조회 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e), 'ranking': []}), 500

# ==========================================
# 🎵 시그니처 관리 (등록 / 수정 / 삭제) — 로그인 필요 (exempt 목록에 없음)
# ==========================================
def _save_signature_files(sig_id, image_file, sound_file):
    """업로드된 파일을 Storage에 올리고 {image_url, sound_url} 조각 반환.

    ⚠️ 파일 경로는 id 기준으로 고정이라 교체 시 URL이 같아진다.
    그러면 Supabase CDN 캐시 때문에 방송 화면에 '옛 사진/옛 음원'이 최대 1시간 계속 나온다.
    저장하는 URL 끝에 버전(?v=타임스탬프)을 붙여 교체 즉시 반영되게 한다.
    """
    ver = int(time.time())
    out = {}
    if image_file and image_file.filename:
        data, ext, ctype = compress_image_to_webp(image_file)
        out['image_url'] = storage_upload(f"images/{sig_id}.{ext}", data, ctype) + f"?v={ver}"
    if sound_file and sound_file.filename:
        ext = (sound_file.filename.rsplit('.', 1)[-1] or 'mp3').lower()
        # 클라이언트가 보낸 content_type은 신뢰하지 않고 확장자로 결정한다.
        # (octet-stream으로 올라가면 일부 브라우저에서 오디오 재생이 실패함)
        AUDIO_TYPES = {'mp3': 'audio/mpeg', 'm4a': 'audio/mp4', 'aac': 'audio/aac',
                       'ogg': 'audio/ogg', 'wav': 'audio/wav', 'webm': 'audio/webm',
                       'mp4': 'video/mp4'}
        ctype = AUDIO_TYPES.get(ext)
        if not ctype:
            ctype = sound_file.content_type or 'application/octet-stream'
        out['sound_url'] = storage_upload(f"sounds/{sig_id}.{ext}", sound_file.read(), ctype) + f"?v={ver}"
    return out

@app.route('/api/signatures/add', methods=['POST'])
def api_signature_add():
    try:
        if not _supabase_ready():
            return jsonify({'status': 'error', 'message': 'Supabase가 설정되지 않았습니다.'}), 500

        amount = int(request.form.get('amount') or 0)
        title = (request.form.get('title') or '').strip() or f"{amount:,}원 시그니처"
        duration = int(request.form.get('duration') or 10)
        if amount <= 0:
            return jsonify({'status': 'error', 'message': '후원 금액을 입력해주세요.'}), 400

        # 1) 행 먼저 삽입해서 id 확보 (파일 경로에 id를 쓰기 때문)
        row = supabase_insert_signature({'amount': amount, 'title': title, 'duration': duration})
        if not row:
            return jsonify({'status': 'error', 'message': '시그니처 생성에 실패했습니다.'}), 500
        sig_id = row['id']

        # 2) 파일 업로드 후 URL 반영
        urls = _save_signature_files(sig_id, request.files.get('image'), request.files.get('sound'))
        if urls:
            row = supabase_update_signature(sig_id, urls) or row

        print(f"  ✅ [시그니처 등록] #{sig_id} '{title}' {amount}원")
        return jsonify({'status': 'success', 'message': '시그니처가 등록되었습니다.', 'signature': row})
    except Exception as e:
        print(f"[시그니처 등록 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/signatures/update/<int:sig_id>', methods=['POST'])
def api_signature_update(sig_id):
    try:
        current = supabase_get_signature(sig_id)
        if not current:
            return jsonify({'status': 'error', 'message': '시그니처를 찾을 수 없습니다.'}), 404

        fields = {}
        if request.form.get('amount') is not None and request.form.get('amount') != '':
            fields['amount'] = int(request.form.get('amount'))
        if request.form.get('title') is not None and request.form.get('title').strip():
            fields['title'] = request.form.get('title').strip()
        if request.form.get('duration'):
            fields['duration'] = int(request.form.get('duration'))

        image_file = request.files.get('image')
        sound_file = request.files.get('sound')
        # 파일 교체 시 기존 Storage 파일 정리 (확장자가 바뀔 수 있으므로 URL 기준 삭제)
        if image_file and image_file.filename:
            storage_delete_by_url(current.get('image_url'))
        if sound_file and sound_file.filename:
            storage_delete_by_url(current.get('sound_url'))
        fields.update(_save_signature_files(sig_id, image_file, sound_file))

        if not fields:
            return jsonify({'status': 'success', 'message': '변경 사항이 없습니다.', 'signature': current})

        row = supabase_update_signature(sig_id, fields)
        print(f"  ✏️ [시그니처 수정] #{sig_id} {list(fields.keys())}")
        return jsonify({'status': 'success', 'message': '시그니처가 수정되었습니다.', 'signature': row})
    except Exception as e:
        print(f"[시그니처 수정 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/signatures/delete/<int:sig_id>', methods=['POST', 'DELETE'])
def api_signature_delete(sig_id):
    try:
        current = supabase_get_signature(sig_id)
        if not current:
            return jsonify({'status': 'error', 'message': '시그니처를 찾을 수 없습니다.'}), 404
        storage_delete_by_url(current.get('image_url'))
        storage_delete_by_url(current.get('sound_url'))
        supabase_delete_signature(sig_id)
        print(f"  🗑️ [시그니처 삭제] #{sig_id} '{current.get('title')}'")
        return jsonify({'status': 'success', 'message': '시그니처가 삭제되었습니다.'})
    except Exception as e:
        print(f"[시그니처 삭제 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# 🏦 은행 원장 (플레이어별 통장 내역 / 잔액 재정산)
# ==========================================
@app.route('/api/bank/statement/<path:player_name>', methods=['GET'])
def get_bank_statement(player_name):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                db_query("""SELECT timestamp, tx_type, score_change, score_balance,
                                   contrib_change, contrib_balance, description
                            FROM bank_ledger WHERE player_name = ? ORDER BY id DESC LIMIT 50"""),
                (player_name,)
            )
            statement = [{
                "timestamp": r[0], "tx_type": r[1],
                "score_change": r[2], "score_balance": r[3],
                "contrib_change": r[4], "contrib_balance": r[5],
                "description": r[6]
            } for r in cursor.fetchall()]

            cursor.execute(db_query("SELECT score, contribution FROM players WHERE name = ?"), (player_name,))
            row = cursor.fetchone()

        return jsonify({
            "status": "success",
            "player_name": player_name,
            "current_score_balance": row[0] if row else 0,
            "current_contrib_balance": row[1] if row else 0,
            "statement_history": statement
        })
    except Exception as e:
        print(f"[통장 내역 조회 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/bank/recalculate', methods=['POST'])
def recalculate_bank_balances():
    """원장에 쌓인 변동분을 처음부터 다시 합산해 현재 잔액을 재구성한다.
       점수가 어긋났다고 의심될 때 쓰는 복구 수단."""
    try:
        global MEMORY_STATE, LAST_PERSISTED
        with file_lock:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(db_query("""
                    SELECT player_name, SUM(score_change), SUM(contrib_change)
                    FROM bank_ledger GROUP BY player_name
                """))
                totals = {r[0]: (r[1] or 0, r[2] or 0) for r in cursor.fetchall()}

                for name, (score_sum, contrib_sum) in totals.items():
                    if IS_POSTGRES:
                        cursor.execute(
                            "INSERT INTO players (name, score, contribution) VALUES (%s, %s, %s) "
                            "ON CONFLICT (name) DO UPDATE SET score = EXCLUDED.score, contribution = EXCLUDED.contribution",
                            (name, score_sum, contrib_sum)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO players (name, score, contribution) VALUES (?, ?, ?) "
                            "ON CONFLICT(name) DO UPDATE SET score = excluded.score, contribution = excluded.contribution",
                            (name, score_sum, contrib_sum)
                        )

            # DB에서 다시 읽어 메모리 상태를 맞춘다.
            # ⚠️ 먼저 큐를 비운다. 재정산 직전에 눌린 점수 버튼의 낡은 스냅샷이 뒤늦게 쓰이면
            #    방금 원장 기준으로 맞춘 점수가 도로 돌아가고, 그 차이가 '수동 변경'으로
            #    장부에 기록되어 재정산이 신뢰하는 원장 자체를 오염시킨다.
            drain_db_writes()
            MEMORY_STATE = None
            LAST_PERSISTED = None
            state = load_data()
            broadcast_event('update', state)

        print(f"  🏦 [원장 재정산] {len(totals)}명 잔액 복구")
        return jsonify({"status": "success",
                        "message": f"{len(totals)}명의 잔액을 원장 기준으로 재정산했습니다.",
                        "updated": len(totals)})
    except Exception as e:
        print(f"[원장 재정산 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 👑 특별 후원자(VIP) 관리
#    조회는 오버레이가 써야 하므로 공개, 등록/삭제는 로그인 필요(exempt 목록에 없음)
# ==========================================
@app.route('/api/vips', methods=['GET'])
def get_vips():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT name, grade, custom_color, badge FROM vip_donators ORDER BY name ASC"))
            vips = [{"name": r[0], "grade": r[1], "custom_color": r[2], "badge": r[3]}
                    for r in cursor.fetchall()]
        return jsonify({"status": "success", "vips": vips})
    except Exception as e:
        print(f"[VIP 목록 조회 오류] {e}")
        return jsonify({"status": "error", "message": str(e), "vips": []}), 500

@app.route('/api/vips', methods=['POST'])
def add_or_update_vip():
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        grade = (data.get('grade') or '').strip()
        custom_color = data.get('custom_color') or '#ffd700'
        badge = data.get('badge') or '👑'
        if not name or not grade:
            return jsonify({"status": "error", "message": "닉네임과 등급은 필수입니다."}), 400

        with get_db_connection() as conn:
            cursor = conn.cursor()
            if IS_POSTGRES:
                cursor.execute("""
                    INSERT INTO vip_donators (name, grade, custom_color, badge)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE
                    SET grade = EXCLUDED.grade,
                        custom_color = EXCLUDED.custom_color,
                        badge = EXCLUDED.badge
                """, (name, grade, custom_color, badge))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO vip_donators (name, grade, custom_color, badge)
                    VALUES (?, ?, ?, ?)
                """, (name, grade, custom_color, badge))

        broadcast_event('vips_updated', {})
        print(f"  👑 [VIP 저장] {name} ({grade})")
        return jsonify({"status": "success", "message": "특별 후원자 정보가 저장되었습니다."})
    except Exception as e:
        print(f"[VIP 저장 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/vips', methods=['DELETE'])
def delete_vip():
    try:
        name = request.args.get('name')
        if not name:
            return jsonify({"status": "error", "message": "닉네임이 누락되었습니다."}), 400
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("DELETE FROM vip_donators WHERE name = ?"), (name,))
        broadcast_event('vips_updated', {})
        print(f"  👑 [VIP 해제] {name}")
        return jsonify({"status": "success", "message": "특별 후원자 해제 완료!"})
    except Exception as e:
        print(f"[VIP 삭제 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/offwork/broadcast', methods=['POST'])
def broadcast_offwork():
    """🏃 퇴근 성공 연출 송출. 운영자가 승인대기함에서 [송출하기]를 누를 때 호출된다."""
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '선수').strip()
        broadcast_event('off_work_event', {'name': name})
        print(f"  🏃 [퇴근 송출] {name}")
        return jsonify({"status": "success", "message": f"{name}님 퇴근 이벤트를 송출했습니다."})
    except Exception as e:
        print(f"[퇴근 송출 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/goal/approve_event', methods=['POST'])
def approve_goal_event():
    """🎯 목표 100% 달성 연출 송출 승인. 운영자가 눌러야 오버레이에 연출이 나간다."""
    try:
        with file_lock:
            state = load_data()
            state['goal_event_pending'] = False
            state['goal_event_approved'] = True
            save_data(state)
            broadcast_event('goal_celebration', {
                'timestamp': time.time(),
                'target_goal': state.get('target_goal', 50000)
            })
            broadcast_event('update', state)
        print("  🎯 [목표 달성 연출 송출]")
        return jsonify({"status": "success", "message": "목표 달성 연출을 방송 화면에 송출했습니다!"})
    except Exception as e:
        print(f"[목표 연출 송출 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/signature/play', methods=['POST'])
def api_signature_play():
    """수동 송출 (정산 장부 기록 없음).
       sig_id 지정 시 해당 시그니처 그대로, 아니면 amount로 매칭."""
    try:
        data = request.get_json(silent=True) or {}
        sig_id = data.get('sig_id')
        amount = int(data.get('amount') or 0)
        donator = (data.get('name') or '수동송출').strip() or '수동송출'
        message = (data.get('message') or '').strip()

        if sig_id:
            sig = supabase_get_signature(sig_id)
            if sig and not amount:
                amount = sig.get('amount') or 0
        else:
            if amount <= 0:
                return jsonify({'status': 'error', 'message': '후원 금액을 입력해주세요.'}), 400
            sig = supabase_match_signature(amount)

        if not sig:
            return jsonify({'status': 'error', 'message': '재생할 시그니처를 찾지 못했습니다.'}), 404

        with file_lock:
            state = load_data()
            # 재생 전용 수동 송출은 실제 후원이 아니므로 시그니처 순위 집계에서 제외한다.
            enqueue_signature(state, sig, amount, donator, message, count_tally=False)
            save_data(state)
            broadcast_event('update', state)

        print(f"  ▶️ [수동 송출] {amount}원 → '{sig.get('title')}' (#{sig.get('id')})")
        return jsonify({'status': 'success', 'message': '송출했습니다.', 'signature': sig})
    except Exception as e:
        print(f"[수동 송출 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# 👥 BJ 일괄 등록 API
# ==========================================
@app.route('/api/bjs/import', methods=['POST'])
def import_bjs():
    try:
        req = request.json
        names = req.get('names', [])
        if not names:
            return jsonify({'status': 'error', 'message': '등록할 이름이 없습니다.'}), 400
            
        with file_lock:
            state = load_data()
            overwrite = req.get('overwrite', False)
            new_bjs = []
            
            for name in names:
                name = name.strip()
                if not name:
                    continue
                new_bjs.append({"name": name, "score": 0, "contribution": 0})
                
            if overwrite:
                state['bjs'] = new_bjs
            else:
                existing_names = {bj['name'] for bj in state.get('bjs', [])}
                for new_bj in new_bjs:
                    if new_bj['name'] not in existing_names:
                        state['bjs'].append(new_bj)
                        
            save_data(state, sync=True)
            broadcast_event('update', state)
            
        return jsonify({'status': 'success', 'count': len(new_bjs)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# 🌐 페이지 라우팅
# ==========================================
@app.route('/setup', methods=['GET', 'POST'])
def serve_setup():
    if request.method == 'POST':
        try:
            data = request.get_json() or {}
            p = data.get('password', '').strip()
            if p == load_auth_config()['admin_password']:
                session['setup_authorized'] = True
                return jsonify({'status': 'success'})
            else:
                return jsonify({'status': 'error', 'message': '비밀번호가 잘못되었습니다.'}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # GET request
    if not session.get('setup_authorized'):
        # Return a simple password protection UI for setup
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔒 라이브 마스터 OTP 등록 게이트</title>
    <style>
        body {{
            background: #0d0d0f;
            color: #f5f5f7;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }}
        .card {{
            background: #16161a;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 20px;
            padding: 40px 30px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            max-width: 400px;
            width: 90%;
            box-sizing: border-box;
        }}
        h2 {{ color: #00ffcc; margin-top: 0; font-size: 22px; }}
        input {{
            width: 100%;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            padding: 12px;
            border-radius: 8px;
            color: #fff;
            font-size: 16px;
            text-align: center;
            box-sizing: border-box;
            outline: none;
            margin: 20px 0;
        }}
        input:focus {{ border-color: #00ffcc; }}
        .btn {{
            background: #00ffcc;
            color: #000;
            border: none;
            padding: 14px 28px;
            font-weight: bold;
            border-radius: 8px;
            cursor: pointer;
            width: 100%;
            font-size: 15px;
        }}
        .err {{ color: #ff453a; font-size: 13px; margin-top: 10px; display: none; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>🔒 OTP 등록 페이지 인증</h2>
        <p style="font-size: 14px; color: #8e8e93;">보안을 위해 서버 비밀번호를 입력해 주세요.</p>
        <input type="password" id="pw" placeholder="비밀번호 입력" autofocus onkeydown="if(event.key==='Enter') verifyPw()">
        <button onclick="verifyPw()" class="btn">인증 및 등록 진행</button>
        <div id="err" class="err">비밀번호가 올바르지 않습니다.</div>
    </div>
    <script>
        async function verifyPw() {{
            const p = document.getElementById('pw').value.trim();
            const err = document.getElementById('err');
            err.style.display = 'none';
            try {{
                const res = await fetch('/setup', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{password: p}})
                }});
                const data = await res.json();
                if (data.status === 'success') {{
                    window.location.reload();
                }} else {{
                    err.innerText = data.message;
                    err.style.display = 'block';
                }}
            }} catch(e) {{
                err.innerText = '인증 중 오류가 발생했습니다.';
                err.style.display = 'block';
            }}
        }}
    </script>
</body>
</html>
"""
        return html

    secret = get_or_create_totp_secret()
    # QR Code compatible URL (ASCII only for label/issuer)
    otp_uri = f"otpauth://totp/LiveMaster:admin?secret={secret}&issuer=LiveMaster"
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔒 라이브 마스터 OTP 초기 페어링</title>
    <style>
        body {{
            background: #0d0d0f;
            color: #f5f5f7;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }}
        .card {{
            background: #16161a;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 20px;
            padding: 40px 30px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            max-width: 420px;
            width: 90%;
            box-sizing: border-box;
        }}
        h2 {{ color: #00ffcc; margin-top: 0; font-size: 22px; }}
        p {{ font-size: 14px; color: #8e8e93; line-height: 1.6; }}
        canvas {{ background: #fff; padding: 10px; border-radius: 10px; margin: 20px 0; }}
        .secret-label {{ font-size: 12px; color: #8e8e93; margin-top: 15px; margin-bottom: 5px; }}
        .secret {{
            background: rgba(255,255,255,0.05);
            padding: 12px;
            border-radius: 8px;
            font-family: monospace;
            font-size: 18px;
            letter-spacing: 2px;
            color: #ff9f0a;
            user-select: all;
            word-break: break-all;
            font-weight: bold;
        }}
        .btn {{
            background: #00ffcc;
            color: #000;
            border: none;
            padding: 14px 28px;
            font-weight: bold;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 25px;
            text-decoration: none;
            display: inline-block;
            transition: opacity 0.2s;
        }}
        .btn:hover {{ opacity: 0.9; }}
    </style>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrious/4.0.2/qrious.min.js"></script>
</head>
<body>
    <div class="card">
        <h2>🔒 모바일 OTP 페어링 타워</h2>
        <p>스마트폰의 <b>구글 OTP (Google Authenticator)</b> 앱을 실행하고,<br>우측 하단의 '+' 버튼을 눌러 아래 QR 코드를 스캔해 주세요.</p>
        <canvas id="qr"></canvas>
        <div class="secret-label">수동 등록을 위한 보안 키 (앱에 직접 입력 가능)</div>
        <div class="secret">{secret}</div>
        <a href="/login" class="btn">인증 로그인 화면으로 이동</a>
    </div>
    <script>
        new QRious({{
            element: document.getElementById('qr'),
            value: '{otp_uri}',
            size: 200
        }});
    </script>
</body>
</html>
"""
    return html

@app.route('/login', methods=['GET', 'POST'])
def serve_login():
    if request.method == 'GET' and session.get('authenticated'):
        if request.query_string:
            return redirect(url_for('serve_controller') + '?' + request.query_string.decode('utf-8'))
        return redirect(url_for('serve_controller'))
        
    if request.method == 'POST':
        try:
            data = request.get_json(silent=True) or request.form or {}
            p = data.get('password', '').strip()
            otp_code = data.get('otp', '').strip()
            
            # PW 검증
            if p == load_auth_config()['admin_password']:
                totp_secret = get_or_create_totp_secret()
                totp = pyotp.TOTP(totp_secret)
                # OTP 번호가 비어있거나 입력된 OTP가 올바른 경우 로그인 승인
                if not otp_code or totp.verify(otp_code, valid_window=1):
                    session['authenticated'] = True
                    return jsonify({'status': 'success'})
                else:
                    return jsonify({'status': 'error', 'message': '보안 OTP 번호가 일치하지 않습니다.'}), 400
            else:
                return jsonify({'status': 'error', 'message': '비밀번호가 잘못되었습니다.'}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
            
    return serve_html_file('login.html')

@app.route('/logout')
def serve_logout():
    session.pop('authenticated', None)
    return redirect(url_for('serve_login'))

@app.route('/')
def serve_root():
    return serve_html_file('overlay.html')

@app.route('/overlay')
@app.route('/overlay.html')
def serve_overlay():
    return serve_html_file('overlay.html')

@app.route('/slot')
@app.route('/slot.html')
def serve_slot():
    return serve_html_file('slot.html')

@app.route('/signature-display')
@app.route('/signature-display.html')
def serve_signature_display():
    return serve_html_file('signature_display.html')

@app.route('/alertbox')
@app.route('/alertbox.html')
def serve_alertbox():
    return serve_html_file('alertbox.html')

@app.route('/manual')
@app.route('/manual_send')
@app.route('/manual_send.html')
def serve_manual_send():
    return serve_html_file('manual_send.html')

@app.route('/streamdeck')
@app.route('/streamdeck.html')
def serve_streamdeck():
    return serve_html_file('streamdeck.html')

@app.route('/controller')
def serve_controller():
    # 모바일/데스크톱 분기를 없애고 하나의 반응형 UI(controller.html)만 서빙한다.
    # (예전엔 mode=mobile 이나 모바일 UA 이면 mobile.html 을 줬지만, 이제 한 UI로 통합)
    return serve_html_file('controller.html')

@app.route('/mobile')
def serve_mobile():
    # 📱 자리 비웠을 때 폰으로 쓰는 전용 화면.
    #    한동안 컨트롤러를 그대로 보냈는데, 폰에서 12개 탭을 다 재현하니 결국 쓰기 불편했다.
    #    지금은 '후원 배정'과 '점수 수정' 두 가지만 있는 별도 페이지를 보낸다.
    return serve_html_file('mobile.html')

@app.route('/admin')
@app.route('/admin.html')
def serve_admin():
    return serve_html_file('admin.html')

@app.route('/upload')
@app.route('/노래등록')
def serve_upload():
    return serve_html_file('upload.html')

@app.route('/<path:filename>')
def serve_dynamic_file(filename):
    if filename.startswith('api/'):
        return jsonify({"status": "error", "message": "API endpoint not found"}), 404
    for root in [BASE_DIR, BUNDLE_DIR]:
        if os.path.exists(os.path.join(root, filename)):
            return send_from_directory(root, filename)
    return jsonify({"error": "File not found"}), 404

# ==========================================
# 🛡️ 투네이션 후원 안전 접수 및 파서
# ==========================================
@app.route('/api/donation', methods=['POST'])
def receive_donation():
    try:
        new_don = request.json or {}
        amount = int(new_don.get('amount', 0))
        tx_id = new_don.get('tx_id')
        
        # 1. 음수(0원 미만) 후원 금액 차단 (0원 시그니처 후원 등 허용)
        if amount < 0:
            return jsonify({"status": "error", "message": "Invalid amount"}), 400
            
        # 2. tx_id 중복 검사로 중복 처리 차단
        if tx_id:
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(db_query("SELECT id FROM donation_history WHERE tx_id = ?"), (tx_id,))
                    if cursor.fetchone():
                        return jsonify({"status": "success", "message": "Duplicate donation ignored."})
            except Exception as dbe:
                print(f"⚠️ [tx_id 중복 확인 오류] {dbe}")

        # 2-b. 재전송 대비: 이름+금액+메시지가 동일한 후원이 아주 짧은 시간 안에
        #      다시 오면 중복으로 간주해 무시한다(시그니처 이중 재생 방지).
        # ⚠️ 예전에는 `if not tx_id:` 였다. 그런데 템퍼몽키 스크립트는 재시도할 때마다
        #    tx_id 를 '새로 만들어' 보낸다. 그래서 응답이 늦어 재시도가 걸리면
        #    tx_id 검사는 통과해버리고(값이 다르니까) 이 검사는 아예 건너뛰어서,
        #    같은 후원이 두 번 들어와 시그니처가 두 번 재생되고 장부에도 두 줄이 남았다.
        #    tx_id 유무와 무관하게 항상 내용 기반으로도 걸러야 한다.
        dup_key = f"{(new_don.get('name') or '').strip()}|{amount}|{(new_don.get('message') or '').strip()}"
        if is_duplicate_donation(dup_key):
            print("⚠️ [내용 기반 중복 후원 무시] 동일 후원이 짧은 시간에 재수신됨")
            return jsonify({"status": "success", "message": "Duplicate donation ignored (content)."})

        # 🎵 시그니처 매칭은 file_lock 밖에서 미리 끝낸다.
        # ⚠️ 이 호출은 Supabase로 나가는 HTTP라 느려질 수 있는데, 예전에는 락을 쥔 채 실행했다.
        #    그러면 후원 한 건이 처리되는 동안 점수 버튼·슬롯·리액션 넘기기 등
        #    락을 쓰는 모든 조작이 통째로 멈춰 방송 중 컨트롤러가 얼어붙었다.
        #    매칭은 state를 읽지 않으므로 락이 필요 없다.
        matched_sig = None
        if amount > 0:
            try:
                matched_sig = supabase_match_signature(amount)
            except Exception as e:
                print(f"⚠️ [자동 시그니처 매칭 오류] {e}")

        with file_lock:
            state = load_data()
            don_id = f"don_{int(time.time() * 1000)}"
            name = new_don.get('name', '익명')
            msg = new_don.get('message', '')
            
            parsed_name = name.strip()
            cleaned_msg = msg.strip()
            
            # 💡 [핵심] 메시지 내 콜론(:)을 감지하여 이름과 메시지를 분리해주는 오토 파서 (시그니처 신청 태그는 제외)
            cleaned_msg_for_split = cleaned_msg.replace('：', ':')
            if cleaned_msg_for_split and ':' in cleaned_msg_for_split and not cleaned_msg.startswith("[시그니처 신청:"):
                split_char = ':' if ':' in cleaned_msg else '：'
                parts = cleaned_msg.split(split_char, 1)
                potential_name = parts[0].strip()
                if 0 < len(potential_name) <= 15:
                    parsed_name = potential_name
                    cleaned_msg = parts[1].strip()
                    
            if parsed_name.endswith('님') and len(parsed_name) > 1:
                parsed_name = parsed_name[:-1]
                
            parsed_don_entry = {
                'id': don_id,
                'name': parsed_name,
                'amount': amount,
                'message': cleaned_msg,
                'time': time.strftime('%H:%M:%S')
            }
            state['pending_donations'].append(parsed_don_entry)
            state['latest_donation'] = {
                'name': parsed_name,
                'amount': amount,
                'message': cleaned_msg,
                'time': time.time()
            }
            # ⚠️ 여기서 reaction_mode 를 무조건 켜면 안 된다.
            #    시그니처가 매칭되지 않는 후원(금액 미등록, 0원 후원, Supabase 일시 오류)에서도
            #    켜져버리는데, 켜는 건 여기뿐이고 끄는 건 '오버레이가 큐를 다 소화했을 때'뿐이라
            #    큐가 비어 있으면 아무도 못 끈다. 그러면 오버레이가 랭킹판·게이지를 숨긴 채
            #    (컨트롤러 표기: '위젯 숨김') 방송이 계속되고, 운영자가 수동으로 끌 때까지 돌아오지 않는다.
            #    실제로 큐에 넣는 enqueue_signature 가 이미 켜주므로 여기서는 손대지 않는다.

            # BJ 점수판 업데이트
            current_total = amount
            target_list_key = 'extra_bjs' if state.get('extra_game_active', False) else 'bjs'
            
            if target_list_key == 'extra_bjs' and not state.get('extra_bjs'):
                state['extra_bjs'] = [{"name": bj['name'], "score": 0, "contribution": 0} for bj in state.get('bjs', [])]
                
            # [비활성화] 닉네임 직접 매칭 자동 점수 가산 기능 해제 (모든 후원이 승인 대기함으로 모이도록 설정)
            # for bj in state.get(target_list_key, []):
            #     if bj['name'] == parsed_name:
            #         add_point = int(amount / 10000 + 0.5)
            #         bj['score'] += add_point
            #         bj['contribution'] = bj.get('contribution', 0) + add_point
            #         current_total = bj['score']
            #         break
            # ⚠️ 한 번 실패하면 그 후원은 정산 장부에서 통째로 사라진다(운영자는 대기함에서 보고
            #    점수를 주지만 장부엔 없다). Supabase 는 유휴 커넥션을 끊기 때문에 조용한 구간 뒤
            #    첫 후원에서 이게 실제로 발생한다. 다른 곳(save_data_sync)은 이미 1회 재시도로
            #    대응하고 있는데 여기만 빠져 있었다. 실패는 상태창에도 남겨 운영자가 알 수 있게 한다.
            for _attempt in range(2):
                try:
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            db_query("INSERT INTO donation_history (timestamp, name, amount, current_total, message, source, tx_id) VALUES (?, ?, ?, ?, ?, ?, ?)"),
                            (time.strftime('%Y-%m-%d %H:%M:%S'), parsed_name, amount, current_total, cleaned_msg, "toonation", tx_id)
                        )
                    break
                except Exception as dbe:
                    if _attempt == 0:
                        print(f"[장부 기록 실패 — 재시도] {dbe}")   # 끊긴 커넥션은 이미 폐기됐다
                        continue
                    print(f"[장부 기록 오류] {dbe}")
                    LAST_DB_ERROR["message"] = f"후원 장부 기록 실패({parsed_name} {amount}원): {dbe}"
                    LAST_DB_ERROR["time"] = time.strftime('%Y-%m-%d %H:%M:%S')
                
            # 🎵 자동 시그니처 리액션 연동 (매칭은 위에서 락 밖에 끝냈고, 여기서는 큐에만 넣는다)
            if matched_sig:
                enqueue_signature(state, matched_sig, amount, parsed_name, cleaned_msg)
                print(f"  🎵 [자동 시그니처] 후원 {amount}원 → '{matched_sig.get('title')}' (#{matched_sig.get('id')}, {matched_sig.get('amount')}원) 큐 추가 완료")


            # ⚠️ 저장 '대기'를 락 안에서 하면 안 된다.
            #    save_data(sync=True) 는 DB 쓰기 큐가 빌 때까지 최대 30초를 기다린다.
            #    점수 버튼을 몇 번 누른 직후라면 그 큐에 앞선 쓰기가 쌓여 있어(Render→Supabase 왕복)
            #    후원 한 건이 file_lock 을 수 초에서 수십 초까지 쥐고 있었다. 그동안
            #    점수 지급·큐 넘김(/api/reaction/next)·대기함 삭제가 전부 얼어붙어,
            #    화면에서는 시그니처가 멈추고 컨트롤러가 먹통이 됐다.
            #    큐에 넣는 것까지만 락 안에서 하고, 기다리는 건 락을 놓은 뒤에 한다.
            pending_write = save_data(state, sync=True, wait=False)
            broadcast_event('update', state)

            print("  🎯 [최종 처리 결과]")
            print(f"    ▶ 최종 분류된 이름  : {parsed_name}")
            print(f"    ▶ 최종 분류된 메시지: {cleaned_msg}")
            print("    ▶ 자동 승인 처리 여부: 🟡 클래식 수동 정산 모드 작동 (승인 대기함 적립)")
            print("======================================================================\n")

        # 락을 놓은 뒤에 기다린다 — 후원이 실제로 저장된 뒤에 응답한다는 보장은 그대로 유지된다.
        if pending_write is not None and not pending_write.wait(timeout=30):
            print("⚠️ [후원 동기 저장 시간 초과] 백그라운드에서 계속 진행됩니다.")
        return jsonify({'status': 'success', 'id': don_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# 📺 CORS 우회 유튜브 검색 API (SSL 무시)
# ==========================================
@app.route('/api/yt/search')
def yt_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
        
    instances = ['https://yewtu.be', 'https://invidious.flokinet.to', 'https://iv.melmac.space']
    ssl_ctx = ssl._create_unverified_context()
    
    for base in instances:
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"{base}/api/v1/search?q={encoded_query}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=3) as response:
                data = json.loads(response.read().decode('utf-8'))
                results = []
                for item in data:
                    if item.get('type') == 'video':
                         length = item.get('lengthSeconds', 0)
                         mins = length // 60
                         secs = length % 60
                         duration_str = f"{mins}:{secs:02d}"
                         
                         video_id = item.get('videoId', '')
                         results.append({
                             'title': item.get('title', ''),
                             'videoId': video_id,
                             'author': item.get('author', ''),
                             'duration': duration_str,
                             'thumbnail': f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
                         })
                return jsonify(results)
        except Exception as e:
            print(f"[YT Search Exception on {base}] {e}")
            continue
            
    return jsonify([])

@app.route('/api/audit/suggest', methods=['POST'])
def api_audit_suggest():
    """[AI 기입 검증] 후원 메시지가 지목하는 플레이어를 추정해 돌려준다.
       컨트롤러가 대기함 후원 1건당 1회 호출해 '추천 배지 / 오배정 경고'에만 쓴다.
       실패해도 항상 200 + target=None 으로 응답해 컨트롤러가 멈추지 않게 한다."""
    try:
        body = request.json or {}
        name = str(body.get('name', ''))
        amount = body.get('amount', 0)
        message = str(body.get('message', ''))
        players = body.get('players')
        if not players:   # 클라이언트가 안 보냈으면 서버 상태에서 현재 플레이어를 읽는다
            with file_lock:
                state = load_data()
                src = 'extra_bjs' if state.get('extra_game_active') else 'bjs'
                players = [b.get('name') for b in state.get(src, [])]
        result = nim_suggest_target(name, amount, message, players)
        return jsonify({"status": "success", **result})
    except Exception as e:
        return jsonify({"status": "success", "target": None, "confidence": 0.0, "error": str(e)[:80]})

@app.route('/api/ai/chat', methods=['POST'])
def api_ai_chat():
    """[AI 서포트 채팅] 운영자가 현재 상황을 물어보면, 실시간 상태 스냅샷을 근거로 답한다.
       조작은 하지 않고 정보/조언만. 실패해도 항상 200 + 안내 문구로 응답한다."""
    try:
        body = request.json or {}
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
        req_body = {"model": NIM_CHAT_MODEL, "messages": msgs, "temperature": 0.3, "max_tokens": 700}
        r = requests.post(NIM_URL, headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                          json=req_body, timeout=30)
        if r.status_code != 200:
            return jsonify({"status": "success", "reply": f"(AI 오류 {r.status_code}) 잠시 후 다시 시도해주세요."})
        msg = r.json()["choices"][0]["message"]
        reply = (msg.get("content") or "").strip()
        if not reply:   # 추론모델이 content 대신 reasoning_content 로 줄 때 대비
            reply = (msg.get("reasoning_content") or "").strip()
        if not reply:
            reply = "(응답이 비어서 왔어요. 다시 한 번 물어봐 주세요.)"
        return jsonify({"status": "success", "reply": reply})
    except Exception as e:
        return jsonify({"status": "success", "reply": f"(오류) {str(e)[:100]}"})

@app.route('/api/data', methods=['GET', 'POST'])
def api_data():
    if request.method == 'POST':
        with file_lock:
            incoming = request.json or {}
            current_state = load_data()

            # 🛡️ [동시성 수정] 예전에는 클라이언트가 보낸 전체 상태로 서버를 통째로 덮어썼다(Last-Write-Wins).
            #   그러면 후원이 막 들어와 서버가 큐에 시그니처를 넣은 순간, (후원 직전 상태를 들고 있던)
            #   조종실이 점수 버튼을 누르면 그 스테일 상태가 서버를 덮어써서 방금 들어온 시그니처가
            #   큐에서 사라졌다("시그니처가 씹힌다"). 그래서 '서버만 건드리는 필드'는 클라이언트가
            #   덮어쓰지 못하게 서버 값을 유지한다. (이 필드들은 후원 수신·큐 조작 엔드포인트에서만 바뀐다.
            #   조종실/모바일/에디터의 어떤 조작도 /api/data 로 이 필드를 직접 수정하지 않으므로 안전하다.)
            SERVER_OWNED = ('reaction_queue', 'latest_donation', 'pending_donations')

            # 🔐 [보안] 응답 전용 필드는 절대 상태로 들어오면 안 된다.
            #   GET /api/data 는 로그인 세션이 있으면 응답에 api_token(= 관리자 비밀키)을 얹어준다.
            #   그런데 에디터는 받은 응답 객체를 통째로 globalData 에 넣고(admin.html) 그대로 다시 POST 한다.
            #   여기서 걸러내지 않으면 그 키가 state 에 눌러앉아 DB 에 평문으로 저장되고,
            #   무인증으로 열려 있는 /api/stream 을 통해 모든 오버레이·알림창에 방송된다.
            #   그 값은 보호된 API 를 전부 통과하는 Bearer 토큰이자 세션 서명키다.
            for _k in ('api_token', 'server_time'):
                incoming.pop(_k, None)

            state = dict(current_state)
            state.update(incoming)                      # 클라이언트 편집 필드는 그대로 반영(점수·설정·승인 등 기존 동작 유지)
            state.pop('api_token', None)                # 과거에 이미 오염됐다면 여기서 씻어낸다
            for k in SERVER_OWNED:
                if k in current_state:
                    state[k] = current_state[k]          # 서버 소유 필드는 서버의 최신 값을 유지
            # 큐에 항목이 남아 있으면 리액션 모드는 항상 켜져 있어야 한다(스테일 클라이언트가 끄는 사고 방지)
            if state.get('reaction_queue'):
                state['reaction_mode'] = True

            # [버전] 409 경고 대신 마지막 전송 기준으로 버전만 올린다.
            state['version'] = max(incoming.get('version', 0), current_state.get('version', 1)) + 1

            # ⚠️ 여기서 동기 저장을 하면 안 된다.
            # 점수 버튼은 방송 중 연타하는 조작인데, Render(오레곤)→Supabase(서울) 왕복 때문에
            # 클릭 한 번에 2초 넘게 걸려 점수 반영이 눈에 띄게 밀렸다.
            # 저장은 백그라운드 큐에 맡기고(수 ms 내 반영), 화면에는 즉시 브로드캐스트한다.
            # 잃으면 안 되는 기록은 방송 시작/종료·리셋·복구 쪽에서 동기로 처리한다.
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
        
    state = load_data()
    if isinstance(state, dict):
        state = state.copy()
        # 🔐 과거에 상태로 새어 들어간 값이 남아 있어도 무인증 응답에 절대 실려나가지 않게 먼저 지운다
        state.pop('api_token', None)
        state['server_time'] = int(time.time() * 1000)
        # 조종실 웹에 로그인 세션이 있을 경우에만 보안 API 토큰을 제공
        if session.get('authenticated'):
            state['api_token'] = load_auth_config()['session_secret']
    return jsonify(state)

@app.route('/api/offwork/pending', methods=['POST'])
def api_offwork_pending():
    """퇴근전쟁 목표를 넘긴 플레이어의 '퇴근 성공' 카드를 서버에 만든다.

    ⚠️ 예전에는 컨트롤러가 자기 pending_donations 에 카드를 직접 넣고 /api/data 로 밀어넣었다.
       그런데 pending_donations 는 SERVER_OWNED 라 그 POST 에서 통째로 버려진다.
       카드는 다음 update 가 오는 순간 화면에서 사라지는데, '이미 알렸다'는 표시
       (home_race_notified)는 서버 소유가 아니라 그대로 저장됐다.
       결과적으로 그 플레이어는 두 번 다시 퇴근 카드를 받지 못했다 = 퇴근 연출을 영영 못 보냄.
       카드 생성과 '알림 표시'를 서버 한 곳에서 같이 처리해 어긋날 수 없게 한다.
    """
    name = ((request.json or {}).get('name') or '').strip()
    if not name:
        return jsonify({"status": "error", "message": "name required"}), 400
    with file_lock:
        state = load_data()
        pend = state.setdefault('pending_donations', [])
        notified = state.setdefault('home_race_notified', [])
        if name in notified or any(d.get('type') == 'off_work' and d.get('name') == name for d in pend):
            return jsonify({"status": "success", "message": "already"})
        notified.append(name)
        pend.insert(0, {
            'id': f"off_{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}",
            'type': 'off_work',
            'name': name,
            'amount': 0,
            'message': '퇴근전쟁 목표 달성!',
            'time': time.strftime('%H:%M:%S'),
        })
        save_data(state)
        broadcast_event('update', state)
    print(f"  🏃 [퇴근전쟁] '{name}' 퇴근 성공 카드 생성")
    return jsonify({"status": "success"})


@app.route('/api/match/timeup', methods=['POST'])
def api_match_timeup():
    """대결 타이머가 0이 됐을 때 오버레이가 알린다.

    ⚠️ 예전에는 오버레이가 이 목적으로 /api/data 에 '자기가 들고 있는 상태 전체'를 POST 했다.
       두 가지가 나빴다.
       1) 그것 때문에 /api/data POST 를 무인증으로 열어둘 수밖에 없었다(누구나 점수를 지울 수 있었다).
       2) 오버레이의 상태가 조금이라도 낡아 있으면 그 낡은 점수가 서버를 덮어썼다.
       그래서 '타이머를 멈춘다'는 사실만 전달하는 좁은 엔드포인트로 분리했다.
    """
    with file_lock:
        state = load_data()
        md = state.get('match_data') or {}
        if not md.get('active'):
            return jsonify({"status": "ignored"})   # 이미 끝난 대결이면 아무것도 하지 않는다
        md['is_running'] = False
        md['time_left_ms'] = 0
        state['match_data'] = md
        save_data(state)
        broadcast_event('update', state)
    return jsonify({"status": "success"})


@app.route('/api/roulette/winner', methods=['POST'])
def api_roulette_winner():
    try:
        req_data = request.json
        winner_name = req_data.get('name', '익명')
        with file_lock:
            state = load_data()
            if 'roulette' not in state:
                state['roulette'] = {
                    "command": None,
                    "command_time": 0,
                    "weight_type": "equal",
                    "select_name": "",
                    "select_index": -1,
                    "winner_name": None,
                    "is_spinning": False,
                    "item_source": "bj",
                    "custom_items": ["벌칙 1", "벌칙 2", "벌칙 3", "벌칙 4", "벌칙 5"]
                }
            state['roulette']['winner_name'] = winner_name
            state['roulette']['command'] = 'ended'
            state['roulette']['is_spinning'] = False
            state['roulette']['command_time'] = int(time.time() * 1000)
            state['roulette_enabled'] = False
            
            # 랭킹 로그에 기록 추가
            time_str = time.strftime('%H:%M:%S')
            if 'logs' not in state:
                state['logs'] = []
            state['logs'].insert(0, {
                'time': time_str,
                'name': f"🎡 룰렛 결과: {winner_name}",
                'val': 0
            })
            if len(state['logs']) > 200:
                state['logs'] = state['logs'][:200]
                
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/layout', methods=['GET', 'POST'])
def api_layout():
    if request.method == 'POST':
        with open(LAYOUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(request.json, f, ensure_ascii=False, indent=4)
        broadcast_event('layout', request.json)
        return jsonify({"status": "success"})
    if os.path.exists(LAYOUT_FILE):
        with open(LAYOUT_FILE, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({})

# ==========================================
# 🎮 번외 게임 모드 제어 API
# ==========================================
@app.route('/api/extra_game/start', methods=['POST'])
def extra_game_start():
    try:
        with file_lock:
            state = load_data()
            state["extra_game_active"] = True
            
            # Initialize extra_bjs with all players from bjs, reset scores to 0
            state["extra_bjs"] = []
            for bj in state.get("bjs", []):
                state["extra_bjs"].append({
                    "name": bj["name"],
                    "score": 0,
                    "contribution": 0
                })
                
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/extra_game/end', methods=['POST'])
def extra_game_end():
    try:
        with file_lock:
            state = load_data()
            if not state.get("extra_game_active", False) or "extra_bjs" not in state:
                return jsonify({"status": "error", "message": "진행 중인 번외 게임이 없습니다."}), 400
                
            extra_scores = {bj["name"]: bj for bj in state.get("extra_bjs", [])}
            
            for bj in state.get("bjs", []):
                bj_name = bj["name"]
                if bj_name in extra_scores:
                    bj["score"] += extra_scores[bj_name]["score"]
                    bj["contribution"] = bj.get("contribution", 0) + extra_scores[bj_name].get("contribution", 0)
                    
            state["extra_game_active"] = False
            state["extra_bjs"] = []
            
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/extra_game/cancel', methods=['POST'])
def extra_game_cancel():
    try:
        with file_lock:
            state = load_data()
            state["extra_game_active"] = False
            state["extra_bjs"] = []
            
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 💾 타임머신 스냅샷 API
# ==========================================
@app.route('/api/snapshots', methods=['GET'])
def get_snapshots():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT id, timestamp, summary FROM snapshots ORDER BY id DESC"))
            rows = cursor.fetchall()
            snapshots = [{"id": r[0], "timestamp": r[1], "summary": r[2]} for r in rows]
        return jsonify({"status": "success", "snapshots": snapshots})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/snapshots/manual', methods=['POST'])
def create_manual_snapshot():
    try:
        req_data = request.json
        label = req_data.get("label", "수동 백업")
        state = load_data()
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                db_query("INSERT INTO snapshots (timestamp, state_json, summary) VALUES (?, ?, ?)"),
                (timestamp, json.dumps(state, ensure_ascii=False), label)
            )
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/snapshots/restore', methods=['POST'])
def restore_snapshot():
    try:
        req_data = request.json
        snap_id = req_data.get("id")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT state_json FROM snapshots WHERE id = ?"), (snap_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "스냅샷을 찾을 수 없습니다."}), 404
            state_json = row[0]
            
        with file_lock:
            state = json.loads(state_json)
            save_data(state, sync=True)
            broadcast_event('update', state)
            
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/snapshots/delete', methods=['POST'])
def delete_snapshot():
    try:
        req_data = request.json
        snap_id = req_data.get("id")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("DELETE FROM snapshots WHERE id = ?"), (snap_id,))
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/server/status', methods=['GET'])
def get_server_status():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Get player count
            cursor.execute(db_query("SELECT COUNT(*) FROM players"))
            player_count = cursor.fetchone()[0]
            
            # Get donation history count
            cursor.execute(db_query("SELECT COUNT(*) FROM donation_history"))
            history_count = cursor.fetchone()[0]
            
            # Get snapshot count
            cursor.execute(db_query("SELECT COUNT(*) FROM snapshots"))
            snapshot_count = cursor.fetchone()[0]

            # 영구 보관 장부 누적 건수 (방송 종료/시작으로도 지워지지 않음)
            try:
                cursor.execute(db_query("SELECT COUNT(*) FROM donation_archive"))
                archive_count = cursor.fetchone()[0]
            except Exception:
                archive_count = 0
            
            # Get last 30 logs from donation_history
            cursor.execute(db_query("SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history ORDER BY id DESC LIMIT 30"))
            history_rows = cursor.fetchall()
            history_list = []
            for r in history_rows:
                history_list.append({
                    'id': r[0],
                    'timestamp': r[1],
                    'name': r[2],
                    'amount': r[3],
                    'current_total': r[4],
                    'message': r[5],
                    'source': r[6]
                })
                
        return jsonify({
            'status': 'success',
            'is_postgres': IS_POSTGRES,
            # 영구 저장 여부. False면 임시 디스크 SQLite라 재시작 시 데이터가 사라진다.
            'persistent_storage': IS_POSTGRES,
            'last_db_error': LAST_DB_ERROR.get('message'),
            'last_db_error_time': LAST_DB_ERROR.get('time'),
            'player_count': player_count,
            'history_count': history_count,
            'snapshot_count': snapshot_count,
            'archive_count': archive_count,
            'logs': history_list
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/server/reset', methods=['POST'])
def reset_server_database():
    try:
        global MEMORY_STATE
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("DELETE FROM players"))
            cursor.execute(db_query("DELETE FROM kv_store"))
            cursor.execute(db_query("DELETE FROM donation_history"))
            cursor.execute(db_query("DELETE FROM snapshots"))
            
        # 얕은 복사면 중첩 객체가 DEFAULT_STATE와 공유되어 기본값 자체가 오염된다
        MEMORY_STATE = copy.deepcopy(DEFAULT_STATE)
        save_data(MEMORY_STATE, is_initial=True, sync=True)
        broadcast_event('update', MEMORY_STATE)
        return jsonify({"status": "success", "message": "데이터베이스가 성공적으로 완전히 리셋되었습니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/server/end_broadcast', methods=['POST'])
def end_broadcast():
    try:
        global MEMORY_STATE
        with file_lock:
            # 0. ⚠️ 지우기 전에 반드시 보존한다.
            #    예전에는 방송 종료 시 장부(donation_history)를 그냥 삭제해서 기록이 영구히 사라졌다.
            session_label = time.strftime('%Y-%m-%d %H:%M:%S') + " 방송분"
            # ⚠️ 스냅샷은 아래 'DELETE FROM snapshots' 뒤에 넣는다.
            #    여기서 만들면 몇 줄 뒤 초기화가 방금 만든 백업까지 지워버려,
            #    실수로 방송을 종료했을 때 되돌릴 방법이 사라진다. 지금은 상태만 떠둔다.
            pre_state = copy.deepcopy(load_data())
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(db_query("""
                        INSERT INTO donation_archive
                            (archived_at, session_label, timestamp, name, amount, current_total, message, source, tx_id)
                        SELECT ?, ?, timestamp, name, amount, current_total, message, source, tx_id
                        FROM donation_history
                    """), (time.strftime('%Y-%m-%d %H:%M:%S'), session_label))
                    cursor.execute(db_query("SELECT COUNT(*) FROM donation_archive"))
                    print(f"  📚 [장부 영구 보관] 누적 {cursor.fetchone()[0]}건")
            except Exception as arch_e:
                # 보관에 실패하면 삭제를 진행하지 않는다 (기록 유실 방지)
                print(f"❌ [장부 보관 실패 - 방송 종료 중단] {arch_e}")
                return jsonify({"status": "error",
                                "message": f"장부 백업에 실패해 방송 종료를 중단했습니다: {arch_e}"}), 500

            # 1. Clear database tables (donation history, snapshots, players)
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(db_query("DELETE FROM players"))
                cursor.execute(db_query("DELETE FROM donation_history"))
                cursor.execute(db_query("DELETE FROM snapshots"))
                # Delete kv_store keys that are NOT persistent configurations
                cursor.execute(
                    db_query("DELETE FROM kv_store WHERE key NOT IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"), 
                    ('theme', 'neon_speed', 'saved_colors', 'target_goal', 'account', 'effect_rules', 'screen_effect', 'ticker_enabled', 'ticker_speed', 'ticker_text', 'totp_secret')
                )
            
            # 초기화가 끝난 뒤에 백업 스냅샷을 넣어야 살아남는다 (되돌리기 지점)
            create_snapshot(pre_state, f"방송 종료 자동 백업 ({session_label})")

            # 2. Get current state from database (which will have only configurations preserved)
            state = load_data()
            
            # Reset memory state and set broadcast_active to False
            state['broadcast_active'] = False
            state['bjs'] = []
            state['bottom_fixed']['score'] = 0
            state['reaction_mode'] = False
            state['match_data'] = {"active": False, "players": [], "time_left_ms": 180000, "is_running": False}
            state['pending_donations'] = []
            state['latest_donation'] = {"name": "", "amount": 0, "message": "", "time": 0}
            state['extra_game_active'] = False
            state['extra_bjs'] = []
            state['roulette_enabled'] = False
            if 'roulette' in state:
                state['roulette']['winner_name'] = None
                state['roulette']['is_spinning'] = False
                state['roulette']['select_name'] = ""
                state['roulette']['select_index'] = -1
            state['logs'] = []
            state['match_logs'] = []
            reset_session_keys(state)

            # ⚠️ is_initial=True 로 전체 키를 다시 쓴다.
            #    위에서 kv_store 행을 지웠는데 메모리 값은 그대로라, 변경분만 쓰는 평소 방식으로는
            #    "바뀐 게 없다"고 판단해 아무것도 복구되지 않는다. 그 상태로 서버가 재시작되면
            #    볼륨·슬롯 후보 같은 설정이 기본값으로 돌아가 버린다.
            save_data(state, is_initial=True, sync=True)
            broadcast_event('update', state)

        return jsonify({"status": "success", "message": "방송이 종료되고 오늘의 데이터가 리셋되었습니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/server/start_broadcast', methods=['POST'])
def start_broadcast():
    try:
        global MEMORY_STATE
        req = request.json or {}
        names = req.get('names', [])
        if not names:
            return jsonify({"status": "error", "message": "최소 한 명 이상의 플레이어를 등록해야 합니다."}), 400
        if len(names) > 10:
            return jsonify({"status": "error", "message": "플레이어는 최대 10명까지 등록할 수 있습니다."}), 400
            
        with file_lock:
            # 0. ⚠️ 방송 시작도 장부를 지우므로, 지우기 전에 지난 기록을 영구 보관한다.
            session_label = time.strftime('%Y-%m-%d %H:%M:%S') + " 방송 시작 전"
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(db_query("""
                        INSERT INTO donation_archive
                            (archived_at, session_label, timestamp, name, amount, current_total, message, source, tx_id)
                        SELECT ?, ?, timestamp, name, amount, current_total, message, source, tx_id
                        FROM donation_history
                    """), (time.strftime('%Y-%m-%d %H:%M:%S'), session_label))
            except Exception as arch_e:
                print(f"❌ [장부 보관 실패 - 방송 시작 중단] {arch_e}")
                return jsonify({"status": "error",
                                "message": f"장부 백업에 실패해 방송 시작을 중단했습니다: {arch_e}"}), 500

            # 1. Clear database tables (donation history, snapshots, players)
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(db_query("DELETE FROM players"))
                cursor.execute(db_query("DELETE FROM donation_history"))
                cursor.execute(db_query("DELETE FROM snapshots"))
                # Delete kv_store keys that are NOT persistent configurations
                cursor.execute(
                    db_query("DELETE FROM kv_store WHERE key NOT IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"), 
                    ('theme', 'neon_speed', 'saved_colors', 'target_goal', 'account', 'effect_rules', 'screen_effect', 'ticker_enabled', 'ticker_speed', 'ticker_text', 'totp_secret')
                )
            
            # 2. Get current state from database (which will have only configurations preserved)
            state = load_data()
            
            # 3. Set broadcast_active to True and initialize players
            state['broadcast_active'] = True
            state['bjs'] = [{"name": name.strip(), "score": 0, "contribution": 0} for name in names if name.strip()]
            state['bottom_fixed']['score'] = 0
            state['reaction_mode'] = False
            state['match_data'] = {"active": False, "players": [], "time_left_ms": 180000, "is_running": False}
            state['pending_donations'] = []
            state['latest_donation'] = {"name": "", "amount": 0, "message": "", "time": 0}
            state['extra_game_active'] = False
            state['extra_bjs'] = []
            state['roulette_enabled'] = False
            if 'roulette' in state:
                state['roulette']['winner_name'] = None
                state['roulette']['is_spinning'] = False
                state['roulette']['select_name'] = ""
                state['roulette']['select_index'] = -1
            state['logs'] = []
            state['match_logs'] = []
            reset_session_keys(state)

            # kv_store 행을 위에서 지웠으므로 전체 키를 다시 기록해야 설정이 살아남는다
            
            save_data(state, is_initial=True, sync=True)
            broadcast_event('update', state)
            
        return jsonify({"status": "success", "message": "방송이 활성화되었습니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
# 📋 수동 조작 이력 조회 API
# ==========================================
@app.route('/api/manual_logs', methods=['GET'])
def get_manual_logs():
    try:
        source_filter = request.args.get('source', 'all')  # all, mobile, toonation
        name_filter = request.args.get('name', '').strip()
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(200, max(10, int(request.args.get('per_page', 50))))
        export_csv = request.args.get('export', '') == 'csv'
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Build WHERE clause
            conditions = []
            params = []
            if source_filter == 'mobile':
                conditions.append("source = " + ("$1" if IS_POSTGRES else "?"))
                params.append("mobile")
            elif source_filter == 'toonation':
                conditions.append("source = " + ("$1" if IS_POSTGRES else "?"))
                params.append("toonation")
            
            if name_filter:
                param_idx = len(params) + 1
                if IS_POSTGRES:
                    conditions.append(f"name LIKE ${param_idx}")
                else:
                    conditions.append("name LIKE ?")
                params.append(f"%{name_filter}%")
            
            where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            
            # Get total count
            count_q = f"SELECT COUNT(*) FROM donation_history{where_clause}"
            if IS_POSTGRES:
                # Replace $N placeholders for count query
                pg_count_q = count_q
                for i in range(len(params)):
                    pg_count_q = pg_count_q.replace(f"${i+1}", "%s", 1)
                cursor.execute(pg_count_q, params)
            else:
                cursor.execute(count_q, params)
            total_count = cursor.fetchone()[0]
            
            # CSV Export mode
            if export_csv:
                data_q = f"SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history{where_clause} ORDER BY id DESC"
                if IS_POSTGRES:
                    pg_data_q = data_q
                    for i in range(len(params)):
                        pg_data_q = pg_data_q.replace(f"${i+1}", "%s", 1)
                    cursor.execute(pg_data_q, params)
                else:
                    cursor.execute(data_q, params)
                rows = cursor.fetchall()
                
                import io, csv
                output = io.StringIO()
                output.write('\ufeff')  # BOM for Excel
                writer = csv.writer(output)
                writer.writerow(['ID', '시간', '이름', '변동량', '누적점수', '메시지', '출처'])
                for r in rows:
                    writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6]])
                
                from flask import Response
                return Response(
                    output.getvalue(),
                    mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=score_log_{time.strftime("%Y%m%d_%H%M%S")}.csv'}
                )
            
            # Paginated fetch
            offset = (page - 1) * per_page
            if IS_POSTGRES:
                param_idx_limit = len(params) + 1
                param_idx_offset = len(params) + 2
                data_q = f"SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history{where_clause} ORDER BY id DESC LIMIT ${param_idx_limit} OFFSET ${param_idx_offset}"
                pg_data_q = data_q
                all_params = params + [per_page, offset]
                for i in range(len(all_params)):
                    pg_data_q = pg_data_q.replace(f"${i+1}", "%s", 1)
                cursor.execute(pg_data_q, all_params)
            else:
                data_q = f"SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history{where_clause} ORDER BY id DESC LIMIT ? OFFSET ?"
                cursor.execute(data_q, params + [per_page, offset])
            
            rows = cursor.fetchall()
            logs = []
            for r in rows:
                logs.append({
                    'id': r[0], 'timestamp': r[1], 'name': r[2],
                    'amount': r[3], 'current_total': r[4],
                    'message': r[5], 'source': r[6]
                })
        
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        return jsonify({
            'status': 'success',
            'logs': logs,
            'page': page,
            'per_page': per_page,
            'total_count': total_count,
            'total_pages': total_pages
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# ⏪ 시간 여행 복원 API (오늘 지정 시간 기준)
# ==========================================
@app.route('/api/time_machine/restore_by_time', methods=['POST'])
def restore_by_time():
    try:
        req_data = request.json
        time_str = req_data.get('time', '').strip()
        if not time_str:
            return jsonify({'status': 'error', 'message': '이동할 시간을 입력해주세요.'}), 400
            
        today_str = time.strftime('%Y-%m-%d')
        target_ts = f"{today_str} {time_str}"
        if len(time_str.split(':')) == 2:
            target_ts += ':00'
            
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("""
                SELECT name, current_total 
                FROM donation_history 
                WHERE id IN (
                    SELECT MAX(id) 
                    FROM donation_history 
                    WHERE timestamp <= ? 
                    GROUP BY name
                )
            """), (target_ts,))
            history_rows = cursor.fetchall()
            
            if not history_rows:
                return jsonify({'status': 'error', 'message': f'[{target_ts}] 시점 또는 그 이전에 기록된 장부가 없습니다.'}), 404
                
            cursor.execute(db_query("SELECT key, value FROM kv_store WHERE key = 'target_goal'"))
            goal_row = cursor.fetchone()
            target_goal = json.loads(goal_row[1]) if goal_row else 50000
            
        import copy
        current_state = load_data()
        restored_state = copy.deepcopy(current_state)
        restored_state['target_goal'] = target_goal
        restored_state['bjs'] = []
        
        for name, score in history_rows:
            restored_state['bjs'].append({
                'name': name,
                'score': score,
                'contribution': score
            })
            
        restored_state['bjs'].sort(key=lambda x: x['contribution'], reverse=True)
        
        global MEMORY_STATE
        MEMORY_STATE = restored_state
        save_data(restored_state, sync=True)
        broadcast_event('update', restored_state)
        
        return jsonify({
            'status': 'success',
            'message': f'⏳ [시간여행 성공]\n오늘 {time_str} 시점의 플레이어 상태로 안전하게 원복되었습니다!'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# 🎛️ 스트림덱 전용 원터치 제어 API (GET 방식)
# ==========================================
@app.route('/api/streamdeck/save', methods=['GET'])
def sd_save():
    try:
        state = load_data()
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        label = "스트림덱 수동 백업"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                db_query("INSERT INTO snapshots (timestamp, state_json, summary) VALUES (?, ?, ?)"),
                (timestamp, json.dumps(state, ensure_ascii=False), label)
            )
        print("  💾 [스트림덱 명령] 수동 스냅샷 세이브포인트 저장 완료!")
        return jsonify({"status": "success", "message": "스냅샷 저장 완료"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/streamdeck/neon', methods=['GET'])
def sd_neon():
    try:
        color = request.args.get('color', 'RAINBOW').upper()
        # 6자리 16진수 색상 코드인 경우 #을 자동으로 붙여줌
        if len(color) == 6 and all(c in '0123456789ABCDEF' for c in color):
            color = '#' + color
            
        with file_lock:
            state = load_data()
            state['effect_trigger'] = {
                'time': int(time.time() * 1000),
                'color': color
            }
            if color != 'OFF':
                state['reaction_mode'] = True
            else:
                state['reaction_mode'] = False
                
            save_data(state)
            broadcast_event('update', state)
        print(f"  💡 [스트림덱 명령] 네온 이펙트 조명 전환: {color}")
        return jsonify({"status": "success", "color": color})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 🎵 커스텀 리액션 플랫폼 API (영구 보존형)
# ==========================================
import uuid

@app.route('/uploads/<file_id>', methods=['GET'])
def get_reaction_file(file_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT filename, content_type, file_data FROM reaction_files WHERE id = ?"), (file_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "File not found"}), 404
            
            filename, content_type, file_data = row
            data_bytes = bytes(file_data)
            
            import os
            from flask import send_file
            
            # Save file to a local cache directory to serve as a real static file.
            # This perfectly resolves HTML5 audio Range requests and buffering stream aborts.
            cache_dir = os.path.join(app.root_path, 'media_cache')
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, file_id)
            
            if not os.path.exists(cache_path):
                with open(cache_path, 'wb') as f:
                    f.write(data_bytes)
            
            response = send_file(
                cache_path,
                mimetype=content_type,
                as_attachment=False,
                download_name=filename,
                conditional=True
            )
            response.headers.set('Cache-Control', 'public, max-age=31536000')
            return response
    except Exception as e:
        print(f"Error serving reaction file {file_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/list', methods=['GET'])
def get_reactions_list():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT id, title, amount, audio_file_id, image_file_id FROM reaction_items ORDER BY id ASC"))
            rows = cursor.fetchall()
            reactions = []
            for r in rows:
                reactions.append({
                    "id": r[0],
                    "title": r[1],
                    "amount": r[2],
                    "audio_url": f"/uploads/{r[3]}" if r[3] else "",
                    "image_url": f"/uploads/{r[4]}" if r[4] else ""
                })
            return jsonify(reactions)
    except Exception as e:
        print(f"Error listing reactions: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/add', methods=['POST'])
def add_reaction():
    try:
        title = request.form.get('title', '').strip()
        amount = int(request.form.get('amount', 0))
        
        if not title:
            return jsonify({"status": "error", "message": "제목을 입력해주세요."}), 400
            
        audio_file = request.files.get('audio')
        image_file = request.files.get('image')
        
        audio_file_id = None
        image_file_id = None
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if audio_file and audio_file.filename:
                audio_file_id = f"aud_{uuid.uuid4().hex}"
                audio_data = audio_file.read()
                cursor.execute(
                    db_query("INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (?, ?, ?, ?)"),
                    (audio_file_id, audio_file.filename, audio_file.content_type, psycopg2.Binary(audio_data) if IS_POSTGRES else audio_data)
                )
                
            if image_file and image_file.filename:
                image_file_id = f"img_{uuid.uuid4().hex}"
                image_data = image_file.read()
                cursor.execute(
                    db_query("INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (?, ?, ?, ?)"),
                    (image_file_id, image_file.filename, image_file.content_type, psycopg2.Binary(image_data) if IS_POSTGRES else image_data)
                )
                
            cursor.execute(
                db_query("INSERT INTO reaction_items (title, amount, audio_file_id, image_file_id) VALUES (?, ?, ?, ?)"),
                (title, amount, audio_file_id, image_file_id)
            )
            conn.commit()
            
        return jsonify({"status": "success", "message": "리액션 곡 등록 완료!"})
    except Exception as e:
        print(f"Error adding reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/delete/<int:item_id>', methods=['POST', 'DELETE'])
def delete_reaction(item_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT audio_file_id, image_file_id FROM reaction_items WHERE id = ?"), (item_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Reaction item not found"}), 404
                
            audio_file_id, image_file_id = row
            
            cursor.execute(db_query("DELETE FROM reaction_items WHERE id = ?"), (item_id,))
            
            if audio_file_id:
                cursor.execute(db_query("DELETE FROM reaction_files WHERE id = ?"), (audio_file_id,))
            if image_file_id:
                cursor.execute(db_query("DELETE FROM reaction_files WHERE id = ?"), (image_file_id,))
                
            conn.commit()
            
        return jsonify({"status": "success", "message": "리액션 곡 삭제 완료!"})
    except Exception as e:
        print(f"Error deleting reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/play/<int:item_id>', methods=['POST'])
def play_reaction(item_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT title, audio_file_id, image_file_id FROM reaction_items WHERE id = ?"), (item_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Reaction item not found"}), 404
                
            title, audio_file_id, image_file_id = row
            audio_url = f"/uploads/{audio_file_id}" if audio_file_id else ""
            image_url = f"/uploads/{image_file_id}" if image_file_id else ""
            
            with file_lock:
                state = load_data()
                reaction_uuid = f"rq_{uuid.uuid4().hex}"
                state['reaction_queue'].append({
                    "id": reaction_uuid,
                    "item_id": item_id,
                    "title": title,
                    "audio_url": audio_url,
                    "image_url": image_url,
                    "donator": "수동송출",
                    "message": ""
                })
                state['reaction_mode'] = True
                save_data(state)
                broadcast_event('update', state)
                
        return jsonify({"status": "success", "message": "방송 송출 완료!"})
    except Exception as e:
        print(f"Error playing reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/next', methods=['POST'])
def next_reaction():
    try:
        data = request.get_json(silent=True) or {}
        pop_id = data.get('id')
        
        with file_lock:
            state = load_data()
            queue = state.get('reaction_queue', [])
            
            if queue:
                # ID가 지정된 경우: 첫 번째 아이템의 ID가 일치할 때만 pop (이중 pop 방지)
                # ID가 없는 경우: 기존 방식대로 무조건 pop (하위 호환)
                if not pop_id or queue[0].get('id') == pop_id:
                    queue.pop(0)
                
            if not queue:
                state['reaction_mode'] = False
                
            save_data(state)
            broadcast_event('update', state)
        # 오버레이가 이 응답의 state 를 그대로 써서 다음 시그니처를 즉시 재생한다
        # (예전엔 pop 후 /api/data 를 한 번 더 불러 왕복이 2회였고, 그 사이 SSE 와 겹쳐
        #  대기열이 깊을 때 재생이 불안정했다. 이제 왕복 1회로 줄여 겹침/지연을 낮춘다.)
        return jsonify({"status": "success", "message": "Popped reaction", "state": state})
    except Exception as e:
        print(f"Error in next_reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/stop', methods=['POST'])
def stop_reaction():
    try:
        with file_lock:
            state = load_data()
            state['reaction_queue'] = []
            state['reaction_mode'] = False
            save_data(state)
            broadcast_event('update', state)
            broadcast_event('reaction_stop', {})
        return jsonify({"status": "success", "message": "All reactions stopped"})
    except Exception as e:
        print(f"Error in stop_reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/slot/spin', methods=['POST'])
def api_slot_spin():
    try:
        data = request.json or {}
        winner = data.get('winner')
        candidates = data.get('candidates', [])

        if not winner:
            # winner 미지정 시: 서버가 무작위 선택.
            # 이번 방송용으로 고른 후보(slot_pool)가 있으면 그 안에서만 뽑는다.
            try:
                sigs = supabase_list_signatures()
            except Exception as e:
                return jsonify({"status": "error", "message": f"시그니처 조회 실패: {e}"}), 500
            if not sigs:
                return jsonify({"status": "error", "message": "등록된 시그니처가 없습니다."}), 400

            pool_ids = load_data().get('slot_pool') or []
            if pool_ids:
                pool_set = {int(i) for i in pool_ids}
                filtered = [s for s in sigs if s.get('id') in pool_set]
                if filtered:
                    sigs = filtered
                else:
                    print("⚠️ [슬롯] 선택된 후보가 목록에 없어 전체에서 뽑습니다.")

            import random
            winner = random.choice(sigs)
            candidates = sigs

        # 릴이 도는 동안 슬롯 위젯이 확실히 보이도록 켠다.
        # (오버레이는 매 업데이트마다 slot_enabled로 표시를 다시 칠하므로 상태로 켜야 한다)
        with file_lock:
            state = load_data()
            state['slot_enabled'] = True
            save_data(state)
            broadcast_event('update', state)

        broadcast_event('slot_spin', {
            "type": "slot_spin",
            "event": "slot_spin",
            "winner": winner,
            "candidates": candidates
        })

        # 당첨 발표(약 3.3초) 뒤에 슬롯을 끄고 시그니처를 리액션 큐에 넣는다.
        # 큐를 태우면 reaction_mode가 켜지고, 재생이 끝나면 큐가 비면서 자동으로 꺼진다.
        # 오버레이는 비인증이라 스스로 재생 API를 부를 수 없으므로 서버가 예약한다.
        threading.Timer(SLOT_RESULT_DELAY_SEC, _slot_finish, args=(winner,)).start()

        return jsonify({"status": "success", "winner": winner})
    except Exception as e:
        print(f"Error spinning slot: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/queue/remove/<string:rq_id>', methods=['POST'])
def remove_from_queue(rq_id):
    try:
        with file_lock:
            state = load_data()
            queue = state.get('reaction_queue', [])
            if queue:
                is_currently_playing = (queue[0]['id'] == rq_id)
                state['reaction_queue'] = [item for item in queue if item['id'] != rq_id]
                
                if is_currently_playing:
                    broadcast_event('reaction_stop', {'id': rq_id})
                    
                if not state['reaction_queue']:
                    state['reaction_mode'] = False
                    
                save_data(state)
                broadcast_event('update', state)
        return jsonify({"status": "success", "message": "Removed from queue"})
    except Exception as e:
        print(f"Error in remove_from_queue: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/pending/remove/<don_id>', methods=['POST'])
def remove_pending_donation(don_id):
    """승인 대기함에서 특정 후원 한 건을 제거한다(전용 read-modify-write).
       pending_donations 는 /api/data 에서 서버 소유로 보호되므로, 승인/무시 시 이 엔드포인트로만 제거해야
       후원이 막 들어온 순간 조종실이 점수를 눌러도 새 후원이 안 사라진다."""
    try:
        with file_lock:
            state = load_data()
            pend = state.get('pending_donations', []) or []
            state['pending_donations'] = [d for d in pend if d.get('id') != don_id]
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success", "message": "Removed from pending"})
    except Exception as e:
        print(f"Error in remove_pending_donation: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 🖥️ GUI 관리자 및 로그인 창
# ==========================================
def start_self_ping():
    import urllib.request
    import threading
    import time
    
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if not url:
        return
        
    def ping_loop():
        # 즉시 초기화 로그 출력
        print(f"⏰ [Self-Ping] Daemon initialized for: {url}", flush=True)
        # 서버 시작 후 첫 30초 대기
        time.sleep(30)
        print(f"⏰ [Self-Ping] Starting self-ping loop...", flush=True)
        while True:
            try:
                req = urllib.request.Request(
                    url,
                    headers={'User-Agent': 'LiveMaster-KeepAwake/1.0'}
                )
                with urllib.request.urlopen(req, timeout=15) as response:
                    print(f"⏰ [Self-Ping] Ping sent successfully, response code: {response.getcode()}", flush=True)
            except Exception as e:
                print(f"⚠️ [Self-Ping] Ping failed: {e}", flush=True)
            time.sleep(600)  # 10분마다 실행 (Render 무료 비활성화 임계치인 15분보다 짧음)
            
    ping_thread = threading.Thread(target=ping_loop, daemon=True)
    ping_thread.start()

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    start_self_ping()
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def has_gui_support():
    if os.environ.get('HEADLESS') or os.environ.get('DATABASE_URL'):
        return False
    if tk is None:
        return False
    try:
        temp_root = tk.Tk()
        temp_root.destroy()
        return True
    except Exception:
        return False

def run_login_gui():
    login_success = [False]
    
    def check_login():
        p = entry_pass.get().strip()
        if p == '0508':
            login_success[0] = True
            login_win.destroy()
        else:
            messagebox.showerror('보안 인증 실패', '비밀번호가 올바르지 않습니다!')
            entry_pass.delete(0, tk.END)
            entry_pass.focus()
            
    def on_login_closing():
        login_win.destroy()
        sys.exit(0)
        
    login_win = tk.Tk()
    login_win.title('🔒 라이브 마스터 서버 기동 인증')
    login_win.geometry('380x220')
    login_win.configure(bg='#111113')
    login_win.resizable(False, False)
    
    ws = login_win.winfo_screenwidth()
    hs = login_win.winfo_screenheight()
    x = (ws / 2) - 190.0
    y = (hs / 2) - 110.0
    login_win.geometry(f'380x220+{int(x)}+{int(y)}')
    
    try:
        login_win.attributes('-alpha', 0.96)
    except:
        pass
        
    title = tk.Label(login_win, text='🔒 SERVER BOOT AUTH', fg='#00ffcc', bg='#111113', font=('Consolas', 15, 'bold'))
    title.pack(pady=20)
    
    frame_pass = tk.Frame(login_win, bg='#111113')
    frame_pass.pack(pady=10)
    
    lbl_pass = tk.Label(frame_pass, text='인증 PW : ', fg='#ffffff', bg='#111113', font=('Malgun Gothic', 10, 'bold'), width=8, anchor='e')
    lbl_pass.pack(side=tk.LEFT)
    
    entry_pass = tk.Entry(frame_pass, show='*', fg='white', bg='#222225', insertbackground='white', font=('Malgun Gothic', 10), width=18, relief='flat')
    entry_pass.pack(side=tk.LEFT)
    entry_pass.focus()
    
    entry_pass.bind('<Return>', lambda e: check_login())
    
    btn_login = tk.Button(login_win, text='🔓 서버 엔진 기동', command=check_login, fg='#000000', bg='#00ffcc', activebackground='#00cca3', font=('Malgun Gothic', 10, 'bold'), width=20, height=2, relief='flat')
    btn_login.pack(pady=15)
    
    login_win.protocol('WM_DELETE_WINDOW', on_closing_exit if 'on_closing_exit' in globals() else on_login_closing)
    login_win.mainloop()
    
    return login_success[0]

def open_link(url):
    webbrowser.open(url)

def on_closing():
    if messagebox.askokcancel('서버 종료', '방송 서버를 완전히 종료하시겠습니까?\n(정산 기능 및 오버레이 송출이 중단됩니다)'):
        root.destroy()
        sys.exit(0)

if __name__ == '__main__':
    init_db()
    if not has_gui_support():
        print("🖥️ [헤드리스 모드] GUI 모드를 사용할 수 없는 환경이거나 클라우드 배포 상태입니다. 백엔드 Flask 서버만 무중단 구동합니다.")
        run_flask()
    else:
        if run_login_gui():
            flask_thread = threading.Thread(target=run_flask, daemon=True)
            flask_thread.start()
            
            root = tk.Tk()
            root.title('💎 라이브 마스터 순정 방송서버')
            root.geometry('460x340')
            root.configure(bg='#111113')
            root.resizable(False, False)
            
            try:
                root.attributes('-alpha', 0.96)
            except:
                pass
                
            ws = root.winfo_screenwidth()
            hs = root.winfo_screenheight()
            x = (ws / 2) - 230.0
            y = (hs / 2) - 170.0
            root.geometry(f'460x420+{int(x)}+{int(y)}')
            
            # UI 구성
            lbl_logo = tk.Label(root, text='💎 LIVE MASTER SERVER', fg='#00ffcc', bg='#111113', font=('Consolas', 18, 'bold'))
            lbl_logo.pack(pady=15)
            
            port = int(os.environ.get('PORT', 5000))
            lbl_status = tk.Label(root, text=f'🟢 실시간 방송 정산 엔진 구동 중 (Port: {port})', fg='#ffffff', bg='#111113', font=('Malgun Gothic', 11, 'bold'))
            lbl_status.pack(pady=5)
            
            lbl_info = tk.Label(root, text='투네이션의 모든 수동 후원이 대기함으로 입하되며,\n조종실 및 방송 오버레이가 한치의 오차 없이 구동됩니다.', fg='#8e8e93', bg='#111113', font=('Malgun Gothic', 9), justify='center')
            lbl_info.pack(pady=5)
            
            # 🔑 OTP 보안 등록 정보 추가
            otp_sec = get_or_create_totp_secret()
            lbl_otp = tk.Label(root, text='🔑 모바일 OTP 보안키: ' + otp_sec, fg='#ff9f0a', bg='#111113', font=('Consolas', 11, 'bold'))
            lbl_otp.pack(pady=5)
            
            lbl_otp_info = tk.Label(root, text=f'* 최초 등록 방법: 스마트폰 구글 OTP 앱에서 위 키를 입력하거나,\n서버 PC 브라우저로 http://localhost:{port}/setup 에 접속해 QR 코드를 스캔하세요.', fg='#8e8e93', bg='#111113', font=('Malgun Gothic', 8), justify='center')
            lbl_otp_info.pack(pady=5)
            
            frame_btns = tk.Frame(root, bg='#111113')
            frame_btns.pack(pady=20)
            
            btn_ctrl = tk.Button(frame_btns, text='💻 제어 센터 (조종실)', command=lambda: open_link(f'http://localhost:{port}/controller'), fg='#000000', bg='#00ffcc', activebackground='#00cca3', font=('Malgun Gothic', 10, 'bold'), width=18, height=2, relief='flat')
            btn_ctrl.pack(side=tk.LEFT, padx=10)
            
            btn_ovr = tk.Button(frame_btns, text='🎬 송출용 오버레이', command=lambda: open_link(f'http://localhost:{port}/overlay'), fg='#ffffff', bg='#333336', activebackground='#444448', font=('Malgun Gothic', 10, 'bold'), width=18, height=2, relief='flat')
            btn_ovr.pack(side=tk.LEFT, padx=10)
            
            root.protocol('WM_DELETE_WINDOW', on_closing)
            root.mainloop()
