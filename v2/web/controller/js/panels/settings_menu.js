/* ⚙ 설정 화면 — 왼쪽 줄에 없는 탭(약 20개)을 묶음별 타일로 모았다(시안 B). 맨 아래 [로그아웃].
   타일을 누르면 그 탭이 가운데 칸에 열리고, 왼쪽 줄에서는 '설정' 이 켜진 채다(맨 위 '← 설정' 으로 돌아온다).
   - 타일 = button.tab.st-tile[data-tab] — 클릭 기록(uistats)이 왼쪽 줄 탭과 같은 이름(tab:<id>)으로 센다.
   - 방송 전에는 '방송 전에도 여는 탭(pre)' 만 눌린다. 나머지는 흐리게(누르면 까닭 알림).
   - 마지막에 고른 타일에 '최근' 딱지(이 컴퓨터에만 기억 — lm2_tab).
   - 숨은 탭의 새 소식(후원 콘솔 계좌 수 · 안 읽은 AI 알림)은 타일 오른쪽 위 숫자로.
   - 새 탭을 다른 곳에서 더하면(묶음에 안 적은 것) 맨 끝 '그 밖' 묶음에 저절로 나온다 — 빠뜨려 못 여는 일이 없게.
   ⚠️ 로그아웃은 있는 POST /logout 을 부르기만 한다(보안 설정은 건드리지 않는다). 방송은 그대로 계속된다. */
import { h } from '../util.js';
import { icon } from '../icons.js';
import { lastTile } from '../tabs.js';
import { openBankExt } from '../bankext.js';
import { mountBigokSettings } from '../bigok.js';   // 🛡️ 큰 금액 확인 기준 칸(10-17 bigok)

// [묶음 이름, [탭 id …]] — '@bank' 는 탭이 아니라 시스템 탭 안의 은행 확장 칸으로 가는 길
const GROUPS = [
    ['방송 화면', ['ops-stage', 'ops-notice', 'ops-fundjar', 'ops-screen', 'ops-media', 'ops-mask']],
    ['시그니처 · 연출', ['sig-admin', 'sig-monitor', 'fx-lights', 'ops-opfx', 'clip']],
    ['기록', ['ledger', 'donorbook', 'donors', 'check', 'monthly', 'uistats']],
    ['AI · 자동', ['ai', 'auto']],
    ['테스트 · 연습', ['@practice']],
    ['시스템', ['ops-bot', 'ops-version', 'ops-system', '@bank', 'ops-migrate']],
];

const DESC = {
    'ops-stage': '방송판에 띄울 것 · 순서표',
    'ops-notice': '방송판 아래로 흐르는 안내',
    'ops-fundjar': '모금함 켜기 · 금액 · 깃발 자리',
    'ops-screen': '계좌 글 · 시작 전/끝 화면',
    'ops-media': '고액 후원 영상 · 노래방',
    'ops-mask': '금칙어 · 전화번호 · 주소 가리기',
    'sig-admin': '음원 · 사진 등록 · 고치기',
    'sig-monitor': '방송판을 작게 미리 보기',
    'fx-lights': '시그니처 때 네온 · 아우디 조명',
    'ops-opfx': '배너 · 번쩍 · 충격파 연출 쏘기',
    clip: '지금 순간 저장 · OBS 연결',
    ledger: '이번 방송 후원 · 점수 기록',
    donorbook: '누구 팬인지 딱지 · 같은 사람 묶기 · 팬클럽 사전',
    donors: '후원 순위 · 순위에서 빼기',
    check: '방송 전 점검표',
    monthly: '이번 달 후원 순위',
    uistats: '자주 누른 단추 순위',
    ai: '상황판 · 물어보기 · 오토파일럿',
    auto: '무인 방송 — 끔 · 그림자 · 켬',
    'ops-bot': '채팅 진행봇 · 라이브 주소',
    'ops-version': '프로그램 버전 되돌리기',
    'ops-system': '연결 상태 · 최근 기록',
    'ops-migrate': '옛 프로그램 설정 가져오기',
};

/** 로그아웃 — 한 번 묻고 POST /logout 뒤 새로 고침(로그인 화면) */
export async function logout(ctx) {
    const ok = await ctx.confirm({
        title: '로그아웃할까요?',
        body: '이 기기에서 조종실을 다시 쓰려면 비밀번호를 넣어야 해요.\n방송 · 방송판은 그대로 계속돼요.',
        ok: '로그아웃', cancel: '그대로 두기', danger: false,
    });
    if (!ok) return;
    try { await fetch('/logout', { method: 'POST', credentials: 'same-origin' }); } catch (e) { /* 그래도 새로 고친다 */ }
    location.reload();
}

