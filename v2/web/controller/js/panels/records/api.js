/* 📡 장부 · 기록 읽기 — GET 만 한다(로그인 쿠키). 실패하면 까닭 글자를 던진다. */

export async function getJSON(path) {
    let r;
    try {
        r = await fetch(path, { cache: 'no-store', credentials: 'same-origin' });
    } catch (e) {
        throw new Error('서버에 닿지 않아요 — 잠시 뒤 다시 눌러 주세요');
    }
    if (r.status === 401) throw new Error('로그인이 풀렸어요 — 새로 고쳐 다시 들어가 주세요');
    let j = null;
    try { j = await r.json(); } catch (e) { j = null; }
    if (!r.ok || !j || j.status === 'error' || j.ok === false) {
        throw new Error((j && (j.message || j.error)) || ('서버가 ' + r.status + ' 로 답했어요'));
    }
    return j;
}

/** 방송 회차 번호 '20261007-2030-ab12' → '10월 7일 (수) 20:30' · 빈 회차 → '방송 밖' */
export function sessionLabel(id, firstAt) {
    const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(String(id || ''));
    let d = null;
    if (m) d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
    else if (firstAt) d = new Date(Number(firstAt) * 1000);
    if (!id) return '방송 밖(시작 전 · 끝난 뒤)';
    if (!d || isNaN(d)) return String(id);
    const wd = '일월화수목금토'[d.getDay()];
    const p = x => String(x).padStart(2, '0');
    return `${d.getMonth() + 1}월 ${d.getDate()}일 (${wd}) ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 초 → '20:31:05' */
export function hms(at) {
    const n = Number(at) || 0;
    if (!n) return '';
    const d = new Date(n < 1e12 ? n * 1000 : n);
    const p = x => String(x).padStart(2, '0');
    return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}
