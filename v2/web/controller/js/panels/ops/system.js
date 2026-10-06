/* 🖥️ 시스템 — 옛 조종실 '시스템' 탭: 서버 상태 · 붙은 화면 · 투네이션 연결(본 계정 · 테스트 계정) · 최근 기록 30건.
   GET /api/health · GET /api/screens · GET/POST /api/toon/accounts · GET /api/events?limit=30
   이 탭이 보이는 동안만 20초마다 다시 읽는다(옛 것과 같다).
   ⚠️ 테스트 계정 주소 끝의 키는 비밀번호 같은 열쇠다 — 비밀번호 칸(가려짐)으로 받고, 서버도 끝 네 글자만 돌려준다
      (조종실 화면이 방송에 잡혀도 새지 않게). */
import { h, fill, api, once, onEnter, blockHead, num } from './common.js';

const KIND = { overlay: '📺 방송판', controller: '🎛️ 조종실', editor: '📐 편집기', bot: '🤖 진행봇', mobile: '📱 폰', console: '💸 후원 콘솔', other: '❔ 기타' };
const DEV = { obs: 'OBS', iphone: '아이폰', ipad: '아이패드', android: '안드로이드', windows: '윈도우', mac: '맥', other: '' };
const TOON = { connected: '🟢 연결됨', connecting: '🟡 연결하는 중', error: '🔴 연결 안 됨', off: '⚪ 꺼짐',
               resting: '💤 오늘은 쉬는 날 (수 · 목)', starting: '🟡 시작하는 중' };

const dur = s => s == null ? '—' : s < 60 ? s + '초' : s < 3600 ? Math.floor(s / 60) + '분' : Math.floor(s / 3600) + '시간 ' + Math.floor(s % 3600 / 60) + '분';
const hm = t => new Date(t * 1000).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

function toonText(a, fallback) {
    if (!a) return fallback;
    let s = TOON[a.state] || String(a.state || '');
    if (a.last_donation) s += ' · 마지막 후원 ' + new Date(a.last_donation * 1000).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    if (a.state === 'error' && a.note) s += ' — ' + a.note;
    return s;
}

