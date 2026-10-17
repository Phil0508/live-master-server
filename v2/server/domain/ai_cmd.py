# -*- coding: utf-8 -*-
"""🗣️ 말로 조종 — AI 가 사람 말을 v2 명령으로 바꾼다(10-17 'AI 권한 넓히기' 1 · 2번).

흐름(POST /api/ai/command {text, bgm?:[곡 제목…]})
  0) 조종실이 먼저 자기 규칙(panels/ai/commands.js — '하율 3점' · '룰렛 돌려' …)으로 풀어 본다. 못 풀면 여기로 온다.
  1) 물음 꼴('밍밍 몇 점이야?')이면 바로 {kind:'question'} — 조종실은 예전처럼 /api/ai/chat 으로 묻는다(AI 를 여기서 안 부른다).
  2) 서버 규칙(rule_plan) — '공지 바꿔: …' · '한마디: …' · '대결 3분 시작' · '예지 기여도 3' · '조명 빨강' … AI 없이 0초.
  3) 못 풀면 Claude 에게 도구(tool use) 하나 'propose_commands' 로 묻는다(ai.ai_tools — 명령 밖 · 다른 갈래 · 시한).
     ⚠️ 돌아온 입력은 하나도 믿지 않는다 — check() 가 **허용 목록(ALLOW)** · 칸 이름 · 값 범위 · 지금 명단 · 대기함 id 를 보고
        이상하면 그 줄을 버린다(버린 까닭은 dropped 로 돌려준다).
  4) 남은 줄마다 카드. 안전한 것(SAFE — 점수 · 돈 · 장부와 상관없는 것)은 스위치(ai_opts.direct, 기본 켬)가 켜져 있으면
     **서버가 바로** bus.run(by='ai') 하고 [되돌리기](바로 앞 값으로 다시 명령)를 붙인다. 한 번 말에 3개까지,
     1분에 10개가 넘으면 멈추고 나머지는 [실행] 카드로. 그 밖(점수 · 대기함 · 게임 · 목표 …)은 **늘 [실행] 카드** —
     사람이 눌러야 조종실이 /api/cmd(명령 번호 cid)로 보낸다. ⚠️ 이 파일은 SAFE 가 아닌 명령을 절대 부르지 않는다.
  AI 가 꺼졌거나 막히면(키 없음 · 붐빔 · 한도) 조용히 {kind:'none'} — 조종실은 예전처럼 /api/ai/chat(서버 계산)으로.

받는 것: {status:'success', kind:'question'|'none'|'reply'|'command', source:'rule'|'ai'|null, reply?: 글,
          cards:[{id, type, data, text, safe, state:'ask'|'ran'|'failed'|'client', error?, undo?:{type, data, text}}],
          dropped?:[{type, why}], note?: 글}
  · state 'client' — BGM(조종실 브라우저가 트는 것): 조종실이 받자마자 스스로 한다(bgm.next · bgm.toggle · bgm.play{title}).
조각 ai_opts(비공개) {direct: True} · 명령 ai.set {direct: bool}

허용 목록(ALLOW) — 큰 일(방송 시작/끝 · 되돌리기 · 설정 옮기기 · 시그니처 지우기 · 버전 바꾸기 …)은 여기 없다:
  [실행] 카드  score.add · pending.assign · pending.ignore · match.start · match.pause · match.set_time · match.add_time ·
               roulette.spin · roulette.stop · slot.spin · reaction.skip · clip.now · goal.set
  바로(SAFE)   notice.add · notice.edit · notice.now · cast.say · cast.up · show.cue · screen.set · show.stage · lights.color ·
               bgm.next · bgm.toggle · bgm.play(조종실 쪽)
"""
import asyncio
import collections
import json
import re
import threading
import time
import uuid

from fastapi.responses import JSONResponse

from ..bus import CommandError, command
from ..state import slice_
from . import ai
from . import ai_facts as af
from .dicegame import STAGE_LABEL
from .legacy import route
from .lights import DEFAULT_COLORS, norm_hex
from .show import NOTICE_LEN, NOTICE_MAX, STAGES

slice_('ai_opts', False, lambda: {'direct': True})

DIRECT_PER_SAY = 3          # 한 번 말에 바로 실행은 3개까지
DIRECT_PER_MIN = 10         # 1분에 10개가 넘으면 멈추고 묻는다
PROPOSE_MAX = 6             # AI 가 한 번에 낼 수 있는 줄
TEXT_MAX = 300              # 사람 말 길이
AI_TIMEOUT, AI_DEADLINE = 12, 28.0
SCORE_MAX, CONTRIB_MAX = 50, 100
GOAL_MAX = 100000000
SAY_MAX, UP_MAX, SCREEN_TITLE_MAX, SCREEN_MIN_MAX = 60, 60, 40, 180

_direct_at = collections.deque()
_direct_lock = threading.Lock()


