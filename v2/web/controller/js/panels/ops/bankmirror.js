/* 🪞 시스템 탭 '은행 확장' 거울 칸 · 📱 '폰 입금알림 앱' 칸 — 옛 controller.html #bankext-box · #bankapp-box(10-14 · 10-16)를 옮겼다.
   거울: 스튜디오 PC 은행 화면의 '엔젤 입금확인' 상자를 그대로 비춘다(같은 신호등 바 · 찾은 입금 · 기록).
         단추는 서버에 명령을 넣고(/api/bank/ext/cmd) 확장이 다음 신호 때(25초 안) 따라 한다. 은행 로그인은 여기서 못 한다.
         읽기는 머리줄 '계좌' 점과 같은 것(bankext.js — 10초마다)을 같이 쓴다.
   앱: 공기계 카메라로 QR(vendor/qrious) 을 찍거나 [APK 받기] — /download/bankphone.apk 는 로그인 없이 받는다(앱 안에 비밀값 없음).
   ⚠️ 바깥 글자(메모 · 기록)는 전부 h()/textContent 로 — innerHTML 금지. */
import { h, num, api, fill } from './common.js';
import { judgeExt, extLevel, pendingText, extWarns, bankAgo, bankHHMM } from '../../bankcore.js';
import { onExt, extNow, extCmd, loadExt } from '../../bankext.js';

export function mountBankMirror(ctx) {
    const ver = h('span', { class: 'ops-sub' });
    const dot = h('span', { class: 'bkx-dot' });
    const t1 = h('b', null, '불러오는 중…'), t2 = h('small');
    const cnt = h('span', { class: 'bkx-cnt' }, '입금 0');
    const bar = h('div', { class: 'bkx-bar' }, dot, h('span', { class: 'bkx-t' }, t1, t2), cnt);
    const toggle = h('button', { type: 'button', class: 'btn sm', onclick: () => extCmd(ctx, 'enable') }, '자동 조회 켜기');
    const sel = h('select', { class: 'ops-select bkx-sel', title: '조회 간격', 'aria-label': '조회 간격' },
        ...[20, 30, 60].map(s => h('option', { value: String(s), selected: s === 30 }, s + '초마다')));
    sel.addEventListener('change', () => extCmd(ctx, 'interval', sel.value));
    const press = h('button', { type: 'button', class: 'btn sm', title: '자동 조회가 꺼져 있어도 [조회]를 한 번 눌러요', onclick: () => extCmd(ctx, 'press') }, '지금 조회');
    const rebase = h('button', { type: 'button', class: 'btn sm', title: '지금 표에 있는 줄은 입금으로 안 알려요 — 계좌 · 기간을 바꾼 뒤에', onclick: () => extCmd(ctx, 'rebase') }, '기준 다시 잡기');
    const pend = h('p', { class: 'ops-hint' });
    const warn = h('div');
    const meta = h('p', { class: 'ops-hint' });
    const found = h('div', { class: 'bkx-found' });
    const log = h('ul', { class: 'bkx-log' });
    const phone = h('span', null, '—');
    const el = h('section', { class: 'ops-blk bkx', 'data-bank-ext': '1', 'aria-label': '은행 확장 거울' },
        h('div', { class: 'ops-bh' }, h('h3', null, '🏦 은행 확장 (스튜디오 PC · 계좌 입금 받기)'), ver),
        bar,
        h('div', { class: 'ops-row wrap' }, toggle, sel, press, rebase),
        pend, warn, meta, found,
        h('details', null, h('summary', { class: 'ops-hint' }, '확장 기록'), log),
        h('p', { class: 'ops-hint' }, '명령은 확장이 다음 신호 때(25초 안) 받아요. 은행 ', h('b', null, '로그인'), '은 스튜디오 PC에서만 할 수 있어요. 폰 앱: ', phone));

    function paint(d) {
        const j = judgeExt(d, Date.now());
        const w = d && d.link && d.link.web, st = (w && w.state) || {};
        dot.className = 'bkx-dot ' + extLevel(j);
        bar.classList.toggle('dead', !!j.dead);
        t1.textContent = j.t1;
        t2.textContent = j.t2;
        cnt.textContent = '입금 ' + ((st.found || []).length);
        ver.textContent = st.v ? '확장 ' + st.v : '';
        toggle.textContent = st.enabled ? '자동 조회 끄기' : '자동 조회 켜기';
        toggle.classList.toggle('on', !!st.enabled);
        toggle.disabled = !w || j.k === 'off';
        if (st.interval && document.activeElement !== sel && [20, 30, 60].includes(st.interval)) sel.value = String(st.interval);
        pend.textContent = pendingText((d && d.pending && d.pending.web) || []);
        pend.hidden = !pend.textContent;
        fill(warn, extWarns(st, !!w).map(x => h('p', { class: 'ops-note warn' }, '⚠ ' + x)));
        meta.textContent = w ? ('신호 ' + bankAgo(w.age_sec) + (w.note ? ' · ' + w.note : '') + (st.lastOkAt ? ' · 마지막 정상 ' + bankHHMM(st.lastOkAt) : '') + (st.rows ? ' · 표 ' + st.rows + '줄' : '')) : '';
        meta.hidden = !meta.textContent;
        fill(found, (st.found || []).length
            ? st.found.map(f => h('div', { class: 'bkx-dep' }, h('b', null, num(f.dep || 0) + '원'), h('span', null, f.memo || '(내용 없음)'),
                h('span', { class: 'ops-dim' }, f.when || ''), h('span', { class: 'ops-dim' }, '찾음 ' + bankHHMM(f.at))))
            : h('p', { class: 'ops-hint' }, '확장이 아직 찾은 입금이 없어요'));
        fill(log, (st.log || []).map(x => h('li', null, x)));
        const ph = d && d.link && d.link.phone;
        phone.textContent = ph ? (ph.age_sec < 90 ? '연결됨 · ' + bankAgo(ph.age_sec) : '마지막 ' + bankAgo(ph.age_sec)) : '안 켜져 있음';
    }
    onExt(paint);
    paint(extNow().data);
    return { el, render() { loadExt(false); } };
}

