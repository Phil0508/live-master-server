#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🔀 Caddy 큰 주소 갈아타기 도구 — Caddyfile 에서 방송 큰 주소(포트 없음) 덩어리 **하나만** 바꿔 끼운 새 파일을 만든다.

쓰는 법(서버에서 — 파이썬 3 만 있으면 된다, 꾸러미 필요 없음):
  python3 caddy_switch.py status <Caddyfile>
  python3 caddy_switch.py apply  <Caddyfile> <새 파일>    큰 주소 덩어리를 Caddyfile.switch 의 덩어리로 바꾼 것을 <새 파일> 에 쓴다
  python3 caddy_switch.py revert <Caddyfile> <새 파일>    Caddyfile.unswitch(옛 덩어리 그대로)로 되돌린 것을 <새 파일> 에 쓴다
⚠️ 원래 Caddyfile 은 절대 고치지 않는다(새 파일 이름이 같으면 거절). 확인(validate) · 바꿔 넣기 · reload 는 사람이 한다
   — 순서는 v2/deploy/README.md '갈아타는 날'.
지키는 것
  - 바꾸는 것은 머리가 정확히 '<큰 주소>' 인 맨 바깥 덩어리 하나. 없거나 둘 이상이면 아무것도 안 쓰고 멈춘다.
  - 다른 덩어리(:8443 v2 · angelcompany.me 홈페이지 · crew …)와 덩어리 밖 글자(주석 · 빈 줄)는 한 글자도 안 바뀐다 —
    쓰기 전에 바뀐 파일을 다시 읽어 맞대 본다.
  - 이미 갈아탄 것에 apply · 안 갈아탄 것에 revert 는 거절(두 번 해도 안전). 갈아탄 표시는 덩어리 안 '# lm2-switch' 한 줄.
  - 괄호는 Caddy 처럼 '홀로 선' { } 만 센다 — 주석(#) · 따옴표 안 · {host} 같은 자리 표시는 안 센다.
검사: v2/tests/test_ops_caddy.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = 'xn--9i1b547a0ublxlz4f.xn--h32bi4v.xn--3e0b707e'          # 엔젤컴퍼니.메인.한국 (퓨니코드)
MARK = '# lm2-switch'
SWITCH = os.path.join(HERE, 'Caddyfile.switch')
UNSWITCH = os.path.join(HERE, 'Caddyfile.unswitch')
SPACE = ' \t\r\n'


class SwitchError(Exception):
    pass


def top_blocks(text):
    """맨 바깥 덩어리들 → [{'head', 'addrs', 'start', 'open', 'end'}] (start = 머리 첫 글자, end = 닫는 } 다음)."""
    out, depth, quote = [], 0, None
    head_start, open_pos = None, None
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if quote:
            if ch == '\\' and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        alone_before = i == 0 or text[i - 1] in SPACE
        if ch == '#' and alone_before:                       # 주석 — 줄 끝까지
            j = text.find('\n', i)
            i = n if j < 0 else j
            continue
        if ch in '"`' and alone_before:
            quote = ch
            if depth == 0 and head_start is None:
                head_start = i
            i += 1
            continue
        alone = alone_before and (i + 1 >= n or text[i + 1] in SPACE)
        if ch == '{' and alone:
            if depth == 0:
                open_pos = i
                if head_start is None:
                    head_start = i                         # 머리 없는 덩어리(전역 설정)
            depth += 1
        elif ch == '}' and alone:
            depth -= 1
            if depth < 0:
                raise SwitchError('닫는 괄호가 남습니다(%d 번째 글자) — Caddyfile 이 깨져 있어요' % i)
            if depth == 0:
                head = text[head_start:open_pos].strip()
                addrs = [a for a in head.replace(',', ' ').split() if a]
                out.append({'head': head, 'addrs': addrs, 'start': head_start, 'open': open_pos, 'end': i + 1})
                head_start = None
        elif depth == 0 and head_start is None and ch not in SPACE:
            head_start = i
        i += 1
    if quote:
        raise SwitchError('따옴표가 안 닫혔습니다 — Caddyfile 이 깨져 있어요')
    if depth != 0:
        raise SwitchError('여는 괄호가 안 닫혔습니다 — Caddyfile 이 깨져 있어요')
    return out


def _target(blocks):
    hits = [b for b in blocks if b['addrs'] == [HOST]]
    if len(hits) != 1:
        raise SwitchError('큰 주소(%s) 덩어리가 %d개입니다 — 딱 하나여야 바꿉니다' % (HOST, len(hits)))
    return hits[0]


def fragment(path):
    """조각 파일에서 큰 주소 덩어리 글자만(머리 주석은 빼고) — 줄바꿈은 \\n 으로."""
    with open(path, encoding='utf-8', newline='') as f:
        text = f.read().replace('\r\n', '\n')
    b = _target(top_blocks(text))
    return text[b['start']:b['end']]


def swap(text, mode):
    """mode 'apply' | 'revert' → 새 글. 바꾸기 전후를 맞대 보고 다르면 SwitchError."""
    blocks = top_blocks(text)
    b = _target(blocks)
    marked = MARK in text[b['start']:b['end']]
    if mode == 'apply' and marked:
        raise SwitchError('이미 갈아탄 상태입니다(덩어리 안에 %s) — 되돌리려면 revert' % MARK)
    if mode == 'revert' and not marked:
        raise SwitchError('갈아탄 덩어리가 아닙니다(%s 표시 없음) — 되돌릴 것이 없어요' % MARK)
    frag = fragment(SWITCH if mode == 'apply' else UNSWITCH)
    if (MARK in frag) != (mode == 'apply'):
        raise SwitchError('조각 파일의 표시(%s)가 이상합니다' % MARK)
    nl = '\r\n' if '\r\n' in text else '\n'
    new = text[:b['start']] + frag.replace('\n', nl) + text[b['end']:]
    _verify(text, new, blocks, b, mode)
    return new


def _verify(old, new, old_blocks, target, mode):
    nb = top_blocks(new)
    t2 = _target(nb)
    if len(nb) != len(old_blocks):
        raise SwitchError('덩어리 수가 달라졌습니다(%d → %d)' % (len(old_blocks), len(nb)))
    if new[:t2['start']] != old[:target['start']] or new[t2['end']:] != old[target['end']:]:
        raise SwitchError('큰 주소 덩어리 밖의 글자가 달라졌습니다')
    others_old = [old[x['start']:x['end']] for x in old_blocks if x is not target]
    others_new = [new[x['start']:x['end']] for x in nb if x['start'] != t2['start']]
    if others_old != others_new:
        raise SwitchError('다른 덩어리가 달라졌습니다')
    if (MARK in new[t2['start']:t2['end']]) != (mode == 'apply'):
        raise SwitchError('바꾼 덩어리의 표시가 이상합니다')


def status(text):
    lines = []
    for b in top_blocks(text):
        name = b['head'] or '(전역 설정)'
        if b['addrs'] == [HOST]:
            name += '   ← 큰 주소 · ' + ('갈아탄 상태(v2)' if MARK in text[b['start']:b['end']] else '옛 상태(전부 옛 서버)')
        lines.append(name)
    return lines


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if not a or a[0] not in ('status', 'apply', 'revert') or (a[0] == 'status' and len(a) != 2) or (a[0] != 'status' and len(a) != 3):
        print(__doc__)
        return 2
    try:
        with open(a[1], encoding='utf-8', newline='') as f:
            text = f.read()
        if a[0] == 'status':
            for line in status(text):
                print(line)
            return 0
        if os.path.abspath(a[2]) == os.path.abspath(a[1]):
            raise SwitchError('새 파일 이름이 원래 Caddyfile 과 같습니다 — 원래 파일은 고치지 않아요. 다른 이름(/tmp/Caddyfile.new)으로')
        new = swap(text, a[0])
        with open(a[2], 'w', encoding='utf-8', newline='') as f:
            f.write(new)
    except (OSError, SwitchError) as e:
        print('❌ %s' % e)
        return 1
    others = len(top_blocks(text)) - 1
    print('✅ %s → %s 에 썼습니다. 큰 주소 덩어리만 바꿨고, 다른 덩어리 %d개는 한 글자도 안 바뀌었습니다.' % (a[0], a[2], others))
    for line in status(new):
        print('   ' + line)
    print('   다음: sudo -u caddy -H caddy validate --config %s --adapter caddyfile' % a[2])
    return 0


if __name__ == '__main__':
    sys.exit(main())
