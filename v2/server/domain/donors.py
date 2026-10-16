# -*- coding: utf-8 -*-
"""👑 특별 후원자 등급 · 🚫 순위에서 빼기.

등급(옛 features/vip.py 그대로): 이번 방송 후원 순위로 매긴다. 동점은 같은 순위, 다음은 건너뛴다(1 · 1 · 3).
  VVIP 1위 · VIP 2~3위 · DIAMOND 4~6위 · BRONZE 7~10위 — 색 · 배지도 옛 것 그대로.
  → tallies.vip {정규화 이름: {name, rank, total, grade, color, badge}} (공개 — 방송판 팝업이 '다이아 6위' 를 그린다)
순위에서 빼기(옛 features/excluded.py): 뺀 이름은 후원 순위 · 한 방 최고 · 소액 띠에서 빠진다.
  다시 넣으면 장부(donations 표)에서 다시 센다.
  donor_rules (비공개) excluded[정규화 이름] · names{정규화 이름: 뺄 때 보이던 이름} · manual{정규화 이름: {name, grade, color, badge}}
직접 준 등급(옛 vip_donators): 순위(1~10위)에 **못 든 사람에게만** 붙는다 — tallies.vip 에 rank 0 · manual True 로 들어간다.
  명령 vip.set {name, grade, color?, badge?} · vip.remove {name}. 방송을 넘어 남는다(방송 시작 · 끝에 안 지운다).
⏸️ VIP 등급 끔(대표님 2026-10-13 "다시 말할 때까지 없애자, 너무 헷갈린다" — 옛 features/vip.py VIP_ON=False 와 같은 한 줄):
  투네이션 공식 칭호 '다이아' 알약과 우리 DIAMOND 등급('다이아 5위')이 한 팝업에 같이 뜰 수 있었다.
  끄면 tallies.vip 가 늘 비고(방송판 등급 옷 · 1위 훈장 · 'OO 6위' 딱지 · 조종실 등급 · AI 사실표 VIP 모두 없음)
  tallies.vip_on = False 로 화면들이 '꺼짐' 을 안다. 새 등급 주기(vip.set)는 409 로 이유를 말하고 막는다.
  순위 · 순위에서 빼기 · 직접 준 등급 기록(donor_rules.manual)은 그대로 — 다시 켜려면 아래 VIP_ON 한 줄을 True 로.
  🧪 검사 서버만 켠다(LM2_VIP_ON=1). 검사(test_donors 등)는 donors.VIP_ON 을 잠깐 True 로 바꿔 등급 계산을 계속 본다.
🏆 한 방 최고 다시 고르기(빼기 · 다시 넣기)는 at 0 — 방송판은 at 이 바뀌면 '최고 기록 갱신!' 을 터뜨리는데,
  이건 갱신이 아니라 사람을 빼거나 넣은 것이라 연출이 나가면 거짓말이 된다(옛 features/excluded.py _best_from_rows 와 같다).
  다시 넣기는 그 사람의 한 방이 지금 기록보다 **클 때만** 기록을 돌려준다(옛 _tally_restore_from_ledger).
"""
import os
import re

from .. import bus as busmod
from ..bus import CommandError, command
from ..state import slice_
from . import donation as dn
from . import session as ses
from .rules import norm_donor

VIP_TIERS = [('VVIP', 1, 1, '#f6c453', '🏆'), ('VIP', 2, 3, '#c8d4e3', '👑'),
             ('DIAMOND', 4, 6, '#5ac8fa', '💎'), ('BRONZE', 7, 10, '#c97f3d', '🥉')]
GRADE_STYLE = {g: (c, bd) for g, _, _, c, bd in VIP_TIERS}
GRADE_STYLE['GOLD'] = ('#ffd700', '⭐')      # 옛 이름 — 직접 준 등급에 남아 있을 수 있다

# ⏸️ VIP 등급 — 꺼 둠(대표님 10-13). 다시 켜려면 이 한 줄을 True 로.
VIP_ON = False
if os.environ.get('LM2_VIP_ON') == '1':          # 🧪 검사 서버만
    VIP_ON = True