let qrLoading = null;
function loadQr() {
    if (window.QRious) return Promise.resolve(true);
    if (!qrLoading) {
        qrLoading = new Promise(res => {
            const s = document.createElement('script');
            s.src = '/vendor/qrious.min.js';          // 우리 서버(저장소 vendor/) — 바깥 CDN 안 씀
            s.onload = () => res(!!window.QRious);
            s.onerror = () => { qrLoading = null; res(false); };
            document.head.append(s);
        });
    }
    return qrLoading;
}

export function mountBankApp(ctx) {
    const url = () => location.origin + '/download/bankphone.apk';
    const ver = h('span', { class: 'ops-sub' });
    const qr = h('canvas', { class: 'bkapp-qr', width: '132', height: '132', 'aria-label': '앱 받는 주소 QR' });
    const urlEl = h('p', { class: 'ops-hint bkapp-url' });
    const dl = h('a', { class: 'btn sm', href: '/download/bankphone.apk' }, '⬇ APK 받기');
    const copy = h('button', { type: 'button', class: 'btn sm' }, '주소 복사');
    const el = h('section', { class: 'ops-blk bkapp', 'aria-label': '폰 입금알림 앱' },
        h('div', { class: 'ops-bh' }, h('h3', null, '📱 폰 입금알림 앱 (안드로이드)'), ver),
        h('div', { class: 'bkapp-row' }, qr,
            h('div', { class: 'bkapp-txt' },
                h('p', { class: 'ops-hint' }, '공기계 카메라로 QR 을 찍거나 아래 단추로 받으세요. 기업은행 앱의 입금 알림을 읽어 ',
                    h('b', null, '후원 콘솔 → 🏦 계좌 입금 추천'), ' 칸으로 보내요(송출은 사람이 눌러요).'),
                h('p', { class: 'ops-hint' }, '깐 뒤 앱에서 ① 알림 읽기 권한 ② 배터리 절약 빼기 ③ 후원 콘솔 [은행 확장 연결]의 열쇠 붙여 넣기.'),
                h('div', { class: 'ops-row wrap' }, dl, copy),
                urlEl)));
    copy.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(url()); ctx.toast('앱 받는 주소를 복사했어요 — 공기계로 보내 열면 받아져요', 'ok'); }
        catch (e) { ctx.toast('이 주소를 공기계에서 여세요: ' + url(), 'info', 9000); }
    });
    let done = false;
    async function load() {
        if (done) return;
        done = true;
        urlEl.textContent = url();
        const r = await api('/api/bank/app');
        if (r.ok) ver.textContent = r.data.ready ? ('판 ' + r.data.version + ' · ' + Math.max(1, Math.round(r.data.size / 1024)) + 'KB') : '아직 앱 파일이 없어요';
        else done = false;
        if (await loadQr()) {
            try { new window.QRious({ element: qr, value: url(), size: 132, level: 'M' }); } catch (e) { /* QR 없이도 단추 · 주소는 된다 */ }
        }
    }
    return { el, render() { load(); } };
}
