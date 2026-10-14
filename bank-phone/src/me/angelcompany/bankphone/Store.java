package me.angelcompany.bankphone;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

/** 폰 안에 남기는 것 — 서버 주소 · 열쇠 · 못 보낸 입금 대기줄 · 최근 알림 · 마지막 전송 결과. */
final class Store {
    private Store() {}

    static final String PROD = "https://xn--9i1b547a0ublxlz4f.xn--h32bi4v.xn--3e0b707e";   // 엔젤컴퍼니.메인.한국
    static final int QUEUE_MAX = 200;
    static final int RECENT_MAX = 20;

    private static SharedPreferences p(Context c) {
        return c.getSharedPreferences("bankphone", Context.MODE_PRIVATE);
    }

    static String server(Context c) { return p(c).getString("server", PROD); }
    static String key(Context c) { return p(c).getString("key", ""); }
    static void saveLink(Context c, String server, String key) {
        p(c).edit().putString("server", server).putString("key", key).apply();
    }

    /** 보낼 수 있는 곳 — 방송 서버, 그리고 시험용 집 안 공유기 주소(192.168.* · 10.* · 172.16~31.*)뿐 */
    static boolean allowed(String url) {
        if (url == null) return false;
        String u = url.trim();
        if (u.equals(PROD) || u.startsWith(PROD + "/")) return true;
        return u.matches("https?://(192\\.168\\.\\d{1,3}\\.\\d{1,3}|10\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}|172\\.(1[6-9]|2\\d|3[01])\\.\\d{1,3}\\.\\d{1,3})(:\\d{1,5})?/?");
    }

    // ── 대기줄(못 보낸 입금) ──
    static synchronized JSONArray queue(Context c) {
        try { return new JSONArray(p(c).getString("queue", "[]")); } catch (Exception e) { return new JSONArray(); }
    }
    static synchronized void setQueue(Context c, JSONArray q) {
        JSONArray out = new JSONArray();
        int start = Math.max(0, q.length() - QUEUE_MAX);
        for (int i = start; i < q.length(); i++) out.put(q.opt(i));
        p(c).edit().putString("queue", out.toString()).apply();
    }
    static synchronized void enqueue(Context c, JSONObject dep) {
        JSONArray q = queue(c);
        String ref = dep.optString("ref");
        for (int i = 0; i < q.length(); i++) {
            JSONObject o = q.optJSONObject(i);
            if (o != null && ref.equals(o.optString("ref"))) return;
        }
        q.put(dep);
        setQueue(c, q);
    }

    // ── 최근 알림(폰 안에서만 — 서버로 안 보낸다) ──
    static synchronized JSONArray recent(Context c) {
        try { return new JSONArray(p(c).getString("recent", "[]")); } catch (Exception e) { return new JSONArray(); }
    }
    static synchronized void addRecent(Context c, JSONObject row) {
        JSONArray r = recent(c);
        JSONArray out = new JSONArray();
        out.put(row);
        for (int i = 0; i < r.length() && out.length() < RECENT_MAX; i++) out.put(r.opt(i));
        p(c).edit().putString("recent", out.toString()).apply();
    }
    static synchronized void clearRecent(Context c) { p(c).edit().putString("recent", "[]").putInt("unparsed", 0).apply(); }

    static synchronized void bumpUnparsed(Context c) { p(c).edit().putInt("unparsed", p(c).getInt("unparsed", 0) + 1).apply(); }
    static int unparsed(Context c) { return p(c).getInt("unparsed", 0); }

    // ── 같은 입금을 두 앱(i-ONE Bank · 스마트알림)이 둘 다 알릴 때 하나만 보낸다 ──
    // ⚠️ **다른 앱**이 20초 안에 같은 금액 · 같은 이름을 알린 것만 같은 입금으로 본다.
    //    같은 앱이 두 번 알렸으면 진짜로 두 번 보낸 것이다(같은 사람이 같은 금액을 연달아 — 실제로 있었다).
    static synchronized boolean seenRecently(Context c, String pkg, long amount, String sender, long now) {
        String k = amount + "|" + sender;
        String last = p(c).getString("lastDep", "");
        String lastPkg = p(c).getString("lastDepPkg", "");
        long at = p(c).getLong("lastDepAt", 0);
        p(c).edit().putString("lastDep", k).putString("lastDepPkg", pkg).putLong("lastDepAt", now).apply();
        return k.equals(last) && !pkg.equals(lastPkg) && now - at < 20_000;
    }

    // ── 마지막 전송 결과 · 알림 읽기 살아 있음 ──
    static void setNet(Context c, String why, long at, int code) {
        SharedPreferences.Editor e = p(c).edit().putString("netWhy", why).putInt("netCode", code);
        if ("ok".equals(why)) e.putLong("netOkAt", at);
        e.putLong("netAt", at).apply();
    }
    static String netWhy(Context c) { return p(c).getString("netWhy", "idle"); }
    static int netCode(Context c) { return p(c).getInt("netCode", 0); }
    static long netOkAt(Context c) { return p(c).getLong("netOkAt", 0); }
    static void setAlive(Context c, long at) { p(c).edit().putLong("aliveAt", at).apply(); }
    static long aliveAt(Context c) { return p(c).getLong("aliveAt", 0); }
    static void setTestMode(Context c, boolean on) { p(c).edit().putBoolean("testMode", on).apply(); }
    static boolean testMode(Context c) { return p(c).getBoolean("testMode", false); }
}
