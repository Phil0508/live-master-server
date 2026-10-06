/* 🧭 머리줄 — 연결 상태 · 방송 중 표시(언제부터) · [방송 끝].
   [방송 끝] 은 점수판 · 대기함 · 시그니처 대기줄을 비운다(서버 session.end) → 화면 안 확인 상자로 한 번 묻는다.
   더해 붙는 것
     · 상태 점 [방송 화면] [후원 받기] · 방송 중 경보 띠(머리줄 맨 아래) · 방송 전 점검표 — alarm.js (소리는 안 낸다)
     · BGM 미니 플레이어(영상이 올라와 있을 때만) — panels/records/bgm.js
     · 💰 이번 방송 후원 칸 — panels/ai/today.js · 🚗 오토파일럿 띠(켜져 있을 때 머리줄 맨 아래) — panels/ai/autopilot.js
     · ✂ 클립 단추 + OBS 점 — clipbtn.js(방송 중에만) */
import { clock } from './util.js';
import { mountAlarm } from './alarm.js';
import { mountBgmMini } from './panels/records/bgm.js';
import { mountTodayPill } from './panels/ai/today.js';   // 💰 이번 방송 후원(장부에서 센 것) — 옛 첫 화면 숫자 칸
import { mountClipButton } from './clipbtn.js';            // ✂️ 어느 탭에서든 클립(옛 머리줄 단추)

const CONN = {
    connecting: ['connecting', '연결 중'],
    live: ['live', '연결됨'],
    down: ['down', '끊김 · 다시 붙는 중'],
};

export function mountHeader(root, ctx) {
    root.innerHTML = `
        <div class="brand"><span class="logo" aria-hidden="true"></span><b>라이브 마스터</b><span class="brand-sub">조종실</span></div>
        <div class="hdr-right">
            <span class="pill conn" data-s="connecting" title="서버와의 실시간 연결"><i aria-hidden="true"></i><span class="t">연결 중</span></span>
            <span class="pill onair" hidden><i aria-hidden="true"></i><span class="t">방송 중</span><span class="since"></span></span>
            <button class="btn danger end-btn" type="button" hidden>방송 끝</button>
        </div>`;
    const conn = root.querySelector('.conn');
    const onair = root.querySelector('.onair');
    const since = root.querySelector('.since');
    const endBtn = root.querySelector('.end-btn');
    const right = root.querySelector('.hdr-right');
    const alarm = mountAlarm(right, root, ctx);           // 점 두 개는 오른쪽 묶음 바로 앞(폰에서는 로고 줄)
    const bgm = mountBgmMini(right);
    const todayPill = mountTodayPill(onair);               // [방송 중] 바로 앞 · 폰에서는 숨긴다(AI 탭에 같은 숫자)
    const clipBtn = mountClipButton(right, ctx);           // 오른쪽 묶음 맨 앞 · 방송 중에만
    // 🧪 시험판(서버 LM2_TRIAL) — 옛 프로그램과 같이 쓰는 기능(시그니처 보관소 · 리스너 설정 · 서버 버전)이 잠겨 있다는 표시
    fetch('/api/health', { cache: 'no-store' }).then(r => r.json()).then(hh => {
        if (!hh || !hh.trial) return;
        const t = document.createElement('span');
        t.className = 'pill trial';
        t.title = '시험판 — 지금 방송 중인 옛 프로그램과 같이 쓰는 것(시그니처 등록 · 지우기, 투네이션 테스트 계정, 서버 버전 바꾸기)은 잠가 뒀어요. 나머지는 마음껏 눌러 보셔도 돼요.';
        t.textContent = '🧪 시험판';
        root.querySelector('.brand').append(t);
    }).catch(() => {});
    let startedAt = 0, busy = false;

    endBtn.addEventListener('click', async () => {
        if (busy) return;
        const s = ctx.slices;
        const pend = (s.pending || []).length;
        const q = ((s.queue || {}).items || []).length;
        const lines = ['점수판 · 기록이 비워지고, 방송판의 점수도 0 으로 돌아갑니다.'];
        if (pend) lines.push(`⚠️ 대기함에 아직 ${pend}건이 남아 있어요 — 끝내면 대기함에서 사라집니다(후원 기록 장부에는 남아요).`);
        if (q) lines.push(`시그니처 대기줄 ${q}개도 멈추고 비워집니다.`);
        const ok = await ctx.confirm({ title: '방송을 끝낼까요?', body: lines.join('\n'), ok: '방송 끝내기', cancel: '계속 방송' });
        if (!ok) return;
        busy = true;
        endBtn.disabled = true;
        const res = await ctx.run('session.end', {});
        busy = false;
        endBtn.disabled = false;
        if (res.ok) ctx.toast('방송을 끝냈어요. 수고하셨습니다!', 'ok');
    });

    function tick() {
        if (!startedAt) { since.textContent = ''; return; }
        const min = Math.max(0, Math.floor((Date.now() / 1000 - startedAt) / 60));
        const dur = min >= 60 ? `${Math.floor(min / 60)}시간 ${min % 60}분째` : `${min}분째`;
        since.textContent = ` · ${clock(startedAt)} 시작 · ${dur}`;
    }

    return {
        render(slices, status, view) {
            const [cls, label] = CONN[status] || CONN.connecting;
            if (conn.dataset.s !== cls) {
                conn.dataset.s = cls;
                conn.querySelector('.t').textContent = label;
            }
            const sess = slices.session || {};
            const live = !!sess.live && view !== 'login';
            onair.hidden = !live;
            endBtn.hidden = !(live && view === 'live');
            const want = live ? (Number(sess.started_at) || 0) : 0;
            if (want !== startedAt) { startedAt = want; tick(); }
            // 하나가 넘어져도 머리줄(연결 · 방송 끝)은 그대로 돌게 따로 감싼다
            try { alarm.render(slices, status, view); } catch (e) { console.error('[점검]', e); }
            try { bgm.render(slices, view); } catch (e) { console.error('[BGM]', e); }
            try { todayPill.render(slices, view); } catch (e) { console.error('[오늘 후원]', e); }
            try { clipBtn.render(slices, view); } catch (e) { console.error('[클립 단추]', e); }
        },
        tick,
    };
}