export function mountSystem(el, ctx) {
    const srv = h('dl', { class: 'sys-dl' });
    const scrN = h('b');
    const scr = h('ul', { class: 'sys-list' });
    const tMain = h('b', null, '확인 중…'), tTest = h('b', null, '확인 중…');
    const url = h('input', { type: 'password', autocomplete: 'off', spellcheck: 'false', class: 'grow',
        placeholder: '두 번째 투네이션 알림창 주소 (https://toon.at/widget/alertbox/…)', 'aria-label': '테스트 계정 알림창 주소' });
    const save = h('button', { type: 'button', class: 'btn pri sm', onclick: () => once(save, toonSave) }, '저장');
    const clear = h('button', { type: 'button', class: 'btn sm', onclick: () => once(clear, () => toonPost({ test_url: '' }, '테스트 계정 주소를 지웠어요')) }, '주소 지우기');
    const testOn = h('input', { type: 'checkbox' });
    const evs = h('ol', { class: 'sys-ev' });
    const refresh = h('button', { type: 'button', class: 'btn sm', onclick: () => once(refresh, () => load(true)) }, '새로고침');
    onEnter(url, () => once(save, toonSave));
    testOn.addEventListener('change', () => toonPost({ enabled: testOn.checked }, testOn.checked ? '🧪 테스트 계정을 켰어요 — 10초 안에 붙어요' : '테스트 계정을 껐어요'));

    el.classList.add('ops', 'ops-system');
    el.append(
        h('section', { class: 'ops-blk' }, h('div', { class: 'ops-bh' }, h('h3', null, '서버 상태'), refresh), srv),
        h('section', { class: 'ops-blk' }, h('div', { class: 'ops-bh' }, h('h3', null, '붙은 화면 '), scrN), scr,
            h('p', { class: 'ops-dim small' }, '폰 조종실 안의 👀 방송 화면 보기는 미리보기(소리 없음)로 따로 세어져요. 끊긴 화면은 저절로 빠져요.')),
        h('section', { class: 'ops-blk' }, blockHead('투네이션 연결', '본 계정은 서버 설정 그대로 · 테스트 계정은 여기서'),
            h('div', { class: 'sys-toon' }, h('span', null, '본 계정'), tMain, h('span', null, '🧪 테스트 계정'), tTest),
            h('p', { class: 'ops-dim small' }, "테스트 계정은 수 · 목(방송하는 날)엔 저절로 쉬어요. 들어온 후원은 대기함에 '🧪 테스트 계정' 으로 표시돼요."),
            h('div', { class: 'ops-row wrap' }, url, save, clear),
            h('label', { class: 'ops-row' }, testOn, h('span', null, '테스트 계정 켜기'))),
        h('section', { class: 'ops-blk' }, blockHead('최근 기록 30건', '조종실 · 리스너 · 방송판이 보낸 명령 — 실패한 것은 안 남아요'), evs),
    );

    async function toonSave() {
        const v = url.value.trim();
        if (!v) { ctx.toast('두 번째 계정의 알림창 주소를 붙여 넣어 주세요', 'err'); url.focus(); return; }
        if (await toonPost({ test_url: v }, '🧪 테스트 계정을 저장했어요 — 10초 안에 붙어요')) url.value = '';
    }
    async function toonPost(body, okMsg) {
        const r = await api('/api/toon/accounts', body);
        if (!r.ok) { ctx.toast(r.error, 'err', 6000); paintToon(null); return false; }
        paintToon(r.data);
        ctx.toast(okMsg, 'ok');
        setTimeout(() => load(true), 12000);
        return true;
    }
    function paintToon(d) {
        if (!d) return;
        const L = d.listener || {}, T = d.test || {};
        tMain.textContent = !L.alive
            ? (L.age_sec == null ? '⚪ 리스너 소식 없음 — 리스너가 이 서버에 없거나 아직 안 켜졌어요' : `🔴 리스너가 ${Math.max(1, Math.round(L.age_sec / 60))}분째 소식이 없어요`)
            : toonText(L.main, '⚪ 본 계정 주소가 서버에 없어요');
        tTest.textContent = !T.set ? '⚪ 주소 없음' : T.enabled === false ? '⚪ 꺼짐'
            : T.resting_today ? '💤 오늘은 쉬는 날 (수 · 목)' : toonText(L.test, '🟡 곧 붙어요 (10초 안)');
        url.placeholder = T.set ? `저장된 주소: ${T.masked} — 바꾸려면 새 주소를 붙여 넣으세요` : '두 번째 투네이션 알림창 주소 (https://toon.at/widget/alertbox/…)';
        testOn.checked = !!T.set && T.enabled !== false;
        testOn.disabled = !T.set;
    }

    let last = 0, busy = false;
    async function load(force) {
        if (busy || (!force && Date.now() - last < 15000)) return;
        busy = true;
        last = Date.now();
        try {
            const [hl, sc, tn, ev] = await Promise.all([api('/api/health'), api('/api/screens'), api('/api/toon/accounts'), api('/api/events?limit=30')]);
            if (hl.ok || hl.data.uptime_sec != null) {
                const d = hl.data, c = d.counts || {};
                fill(srv, ...[
                    ['가동 시간', dur(d.uptime_sec)], ['장부(SQLite) 응답', d.db && d.db.ping_ms != null ? d.db.ping_ms + 'ms' : '실패'],
                    ['메모리', d.rss_mb != null ? d.rss_mb + 'MB' : '—'], ['선수 · 대기함', `${num(c.players)}명 · ${num(c.pending)}건`],
                    ['시그 대기줄', num(c.sig_queue) + '개'], ['마지막 후원', d.last_donation_sec == null ? '—' : dur(d.last_donation_sec) + ' 전'],
                    ['못 보낸 후원(리스너)', d.spool == null ? '?' : num(d.spool) + '건'], ['끊어 낸 화면', num(d.dropped) + '번'],
                ].flatMap(([k, v]) => [h('dt', null, k), h('dd', null, v)]));
            }
            if (sc.ok) {
                const list = (sc.data.screens || []).slice().sort((a, b) => a.kind === b.kind ? a.since_sec - b.since_sec : (a.kind > b.kind ? 1 : -1));
                scrN.textContent = list.length + '개';
                fill(scr, list.length ? list.map(s => h('li', null,
                    h('b', null, KIND[s.kind] || s.kind), s.monitor ? h('span', { class: 'tag plain' }, '미리보기') : null,
                    DEV[s.dev] ? h('span', { class: 'tag' + (s.dev === 'obs' ? ' live' : ' plain') }, DEV[s.dev]) : null,
                    h('small', { class: 'ops-dim' }, ` ${dur(s.since_sec)}째`))) : h('li', { class: 'empty' }, '붙은 화면이 없어요'));
            }
            if (tn.ok) paintToon(tn.data);
            if (ev.ok) {
                const rows = ev.data.events || [];
                fill(evs, rows.length ? rows.map(e => h('li', null, h('span', { class: 'ops-dim' }, hm(e.at)), h('b', null, e.type),
                    h('small', { class: 'ops-dim' }, e.by), e.data ? h('code', null, e.data) : null)) : h('li', { class: 'empty' }, '아직 기록이 없어요'));
            }
        } finally { busy = false; }
    }

    // 이 탭이 보이는 동안만 20초마다
    const timer = setInterval(() => { if (!el.isConnected) { clearInterval(timer); return; } if (el.offsetParent) load(false); }, 20000);
    return { render() { load(false); } };
}