export function mountSettings(el, ctx) {
    const tabs = () => ctx.tabs;                    // main.js 가 mountTabs 뒤에 넣어 둔다
    const all = tabs() ? tabs().panels : [];
    const byId = new Map(all.map(p => [p.id, p]));
    const tiles = new Map();                        // id → { btn, news }

    function tile(id) {
        if (id === '@bank') {
            const b = h('button', { type: 'button', class: 'st-tile st-act', 'data-act': 'bank-ext', onclick: () => {
                if (tabs() && tabs().locked('ops-system')) { ctx.toast('방송을 시작하면 열려요', 'info'); return; }
                openBankExt();
            } },
                h('span', { class: 'st-emo', 'aria-hidden': 'true' }, '🏦'),
                h('span', { class: 'st-tx' }, h('b', null, '은행 확장'), h('small', null, '계좌 입금 확장 · 폰 앱 상태')));
            tiles.set(id, { btn: b, lockId: 'ops-system' });
            return b;
        }
        if (id === '@practice') {       // 🧪🎓 따로 페이지(/practice/, 10-19) — 방송 전에도 열린다
            const b = h('button', { type: 'button', class: 'st-tile st-act', 'data-act': 'practice', 'data-zone': 'practice',
                onclick: () => { window.open('/practice/', 'lm-practice'); } },
                h('span', { class: 'st-emo', 'aria-hidden': 'true' }, '🧪'),
                h('span', { class: 'st-tx' }, h('b', null, '테스트 · 연습'), h('small', null, '방송판 화면 테스트 · 가짜 후원으로 배정 연습')));
            tiles.set(id, { btn: b, lockId: 'settings' });     // 설정 화면(pre)과 같이 — 방송 전에도 눌린다
            return b;
        }
        const p = byId.get(id);
        if (!p) return null;
        const news = h('span', { class: 'st-news', hidden: true });
        const last = h('span', { class: 'st-last', hidden: true }, '최근');
        const b = h('button', { type: 'button', class: 'tab st-tile', 'data-tab': id, title: p.label, onclick: () => tabs() && tabs().open(id) },
            h('span', { class: 'st-emo', 'aria-hidden': 'true' }, p.icon || '•'),
            h('span', { class: 'st-tx' }, h('b', null, p.label), DESC[id] ? h('small', null, DESC[id]) : null),
            last, news);
        tiles.set(id, { btn: b, news, last, lockId: id });
        return b;
    }

    const used = new Set();
    const blocks = GROUPS.map(([name, ids]) => {
        const kids = ids.map(id => { used.add(id); return tile(id); }).filter(Boolean);
        return kids.length ? h('section', { class: 'st-grp' }, h('h3', null, name), h('div', { class: 'st-tiles' }, kids)) : null;
    }).filter(Boolean);
    const rest = all.filter(p => !p.rail && !p.home && p.id !== 'settings' && !used.has(p.id)).map(p => tile(p.id)).filter(Boolean);
    if (rest.length) blocks.push(h('section', { class: 'st-grp' }, h('h3', null, '그 밖'), h('div', { class: 'st-tiles' }, rest)));

    const outBtn = h('button', { type: 'button', class: 'btn sm st-logout', onclick: () => logout(ctx) }, icon('logout'), '로그아웃');
    const bigok = mountBigokSettings(ctx);          // 🛡️ 큰 금액 확인 — 기준(서버 조각 bigok)
    el.classList.add('st-panel');
    el.append(
        h('div', { class: 'sec-head' }, h('h2', null, '설정'),
            h('span', { class: 'muted small' }, '자주 안 쓰는 화면을 모았어요. 타일을 누르면 열려요.')),
        ...blocks,
        bigok.el,
        h('section', { class: 'st-grp st-out' }, h('h3', null, '이 기기'),
            h('div', { class: 'st-outrow' }, outBtn, h('span', { class: 'muted small' }, '방송은 그대로 계속돼요'))));

    return {
        render() {
            bigok.render();
            const T = tabs();
            if (!T) return;
            const lt = lastTile();
            for (const [id, t] of tiles) {
                const lock = T.locked(t.lockId);
                t.btn.classList.toggle('locked', lock);
                if (lock) t.btn.setAttribute('aria-disabled', 'true'); else t.btn.removeAttribute('aria-disabled');
                if (t.last) { const on = id === lt; if (t.last.hidden === on) t.last.hidden = !on; }
                if (t.news) {
                    const n = T.newsText(id);
                    if (t.news.textContent !== n) t.news.textContent = n;
                    if (t.news.hidden !== !n) t.news.hidden = !n;
                }
            }
        },
    };
}

export const SETTINGS_PANEL = { id: 'settings', label: '설정', short: '설정', icon: '⚙️', rail: true, pre: true, mount: mountSettings };
