# -*- coding: utf-8 -*-
"""⚔️ 대결 — 대결자(또는 팀) 2~4명이 점수를 겨룬다 · 타이머 · 후원판 점수 연동.

조각
  match      (공개)   active · title · fire · link · teams[{id, name, score, members}] ·
                      timer{running, end_ms, left_ms, restart_ms, held, ended_at} · lead · gap · leader · flash
  match_logs (비공개) 대결 점수 기록(최근 200줄) [{at, team, name, val, before, after, ref, kind, member?, src?}]
                      kind 'manual' = 조종실 손 점수 · 'link' = 후원판 점수를 따라 올라간 것(src = 장부 score_log 줄 번호)
  ⚠️ 비밀은 없다. 기록만 비공개다(옛 PRIVATE_STATE_FIELDS 의 match_logs 와 같다 — server.py:864).

명령(팀은 id 로 고른다. name 으로도 되지만 같은 이름이 둘이면 409)
  match.open{title?} · match.close · match.title{title} · match.fire{on} · match.link{mode: off|solo|team}
  match.add_team{name?} · match.remove_team{id} · match.rename_team{id, to} · match.member{id, member, on?}
  match.score{id, delta, popup?} · match.undo{ref?} · match.reset
  match.start · match.pause · match.add_time{sec} · match.set_time{min, sec} · match.reset_time · match.end
  match.timeup — 로그인 없이(방송판이 '0 이 됐다' 고 알린다)

옛 규칙(그대로 옮김)
  - 처음 모습: 꺼짐 · 대결자 없음 · 타이머 3분(180000ms) 멈춤 · 연동 끔 (server.py:1361)
  - 켜면 무대에 올린다. 무대를 다른 판으로 바꿔도 대결은 안 끝난다(점수 · 연동 · 시계 그대로) — 끄기가 '끝내기' (show.py:161-164 · 238-249 · controller.html:6903)
  - 대결자는 4명(팀)까지, 새 대결자 이름은 'Player' · 0점 (controller.html:8049)
  - 손 점수는 정수만, 대결자 점수에만 · 기록 줄에 앞뒤 값 · 올리면 점수 팝업(features/score.py:218-265 · controller.html:7760)
  - 연동(link): 끔 · 개인전(solo, 대결자마다 점수판 한 명) · 팀전(team, 팀원 여럿). 켜져 있고 대결이 열려 있으면
    점수판 사람이 받은 **점수(delta)** 가 그 사람이 속한 팀 점수로도 오른다(음수도). 기여도만 오른 것은 안 따라간다.
    번외 판 점수도 따라간다(옛 것은 판을 가리지 않았다). 운영비는 안 따라간다. (features/score.py:14-31 · 193-213)
  - 한 사람은 한 팀에만 — 다른 팀에 넣으면 옮긴다. 개인전은 한 명만(고르면 바뀐다), 이름이 비었거나 'Player' 거나
    전에 고른 사람 이름 그대로면 고른 사람 이름으로 바꾼다. 팀전→개인전은 맨 앞 한 명만 남긴다. (controller.html:8004-8047 · server.py:2814-2833)
  - 팀원은 지금 점수판(번외 판이 켜져 있으면 번외 판) 사람 중에서 고른다 (controller.html:7977)
  - 되돌리기는 **그때 들어간 팀**에서 뺀다 — 지금 소속으로 찾으면 팀을 옮긴 뒤 엉뚱한 팀에서 빠졌다(09-30 재현) (features/score.py:175-189)
  - 타이머: 시작 = 남은 시간이 0 이면 마지막으로 맞춘 시간(restart)부터 · 멈춤 = 남은 시간을 얼린다 ·
    ±시간: 도는 중이면 끝 시각을, 멈춰 있으면 남은 시간(0 밑으로 안 감)을 · 맞추기: 0초 안 됨 · 180분까지 · 초 칸 60 이상은 분으로 ·
    리셋 = 멈춤 + 3분 (controller.html:8051-8112 · mobile.html:612-626)
  - 방송판이 '0 이 됐다' 고 알리면 끝 — 로그인 없는 길이라 서버가 정말 끝났는지 본다. 3초는 시계 차이 · 전송 지연 몫 (features/effects.py:16-47)
  - 시그니처가 돌기 시작하면 도는 시계를 얼리고, 대기줄이 비면 이어서 돌린다 — **누가 틀었든** 같다(대표님 09-30).
    손으로 멈춘 시계는 안 건드린다. 시그가 도는 중에 손으로 시작하면 그대로 돈다(바뀌는 순간에만 본다). (server.py:2162-2197)
  - 1등 빛은 혼자 1등일 때만(0점 초과) · 격차 = 1위 − 2위 · '동점!' = 따라잡은 순간 · '역전!' = 혼자 1등이 바뀐 순간
    (동점인 동안은 전 1등을 기억해 둔다) · 대결자가 늘거나 줄면 기억을 버린다 (overlay.html:4021-4105 · 4130-4190)
  - 방송 시작 · 끝에 대결 · 기록을 비운다 (server.py:3169 · 3244)

v2 에서 고친 것 · 버린 것
  - 버림: _keep_match_scores · 설정 패치의 명단 지키기 (server.py:2654-2700 · 3356-3368) — 화면이 대결을 통째로 저장하던 때의
    보호막이다. 명령은 자기 칸만 고친다. '한 명만 이름이 바뀌면 개명으로 보고 점수 물려주기' · 같은 이름 'Player' 짝짓기도
    같은 이유라 버렸다 — 대결자에 id 가 있어 이름을 바꿔도 점수가 그대로다.
  - 버림: 저장할 때 이름 공백 다듬기(server.py:2814) → 명령이 받을 때 다듬는다.
  - 버림: paused_time_left 가 없을 때 180000 으로 메우기(controller.html:7652 · 7672) — 화면의 NaN 막이였다. restart_ms 는 늘 0 보다 크다.
  - 고침: 시그 끝나고 이어 돌릴 때 남은 시간이 0 이면 옛 것은 3분부터 다시 돌았다(server.py:2190) → 이어 돌리지 않는다.
    시그가 시작될 때 이미 시간이 지났으면 얼리지 않고 그 자리에서 끝낸다.
  - 고침: 끄기(match.close)가 시계를 얼린다 — 옛 것은 꺼도 '도는 중' 으로 남아 다시 켜면 바로 '시간종료' 가 터졌다.
    룰렛 · 슬롯이 대결 위에 잠깐 올라와 있을 때 끄면 끝난 뒤 대결로 돌아가지 않는다(show.ret 를 비운다).
  - 고침: 되돌리기는 연동을 꺼도 · 대결을 닫아도 그때 들어간 팀에서 정확히 뺀다(옛 것은 켜져 있을 때만 — features/score.py:205).
    기록은 match.reset · 방송 시작/끝에 비우므로 지난 판 점수를 새 판에서 빼는 일은 없다.
  - 고침: 리셋(시간)은 '시그 때문에 멈춤' 표시도 지운다 — 옛 것은 리셋 뒤 시그가 끝나면 3분이 저절로 돌았다.
  - 새로: match.reset(점수만 0, 기록 비움) — 옛 것은 대결자를 지웠다 다시 넣어야 했다. match.end(조종실이 지금 끝내기).
    로그인한 쪽의 '시간 안 됐어도 끝내기' 는 timeup 대신 match.end 로.
  - 새로: 1등 · 격차 · 역전/동점 판정을 서버가 한다(lead · gap · leader · flash) — 방송판이 두 번 고친 계산이다(동점 빛 · 가짜 역전).
  - team_mode + link 두 칸 → link 한 칸(off · solo · team).

화면 약속
  방송판(공개 조각만 받는다 — match)
  - 판은 show.stage == 'match' 일 때만 그린다. active 는 '대결이 열려 있나'(무대가 잠깐 다른 판이어도 대결은 이어진다).
  - 남은 시간 = timer.running ? max(0, timer.end_ms − 서버시각) : timer.left_ms. 서버시각 = Date.now() + 차이(서버가 준 시각으로 맞춘다).
    표시는 ceil(남은/1000) 을 mm:ss · 0 이면 '시간종료'.
  - 피버(불꽃 테두리 match-fever-on): running 이고 0 < 남은 초 ≤ 60. 수동 불꽃(match-fire-on): fire (무대가 match 일 때만).
  - 마지막 10초(running · 남은 ≤ 10000): 빨개지며 커지고 초가 바뀔 때마다 삐 — 1초 남으면 여섯 번.
  - 끝 연출(폭발 · 꽃가루 · '시간종료' 3초)은 판마다 한 번: ① running 인데 내 시계가 end_ms 를 지나면 그때 터뜨리고
    match.timeup 을 로그인 없이 보낸다(열쇠 = end_ms). ② 조종실이 match.end 로 끝내 ended_at 이 새 값이 되면(아직 안 터뜨린 판이면) 그때.
  - 카드 · 게이지 자리 = teams 순서(색 = 순서 i 의 M_COLS[i % 6]). 점수 굴리기 · 통통(m-bump)은 team.id 로 전 값을 기억한다.
    link != 'off' 이면 카드 밑에 members 를 ' · ' 로.
  - 게이지 몫: total = Σ max(0, score) · total > 0 ? max(0.05, max(0, score)/total) : 1/팀 수.
  - 👑 빛(lead 클래스): lead 가 하나일 때 그 팀만. 둘 이상이면 동점 — 아무도 안 빛난다. lead 가 비면 아무도.
  - 격차: gap == null 이면 숨김 · 0 이면 '동점' · 그 밖엔 숫자 + (팀 3~4개면 '1·2위 차이', 둘이면 '차이') + '(gap+1)점시 역전!'.
    전선 자리 = lead[0] 칸의 모서리(2위가 오른쪽에 있으면 오른쪽 끝, 아니면 왼쪽 끝). 붙었다(tight) = total > 0 · gap/total ≤ 0.08.
  - 순간 글씨: flash.at 이 처음 보는 값이고 3초 안이면 flash.text('역전!' · '동점!')를 한 번. 다시 붙어 받은 옛 flash 는 안 띄운다.
  - held(시그 때문에 멈춤)는 따로 안 그린다 — 리액션 가리개가 판을 덮는다.
  조종실(로그인 — match + match_logs)
  - 시계는 위와 같은 식. running 이면 [정지](match.pause), 아니면 [시작](match.start). held 면 '시그 재생 중 — 끝나면 이어서'.
    +10초 · +30초 · +1분 · +3분 · +5분 · −1분 = match.add_time{sec} · 분/초 칸 = match.set_time{min, sec} · [리셋] = match.reset_time.
  - 대결자 표: teams(이름 칸 = match.rename_team · 점수 · [+점수] = match.score · 🗑 = match.remove_team).
  - 팀원 칩: 점수판(players.list, 번외 판이 켜져 있으면 players.extra) 이름들. members 에 있는데 점수판에 없는 이름은
    노란 경고('점수판에 없는 팀원 — 다시 골라 주세요') — 점수판에서 이름을 바꾸면 합산이 조용히 멈춘다.
  - 기록(match_logs): manual → '[시각] 팀 +N (전→후)', link → '하율 +5 → 팀 A'. 되돌리기: manual 줄은 match.undo{ref},
    link 줄은 후원판 되돌리기(score.undo{ref}) — 후원판 점수와 팀 점수가 같이 돌아간다.
"""
import re
import uuid

