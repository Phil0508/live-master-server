package me.angelcompany.bankphone;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.NumberFormat;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** 한 화면 — 권한 상태 · 열쇠 · 보낸 결과 · 시험 · 최근 기업은행 알림(폰 안에서만). */
public class MainActivity extends Activity {
    private static final int BG = Color.rgb(20, 22, 30), CARD = Color.rgb(30, 33, 44), FG = Color.rgb(232, 236, 243),
            MUTED = Color.rgb(154, 166, 187), OK = Color.rgb(126, 226, 168), WARN = Color.rgb(255, 200, 90), BAD = Color.rgb(255, 120, 120),
            ACCENT = Color.rgb(240, 123, 63);

    private final Handler h = new Handler(Looper.getMainLooper());
    private TextView stPerm, stBattery, stNet, stAlive, recentView;
    private Button btnPerm, btnBattery;
    private EditText inServer, inKey;

    private final Runnable tick = new Runnable() {
        @Override public void run() { refresh(); h.postDelayed(this, 2000); }
    };

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(BG);
        LinearLayout root = col();
        root.setPadding(dp(16), dp(20), dp(16), dp(32));
        sv.addView(root);
        setContentView(sv);

        root.addView(text("🏦 엔젤 입금알림", 22, FG, true));
        root.addView(text("기업은행 앱의 입금 알림을 읽어 방송 프로그램 '계좌 입금 추천' 칸으로 보내요. 송출은 후원 콘솔에서 사람이 눌러요.", 13, MUTED, false));

