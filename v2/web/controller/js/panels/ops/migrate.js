/* 📦 옛 설정 옮기기 — 옛 조종실 [💾 백업] 파일(live_master_backup_날짜.json)을 골라 v2 로.
   명령 admin.import_old {state} — 한 번에(하나라도 이상하면 아무것도 안 바뀐다). 결과 notes.imported = 옮긴 것 이름들.
   옮기는 것: 공지 · 계좌 · 목표 · 테마 · 퇴근빵 목표 · 내 퀴즈 문제 · 고액 영상 · 모금함 · 룰렛 · 슬롯 · 주사위 판 · 스위치 · 운영비 이름 · 진행봇.
   ⚠️ 점수 · 대기함 · 시그니처 대기줄 같은 '방송 한 회' 것은 옮기지 않는다 — 갈아타기는 방송과 방송 사이에 한다.
   ⚠️ 지난 후원 기록 · 후원자 기억은 여기가 아니라 서버에서 v2/tools/import_old_db.py 로 옮긴다(옛 장부 DB 를 읽어야 해서). */
import { h, fill, once, blockHead } from './common.js';

const LOOK = [
    ['notice_msgs', '공지'], ['account', '계좌'], ['target_goal', '목표'], ['theme', '테마'], ['home_goals', '퇴근빵 목표'],
    ['quiz', '내 퀴즈 문제'], ['account_video_tiers', '고액 영상'], ['fundjar', '모금함'], ['roulette', '룰렛 항목'],
    ['slot_pool', '슬롯 후보'], ['dicegame', '주사위 판'], ['show', '고정 자리 · 알림 스위치'], ['bottom_fixed', '운영비 이름'],
    ['announce_bot', '진행봇'],
];

export function mountMigrate(el, ctx) {
    const file = h('input', { type: 'file', accept: '.json,application/json', 'aria-label': '옛 백업 파일 고르기' });
    const what = h('div', { class: 'mg-what' });
    const go = h('button', { type: 'button', class: 'btn pri', disabled: true, onclick: () => once(go, run) }, '이 설정을 v2 로 옮기기');
    const done = h('div', { class: 'mg-done', hidden: true });
    let state = null, fname = '';

    el.classList.add('ops', 'ops-migrate');
    el.append(
        h('section', { class: 'ops-blk' }, blockHead('옛 조종실 백업 파일', '옛 조종실 오른쪽 아래 [💾 백업] 을 누르면 받아지는 파일이에요'),
            h('div', { class: 'ops-row wrap' }, file), what, h('div', { class: 'ops-row end' }, go)),
        done,
        h('p', { class: 'ops-note gold' }, '점수 · 대기함 · 시그니처 대기줄은 옮기지 않아요(방송 한 회 것). 지난 후원 기록 · 후원자 기억은 서버에서 따로 옮겨요.'),
    );

    file.addEventListener('change', () => {
        state = null;
        go.disabled = true;
        done.hidden = true;
        const f = file.files && file.files[0];
        if (!f) { fill(what); return; }
        fname = f.name;
        if (f.size > 20 * 1024 * 1024) { fill(what, h('p', { class: 'ops-note warn' }, '파일이 너무 커요(20MB 넘음) — 옛 백업 파일이 맞나요?')); return; }
        const rd = new FileReader();
        rd.onload = () => {
            let j;
            try { j = JSON.parse(String(rd.result || '')); } catch (e) { fill(what, h('p', { class: 'ops-note warn' }, 'JSON 파일이 아니에요 — 옛 조종실 [💾 백업] 파일을 골라 주세요')); return; }
            if (!j || typeof j !== 'object' || Array.isArray(j)) { fill(what, h('p', { class: 'ops-note warn' }, '옛 상태 파일 모양이 아니에요')); return; }
            const found = LOOK.filter(([k]) => j[k] !== undefined && j[k] !== null);
            if (!found.length) { fill(what, h('p', { class: 'ops-note warn' }, '옮길 설정을 찾지 못했어요 — 옛 조종실 [💾 백업] 파일이 맞나요?')); return; }
            state = j;
            go.disabled = false;
            fill(what,
                h('p', { class: 'ops-dim' }, `📄 ${fname} — 옮길 수 있는 것 ${found.length}가지`),
                h('div', { class: 'mg-chips' }, found.map(([, n]) => h('span', { class: 'tag plain' }, n))),
                (j.notice_msgs || []).length ? h('small', { class: 'ops-dim' }, `공지 ${j.notice_msgs.length}줄 · 첫 줄: ${String(j.notice_msgs[0]).slice(0, 40)}`) : null,
                j.account && j.account.bank ? h('small', { class: 'ops-dim' }, `계좌: ${j.account.bank} ${j.account.name || ''}`) : null);
        };
        rd.onerror = () => fill(what, h('p', { class: 'ops-note warn' }, '파일을 읽지 못했어요'));
        rd.readAsText(f, 'utf-8');
    });

    async function run() {
        if (!state) return;
        const ok = await ctx.confirm({
            title: '옛 설정을 v2 로 옮길까요?',
            body: '공지 · 계좌 · 목표 · 테마 · 게임 판 설정이 이 파일의 것으로 바뀌어요.\n점수 · 대기함은 그대로예요. 하나라도 이상하면 아무것도 안 바뀌어요.',
            ok: '옮기기', cancel: '그만두기', danger: false,
        });
        if (!ok) return;
        const res = await ctx.run('admin.import_old', { state });
        if (!res.ok) return;
        const got = res.imported || (res.notes && res.notes.imported) || [];
        done.hidden = false;
        fill(done, h('p', { class: 'ops-note gold' }, '✅ 옮겼어요: ', h('b', null, got.join(' · ') || '(알 수 없음)')));
        ctx.toast('📦 옛 설정을 옮겼어요', 'ok');
    }

    return { render() {} };
}
