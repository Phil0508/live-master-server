# -*- coding: utf-8 -*-
"""🧮 AI 도우미의 '사실표' · 즉답 · 프롬프트 (2026-09-29 개편).

왜 만들었나
  실제로 물어보니 AI 가 계산을 틀렸다 — 3만 원을 +30점이라 하고, 방송 목표(점수)를 오늘 후원 합계(원)와
  비교해 "이미 초과 달성" 이라 했고, 퇴근빵 목표를 엉뚱한 사람에게 붙였다. 답도 한 번에 20줄씩 길었고
  "예지랑에게 몰아주면 역전" 같은 조언까지 했다(후원은 후원자가 말한 사람에게 가야 한다).
  NVIDIA 의 다른 무료 모델은 15~40초씩 걸려 못 쓴다 → 모델을 바꾸는 대신 '생각할 거리를 줄인다'.

  ① 사실표 — 순위 · 차이 · 목표까지 남은 점수 · 퇴근빵 남은 점수 · 대기함 점수 · 대결 남은 시간을
     서버가 전부 계산해서 넘긴다. AI 는 옮겨 적기만 한다.
  ② 즉답 — 자주 묻는 것(순위 · 대기함 · 목표 · 대결 · 퇴근빵 · 오늘 후원 · 시그 · 최근 흐름)은
     AI 없이 사실표로 바로 답한다. 0초 · 틀릴 일 없음 · NVIDIA 가 붐벼도 된다.
  ③ 프롬프트 — 짧게(5줄), 한국어만, 묻지 않은 전략 조언 금지.

⚠️ 이 파일은 server 를 부르지 않는다(순수 함수만). 검사와 실력 재기(ai_eval)에서 서버 없이 쓴다.
"""
import json
import re
import time

# ── 공용 셈 ─────────────────────────────────────────────


