import me.angelcompany.bankphone.Parser;

/** 🏦 폰 앱의 알림 읽기 규칙 검사 — 컴퓨터의 자바로 돌린다(안드로이드 없이). */
public class ParserTest {
    static int ok = 0, bad = 0;

    static void chk(String name, boolean cond, Object detail) {
        if (cond) { ok++; System.out.println("  [OK] " + name); }
        else { bad++; System.out.println("  [!!] " + name + "  -- " + detail); }
    }

    static void dep(String text, long amount, String sender) {
        Parser.Result r = Parser.parse(text);
        chk("입금: " + text.replace("\n", " / "), r.deposit && r.amount == amount && r.sender.equals(sender),
                r.deposit + " " + r.amount + " '" + r.sender + "' " + r.reason);
    }

    static void no(String text) {
        Parser.Result r = Parser.parse(text);
        chk("입금 아님: " + text.replace("\n", " / "), !r.deposit, r.reason);
    }

    public static void main(String[] a) {
        System.out.println("① 새 모양 [입금]");
        dep("[입금] 50,000원 홍길동", 50000, "홍길동");
        dep("[입금] 50,000원 영원 밍밍 화이팅", 50000, "영원 밍밍 화이팅");
        dep("IBK입출금알림\n[입금] 1,000원 테스트/안녕", 1000, "테스트/안녕");
        dep("[입금] 20000원", 20000, "");
        dep("[입금] 300,000원 구름빵 잔액 1,234,567원", 300000, "구름빵");
        dep("[입금] 10,000원 별빛 10/14 19:01", 10000, "별빛");
        System.out.println("② 옛 모양 금액 입금");
        dep("50,000원 입금\n홍길동", 50000, "홍길동");
        dep("IBK기업은행\n10/14 19:01 123-******-01-012\n30,000원 입금\n영원", 30000, "영원");
        dep("1,000원 입금", 1000, "");
        System.out.println("③ 예비 모양 입금 금액");
        dep("입금 5,000원 바람", 5000, "");
        System.out.println("④ 입금 아닌 것");
        no("[출금] 12,000원 편의점");
        no("12,000원 출금 체크카드");
        no("IBK입출금알림 출금 8,000원");
        no("카드 결제 승인 15,000원");
        no("입금 예정 이자 안내 1,200원");
        no("[이벤트] 입금하면 혜택 10,000원");
        no("오늘도 좋은 하루 되세요");
        no("입출금 내역을 확인하세요");
        no("[입금] 0원 이상한값");
        no("[입금] 999,999,999원 너무큼");
        System.out.println();
        System.out.println("통과 " + ok + " · 실패 " + bad);
        System.exit(bad == 0 ? 0 : 1);
    }
}
