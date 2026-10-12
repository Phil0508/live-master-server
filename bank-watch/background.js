/* 🏦 엔젤 입금확인 — 방송 서버로 보내는 곳(확장의 배경, 0.2 · 2026-10-13).
 *
 * 왜 따로 있나: 은행 화면 쪽(content.js)은 남의 사이트 안이라 우리 서버로 바로 못 보낸다(브라우저 CORS).
 *   확장의 배경은 manifest 의 host_permissions 에 적힌 주소로만 보낼 수 있다.
 * ⚠️ 보내는 곳은 방송 서버(엔젤컴퍼니.메인.한국)와 내 PC 시험 서버(127.0.0.1 · localhost)뿐 — 다른 주소는 거절한다.
 * ⚠️ 서버가 받는 것은 '추천 카드' 뿐이다. 송출 · 장부 · 점수는 대표님이 후원 콘솔에서 눌러야 간다.
 * 못 보낸 입금은 확장 저장소(aw-q)에 쌓아 두고, 다음 신호(30초마다) 때 다시 보낸다. 같은 입금(ref)은 서버가 한 번만 받는다.
 */
const PROD = 'https://xn--9i1b547a0ublxlz4f.xn--h32bi4v.xn--3e0b707e';   // 엔젤컴퍼니.메인.한국
const LINK = 'aw-link';
const QUEUE = 'aw-q';
const QMAX = 200;
const BATCH = 30;

function allowed(url) {
  try {
    const u = new URL(url);
    if (u.origin === PROD) return true;
    return u.protocol === 'http:' && (u.hostname === '127.0.0.1' || u.hostname === 'localhost');
  } catch (e) {
    return false;
  }
}

function mergeQueue(q, deposits) {
  const out = (q || []).slice();
  for (const d of deposits || []) {
    if (d && d.ref && !out.some((x) => x.ref === d.ref)) out.push(d);
  }
  return out.slice(-QMAX);
}

if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
  const get = (k) => new Promise((r) => chrome.storage.local.get(k, (o) => r(o && o[k])));
  const set = (o) => new Promise((r) => chrome.storage.local.set(o, () => r()));

  async function flush(msg) {
    const link = Object.assign({ server: PROD, key: '' }, await get(LINK));
    let q = mergeQueue(await get(QUEUE), msg.deposits);
    await set({ [QUEUE]: q });
    if (!link.key) return { ok: false, why: 'nokey', queued: q.length };
    if (!allowed(link.server)) return { ok: false, why: 'server', queued: q.length };
    const batch = q.slice(0, BATCH);
    try {
      const r = await fetch(link.server.replace(/\/+$/, '') + '/api/bank/deposit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Bank-Key': link.key },
        body: JSON.stringify({ source: 'web', deposits: batch, note: String(msg.note || '').slice(0, 60) }),
      });
      if (r.status === 401) return { ok: false, why: 'key', queued: q.length };
      if (!r.ok) return { ok: false, why: 'http', code: r.status, queued: q.length };
      const sent = new Set(batch.map((d) => d.ref));
      q = ((await get(QUEUE)) || []).filter((d) => !sent.has(d.ref));
      await set({ [QUEUE]: q });
      return { ok: true, queued: q.length, at: Date.now() };
    } catch (e) {
      return { ok: false, why: 'net', queued: q.length };
    }
  }

  // 한 번에 하나씩 — 두 틀이 동시에 보내도 대기줄이 꼬이지 않게
  let chain = Promise.resolve();
  chrome.runtime.onMessage.addListener((msg, sender, reply) => {
    if (!msg || msg.t !== 'aw-send') return false;
    chain = chain.then(() => flush(msg)).then(reply, () => reply({ ok: false, why: 'err' }));
    return true;   // 답은 나중에 준다
  });
}

if (typeof module !== 'undefined') module.exports = { allowed, mergeQueue, PROD };