from .. import bus as busmod
from ..bus import CommandError, command
from ..state import slice_
from . import players as pl
from . import session as ses
from . import show as sh
from .rules import LOG_MAX

TEAMS_MAX = 4
TEAM_DEFAULT_NAME = 'Player'
TIMER_DEFAULT_MS = 180000            # 3분 — 처음 · 리셋
TIMER_SET_MAX_MS = 180 * 60000       # 맞추기는 세 시간(180분)까지
TIMEUP_GRACE_MS = 3000               # 방송판 '0 이 됐다' 를 이만큼 일찍 와도 받는다(시계 차이 · 전송 지연)
TITLE_MAX = 40
LINKS = ('off', 'solo', 'team')


def _timer():
    return {'running': False, 'end_ms': 0, 'left_ms': TIMER_DEFAULT_MS, 'restart_ms': TIMER_DEFAULT_MS,
            'held': False, 'ended_at': 0}


def _default():
    return {'active': False, 'title': '', 'fire': False, 'link': 'off', 'teams': [], 'timer': _timer(),
            'lead': [], 'gap': None, 'leader': None, 'flash': None}


slice_('match', True, _default)
slice_('match_logs', False, lambda: [])


# ── 도구 ──
def _ms(ctx):
    return int(ctx.now * 1000)


