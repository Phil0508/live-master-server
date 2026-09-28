# -*- coding: utf-8 -*-
"""👑 특별 후원자(VIP) — 등급은 이번 방송 후원 순위로 매긴다.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import time
from flask import jsonify, request
from server import (
    IS_POSTGRES, app, broadcast_event, db_query, get_db_connection, is_excluded, load_data,
    request_is_authed,
)


# ==========================================
# 👑 특별 후원자(VIP) 관리
#    조회는 오버레이가 써야 하므로 공개, 등록/삭제는 로그인 필요(exempt 목록에 없음)
# ==========================================

# ── 등급 = 이번 방송 후원 순위 (실시간) ──
# 2026-09-09 사장님: "한달치가 아니라 수~목 방송 한 회차의 순위로 등록" · "실시간으로 반영".
#   회차 = 조종실 방송 On ~ Off (수 17:00 ~ 목 03:00 처럼 날짜를 걸쳐도 한 회차).
#   순위는 후원 순위 위젯이 쓰는 donor_tally(이번 방송분 합산, 투네이션·계좌 모두) 그대로.
#   1위 VVIP · 2~3위 VIP · 4~6위 DIAMOND · 7~10위 BRONZE · 11위부터 없음.
#   동점은 같은 순위(둘 다 위 등급). 익명·순위에서 뺀 이름은 순위에 안 들어간다.
#   후원이 들어올 때마다 순위가 다시 매겨지므로 등급도 그 자리에서 바뀐다 — 저장하지 않는다.
# ⚠️ 예전(평생 누적 금액: VVIP 300만+ …)에는 한 번 오르면 아무도 안 내려가 골드만 늘었다.
#    그때 준 등급은 서버가 처음 뜰 때 한 번 비운다(_vip_wipe_legacy_once).
#    직접 준 등급(vip_donators)은 예외용으로 남는다 — 순위에 못 든 사람에게만 붙는다.
# 🎖️ 색은 **귀금속 순서**다 — 금 > 백금 > 다이아 > 동. 누구나 아는 차례라 설명이 필요 없다.
#    예전에는 1위가 형광 빨강(#ff3b30)이었다. 빨강은 화면에서 경고·에러로 읽히는 색이라
#    제일 귀한 등급이 제일 안 귀해 보였다(사장님: "vip 1등이 강조가 안 되고 vip스럽지 않다").
#    게다가 1위는 빨강인데 7~10위 이름이 GOLD(노랑)여서 제일 귀한 색을 제일 낮은 등급이 썼다.
#    그래서 7~10위를 BRONZE 로 바꿨다 — 이름과 색이 같은 곳을 가리켜야 말이 된다.
# ⚠️ 백금은 순백(#ffffff)이 아니라 살짝 푸른 은백(#c8d4e3)이다. 순백으로 하면 팝업에서
#    일반 후원자 이름(#fff)과 똑같아져서 등급이 있는지 없는지 구별이 안 된다.
# ⚠️ 'GOLD' 는 옛 이름이다. 직접 준 등급(vip_donators)에 남아 있을 수 있으니 화면에 찍는
#    쪽(overlay·controller)에서는 옛 이름도 계속 알아듣게 둔다.
VIP_TIERS = [
    # (등급, 순위 시작, 순위 끝, 색, 뱃지)
    ('VVIP',    1,  1, '#f6c453', '🏆'),   # 금   — 방송판 기본 금색(--gold) 그대로
    ('VIP',     2,  3, '#c8d4e3', '👑'),   # 백금
    ('DIAMOND', 4,  6, '#5ac8fa', '💎'),   # 다이아
    ('BRONZE',  7, 10, '#c97f3d', '🥉'),   # 동
]
VIP_ORDER = {g: i for i, (g, _, _, _, _) in enumerate(VIP_TIERS)}   # 0 이 제일 높다
VIP_STYLE = {g: (c, bd) for g, _, _, c, bd in VIP_TIERS}


def vip_tier_for_rank(rank):
    """이 순위면 어느 등급인가. 10위 밖이면 None."""
    for g, lo, hi, _, _ in VIP_TIERS:
        if lo <= rank <= hi:
            return g
    return None


def _vip_live(state):
    """이번 방송 후원 순위 → 등급. {다듬은 이름: {name, rank, total, grade, custom_color, badge}}
    ⚠️ 순위표는 여기 하나에서만 만든다 — 방송판·조종실·AI 가 서로 다른 순위를 보면 안 된다."""
    tally = (state or {}).get('donor_tally') or {}
    rows = []
    for who, row in tally.items():
        if not isinstance(row, dict) or is_excluded(who):
            continue
        total = int(row.get('total') or 0)
        if total <= 0:
            continue
        rows.append((who, ' '.join(str(row.get('name') or who).split()) or who, total))
    rows.sort(key=lambda r: (-r[2], r[1]))
    out, rank, prev = {}, 0, None
    for i, (who, shown, total) in enumerate(rows):
        if total != prev:
            rank = i + 1          # 동점은 같은 순위, 다음 순위는 건너뛴다 (1·1·3)
            prev = total
        g = vip_tier_for_rank(rank)
        if not g:
            break                 # 정렬돼 있으니 뒤는 전부 밖이다
        c, bd = VIP_STYLE[g]
        out[who] = {'name': shown, 'rank': rank, 'total': total, 'grade': g,
                    'custom_color': c, 'badge': bd}
    return out


def _vip_wipe_legacy_once(cursor):
    """평생 누적으로 준 옛 등급을 한 번만 비운다. 사장님: '지금 바로 전부 지우고 시작'.
    ⚠️ 표시는 kv_store 에 두지 않는다 — 거기 키는 상태로 읽히고 방송 종료 때 지워진다."""
    cursor.execute("CREATE TABLE IF NOT EXISTS app_flags (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute(db_query("SELECT value FROM app_flags WHERE key = ?"), ('vip_rank_reset_v1',))
    if cursor.fetchone():
        return
    cursor.execute("DELETE FROM vip_donators")
    cursor.execute(db_query("INSERT INTO app_flags (key, value) VALUES (?, ?)"),
                   ('vip_rank_reset_v1', time.strftime('%Y-%m-%d %H:%M:%S')))
    print('  👑 [VIP] 등급이 회차 순위 기준으로 바뀌어 옛 평생누적 등급을 비웠다', flush=True)


@app.route('/api/vips/candidates')
def api_vip_candidates():
    """이번 방송 후원 순위와 그에 따른 등급 — 조종실 표시용. 등급은 저장하지 않는다.
    (이름은 옛 '후보' 그대로 둔다 — 조종실이 이 주소를 부른다.)"""
    if not request_is_authed():
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    try:
        state = load_data()
        live = _vip_live(state)
        tally = state.get('donor_tally') or {}
        rows = []
        for who, row in tally.items():
            if not isinstance(row, dict) or is_excluded(who):
                continue
            total = int(row.get('total') or 0)
            if total <= 0:
                continue
            v = live.get(who) or {}
            rows.append({'key': who, 'name': ' '.join(str(row.get('name') or who).split()) or who,
                         'total': total, 'count': int(row.get('count') or 0),
                         'rank': v.get('rank') or 0, 'grade': v.get('grade') or ''})
        rows.sort(key=lambda r: (-r['total'], r['name']))
        # 등급 밖 사람도 순위는 이어서 매긴다 (11위, 12위 …) — 몇 등인지 보이게
        rank, prev = 0, None
        for i, r in enumerate(rows):
            if r['total'] != prev:
                rank, prev = i + 1, r['total']
            r['rank'] = rank
        return jsonify({
            'status': 'success',
            'rows': rows,
            'broadcast_active': bool(state.get('broadcast_active')),
            'tiers': [{'grade': g, 'from': lo, 'to': hi, 'color': c, 'badge': bd}
                      for g, lo, hi, c, bd in VIP_TIERS],
        })
    except Exception as e:
        print(f'[등급 순위 조회 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e), 'rows': []}), 500


@app.route('/api/vips', methods=['GET'])
def get_vips():
    try:
        load_data()   # 갓 뜬 서버는 첫 상태 읽기에서 표를 만든다 — 그 전에 오면 '표가 없다' 가 났다
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
