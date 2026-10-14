package me.angelcompany.bankphone;

import android.app.Notification;
import android.content.ComponentName;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import org.json.JSONArray;
import org.json.JSONObject;

import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.Arrays;
import java.util.Date;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

/**
 * 📩 폰에 뜨는 알림 중 **기업은행 앱 두 개**의 것만 읽는다. 다른 앱 알림은 보지도 않는다.
 * 입금이면 대기줄에 넣고 바로 보낸다. 30초마다 '살아 있음' 신호(후원 콘솔: '은행 연결됨 · 폰').
 */
public class BankListener extends NotificationListenerService {
    static final Set<String> IBK = new HashSet<>(Arrays.asList("com.ibk.android.ionebank", "com.IBK.SmartPush.app"));
    static final String TEST_TAG = "[엔젤 시험]";
    private static final long BEAT_MS = 30_000;

    private final Handler h = new Handler(Looper.getMainLooper());
    private final Runnable beat = new Runnable() {
        @Override public void run() {
            Store.setAlive(BankListener.this, System.currentTimeMillis());
            Sender.flushAsync(BankListener.this, note());
            h.postDelayed(this, BEAT_MS);
        }
    };

    private String note() {
        int u = Store.unparsed(this);
        return "폰 알림 읽는 중" + (u > 0 ? " · 못 읽은 입금 알림 " + u + "건" : "");
    }

    @Override public void onListenerConnected() {
        h.removeCallbacks(beat);
        h.post(beat);
    }

    @Override public void onListenerDisconnected() {
        h.removeCallbacks(beat);
        try { requestRebind(new ComponentName(this, BankListener.class)); } catch (Exception ignored) {}
    }

    @Override public void onNotificationPosted(StatusBarNotification sbn) {
        try { handle(sbn); } catch (Exception ignored) { /* 알림 하나 때문에 듣기가 멈추면 안 된다 */ }
    }

    private void handle(StatusBarNotification sbn) throws Exception {
        String pkg = sbn.getPackageName();
        Notification n = sbn.getNotification();
        if (n == null) return;
        String text = textOf(n.extras);
        boolean isTest = getPackageName().equals(pkg) && text.contains(TEST_TAG);
        if (!IBK.contains(pkg) && !isTest) return;
        if ((n.flags & Notification.FLAG_GROUP_SUMMARY) != 0) return;   // 묶음 머리 알림은 내용이 없다
        if (isTest) text = text.replace(TEST_TAG, "").trim();

        long now = System.currentTimeMillis();
        Parser.Result r = Parser.parse(text);
        String when = new SimpleDateFormat("yyyy.MM.dd HH:mm:ss", Locale.KOREA).format(new Date(sbn.getPostTime()));
        String app = isTest ? "시험" : ("com.IBK.SmartPush.app".equals(pkg) ? "스마트알림" : "i-ONE Bank");

        JSONObject row = new JSONObject();
        row.put("at", now);
        row.put("app", app);
        row.put("text", text.length() > 200 ? text.substring(0, 200) : text);
        row.put("deposit", r.deposit);
        row.put("amount", r.amount);
        row.put("sender", r.sender);
        row.put("reason", r.reason);

        if (!r.deposit) {
            if (text.contains("입금") && r.reason.startsWith("입금 글은")) Store.bumpUnparsed(this);
            Store.addRecent(this, row);
            return;
        }
        if (Store.seenRecently(this, pkg, r.amount, r.sender, now)) {
            row.put("reason", "다른 은행 앱이 같은 입금을 먼저 알림 — 한 번만 보냄");
            Store.addRecent(this, row);
            return;
        }
        JSONObject dep = new JSONObject();
        dep.put("ref", "ph:" + sha(pkg + "|" + sbn.getPostTime() + "|" + sbn.getKey() + "|" + text));
        dep.put("amount", r.amount);
        dep.put("when", when);
        JSONArray fields = new JSONArray();
        if (!r.sender.isEmpty()) fields.put(new JSONArray().put("입금자명").put(r.sender));
        dep.put("fields", fields);
        Store.enqueue(this, dep);
        row.put("reason", r.reason + " → 방송 서버로 보냄");
        Store.addRecent(this, row);
        Sender.flushAsync(this, note());
    }

    /** 알림 제목 · 본문 · 펼친 본문 · 여러 줄을 겹치지 않게 이어 붙인다 */
    static String textOf(Bundle ex) {
        if (ex == null) return "";
        Set<String> parts = new LinkedHashSet<>();
        add(parts, ex.getCharSequence(Notification.EXTRA_TITLE));
        CharSequence big = ex.getCharSequence(Notification.EXTRA_BIG_TEXT);
        add(parts, big != null ? big : ex.getCharSequence(Notification.EXTRA_TEXT));
        CharSequence[] lines = ex.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
        if (lines != null) for (CharSequence l : lines) add(parts, l);
        StringBuilder sb = new StringBuilder();
        for (String s : parts) { if (sb.length() > 0) sb.append('\n'); sb.append(s); }
        return sb.toString();
    }

    private static void add(Set<String> parts, CharSequence cs) {
        if (cs == null) return;
        String s = cs.toString().trim();
        if (!s.isEmpty()) parts.add(s);
    }

    private static String sha(String s) throws Exception {
        byte[] d = MessageDigest.getInstance("SHA-1").digest(s.getBytes("UTF-8"));
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 8; i++) sb.append(String.format("%02x", d[i]));
        return sb.toString();
    }
}
