# -*- coding: utf-8 -*-
"""📺 방송 화면 — 지금 무엇이 떠 있는지 한 곳에서 정한다 (2026-09-29 개편).

왜 바꿨나
  예전에는 위젯마다 스위치가 따로 있었다(25개). 그 스위치를 바꾸는 서버 길이 12군데를 넘었고,
  방송판 안에는 여러 위젯을 몰래 한꺼번에 가리는 규칙이 5개 더 숨어 있었다.
  "왜 안 뜨지?" 를 찾으려면 여러 곳을 뒤져야 했고, 슬롯은 당첨 뒤 저절로 꺼져 화면이 비었다.

화면은 층 다섯 개다
  순서표(cues) — 방송 단계 목록. 한 단계 = 고정 자리 + 무대(+ 배치). [다음 ▶] 로 넘긴다.
                 (단계 목록 자체는 세이브 슬롯 layout_presets 를 그대로 쓴다. 여기엔 '지금 몇 번째' 만)
  덮기(cover)  — 시작·끝 화면 · 노래방 · 시그 리액션. 저장하지 않는다 — 다른 상태에서 계산한다.
                 덮는 동안 아래 층은 꺼지는 게 아니라 잠깐 가려지기만 한다.
  무대(stage)  — 큰 판 **하나**. 하나를 올리면 나머지는 내려간다.
                 슬롯·룰렛은 '잠깐' 올라왔다 끝나면 원래 무대로 돌아간다(ret).
  고정 자리(hud) — 늘 떠 있는 것. 켜고 끄기는 여기서만.
  알림(alerts) — 일이 생기면 떴다 사라지는 것. 끌 것만 끈다.

⚠️ 옛 스위치(roulette_enabled · dicegame.enabled · sig_tally_enabled …)는 이제 **여기서 계산해 적는다**
   (project). 폰·스트림덱·알림창이 그 값을 읽는다. 밖에서 옛 스위치를 직접 바꾸는 길은 막았다
   (server.py SERVER_OWNED · PATCH_DENY). 바꾸려면 /api/show 로.
⚠️ 대결·지옥탈출은 '보이기' 와 '진행' 이 따로다. 무대에서 내려가도 대결 점수·타이머·팀 연동,
   지옥탈출 기록·탈출 판정은 그대로 돈다 — 잠깐 슬롯을 돌려도 대결이 끝나면 안 된다.
⚠️ 이 파일은 Flask 를 모른다. 상태 사전만 받아 고친다(잠금·저장·방송은 부르는 쪽 몫).
"""

STAGES = ('match', 'pinball', 'dicegame', 'siggame', 'roulette', 'slot', 'home_race', 'hell', 'quiz')
TEMP_STAGES = ('roulette', 'slot')          # 끝나면 원래 무대로 돌아가는 것
STAGE_LABEL = {
    'match': '대결', 'pinball': '핀볼', 'dicegame': '주사위', 'siggame': '시그뒤집기',
    'roulette': '룰렛', 'slot': '슬롯', 'home_race': '퇴근빵', 'hell': '지옥탈출',
    'quiz': '퀴즈',
}

HUD_KEYS = ('ranking', 'gauge', 'account', 'notice', 'ticker', 'donor_rank', 'sig_tally', 'best', 'fundjar')
HUD_DEFAULT = {'ranking': True, 'gauge': True, 'account': True, 'notice': False, 'ticker': True,
               'donor_rank': False, 'sig_tally': False, 'best': False, 'fundjar': False}
HUD_LABEL = {'ranking': '점수판', 'gauge': '게이지', 'account': '계좌', 'notice': '공지', 'ticker': '전광판',
             'donor_rank': '후원 순위', 'sig_tally': '시그 순위', 'best': '최고 후원', 'fundjar': '모금함'}