class Bad(Exception):
    """AI 가 낸 줄이 허용 밖 · 범위 밖 — 그 줄만 버린다."""


# ── 허용 목록 ───────────────────────────────────────────
SAFE = ('notice.add', 'notice.edit', 'notice.now', 'cast.say', 'cast.up', 'show.cue', 'screen.set', 'show.stage',
        'lights.color', 'bgm.next', 'bgm.toggle', 'bgm.play')
ASK = ('score.add', 'pending.assign', 'pending.ignore', 'match.start', 'match.pause', 'match.set_time', 'match.add_time',
       'roulette.spin', 'roulette.stop', 'slot.spin', 'reaction.skip', 'clip.now', 'goal.set')
CLIENT = ('bgm.next', 'bgm.toggle', 'bgm.play')      # 서버 명령이 아니다 — 조종실 브라우저가 한다
ALLOW = SAFE + ASK

# AI 에게 보여 줄 설명(도구 설명에 들어간다) — 칸 이름은 check() 와 같아야 한다
HELP = {
    'score.add': '{name, delta} 점수(±1~50) 또는 {name, contrib} 기여도(±1~100) — name 은 지금 선수 이름 그대로',
    'pending.assign': '{id, name} 대기함 후원 하나를 선수 한 명에게 — id 는 대기함 목록의 id 그대로',
    'pending.ignore': '{id} 대기함 후원 무시',
    'match.start': '{} 대결 타이머 시작', 'match.pause': '{} 대결 타이머 멈춤',
    'match.set_time': '{min, sec} 대결 시간을 맞춤(0~180분)', 'match.add_time': '{sec} 대결 시간 ±초',
    'roulette.spin': '{} 룰렛 돌리기', 'roulette.stop': '{} 룰렛 멈추기', 'slot.spin': '{} 슬롯 돌리기',
    'reaction.skip': '{} 재생 중인 시그니처 넘기기', 'clip.now': '{} 클립 남기기',
    'goal.set': '{target} 목표 금액(원)',
    'notice.add': '{text} 공지 한 줄 추가', 'notice.edit': '{index, text} 공지 index 번째(0부터)를 고침',
    'notice.now': '{text} 또는 {index} 공지를 지금 바로 흘림',
    'cast.say': '{text} 방송 화면 가운데 1초 한마디(60자)', 'cast.up': '{text} 가운데 금색 UP 자막(60자)',
    'show.cue': '{dir: next|prev} 순서표 다음 · 이전 단계', 'screen.set': '{mode: start|end|off, title?, minutes?} 시작 전 · 끝 화면',
    'show.stage': '{stage: %s | null} 무대에 게임판 띄우기(띄우기만 — 게임은 안 돌린다) · null 이면 비우기' % '|'.join(STAGES),
    'lights.color': '{color: #rrggbb | RAINBOW | OFF} 조명 색',
    'bgm.next': '{} BGM 다음 곡', 'bgm.toggle': '{} BGM 재생 · 멈춤', 'bgm.play': '{title} BGM 목록에서 그 곡 틀기',
}


