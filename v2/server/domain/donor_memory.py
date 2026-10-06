# -*- coding: utf-8 -*-
"""🧠 후원자 기억 · 별명 기억 · '이 후원은 누구 것인가' 판단(규칙 단계) — 옛 features/donor_memory.py + ai.py suggest_target.

표(이 모듈이 만든다 — store.py 는 안 건드린다. 처음 쓸 때 CREATE TABLE IF NOT EXISTS)
  donor_memory  후원 한 건이 누구에게 갔나 (at · donor(정규화) · player · amount(준 점수 — 옛 것과 같다) · message · ref(후원 id))
  alias_memory  메시지 속 낱말이 어느 선수로 이어졌나 (token · player · hits · updated) — (token, player) 하나에 한 줄
  ⚠️ 방송이 끝나도 지우지 않는다. 방송을 거듭할수록 정확해지는 것이 요점이다(옛 것과 같다).
  ⚠️ 옛 표 이름 그대로다 — 옛 DB 를 옮겨 올 때(migrate) 같은 이름으로 넣으면 된다(옛 timestamp TEXT → at 초).

언제 기억하나(고리)
  players.AFTER_SCORE — apply_scores 가 끝난 뒤. ctx.notes['ref'] 가 'don_' 으로 시작하면(= pending.assign 이 후원 id 로 준 것)
  장부(ctx.store.donation(ref))에서 후원자 · 메시지를, score_log(ref)에서 **점수(+)를 받은 선수**를 읽어 기억한다.
  - 옛 것과 같다: 점수가 0 보다 큰 줄만(기여도 카드 · 운영비 · 손 점수 'act_' 는 안 배운다) · 익명은 안 배운다.
  - 같은 명령 안(장부 한 번)에서 적는다 — 배정이 실패해 되감기면 기억도 같이 되감긴다. 기억 쓰기가 실패하면
    SAVEPOINT 로 그 부분만 되돌리고 **배정은 그대로 둔다**(기억 때문에 점수가 안 들어가면 안 된다).
  - 새로: 테스트 후원(리스너 toon_t2_)은 안 배운다.
  players.ON_UNDO — 새로: 후원 배정을 되돌리면 그 배정에서 배운 것도 잊는다(옛 것은 잘못 준 것을 그대로 배웠다.
  v2 는 되돌리면 후원이 대기함으로 돌아오고, 다시 줄 때 다시 배운다).

판단 단계(옛 features/ai.py suggest_target 그대로 — 숫자 · 문턱을 안 바꿨다)
  ① 메시지에 이름이 낱말로 딱 — 한 명 0.97 auto · 여럿이면 모름
  ② 별명 기억 — 두 번 이상 · 한 사람에게만 이어진 말: min(0.95, 0.62 + 0.09×적중)
  ③ 후원자 이력 — 늘 같은 사람(2번 이상): min(0.93, 0.66 + 0.07×횟수) · 3배 이상 쏠림: 0.7
  ③-b 글자만 겹치는 이름 하나: 0.75 추천 · 여럿이면 모름
  ③-c 이름 일부 · 초성 · 줄임(nickname_hints) — AI 에게 힌트로. AI 가 꺼졌거나 붐비면 하나뿐일 때 0.72 추천
  ④ AI(ai.py 가 명령 밖에서 부른다) — 최대 0.88(AI 는 이력 · 별명만큼 믿지 않는다)
  단계(tier): 0.90 이상 auto(오토파일럿이 스스로 배정) · 0.60 이상 suggest(사람이 누른다) · 그 아래 unknown
  ⚠️ 이력 · 별명 · AI 로 auto 가 나와도 메시지에 **다른** 선수 이름 글자가 붙어 있으면 suggest(최대 0.85)로 낮춘다.
"""
import re
import time

from . import players as pl
from .ai_facts import NIM_RETRYABLE, names_in_message, nickname_hints
from .rules import norm_donor

