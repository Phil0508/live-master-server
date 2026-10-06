/* 🎤 노래방 — karaoke 조각(on · video · at). 옛 updateKaraoke 그대로.
   - 켜져 있고 영상이 있으면 유튜브(inst) 영상을 큰 화면(40,560 · 1000×563)에 띄운다. 금테 · 검은 바탕.
   - 영상이 **바뀔 때만** iframe 을 새로 만든다(조각이 올 때마다 처음으로 튀지 않게). 꺼지면 iframe 을 지워 소리까지 멈춘다.
   - 이건 상태다(알림이 아니다) — 방송판을 새로 열어도 켜져 있으면 다시 뜬다(옛 것과 같다).
   - 소리: 준비되기 전 명령은 버려지므로 unMute + setVolume 을 0.5초 × 8번 보낸다. 크기는 karaoke.volume(0~100, 없으면 70 — 옛 기본값).
   - video 는 유튜브 번호 또는 주소(조종실이 붙여 넣은 링크) — 번호만 뽑는다.
   - ?monitor=1(미리보기)은 mute=1 로 소리 없이. */
import { youtubeId } from './acct-video.js';
import { isLeader } from '../../audio_lead.js';   // 🔊 방송판이 여러 개면 소리는 담당 창 하나만

function clampVol(v) {
    const n = Math.round(Number(v));
    if (!isFinite(n)) return 70;
    return Math.max(0, Math.min(100, n));
}

export function mount(root, lm, opts) {
    const MON = !!opts.monitor;
    root.innerHTML = '<div class="kr-box"><div class="kr-frame"></div></div>';
    const box = root.firstElementChild;
    const frame = root.querySelector('.kr-frame');
    let curId = null, volWanted = 70, volApplied = null, volTimer = null;

    function cmd(func, args) {
        const f = frame.querySelector('iframe');
        if (!f || !f.contentWindow) return;
        try { f.contentWindow.postMessage(JSON.stringify({ event: 'command', func, args: args || [] }), 'https://www.youtube.com'); } catch (e) {}
    }

    function off() {
        if (curId === null) return;
        curId = null;
        volApplied = null;
        clearInterval(volTimer); volTimer = null;
        frame.innerHTML = '';                      // iframe 제거 → 재생 · 소리 완전 정지
        box.classList.remove('on');
    }

    lm.on('karaoke', k => {
        k = k || {};
        const id = k.on ? youtubeId(k.video) : '';
        if (!id) {
            if (k.on && k.video) console.warn('[노래방] 유튜브 링크를 못 읽었습니다:', k.video);
            off();
            return;
        }
        volWanted = clampVol(k.volume !== undefined ? k.volume : 70);
        if (curId !== id) {
            curId = id;
            volApplied = null;
            let src = 'https://www.youtube.com/embed/' + encodeURIComponent(id)
                + '?autoplay=1&rel=0&modestbranding=1&playsinline=1&fs=0&enablejsapi=1' + (MON || !isLeader() ? '&mute=1' : '');
            // origin 은 http(s) 로 서비스될 때만 — file:// 이면 'null' 이 되어 임베드가 거부된다
            if (location.protocol === 'http:' || location.protocol === 'https:') src += '&origin=' + encodeURIComponent(location.origin);
            frame.innerHTML = '<iframe width="100%" height="100%" src="' + src
                + '" frameborder="0" allow="autoplay; encrypted-media" allowfullscreen style="border:0;display:block;"></iframe>';
            box.classList.add('on');
            if (MON || !isLeader()) return;          // 담당 창이 아니면 소리를 안 켠다
            clearInterval(volTimer);
            let tries = 0;
            volTimer = setInterval(() => {
                cmd('unMute');
                cmd('setVolume', [volWanted]);
                volApplied = volWanted;
                if (++tries >= 8) { clearInterval(volTimer); volTimer = null; }
            }, 500);
            return;
        }
        if (!MON && isLeader() && volWanted !== volApplied) { volApplied = volWanted; cmd('setVolume', [volWanted]); }
    });
}
