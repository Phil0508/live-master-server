/* 🎵 시그니처 관리 탭이 같이 쓰는 도구 — 주소 부르기 · 숫자 · 파일 검사.
   서버: v2/server/domain/sigadmin.py (옛 /api/signatures/add · update/{id} · delete/{id} 와 같은 모양)
   ⚠️ 바깥 글자(제목 · 파일 이름)는 h()/textContent 로만 넣는다 — innerHTML 금지. */
import { h, num, won, clock } from '../../util.js';

export { h, num, won, clock };

// 서버 sigadmin.py 와 같은 값
export const MAX_MB = 80;
export const DUR_MIN = 1, DUR_MAX = 600, DUR_DEFAULT = 10;
export const SIG_ROUND_FLOOR = 10000;              // 시그니처 최저선은 1만 원을 못 넘는다(서버 rules.SIG_ROUND_FLOOR)
export const AUDIO_EXT = ['mp3', 'm4a', 'aac', 'ogg', 'oga', 'wav', 'webm', 'mp4', 'flac', 'opus'];
export const IMAGE_EXT = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif'];

/** '12,000' · ' 5000원 ' → 12000. 정수가 아니면 null */
export function parseWon(s) {
    const t = String(s == null ? '' : s).trim().replace(/[,\s원₩]/g, '');
    if (!/^\d{1,9}$/.test(t)) return null;
    return parseInt(t, 10);
}

export const extOf = name => { const n = String(name || ''); return n.includes('.') ? n.split('.').pop().toLowerCase() : ''; };

/** 파일 검사 — 서버와 같은 규칙. 괜찮으면 '' · 아니면 까닭 */
export function checkImage(f) {
    if (!f) return '';
    if ((f.type || '').startsWith('image/') || IMAGE_EXT.includes(extOf(f.name))) return '';
    return `사진 파일이 아니에요 (png · jpg · gif · webp): ${f.name}`;
}
export function checkSound(f) {
    if (!f) return '';
    if (AUDIO_EXT.includes(extOf(f.name)) || (f.type || '').startsWith('audio/')) return '';
    return `음원 파일이 아니에요 (mp3 · m4a · wav · ogg · aac): ${f.name}`;
}

/** 바이트 → '3.2MB' · 작으면 '84KB' */
export const mb = n => {
    const b = Number(n || 0);
    return b < 1024 * 1024 ? Math.max(1, Math.round(b / 1024)) + 'KB' : (b / 1024 / 1024).toFixed(1) + 'MB';
};

/** GET · JSON POST — 답은 {ok, status, data, error} */
export async function call(path, body) {
    try {
        const init = { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', headers: {} };
        if (body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
        const r = await fetch(path, init);
        const data = await r.json().catch(() => ({}));
        const ok = r.ok && (data.ok === true || data.status === 'success');
        return { ok, status: r.status, data, error: ok ? '' : (data.message || data.error || ('실패했어요 (' + r.status + ')')) };
    } catch (e) {
        return { ok: false, status: 0, data: {}, error: '서버에 닿지 않아요 — 다시 눌러 주세요' };
    }
}

/** 파일 올리기(form) — fetch 는 올리는 진행을 못 본다. XHR 로 몇 % 인지 onProgress(0~100) 로 알려 준다 */
export function upload(path, fd, onProgress) {
    return new Promise(resolve => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', path);
        xhr.withCredentials = true;
        xhr.upload.onprogress = e => { if (e.lengthComputable && onProgress) onProgress(Math.round(e.loaded / e.total * 100)); };
        xhr.onload = () => {
            let data = {};
            try { data = JSON.parse(xhr.responseText || '{}'); } catch (e) { data = {}; }
            const ok = xhr.status >= 200 && xhr.status < 300 && (data.ok === true || data.status === 'success');
            resolve({ ok, status: xhr.status, data, error: ok ? '' : (xhr.status === 401 ? '로그인이 풀렸어요 — 새로 고쳐 다시 들어가 주세요'
                : (data.message || data.error || ('실패했어요 (HTTP ' + xhr.status + ')'))) });
        };
        xhr.onerror = () => resolve({ ok: false, status: 0, data: {}, error: '서버에 닿지 않아요 — 다시 눌러 주세요' });
        xhr.send(fd);
    });
}

/** 단추 하나를 '보내는 중' 으로 묶는다 — 두 번 눌러도 한 번만 */
export async function once(btn, fn) {
    if (!btn || btn.dataset.busy) return undefined;
    btn.dataset.busy = '1';
    btn.classList.add('wait');
    btn.setAttribute('aria-busy', 'true');
    try { return await fn(); } finally {
        delete btn.dataset.busy;
        btn.classList.remove('wait');
        btn.removeAttribute('aria-busy');
    }
}

/** 한글 입력 중(조합 중) Enter 는 무시 */
export function onEnter(input, fn) {
    input.addEventListener('keydown', e => {
        if (e.key !== 'Enter' || e.isComposing || e.keyCode === 229) return;
        e.preventDefault();
        fn(e);
    });
}

/** 시그니처 한 줄 → '#12 사쿠란보 · 10,300원' */
export const label = s => `#${s.id} ${s.title || '시그니처'} · ${num(s.amount)}원`;