def _clean(name):
    """점수판 이름과 같은 규칙(players._clean) — 다르면 '밍밍' 과 '밍밍 ' 이 갈라져 합산이 조용히 멈춘다."""
    return ' '.join(str(name or '').split())[:pl.NAME_MAX]


def _int(v, what):
    """정수만 — '1,000' · '+5' 는 받고 1.5 · '3점' · True 는 거절(옛 parseIntStrict 와 같다 — controller.html:7754)."""
    if isinstance(v, bool) or v is None:
        raise CommandError('%s 은(는) 정수로 넣어 주세요' % what)
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        s = v.strip().replace(',', '')
        if re.fullmatch(r'[+-]?[0-9]+', s):
            return int(s)
    raise CommandError('%s 은(는) 정수로 넣어 주세요' % what)


def _settle(ctx):
    """시간이 다 됐는데 아직 '도는 중' 이면 여기서 끝낸다 — 서버가 판을 끝내는 자리(명령이 올 때마다 먼저 본다).
       돌려받는 값: 지금 끝냈나"""
    t = ctx.read('match')['timer']
    if t['running'] and _ms(ctx) >= t['end_ms']:
        t = ctx.edit('match')['timer']
        t.update(running=False, left_ms=0, held=False, ended_at=t['end_ms'])
        return True
    return False


