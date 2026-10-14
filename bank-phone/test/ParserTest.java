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
        System.out.println("⓪ 실제 알림 (10-14 대표님 폰, i-ONE Bank 기업)");
        dep("i-ONE뱅크 기업\n[입금] 1원\n스트밍밍플러 -> 내 입출금통장(04-011)\n잔액 37,449,258원", 1, "스트밍밍플러");
        dep("[입금] 1원\n스트밍밍플러 -> 내 입출금통장(04-011)\n잔액 37,449,258원", 1, "스트밍밍플러");
        dep("[입금] 1원 스트밍밍플러 -> 내 입출금통장(04-011) 잔액 37,449,258원", 1, "스트밍밍플러");
        dep("i-ONE뱅크 기업\n[입금] 50,000원\n영원 밍밍 화이팅 -> 내 입출금통장(04-011)\n잔액 37,499,258원", 50000, "영원 밍밍 화이팅");
        dep("[입금] 30,000원\n잔액 37,449,258원", 30000, "");
        no("i-ONE뱅크 기업\n[입금] 11,800원\n카카오T택시_가승인 -> 내 입출금통장(04-011)\n잔액 37,461,557원");
        no("i-ONE뱅크 기업\n[출금] 1원\n내 입출금통장(04-011) -> 스트밍밍플러\n잔액 37,449,257원");
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