CONF_AUTO = 0.90      # 이 위는 오토파일럿이 스스로 배정한다
CONF_SUGGEST = 0.60   # 이 위는 추천만 한다(사람이 누른다)

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS donor_memory ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, donor TEXT NOT NULL, player TEXT NOT NULL,"
    " amount INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '', ref TEXT NOT NULL DEFAULT '')",
    "CREATE INDEX IF NOT EXISTS donor_memory_donor ON donor_memory(donor)",
    "CREATE INDEX IF NOT EXISTS donor_memory_ref ON donor_memory(ref)",
    "CREATE TABLE IF NOT EXISTS alias_memory ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL, player TEXT NOT NULL,"
    " hits INTEGER NOT NULL DEFAULT 1, updated REAL NOT NULL DEFAULT 0, UNIQUE(token, player))",
)


def ensure(store):
    """표가 없으면 만든다. ⚠️ executescript 는 열린 장부(BEGIN)를 몰래 COMMIT 하므로 쓰지 않는다 — 한 줄씩.
       명령 안(장부가 열려 있을 때)에서 만들면 그 명령이 되감길 때 표도 사라지므로 '만들었다' 고 기억하지 않는다."""
    if getattr(store, '_lm_donor_memory', False):
        return
    for q in _SCHEMA:
        store.db.execute(q)
    if not store.db.in_transaction:
        store._lm_donor_memory = True


# ── 별명 후보 ───────────────────────────────────────────
# ⚠️ 너무 많이 뽑으면 아무 말이나 별명이 되어 오답을 만든다. 짧고 흔한 말은 버린다(옛 목록 그대로).
_ALIAS_STOP = {'화이팅', '파이팅', '감사', '감사합니다', '고생', '고생하셨어요', '수고',
               '수고하셨습니다', '응원', '응원합니다', '축하', '사랑해요', '가즈아', '대박',
               '오늘', '방송', '재밌어요', '잘보고있어요', '님', '언니', '누나', '형', '오빠'}


def alias_tokens(message):
    """메시지에서 별명 후보를 뽑는다(최대 6개)."""
    out = []
    for w in re.split(r'[\s,./!?~\-()\[\]"\'·:;]+', str(message or '')):
        w = w.strip().strip('님아야이가는은를을에게한테')
        if not (2 <= len(w) <= 8):
            continue
        if w in _ALIAS_STOP:
            continue
        if w.isdigit():          # 순수 숫자는 금액·시각일 때가 많다
            continue
        out.append(w)
    return out[:6]


# ── 기억하기 · 잊기 · 찾기 ───────────────────────────────
def remember_assignment(store, donor, player, amount, message, ref='', at=None):
    """후원 한 건이 누구에게 갔는지 기억한다. 익명 · 빈 이름은 안 적는다(사람을 특정할 수 없다). 적었으면 True."""
    d = norm_donor(donor)
    p = str(player or '').strip()
    if not p or d == '익명':
        return False
    ensure(store)
    now = time.time() if at is None else float(at)
    msg = str(message or '')[:300]
    store.db.execute('INSERT INTO donor_memory(at, donor, player, amount, message, ref) VALUES(?, ?, ?, ?, ?, ?)',
                     (now, d, p, int(amount or 0), msg, str(ref or '')))
    for tok in alias_tokens(msg):
        store.db.execute('INSERT INTO alias_memory(token, player, hits, updated) VALUES(?, ?, 1, ?) '
                         'ON CONFLICT(token, player) DO UPDATE SET hits = hits + 1, updated = excluded.updated',
                         (tok, p, now))
    return True


