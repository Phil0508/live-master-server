// ==UserScript==
// @name         🎯 투네이션 마스터 V11.4 (실시간 정밀 디버깅 로그 탑재)
// @namespace    http://tampermonkey.net/
// @version      11.4
// @description  시그니처 및 일반 캐시 후원 감지 시 디버그 로그를 상세히 출력하여 인식이 안 되는 구간을 명확히 추적합니다.
// @match        https://toon.at/widget/alertbox/0ff7d51634720c364b007009dd564dff*
// @noframes
// @grant        GM_xmlhttpRequest
// @connect      live-master-server.onrender.com
// @connect      127.0.0.1
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    if (window !== window.parent) {
        return;
    }

    // 💡 [성능 최적화] 디버그 모드가 켜져 있을 때만 콘솔에 상세 로그를 출력합니다.
    // 콘솔 로그가 과도하게 쌓여 탭이 느려지는 현상을 막기 위해 기본값은 false(비활성화)입니다.
    const DEBUG_LOG = false; 

    function log(...args) {
        if (DEBUG_LOG) {
            console.log(...args);
        }
    }

    console.log("🎯 [투네이션 마스터] V11.4 (상세 로그 비활성화 모드 - 서버 전송 결과만 기록) 가동 완료!");

    let lastSentState = "";      
    let lastFilteredState = "";  
    let sendingState = "";       
    let lastLoggedLockState = ""; // 콘솔 로그 도배 방지용 변수
    
    let lastSeenState = "";      
    let stableTicks = 0;         

    setInterval(() => {
        // 1. 필요한 DOM 요소 추출
        const animTextsRaw = Array.from(document.querySelectorAll('.template-animated-text')).map(el => el.innerText.trim());
        const titleEl = document.querySelector('.title-name-effect');
        const titleText = titleEl ? titleEl.innerText.trim() : "";

        // [등급 제외 필터] 노블레스 등급 명칭(예: "그린노블레스")이 텍스트 목록에 포함되어 있다면 이를 제외하고 실제 닉네임과 상품명만 남깁니다.
        const animTexts = animTextsRaw.filter(txt => txt && txt !== titleText);

        const sigCashEl = document.querySelector('.signature-amount') || document.querySelector('[class*="SignatureCash"]') || document.querySelector('[class*="signature-cash"]');
        const sigCashText = sigCashEl ? sigCashEl.innerText.trim() : "";

        // 텍스트 영역이 감지되었을 때 디버깅 로그 출력
        if (animTexts.length > 0) {
            log(`🔍 [감지 로그] 텍스트 노드 개수: ${animTexts.length} | 시그니처 돔 존재: ${!!sigCashEl} ("${sigCashText}")`);
            log(`  ▶ 텍스트 목록:`, animTexts);
        } else {
            // 💡 [락 자동 해제] 화면에 알림창이 닫혀 텍스트가 감지되지 않으면 이전 후원 상태 캐시를 클리어합니다.
            // 이를 통해 완전히 동일한 후원이 연달아 오더라도 차단되지 않고 정상 전송됩니다.
            if (lastSentState !== "") {
                log("  🔓 [락 해제] 알림창이 닫혔으므로 이전 전송 상태 락을 초기화합니다.");
                lastSentState = "";
                lastFilteredState = "";
                sendingState = "";
                lastLoggedLockState = "";
                lastSeenState = "";
                stableTicks = 0;
            }
            return;
        }

        // 2. 시그니처 후원 텍스트 패턴 판별 (예: '홍길동님이 "시그니처1"을 신청하셨어요')
        const signatureRegex = /^(.+?)님이\s+["'“]?(.*?)["'”?]?(?:을|를)\s+신청하셨어요/;
        let isSignature = false;
        let sigName = "";
        let sigProduct = "";
        let matchedAnimText = "";

        // 방법 A: 돔(DOM)에 시그니처 금액란(.signature-amount)이 존재하는 경우 (가장 확실함)
        if (sigCashEl) {
            isSignature = true;
            if (animTexts.length >= 2) {
                sigName = animTexts[0].trim();
                sigProduct = animTexts[1].trim();
            } else if (animTexts.length === 1) {
                sigName = animTexts[0].trim();
                sigProduct = "시그니처";
            }
        } else {
            // 방법 B: 정규식을 통한 폴백 판정
            for (const txt of animTexts) {
                if (signatureRegex.test(txt)) {
                    const match = txt.match(signatureRegex);
                    sigName = match[1].trim();
                    sigProduct = match[2].trim();
                    isSignature = true;
                    matchedAnimText = txt;
                    break;
                }
            }
        }

        let name = "";
        let amountText = "";

        if (isSignature) {
            name = sigName;
            if (sigCashText) {
                amountText = sigCashText;
            } else {
                const otherTexts = animTexts.filter(t => t !== matchedAnimText);
                amountText = otherTexts.length > 0 ? otherTexts[0] : "";
            }
            log(`  ⭐ [시그니처 판정] 이름: ${name} | 금액 텍스트 후보: ${amountText} | 상품명: ${sigProduct}`);
        } else {
            // 일반 후원 파싱 로직 (최소 2개 이상의 텍스트가 존재해야 함)
            if (animTexts.length < 2) {
                log(`  ⚠️ [일반 후원 대기] 텍스트가 2개 미만이라 파싱을 보류합니다.`);
                return;
            }
            const t1 = animTexts[0];
            const t2 = animTexts[1];

            const isNumericAmount = (str) => {
                const cleaned = str.replace(/[\s,원₩$]/g, '');
                return cleaned.length > 0 && /^\d+$/.test(cleaned);
            };

            if (isNumericAmount(t1) && !isNumericAmount(t2)) {
                amountText = t1;
                name = t2;
            } else if (isNumericAmount(t2) && !isNumericAmount(t1)) {
                amountText = t2;
                name = t1;
            } else {
                const numDigits = (str) => (str.match(/\d/g) || []).length;
                if (numDigits(t1) > numDigits(t2)) {
                    amountText = t1;
                    name = t2;
                } else {
                    name = t1;
                    amountText = t2;
                }
            }
            log(`  👤 [일반 후원 판정] 이름 후보: ${name} | 금액 후보: ${amountText}`);
        }

        let amount = parseInt(amountText.replace(/[^\d]/g, '')) || 0;

        // [신규] 만약 금액 자리에 숫자가 전혀 없는 텍스트(예: "닭비트")가 들어왔다면 이를 0원짜리 시그니처 신청으로 우회 판정합니다.
        let isZeroAmountSignature = false;
        let zeroAmountSigProduct = "";
        if (amount === 0 && amountText && !/\d/.test(amountText)) {
            isZeroAmountSignature = true;
            zeroAmountSigProduct = amountText.trim();
        }

        // 4. 메시지 파싱
        let message = "";
        const msgSpan = document.querySelector('.template-content span') || document.querySelector('.text-content span');
        if (msgSpan) {
            message = msgSpan.innerText.trim();
        }

        if (isSignature && sigProduct) {
            message = `[시그니처 신청: ${sigProduct}]` + (message ? ` ${message}` : "");
        } else if (isZeroAmountSignature && zeroAmountSigProduct) {
            message = `[시그니처 신청: ${zeroAmountSigProduct}]` + (message ? ` ${message}` : "");
        }

        log(`  📝 [최종 파싱 데이터] 이름: ${name} | 금액: ${amount}원 | 메시지: "${message}"`);

        // 금액이 0원 이하이더라도 시그니처 신청인 경우 통과시킵니다.
        if (!name || (amount <= 0 && !isZeroAmountSignature)) {
            log(`  ❌ [데이터 오류] 금액 또는 이름이 올바르지 않아 중단합니다.`);
            return;
        }

        const currentTextState = `${name}_${amount}_${message}`;

        // 5. 전송 락 및 중복 정산 검증 (메모리 락 검사)
        if (currentTextState === lastSentState || currentTextState === lastFilteredState || currentTextState === sendingState) {
            if (lastLoggedLockState !== currentTextState) {
                log(`  🔒 [락 검증] 이미 처리되었거나 처리 중인 상태입니다. 무시합니다. (State: ${currentTextState})`);
                lastLoggedLockState = currentTextState;
            }
            return;
        }

        // 6. 애니메이션/타이프라이터 텍스트 안정화 검증 (Debounce)
        if (currentTextState === lastSeenState) {
            stableTicks += 1;
            log(`  ⏳ [안정화 진행 중] 동일 상태 유지 틱: ${stableTicks}/5`);
        } else {
            stableTicks = 0; 
            lastSeenState = currentTextState;
            log(`  🔄 [상태 변화 감지] 새로운 상태로 틱 초기화: ${currentTextState}`);
        }

        if (stableTicks < 5) {
            return; 
        }

        // 7. 후원 필터링 (1만원 미만 무시 - 단, 시그니처 신청은 0원이라도 필터 통과)
        const isSig = isSignature || isZeroAmountSignature;
        if (!isSig && amount < 10000) {
            log(`  🗑️ [필터 컷] 1만원 미만 후원은 서버로 전송하지 않고 필터 락 처리합니다. (금액: ${amount}원)`);
            lastFilteredState = currentTextState; 
            return;
        }

        // 8. 서버로 비동기 후원 접수 전송
        sendingState = currentTextState;
        console.log(`  📡 [서버 전송 트리거] ${name}님 ${amount}원 전송 프로세스 가동`);

        const sendDonation = () => {
            const txId = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : (Math.random().toString(36).substring(2) + Date.now().toString(36));
            GM_xmlhttpRequest({
                method: "POST",
                url: "https://live-master-server.onrender.com/api/donation",
                headers: { 
                    "Content-Type": "application/json",
                    "Authorization": "Bearer isacbin_master_key_0508"
                },
                data: JSON.stringify({
                    name: name,
                    amount: amount,
                    message: message,
                    tx_id: txId
                }),
                onload: function(response) {
                    if (response.status === 200) {
                        console.log(`  ✅ [서버 전송 성공] ${name}님 ${amount}원 (TX: ${txId})`);
                        lastSentState = currentTextState; 
                        sendingState = ""; 
                    } else {
                        console.error(`  ❌ [서버 응답 오류] 상태코드: ${response.status}. 3초 후 재시도합니다.`);
                        setTimeout(sendDonation, 3000);
                    }
                },
                onerror: function(err) {
                    console.error("  ❌ [네트워크 연결 실패] 서버 연결 오류. 5초 후 재시도합니다.", err);
                    setTimeout(sendDonation, 5000);
                }
            });
        };

        sendDonation();
    }, 200);
})();
