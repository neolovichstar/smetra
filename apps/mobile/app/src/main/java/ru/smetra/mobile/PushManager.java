package ru.smetra.mobile;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

final class PushManager {
    interface Callback { void complete(boolean success, String message); }
    private static final String PREFS = "smetra_push_preferences";
    private static final String ENABLED = "enabled";
    private static final String INSTALLATION = "installation_id";
    private static final String TOKEN = "token";
    private static final ExecutorService IO = Executors.newSingleThreadExecutor();
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private PushManager() {}

    static boolean isConfigured() { return !BuildConfig.RUSTORE_PUSH_PROJECT_ID.trim().isEmpty(); }
    static boolean isEnabled(Context c) { return prefs(c).getBoolean(ENABLED, false); }
    static void setEnabled(Context c, boolean enabled) { prefs(c).edit().putBoolean(ENABLED, enabled).apply(); }

    static String getInstallationId(Context c) {
        SharedPreferences p = prefs(c);
        String old = p.getString(INSTALLATION, "");
        if (old != null && old.matches("[0-9a-fA-F-]{36}")) return old;
        String id = UUID.randomUUID().toString();
        p.edit().putString(INSTALLATION, id).apply();
        return id;
    }

    private static SharedPreferences prefs(Context c) {
        return c.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static void requestTokenAndRegister(Activity activity, String sessionToken, Callback cb) {
        if (!isConfigured()) { cb.complete(false, "Push ещё не подключён: не задан ID проекта RuStore."); return; }
        if (sessionToken == null || sessionToken.trim().isEmpty()) { cb.complete(false, "Сначала войдите в аккаунт Сметры."); return; }
        ru.rustore.sdk.pushclient.RuStorePushClient.INSTANCE.getToken()
            .addOnSuccessListener(t -> register(activity, sessionToken, t, cb))
            .addOnFailureListener(e -> cb.complete(false, "RuStore не выдал push-токен. Проверьте установку RuStore и подпись приложения."));
    }

    static void syncIfEnabled(Context c, String sessionToken) {
        if (!isEnabled(c) || !isConfigured() || sessionToken == null || sessionToken.isEmpty()) return;
        ru.rustore.sdk.pushclient.RuStorePushClient.INSTANCE.getToken()
            .addOnSuccessListener(t -> registerBackground(c, sessionToken, t));
    }

    static void onTokenRefresh(Context c, String pushToken) {
        if (pushToken == null || pushToken.length() < 16 || pushToken.length() > 4096) return;
        prefs(c).edit().putString(TOKEN, pushToken).apply();
        if (!isEnabled(c)) return;
        String session = new TokenVault(c).read();
        if (session != null && !session.isEmpty()) registerBackground(c, session, pushToken);
    }

    private static void register(Activity a, String session, String pushToken, Callback cb) {
        if (pushToken == null || pushToken.length() < 16 || pushToken.length() > 4096) {
            cb.complete(false, "RuStore вернул некорректный push-токен."); return;
        }
        prefs(a).edit().putString(TOKEN, pushToken).apply();
        IO.execute(() -> {
            boolean ok = send(a, session, "POST", "/api/push-devices", pushToken);
            MAIN.post(() -> cb.complete(ok, ok ? "Push-уведомления подключены." : "Не удалось привязать устройство. Проверьте backend и повторите попытку."));
        });
    }

    private static void registerBackground(Context c, String session, String pushToken) {
        if (pushToken == null || pushToken.length() < 16 || pushToken.length() > 4096) return;
        IO.execute(() -> send(c, session, "POST", "/api/push-devices", pushToken));
    }

    static void unregister(Context c, String installationId, String session, Runnable done) {
        IO.execute(() -> {
            if (session != null && !session.isEmpty())
                send(c, session, "DELETE", "/api/push-devices/" + installationId, null);
            MAIN.post(() -> { if (done != null) done.run(); });
        });
    }

    private static boolean send(Context c, String session, String method, String path, String pushToken) {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection)new URL(BuildConfig.API_BASE_URL + path).openConnection();
            connection.setRequestMethod(method);
            connection.setConnectTimeout(5000);
            connection.setReadTimeout(5000);
            connection.setRequestProperty("Authorization", "Bearer " + session);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            if ("POST".equals(method)) {
                JSONObject payload = new JSONObject().put("installation_id", getInstallationId(c))
                    .put("token", pushToken).put("platform", "android");
                byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
                connection.setDoOutput(true);
                connection.setFixedLengthStreamingMode(body.length);
                try (OutputStream out = connection.getOutputStream()) { out.write(body); }
            }
            int status = connection.getResponseCode();
            InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            if (stream != null) try (InputStream in=stream; ByteArrayOutputStream out=new ByteArrayOutputStream()) {
                byte[] buffer=new byte[1024]; int count, total=0;
                while ((count=in.read(buffer))!=-1 && total<65536) {
                    int accepted=Math.min(count,65536-total); out.write(buffer,0,accepted); total+=accepted;
                }
            }
            return status>=200 && status<300;
        } catch (Exception ignored) {
            return false;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }
}
