package me.angelcompany.bankphone;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 방송 서버 /api/bank/deposit 으로 보낸다 — 은행 웹 확장과 같은 입구, source 'phone'.
 * 받는 쪽은 후원 콘솔 '계좌 입금 추천' 카드뿐이다(송출 · 장부 · 점수는 대표님이 눌러야 간다).
 * 못 보낸 입금은 폰에 쌓아 두고 다음 신호(30초마다) 때 다시 보낸다. 같은 ref 는 서버가 한 번만 받는다.
 */
final class Sender {
    private Sender() {}

    private static final ExecutorService ONE = Executors.newSingleThreadExecutor();
    private static final int BATCH = 30;

    static void flushAsync(final Context c, final String note) {
        final Context app = c.getApplicationContext();
        ONE.execute(new Runnable() {
            @Override public void run() { flush(app, note); }
        });
    }

    /** 대기줄을 보낸다(비어 있으면 '살아 있음' 신호만). 결과는 Store.setNet 에 남긴다. */
    static void flush(Context c, String note) {
        String key = Store.key(c), server = Store.server(c);
        long now = System.currentTimeMillis();
        if (key.isEmpty()) { Store.setNet(c, "nokey", now, 0); return; }
        if (!Store.allowed(server)) { Store.setNet(c, "server", now, 0); return; }
        JSONArray q = Store.queue(c);
        JSONArray batch = new JSONArray();
        for (int i = 0; i < q.length() && i < BATCH; i++) batch.put(q.opt(i));
        HttpURLConnection h = null;
        try {
            JSONObject body = new JSONObject();
            body.put("source", "phone");
            body.put("deposits", batch);
            body.put("note", note == null ? "" : (note.length() > 60 ? note.substring(0, 60) : note));
            byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
            URL url = new URL(server.replaceAll("/+$", "") + "/api/bank/deposit");
            h = (HttpURLConnection) url.openConnection();
            h.setConnectTimeout(10_000);
            h.setReadTimeout(10_000);
            h.setRequestMethod("POST");
            h.setDoOutput(true);
            h.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            h.setRequestProperty("X-Bank-Key", key);
            OutputStream os = h.getOutputStream();
            os.write(data);
            os.close();
            int code = h.getResponseCode();
            InputStream is = code < 400 ? h.getInputStream() : h.getErrorStream();
            if (is != null) { while (is.read() != -1) { /* 비운다 */ } is.close(); }
            if (code == 401) { Store.setNet(c, "key", now, code); return; }
            if (code < 200 || code >= 300) { Store.setNet(c, "http", now, code); return; }
            // 보낸 것만 대기줄에서 뺀다(그사이 새로 들어온 것은 남긴다)
            Set<String> sent = new HashSet<>();
            for (int i = 0; i < batch.length(); i++) {
                JSONObject o = batch.optJSONObject(i);
                if (o != null) sent.add(o.optString("ref"));
            }
            JSONArray cur = Store.queue(c), left = new JSONArray();
            for (int i = 0; i < cur.length(); i++) {
                JSONObject o = cur.optJSONObject(i);
                if (o != null && !sent.contains(o.optString("ref"))) left.put(o);
            }
            Store.setQueue(c, left);
            Store.setNet(c, "ok", now, code);
        } catch (Exception e) {
            Store.setNet(c, "net", now, 0);
        } finally {
            if (h != null) h.disconnect();
        }
    }
}