def _won(n):
    n = int(n or 0)
    if n and n % 10000 == 0:
        return '%s만 원' % format(n // 10000, ',')
    return '%s원' % format(n, ',')


def _int(v, lo, hi, what):
    if isinstance(v, bool) or v is None or v == '':
        raise Bad('%s 이(가) 숫자가 아님' % what)
    if isinstance(v, float):
        if v != int(v):
            raise Bad('%s 은(는) 정수여야 함' % what)
        v = int(v)
    if isinstance(v, str):
        t = v.replace(',', '').replace('원', '').strip()
        if not re.fullmatch(r'[+-]?\d{1,10}', t):
            raise Bad('%s 이(가) 숫자가 아님' % what)
        v = int(t)
    if not isinstance(v, int):
        raise Bad('%s 이(가) 숫자가 아님' % what)
    if not lo <= v <= hi:
        raise Bad('%s 범위 밖(%s~%s)' % (what, lo, hi))
    return v


def _text(v, n, what):
    if not isinstance(v, (str, int, float)) or isinstance(v, bool):
        raise Bad('%s 글이 없음' % what)
    t = ' '.join(str(v).split())
    if not t:
        raise Bad('%s 글이 비었음' % what)
    return t[:n]


def _only(data, keys):
    if not isinstance(data, dict):
        raise Bad('data 가 사전이 아님')
    extra = [k for k in data if k not in keys]
    if extra:
        raise Bad('모르는 칸: %s' % ', '.join(str(k) for k in extra[:3]))
    return data


def _pending_item(slices, pid):
    pid = str(pid or '')
    it = next((x for x in (slices.get('pending') or []) if isinstance(x, dict) and x.get('id') == pid), None)
    if it is None:
        raise Bad('대기함에 없는 후원(id)')
    if it.get('type') == 'off_work' or it.get('kind') == 'contrib' or it.get('display_only'):
        raise Bad('후원 카드가 아님')
    return it


def _pending_label(it):
    return "'%s %s'" % (str(it.get('name') or '익명')[:20], _won(it.get('amount')))


def check(type_, data, slices):
    """AI(또는 규칙)가 낸 줄 하나 → (깨끗한 data, 사람 말). 허용 밖 · 범위 밖 · 없는 선수 · 없는 id 면 Bad.
       ⚠️ 돌려주는 data 는 여기서 새로 만든 것만 담는다(들어온 칸을 그대로 넘기지 않는다)."""
    if type_ not in ALLOW:
        raise Bad('허용 목록 밖 명령')
    data = {} if data is None else data
    names = af.current_names(slices)
    P = slices.get('players') or {}
    if type_ == 'score.add':
        d = _only(data, ('name', 'delta', 'contrib'))
        name = str(d.get('name') or '').strip()
        if name not in names:
            raise Bad("지금 판에 없는 선수 '%s'" % name[:20])
        out = {'name': name, 'list': 'extra' if P.get('extra_active') else 'list'}
        delta = _int(d['delta'], -SCORE_MAX, SCORE_MAX, '점수') if d.get('delta') not in (None, '', 0) else 0
        contrib = _int(d['contrib'], -CONTRIB_MAX, CONTRIB_MAX, '기여도') if d.get('contrib') not in (None, '', 0) else 0
        if not delta and not contrib:
            raise Bad('점수 · 기여도가 둘 다 0')
        if delta and contrib:
            raise Bad('점수 · 기여도는 한 줄에 하나만')
        pre = '[번외] ' if P.get('extra_active') else ''
        if delta:
            out['delta'] = delta
            return out, '%s%s에게 %+d점' % (pre, name, delta)
        out.update(delta=0, contrib=contrib)
        return out, '%s%s 기여도 %+d' % (pre, name, contrib)
    if type_ == 'pending.assign':
        d = _only(data, ('id', 'name'))
        it = _pending_item(slices, d.get('id'))
        name = str(d.get('name') or '').strip()
        if name not in names:
            raise Bad("지금 판에 없는 선수 '%s'" % name[:20])
        return {'id': it['id'], 'name': name}, '대기함 %s → %s' % (_pending_label(it), name)
    if type_ == 'pending.ignore':
        d = _only(data, ('id',))
        it = _pending_item(slices, d.get('id'))
        return {'id': it['id']}, '대기함 %s 무시' % _pending_label(it)
    if type_ in ('match.start', 'match.pause', 'roulette.spin', 'roulette.stop', 'slot.spin', 'reaction.skip', 'clip.now',
                 'bgm.next', 'bgm.toggle'):
        _only(data, ())
        return {}, {'match.start': '⚔️ 대결 타이머 시작', 'match.pause': '⚔️ 대결 타이머 멈춤', 'roulette.spin': '🎡 룰렛 돌리기',
                    'roulette.stop': '🎡 룰렛 멈추기', 'slot.spin': '🎰 슬롯 돌리기', 'reaction.skip': '⏭ 시그니처 넘기기',
                    'clip.now': '✂️ 클립 남기기', 'bgm.next': '🎵 BGM 다음 곡', 'bgm.toggle': '🎵 BGM 재생 · 멈춤'}[type_]
    if type_ == 'match.set_time':
        d = _only(data, ('min', 'sec'))
        mins = _int(d.get('min') if d.get('min') not in (None, '') else 0, 0, 180, '분')
        secs = _int(d.get('sec') if d.get('sec') not in (None, '') else 0, 0, 59, '초')
        if not mins and not secs:
            raise Bad('0초')
        return {'min': mins, 'sec': secs}, '⏱ 대결 시간 %s' % ('%d분' % mins if mins else '') + (' %d초' % secs if secs else '')
    if type_ == 'match.add_time':
        d = _only(data, ('sec',))
        sec = _int(d.get('sec'), -10800, 10800, '초')
        if not sec:
            raise Bad('0초')
        a = abs(sec)
        return {'sec': sec}, '⏱ 대결 시간 %s%s' % ('+' if sec > 0 else '−', '%d분' % (a // 60) + (' %d초' % (a % 60) if a % 60 else '') if a >= 60 else '%d초' % a)
    if type_ == 'goal.set':
        d = _only(data, ('target',))
        t = _int(d.get('target'), 0, GOAL_MAX, '목표 금액')
        return {'target': t}, '🎯 목표 %s 으로' % _won(t)
    if type_ == 'notice.add':
        d = _only(data, ('text',))
        if len((slices.get('notice') or {}).get('msgs') or []) >= NOTICE_MAX:
            raise Bad('공지가 이미 %d개' % NOTICE_MAX)
        t = _text(d.get('text'), NOTICE_LEN, '공지')
        return {'text': t}, '📢 공지 추가: %s' % t
    if type_ == 'notice.edit':
        d = _only(data, ('index', 'text'))
        msgs = (slices.get('notice') or {}).get('msgs') or []
        if not msgs:
            raise Bad('고칠 공지가 없음')
        i = _int(d.get('index'), 0, len(msgs) - 1, '공지 번호')
        t = _text(d.get('text'), NOTICE_LEN, '공지')
        return {'index': i, 'text': t}, '📢 공지 %d번 고치기: %s' % (i + 1, t)
    if type_ == 'notice.now':
        d = _only(data, ('text', 'index'))
        if d.get('text') not in (None, ''):
            t = _text(d.get('text'), NOTICE_LEN, '공지')
            return {'text': t}, '📢 공지 지금 띄우기: %s' % t
        msgs = (slices.get('notice') or {}).get('msgs') or []
        if not msgs:
            raise Bad('띄울 공지가 없음')
        i = _int(d.get('index', 0), 0, len(msgs) - 1, '공지 번호')
        return {'index': i}, '📢 공지 %d번 지금 띄우기' % (i + 1)
    if type_ in ('cast.say', 'cast.up'):
        d = _only(data, ('text',))
        t = _text(d.get('text'), SAY_MAX if type_ == 'cast.say' else UP_MAX, '글')
        return {'text': t}, ('💬 화면에 한마디: %s' if type_ == 'cast.say' else '⬆ UP 자막: %s') % t
    if type_ == 'show.cue':
        d = _only(data, ('dir',))
        if d.get('dir') not in ('next', 'prev'):
            raise Bad('dir 은 next · prev')
        ps = (slices.get('presets') or {}).get('list') or []
        if not ps:
            raise Bad('순서표가 비었음')
        return {'dir': d['dir']}, '▶ 순서표 다음 단계' if d['dir'] == 'next' else '◀ 순서표 이전 단계'
    if type_ == 'screen.set':
        d = _only(data, ('mode', 'title', 'minutes'))
        mode = d.get('mode')
        if mode not in ('start', 'end', 'off'):
            raise Bad('mode 는 start · end · off')
        out = {'mode': mode}
        if mode != 'off':
            if d.get('title') not in (None, ''):
                out['title'] = _text(d.get('title'), SCREEN_TITLE_MAX, '제목')
            if mode == 'start' and d.get('minutes') not in (None, '', 0):
                out['minutes'] = _int(d.get('minutes'), 0, SCREEN_MIN_MAX, '분')
        label = {'start': '🎬 시작 전 화면', 'end': '🌙 끝 화면', 'off': '🎬 시작 · 끝 화면 내리기'}[mode]
        if out.get('minutes'):
            label += ' (%d분 뒤 시작)' % out['minutes']
        if out.get('title'):
            label += ' — %s' % out['title']
        return out, label
    if type_ == 'show.stage':
        d = _only(data, ('stage',))
        st = d.get('stage')
        if st in ('', 'none', 'null', None):
            return {'stage': None}, '📺 무대 비우기'
        if st not in STAGES:                     # 퇴근빵 · 지옥탈출(hell · home_race)은 판 스위치라 여기서 안 받는다
            raise Bad("모르는 판 '%s'" % str(st)[:20])
        if st == 'quiz' and not (slices.get('quiz') or {}).get('tiles'):
            raise Bad('띄울 퀴즈가 없음')
        return {'stage': st}, '📺 무대에 %s판 띄우기' % STAGE_LABEL.get(st, st)
    if type_ == 'lights.color':
        d = _only(data, ('color',))
        c = str(d.get('color') or '').strip()
        up = c.upper()
        if up in ('RAINBOW', 'OFF'):
            return {'color': up}, '💡 조명 ' + ('무지개' if up == 'RAINBOW' else '끄기')
        h = norm_hex(c)
        if h is None:
            raise Bad("모르는 색 '%s'" % c[:20])
        return {'color': h}, '💡 조명 %s' % h
    if type_ == 'bgm.play':
        d = _only(data, ('title',))
        t = _text(d.get('title'), 120, '곡 제목')
        return {'title': t}, '🎵 BGM: %s' % t
    raise Bad('허용 목록 밖 명령')


# ── 되돌리기 — 바로 앞 값으로 다시 명령(안전한 것만) ─────────
def undo_of(type_, data, slices):
    """바로 실행하기 **전** 조각을 보고 '되돌리기' 명령을 만든다. 되돌릴 수 없는 것(1초 한마디 · 다음 곡)은 None."""
    if type_ == 'notice.add':
        n = len((slices.get('notice') or {}).get('msgs') or [])
        return {'type': 'notice.remove', 'data': {'index': n}, 'text': '방금 넣은 공지 빼기'}
    if type_ == 'notice.edit':
        msgs = (slices.get('notice') or {}).get('msgs') or []
        i = data['index']
        if 0 <= i < len(msgs):
            return {'type': 'notice.edit', 'data': {'index': i, 'text': msgs[i]}, 'text': '공지 %d번을 전 글로' % (i + 1)}
        return None
    if type_ == 'show.stage':
        prev = (slices.get('show') or {}).get('stage')
        return {'type': 'show.stage', 'data': {'stage': prev}, 'text': '무대를 전으로(%s)' % (STAGE_LABEL.get(prev, prev) if prev else '비움')}
    if type_ == 'show.cue':
        s = slices.get('show') or {}
        ps = (slices.get('presets') or {}).get('list') or []
        try:
            at = int(s.get('cue_at', -1))
        except (TypeError, ValueError):
            at = -1
        if 0 <= at < len(ps) and ps[at].get('id'):
            return {'type': 'show.cue', 'data': {'dir': 'go', 'id': ps[at]['id']}, 'text': '순서표를 전 단계로'}
        return None
    if type_ == 'screen.set':
        s = slices.get('screen') or {}
        mode = s.get('mode') or 'off'
        if mode == 'off':
            return {'type': 'screen.set', 'data': {'mode': 'off'}, 'text': '시작 · 끝 화면 내리기'}
        back = {'mode': mode, 'title': s.get('title') or ''}
        if mode == 'start':
            back['names'] = list(s.get('names') or [])
            left = int(s.get('start_at') or 0) - int(time.time() * 1000)
            if left > 0:
                back['minutes'] = max(1, round(left / 60000))
        return {'type': 'screen.set', 'data': back, 'text': '시작 · 끝 화면을 전으로'}
    if type_ == 'lights.color':
        L = slices.get('lights') or {}
        return {'type': 'lights.set', 'data': {'color': L.get('color') or 'OFF', 'audi': bool(L.get('audi'))},
                'text': '조명을 전 색으로'}
    return None


# ── 물음 꼴 · 명령 꼴 ─────────────────────────────────────
_Q_RE = re.compile(r'(\?|？|몇\s*점|몇\s*명|몇\s*번|누구|뭐야|뭐지|무엇|얼마|어때|어떻게|왜|언제|어디|알려|보여\s*줘|순위|있어\s*$|됐어\s*$|맞아\s*$|인가|일까|니\s*$|나요\s*$|까요?\s*$)')
_CMD_RE = re.compile(r'(줘|주라|해라|하라|줘라|주세요|돌려|시작|멈춰|정지|스톱|바꿔|변경|고쳐|수정|띄워|올려|내려|틀어|켜|꺼|넘겨|추가|넣어|빼|배정|무시|해줘|해\s*$|하자|세팅|맞춰|설정|비워|[:：])')


def looks_like_question(text):
    t = str(text or '').strip()
    if re.search(r'[:：]', t):
        return False                               # '공지 바꿔: 누구나 환영' — 콜론 뒤는 글이다
    return bool(_Q_RE.search(t)) and not re.search(r'(돌려|시작|멈춰|띄워|틀어|켜|꺼|바꿔)\s*줘?\s*$', t)


def looks_like_command(text):
    return bool(_CMD_RE.search(str(text or '')))


# ── 서버 규칙(AI 없이) ─────────────────────────────────────
COLOR_WORDS = {'빨강': '#ff0000', '빨간': '#ff0000', '레드': '#ff0000', '파랑': '#0000ff', '파란': '#0000ff', '블루': '#0000ff',
               '초록': '#00ff00', '녹색': '#00ff00', '그린': '#00ff00', '노랑': '#ffff00', '노란': '#ffff00', '옐로': '#ffff00',
               '주황': '#ff9100', '오렌지': '#ff9100', '보라': '#d500f9', '퍼플': '#d500f9', '분홍': '#ff0055', '핑크': '#ff0055',
               '하늘': '#00e5ff', '민트': '#00e5ff', '흰': '#ffffff', '하양': '#ffffff', '화이트': '#ffffff'}
STAGE_WORDS = {'룰렛': 'roulette', '슬롯': 'slot', '대결': 'match', '핀볼': 'pinball', '주사위': 'dicegame', '시그뒤집기': 'siggame',
               '퀴즈': 'quiz'}
_COLON = r'\s*[:：]\s*(.+)$'


def _name_hit(word, names):
    exact = [n for n in names if n == word]
    if exact:
        return exact[0]
    hit = [n for n in names if word and word in n]
    return hit[0] if len(hit) == 1 else None


def rule_plan(text, slices):
    """서버 규칙 — 풀리면 [{type, data}], 못 풀면 None. 검사(check)는 부른 쪽이 똑같이 한다(AI 답과 같은 길)."""
    t = ' '.join(str(text or '').split())
    names = af.current_names(slices)
    msgs = (slices.get('notice') or {}).get('msgs') or []
    m = re.match(r'^공지\s*(?:를|을)?\s*(추가|더해|넣어)\s*(?:줘)?' + _COLON, t)
    if m:
        return [{'type': 'notice.add', 'data': {'text': m.group(2)}}]
    m = re.match(r'^공지\s*(?:를|을)?\s*(?:지금\s*)?(띄워|올려|흘려)\s*(?:줘)?' + _COLON, t)
    if m:
        return [{'type': 'notice.now', 'data': {'text': m.group(2)}}]
    m = re.match(r'^공지\s*(?:를|을)?\s*(바꿔|변경|고쳐|수정)?\s*(?:줘)?' + _COLON, t)
    if m:
        body = m.group(2)
        if msgs:
            return [{'type': 'notice.edit', 'data': {'index': 0, 'text': body}}]
        return [{'type': 'notice.add', 'data': {'text': body}}]
    m = re.match(r'^(?:화면에\s*)?한\s*마디' + _COLON, t)
    if m:
        return [{'type': 'cast.say', 'data': {'text': m.group(1)}}]
    m = re.match(r'^(?:UP|up|업)\s*(?:자막)?' + _COLON, t)
    if m:
        return [{'type': 'cast.up', 'data': {'text': m.group(1)}}]
    m = re.match(r'^대결\s*(?:시간\s*)?(\d{1,3})\s*분\s*(?:(\d{1,2})\s*초)?\s*(시작|으로|로)?\s*(?:해\s*줘|해|줘)?$', t)
    if m:
        out = [{'type': 'match.set_time', 'data': {'min': int(m.group(1)), 'sec': int(m.group(2) or 0)}}]
        if m.group(3) == '시작':
            out.append({'type': 'match.start', 'data': {}})
        return out
    m = re.match(r'^([가-힣A-Za-z0-9]+?)\s*(?:이랑|랑|한테|에게)?\s*기여도\s*([+-]?\d{1,3})\s*(?:줘|추가|만큼)?$', t)
    if m:
        nm = _name_hit(m.group(1), names)
        if nm:
            return [{'type': 'score.add', 'data': {'name': nm, 'contrib': int(m.group(2))}}]
    m = re.match(r'^([가-힣A-Za-z0-9]+?)\s*(?:이한테|한테|에게)?\s*([+-]?\d{1,2})\s*점\s*(?:줘|주기|추가|더)?$', t)
    if m:
        nm = _name_hit(m.group(1), names)
        if nm:
            return [{'type': 'score.add', 'data': {'name': nm, 'delta': int(m.group(2))}}]
    m = re.match(r'^룰렛\s*(멈춰|정지|스톱|세워)', t)
    if m:
        return [{'type': 'roulette.stop', 'data': {}}]
    m = re.match(r'^조명\s*(?:을|를)?\s*(.+?)\s*(?:색|으로|로)?\s*(?:바꿔|해|켜)?\s*(?:줘)?$', t)
    if m:
        w = m.group(1).replace(' ', '')
        if w in ('꺼', '끄기', '끄', 'OFF', 'off'):
            return [{'type': 'lights.color', 'data': {'color': 'OFF'}}]
        if w.startswith('무지개') or w.upper() == 'RAINBOW':
            return [{'type': 'lights.color', 'data': {'color': 'RAINBOW'}}]
        for k, v in COLOR_WORDS.items():
            if w.startswith(k):
                return [{'type': 'lights.color', 'data': {'color': v}}]
        if norm_hex(w):
            return [{'type': 'lights.color', 'data': {'color': w}}]
    if re.match(r'^(시작\s*(전\s*)?화면|대기\s*화면)\s*(띄워|켜|올려)?', t):
        mm = re.search(r'(\d{1,3})\s*분', t)
        d = {'mode': 'start'}
        if mm:
            d['minutes'] = int(mm.group(1))
        return [{'type': 'screen.set', 'data': d}]
    if re.match(r'^(끝\s*화면|엔딩\s*화면|마무리\s*화면)\s*(띄워|켜|올려)?', t):
        return [{'type': 'screen.set', 'data': {'mode': 'end'}}]
    if re.match(r'^(시작|끝)?\s*화면\s*(내려|꺼|치워)', t):
        return [{'type': 'screen.set', 'data': {'mode': 'off'}}]
    m = re.match(r'^(?:무대\s*(?:에)?\s*)?([가-힣]+?)\s*판\s*(?:을|를)?\s*(띄워|올려|켜)', t)
    if m and m.group(1) in STAGE_WORDS:
        return [{'type': 'show.stage', 'data': {'stage': STAGE_WORDS[m.group(1)]}}]
    if re.match(r'^무대\s*(비워|내려|치워)', t):
        return [{'type': 'show.stage', 'data': {'stage': None}}]
    if re.match(r'^(BGM|bgm|브금|음악|노래)\s*(다음|넘겨|스킵)', t):
        return [{'type': 'bgm.next', 'data': {}}]
    if re.match(r'^(BGM|bgm|브금|음악|노래)\s*(틀어|켜|멈춰|꺼|재생|정지)\s*(줘)?$', t):
        return [{'type': 'bgm.toggle', 'data': {}}]
    return None


# ── AI(Claude 도구 쓰기) ─────────────────────────────────
TOOL_NAME = 'propose_commands'


def tool_def():
    return {
        'name': TOOL_NAME,
        'description': '진행자의 말을 방송 프로그램 명령으로 바꾼다. 명령이 아니거나 무엇을 할지 모르면 commands 를 비우고 reply 로 되묻는다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'commands': {'type': 'array', 'maxItems': PROPOSE_MAX, 'items': {
                    'type': 'object',
                    'properties': {'type': {'type': 'string', 'enum': list(ALLOW)},
                                   'data': {'type': 'object'}},
                    'required': ['type', 'data']}},
                'reply': {'type': 'string', 'description': '진행자에게 한 줄(한국어). 되물을 때만 길게.'},
            },
            'required': ['commands'],
        },
    }