def man_won(amount):
    """금액 → 점수. server.man_won · 조종실 manWon() 과 같은 식(4천 원부터 올림)."""
    try:
        return (int(amount) + 4000) // 10000
    except (TypeError, ValueError):
        return 0


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def won(n):
    """30000 → '3만 원', 4870000 → '487만 원', 12500 → '12,500원', 1억 2천만 → '1억 2,000만 원'."""
    n = _int(n)
    if n and n % 10000 == 0:
        eok, man = divmod(n // 10000, 10000)
        if eok:    # ⚠️ '6,000,000만 원' 처럼 읽기 어려운 글자가 나왔다(샌드박스 목표 60억)
            return f"{eok:,}억" + (f" {man:,}만" if man else '') + " 원"
        return f"{man:,}만 원"
    return f"{n:,}원"


def ga(name):
    """받침이 있으면 '이', 없으면 '가' — '예지랑이', '밍밍이', '하율이'."""
    ch = str(name or '').strip()[-1:]
    c = ord(ch) if ch else 0
    if not (0xAC00 <= c <= 0xD7A3):
        return '이(가)'
    return '이' if (c - 0xAC00) % 28 else '가'


def mmss(ms):
    s = max(0, _int(ms) // 1000)
    return f"{s // 60}:{s % 60:02d}"


# ── 이름 모양 ───────────────────────────────────────────
# 이름 뒤에 흔히 붙는 조사·호칭. '철수형' → '철수' 로 되돌리려고 쓴다.
#    ⚠️ 순서가 뜻이 있다 — 앞의 것부터 떼 본다('님께' 를 '께' 보다 먼저). features/ai.py 에서 옮겨 왔다.
NAME_TAILS = ('에게', '한테', '이랑', '님께', '님', '씨', '형', '누나', '오빠', '언니',
              '쨩', '찡', '아', '야', '이', '가', '은', '는', '을', '를', '와', '과',
              '랑', '도', '만', '께')
_SPLIT = r'[\s,./!?~\-()\[\]"\'·:;]+'


def name_forms(word):
    """낱말 하나에서 '이름일 수 있는 모양'들을 만든다(조사·호칭을 두 번까지 뗀다)."""
    out = {word}
    cur = word
    for _ in range(2):
        for t in NAME_TAILS:
            if len(cur) > len(t) and cur.endswith(t):
                cur = cur[:-len(t)]
                out.add(cur)
                break
        else:
            break
    return out


_CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'


def chosung(s):
    out = []
    for ch in str(s or ''):
        c = ord(ch)
        out.append(_CHO[(c - 0xAC00) // 588] if 0xAC00 <= c <= 0xD7A3 else ch)
    return ''.join(out)


def _is_subseq(short, long_):
    it = iter(long_)
    return all(ch in it for ch in short)


def nickname_hints(msg, names):
    """메시지 속 낱말이 선수 이름의 '일부' 인 경우를 찾는다. {선수: 근거}.

       '행복이' → 행복한걸(앞), '지랑이' → 예지랑(뒤), '행걸' → 행복한걸(줄임), 'ㅎㅂㅎㄱ' → 행복한걸(초성).
       ⚠️ 이것만으로 배정하지 않는다 — '대단한걸' 도 '행복한걸' 과 뒤가 겹친다. AI 에게 힌트로 주고,
          AI 가 못 답할 때만 '추천(확인 필요)' 으로 올린다.
    """
    hits = {}
    txt = str(msg or '')
    for w in re.split(_SPLIT, txt):
        w = w.strip()
        if not w:
            continue
        for f in name_forms(w):
            if len(f) < 2:
                continue
            for n in names:
                if not n or f == n or n in hits:
                    continue
                if len(n) >= 3 and n.startswith(f):
                    hits[n] = f"'{f}' 는 '{n}' 이름 앞부분"
                elif len(n) >= 3 and n.endswith(f):
                    hits[n] = f"'{f}' 는 '{n}' 이름 뒷부분"
                elif all('ㄱ' <= c <= 'ㅎ' for c in f) and chosung(n) == f:
                    hits[n] = f"'{f}' 는 '{n}' 의 초성"
                elif len(n) >= 3 and f[0] == n[0] and f[-1] == n[-1] and _is_subseq(f, n):
                    hits[n] = f"'{f}' 는 '{n}' 의 줄임"
    return hits


# ── ① 사실표 ───────────────────────────────────────────


def _log_minutes(hms, now_min):
    """'HH:MM:SS' → 지금보다 몇 분 전인가. 자정을 넘긴 것도 센다."""
    try:
        h, m = [int(x) for x in str(hms).split(':')[:2]]
    except Exception:
        return None
    ago = now_min - (h * 60 + m)
    if ago < 0:
        ago += 24 * 60
    return ago


def _kst_now_min(now=None):
    t = time.gmtime((now or time.time()) + 9 * 3600)
    return t.tm_hour * 60 + t.tm_min


def build_facts(state, today=None, vip=None, suggest=None, now=None):
    """AI 에게 넘길 사실표. 계산할 것은 전부 여기서 끝낸다.

       today   — _today_donations() 결과(장부에서 센 오늘 후원)
       vip     — _ai_vip_list() 결과
       suggest — 대기 후원 하나를 받아 이미 해 둔 배정 판단을 돌려주는 함수(없으면 None)
       now     — 시험용 지금 시각(초)
    """
    now = now or time.time()
    now_ms = int(now * 1000)
    extra = bool(state.get('extra_game_active'))
    players = state.get('extra_bjs' if extra else 'bjs') or []
    rows = sorted(({'이름': b.get('name'), '점수': _int(b.get('score')), '기여도': _int(b.get('contribution'))}
                   for b in players if b.get('name')), key=lambda r: r['기여도'], reverse=True)
    rank = []
    for i, r in enumerate(rows):
        e = dict(순위=i + 1, **r)
        if i:
            e['윗순위와_기여도차'] = rows[i - 1]['기여도'] - r['기여도']
            e['윗순위와_점수차'] = rows[i - 1]['점수'] - r['점수']
        rank.append(e)

    f = {
        '방송': '진행 중' if state.get('broadcast_active') else '꺼짐',
        '판': '임시게임(엑스트라)' if extra else '본게임',
        '단위': '점수 1점 = 후원 1만 원(4천 원부터 올림). 순위는 기여도 순.',
        '순위': rank,
    }

    # 목표 — 막대와 같은 셈(선수 점수 합 + 운영비 + 보정). 단위는 점수다.
    tgt = _int(state.get('target_goal'))
    #    ⚠️ goal_offset 은 방송판(overlay)이 점수 합에 그대로 더한다 — 여기서도 그대로 더한다.
    cur = _int((state.get('bottom_fixed') or {}).get('score')) + sum(r['점수'] for r in rows) \
        + _int(state.get('goal_offset'))
    if tgt > 0:
        f['목표'] = {'목표점수': tgt, '현재점수': cur, '남은점수': max(0, tgt - cur),
                   '달성률': f"{min(999, cur * 100 // tgt)}%", '달성': cur >= tgt,
                   '연출_승인_대기': bool(cur >= tgt and not state.get('goal_event_approved'))}
    else:
        f['목표'] = '목표 없음'

    # 대기함 — 점수 환산 · 기다린 시간 · 이미 해 둔 배정 판단
    pend = []
    for d in (state.get('pending_donations') or []):
        if not isinstance(d, dict) or d.get('type') == 'off_work':
            continue
        e = {'후원자': d.get('name') or '익명', '금액': _int(d.get('amount')),
             '점수': man_won(d.get('amount')), '메시지': (d.get('message') or '')[:80]}
        if d.get('kind') == 'contrib':
            e['종류'] = '기여도 알림(후원 아님)'
        m = re.match(r'^don_(\d+)', str(d.get('id') or ''))
        if m:
            e['기다린_분'] = max(0, (now_ms - int(m.group(1))) // 60000)
        if suggest and d.get('kind') != 'contrib':
            try:
                s = suggest(d)
            except Exception:
                s = None
            if s:
                e['추천'] = s
        pend.append(e)
    f['대기함'] = pend
    f['대기함_합계'] = {'건수': len(pend), '금액': sum(p['금액'] for p in pend),
                    '점수': sum(p['점수'] for p in pend)}

    # 대결
    md = state.get('match_data') or {}
    if md.get('active') and md.get('players'):
        ps = sorted(({'이름': p.get('name'), '점수': _int(p.get('score'))} for p in md.get('players') or []),
                    key=lambda p: p['점수'], reverse=True)
        if md.get('is_running') and md.get('end_time_ms'):
            left = max(0, _int(md.get('end_time_ms')) - now_ms)
            st = f'진행 중 · {mmss(left)} 남음'
        elif md.get('is_running'):
            st = f"진행 중 · {mmss(md.get('time_left_ms'))} 남음"
        else:
            left = md.get('paused_time_left', md.get('time_left_ms'))
            st = f'멈춤 · {mmss(left)} 남음' if _int(left) else '멈춤(시간 끝)'
        e = {'상태': st, '점수': ps}
        if len(ps) >= 2:
            gap = ps[0]['점수'] - ps[1]['점수']
            e['앞선_쪽'] = ps[0]['이름'] if gap else '동점'
            e['차이'] = gap
        f['대결'] = e
    else:
        f['대결'] = '대결 안 함'

    # 퇴근빵 · 지옥탈출 — 진행 기준은 점수(방송판과 같다). 지금 선수만.
    hell = state.get('hell') or {}
    race_on = bool(state.get('home_race_enabled')) or bool(hell.get('on'))
    goals = (hell.get('goals') if hell.get('on') else state.get('home_goals')) or {}
    base = (hell.get('base') or {}) if hell.get('on') else {}
    race = []
    for r in rows:
        g = _int(goals.get(r['이름']))
        if g <= 0:
            continue
        c = max(0, r['점수'] - _int(base.get(r['이름']))) if hell.get('on') else r['점수']
        race.append({'이름': r['이름'], '현재': c, '목표': g, '남은점수': max(0, g - c), '달성': c >= g})
    race.sort(key=lambda x: (x['달성'], x['남은점수']))
    if race or race_on:
        f['퇴근빵'] = {'이름': '지옥탈출' if hell.get('on') else '퇴근빵',
                    '켜짐': race_on, '선수별': race,
                    '가장_가까운_미달성': next((x['이름'] for x in race if not x['달성']), None)}

    # 최근 흐름 — 최근 15분(없으면 최근 20줄) 사람별 점수 합
    logs = [l for l in (state.get('logs') or []) if isinstance(l, dict) and l.get('kind') != 'contrib']
    nm = _kst_now_min(now)
    ago = [(l, _log_minutes(l.get('time'), nm)) for l in logs]
    win = [l for l, a in ago if a is not None and a <= 15]     # ⚠️ 'or 999' 로 쓰면 방금(0분 전) 것이 빠진다
    span = '최근 15분'
    if not win:
        win, span = logs[:20], f'최근 {min(20, len(logs))}건'
    flow = {}
    for l in win:
        flow[l.get('name')] = flow.get(l.get('name'), 0) + _int(l.get('val'))
    if flow:
        top = sorted(flow.items(), key=lambda kv: kv[1], reverse=True)
        f['최근_흐름'] = {'기간': span + (f" ({win[-1].get('time')}~{win[0].get('time')})" if win else ''),
                      '사람별_점수합': dict(top), '가장_많이_오른_사람': top[0][0]}

    if today:
        f['오늘_후원'] = today

    # 시그니처 — 많이 나온 것 · 많이 쏜 사람(횟수 · 금액)
    tally = state.get('sig_tally') or {}
    sig_rows = sorted(({'제목': v.get('title'), '횟수': _int(v.get('count')), '금액': _int(v.get('amount'))}
                       for v in tally.values()), key=lambda x: x['횟수'], reverse=True)
    donor = {}
    for v in tally.values():
        amt = _int(v.get('amount'))
        for who, cnt in (v.get('donors') or {}).items():
            row = donor.setdefault(who, {'이름': who, '횟수': 0, '금액합': 0})
            row['횟수'] += _int(cnt)
            row['금액합'] += _int(cnt) * amt
    if sig_rows:
        f['시그니처'] = {'많이_나온_것': sig_rows[:5],
                     '횟수_순': sorted(donor.values(), key=lambda x: x['횟수'], reverse=True)[:5],
                     '금액_순': sorted(donor.values(), key=lambda x: x['금액합'], reverse=True)[:5]}

    rq = state.get('reaction_queue') or []
    if rq:
        f['리액션_대기줄'] = [f"{x.get('title') or '시그니처'}" + (f" ×{x.get('count')}" if _int(x.get('count')) > 1 else '')
                        for x in rq[:5]] + ([f'…그 외 {len(rq) - 5}개'] if len(rq) > 5 else [])
    games = []
    if state.get('slot_enabled'):
        games.append('슬롯 켜짐')
    roul = state.get('roulette') or {}
    if state.get('roulette_enabled'):
        games.append('룰렛 켜짐' + (f" · 당첨 {roul.get('winner_name')}" if roul.get('winner_name') else ''))
    if games:
        f['게임'] = games
    if vip:
        f['VIP'] = vip[:10]
    return f


def facts_for_ai(f):
    """사실표를 AI 가 옮겨 적기 좋은 글자로 바꾼다.

       ⚠️ 숫자를 날것(4870000)으로 주면 '4870000 (원)' 처럼 그대로 옮기거나 '오늘_후원.합계금액' 같은
          항목 이름까지 답에 적었다. 돈은 '487만 원' 으로, 추천은 '행복한걸(확인 필요)' 로 미리 써 준다.
    """
    g = json.loads(json.dumps(f, ensure_ascii=False))
    for e in g.get('대기함') or []:
        e['금액'] = won(e.get('금액'))
        e['점수'] = f"{e.get('점수')}점"
        if '기다린_분' in e:
            e['기다린_시간'] = f"{e.pop('기다린_분')}분째"
        s = e.pop('추천', None)
        if isinstance(s, dict):
            e['누구_것'] = (s['target'] + ('' if s.get('tier') == 'auto' else '(확인 필요)')) if s.get('target') \
                else '모름(사람이 봐야 함)'
    s = g.get('대기함_합계')
    if isinstance(s, dict):
        g['대기함_합계'] = f"{s.get('건수')}건 · {won(s.get('금액'))} · {s.get('점수')}점"
    gl = g.get('목표')
    if isinstance(gl, dict):
        gl['남은_금액'] = won(_int(gl.get('남은점수')) * 10000)
    t = g.get('오늘_후원')
    if isinstance(t, dict):
        g['오늘_후원'] = {'건수': f"{_int(t.get('건수')):,}건", '합계': won(t.get('합계금액')),
                       '많이_쏜_사람': [f"{x.get('이름')} {won(x.get('금액합'))}({_int(x.get('횟수'))}건)"
                                    for x in (t.get('많이_쏜_사람') or [])]}
    s = g.get('시그니처')
    if isinstance(s, dict):
        g['시그니처'] = {
            '많이_나온_시그': [f"{x['제목']} {x['횟수']}번({won(x['금액'])}짜리)" for x in s.get('많이_나온_것') or []],
            '많이_쏜_사람_횟수순': [f"{x['이름']} {x['횟수']}번" for x in s.get('횟수_순') or []],
            '많이_쏜_사람_금액순': [f"{x['이름']} {won(x['금액합'])}" for x in s.get('금액_순') or []]}
    return g


_HANGUL = re.compile(r'[가-힣ㄱ-ㅣ]')


def looks_broken(text):
    """모델이 가끔 깨진 글자를 뱉는다(실측: '재시 가장의 ( :1{" TEXT [[[H0[[[0…'). 그대로 보이면 안 된다."""
    t = str(text or '')
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 2:
        return True
    if len(_HANGUL.findall(t)) < len(letters) * 0.5:
        return True
    return bool(re.search(r'\[\[|\{"|TEXT', t))


def board_tiles(f):
    """조종실 AI 패널 위 상황판 네 칸(B안). 사실표에서 바로 — AI 를 안 부른다.

       [{intent, k(머리글), v(큰 글자), s(작은 글자), hot(주황), pct(목표 막대)}]
       칸을 누르면 같은 intent 의 즉답이 대화에 뜬다.
    """
    out = []
    allp = f.get('대기함') or []
    p = [x for x in allp if not x.get('종류')]          # 기여도 알림은 후원이 아니다
    if p:
        old = max(p, key=lambda x: _int(x.get('기다린_분')))
        mins = _int(old.get('기다린_분'))
        out.append({'intent': 'pending', 'k': '📥 대기함' + (f' · {mins}분째 있음' if mins else ''),
                    'v': f"{len(p)}건 · {sum(_int(x.get('점수')) for x in p)}점",
                    's': f"가장 오래: {old['후원자']} {won(old['금액'])}",
                    'hot': mins >= 3})              # 조종실 '3분째 대기' 알림과 같은 기준
    else:
        out.append({'intent': 'pending', 'k': '📥 대기함', 'v': '비어 있음',
                    's': f'기여도 알림 {len(allp)}건' if allp else '', 'hot': False})

    m = f.get('대결')
    if isinstance(m, dict):
        st = m.get('상태') or ''
        tm = re.search(r'\d+:\d\d', st)
        k = '⚔️ 대결 · ' + ('멈춤' if st.startswith('멈춤') else (tm.group(0) if tm else '진행 중'))
        ps = m.get('점수') or []
        if m.get('앞선_쪽') == '동점':
            v = '동점'
        elif m.get('앞선_쪽'):
            v = f"{m['앞선_쪽']} +{m['차이']}"
        else:
            v = ps[0]['이름'] if ps else '-'
        out.append({'intent': 'match', 'k': k, 'v': v,
                    's': ' : '.join(f"{x['이름']} {x['점수']}" for x in ps), 'hot': False})
    else:
        out.append({'intent': 'match', 'k': '⚔️ 대결', 'v': '안 함', 's': '', 'hot': False})

    g = f.get('목표')
    if isinstance(g, dict):
        wait = bool(g.get('연출_승인_대기'))
        out.append({'intent': 'goal', 'k': '🎯 목표' + (' · 연출 승인 대기' if wait else ''),
                    'v': f"{g['현재점수']:,} / {g['목표점수']:,}점",
                    's': '달성!' if g['달성'] else f"{g['남은점수']:,}점 남음",
                    'pct': max(0, min(100, g['현재점수'] * 100 // max(1, g['목표점수']))), 'hot': wait})
    else:
        out.append({'intent': 'goal', 'k': '🎯 목표', 'v': '목표 없음', 's': '', 'hot': False})

    r = f.get('퇴근빵') or {}
    rows = r.get('선수별') or []
    if rows:
        nm = r.get('이름') or '퇴근빵'
        near = r.get('가장_가까운_미달성')
        done = [x['이름'] for x in rows if x['달성']]
        if near:
            e = next(x for x in rows if x['이름'] == near)
            v = f"{near} {e['남은점수']:,}점 남음"
        else:
            v = '전원 달성'
        out.append({'intent': 'race', 'k': f'🏃 {nm}' + ('' if r.get('켜짐') else ' · 꺼짐'), 'v': v,
                    's': ('달성: ' + ' · '.join(done)) if (done and near) else '', 'hot': False})
    else:
        out.append({'intent': 'race', 'k': '🏃 퇴근빵', 'v': '목표 없음', 's': '', 'hot': False})
    return out


# ── ② 즉답 ─────────────────────────────────────────────
# 조종실의 빠른 질문 단추가 부른다. AI 가 붐벼 답을 못 받았을 때도 이걸로 답한다.

INTENTS = {
    'rank':    '📊 순위',
    'pending': '📥 대기함',
    'goal':    '🎯 목표',
    'match':   '⚔️ 대결',
    'race':    '🏃 퇴근빵',
    'today':   '💰 오늘 후원',
    'sig':     '🎵 시그 순위',
    'flow':    '📈 최근 흐름',
}

_INTENT_RE = [
    ('match',   r'대결|매치'),
    ('race',    r'퇴근|지옥'),
    ('goal',    r'목표'),
    ('pending', r'대기|밀린|안\s*준|배정\s*안|누구\s*(한테|에게)\s*(줘|줄)'),
    ('sig',     r'시그'),
    ('flow',    r'치고|급상승|올라온|상승세|떡상|요즘|최근.*(누가|많이)'),
    ('today',   r'(오늘|총|전체).*(후원|얼마|합계|몇\s*건)|후원.*(합계|총|몇\s*건)'),
    ('rank',    r'[1-9일이삼]\s*등|순위|랭킹|차이'),
]


def detect_intent(question):
    q = str(question or '')
    for key, pat in _INTENT_RE:
        if re.search(pat, q):
            return key
    return None


def _b(s):
    return f"**{s}**"


def quick_answer(intent, f):
    """사실표 → 사람이 읽을 답. 모르는 intent 면 None."""
    if intent == 'rank':
        r = f.get('순위') or []
        if not r:
            return '지금 점수판에 선수가 없어요.'
        top = r[0]
        out = [f"1등은 {_b(top['이름'])} — 기여도 {top['기여도']:,} (점수 {top['점수']:,})"]
        for e in r[1:]:
            out.append(f"- {e['순위']}등 {e['이름']} {e['기여도']:,} (점수 {e['점수']:,}) · 윗순위와 {e['윗순위와_기여도차']:,} 차")
        return '\n'.join(out)

    if intent == 'pending':
        p, s = f.get('대기함') or [], f.get('대기함_합계') or {}
        if not p:
            return '대기함이 비어 있어요.'
        out = [f"대기함 {_b(str(s.get('건수')) + '건')} · {won(s.get('금액'))} ({s.get('점수')}점)"]
        for e in sorted(p, key=lambda e: -_int(e.get('기다린_분'))):
            if e.get('종류'):
                out.append(f"- {e['후원자']} · {e['종류']}")
                continue
            line = f"- {e['후원자']} {won(e['금액'])}({e['점수']}점)"
            if e.get('메시지'):
                line += f" \"{e['메시지'][:24]}\""
            if e.get('기다린_분'):
                line += f" · {e['기다린_분']}분째"
            sg = e.get('추천')
            if sg and sg.get('target'):
                line += f" → {sg['target']}" + ('' if sg.get('tier') == 'auto' else '(확인 필요)')
            elif sg:
                line += ' → 누구 것인지 모름'
            out.append(line)
        return '\n'.join(out)

    if intent == 'goal':
        g = f.get('목표')
        if not isinstance(g, dict):
            return '방송 목표가 정해져 있지 않아요. (조종실에서 목표 점수를 넣으면 셀 수 있어요)'
        if g['달성']:
            head = f"목표 {_b('달성')} — {g['현재점수']:,} / {g['목표점수']:,}점 ({g['달성률']})"
            if g.get('연출_승인_대기'):
                head += '\n- 목표 연출이 승인을 기다리고 있어요'
            return head
        return (f"목표까지 {_b(format(g['남은점수'], ',') + '점')} 남았어요 ({won(g['남은점수'] * 10000)})\n"
                f"- 지금 {g['현재점수']:,} / {g['목표점수']:,}점 ({g['달성률']})")

    if intent == 'match':
        m = f.get('대결')
        if not isinstance(m, dict):
            return '지금 대결은 꺼져 있어요.'
        ps = m.get('점수') or []
        board = ' : '.join(f"{p['이름']} {p['점수']}" for p in ps)
        if m.get('앞선_쪽') == '동점':
            head = f"대결 {_b('동점')} — {board}"
        elif m.get('앞선_쪽'):
            head = f"{_b(m['앞선_쪽'])}{ga(m['앞선_쪽'])} {m['차이']}점 앞서요 — {board}"
        else:
            head = f"대결 — {board}"
        return head + f"\n- {m.get('상태')}"

    if intent == 'race':
        r = f.get('퇴근빵')
        if not r:
            return '퇴근빵 목표가 없어요.'
        nm = r.get('이름') or '퇴근빵'
        rows = r.get('선수별') or []
        if not rows:
            return f"{nm} 목표가 지금 선수들에게 안 들어가 있어요."
        out = []
        near = r.get('가장_가까운_미달성')
        if near:
            e = next(x for x in rows if x['이름'] == near)
            out.append(f"가장 가까운 사람은 {_b(near)} — {e['남은점수']:,}점 남음 ({e['현재']:,}/{e['목표']:,})")
        else:
            out.append(f"{nm} {_b('전원 달성')}!")
        for e in rows:
            if e['이름'] == near:
                continue
            out.append(f"- {e['이름']} " + ('달성 ✓' if e['달성'] else f"{e['남은점수']:,}점 남음")
                       + f" ({e['현재']:,}/{e['목표']:,})")
        if not r.get('켜짐'):
            out.append(f'- {nm}은 지금 방송판에 꺼져 있어요')
        return '\n'.join(out)

    if intent == 'today':
        t = f.get('오늘_후원')
        if not t:
            return '오늘 후원 장부를 못 읽었어요. 잠시 뒤 다시 눌러 주세요.'
        out = [f"오늘 후원 {_b(format(_int(t.get('건수')), ',') + '건')} · {won(t.get('합계금액'))}"]
        for e in (t.get('많이_쏜_사람') or [])[:3]:
            out.append(f"- {e['이름']} {won(e['금액합'])} ({e['횟수']}건)")
        return '\n'.join(out)

    if intent == 'sig':
        s = f.get('시그니처')
        if not s:
            return '이번 방송에 나온 시그니처가 아직 없어요.'
        cnt, amt = s['횟수_순'], s['금액_순']
        out = [f"시그 제일 많이 쏜 사람: {_b(cnt[0]['이름'])} {cnt[0]['횟수']}번"]
        if amt and amt[0]['이름'] != cnt[0]['이름']:
            out.append(f"- 금액으로는 {amt[0]['이름']} {won(amt[0]['금액합'])}")
        top = s['많이_나온_것'][0]
        out.append(f"- 제일 많이 나온 시그: {top['제목']} {top['횟수']}번")
        return '\n'.join(out)

    if intent == 'flow':
        fl = f.get('최근_흐름')
        if not fl:
            return '최근 점수 기록이 없어요.'
        items = list(fl['사람별_점수합'].items())
        out = [f"{fl['기간']} 가장 많이 오른 사람: {_b(items[0][0])} +{items[0][1]}점"]
        for n, v in items[1:4]:
            out.append(f"- {n} {v:+d}점")
        return '\n'.join(out)
    return None


# ── ③ 프롬프트 ─────────────────────────────────────────

CHAT_PROMPT = """너는 '엔젤컴퍼니' 라이브 방송 조종실의 AI 도우미다. 방송 중인 운영자가 짧게 묻고, 너는 짧고 정확하게 답한다.

[사실표 읽는 법]
- 아래 [사실표]의 숫자는 서버가 이미 계산했다. 그대로 옮겨 쓴다. 다시 더하거나 빼지 않는다.
- 점수 1점 = 후원 1만 원이다. 3만 원 후원은 3점이다.
- 순위는 기여도 순이다. 점수와 기여도는 다르다. 물은 쪽을 답하고, 애매하면 둘 다 쓴다.
- 방송 목표는 점수 단위다(1,000점 = 1,000만 원). 오늘 후원 합계(원)와 섞지 않는다.
- 사실표에 없는 것은 지어내지 않는다. "여기선 안 보여요" 라고 하고 어디서 보면 되는지 한 줄로 알려 준다.

[답하는 법]
- 한국어 존댓말(~요)로만 쓴다. 영어·일본어·한자 문장을 섞지 않는다(이름은 그대로 쓴다).
- 사실표의 항목 이름(밑줄 붙은 말)이나 영어 낱말은 답에 옮기지 않는다. 돈은 사실표에 적힌 대로 '3만 원' 처럼 쓴다.
- 첫 줄에 바로 답한다. 그다음 필요한 숫자만 1~3줄. 전체 5줄을 넘기지 않는다.
- 목록은 "- " 로 시작한다. 강조는 **이름**이나 **숫자**에만 쓴다. 제목(#)·표는 쓰지 않는다.
- 묻지 않은 조언은 하지 않는다. "뭐부터", "어떻게" 를 물을 때만 할 일을 짧게 순서대로 쓴다.
- 후원은 후원자가 말한 사람에게 간다. 누구에게 점수를 몰아주라거나 승부를 바꾸라는 말은 절대 하지 않는다.
- 너는 버튼을 누를 수 없다. 조작이 필요하면 조종실 어디서 누르는지만 알려 준다.

[예시 — 이름과 숫자는 예시일 뿐이다]
질문: 1등 누구야?
답: 1등은 **가온** — 기여도 512 (점수 160)
- 2등 나래 498, 기여도 14 차이

질문: 대기함 뭐 있어?
답: 대기함 **2건 · 6점**(6만 원)
- 다온 5만 원 "나래 화이팅" · 4분째 → 나래
- 별이 1만 원 (메시지 없음) → 누구 것인지 모름

질문: 뭐부터 하면 돼?
답: 1) 대기함 2건부터 — 다온 5만 원이 4분째 기다려요
2) 대결 0:40 남음 — 끝나면 결과 발표
"""

CHAT_MAX_TOKENS = 400


def chat_system_prompt(facts, question=None):
    """사실표를 붙인 시스템 프롬프트. 질문 종류를 알아보면 서버가 계산한 답도 같이 준다.

       ⚠️ 사실표만 주면 여러 줄을 가로질러 보는 질문을 가끔 틀린다(실측: '시그 제일 많이 쏜 사람' 에
          횟수 1등 지수크루 대신 금액 1등 재성을 '7번' 이라 했다). 계산한 답을 쥐여 주면 말만 다듬는다.
    """
    s = CHAT_PROMPT + "\n[사실표]\n" + json.dumps(facts_for_ai(facts), ensure_ascii=False, separators=(',', ':'))
    qa = quick_answer(detect_intent(question), facts) if question else None
    if qa:
        s += ("\n\n[이 질문에 맞는 계산 결과 — 숫자와 이름은 이것을 그대로 쓴다. 질문에 필요한 줄만 골라 말을 다듬는다]\n"
              + qa)
    return s


_FOREIGN = re.compile(r'[぀-ヿㇰ-ㇿ一-鿿]+')   # 가나 · 한자


def clean_reply(text):
    """모델이 가끔 일본어를 섞는다('残り', 'これにより'). 가나 · 한자는 조종실 답에 쓸 일이 없으니 걷어낸다."""
    t = _FOREIGN.sub('', str(text or ''))
    t = re.sub(r'[ \t]{2,}', ' ', t)
    t = re.sub(r'^#{1,6}\s*', '', t, flags=re.M)     # 제목(#) 은 조종실에서 글자로 보인다
    return re.sub(r'\n{3,}', '\n\n', t).strip()


def assign_system_prompt(names, hints=None, history=None, context=None):
    """배정 판단 프롬프트. hints = nickname_hints() 결과, history = [(선수, 횟수)], context = [말]."""
    extra = ''
    if hints:
        extra += '\n글자 힌트: ' + ' / '.join(hints.values())
    if history:
        extra += '\n이 후원자의 과거 배정(참고만): ' + ', '.join(f'{p} {c}번' for p, c in history[:4])
    if context:
        extra += '\n지금 방송 상황: ' + ' / '.join(context)
    return (
        "너는 라이브 후원 방송에서 '이 후원이 어느 선수를 응원하는가' 를 가리는 도우미다.\n"
        "선수: " + ', '.join(names) + extra + "\n\n"
        "[규칙]\n"
        "- 메시지가 선수 한 명을 부르면 그 선수다. 별명도 부른 것이다:\n"
        "  · 이름 일부나 줄임: '가온누리'→'가온','누리','가리'\n"
        "  · 초성: 'ㄱㅇㄴㄹ'→'가온누리'\n"
        "  · 영어·로마자·뜻 번역: 'nare'→'나래', '스타'→'별이'\n"
        "  · 애칭 꼬리('-이','-쨩','-찡','언니','오빠','님')를 떼고 보고, 한 글자 틀린 오타도 같은 사람이다.\n"
        "- 두 명 이상을 부르면 null(사람이 나눠야 한다).\n"
        "- 선수를 부르지 않는 인사·감탄·방송 칭찬·'1등 가자' 는 null.\n"
        "- 목록에 없는 이름이면 null. 답은 반드시 목록의 이름을 그대로 쓴다.\n"
        "- 과거 배정은 참고만 한다. 메시지가 다른 사람을 부르면 메시지를 따른다.\n\n"
        "[confidence] 이름·뚜렷한 별명 0.9 이상 / 짐작 0.6~0.8 / 모르겠으면 target 을 null.\n"
        'JSON 한 줄만 출력: {"target": "선수 이름" 또는 null, "confidence": 0.0~1.0}'
    )


def assign_user_prompt(donor, amount, message):
    return f"후원자: {donor} / 금액: {_int(amount):,}원 / 메시지: {message}"