def forget_assignment(store, ref):
    """그 후원(ref)으로 배운 것을 잊는다 — 이력 줄을 지우고 별명 적중을 하나씩 뺀다(0 이 되면 지운다)."""
    if not ref:
        return 0
    ensure(store)
    rows = store.db.execute('SELECT player, message FROM donor_memory WHERE ref = ?', (str(ref),)).fetchall()
    for r in rows:
        for tok in alias_tokens(r['message']):
            store.db.execute('UPDATE alias_memory SET hits = hits - 1 WHERE token = ? AND player = ?', (tok, r['player']))
    if rows:
        store.db.execute('DELETE FROM alias_memory WHERE hits <= 0')
        store.db.execute('DELETE FROM donor_memory WHERE ref = ?', (str(ref),))
    return len(rows)


def donor_history(store, donor, limit=5):
    """이 후원자가 누구에게 갔는지. [(선수, 횟수)] 많은 순(같으면 최근 순)."""
    d = norm_donor(donor)
    if d == '익명':
        return []
    try:
        ensure(store)
        cur = store.db.execute('SELECT player, COUNT(*) AS c, MAX(at) AS last FROM donor_memory WHERE donor = ? '
                               'GROUP BY player ORDER BY c DESC, last DESC LIMIT ?', (d, int(limit)))
        return [(r['player'], int(r['c'])) for r in cur.fetchall()]
    except Exception:
        return []


def alias_lookup(store, message, players):
    """메시지 안의 말이 특정 선수로만 이어져 왔는지. 돌려받는 값: (선수, 적중 수, 그 말) 또는 None."""
    toks = alias_tokens(message)
    if not toks:
        return None
    names = {str(p).strip() for p in (players or []) if str(p or '').strip()}
    try:
        ensure(store)
        ph = ', '.join(['?'] * len(toks))
        rows = [r for r in store.db.execute('SELECT token, player, hits FROM alias_memory WHERE token IN (%s)' % ph,
                                            tuple(toks)).fetchall() if r['player'] in names]
    except Exception:
        return None
    by_tok = {}
    for r in rows:
        by_tok.setdefault(r['token'], []).append((r['player'], int(r['hits'])))
    best = None
    for tok, lst in by_tok.items():
        if len(lst) != 1:
            continue          # 그 말이 두 사람 이상을 가리킨 적이 있다 → 믿을 수 없다
        player, hits = lst[0]
        if not best or hits > best[1]:
            best = (player, hits, tok)
    return best


# ── 고리: 배정 뒤 기억 · 되돌리면 잊기 ────────────────────
def _after_score(ctx):
    ref = str(ctx.notes.get('ref') or '')
    if not ref.startswith('don_'):
        return
    db = ctx.store.db
    try:
        d = ctx.store.donation(ref)
        if not d or d.get('source') == 'toonation_test':
            return
        rows = [r for r in ctx.store.score_rows(ref)
                if r['field'] == 'score' and int(r['delta']) > 0 and r['list'] in ('list', 'main', 'extra')]
        if not rows:
            return
        db.execute('SAVEPOINT lm_donor_memory')
    except Exception:
        return
    try:
        for r in rows:
            remember_assignment(ctx.store, d['name'], r['player'], r['delta'], d.get('message') or '', ref=ref, at=ctx.now)
        db.execute('RELEASE lm_donor_memory')
    except Exception:
        try:
            db.execute('ROLLBACK TO lm_donor_memory')
            db.execute('RELEASE lm_donor_memory')
        except Exception:
            pass


def _on_undo(ctx, ref):
    if not str(ref or '').startswith('don_'):
        return
    db = ctx.store.db
    try:
        db.execute('SAVEPOINT lm_donor_forget')
    except Exception:
        return
    try:
        forget_assignment(ctx.store, ref)
        db.execute('RELEASE lm_donor_forget')
    except Exception:
        try:
            db.execute('ROLLBACK TO lm_donor_forget')
            db.execute('RELEASE lm_donor_forget')
        except Exception:
            pass


pl.AFTER_SCORE.append(_after_score)
pl.ON_UNDO.append(_on_undo)


# ── 판단(규칙 단계) ─────────────────────────────────────
def tier(conf):
    if conf >= CONF_AUTO:
        return 'auto'
    if conf >= CONF_SUGGEST:
        return 'suggest'
    return 'unknown'


