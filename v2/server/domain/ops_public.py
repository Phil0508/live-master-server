# -*- coding: utf-8 -*-
"""🌐 로그인 없이 바깥에서 읽는 주소 — 옛 프로그램과 **같은 모양**으로(10-17 이사 1차 · ops).

GET /api/signatures/board   📜 크루 사이트 시그리스트가 읽는다(옛 features/signature_play.py api_signature_board · 3715894 · 3477d81)
    → {"status":"success","rows":[{"amount","title","image_url","sound_url"}…],"count":N}  금액 순(같으면 이름 순)
    - 번호(id)는 안 준다 — 시그게임 카드가 번호로 나가서, 번호→이름을 이어 볼 수 없게(옛 것과 같다).
    - 1분 동안 같은 답. 시그 목록은 서버의 시그니처 기억(bus.sigs — 10분 · 시그 관리에서 고치면 바로 새로)을 쓴다 —
      Supabase 를 따로 부르지 않는다. 못 읽으면 지난 답, 처음부터 못 읽으면 502 {"status":"error","rows":[]}.
GET /api/oraksil/donors     🏆 크루 사이트 '엔젤오락실 후원 순위'가 읽는다(옛 features/archive.py api_oraksil_donors · 6076216)
    → {"rows":[{"day","name","amount","count"}…]}  최근 방송부터, 그 안에서는 많이 낸 순
    - 셈은 월별 순위(monthly.py)와 같다: 수요일 방송 창(bc_day) 안 후원만, 그 방송이 시작한 수요일 × 사람(norm_donor 로 묶고
      보여줄 이름은 처음 쓴 원래 이름). 익명 · 순위에서 뺀 이름(donor_rules.excluded) · 테스트 계정(source toonation_test) ·
      0원 이하 · 화면에만 뜬 소액(status display — 장부 합계에 안 세는 것)은 뺀다.
    - 금액 · 이름 · 건수 · 날만 — 메시지 · 시각 · 출처는 안 나간다. 1분 기억 · 못 읽으면 지난 답 · 처음부터 못 읽으면 502.
GET /privacy · /terms       📄 구글 OAuth 동의 화면에 적은 주소(옛 features/legal.py — 글자 하나 안 바꿨다, 검사가 옛 것과 맞대 본다)

⚠️ 칸 이름을 바꾸면 크루 사이트가 깨진다(crew-site 의 MAIN_SIG_URL · MAIN_RANK_URL 이 그대로 읽는다).
⚠️ 기억은 서버마다(bus.ops_public_cache) — 검사에서 서버를 새로 만들면 기억도 새로다.
"""
import asyncio
import os
import time

from fastapi.responses import HTMLResponse, JSONResponse

from .legacy import route
from .monthly import bc_day
from .rules import COUNTED, norm_donor

BOARD_TTL = 60
DONORS_TTL = 60
TEST_SOURCE = 'toonation_test'


def _cache(bus, name):
    c = getattr(bus, 'ops_public_cache', None)
    if c is None:
        c = bus.ops_public_cache = {}
    return c.setdefault(name, {'t': 0.0, 'rows': None})


def _as_int(v, default=None):
    """옛 server._as_int 그대로 — 글자 · None · 소수 무엇이 와도 예외 없이."""
    if isinstance(v, bool) or v is None:
        return default
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


# ── 📜 시그리스트 ──
def board_rows(sigs):
    rows = []
    for s in sigs or []:
        amt = _as_int(s.get('amount')) if isinstance(s, dict) else None
        if amt and amt > 0:
            rows.append({'amount': amt, 'title': str(s.get('title') or '').strip(),
                         'image_url': s.get('image_url') or '', 'sound_url': s.get('sound_url') or ''})
    rows.sort(key=lambda r: (r['amount'], r['title']))
    return rows


def _read_sigs(sigs):
    rows = sigs.rows()
    if not rows and getattr(sigs, 'last_error', ''):
        raise RuntimeError(sigs.last_error)          # 한 번도 못 읽었다(기억도 비었다)
    return rows


@route('/api/signatures/board', methods=('GET',))
async def signature_board(req, bus, authed, answer):
    c = _cache(bus, 'board')
    now = time.time()
    if c['rows'] is None or now - c['t'] > BOARD_TTL:
        try:
            raw = await asyncio.to_thread(_read_sigs, bus.sigs)
            c.update(t=now, rows=board_rows(raw))
        except Exception as e:
            print('[시그리스트 조회 오류] %s' % type(e).__name__, flush=True)
            if c['rows'] is None:
                return JSONResponse({'status': 'error', 'message': '시그 목록을 못 읽었어요', 'rows': []}, status_code=502)
    resp = JSONResponse({'status': 'success', 'rows': c['rows'], 'count': len(c['rows'])})
    resp.headers['Cache-Control'] = 'public, max-age=60'
    return resp


