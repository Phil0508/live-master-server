# -*- coding: utf-8 -*-
"""🛡️ 큰 금액은 한 번 더 확인(10-17 bigok) — 기준만 서버에 둔다. 묻는 것은 조종실 화면(js/bigok.js).

조종실에서 사람이 점수를 줄 때(대기함 선수 단추 · 추천 단추 · 나눠 주기 · 폰 서랍 · AI '말로 조종' [실행]/[모두 실행] ·
점수판 손 점수 · Ctrl+K '밍밍 5'), 후원 금액이 won 이상이거나 손으로 넣는 점수가 pts 이상이면
화면 안 확인 상자('영원 500,000원 → 밍밍에게 50점 줄까요? [주기] [취소]')를 띄운다.
기준을 조각에 두는 까닭: PC · 폰이 같은 값을 쓴다(브라우저마다 기억하면 폰만 꺼져 있을 수 있다).

조각 bigok(비공개 — 방송판엔 안 간다) {won: 200000, pts: 20}   0 이면 그 확인은 끔.
명령 bigok.set {won?, pts?}
⚠️ 자동 진행(서버 autopilot · 조종실 오토파일럿 via 'ap')은 여기와 상관없다 — 그쪽은 상한(assign_max) 이상을 이미 보류한다.
"""
from ..bus import CommandError, command
from ..state import slice_

WON_DEFAULT, PTS_DEFAULT = 200000, 20
WON_MAX, PTS_MAX = 100000000, 100000

slice_('bigok', False, lambda: {'won': WON_DEFAULT, 'pts': PTS_DEFAULT})


def _int(v, top, what):
    if isinstance(v, bool):
        raise CommandError(what + ' 는 숫자로 적어 주세요')
    if isinstance(v, str):
        v = v.replace(',', '').replace('원', '').replace('점', '').strip()
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        raise CommandError(what + ' 는 숫자로 적어 주세요')
    if n < 0 or n > top:
        raise CommandError('%s 는 0 ~ %s 사이로 적어 주세요 (0 = 묻지 않음)' % (what, format(top, ',')))
    return n


@command('bigok.set')
def bigok_set(ctx, data):
    """{won?, pts?} — 큰 금액 확인 기준. 둘 중 하나만 와도 된다."""
    if 'won' not in data and 'pts' not in data:
        raise CommandError('바꿀 기준(won · pts)이 없어요')
    b = ctx.edit('bigok')
    if 'won' in data:
        b['won'] = _int(data['won'], WON_MAX, '후원 금액 기준')
    if 'pts' in data:
        b['pts'] = _int(data['pts'], PTS_MAX, '손 점수 기준')
    ctx.notes['bigok'] = {'won': b['won'], 'pts': b['pts']}
