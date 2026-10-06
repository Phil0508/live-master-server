/* 🎞️ 계좌 고액후원 영상 — acct_video 조각의 now {video, label, at}. 옛 acctVideoPlay / acctVideoPlayFile 그대로.
   - 운영자가 금액대를 골라 틀면(acctvid.play) 화면 가운데 큰 영상 상자(1280×720 × 0.84)에 튼다. 화면 전체를 덮지 않는다
     (옛 사고: 1920×1080 검은 바탕으로 깔아 시그니처까지 가렸다). 시그니처 · 후원 알림은 영상 위에 뜬다(층 표).
   - video 가 유튜브 번호(11자)거나 유튜브 주소면 유튜브로, http(s) · / 로 시작하는 그 밖의 주소면 영상 파일(<video>)로.
     파일은 광고 · 추천 · 로고가 없고 끝(onended)을 확실히 안다.
   - 끝나면(유튜브 ENDED · 파일 onended) · 실패하면(파일 onerror · 유튜브 onError) · 20분 안전장치가 울리면 내리고
     서버에 알린다: lm.cmd('acctvid.ended', {at}) — 서버는 지금 그 영상(at)일 때만 내린다(다른 방송판이 늦게 알려도 안전).
   - ?monitor=1(미리보기)은 소리 없이(muted · mute=1) 틀고, 끝났다고 알리지 않는다(방송판 OBS 한 곳만 알린다).
   - 붙은 직후 통째로 받은 것은 30초 안의 것만 튼다(다시 붙었을 때 지난 영상이 처음부터 다시 나오지 않게).
   - 노래방도 유튜브 iframe 이라 상태 메시지를 받으면 **보낸 iframe 이 내 것인지** 대조한다(노래방 곡이 끝났다는 신호에 영상이 잘리지 않게). */

import { isLeader } from '../../audio_lead.js';   // 🔊 방송판이 여러 개면 소리는 담당 창 하나만
const SAFETY_MS = 20 * 60 * 1000;

export function youtubeId(v) {
    const t = String(v || '').trim();
    if (/^[A-Za-z0-9_-]{11}$/.test(t)) return t;
    const m = t.match(/(?:youtu\.be\/|youtube(?:-nocookie)?\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/|live\/|v\/))([A-Za-z0-9_-]{11})/);
    return m ? m[1] : '';
}

function isFile(v) {
    const t = String(v || '').trim();
    return /^https?:\/\//i.test(t) || t.startsWith('/');
}