# ── 🏆 엔젤오락실 후원 순위 ──
def oraksil_rows(rows, excluded):
    """rows = [(at(epoch 초), name, amount, source)] 들어온 순서대로 → [{day, name, amount, count}] (옛 _oraksil_donor_rows 셈)"""
    tally = {}
    for at, name, amount, source in rows:
        if str(source or '') == TEST_SOURCE:
            continue                                  # 테스트용 두 번째 투네이션 — 진짜 후원이 아니다
        day = bc_day(at)
        if not day:
            continue                                  # 방송 시간 밖 — 안 센다
        who = norm_donor(name)
        if who == '익명' or who in excluded:
            continue
        try:
            amt = int(amount or 0)
        except (TypeError, ValueError):
            continue
        if amt <= 0:
            continue
        key = (str(day), who)
        row = tally.get(key)
        if row is None:
            row = tally[key] = {'day': str(day), 'name': ' '.join(str(name or '').split()) or who, 'amount': 0, 'count': 0}
        row['amount'] += amt
        row['count'] += 1
    # 최근 방송부터, 그 안에서는 많이 낸 순(같으면 먼저 온 사람이 위 — 옛 것과 같은 정렬)
    return sorted(tally.values(), key=lambda r: (r['day'], r['amount']), reverse=True)


def _ledger(bus):
    return [(r['at'], r['name'], r['amount'], r['source']) for r in bus.store.db.execute(
        'SELECT at, name, amount, source FROM donations WHERE status IN (%s) ORDER BY at, rowid'
        % ','.join('?' * len(COUNTED)), COUNTED)]


@route('/api/oraksil/donors', methods=('GET',))
async def oraksil_donors(req, bus, authed, answer):
    c = _cache(bus, 'donors')
    now = time.time()
    if c['rows'] is None or now - c['t'] > DONORS_TTL:
        try:
            excluded = set(bus.state.get('donor_rules').get('excluded') or [])
            c.update(t=now, rows=oraksil_rows(_ledger(bus), excluded))
        except Exception as e:
            print('[엔젤오락실 후원 순위 조회 오류] %s' % type(e).__name__, flush=True)
            if c['rows'] is None:
                return JSONResponse({'rows': [], 'message': '후원 장부를 못 읽었어요'}, status_code=502)
    return JSONResponse({'rows': c['rows']})


# ── 📄 개인정보처리방침 · 서비스 약관 — 옛 features/legal.py 를 글자 그대로 옮겼다 ──
#   구글 OAuth 동의 화면을 '프로덕션' 으로 게시하려면 이 두 주소가 있어야 한다.
#   테스트 상태로 두면 갱신 토큰이 7일마다 만료돼 진행봇이 일주일마다 멈춘다.
#   ⚠️ 무인증으로 연다. 구글과 시청자가 로그인 없이 봐야 한다.
#   ⚠️ 내용은 '이 시스템이 실제로 하는 일' 이다. 하는 일이 바뀌면 여기도 고쳐야 한다.
LEGAL_CONTACT = os.environ.get('CONTACT_EMAIL', 'isacbin010@gmail.com')
LEGAL_UPDATED = '2026-09-14'