def _edit(ctx):
    _settle(ctx)
    return ctx.edit('match')


def _team(m, data):
    tid = data.get('id')
    if tid:
        t = next((x for x in m['teams'] if x['id'] == tid), None)
    else:
        nm = _clean(data.get('name'))
        hits = [x for x in m['teams'] if x['name'] == nm]
        if len(hits) > 1:
            raise CommandError('같은 이름의 대결자가 둘입니다 — 표에서 골라 주세요', 409)
        t = hits[0] if hits else None
    if t is None:
        raise CommandError('없는 대결자입니다', 404)
    return t


def _forget_lead(m):
    """대결자가 늘거나 줄면 '전 1등' 기억을 버린다 — 안 그러면 가짜 '역전!' 이 뜬다(overlay.html:4029)."""
    m['leader'], m['gap'] = None, None


def _board(m, now_ms):
    """1등 · 격차 · 역전/동점 — 방송판 renderMatchGap 의 판정을 서버가 한다(overlay.html:4130-4190)."""
    teams = m['teams']
    top = max((t['score'] for t in teams), default=0)
    lead = [t['id'] for t in teams if t['score'] == top] if top > 0 else []
    m['lead'] = lead
    if len(teams) < 2 or not lead:
        _forget_lead(m)
        return
    first = lead[0]
    second = max(t['score'] for t in teams if t['id'] != first)
    gap = max(0, top - second)
    if gap == 0:
        # 따라잡은 순간만 '동점!' — 동점인 동안 전 1등(leader)은 그대로 둔다
        if m['gap'] is not None and m['gap'] > 0:
            m['flash'] = {'text': '동점!', 'at': now_ms}
    else:
        if m['leader'] and m['leader'] != first:
            m['flash'] = {'text': '역전!', 'at': now_ms}
        m['leader'] = first
    m['gap'] = gap