def hold_if_message_points_elsewhere(res, loose):
    """메시지가 다른 이름 글자를 품고 있으면 자동 배정을 막는다.
       ⚠️ 이력 · 별명은 통계일 뿐 — 그 후원 메시지에 '철수화이팅' 처럼 다른 이름이 붙어 있으면 사람이 봐야 한다."""
    tgt = res.get('target')
    if not tgt or not loose or tgt in loose:
        return res
    if res.get('tier') != 'auto':
        return res
    other = ', '.join(sorted(loose))
    return dict(res, tier='suggest', confidence=min(res.get('confidence') or 0, 0.85),
                why=(res.get('why') or '') + f" — 다만 메시지에 '{other}' 글자가 있어 확인 필요")


def suggest_rules(store, donor, message, names):
    """①~③-c — AI 없이 풀리면 (답, 재료), 못 풀면 (None, 재료). 재료는 AI 에게 넘길 것과 마무리에 쓸 것.
       답: {target, confidence, tier, source, why, history[{name, count}]}"""
    names = [str(n).strip() for n in (names or []) if str(n or '').strip()]
    msg = str(message or '')
    hist = donor_history(store, donor)
    base = {'target': None, 'confidence': 0.0, 'tier': 'unknown', 'source': None, 'why': None,
            'history': [{'name': p, 'count': c} for p, c in hist]}
    pre = {'base': base, 'hist': hist, 'known': [], 'loose': set(), 'hints': {}, 'names': names}
    if not names:
        return base, pre

    # ① 메시지에 이름이 그대로 — 가장 확실하다(낱말이 딱 떨어질 때만)
    exact, loose = names_in_message(msg, names)
    pre['loose'] = loose
    if len(exact) == 1:
        one = next(iter(exact))
        return dict(base, target=one, confidence=0.97, tier='auto', source='이름', why=f'메시지에 \'{one}\' 이 있음'), pre
    if len(exact) > 1:      # 두 사람 이상을 부른 후원은 반반일 수 있다
        return dict(base, source='이름', why='여러 사람을 부름: ' + ', '.join(sorted(exact))), pre

    # ② 별명 기억 — 한 번만 본 말은 잡음. 두 번 이상 같은 사람으로 이어졌을 때부터 '별명'
    al = alias_lookup(store, msg, names)
    if al and al[1] >= 2:
        player, hits, tok = al
        conf = min(0.95, 0.62 + 0.09 * hits)
        return hold_if_message_points_elsewhere(
            dict(base, target=player, confidence=round(conf, 2), tier=tier(conf), source='별명',
                 why=f'\'{tok}\' 은 지금까지 {hits}번 모두 {player} 였음'), loose), pre

    # ③ 후원자 이력 — 늘 같은 사람에게 갔는가
    known = [(p, c) for p, c in hist if p in names]
    pre['known'] = known
    if known:
        top_p, top_c = known[0]
        others = sum(c for p, c in known[1:])
        if others == 0 and top_c >= 2:
            conf = min(0.93, 0.66 + 0.07 * top_c)
            return hold_if_message_points_elsewhere(
                dict(base, target=top_p, confidence=round(conf, 2), tier=tier(conf), source='이력',
                     why=f'이 후원자는 지금까지 {top_c}번 모두 {top_p} 였음'), loose), pre
        if top_c >= 3 * max(1, others):
            conf = 0.7
            return hold_if_message_points_elsewhere(
                dict(base, target=top_p, confidence=conf, tier=tier(conf), source='이력',
                     why=f'{top_c}번 {top_p} / 그 외 {others}번'), loose), pre

    # ③-b 글자만 겹치는 이름 — '추천' 으로만('밍밍화이팅' 은 살리고 '철수했다가' 로 돈이 자동으로 가지 않게)
    if len(loose) == 1:
        one = next(iter(loose))
        return dict(base, target=one, confidence=0.75, tier=tier(0.75), source='이름',
                    why=f'메시지에 \'{one}\' 글자가 있음 (낱말이 딱 떨어지진 않음)'), pre
    if len(loose) > 1:
        return dict(base, source='이름', why='여러 이름 글자가 섞임: ' + ', '.join(sorted(loose))), pre

    # ③-c 이름 일부 · 초성 · 줄임 — 이것만으로 배정하지 않는다. AI 에게 힌트로.
    pre['hints'] = nickname_hints(msg, names)
    return None, pre