def system_prompt(slices, bgm=None):
    names = af.current_names(slices)
    pend = [x for x in (slices.get('pending') or []) if isinstance(x, dict) and x.get('type') != 'off_work'
            and x.get('kind') != 'contrib'][:12]
    msgs = (slices.get('notice') or {}).get('msgs') or []
    ps = (slices.get('presets') or {}).get('list') or []
    stage = (slices.get('show') or {}).get('stage')
    lines = [
        '너는 라이브 방송 조종실의 명령 비서다. 진행자의 한국어 말을 아래 명령 목록에 있는 것으로만 바꾼다.',
        '규칙: 말한 것만 한다(추측해서 더하지 않는다). 이름은 선수 명단에 있는 그대로. 대기함은 id 를 그대로 쓴다.',
        '명령이 아니거나(질문 · 잡담) 누구 · 무엇인지 애매하면 commands 를 비우고 reply 로 짧게 되묻는다.',
        '반드시 %s 도구로만 답한다.' % TOOL_NAME,
        '',
        '명령 목록(type: data):',
    ]
    lines += ['- %s: %s' % (k, HELP[k]) for k in ALLOW]
    lines += ['', '지금 상황:',
              '- 선수: %s' % (', '.join(names) or '(없음)'),
              '- 대기함: %s' % ('; '.join('id=%s %s %s %s' % (x.get('id'), str(x.get('name') or '')[:16], _won(x.get('amount')),
                                                            json.dumps(str(x.get('message') or '')[:40], ensure_ascii=False))
                                         for x in pend) or '(비었음)'),
              '- 공지: %s' % ('; '.join('%d=%s' % (i, m[:40]) for i, m in enumerate(msgs[:10])) or '(없음)'),
              '- 무대: %s' % (STAGE_LABEL.get(stage, stage) if stage else '비었음'),
              '- 순서표 단계: %s' % (', '.join(str(p.get('name') or '')[:16] for p in ps[:12]) or '(없음)'),
              '- 조명 색 예: %s · RAINBOW · OFF' % ', '.join(DEFAULT_COLORS[:6])]
    if bgm:
        lines.append('- BGM 목록: %s' % ' / '.join(str(b)[:40] for b in bgm[:30]))
    return '\n'.join(lines)