# 옛 스위치 이름 (fundjar 는 fundjar.enabled 라 따로 다룬다 · ranking/gauge/account 는 옛 스위치가 없었다)
HUD_LEGACY = {'notice': 'notice_enabled', 'ticker': 'ticker_enabled', 'donor_rank': 'donor_rank_enabled',
              'sig_tally': 'sig_tally_enabled', 'best': 'best_enabled'}

# 💬 small: 1천~9천 원 후원을 가운데 카드 대신 맨 위 반투명 띠 한 줄로. 끄면 1천~9천 원은 아무것도 안 뜬다 (옛 스위치 없음 — 새 칸)
ALERT_KEYS = ('popup', 'takeover', 'reaction_title', 'small')
ALERT_LABEL = {'popup': '후원 팝업', 'takeover': '1등 탈환', 'reaction_title': '시그 제목', 'small': '1천~9천 알림'}
ALERT_LEGACY = {'popup': 'popup_enabled', 'takeover': 'takeover_enabled', 'reaction_title': 'reaction_title_enabled'}

# 밖에서 직접 못 바꾸는 옛 스위치 — server.py 가 SERVER_OWNED · PATCH_DENY 에 더한다
LEGACY_OWNED = ('roulette_enabled', 'slot_enabled', 'home_race_enabled') + tuple(HUD_LEGACY.values()) \
    + tuple(ALERT_LEGACY.values())

COVER_LABEL = {'screen_start': '시작 화면', 'screen_end': '끝 화면', 'karaoke': '노래방', 'reaction': '시그 리액션'}


def _default():
    return {'stage': None, 'ret': None, 'hud': dict(HUD_DEFAULT), 'alerts': {k: True for k in ALERT_KEYS},
            'cue_at': -1, 'rev': 0}


def _g(state, key):
    v = state.get(key)
    return v if isinstance(v, dict) else {}


def stage_from_legacy(state):
    """옛 스위치를 보고 지금 무대가 무엇인지 — 처음 한 번 옮겨 담을 때만 쓴다."""
    if state.get('roulette_enabled'):
        return 'roulette'
    if state.get('slot_enabled') is True:
        return 'slot'
    for k in ('siggame', 'dicegame', 'pinball'):
        if _g(state, k).get('enabled'):
            return k
    if _g(state, 'hell').get('on'):
        return 'hell'
    if state.get('home_race_enabled'):
        return 'home_race'
    if _g(state, 'match_data').get('active'):
        return 'match'
    return None


def ensure(state):
    """state['show'] 를 늘 온전한 모양으로. 없으면 옛 스위치에서 옮겨 담는다(한 번)."""
    s = state.get('show')
    if not isinstance(s, dict):
        s = _default()
        s['stage'] = stage_from_legacy(state)
        for k, lk in HUD_LEGACY.items():
            if lk in state:
                s['hud'][k] = bool(state.get(lk))
        s['hud']['fundjar'] = bool(_g(state, 'fundjar').get('enabled'))
        for k, lk in ALERT_LEGACY.items():
            if lk in state:
                s['alerts'][k] = bool(state.get(lk))
        state['show'] = s
    if s.get('stage') not in STAGES:
        s['stage'] = None
    if s.get('ret') not in STAGES or s.get('stage') not in TEMP_STAGES:
        s['ret'] = None
    hud = s.get('hud') if isinstance(s.get('hud'), dict) else {}
    s['hud'] = {k: bool(hud.get(k, HUD_DEFAULT[k])) for k in HUD_KEYS}
    al = s.get('alerts') if isinstance(s.get('alerts'), dict) else {}
    s['alerts'] = {k: bool(al.get(k, True)) for k in ALERT_KEYS}
    try:
        s['cue_at'] = int(s.get('cue_at', -1))
    except (TypeError, ValueError):
        s['cue_at'] = -1
    try:
        s['rev'] = int(s.get('rev') or 0)
    except (TypeError, ValueError):
        s['rev'] = 0
    # 저장본에는 이 칸들만 — 밖으로 나갈 때 붙는 cover · summary 가 되돌아와 눌러앉지 않게
    for k in list(s.keys()):
        if k not in ('stage', 'ret', 'hud', 'alerts', 'cue_at', 'rev'):
            s.pop(k, None)
    return s


