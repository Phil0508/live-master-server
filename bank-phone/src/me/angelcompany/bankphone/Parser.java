package me.angelcompany.bankphone;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 기업은행 입금 알림 글 → 금액 · 보낸 사람.
 *
 * 알려진 모양:
 *   "[입금] 1원\n스트밍밍플러 -> 내 입출금통장(04-011)\n잔액 37,449,258원"
 *                                 — ✅ 실제 알림(i-ONE Bank 기업, 10-14). 보낸 사람은 다음 줄, ' -> ' 뒤는 내 통장
 *   "[입금] 50,000원 홍길동"      — 한 줄로 붙어 올 때
 *   "50,000원 입금" (+ 다른 줄)   — 옛 모양
 *   "입금 50,000원"               — 다른 은행에 흔한 모양(예비)
 * 결과는 '추천' 카드가 될 뿐이다(송출은 사람이 누른다). 그래서 애매하면 놓치는 쪽보다 잡는 쪽으로 둔다.
 * ⚠️ 이 파일은 안드로이드를 안 부른다 — 컴퓨터에서 ParserTest 로 바로 검사한다.
 */
public final class Parser {
    private Parser() {}

    public static final class Result {
        public final boolean deposit;
        public final long amount;
        public final String sender;
        public final String reason;

        Result(boolean deposit, long amount, String sender, String reason) {
            this.deposit = deposit;
            this.amount = amount;
            this.sender = sender == null ? "" : sender;
            this.reason = reason;
        }
    }

    public static final long AMOUNT_MAX = 100_000_000L;

    private static final String AMT = "([1-9][0-9]{0,2}(?:,[0-9]{3})+|[1-9][0-9]*)";
    /** 보낸 사람은 같은 줄 뒤나 바로 다음 줄에 온다(10-14 실제 알림은 다음 줄) */
    private static final Pattern BRACKET = Pattern.compile("\\[입금\\]\\s*" + AMT + "\\s*원(?:[ \\t]*(?:\\r?\\n)?[ \\t]*([^\\r\\n]+))?");
    /** ' -> 내 입출금통장(04-011)' — 화살표 뒤는 받는 내 통장이다 */
    private static final Pattern TO_ACCOUNT = Pattern.compile("\\s*(->|→|▶|=>).*$");
    private static final Pattern AMT_THEN_IN = Pattern.compile(AMT + "\\s*원\\s*입금");
    private static final Pattern IN_THEN_AMT = Pattern.compile("입금\\s*[:：]?\\s*" + AMT + "\\s*원");
    /** 출금 · 결제가 섞인 알림은 입금이 아니다. '입출금 알림' 같은 머리글은 미리 지운다. */
    private static final Pattern WITHDRAW = Pattern.compile("\\[출금\\]|출금\\s*[0-9]|[0-9,]+\\s*원\\s*출금");
    private static final String[] REJECT = {"결제", "승인", "취소", "자동이체", "광고", "이벤트", "혜택", "포인트",
            "캐시백", "대출", "이자", "납부", "청구", "미납"};
    /** 보낸 사람 칸에 붙어 오는 꼬리 — 잔액 · 계좌 · 시각 */
    private static final Pattern SENDER_TAIL = Pattern.compile("\\s*(잔액|잔고).*$|\\s*\\d{2,}[-*][\\d*-]+.*$|\\s*\\d{1,2}[:/]\\d{2}.*$");

    public static Result parse(String text) {
        String t = text == null ? "" : text.replace(' ', ' ');
        if (!t.contains("입금")) return new Result(false, 0, "", "입금 글자 없음");
        String scan = t.replace("입출금", "");
        if (WITHDRAW.matcher(scan).find()) return new Result(false, 0, "", "출금 알림");
        for (String w : REJECT) {
            if (scan.contains(w)) return new Result(false, 0, "", "제외 낱말: " + w);
        }
        Matcher m = BRACKET.matcher(t);
        if (m.find()) return ok(m.group(1), m.group(2), "[입금] 모양");
        m = AMT_THEN_IN.matcher(t);
        if (m.find()) return ok(m.group(1), guessSender(t, m.group(0)), "금액 입금 모양");
        m = IN_THEN_AMT.matcher(t);
        if (m.find()) return ok(m.group(1), guessSender(t, m.group(0)), "입금 금액 모양");
        return new Result(false, 0, "", "입금 글은 있는데 모양을 못 읽음");
    }

    private static Result ok(String amt, String sender, String how) {
        long a;
        try {
            a = Long.parseLong(amt.replace(",", ""));
        } catch (NumberFormatException e) {
            return new Result(false, 0, "", "금액을 숫자로 못 읽음");
        }
        if (a <= 0 || a > AMOUNT_MAX) return new Result(false, 0, "", "금액이 이상함");
        return new Result(true, a, cleanSender(sender), how);
    }

    /** 옛 모양은 보낸 사람이 다른 줄에 있다 — 금액 · 시각 · 계좌 · 은행 이름이 아닌 짧은 줄을 고른다. */
    static String guessSender(String text, String amountPart) {
        for (String line : text.split("[\\r\\n]+")) {
            String l = line.trim();
            if (l.isEmpty() || l.contains(amountPart) || l.contains("입금") || l.contains("잔액")) continue;
            if (l.matches(".*(은행|IBK|기업|뱅크|알림).*")) continue;
            if (l.matches("[0-9 ,.:/*()\\-]+")) continue;
            if (l.length() <= 20) return l;
        }
        return "";
    }

    static String cleanSender(String s) {
        if (s == null) return "";
        String v = s.replace(' ', ' ').trim();
        v = TO_ACCOUNT.matcher(v).replaceAll("").trim();
        v = SENDER_TAIL.matcher(v).replaceAll("").trim();
        v = v.replaceAll("\\s+", " ");
        return v.length() > 40 ? v.substring(0, 40) : v;
    }
}