def ai_plan(text, slices, bgm=None):
    """Claude 에게 묻는다(막히는 호출 — 다른 갈래에서). 돌려받는 값: (proposals | None, reply, why_none)."""
    uses, said, code = ai.ai_tools(system_prompt(slices, bgm), [{'role': 'user', 'content': text}], [tool_def()],
                                   tool_choice={'type': 'tool', 'name': TOOL_NAME}, max_tokens=700, timeout=AI_TIMEOUT)
    if code != 200:
        return None, '', str(code)
    props, reply = [], said
    for name, inp in uses:
        if name != TOOL_NAME or not isinstance(inp, dict):
            continue                                  # 모르는 도구 · 이상한 입력 — 통째로 버린다
        cmds = inp.get('commands')
        if isinstance(inp.get('reply'), str):
            reply = inp['reply']
        if isinstance(cmds, list):
            for c in cmds[:PROPOSE_MAX]:
                if isinstance(c, dict):
                    props.append({'type': c.get('type'), 'data': c.get('data')})
                else:
                    props.append({'type': None, 'data': None})
    return props, ' '.join(str(reply or '').split())[:300], ''


# ── 바로 실행 상한 ──
def _direct_ok(now=None):
    """1분 안에 바로 실행이 10개 미만이면 True(그리고 하나를 센다)."""
    now = time.time() if now is None else now
    with _direct_lock:
        while _direct_at and now - _direct_at[0] > 60:
            _direct_at.popleft()
        if len(_direct_at) >= DIRECT_PER_MIN:
            return False
        _direct_at.append(now)
        return True