def project(state):
    """show → 옛 스위치. 폰·스트림덱·알림창·옛 검사가 읽는 값을 여기서만 적는다."""
    s = ensure(state)
    st = s['stage']
    for k in ('dicegame', 'siggame', 'pinball'):
        g = state.get(k)
        if isinstance(g, dict):
            g['enabled'] = (st == k)
            if k == 'pinball' and st != 'pinball':
                g['running'] = False          # 내리면 굴리던 것도 멈춘다(예전 _solo_board 와 같다)
    state['roulette_enabled'] = (st == 'roulette')
    state['slot_enabled'] = (st == 'slot')
    state['home_race_enabled'] = (st == 'home_race')
    for k, lk in HUD_LEGACY.items():
        state[lk] = s['hud'][k]
    fj = state.get('fundjar')
    if isinstance(fj, dict):
        fj['enabled'] = s['hud']['fundjar']
    for k, lk in ALERT_LEGACY.items():
        state[lk] = s['alerts'][k]
    return s


def _bump(s):
    s['rev'] = int(s.get('rev') or 0) + 1


def set_stage(state, stage, temp=False):
    """무대에 올린다(None 이면 비운다). temp=True 면 잠깐 — end_temp 가 원래 무대로 돌려놓는다.
       돌려받는 값: (전 무대, 새 무대)."""
    s = ensure(state)
    if stage not in STAGES:
        stage = None
    cur = s['stage']
    if temp and stage in TEMP_STAGES:
        if cur not in TEMP_STAGES:
            s['ret'] = cur                      # 슬롯 위에 룰렛처럼 잠깐 위에 잠깐이면 처음 자리를 지킨다
    else:
        s['ret'] = None
    s['stage'] = stage
    if stage == 'match':
        md = state.get('match_data')
        if isinstance(md, dict):
            md['active'] = True                 # 무대에 올리면 대결 시작(내려도 끝나지는 않는다)
    _bump(s)
    project(state)
    return cur, stage


def end_temp(state, stage):
    """잠깐 올라온 판(슬롯·룰렛)이 끝났다 — 그게 지금 무대면 원래 무대로 돌아간다."""
    s = ensure(state)
    if s['stage'] != stage:
        return None
    back = s.get('ret')
    s['stage'] = back if back in STAGES else None
    s['ret'] = None
    _bump(s)
    project(state)
    return s['stage']


def clear_stage(state, stage):
    """그 판이 지금 무대면 내린다(다른 판이 올라와 있으면 아무것도 안 한다)."""
    s = ensure(state)
    if s['stage'] != stage:
        return False
    s['stage'] = None
    s['ret'] = None
    _bump(s)
    project(state)
    return True


def set_hud(state, key, on):
    s = ensure(state)
    if key not in HUD_KEYS:
        return False
    s['hud'][key] = bool(on)
    _bump(s)
    project(state)
    return True


def set_alert(state, key, on):
    s = ensure(state)
    if key not in ALERT_KEYS:
        return False
    s['alerts'][key] = bool(on)
    _bump(s)
    project(state)
    return True


def reset_session(state):
    """방송 시작·끝 — 무대를 비운다. 고정 자리·알림은 설정이라 남긴다(예전에도 안 지웠다)."""
    s = ensure(state)
    s['stage'] = None
    s['ret'] = None
    s['cue_at'] = -1
    _bump(s)
    project(state)


def cover_of(state):
    """덮기 — 저장하지 않고 늘 계산한다. 위에서부터 먼저 걸리는 것 하나."""
    ss = _g(state, 'stage_screen')
    mode = ss.get('mode')
    if mode in ('start', 'end'):
        return 'screen_' + mode
    if state.get('karaoke_enabled') and state.get('karaoke_video'):
        return 'karaoke'
    if state.get('reaction_mode'):
        return 'reaction'
    return None


