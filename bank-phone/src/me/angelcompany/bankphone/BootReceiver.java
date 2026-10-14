package me.angelcompany.bankphone;

import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.service.notification.NotificationListenerService;

/** 폰을 다시 켜거나 앱을 새로 깔면 알림 읽기를 다시 붙여 달라고 한다(권한이 켜져 있을 때만 된다). */
public class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context c, Intent i) {
        try {
            NotificationListenerService.requestRebind(new ComponentName(c, BankListener.class));
        } catch (Exception ignored) {}
        Sender.flushAsync(c, "폰을 다시 켬");
    }
}
