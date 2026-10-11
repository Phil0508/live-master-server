/* 🏦 엔젤 입금확인 — 은행 화면 쪽(MAIN world)에 붙는 작은 고리.
 *
 * 왜 필요한가: 자동 조회 중에 은행이 alert('조회내역이 없습니다') 같은 창을 띄우면
 *   그 창을 누가 닫기 전까지 화면 전체가 멈춘다(우리 타이머까지 같이 멈춘다).
 *   그래서 **자동 조회가 켜져 있을 때만** alert 를 막지 않고 기록으로 돌린다.
 *   confirm 은 '연장' 을 묻는 것만 '예' 로 답하고, 나머지는 원래대로 사람에게 묻는다.
 * ⚠️ 켜짐 표시는 content.js 가 <html data-aw-on="1"> 로 알려 준다(서로 다른 세계라 변수를 못 나눈다).
 * ⚠️ 은행 쪽 변수 · 함수는 읽지도 바꾸지도 않는다. alert · confirm 두 개만 감싼다.
 */
(() => {
  if (window.__awHooked) return;
  window.__awHooked = true;
  const on = () => document.documentElement && document.documentElement.getAttribute('data-aw-on') === '1';
  const tell = (kind, msg) => {
    try { window.postMessage({ __aw: kind, msg: String(msg == null ? '' : msg).slice(0, 300) }, '*'); } catch (e) {}
  };
  const origAlert = window.alert;
  const origConfirm = window.confirm;
  window.alert = function (msg) {
    if (on()) { tell('alert', msg); return undefined; }
    return origAlert.apply(this, arguments);
  };
  window.confirm = function (msg) {
    if (on() && /연장/.test(String(msg || ''))) { tell('confirm-yes', msg); return true; }
    if (on()) tell('confirm', msg);
    return origConfirm.apply(this, arguments);
  };
})();
