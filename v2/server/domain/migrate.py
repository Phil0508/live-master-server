# -*- coding: utf-8 -*-
"""📦 옛 프로그램 설정 옮겨 오기 — 옛 조종실 [💾 백업] 파일(상태 JSON)을 v2 조각으로.

명령 admin.import_old {state: {…옛 상태…}} — 한 번에(하나라도 이상하면 아무것도 안 바뀐다).
**설정만** 옮긴다(공지 · 계좌 · 목표 · 테마 · 퇴근빵 목표 · 내 퀴즈 문제 · 고액 영상 · 모금함 · 룰렛 항목 ·
슬롯 값/후보 · 주사위 판 · 후원 순위 보이기 · 고정 자리/알림 스위치 · 운영비 이름).
점수 · 대기함 · 시그니처 대기줄 같은 '방송 한 회' 것은 옮기지 않는다 — 갈아타기는 방송과 방송 사이에 한다.
"""
from ..bus import CommandError, command

_STR = lambda v, n: ' '.join(str(v or '').split())[:n]


def _int(v, lo, hi, dflt):
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return dflt


@command('admin.import_old')
def import_old(ctx, data):
    old = data.get('state')
    if not isinstance(old, dict) or not old:
        raise CommandError('옛 상태(JSON 객체)가 필요합니다')
    done, skipped = [], []

    def did(name):
        done.append(name)

    if isinstance(old.get('account'), dict):
        a = ctx.edit('account')
        for k in ('bank', 'acc_num', 'name'):
            a[k] = _STR(old['account'].get(k), 40)
        did('계좌')
    if 'target_goal' in old:
        ctx.edit('goal')['target'] = _int(old.get('target_goal'), 0, 10 ** 7, 0)
        did('목표')
    if old.get('theme'):
        t = str(old.get('theme'))
        ctx.edit('look')['theme'] = 'rose' if t == 'pink' else t[:30]
        did('테마')
    look = ctx.edit('look')
    if 'donor_rank_anon' in old:
        look['donor_anon'] = bool(old.get('donor_rank_anon'))
    if 'donor_rank_amount' in old:
        look['donor_amount'] = old.get('donor_rank_amount') is not False
    msgs = old.get('notice_msgs')
    if isinstance(msgs, list):
        n = ctx.edit('notice')
        n['msgs'] = [_STR(m, 120) for m in msgs if _STR(m, 120)][:30]
        n['period'] = _int(old.get('notice_period'), 20, 3600, n['period'])
        n['speed'] = _int(old.get('notice_speed'), 40, 400, n['speed'])
        did('공지 %d줄' % len(n['msgs']))
    if isinstance(old.get('home_goals'), dict):
        ctx.edit('home')['goals'] = {_STR(k, 20): _int(v, 0, 100000, 0) for k, v in old['home_goals'].items()
                                     if _STR(k, 20) and _int(v, 0, 100000, 0) > 0}
        did('퇴근빵 목표')
    q = old.get('quiz')
    if isinstance(q, dict) and isinstance(q.get('custom'), dict):
        ops = ctx.edit('quiz_ops')
        for k in ('chosung', 'idiom'):
            rows = q['custom'].get(k)
            if isinstance(rows, list):
                ops['custom'][k] = [[str(x[0])[:10], str(x[1] or '')[:60]] for x in rows
                                    if isinstance(x, (list, tuple)) and len(x) == 2 and str(x[0]).strip()][:500]
        did('내 퀴즈 문제')
    tiers = old.get('account_video_tiers')
    if isinstance(tiers, list) and tiers:
        av = ctx.edit('acct_video')
        av['tiers'] = [{'min': _int(t.get('min'), 0, 10 ** 9, 0), 'label': _STR(t.get('label'), 20) or '?',
                        'video': str(t.get('video') or '')[:500]} for t in tiers if isinstance(t, dict)][:20]
        did('고액 영상 %d칸' % len(av['tiers']))
    fj = old.get('fundjar')
    if isinstance(fj, dict):
        j = ctx.edit('fundjar')
        j['name'] = _STR(fj.get('name'), 20) or j['name']
        j['enabled'] = bool(fj.get('enabled'))
        j['seed'] = _int(fj.get('seed'), 0, 10 ** 9, j['seed'])
        did('모금함')
    bf = old.get('bottom_fixed')
    if isinstance(bf, dict) and _STR(bf.get('name'), 20):
        ctx.edit('players')['bottom']['name'] = _STR(bf.get('name'), 20)
        did('운영비 이름')
    r = old.get('roulette')
    if isinstance(r, dict):
        rr = ctx.edit('roulette')
        if isinstance(r.get('custom_items'), list):
            rr['custom'] = [_STR(x, 30) for x in r['custom_items'] if _STR(x, 30)][:30]
        if r.get('item_source') in ('bj', 'custom'):
            rr['source'] = r['item_source']
        if r.get('weight_type') in ('equal', 'contrib'):
            rr['weight'] = r['weight_type']
        did('룰렛 항목')
    if 'slot_price' in old or 'slot_pool' in old:
        so = ctx.edit('slot_ops')
        so['price'] = _int(old.get('slot_price'), 0, 10 ** 8, so['price'])
        if isinstance(old.get('slot_pool'), list):
            so['pool'] = [str(x) for x in old['slot_pool']][:200]
        did('슬롯 값 · 후보')
    dg = old.get('dicegame')
    if isinstance(dg, dict):
        g = ctx.edit('dicegame')
        for k, lo, hi in (('cols', 3, 12), ('rows', 3, 12), ('dice', 1, 2), ('roll_price', 0, 10 ** 8), ('lap_contrib', 0, 1000)):
            if k in dg:
                g[k] = _int(dg.get(k), lo, hi, g[k])
        if isinstance(dg.get('tiles'), list) and dg['tiles']:
            g['tiles'] = dg['tiles']
        if isinstance(dg.get('keys'), list):
            ctx.edit('dicegame_private')['keys'] = dg['keys']
        did('주사위 판')
    sh = old.get('show')
    if isinstance(sh, dict):
        s = ctx.edit('show')
        for part in ('hud', 'alerts'):
            if isinstance(sh.get(part), dict):
                for k, v in sh[part].items():
                    if k in s[part]:
                        s[part][k] = bool(v)
        did('고정 자리 · 알림 스위치')
    from . import announce as _an
    if _an.import_old(ctx, old):
        did('진행봇')
    # 💡 조명 속도(neon_speed) · 색 슬롯(saved_colors) · ✨ 테마 연출(theme_fx_enabled) — 옛 BROADCAST_KEEP_KEYS 의 설정 칸
    from . import lights as _li
    for name in _li.import_old(ctx, old):
        did(name)
    # 🎚️ 시그니처 보이는 모습(reaction_*) · 목록 개수 · 효과음 · 노래방 음량 · 세이브 슬롯(자리 빼고) — settings2.py
    from . import settings2 as _s2
    for name in _s2.import_old(ctx, old):
        did(name)
    if not done:
        raise CommandError('옮길 것을 찾지 못했습니다 — 옛 조종실 [💾 백업] 파일이 맞나요?')
    ctx.notes['imported'] = done
