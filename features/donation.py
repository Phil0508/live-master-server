# -*- coding: utf-8 -*-
"""🛡️ 후원 접수 — 투네이션 후원을 안전하게 받아 이름 · 금액을 읽고 대기줄에 올린다. 대기 후원 빼기.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import collections
import os
import re
import secrets
import threading
import time
import uuid
from flask import jsonify, request
import server  # 연습 서버가 가짜로 바꿔 끼우는 시그니처 조회는 부를 때마다 server 에서 찾는다
from server import (
    LAST_DB_ERROR, NOTICE_DONORS_MAX, NOTICE_DONOR_NAME_MAX, PENDING_WARN_AT, _as_int,
    _norm_donor, _sig_min_amount, app, broadcast_event, db_query, enqueue_signature,
    excluded_names, file_lock, get_db_connection, is_duplicate_donation, load_data, now_hms,
    request_is_authed, request_is_from_this_server, save_data,
)


# ==========================================
# 🛡️ 투네이션 후원 안전 접수 및 파서
# ==========================================

# 메시지 앞에 붙은 "닉네임: 내용" 을 대리 후원 표기로 볼지 판정한다.
#
# ⚠️ 예전에는 '콜론이 있고 앞이 15자 이하'면 무조건 이름으로 갈아끼웠다. 그래서
#    "수고하셨습니다 :)" 는 후원자가 '수고하셨습니다' 가 되고, "10:30에 봐요" 는 '10',
#    "목표: 100만" 은 '목표' 가 됐다. 이모티콘과 시각 표기가 흔해 자주 터졌고,
#    바뀐 이름이 그대로 대기함·장부·순위에 박혀 되돌릴 방법도 없었다.
#    아래 조건은 전부 '그건 이름일 리 없다'가 확실한 경우만 걸러낸다.
_EMOTICON_AFTER_COLON = set(')(dDpPoO3/\\|<>^_-*;')


# 플랫폼이 이름을 제대로 안 준 경우들. 이때만 메시지에서 이름을 가져온다.
_ANONYMOUS_NAMES = {'', '-', '익명', '익명의 후원자', '익명후원자', '무명', '후원자',
                    'anonymous', 'anon', 'unknown'}


def name_is_missing(name):
    """플랫폼이 준 이름이 '사실상 없는' 것인가."""
    return str(name or '').strip().lower() in _ANONYMOUS_NAMES


def looks_like_proxy_name(prefix, rest):
    """prefix 가 '대리 후원 닉네임'으로 보이는가."""
    if not prefix or len(prefix) > 12:
        return False            # 너무 길면 이름이 아니라 문장이다
    if not rest:
        return False            # 콜론 뒤가 비었으면 이름이 아니다
    if rest[0] in _EMOTICON_AFTER_COLON:
        return False            # :) :D :3 :/ ... 이모티콘
    if prefix.isdigit():
        return False            # 10:30 같은 시각·숫자
    if any(ch in prefix for ch in '.,!?~…'):
        return False            # 문장 부호가 섞였으면 이름이 아니다
    if not any(ch.isalnum() for ch in prefix):
        return False            # 글자가 하나도 없으면 이름이 아니다
    return True
_HEX6 = re.compile(r'^#[0-9A-Fa-f]{6}$')
_HEX16 = re.compile(r'^[0-9a-f]{16}$')
_TITLE_ICON_PREFIX = 'https://cache.cdn.toona.xyz/prod/uploaded/__special_title_img__/'


def _donor_extras(new_don):
    """🏷️ 리스너가 붙여 보낸 칭호 · 레벨 · VIP · 번호표를 다시 다듬는다(대표님 2026-10-08).
       돌려받는 값: (화면에 실어도 되는 것, 대기함 · 장부에만 둘 것). 번호표는 화면 쪽에 절대 안 싣는다.
       ⚠️ 칭호 그림은 투네이션 칭호 그림 주소로 시작할 때만 받는다(아무 주소나 방송판에 띄우지 않게)."""
    pub, priv = {}, {}
    t = new_don.get('title')
    if isinstance(t, dict):
        nm = ' '.join(str(t.get('name') or '').split())[:24]
        if nm:
            tt = {'name': nm}
            col = str(t.get('color') or '').strip()
            if _HEX6.match(col):
                tt['color'] = col.upper()
            icon = str(t.get('icon') or '')
            if icon.startswith(_TITLE_ICON_PREFIX) and len(icon) <= 300 and re.fullmatch(r'[A-Za-z0-9_\-=./:]+', icon):
                tt['icon'] = icon
            pub['donor_title'] = tt
    try:
        lv = int(new_don.get('level'))
        if 0 < lv < 1000:
            pub['donor_level'] = lv
    except (TypeError, ValueError):
        pass
    vip = ' '.join(str(new_don.get('vip') or '').split())[:12]
    if vip:
        priv['vip'] = vip
    key = str(new_don.get('donor_key') or '')
    if _HEX16.match(key):
        priv['donor_key'] = key
    return pub, priv


def donation_source_allowed():
    """후원 접수를 받아줄 상대인가.

    ⚠️ 이 경로는 예전에 완전히 열려 있었다. 크롬 유저스크립트가 바깥에서 쏴야 했기 때문인데,
       그 대가로 '주소만 알면 누구나 100만원 후원을 만들어낼 수 있는' 상태였다.
       가짜 후원은 대기함에 쌓이고, 금액에 맞는 시그니처가 방송에 재생되고, 장부에도 남는다.
    ⚠️ 이제 투네이션 리스너가 같은 서버 안에서(127.0.0.1) 부르므로 바깥을 막을 수 있다.
       유저스크립트를 다시 쓰려면 DONATION_KEY 를 정하고 스크립트에 같은 값을
       X-Donation-Key 헤더로 넣으면 된다.
    """
    if request_is_from_this_server():
        return True                      # 서버 안의 리스너
    if request_is_authed():
        return True                      # 조종실에서 수동 송출
    key = (os.environ.get('DONATION_KEY') or '').strip()
    if key:
        sent = (request.headers.get('X-Donation-Key') or '').strip()
        if sent and secrets.compare_digest(sent, key):
            return True
    return False


# ══ 🔒 같은 tx_id 가 두 번 세어지지 않게 — '처리 중' · '처리 끝' 표 ══
#
# ⚠️ [실제로 두 번 세어지던 구멍] 예전에는 tx_id 중복을 장부(donation_history)로만 봤다.
#    그런데 장부에 줄이 생기는 건 처리 **맨 끝**(시그니처 매칭 뒤, 락 안)이고, 그 매칭은
#    Supabase 왕복이라 느리면 18초까지 걸린다. 리스너는 10초 만에 포기하고 0.6초 뒤
#    **같은 tx_id** 로 다시 보냈다 → 두 요청 다 장부 검사를 통과(아직 줄이 없다) →
#    대기함 2건 · 후원 순위 2배 · 시그니처 2번. 리스너 후원(toon_)은 12초 내용 필터도
#    건너뛰므로 막을 곳이 하나도 없었다.
#    그래서 느린 일을 하기 **전에** tx_id 를 '처리 중' 으로 찍는다. 확인과 찍기는 한 자물쇠 안에서
#    한 번에 한다 — 둘 사이가 벌어지면 똑같은 구멍이 다시 생긴다.
# ⚠️ file_lock 이 아니라 전용 자물쇠를 쓴다. 여기서 하는 일은 표 한 칸 보고 적기뿐이라
#    원자성은 똑같고, 점수 버튼 · 큐 넘기기가 쓰는 file_lock 을 후원마다 한 번 더 잡지 않아도 된다.
# ⚠️ 처리가 **실패하면 '처리 중' 을 풀어준다**(끝 표에는 안 넣는다). 서버가 도중에 죽거나 예외가 나면
#    리스너 대기줄이 같은 tx_id 로 다시 보내는데, 그때는 진짜로 처리돼야 한다.
# ⚠️ 서버가 여러 프로세스로 뜨면 이 표는 프로세스마다 따로다. 지금은 한 프로세스(file_lock 도
#    threading.Lock)라 괜찮다. 여러 개로 늘리면 장부 tx_id 에 UNIQUE 를 거는 게 먼저다.
_tx_lock = threading.Lock()
_tx_inflight = set()
_tx_done = collections.OrderedDict()     # tx_id → 끝난 시각. 오래된 것부터 흘려보낸다
_TX_DONE_MAX = 5000


def _tx_claim(tx):
    """tx_id 를 '처리 중' 으로 찍는다. 'ok'(찍었다) · 'busy'(다른 요청이 처리 중) · 'done'(이미 끝났다)."""
    with _tx_lock:
        if tx in _tx_done:
            return 'done'
        if tx in _tx_inflight:
            return 'busy'
        _tx_inflight.add(tx)
        return 'ok'


def _tx_release(tx, handled):
    """'처리 중' 을 푼다. handled 면 '처리 끝' 에 올려 다음 재전송을 장부까지 안 가고 거른다."""
    with _tx_lock:
        _tx_inflight.discard(tx)
        if handled:
            _tx_done[tx] = time.time()
            while len(_tx_done) > _TX_DONE_MAX:
                _tx_done.popitem(last=False)


# ══ 📒 장부엔 있는데 상태(대기함)엔 없는 후원 되살리기 ══
#
# ⚠️ 장부 INSERT 는 상태 저장보다 **먼저** 끝난다(상태는 락을 놓은 뒤 DB 에 쓰인다).
#    그 사이에 서버가 재시작되면 장부엔 줄이 있는데 대기함 · 순위엔 없다. 리스너가 같은 tx_id 로
#    다시 보내도 '장부에 있으니 중복' 으로 버려져, 그 후원은 대기함에 영영 안 나타났다(돈은 받았는데 점수 못 줌).
#    그래서 상태 안에도 '이 tx_id 는 상태까지 들어갔다' 는 표시를 남긴다.
# ⚠️ 표시는 latest_donation 안에 둔다. 새 칸을 만들면 조종실이 상태를 통째로 보낼 때 낡은 사본이
#    그 칸을 덮어써(서버 소유 칸이 아니다) '들어간 적 없다' 로 잘못 읽고 **두 번 넣는다**.
#    latest_donation 은 서버 소유 칸이라 조종실이 못 덮고, 방송 시작 · 종료 때 장부와 같이 비워진다.
# ⚠️ 목록은 짧게(방송 화면으로도 같이 나간다). 잘려 나간 것을 '안 들어갔다' 로 착각하지 않게
#    'since'(이 시각 이후 장부 줄만 판단한다)를 같이 적는다 — 처음 배포한 날의 옛 장부 줄도 이걸로 걸러진다.
_TX_LOG_MAX = 60


def _tx_log_add(latest, prev_latest, tx):
    """새 latest_donation 에 앞 목록을 이어 붙이고 tx 를 적는다."""
    old = (prev_latest or {}).get('tx_log') if isinstance(prev_latest, dict) else None
    now = int(time.time())
    if isinstance(old, dict) and isinstance(old.get('ids'), list):
        ids = [x for x in old['ids'] if isinstance(x, list) and len(x) == 2]
        since = int(old.get('since') or now)
    else:
        ids, since = [], now
    if tx:
        ids.append([tx, now])
    while len(ids) > _TX_LOG_MAX:
        gone = ids.pop(0)
        since = max(since, int(gone[1]) + 1)     # 잘린 것보다 뒤만 판단한다
    latest['tx_log'] = {'since': since, 'ids': ids}


def _tx_state_missing(state, tx, ledger_ts):
    """장부에 있는 tx 가 상태에는 안 들어갔는가. 확실할 때만 True — 애매하면 False(= 평소처럼 중복으로 버린다)."""
    log_ = (state.get('latest_donation') or {}).get('tx_log')
    if not isinstance(log_, dict) or not isinstance(log_.get('ids'), list):
        return False
    if any(isinstance(x, list) and x and x[0] == tx for x in log_['ids']):
        return False
    try:
        row_at = time.mktime(time.strptime(str(ledger_ts), '%Y-%m-%d %H:%M:%S'))
    except (TypeError, ValueError, OverflowError):
        return False
    return row_at >= int(log_.get('since') or 0) + 1   # 초 단위라 1초 여유를 둔다


@app.route('/api/donation', methods=['POST'])
def receive_donation():
    if not donation_source_allowed():
        print(f"⛔ [후원 접수 거부] 허용되지 않은 곳에서 왔습니다 (ip={request.remote_addr}, "
              f"xff={request.headers.get('X-Forwarded-For')})", flush=True)
        return jsonify({"status": "error",
                        "message": "이 서버에서만 후원을 접수합니다. 바깥에서 보내려면 "
                                   "DONATION_KEY 를 정하고 X-Donation-Key 헤더에 같은 값을 넣으세요."}), 401
    _tx = ''            # 이 요청이 '처리 중' 으로 찍은 tx_id (finally 에서 푼다)
    _handled = False    # 이 tx_id 를 '처리 끝' 으로 볼 것인가 — 실패로 끝나면 False 로 남아 재전송이 통한다
    try:
        new_don = request.get_json(silent=True)
        if not isinstance(new_don, dict):
            return jsonify({"status": "error",
                            "message": "후원 내용(JSON)이 필요합니다"}), 400
        # ⚠️ 금액은 바깥(리스너·템퍼몽키)에서 온다. 숫자가 아니면 그 자리에서 예외가 나
        #    500 이 되고, 보내는 쪽은 '서버가 고장났다'로 보고 계속 재시도한다.
        #    무엇이 잘못됐는지 알려주고 곱게 거절한다.
        amount = _as_int(new_don.get('amount', 0))
        if amount is None:
            return jsonify({"status": "error",
                            "message": "금액(amount)이 숫자가 아닙니다"}), 400
        tx_id = new_don.get('tx_id')
        
        # 1. 음수(0원 미만) 후원 금액 차단 (0원 시그니처 후원 등 허용)
        if amount < 0:
            return jsonify({"status": "error", "message": "Invalid amount"}), 400
            
        # 2-0. 🔒 같은 tx_id 가 지금 처리 중이거나 이미 끝났으면 여기서 끊는다(느린 일보다 먼저 — 위 _tx_claim 설명).
        #      ⚠️ '처리 중' 에 성공(200)을 주면 안 된다. 앞 요청이 그 뒤에 실패하면 보낸 쪽은 '들어갔다' 고
        #         믿고 버려서 후원이 사라진다. 409 로 '잠시 뒤 다시' 를 알리면 리스너는 대기줄에 넣고
        #         10초 뒤 다시 보낸다 — 그때는 '이미 끝남'(200) 이거나, 앞 요청이 실패했으면 새로 처리된다.
        _recover = False     # 장부엔 있는데 상태엔 없는 후원을 되살리는 중인가(장부 줄은 다시 안 적는다)
        if tx_id not in (None, ''):
            _t = str(tx_id).strip()
            _claim = _tx_claim(_t) if _t else 'ok'
            if _claim == 'done':
                return jsonify({"status": "success", "message": "Duplicate donation ignored."})
            if _claim == 'busy':
                print(f"⏳ [같은 후원 처리 중] tx_id={_t} — 409 로 돌려보냅니다(보낸 쪽이 잠시 뒤 다시 보낸다)", flush=True)
                return jsonify({"status": "error", "in_progress": True,
                                "message": "같은 후원을 아직 처리 중입니다 — 잠시 뒤 다시 보내 주세요"}), 409
            _tx = _t

        # 2. tx_id 중복 검사로 중복 처리 차단 (서버를 다시 켠 뒤라 위 표가 비어 있을 때 — 장부가 정본이다)
        if tx_id:
            _row = None
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(db_query("SELECT id, timestamp FROM donation_history WHERE tx_id = ?"), (tx_id,))
                    _row = cursor.fetchone()
            except Exception as dbe:
                print(f"⚠️ [tx_id 중복 확인 오류] {dbe}")
            if _row:
                # 📒 장부 줄은 있는데 상태까지 못 간 후원인가(장부 INSERT 와 상태 저장 사이에 서버가 죽은 경우)
                with file_lock:
                    _missing = _tx_state_missing(load_data(), str(tx_id).strip(), _row[1])
                if not _missing:
                    _handled = True
                    return jsonify({"status": "success", "message": "Duplicate donation ignored."})
                _recover = True
                print(f"🩹 [후원 되살리기] tx_id={tx_id} 는 장부에만 있고 대기함 · 순위엔 없습니다 "
                      f"— 장부 줄은 그대로 두고 대기함 · 순위만 다시 채웁니다", flush=True)

        # 2-b. 재전송 대비: 이름+금액+메시지가 동일한 후원이 아주 짧은 시간 안에
        #      다시 오면 중복으로 간주해 무시한다(시그니처 이중 재생 방지).
        # ⚠️ 예전에는 `if not tx_id:` 였다. 그런데 템퍼몽키 스크립트는 재시도할 때마다
        #    tx_id 를 '새로 만들어' 보낸다. 그래서 응답이 늦어 재시도가 걸리면
        #    tx_id 검사는 통과해버리고(값이 다르니까) 이 검사는 아예 건너뛰어서,
        #    같은 후원이 두 번 들어와 시그니처가 두 번 재생되고 장부에도 두 줄이 남았다.
        #    tx_id 유무와 무관하게 항상 내용 기반으로도 걸러야 한다.
        #    ⚠️ 단, 웹소켓 리스너(tx_id 가 'toon_' 로 시작)가 보낸 것은 예외로 둔다.
        #       리스너는 실패해도 재시도하지 않고, 소켓 재전송은 리스너가 스스로 걸러낸다.
        #       그래서 여기까지 온 리스너 후원은 '진짜로 두 번 쏜 것'이며, 버리면 돈이 사라진다.
        #       (실제 방송에서 같은 사람이 같은 금액·같은 메시지로 연달아 쏘자 두 번째가 날아갔다)
        #       이 예외는 템퍼몽키를 끄고 리스너만 쓸 때를 전제로 한다. 둘을 같이 켜면
        #       알림창 애니메이션이 긴 후원에서 중복이 통과할 수 있으니 한쪽만 쓸 것.
        from_listener = str(tx_id or '').startswith('toon_')
        # 🧑‍💼 로그인한 운영자가 조종실 · 후원 콘솔에서 직접 넣은 것(tx_id manual_)도 건너뛴다(대표님 2026-09-29).
        #    계좌로 같은 사람이 같은 금액 · 같은 메시지를 연달아 보내면 두 번째가 12초 필터에 걸려 사라졌다.
        #    사람이 일부러 누른 것이라 '재전송'이 아니다. 송출 단추는 보내는 동안 잠겨 두 번 눌리지 않는다.
        from_manual = str(tx_id or '').startswith('manual_') and request_is_authed()
        # 🏷️ 칭호 · 레벨(화면에 실어도 됨) / VIP · 번호표(대기함 · 장부에만) — 리스너가 보낸 것만 믿는다
        _pub, _priv = _donor_extras(new_don) if from_listener else ({}, {})
        dup_key = f"{(new_don.get('name') or '').strip()}|{amount}|{(new_don.get('message') or '').strip()}"
        # ⚠️ 되살리는 중(_recover)이면 거르지 않는다 — 장부로 '진짜 한 건' 이 확인된 후원이다.
        if not from_listener and not from_manual and not _recover and is_duplicate_donation(dup_key):
            print("⚠️ [내용 기반 중복 후원 무시] 동일 후원이 짧은 시간에 재수신됨")
            _handled = True
            return jsonify({"status": "success", "message": "Duplicate donation ignored (content)."})

        # 💬 1만 원 미만 '화면에만' 후원 — 리스너가 display_only 를 붙여 보낸다(대표님 2026-09-29).
        #    방송판 맨 위 반투명 띠만 띄운다. 대기함 · 점수 · 정산 장부 · 후원 순위 · 시그니처는 건드리지 않는다.
        #    (그전까지 리스너가 1만 원 미만을 버려서 여기까지 오지도 않았다 — 그 결과는 그대로 둔다)
        #    ⚠️ 리스너(tx_id 가 toon_)가 보낸 것만 이 길로 받는다. 다른 곳이 붙여 보내면 평소대로 처리한다.
        #    ⚠️ 장부에 안 적으니 tx_id 중복 검사(위)가 안 걸린다 — 최근 것을 따로 기억해 재전송을 거른다.
        if new_don.get('display_only') and from_listener and 0 < amount < SMALL_DISPLAY_MAX:
            if tx_id and tx_id in _display_seen:
                _handled = True
                return jsonify({"status": "success", "message": "Duplicate donation ignored.", "display_only": True})
            if tx_id:
                _display_seen.append(tx_id)
            _nm = ' '.join(str(new_don.get('name') or '').split()) or '익명'
            with file_lock:
                state = load_data()
                _new_latest = {'name': _nm, 'amount': amount,
                               'message': str(new_don.get('message') or '').strip(),
                               'time': time.time(), 'display_only': True}
                _new_latest.update(_pub)
                # 📒 '상태까지 들어간 tx' 목록은 이어 붙인다(여기서 끊기면 되살리기 판단이 틀어진다).
                #    화면에만 후원은 장부에 안 적으므로 목록에 넣을 필요는 없다.
                _tx_log_add(_new_latest, state.get('latest_donation'), None)
                state['latest_donation'] = _new_latest
                save_data(state)
                broadcast_event('update', state)
            _handled = True
            print(f"  💬 [화면에만] {_nm} {amount:,}원 — 방송판 맨 위 띠로만 띄웁니다", flush=True)
            return jsonify({'status': 'success', 'display_only': True})

        # 🎵 시그니처 매칭은 file_lock 밖에서 미리 끝낸다.
        # ⚠️ 이 호출은 Supabase로 나가는 HTTP라 느려질 수 있는데, 예전에는 락을 쥔 채 실행했다.
        #    그러면 후원 한 건이 처리되는 동안 점수 버튼·슬롯·리액션 넘기기 등
        #    락을 쓰는 모든 조작이 통째로 멈춰 방송 중 컨트롤러가 얼어붙었다.
        #    매칭은 state를 읽지 않으므로 락이 필요 없다.
        matched_sig = None
        _small_donation = False          # 시그니처 없이 전광판으로만 가는 후원인가
        if amount > 0:
            try:
                # 💸 제일 싼 시그니처보다 적게 넣었으면 아무것도 안 튼다.
                #    ⚠️ gte 매칭은 '올림' 이라 1,000원 후원에도 제일 싼 10,300원짜리가 걸렸다 —
                #       1,000원 내고 10,300원짜리 리액션을 가져가는 셈이었다.
                #    ⚠️ 막는 것은 후원 경로뿐이다. 매칭 함수 자체는 주사위·시그뒤집기도 쓴다.
                _floor = _sig_min_amount()
                if _floor and amount < _floor:
                    _small_donation = True
                    print(f"  💸 [시그니처] {amount:,}원은 제일 싼 시그니처({_floor:,}원)보다 "
                          f"적어 재생하지 않습니다 — 전광판에 올립니다", flush=True)
                else:
                    matched_sig = server.supabase_match_signature(amount)
            except Exception as e:
                print(f"⚠️ [자동 시그니처 매칭 오류] {e}")

        # 🧪🔁 '후원 테스트' · 대시보드 '다시 보기' — 화면에만 띄운다(대표님 2026-10-08).
        #    ⚠️ 예전엔 둘 다 진짜 후원처럼 대기함 · 정산 장부 · 후원 순위에 들어갔다. 다시 보기는 지난 후원을 한 번 더
        #       보내는 것이라 80만 원 후원이 장부에 두 번 적혔다(실측). 시그니처 · 팝업은 그대로 보여 준다(그게 누른 목적이다).
        #    시그 순위도 안 센다(count_tally=False). 리스너(tx_id toon_)가 붙여 보낸 것만 이 길로 받는다.
        _show_only = 'replay' if new_don.get('replay') is True else ('test' if new_don.get('test') is True else '')
        if _show_only and from_listener:
            _nm = ' '.join(str(new_don.get('name') or '').split()) or '익명'
            _msg = str(new_don.get('message') or '').strip()
            with file_lock:
                state = load_data()
                _latest = {'name': _nm, 'amount': amount, 'message': _msg, 'time': time.time(), 'show_only': _show_only}
                _latest.update(_pub)
                if matched_sig:
                    enqueue_signature(state, matched_sig, amount, _nm, _msg, count_tally=False, extra=dict(_pub) or None)
                elif amount < SMALL_DISPLAY_MAX:
                    _latest['display_only'] = True
                _tx_log_add(_latest, state.get('latest_donation'), None)
                state['latest_donation'] = _latest
                save_data(state)
                broadcast_event('update', state)
            _handled = True
            print(f"  {'🔁 [다시 보기]' if _show_only == 'replay' else '🧪 [후원 테스트]'} {_nm} {amount:,}원 "
                  f"— 화면에만 띄웁니다(대기함 · 장부 · 순위엔 안 넣음)", flush=True)
            return jsonify({'status': 'success', 'show_only': _show_only})

        with file_lock:
            state = load_data()
            # ⚠️ 예전에는 don_<밀리초> 였다. 같은 밀리초에 두 건이 들어오면 번호가 겹쳐,
            #    한 건을 대기함에서 지울 때 두 건이 같이 사라진다. 리액션 큐는 이미 uuid 를 쓴다.
            don_id = f"don_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
            name = new_don.get('name', '익명')
            msg = new_don.get('message', '')
            
            orig_name = name.strip()          # 투네이션이 준 진짜 닉네임. 무슨 일이 있어도 보존한다.
            parsed_name = orig_name
            cleaned_msg = msg.strip()

            # 💡 "닉네임: 내용" 형태로 보낸 이름을 가져온다(시그니처 신청 태그는 제외).
            #
            # ⚠️ 플랫폼이 이름을 제대로 준 경우에는 절대 건드리지 않는다.
            #    이 기능은 '익명'처럼 이름이 안 들어올 때 메시지로 알려주라고 있는 것인데,
            #    예전에는 이름이 멀쩡해도 메시지에 콜론만 있으면 갈아끼웠다.
            #    그래서 "목표: 100만 가자" 같은 평범한 문장에도 후원자가 '목표'가 됐다.
            #    "목표: …" 와 "철수: …" 는 글자 모양이 같아 내용만으로는 구분할 수 없다.
            #    그래서 '이름이 없을 때만' 이라는, 헷갈릴 여지가 없는 기준을 쓴다.
            cleaned_msg_for_split = cleaned_msg.replace('：', ':')
            if (name_is_missing(orig_name)
                    and cleaned_msg_for_split and ':' in cleaned_msg_for_split
                    and not cleaned_msg.startswith("[시그니처 신청:")):
                split_char = ':' if ':' in cleaned_msg else '：'
                parts = cleaned_msg.split(split_char, 1)
                potential_name = parts[0].strip()
                rest = parts[1].strip() if len(parts) > 1 else ''
                if looks_like_proxy_name(potential_name, rest):
                    parsed_name = potential_name
                    cleaned_msg = rest
                    print(f"  ↪️ [이름 보정] 이름이 '{orig_name}' 으로 들어와, 메시지에서 '{parsed_name}' 을 가져왔습니다")

            # ⚠️ '님' 떼기는 화면 글자를 긁어오던 시절의 보정이다("홍길동님이 후원하셨습니다").
            #    웹소켓 리스너(tx_id 가 toon_)는 닉네임을 그대로 주므로 떼면 안 된다 —
            #    '하늘님' 같은 닉네임이 '하늘' 로 바뀌어 순위가 두 사람으로 쪼개진다.
            if not str(tx_id or '').startswith('toon_'):
                if parsed_name.endswith('님') and len(parsed_name) > 1:
                    parsed_name = parsed_name[:-1]

            parsed_don_entry = {
                'id': don_id,
                'name': parsed_name,
                # 실제로 돈을 보낸 사람. parsed_name 이 대리 후원 표기로 바뀌어도 여기는 그대로다.
                # (예전에는 원본이 어디에도 안 남아, 잘못 바뀌면 되돌릴 방법이 없었다)
                'orig_name': orig_name,
                'amount': amount,
                'message': cleaned_msg,
                'time': now_hms()
            }
            # 🏷️ 칭호 · 레벨 · VIP · 번호표 — 대기함은 조종실만 본다(번호표가 방송판으로 안 나간다)
            if _pub.get('donor_title'):
                parsed_don_entry['title'] = _pub['donor_title']
            if _pub.get('donor_level'):
                parsed_don_entry['level'] = _pub['donor_level']
            parsed_don_entry.update(_priv)
            # 🧪 테스트용 두 번째 투네이션(리스너가 toon_t2_ 를 붙인다) — 대기함 · 장부에 표시해 구분한다
            _test_acct = str(tx_id or '').startswith('toon_t2_')
            if _test_acct:
                parsed_don_entry['test_acct'] = True
            state['pending_donations'].append(parsed_don_entry)
            # 대기함이 커지면 state 전체가 그만큼 무거워지고, 그게 접속 대수만큼 곱해져 나간다.
            # (부하 테스트: 802건 → state 120KB → 12대에 1.4MB/회)
            if len(state['pending_donations']) == PENDING_WARN_AT:
                print(f"⚠️ [대기함 {PENDING_WARN_AT}건] 배정이 밀려 있습니다. 화면 갱신이 무거워집니다 "
                      f"— 조종실에서 처리하거나 오토파일럿을 켜주세요.")
            _new_latest = {
                'name': parsed_name,
                'amount': amount,
                'message': cleaned_msg,
                'time': time.time()
            }
            _new_latest.update(_pub)          # 칭호 · 레벨(방송판 팝업 · 띠)
            # 📒 이 tx 가 '상태까지 들어갔다' 고 적는다 — 대기함 줄과 **같은 저장**에 실려야 의미가 있다(위 설명).
            _tx_log_add(_new_latest, state.get('latest_donation'), _tx or None)
            state['latest_donation'] = _new_latest
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
            #         add_point = man_won(amount)   # 5,000원대 내림, 6,000부터 올림
            #         bj['score'] += add_point
            #         bj['contribution'] = bj.get('contribution', 0) + add_point
            #         current_total = bj['score']
            #         break
            # 🏅 후원 순위 집계 — 이번 방송에 누가 얼마를 넣었나.
            #    ⚠️ 여기서 적어두면 SSE 를 타고 방송 화면까지 저절로 간다.
            #       DB 를 매번 뒤져 순위를 내면 화면이 몇 초마다 물어봐야 하고 반영도 늦다.
            #    ⚠️ 익명도 일단 세어 둔다. 순위에 넣을지 말지는 보여줄 때 정한다 —
            #       그래야 방송 중에 '익명 포함' 을 껐다 켜도 숫자가 안 틀어진다.
            #    ⚠️ 묶는 이름과 보여줄 이름을 나눈다. _norm_donor 는 '홍길동님' 을 '홍길동' 으로
            #       합치려고 끝의 '님' 을 떼는데, 닉네임이 '새손님' 인 사람은 '새손' 이 되어
            #       방송 화면에 틀린 이름이 나간다. 합산은 정규화된 이름으로, 표시는 원래 이름으로.
            try:
                _who = _norm_donor(parsed_name)
                # 🚫 사장님이 순위에서 빼둔 이름이면 아예 안 센다(테스트 후원 등).
                #    ⚠️ 익명은 여기서 빼지 않는다 — 위에 적었듯 '익명 포함' 을 방송 중에
                #       껐다 켜도 숫자가 안 틀어지게 세어는 두고, 보여줄 때 정한다.
                if _who not in excluded_names():
                    _dt = state.setdefault('donor_tally', {})
                    _row = _dt.get(_who) or {'total': 0, 'count': 0}
                    _row['total'] = int(_row.get('total') or 0) + max(0, amount)
                    _row['count'] = int(_row.get('count') or 0) + 1
                    _shown = ' '.join(str(parsed_name or '').split())
                    _row['name'] = _shown or _who
                    _dt[_who] = _row
            except Exception as _e:
                print(f"⚠️ [후원 순위 집계 실패] {_e}")

            # 💥 한 방 최고 후원 — 이번 방송에서 **한 번에** 가장 크게 보낸 후원.
            #    ⚠️ 순위에서 빼둔 이름(테스트 후원 등)은 기록하지 않는다.
            #    ⚠️ 같은 금액이면 **먼저 보낸 분**이 자리를 지킨다(크다만 본다, 같거나 크다가 아니다).
            #    ⚠️ 사전을 새로 만들어 넣는다 — 기본값 객체를 고치면 다음 방송이 이 기록을 물고 시작한다.
            try:
                if amount > 0 and _norm_donor(parsed_name) not in excluded_names():
                    _bs = state.get('best_single') or {}
                    if amount > int(_bs.get('amount') or 0):
                        state['best_single'] = {
                            'name': ' '.join(str(parsed_name or '').split()) or '익명',
                            'amount': amount,
                            'at': int(time.time() * 1000),
                            'id': don_id,
                            'member': '',
                        }
            except Exception as _e:
                print(f"⚠️ [한 방 최고 후원 기록 실패] {_e}")

            # 💛 소액 후원은 전광판에 이름을 올린다 — 시그니처 대신 이걸로 고마움을 전한다.
            #    ⚠️ 순위에서 빼둔 이름(테스트 후원 등)은 여기서도 뺀다. 익명은 그대로 올린다 —
            #       익명으로 보낸 사람도 방송에서 인사를 받아야 한다.
            if _small_donation:
                try:
                    if _norm_donor(parsed_name) not in excluded_names():
                        _nd = state.setdefault('notice_donors', [])
                        # ⚠️ 이름 길이를 자른다. 후원자 이름은 바깥에서 오는 값이라 길이 제한이
                        #    없다 — 긴 이름 하나가 전광판 한 줄을 통째로 밀어내고, 그 줄이 길수록
                        #    오래 떠 있어(noticeDur) 다음 안내까지 늦춘다.
                        # ⚠️ 별표(*)도 뗀다. 전광판은 *별표* 를 굵게 바꾸는데, 이름에 별표가
                        #    하나 끼면 그 뒤 글자가 통째로 굵어진다.
                        _nm = ' '.join(str(parsed_name or '').split()).replace('*', '')
                        _nd.append({'name': _nm[:NOTICE_DONOR_NAME_MAX] or '익명',
                                    'amount': int(amount), 'ts': int(time.time() * 1000)})
                        del _nd[:-NOTICE_DONORS_MAX]      # 오래된 것부터 흘려보낸다
                except Exception as _e:
                    print(f"⚠️ [전광판 소액 후원 기록 실패] {_e}")

            # ⚠️ 한 번 실패하면 그 후원은 정산 장부에서 통째로 사라진다(운영자는 대기함에서 보고
            #    점수를 주지만 장부엔 없다). Supabase 는 유휴 커넥션을 끊기 때문에 조용한 구간 뒤
            #    첫 후원에서 이게 실제로 발생한다. 다른 곳(save_data_sync)은 이미 1회 재시도로
            #    대응하고 있는데 여기만 빠져 있었다. 실패는 상태창에도 남겨 운영자가 알 수 있게 한다.
            # ⚠️ 되살리는 중(_recover)이면 장부 줄은 이미 있다 — 또 적으면 정산에 두 번 잡힌다.
            for _attempt in range(0 if _recover else 2):
                try:
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            db_query("INSERT INTO donation_history (timestamp, name, amount, current_total, message, source, tx_id) VALUES (?, ?, ?, ?, ?, ?, ?)"),
                            (time.strftime('%Y-%m-%d %H:%M:%S'), parsed_name, amount, current_total, cleaned_msg,
                             "toonation_test" if _test_acct else "toonation", tx_id)
                        )
                    break
                except Exception as dbe:
                    if _attempt == 0:
                        print(f"[장부 기록 실패 — 재시도] {dbe}")   # 끊긴 커넥션은 이미 폐기됐다
                        continue
                    print(f"[장부 기록 오류] {dbe}")
                    LAST_DB_ERROR["message"] = f"후원 장부 기록 실패({parsed_name} {amount}원): {dbe}"
                    LAST_DB_ERROR["time"] = time.strftime('%Y-%m-%d %H:%M:%S')

            # 🏷️ 번호표 한 줄(tx_id 로 장부와 잇는다). 실패해도 후원은 그대로 간다 — 부가 정보다.
            if _priv.get('donor_key') and tx_id and not _recover:
                try:
                    with get_db_connection() as conn:
                        conn.cursor().execute(
                            db_query("INSERT INTO donor_keys (tx_id, donor_key, level, title, vip, at) VALUES (?, ?, ?, ?, ?, ?)"),
                            (str(tx_id), _priv['donor_key'], _pub.get('donor_level'),
                             (_pub.get('donor_title') or {}).get('name'), _priv.get('vip'),
                             time.strftime('%Y-%m-%d %H:%M:%S')))
                except Exception as _ke:
                    print(f"⚠️ [번호표 기록 실패 — 후원은 정상] {type(_ke).__name__}", flush=True)

            # 🎵 자동 시그니처 리액션 연동 (매칭은 위에서 락 밖에 끝냈고, 여기서는 큐에만 넣는다)
            if matched_sig:
                enqueue_signature(state, matched_sig, amount, parsed_name, cleaned_msg, extra=dict(_pub) or None)
                print(f"  🎵 [자동 시그니처] 후원 {amount}원 → '{matched_sig.get('title')}' (#{matched_sig.get('id')}, {matched_sig.get('amount')}원) 큐 추가 완료")


            # ⚠️ 저장 '대기'를 락 안에서 하면 안 된다.
            #    save_data(sync=True) 는 DB 쓰기 큐가 빌 때까지 최대 30초를 기다린다.
            #    점수 버튼을 몇 번 누른 직후라면 그 큐에 앞선 쓰기가 쌓여 있어(Render→Supabase 왕복)
            #    후원 한 건이 file_lock 을 수 초에서 수십 초까지 쥐고 있었다. 그동안
            #    점수 지급·큐 넘김(/api/reaction/next)·대기함 삭제가 전부 얼어붙어,
            #    화면에서는 시그니처가 멈추고 컨트롤러가 먹통이 됐다.
            #    큐에 넣는 것까지만 락 안에서 하고, 기다리는 건 락을 놓은 뒤에 한다.
            pending_write = save_data(state, sync=True, wait=False)
            # 🔒 여기부터는 '처리 끝' 이다. 뒤에서 무슨 예외가 나도 대기함 · 장부엔 이미 들어갔으므로
            #    같은 tx_id 재전송은 걸러야 한다(안 그러면 두 번 들어간다).
            _handled = True
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
    finally:
        # 🔒 '처리 중' 을 반드시 푼다 — 안 풀면 그 tx_id 는 영원히 409 가 되어 후원이 못 들어온다.
        if _tx:
            _tx_release(_tx, _handled)

# 💬 '화면에만' 후원 — 이 금액 미만만(방송판 SMALL_DON_MAX 와 같게), 최근 tx_id 500개로 재전송을 거른다
SMALL_DISPLAY_MAX = 10000
_display_seen = collections.deque(maxlen=500)


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