def vip_on():
    return bool(VIP_ON)

slice_('donor_rules', False, lambda: {'excluded': []})


def tier(rank):
    for g, lo, hi, c, bd in VIP_TIERS:
        if lo <= rank <= hi:
            return g, c, bd
    return None


def recompute_vip(ctx):
    if not vip_on():
        _vip_off(ctx)
        return
    t = ctx.edit('tallies')
    t['vip_on'] = True
    rows = [(k, v.get('name') or k, int(v.get('total') or 0)) for k, v in (t.get('donors') or {}).items()
            if int(v.get('total') or 0) > 0]
    rows.sort(key=lambda r: (-r[2], r[1]))
    out, rank, prev = {}, 0, None
    for i, (k, shown, total) in enumerate(rows):
        if total != prev:
            rank, prev = i + 1, total
        tr = tier(rank)
        if not tr:
            break
        out[k] = {'name': shown, 'rank': rank, 'total': total, 'grade': tr[0], 'color': tr[1], 'badge': tr[2]}
    # 직접 준 등급 — 순위에 못 든 사람에게만(옛 규칙). 순위에서 뺀 이름에는 안 붙인다.
    rules = ctx.read('donor_rules')
    ex = set(rules.get('excluded') or [])
    for k, m in (rules.get('manual') or {}).items():
        if k in out or k in ex:
            continue
        d = (t.get('donors') or {}).get(k) or {}
        out[k] = {'name': d.get('name') or m.get('name') or k, 'rank': 0, 'total': int(d.get('total') or 0),
                  'grade': m.get('grade'), 'color': m.get('color'), 'badge': m.get('badge'), 'manual': True}
    t['vip'] = out


def _vip_off(ctx):
    """⏸️ 꺼져 있으면 등급을 비운다 — 바뀔 때만 고친다(안 바뀐 조각은 쪽지에 안 실린다)."""
    t = ctx.read('tallies')
    if t.get('vip') or t.get('vip_on') is not False:
        e = ctx.edit('tallies')
        e['vip'] = {}
        e['vip_on'] = False


def _vip_guard(ctx):
    """모든 명령 뒤(bus.AFTER) — 꺼져 있는데 등급이 남아 있으면(옛 DB · 방송 시작 · 끝에 집계를 새로 만든 뒤) 비운다."""
    if not vip_on():
        _vip_off(ctx)


busmod.AFTER.append(_vip_guard)


def _after_donation(ctx, name, amount):
    key = norm_donor(name)
    if key in ctx.read('donor_rules')['excluded']:
        t = ctx.edit('tallies')
        t['donors'].pop(key, None)
        if t.get('best') and norm_donor(t['best'].get('name')) == key:
            t['best'] = _best_from_ledger(ctx)
        t['notice_donors'] = [d for d in t['notice_donors'] if norm_donor(d.get('name')) != key]
    recompute_vip(ctx)


dn.AFTER_DONATION.append(_after_donation)


def _best_from_ledger(ctx):
    """장부로 '한 방 최고' 를 다시 고른다(같은 금액이면 먼저 보낸 분). ⚠️ at 은 0 — 갱신이 아니다(맨 위 설명)."""
    ex = set(ctx.read('donor_rules')['excluded'])
    best = None
    for d in ctx.store.donations(session=ses.session_id(ctx), limit=5000):
        if d['status'] in ('pending', 'assigned', 'ignored') and d['amount'] > 0 and norm_donor(d['name']) not in ex:
            if best is None or d['amount'] > best['amount'] or (d['amount'] == best['amount'] and d['at'] < best['_at']):
                best = {'name': d['name'], 'amount': d['amount'], 'at': 0, 'id': d['id'],
                        'member': d['player'] or '', '_at': d['at']}
    if best:
        best.pop('_at')
    return best