        LinearLayout c1 = card(root, "① 준비");
        stPerm = text("", 14, FG, false); c1.addView(stPerm);
        btnPerm = button("알림 읽기 권한 켜러 가기", new View.OnClickListener() {
            @Override public void onClick(View v) { startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)); }
        });
        c1.addView(btnPerm);
        stBattery = text("", 14, FG, false); c1.addView(stBattery);
        btnBattery = button("배터리 절약에서 빼러 가기", new View.OnClickListener() {
            @Override public void onClick(View v) { askBattery(); }
        });
        c1.addView(btnBattery);
        c1.addView(text("기업은행 앱(i-ONE Bank 기업 · 개인, IBK 스마트알림)의 입금 알림을 켜 두고, 이 폰은 충전기에 꽂아 두세요.", 12, MUTED, false));

        LinearLayout c2 = card(root, "② 방송 서버 연결");
        c2.addView(text("후원 콘솔 → 🏦 계좌 입금 추천 → [은행 확장 연결]의 열쇠를 붙여 넣으세요.", 12, MUTED, false));
        inKey = new EditText(this);
        inKey.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        inKey.setTextColor(FG); inKey.setHintTextColor(MUTED);
        c2.addView(inKey);
        inServer = new EditText(this);
        inServer.setSingleLine(true);
        inServer.setTextColor(FG); inServer.setTextSize(12);
        inServer.setText(Store.server(this));
        c2.addView(inServer);
        c2.addView(button("저장하고 신호 보내기", new View.OnClickListener() {
            @Override public void onClick(View v) { saveLink(); }
        }));
        stNet = text("", 14, FG, false); c2.addView(stNet);
        stAlive = text("", 12, MUTED, false); c2.addView(stAlive);

        LinearLayout c3 = card(root, "③ 시험");
        c3.addView(text("돈을 안 보내고 시험해요. 이 폰에 '[입금] 1,000원 시험손님' 알림을 띄우면, 앱이 읽어서 방송 서버로 보내요. "
                + "후원 콘솔에 '시험손님 1,000원' 카드가 뜨면 성공이에요(카드는 [숨기기]로 지우세요).", 12, MUTED, false));
        c3.addView(button("시험 알림 보내기", new View.OnClickListener() {
            @Override public void onClick(View v) { testNotify(); }
        }));

        LinearLayout c4 = card(root, "④ 최근 기업은행 알림 (이 폰 안에서만 보여요)");
        recentView = text("", 13, FG, false);
        recentView.setTypeface(Typeface.MONOSPACE);
        c4.addView(recentView);
        c4.addView(button("기록 지우기", new View.OnClickListener() {
            @Override public void onClick(View v) { Store.clearRecent(MainActivity.this); refresh(); }
        }));
    }

    @Override protected void onResume() { super.onResume(); h.post(tick); }
    @Override protected void onPause() { super.onPause(); h.removeCallbacks(tick); }

    private void refresh() {
        boolean perm = listenerEnabled();
        stPerm.setText(perm ? "✓ 알림 읽기 권한 켜짐" : "✗ 알림 읽기 권한이 꺼져 있어요 — 아래 단추로 '엔젤 입금알림'을 켜 주세요");
        stPerm.setTextColor(perm ? OK : BAD);
        btnPerm.setVisibility(perm ? View.GONE : View.VISIBLE);

        boolean bat = batteryIgnored();
        stBattery.setText(bat ? "✓ 배터리 절약에서 빠짐" : "△ 배터리 절약 중 — 화면이 꺼지면 늦게 보낼 수 있어요");
        stBattery.setTextColor(bat ? OK : WARN);
        btnBattery.setVisibility(bat ? View.GONE : View.VISIBLE);

        String key = Store.key(this);
        inKey.setHint(key.isEmpty() ? "열쇠 붙여 넣기" : "저장됨 ••••" + key.substring(Math.max(0, key.length() - 4)) + " (바꾸려면 새로 붙여 넣기)");

        int queued = Store.queue(this).length();
        String why = Store.netWhy(this);
        String msg; int color;
        switch (why) {
            case "ok": msg = "✓ 방송 서버로 보냄 " + hms(Store.netOkAt(this)) + (queued > 0 ? " · 기다리는 입금 " + queued + "건" : ""); color = OK; break;
            case "nokey": msg = "열쇠를 넣어야 방송 서버로 보내요"; color = WARN; break;
            case "key": msg = "✗ 열쇠가 맞지 않아요 — 후원 콘솔에서 다시 복사해 주세요"; color = BAD; break;
            case "server": msg = "✗ 보낼 수 없는 서버 주소예요"; color = BAD; break;
            case "http": msg = "✗ 방송 서버가 받지 않았어요(" + Store.netCode(this) + ") — 30초마다 다시 보내요"; color = BAD; break;
            case "net": msg = "✗ 방송 서버에 연결하지 못했어요 — 30초마다 다시 보내요" + (queued > 0 ? " (기다리는 입금 " + queued + "건)" : ""); color = BAD; break;
            default: msg = "아직 안 보냄"; color = MUTED;
        }
        stNet.setText(msg); stNet.setTextColor(color);
        long alive = Store.aliveAt(this);
        stAlive.setText(alive == 0 ? "알림 읽기가 아직 신호를 안 보냈어요(권한을 켜면 30초 안에 시작해요)"
                : "알림 읽기 마지막 신호 " + ago(alive));

        StringBuilder sb = new StringBuilder();
        JSONArray r = Store.recent(this);
        if (r.length() == 0) sb.append("아직 없어요.");
        NumberFormat nf = NumberFormat.getInstance(Locale.KOREA);
        for (int i = 0; i < r.length(); i++) {
            JSONObject o = r.optJSONObject(i);
            if (o == null) continue;
            sb.append(hms(o.optLong("at"))).append(" · ").append(o.optString("app")).append('\n');
            if (o.optBoolean("deposit")) {
                sb.append("  입금 ").append(nf.format(o.optLong("amount"))).append("원");
                if (!o.optString("sender").isEmpty()) sb.append(" · ").append(o.optString("sender"));
                sb.append('\n');
            }
            sb.append("  ").append(o.optString("reason")).append('\n');
            sb.append("  원문: ").append(o.optString("text").replace("\n", " / ")).append("\n\n");
        }
        int u = Store.unparsed(this);
        if (u > 0) sb.insert(0, "⚠️ 입금 알림인데 못 읽은 것 " + u + "건 — 이 화면을 캡처해 보내 주세요\n\n");
        recentView.setText(sb.toString());
    }

    private void saveLink() {
        String key = inKey.getText().toString().trim();
        String server = inServer.getText().toString().trim();
        if (key.isEmpty()) key = Store.key(this);
        if (!key.matches("[0-9a-f]{32}")) { toast("열쇠 모양이 아니에요 — 후원 콘솔에서 [복사]한 32글자를 그대로 붙여 주세요"); return; }
        if (!Store.allowed(server)) { toast("보낼 수 없는 주소예요 — 방송 서버 주소를 그대로 두세요"); return; }
        Store.saveLink(this, server, key);
        inKey.setText("");
        toast("저장했어요 — 신호를 보내 볼게요");
        Sender.flushAsync(this, "폰 앱 연결");
    }

    private void testNotify() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1);
            toast("알림 띄우기를 허용한 뒤 다시 눌러 주세요");
            return;
        }
        if (!listenerEnabled()) { toast("먼저 알림 읽기 권한을 켜 주세요"); return; }
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        Notification.Builder nb;
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(new NotificationChannel("test", "시험 알림", NotificationManager.IMPORTANCE_DEFAULT));
            nb = new Notification.Builder(this, "test");
        } else {
            nb = new Notification.Builder(this);
        }
        String stamp = new SimpleDateFormat("HHmmss", Locale.KOREA).format(new Date());
        nb.setSmallIcon(android.R.drawable.stat_notify_chat)
                .setContentTitle(BankListener.TEST_TAG + " " + stamp)
                .setContentText("[입금] 1,000원 시험손님")
                .setAutoCancel(true);
        nm.notify((int) (System.currentTimeMillis() % 100000), nb.build());
        toast("시험 알림을 띄웠어요 — 후원 콘솔을 확인하세요");
    }

    private boolean listenerEnabled() {
        String flat = Settings.Secure.getString(getContentResolver(), "enabled_notification_listeners");
        String me = new ComponentName(this, BankListener.class).flattenToString();
        return flat != null && flat.contains(me);
    }

    private boolean batteryIgnored() {
        if (Build.VERSION.SDK_INT < 23) return true;
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        return pm != null && pm.isIgnoringBatteryOptimizations(getPackageName());
    }

    private void askBattery() {
        if (Build.VERSION.SDK_INT < 23) return;
        try {
            Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
            i.setData(Uri.parse("package:" + getPackageName()));
            startActivity(i);
        } catch (Exception e) {
            startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
        }
    }

    // ── 화면 도구 ──
    private LinearLayout col() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    private LinearLayout card(LinearLayout root, String title) {
        LinearLayout c = col();
        c.setBackgroundColor(CARD);
        c.setPadding(dp(14), dp(12), dp(14), dp(12));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(14);
        c.setLayoutParams(lp);
        c.addView(text(title, 16, FG, true));
        root.addView(c);
        return c;
    }

    private TextView text(String s, int sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setPadding(0, dp(4), 0, dp(4));
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    private Button button(String label, View.OnClickListener on) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setBackgroundColor(ACCENT);
        b.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(6);
        b.setLayoutParams(lp);
        b.setOnClickListener(on);
        return b;
    }

    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density + 0.5f); }
    private void toast(String s) { Toast.makeText(this, s, Toast.LENGTH_LONG).show(); }
    private static String hms(long t) { return t == 0 ? "-" : new SimpleDateFormat("HH:mm:ss", Locale.KOREA).format(new Date(t)); }
    private static String ago(long t) {
        long s = Math.max(0, (System.currentTimeMillis() - t) / 1000);
        return s < 60 ? s + "초 전" : (s < 3600 ? s / 60 + "분 전" : s / 3600 + "시간 전");
    }
}