export function mount(root, lm, opts) {
    const MON = !!opts.monitor;
    root.innerHTML = '<div class="av-box"><div class="av-frame"></div></div>';
    const box = root.firstElementChild;
    const frame = root.querySelector('.av-frame');
    let playingAt = 0, safety = null, kick = null, seenAt = 0;

    function stop() {
        clearTimeout(safety); safety = null;
        clearInterval(kick); kick = null;
        // ⚠️ <video> 는 지우기 전에 멈춰 둔다. 요소만 떼면 브라우저에 따라 소리가 남는다
        const v = frame.querySelector('video');
        if (v) { try { v.pause(); v.removeAttribute('src'); v.load(); } catch (e) {} }
        frame.innerHTML = '';                       // iframe/video 제거 → 재생 · 소리 완전 정지
        box.classList.remove('on');
        if (playingAt) opts.stage.setMode('acctvideo', false);
        playingAt = 0;
    }

    function finished(why) {
        const at = playingAt;
        if (!at) return;
        stop();
        if (MON) return;
        Promise.resolve(lm.cmd('acctvid.ended', { at })).then(r => {
            if (r && r.ok === false) console.warn('[고액후원 영상] 끝 알림 실패:', r.error);
        }).catch(() => {});
        console.log('[고액후원 영상] 끝 — ' + why);
    }

    function playYoutube(id) {
        let src = 'https://www.youtube.com/embed/' + encodeURIComponent(id)
            + '?autoplay=1&rel=0&modestbranding=1&playsinline=1&fs=0&enablejsapi=1' + (MON || !isLeader() ? '&mute=1' : '');
        if (location.protocol === 'http:' || location.protocol === 'https:') src += '&origin=' + encodeURIComponent(location.origin);
        frame.innerHTML = '<iframe width="100%" height="100%" src="' + src
            + '" frameborder="0" allow="autoplay; encrypted-media" allowfullscreen style="border:0;display:block;"></iframe>';
        // 유튜브가 상태 메시지를 보내오도록 '듣기 시작' 신호를 몇 번(준비 전 명령은 버려진다)
        let tries = 0;
        kick = setInterval(() => {
            const f = frame.querySelector('iframe');
            if (f && f.contentWindow) {
                try { f.contentWindow.postMessage(JSON.stringify({ event: 'listening', id }), 'https://www.youtube.com'); } catch (e) {}
            }
            if (++tries >= 8) { clearInterval(kick); kick = null; }
        }, 500);
    }

    function playFile(url) {
        const v = document.createElement('video');
        v.src = url;
        v.autoplay = true;
        v.playsInline = true;
        v.controls = false;
        v.preload = 'auto';
        if (MON || !isLeader()) v.muted = true;    // 🔇 폰으로 들여다보는 창 · 소리 담당이 아닌 창에서 소리가 터지지 않게
        v.onended = () => finished('다 틀었다');
        v.onerror = () => { console.warn('[고액후원 영상] 재생 실패 —', url); finished('재생 실패'); };
        frame.appendChild(v);
        // ⚠️ 일반 브라우저는 소리 있는 자동재생을 막는다 — 막히면 음소거로라도(OBS 는 열려 있어 실제 방송에선 소리가 난다)
        const p = v.play();
        if (p && p.catch) {
            p.catch(() => {
                if (!v.isConnected) return;         // 이미 내렸다(실패 · 멈춤) — 다시 틀 것이 없다
                v.muted = true;
                v.play().catch(e => { console.warn('[고액후원 영상] 음소거 재생도 실패:', e); finished('재생 실패'); });
            });
        }
    }

    function play(now) {
        stop();
        const video = String(now.video || '').trim();
        const yid = youtubeId(video);
        if (!yid && !isFile(video)) { console.warn('[고액후원 영상] 알 수 없는 영상:', video); return; }
        playingAt = Number(now.at) || 0;
        box.classList.add('on');
        opts.stage.setMode('acctvideo', true);
        if (yid) playYoutube(yid); else playFile(video);
        // 안전장치: 끝 감지를 놓쳐 영상이 화면에 눌러앉지 않게(최대 20분)
        safety = setTimeout(() => finished('20분 안전장치'), SAFETY_MS);
    }

    lm.on('acct_video', av => {
        const now = av && av.now;
        if (!now || !now.video) { if (playingAt) stop(); return; }
        const at = Number(now.at) || 0;
        if (at === playingAt) return;              // 같은 영상 — 다시 붙었을 때 처음부터 다시 틀지 않는다
        if (at === seenAt) return;
        seenAt = at;
        if (!opts.isFresh(at)) { if (playingAt) stop(); return; }
        try { play(now); } catch (e) { console.error('[고액후원 영상] 틀기 실패:', e); stop(); }
    });

    // 유튜브 상태 메시지 — ENDED(0) · onError 면 내린다. 내 iframe 에서 온 것만.
    window.addEventListener('message', e => {
        if (typeof e.origin === 'string' && e.origin.indexOf('youtube.com') === -1) return;
        const mine = frame.querySelector('iframe');
        if (!mine || !e.source || e.source !== mine.contentWindow) return;
        let data = e.data;
        if (typeof data === 'string') { try { data = JSON.parse(data); } catch (err) { return; } }
        if (!data || typeof data !== 'object') return;
        const info = data.info;
        const state = (info && typeof info === 'object') ? info.playerState : (typeof info === 'number' ? info : undefined);
        if (data.event === 'onStateChange' && data.info === 0) finished('유튜브 끝');
        else if (data.event === 'infoDelivery' && state === 0) finished('유튜브 끝');
        else if (data.event === 'onError') finished('유튜브 오류 ' + JSON.stringify(info));
    });
}