@command('donor.exclude')
def donor_exclude(ctx, data):
    key = norm_donor(data.get('name'))
    r = ctx.edit('donor_rules')
    if key in r['excluded']:
        raise CommandError('이미 뺀 이름입니다', 409)
    r['excluded'].append(key)
    t = ctx.edit('tallies')
    # 화면에 보이던 이름을 같이 적어 둔다(키는 '님' 을 뗀 정규화 이름이라 다를 수 있다)
    r.setdefault('names', {})[key] = (t['donors'].get(key) or {}).get('name') or ' '.join(str(data.get('name') or '').split()) or key
    t['donors'].pop(key, None)
    if t.get('best') and norm_donor(t['best'].get('name')) == key:
        t['best'] = _best_from_ledger(ctx)
    t['notice_donors'] = [d for d in t['notice_donors'] if norm_donor(d.get('name')) != key]
    recompute_vip(ctx)


@command('donor.include')
def donor_include(ctx, data):
    """다시 넣기 — 이번 방송 장부에서 다시 센다."""
    key = norm_donor(data.get('name'))
    r = ctx.edit('donor_rules')
    if key not in r['excluded']:
        raise CommandError('뺀 이름이 아닙니다', 404)
    r['excluded'].remove(key)
    (r.get('names') or {}).pop(key, None)
    t = ctx.edit('tallies')
    total = count = 0
    shown = data.get('name')
    for d in ctx.store.donations(session=ses.session_id(ctx), limit=5000):
        if norm_donor(d['name']) == key and d['status'] in ('pending', 'assigned', 'ignored'):
            total += max(0, d['amount'])
            count += 1
            shown = d['name']
    if count:
        t['donors'][key] = {'name': shown, 'total': total, 'count': count}
    # 💥 되돌린 사람의 한 방이 지금 기록보다 **크면** 기록도 돌려준다(옛 것과 같다 — 같거나 작으면 지금 기록 그대로)
    cand = _best_from_ledger(ctx)
    if cand and norm_donor(cand['name']) == key and cand['amount'] > int((t.get('best') or {}).get('amount') or 0):
        t['best'] = cand
    recompute_vip(ctx)


@command('vip.set')
def vip_set(ctx, data):
    """직접 등급 주기 — {name, grade(VVIP · VIP · DIAMOND · BRONZE), color?, badge?}. 색 · 배지를 안 주면 등급 것."""
    name = ' '.join(str(data.get('name') or '').split())[:30]
    key = norm_donor(name)
    if not vip_on():
        # 꺼져 있는 동안 받으면 저장만 되고 어디에도 안 보여서 '등록이 안 된다' 로 읽힌다 — 이유를 말하고 막는다(옛 것과 같다)
        raise CommandError('VIP 등급은 지금 꺼져 있어요(10-13). 다시 켜려면 말씀해 주세요.', 409)
    if not name or key == '익명':
        raise CommandError('후원자 이름을 적어 주세요')
    grade = str(data.get('grade') or '').strip().upper()
    if grade not in GRADE_STYLE:
        raise CommandError('등급을 골라 주세요 (VVIP · VIP · DIAMOND · BRONZE)')
    color = str(data.get('color') or '').strip()
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        color = GRADE_STYLE[grade][0]
    badge = str(data.get('badge') or '').strip()[:4] or GRADE_STYLE[grade][1]
    r = ctx.edit('donor_rules')
    r.setdefault('manual', {})[key] = {'name': name, 'grade': grade, 'color': color, 'badge': badge}
    recompute_vip(ctx)


@command('vip.remove')
def vip_remove(ctx, data):
    key = norm_donor(data.get('name'))
    r = ctx.edit('donor_rules')
    if key not in (r.get('manual') or {}):
        raise CommandError('직접 준 등급이 없는 이름입니다', 404)
    r['manual'].pop(key)
    recompute_vip(ctx)


def _vip_on_start(ctx, data):
    """방송을 시작하면(집계가 비워진 뒤) 직접 준 등급부터 다시 붙인다 — 첫 후원 전에도 방송판이 등급을 안다."""
    recompute_vip(ctx)


ses.ON_START.append(_vip_on_start)       # ⚠️ donation 모듈(집계 비우기)보다 뒤에 불려야 한다 — domain/__init__ 순서가 그렇다