def _add(ctx, team, delta, ref, kind, **extra):
    before = team['score']
    team['score'] += delta
    logs = ctx.edit('match_logs')
    logs.insert(0, dict({'at': ctx.now, 'team': team['id'], 'name': team['name'], 'val': delta, 'before': before,
                         'after': team['score'], 'ref': ref, 'kind': kind}, **extra))
    del logs[LOG_MAX:]


def _freeze(t, now_ms):
    if t['running']:
        t.update(running=False, left_ms=max(0, t['end_ms'] - now_ms))
    t['held'] = False


def _end_now(t, now_ms):
    t.update(running=False, left_ms=0, held=False, ended_at=now_ms)


# ── 열고 닫기 · 꾸미기 ──
@command('match.open')
def match_open(ctx, data):
    """대결 위젯 켜기 — 대결을 열고 무대에 올린다. 점수는 그대로(새 판은 match.reset)."""
    m = _edit(ctx)
    m['active'] = True
    if 'title' in data:
        m['title'] = ' '.join(str(data.get('title') or '').split())[:TITLE_MAX]
    sh.set_stage(ctx, 'match')


@command('match.close')
def match_close(ctx, data):
    """대결 끝내기(끄기) — 시계를 얼리고 무대에서 내린다. 룰렛 · 슬롯이 위에 잠깐 올라와 있으면 끝난 뒤 돌아갈 자리도 지운다."""
    m = _edit(ctx)
    if not m['active']:
        ctx.notes['already'] = True
    m['active'] = False
    _freeze(m['timer'], _ms(ctx))
    s = ctx.read('show')
    if s['stage'] == 'match':
        sh.set_stage(ctx, None)
    elif s['ret'] == 'match':
        ctx.edit('show')['ret'] = None


@command('match.title')
def match_title(ctx, data):
    _edit(ctx)['title'] = ' '.join(str(data.get('title') or '').split())[:TITLE_MAX]


@command('match.fire')
def match_fire(ctx, data):
    """이글이글 효과(수동 불꽃 테두리)."""
    m = _edit(ctx)
    m['fire'] = bool(data['on']) if 'on' in data else not m['fire']


@command('match.link')
def match_link(ctx, data):
    """후원판 점수 연동 — off · solo(개인전) · team(팀전). 개인전으로 바꾸면 대결자마다 맨 앞 한 명만 남긴다."""
    mode = data.get('mode')
    if mode not in LINKS:
        raise CommandError('연동 방식은 off · solo · team 중 하나입니다')
    m = _edit(ctx)
    m['link'] = mode
    if mode == 'solo':
        for t in m['teams']:
            del t['members'][1:]


# ── 대결자 ──
@command('match.add_team')
def match_add_team(ctx, data):
    m = _edit(ctx)
    if len(m['teams']) >= TEAMS_MAX:
        raise CommandError('대결자는 %d명(팀)까지입니다' % TEAMS_MAX)
    tid = 'mt_' + uuid.uuid4().hex[:8]
    m['teams'].append({'id': tid, 'name': _clean(data.get('name')) or TEAM_DEFAULT_NAME, 'score': 0, 'members': []})
    _forget_lead(m)
    _board(m, _ms(ctx))
    ctx.notes['id'] = tid


@command('match.remove_team')
def match_remove_team(ctx, data):
    m = _edit(ctx)
    t = _team(m, data)
    m['teams'] = [x for x in m['teams'] if x['id'] != t['id']]
    _forget_lead(m)
    _board(m, _ms(ctx))


@command('match.rename_team')
def match_rename_team(ctx, data):
    """이름만 바꾼다 — id 가 그대로라 점수 · 팀원도 그대로(옛 것은 '하나 빠지고 하나 생기면 개명' 으로 짐작했다)."""
    m = _edit(ctx)
    t = _team(m, data)
    new = _clean(data.get('to'))
    if not new:
        raise CommandError('새 이름을 적어 주세요')
    t['name'] = new