def _legal_page(title, blocks):
    """검은 배경에 읽기 좋은 한 장짜리 문서. 폰에서도 읽히게 글자를 키웠다."""
    body = ''
    for head, items in blocks:
        body += f'<h2>{head}</h2><ul>'
        for it in items:
            body += f'<li>{it}</li>'
        body += '</ul>'
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · 엔젤컴퍼니</title><style>
  body{{margin:0;background:#101014;color:#e6e6ee;line-height:1.75;
       font-family:'Pretendard','Malgun Gothic','Apple SD Gothic Neo',sans-serif}}
  .wrap{{max-width:820px;margin:0 auto;padding:46px 22px 80px}}
  h1{{font-size:30px;margin:0 0 6px;color:#fff}}
  .sub{{color:#9a9aac;font-size:15px;margin:0 0 34px}}
  h2{{font-size:20px;color:#f6c453;margin:34px 0 10px}}
  ul{{padding-left:20px;margin:0}} li{{margin:7px 0;font-size:16px;color:#cfcfdc}}
  b{{color:#fff}} a{{color:#7fb2ff}}
  .foot{{margin-top:44px;padding-top:18px;border-top:1px solid #2b2b36;
         color:#8a8a99;font-size:14px}}
</style></head><body><div class="wrap">
<h1>{title}</h1><p class="sub">엔젤컴퍼니 · 마지막 수정 {LEGAL_UPDATED}</p>
{body}
<div class="foot">문의: <a href="mailto:{LEGAL_CONTACT}">{LEGAL_CONTACT}</a></div>
</div></body></html>'''


def privacy_html():
    return _legal_page('개인정보처리방침', [
        ('무엇을 하는 서비스인가요', [
            '엔젤컴퍼니는 인터넷 방송을 진행하면서 <b>후원 내역과 게임 진행 상황을 화면에 띄우는</b> 도구를 씁니다.',
            '<b>진행봇</b>은 방송에서 일어난 일(후원 감사, 주사위 결과, 순위 변동 등)을 유튜브 라이브 채팅에 자동으로 알려주는 프로그램입니다.',
        ]),
        ('어떤 정보를 다루나요', [
            '<b>후원 정보</b> — 후원자가 직접 적은 표시 이름, 후원 금액, 후원 메시지. 후원 플랫폼과 계좌 입금 내역에서 들어옵니다. 방송 화면 표시와 정산에만 씁니다.',
            '<b>방송 진행 정보</b> — 출연자 점수, 게임 상태. 개인을 알아볼 수 있는 정보가 아닙니다.',
            '<b>유튜브 계정 권한(진행봇)</b> — 운영자가 따로 만든 <b>봇 전용 계정</b>의 채팅 작성 권한만 받습니다.',
        ]),
        ('하지 않는 일', [
            '주민등록번호·카드번호·계좌 비밀번호 같은 <b>민감한 정보는 받지 않습니다.</b>',
            '<b>시청자의 채팅을 읽거나 저장하지 않습니다.</b> 진행봇은 채팅을 쓰기만 합니다.',
            '시청자의 유튜브 계정 정보에 접근하지 않습니다.',
            '어떤 정보도 <b>광고·마케팅에 쓰거나 제3자에게 팔지 않습니다.</b>',
        ]),
        ('구글 사용자 데이터', [
            '진행봇은 <code>youtube.force-ssl</code> 권한을 받습니다. 이 권한은 <b>봇 계정으로 라이브 채팅에 글을 쓰는 데에만</b> 씁니다.',
            '영상·구독자·시청자 정보를 읽거나 바꾸지 않습니다.',
            '엔젤컴퍼니는 구글 API 서비스 사용자 데이터 정책(<b>제한적 사용 요건</b> 포함)을 따릅니다. <a href="https://developers.google.com/terms/api-services-user-data-policy">정책 보기</a>',
            '운영자는 구글 계정 설정에서 <b>언제든 이 권한을 회수</b>할 수 있습니다.',
        ]),
        ('얼마나 보관하나요', [
            '방송 화면에 쓰는 정보는 <b>방송 회차가 끝나면 지웁니다.</b>',
            '후원 내역은 정산과 문의 대응을 위해 보관하며, 필요가 없어지면 지웁니다.',
            '봇 계정 권한(토큰)은 운영자 컴퓨터에만 두고 외부에 보내지 않습니다.',
        ]),
        ('문의와 요청', [
            '내 후원 기록을 지워달라는 요청은 아래 메일로 주시면 확인 후 처리합니다.',
            '이 방침이 바뀌면 이 페이지에 새 수정일과 함께 올립니다.',
        ]),
    ])


def terms_html():
    return _legal_page('서비스 약관', [
        ('이 약관은 무엇인가요', [
            '엔젤컴퍼니가 운영하는 방송 화면·후원 안내·진행봇에 적용되는 이용 약관입니다.',
            '방송을 보시거나 후원하시면 이 약관에 동의하신 것으로 봅니다.',
        ]),
        ('후원에 대하여', [
            '후원은 <b>자발적인 응원</b>이며, 물건이나 서비스를 사는 것이 아닙니다.',
            '후원하신 금액은 방송 진행과 출연자 정산에 쓰입니다.',
            '<b>잘못 보내셨거나 실수로 후원하신 경우</b> 아래 메일로 알려주시면 확인 후 처리해 드립니다.',
            '방송 화면에 표시되는 이름과 메시지는 후원하실 때 직접 적으신 내용입니다.',
        ]),
        ('하시면 안 되는 것', [
            '남을 욕하거나 괴롭히는 내용, 불법적인 내용을 후원 메시지에 적는 것',
            '다른 사람인 척하거나 남의 결제 수단을 쓰는 것',
            '자동 프로그램으로 서비스를 방해하거나 과도하게 요청을 보내는 것',
            '이런 경우 해당 메시지를 화면에 띄우지 않거나 표시를 제한할 수 있습니다.',
        ]),
        ('진행봇에 대하여', [
            '진행봇은 <b>사람이 아니라 프로그램</b>이며, 채팅에서 봇임을 밝히고 있습니다.',
            '방송 상황을 알려줄 뿐이고, 시청자의 질문에 답하거나 대화하지 않습니다.',
        ]),
        ('책임의 한계', [
            '인터넷 상황, 방송 플랫폼 사정, 점검 등으로 서비스가 잠시 멈출 수 있습니다.',
            '방송 내용과 진행 방식은 사전 예고 없이 바뀔 수 있습니다.',
        ]),
        ('약관 변경', [
            '약관이 바뀌면 이 페이지에 새 수정일과 함께 올립니다.',
            '궁금한 점은 아래 메일로 물어봐 주세요.',
        ]),
    ])


@route('/privacy', methods=('GET',))
async def privacy(req, bus, authed, answer):
    return HTMLResponse(privacy_html())


@route('/terms', methods=('GET',))
async def terms(req, bus, authed, answer):
    return HTMLResponse(terms_html())