def ingest_match(state, was_active):
    """폰처럼 옛 방식으로 대결을 켜고 끄면(match_data.active) 무대도 따라간다."""
    now_active = bool(_g(state, 'match_data').get('active'))
    if now_active and not was_active:
        s = ensure(state)
        if s['stage'] != 'match':
            set_stage(state, 'match')
            return 'on'
    elif was_active and not now_active:
        if clear_stage(state, 'match'):
            return 'off'
    return None


def ingest_roulette(state, before_roulette):
    """조종실·폰이 룰렛을 돌리면(roulette.command = spin, 새 command_time) 룰렛을 잠깐 무대에 올린다."""
    r = _g(state, 'roulette')
    b = before_roulette if isinstance(before_roulette, dict) else {}
    if r.get('command') == 'spin' and r.get('command_time') != b.get('command_time'):
        set_stage(state, 'roulette', temp=True)
        return True
    return False


def view(state):
    """밖으로 보낼 모양 — 저장본 + 계산한 덮기 + 사람이 읽는 한 줄."""
    s = ensure(state)
    out = dict(s)
    out['hud'] = dict(s['hud'])
    out['alerts'] = dict(s['alerts'])
    out['cover'] = cover_of(state)
    out['summary'] = summary(state, out['cover'])
    return out


def summary(state, cover=None):
    s = ensure(state)
    cover = cover_of(state) if cover is None else cover
    st = STAGE_LABEL.get(s['stage'], '없음')
    if s.get('ret'):
        st += ' (끝나면 %s)' % STAGE_LABEL.get(s['ret'], '')
    hud = ' · '.join(HUD_LABEL[k] for k in HUD_KEYS if s['hud'].get(k)) or '없음'
    return '무대: %s · 덮기: %s · 고정: %s' % (st, COVER_LABEL.get(cover, '없음'), hud)


# ── 순서표(세이브 슬롯) 한 단계 — 옛 모양({switches, board})도 읽는다 ──
def cue_from_state(state):
    s = ensure(state)
    return {'hud': dict(s['hud']), 'stage': s['stage'] if s['stage'] not in TEMP_STAGES else s.get('ret')}


def cue_hud(cue):
    """단계에 담긴 고정 자리. 새 모양은 hud, 옛 슬롯은 switches(옛 스위치 이름) 에서 옮긴다.
       담겨 있지 않은 칸은 None — 불러올 때 건드리지 않는다."""
    if isinstance(cue.get('hud'), dict):
        return {k: bool(v) for k, v in cue['hud'].items() if k in HUD_KEYS}
    sw = cue.get('switches') if isinstance(cue.get('switches'), dict) else {}
    back = {lk: k for k, lk in HUD_LEGACY.items()}
    out = {}
    for lk, v in sw.items():
        if lk in back:
            out[back[lk]] = bool(v)
        elif lk == 'fundjar':
            out['fundjar'] = bool(v)
    return out


def cue_stage(cue):
    st = cue.get('stage') if 'stage' in cue else (cue.get('board') or None)
    return st if st in STAGES else None


def apply_cue(state, cue):
    """단계 하나를 불러온다 — 고정 자리 + 무대. (배치는 부르는 쪽이 배치 파일에 쓴다)"""
    s = ensure(state)
    for k, v in cue_hud(cue).items():
        s['hud'][k] = v
    st = cue_stage(cue)
    # ⚠️ 옛 슬롯(board 만 있는 것)은 게임판 다섯만 다뤘다 — 대결·지옥탈출·퇴근빵은 건드리지 않았다.
    #    옛 슬롯에 판이 없으면 그 셋은 그대로 둔다(예전과 같게).
    if 'stage' not in cue and st is None and s['stage'] in ('match', 'hell', 'home_race'):
        _bump(s)
        project(state)
        return s
    set_stage(state, st)                   # set_stage 가 rev 를 올리고 project 한다
    return s