@command('match.member')
def match_member(ctx, data):
    """팀원 넣기/빼기 {id, member, on?} — on 을 안 주면 뒤집는다.
       한 사람은 한 팀에만(다른 팀에 있으면 옮긴다). 개인전은 한 명만 — 이름이 비었거나 'Player' 거나 전에 고른 사람
       이름 그대로면 고른 사람 이름으로 바꾼다(controller.html:8004-8031)."""
    m = _edit(ctx)
    t = _team(m, data)
    who = _clean(data.get('member'))
    if not who:
        raise CommandError('팀원 이름을 골라 주세요')
    has = who in t['members']
    want = bool(data['on']) if 'on' in data else not has
    if not want:
        if has:
            t['members'].remove(who)
        return
    if has:
        return
    p = ctx.read('players')
    roster = [r['name'] for r in p['extra' if p.get('extra_active') else 'list']]
    if who not in roster:
        raise CommandError('점수판에 없는 사람입니다: %s' % who, 404)
    prev = t['members'][0] if t['members'] else None
    for x in m['teams']:
        if who in x['members']:
            x['members'].remove(who)
    if m['link'] == 'solo':
        t['members'] = [who]
        tn = t['name'].strip()
        if not tn or tn.lower() == TEAM_DEFAULT_NAME.lower() or (prev and tn == prev):
            t['name'] = who
    else:
        t['members'].append(who)


# ── 점수 ──
@command('match.score')
def match_score(ctx, data):
    """대결 점수 직접 넣기 {id, delta, popup?} — 후원판(점수판)과 별개. 올리면 점수 팝업(popup:false 면 안 띄운다)."""
    m = _edit(ctx)
    t = _team(m, data)
    d = _int(data.get('delta'), '점수')
    if not d:
        raise CommandError('0점은 넣지 않습니다')
    ref = 'mx_' + uuid.uuid4().hex[:10]
    _add(ctx, t, d, ref, 'manual')
    _board(m, _ms(ctx))
    if d > 0 and data.get('popup', True) is not False:
        ctx.edit('popup')['score'] = {'name': t['name'], 'diff': d, 'at': _ms(ctx)}
    ctx.notes['ref'] = ref


@command('match.undo')
def match_undo(ctx, data):
    """손 점수 되돌리기 — ref 를 안 주면 마지막 손 점수. 연동 줄(link)은 후원판 되돌리기(score.undo)로."""
    logs = ctx.read('match_logs')
    ref = data.get('ref')
    if not ref:
        last = next((r for r in logs if r.get('kind') == 'manual'), None)
        if last is None:
            raise CommandError('되돌릴 대결 점수가 없습니다', 404)
        ref = last['ref']
    rows = [r for r in logs if r.get('ref') == ref]
    if not rows:
        raise CommandError('이미 되돌렸거나 없는 기록입니다', 404)
    if any(r.get('kind') != 'manual' for r in rows):
        raise CommandError('후원판에서 따라온 점수입니다 — 후원판 되돌리기로 되돌려 주세요', 409)
    m = _edit(ctx)
    for r in rows:
        t = next((x for x in m['teams'] if x['id'] == r['team']), None)
        if t is not None:                  # 그 사이 대결자를 지웠으면 남은 대결자만
            t['score'] -= r['val']
    ctx.put('match_logs', [r for r in logs if r.get('ref') != ref])
    _board(m, _ms(ctx))
    ctx.notes['undone'] = ref


@command('match.reset')
def match_reset(ctx, data):
    """새 판 — 점수만 0, 기록 비움(지난 판 점수를 새 판에서 되돌리는 일이 없게). 이름 · 팀원 · 시계는 그대로."""
    m = _edit(ctx)
    for t in m['teams']:
        t['score'] = 0
    _forget_lead(m)
    m['flash'] = None
    _board(m, _ms(ctx))
    ctx.put('match_logs', [])


# ── 타이머 ──
@command('match.start')
def match_start(ctx, data):
    """시작 — 남은 시간이 0 이면 마지막으로 맞춘 시간(restart_ms)부터. 이미 돌고 있으면 그대로(두 번 눌러도 한 번)."""
    t = _edit(ctx)['timer']
    if t['running']:
        ctx.notes['already'] = True
        return
    left = t['left_ms'] if t['left_ms'] > 0 else t['restart_ms']
    t.update(running=True, end_ms=_ms(ctx) + left, left_ms=left, held=False, ended_at=0)