def suggest_after_ai(pre, ai):
    """④ AI 답(ai.nim_suggest_target 의 모양)으로 마무리. AI 를 못 불렀으면(키 없음 · 한도 · 붐빔) 그 까닭을 사람 말로."""
    base, hints, loose, hist = pre['base'], pre['hints'], pre['loose'], pre['hist']
    ai = ai or {}
    conf = float(ai.get('confidence') or 0)
    retry = bool(ai.get('retry'))
    if not ai.get('target') and len(hints) == 1 and (ai.get('error') or ai.get('skipped')):
        # AI 가 붐비거나 꺼져 있을 때 — 글자가 겹치는 선수가 하나뿐이면 '확인 필요' 추천으로만.
        # 0.72 는 배지만 뜨고(0.6↑) '지급할까요' 창(0.75↑) · 오토파일럿(0.9↑)은 안 움직이는 자리다.
        one, why_h = next(iter(hints.items()))
        return dict(base, target=one, confidence=0.72, tier=tier(0.72), source='별명',
                    why=why_h + ' (AI 없이 글자로만 봄)', retry=retry)
    if not ai.get('target'):
        # ⚠️ 왜 모르는지를 사람 말로. 'rate' 같은 낱말이 그대로 뜨면 운영자가 그 표시를 안 믿게 된다.
        if ai.get('reason') == 'rate':
            why = 'AI 호출이 잠시 몰려 못 물어봄 (조금 뒤 다시 봄)'
        elif ai.get('skipped'):
            why = 'AI 가 꺼져 있음 — 이름·별명·이력으로는 못 찾음'
        elif ai.get('error') in NIM_RETRYABLE:
            why = 'AI 서버가 붐빕니다 — 잠시 뒤 저절로 됩니다'      # '오류' 라 하면 방송 중에 서버를 건드리러 간다
        elif ai.get('gone'):
            why = 'AI 모델이 종료됐습니다 — 서버 설정에서 모델을 바꿔주세요'
        elif ai.get('error'):
            why = 'AI 오류로 못 물어봄'
        elif hist:
            why = '메시지로도 이력으로도 특정이 안 됨'
        else:
            why = '처음 보는 후원자이고 메시지에 단서가 없음'
        return dict(base, target=None, confidence=0.0, tier='unknown', source='AI', why=why, retry=retry)
    conf = min(conf, 0.88)          # AI 는 이력 · 별명만큼 믿지 않는다 — 위 단계에서 안 걸린 건은 애매한 것이다
    why = '메시지 내용으로 추정' + (f" — {hints[ai['target']]}" if ai['target'] in hints else '')
    return hold_if_message_points_elsewhere(
        dict(base, target=ai['target'], confidence=round(conf, 2), tier=tier(conf), source='AI', why=why), loose)


def suggest_target(store, donor, message, names, ask_ai=None):
    """한 번에(검사 · 동기 경로용). ask_ai(pre) → AI 답 dict. 없으면 'AI 꺼짐' 으로 마무리한다.
       ⚠️ 서버는 이걸 쓰지 않는다 — ai.py 가 규칙 단계와 AI 호출을 나눠 AI 만 명령 밖 · 다른 갈래에서 부른다."""
    res, pre = suggest_rules(store, donor, message, names)
    if res is not None:
        return res
    ai = ask_ai(pre) if ask_ai else {'target': None, 'confidence': 0.0, 'skipped': True}
    return suggest_after_ai(pre, ai)
