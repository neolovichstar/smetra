package ru.smetra.mobile;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.text.TextUtils;
import java.util.List;
import java.util.Map;
import ru.rustore.sdk.pushclient.messaging.model.RemoteMessage;
import ru.rustore.sdk.pushclient.messaging.service.RuStoreMessagingService;
import ru.rustore.sdk.pushclient.messaging.exception.RuStorePushClientException;

public final class SmetraPushMessagingService extends RuStoreMessagingService {
    private static final String CHANNEL_ID = "smetra_updates";
    private static final String CHANNEL_NAME = "Уведомления Сметры";

    @Override public void onNewToken(String token) {
        PushManager.onTokenRefresh(getApplicationContext(), token);
    }

    @Override public void onMessageReceived(RemoteMessage message) {
        if (message == null) return;
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            return;
        }

        String title = "Сметра";
        String body = "Есть новое событие. Откройте Сметру, чтобы посмотреть подробности.";
        RemoteMessage.Notification content = message.getNotification();
        if (content != null) {
            if (!TextUtils.isEmpty(content.getTitle())) title = content.getTitle();
            if (!TextUtils.isEmpty(content.getBody())) body = content.getBody();
        }
        Map<String, String> data = message.getData();
        if (content == null && data != null && !data.isEmpty()) {
            String dataBody = data.get("body");
            if (!TextUtils.isEmpty(dataBody)) body = dataBody;
        }

        NotificationManager manager =
                (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager == null) return;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, CHANNEL_NAME, NotificationManager.IMPORTANCE_DEFAULT);
            channel.setDescription("Согласования и рабочие события");
            manager.createNotificationChannel(channel);
        }

        Intent open = new Intent(this, MainActivity.class);
        open.setAction("ru.smetra.mobile.OPEN_NOTIFICATIONS");
        open.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        int notificationId = message.hashCode();
        PendingIntent pending = PendingIntent.getActivity(
                this,
                notificationId,
                open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        Notification notification = builder
                .setSmallIcon(R.drawable.logo_monochrome)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setContentIntent(pending)
                .setAutoCancel(true)
                .setShowWhen(true)
                .setCategory(Notification.CATEGORY_EVENT)
                .setPriority(Notification.PRIORITY_DEFAULT)
                .build();
        manager.notify(notificationId, notification);
    }

    @Override public void onDeletedMessages() {
        // The app refreshes its in-app notification centre when it is opened.
    }

    @Override public void onError(List<? extends RuStorePushClientException> errors) {
        // Do not write service or device tokens into production logs.
    }
}