@command('match.pause')
def match_pause(ctx, data):
    t = _edit(ctx)['timer']
    if not t['running']:
        t['held'] = False                  # 시그 때문에 멈춰 있던 것을 손으로 멈춤 → 시그 끝나도 안 돈다
        ctx.notes['already'] = True
        return
    _freeze(t, _ms(ctx))


@command('match.add_time')
def match_add_time(ctx, data):
    """±초 {sec} — 도는 중이면 끝 시각을 민다(끝 시각이 지나 버리면 그 자리에서 끝),
       멈춰 있으면 남은 시간(0 밑으로 안 감)을 고치고 다음 시작 시간으로도 삼는다."""
    sec = _int(data.get('sec'), '초')
    if not sec:
        raise CommandError('0초는 더하지 않습니다')
    t = _edit(ctx)['timer']
    now = _ms(ctx)
    if t['running']:
        t['end_ms'] += sec * 1000
        if t['end_ms'] <= now:
            _end_now(t, now)
        return
    t['left_ms'] = max(0, t['left_ms'] + sec * 1000)
    if t['left_ms'] > 0:
        t['restart_ms'] = t['left_ms']
        t['ended_at'] = 0


@command('match.set_time')
def match_set_time(ctx, data):
    """분 · 초로 맞춘다 {min, sec} — 빈 칸은 0, 초 칸 60 이상은 분으로(90초 = 1분 30초). 0초는 안 되고 180분까지.
       돌고 있으면 그 시간부터 이어서 돈다."""
    mins = _int(data.get('min') if data.get('min') not in (None, '') else 0, '분')
    secs = _int(data.get('sec') if data.get('sec') not in (None, '') else 0, '초')
    if mins < 0 or secs < 0:
        raise CommandError('분 · 초는 0 이상의 정수로 넣어 주세요')
    ms = (mins * 60 + secs) * 1000
    if ms <= 0:
        raise CommandError('0초로는 맞출 수 없어요 — 시간을 넣어 주세요')
    if ms > TIMER_SET_MAX_MS:
        raise CommandError('세 시간(180분)까지만 넣을 수 있어요')
    t = _edit(ctx)['timer']
    if t['running']:
        t['end_ms'] = _ms(ctx) + ms
    t.update(left_ms=ms, restart_ms=ms, ended_at=0)


@command('match.reset_time')
def match_reset_time(ctx, data):
    """멈추고 3분으로."""
    t = _edit(ctx)['timer']
    t.update(running=False, end_ms=0, left_ms=TIMER_DEFAULT_MS, restart_ms=TIMER_DEFAULT_MS, held=False, ended_at=0)


@command('match.end')
def match_end(ctx, data):
    """조종실이 지금 끝낸다 — 시간이 남아 있어도."""
    t = _edit(ctx)['timer']
    if not t['running'] and t['left_ms'] == 0 and t['ended_at']:
        ctx.notes['already'] = True
        return
    _end_now(t, _ms(ctx))


@command('match.timeup', auth=False)
def match_timeup(ctx, data):
    """방송판이 '0 이 됐다' 고 알린다(로그인 없이) — 열린 대결이 돌고 있고, 끝 시각 3초 전 이후일 때만 받는다.
       너무 이르면 409(아무것도 안 바뀐다). 이미 끝났거나 꺼져 있으면 무시."""
    m = ctx.read('match')
    t = m['timer']
    if not m['active'] or not t['running']:
        ctx.notes['ignored'] = True
        return
    now = _ms(ctx)
    if now < t['end_ms'] - TIMEUP_GRACE_MS:
        raise CommandError('아직 시간이 남았습니다', 409)
    _end_now(ctx.edit('match')['timer'], min(now, t['end_ms']))