async def plan_and_run(bus, text, bgm=None):
    """말 하나 → 답(위 '받는 것'). ⚠️ SAFE 가 아닌 명령은 절대 bus.run 하지 않는다 — 카드로만 돌려준다."""
    text = ' '.join(str(text or '').split())[:TEXT_MAX]
    if not text:
        return {'status': 'success', 'kind': 'none', 'cards': [], 'reply': '무엇을 할까요?'}
    slices = bus.state.slices
    props = rule_plan(text, slices)
    source = 'rule'
    reply = ''
    if props is None:
        if looks_like_question(text) or not looks_like_command(text):
            return {'status': 'success', 'kind': 'question', 'cards': []}
        if not ai.claude_key():
            return {'status': 'success', 'kind': 'none', 'cards': [], 'note': 'AI 가 꺼져 있어요'}
        try:
            props, reply, why = await asyncio.wait_for(asyncio.to_thread(ai_plan, text, slices, bgm), AI_DEADLINE)
        except asyncio.TimeoutError:
            props, reply, why = None, '', 'timeout'
        if props is None:
            return {'status': 'success', 'kind': 'none', 'cards': [], 'note': 'AI 가 붐벼요 (%s)' % (why or '?')}
        source = 'ai'
        slices = bus.state.slices                      # AI 를 기다리는 사이 바뀌었을 수 있다 — 지금 것으로 검사
    cards, dropped = [], []
    for p in props:
        t = p.get('type')
        try:
            data, label = check(t, p.get('data'), slices)
        except Bad as e:
            dropped.append({'type': str(t or '?')[:30], 'why': str(e)})
            continue
        cards.append({'id': 'k' + uuid.uuid4().hex[:8], 'type': t, 'data': data, 'text': label, 'safe': t in SAFE,
                      'state': 'ask'})
    if not cards:
        out = {'status': 'success', 'kind': 'reply' if (reply or dropped) else 'none', 'source': source, 'cards': [],
               'reply': reply or ('할 수 있는 명령으로 못 바꿨어요' if dropped else '')}
        if dropped:
            out['dropped'] = dropped
        return out
    direct = bool((bus.state.slices.get('ai_opts') or {}).get('direct', True))
    ran, note = 0, ''
    for c in cards:
        if not (direct and c['safe']):
            continue
        if ran >= DIRECT_PER_SAY:
            note = '한 번에 바로 하는 건 %d개까지예요 — 나머지는 눌러서 실행해 주세요' % DIRECT_PER_SAY
            break
        if not _direct_ok():
            note = '1분에 %d개가 넘어 바로 하기를 멈췄어요 — 눌러서 실행해 주세요' % DIRECT_PER_MIN
            break
        ran += 1
        if c['type'] in CLIENT:
            c['state'] = 'client'                       # 조종실 브라우저가 받자마자 한다
            continue
        undo = undo_of(c['type'], c['data'], bus.state.slices)
        try:
            res = await bus.run(c['type'], dict(c['data']), by='ai', authed=True)
        except Exception as e:
            res = {'ok': False, 'error': type(e).__name__}
        if res.get('ok'):
            c['state'] = 'ran'
            if undo:
                c['undo'] = undo
        else:
            c['state'] = 'failed'
            c['error'] = str(res.get('error') or '실패')[:120]
    out = {'status': 'success', 'kind': 'command', 'source': source, 'cards': cards, 'reply': reply}
    if dropped:
        out['dropped'] = dropped
    if note:
        out['note'] = note
    return out


# ── 명령 · 주소 ───────────────────────────────────────────
@command('ai.set')
def ai_set(ctx, data):
    """{direct: true|false} — '🤖 안전한 건 AI 가 바로'(끄면 전부 [실행] 카드)."""
    if not isinstance(data.get('direct'), bool):
        raise CommandError('direct 는 true · false 입니다')
    ctx.edit('ai_opts')['direct'] = data['direct']
    ctx.notes['direct'] = data['direct']


@route('/api/ai/command')
async def ai_command(req, bus, authed, answer):
    if not authed(req):
        return JSONResponse({'status': 'error', 'message': '로그인이 필요합니다'}, status_code=401)
    try:
        body = await req.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}
    bgm = [str(x)[:80] for x in (body.get('bgm') or [])[:50]] if isinstance(body.get('bgm'), list) else None
    try:
        return await plan_and_run(bus, body.get('text'), bgm)
    except Exception as e:
        print('⚠️ [말로 조종] %s' % type(e).__name__, flush=True)
        return {'status': 'success', 'kind': 'none', 'cards': [], 'note': '(오류) %s' % type(e).__name__}