# ── 다른 모듈에 거는 것 ──
def follow_scores(ctx):
    """점수판 점수가 오른 뒤(players.AFTER_SCORE) — 연동이 켜져 있으면 그 사람 팀 점수도 같이.
       무엇이 올랐는지는 장부(score_log)의 이번 묶음(ctx.notes['ref'])에서 읽는다. 이미 따라간 줄(src)은 다시 안 센다."""
    m = ctx.read('match')
    if not m['active'] or m['link'] == 'off' or not m['teams']:
        return
    ref = ctx.notes.get('ref')
    if not ref:
        return
    seen = {r.get('src') for r in ctx.read('match_logs') if r.get('kind') == 'link'}
    hits = []
    for row in ctx.store.score_rows(ref):
        if row['field'] != 'score' or not row['delta'] or row['id'] in seen or row['list'] == 'bottom':
            continue
        team = next((t for t in m['teams'] if row['player'] in t['members']), None)
        if team is not None:
            hits.append((team['id'], row))
    if not hits:
        return
    m = ctx.edit('match')
    for tid, row in hits:
        team = next(t for t in m['teams'] if t['id'] == tid)
        _add(ctx, team, int(row['delta']), ref, 'link', member=row['player'], src=row['id'])
    _board(m, _ms(ctx))


def undo_link(ctx, ref):
    """후원판 되돌리기(players.ON_UNDO) — 그때 들어간 팀에서 뺀다(지금 소속이 아니라)."""
    logs = ctx.read('match_logs')
    rows = [r for r in logs if r.get('ref') == ref and r.get('kind') == 'link']
    if not rows:
        return
    m = ctx.edit('match')
    for r in rows:
        t = next((x for x in m['teams'] if x['id'] == r['team']), None)
        if t is not None:
            t['score'] -= r['val']
    ctx.put('match_logs', [r for r in logs if not (r.get('ref') == ref and r.get('kind') == 'link')])
    _board(m, _ms(ctx))


def follow_reaction(ctx):
    """⏱️ 명령 하나가 끝난 뒤(bus.AFTER) — 시그니처 대기줄이 비었다 ↔ 찼다로 **바뀐 순간**에만 대결 시계를 얼리고 이어 돌린다.
       누가 틀었든(후원 · 바로 틀기 · 시그뒤집기 …) 같다 — 옛 것은 리액션을 켜는 곳이 여덟 군데라 한 곳씩 고치다 빠졌다.
       ⚠️ '전' 은 이 명령 전 상태(ctx.work.state) · '후' 는 지금 작업본이다."""
    before = bool(ctx.work.state.get('queue')['items'])
    after = bool(ctx.read('queue')['items'])
    if before == after:
        return
    t = ctx.read('match')['timer']
    if after:
        if not t['running'] or _settle(ctx):           # 멈춰 있거나 · 이미 시간이 지났으면(그 자리에서 끝) 얼릴 것이 없다
            return
        t = ctx.edit('match')['timer']
        t.update(running=False, left_ms=t['end_ms'] - _ms(ctx), held=True)
    elif t['held']:
        t = ctx.edit('match')['timer']
        if t['left_ms'] <= 0:                           # 멈춘 사이 시간을 다 뺐다 — 이어 돌릴 것이 없다
            t['held'] = False
            return
        t.update(running=True, end_ms=_ms(ctx) + t['left_ms'], held=False)


def _reset(ctx, data):
    ctx.put('match', _default())
    ctx.put('match_logs', [])


pl.AFTER_SCORE.append(follow_scores)
pl.ON_UNDO.append(undo_link)
ses.ON_START.append(_reset)
ses.ON_END.append(_reset)
# ⚠️ bus.AFTER(명령 하나가 끝난 뒤 같이 볼 일)는 아직 공용 모듈에 없다 — 생기면 저절로 걸린다.
#    없으면 시그가 돌아도 대결 시계가 안 멈춘다(test_match 가 '건너뜀' 으로 알린다).
if hasattr(busmod, 'AFTER'):
    busmod.AFTER.append(follow_reaction)
