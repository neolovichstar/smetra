package ru.smetra.mobile;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.speech.RecognizerIntent;
import android.util.Base64;
import android.webkit.WebView;
import androidx.core.content.FileProvider;
import androidx.webkit.JavaScriptReplyProxy;
import androidx.webkit.WebMessageCompat;
import androidx.webkit.WebViewCompat;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Receives typed requests from the web cabinet (see BridgeProtocol) and answers
 * on the same channel. Only the configured HTTPS origin's main frame is heard;
 * every argument is validated here, and sensitive actions are still authorised
 * by the server with the user's session.
 */
final class ShellBridge implements WebViewCompat.WebMessageListener {
    private static final int MAX_FILE_BYTES = 10 * 1024 * 1024;
    private final ShellActivity activity;
    private final WebView web;
    private JavaScriptReplyProxy page;
    private final List<String> queued = new ArrayList<>();
    private final Map<Integer, String> waiting = new HashMap<>();
    private byte[] pendingSave;
    private boolean closed;

    ShellBridge(ShellActivity activity, WebView web) { this.activity = activity; this.web = web; }

    static JSONObject message(String text) {
        try { return new JSONObject().put("message", text); } catch (JSONException error) { return new JSONObject(); }
    }

    @Override public void onPostMessage(WebView view, WebMessageCompat message, Uri sourceOrigin, boolean isMainFrame, JavaScriptReplyProxy reply) {
        String raw = message.getData();
        if (!isMainFrame || sourceOrigin == null || !BridgeProtocol.trustedOrigin(sourceOrigin.toString(), ShellSession.ORIGIN)) return;
        BridgeProtocol.Request request;
        try { request = BridgeProtocol.parse(raw); }
        catch (BridgeProtocol.BridgeException error) {
            String id = BridgeProtocol.idOf(raw);
            if (!id.isEmpty()) reply.postMessage(BridgeProtocol.error(id, error.code, error.getMessage()));
            return;
        }
        if ("app.hello".equals(request.op)) {
            page = reply;
            reply.postMessage(BridgeProtocol.ok(request.id, capabilities()));
            for (String event : queued) reply.postMessage(event);
            queued.clear();
            return;
        }
        try { handle(request, reply); }
        catch (Exception error) { reply.postMessage(BridgeProtocol.error(request.id, "failed", "Не удалось выполнить действие")); }
    }

    private void handle(BridgeProtocol.Request r, JavaScriptReplyProxy reply) throws Exception {
        switch (r.op) {
            case "app.capabilities": reply.postMessage(BridgeProtocol.ok(r.id, capabilities())); return;
            case "app.openStore": ShellUpdates.openStore(activity); ok(reply, r.id, null); return;
            case "app.openExternal": {
                Uri url = Uri.parse(r.args.optString("url", ""));
                if (!"https".equals(url.getScheme())) { error(reply, r.id, "bad_request", "Можно открыть только https-ссылку"); return; }
                activity.openExternal(url); ok(reply, r.id, null); return;
            }
            case "app.setTheme": activity.setDarkChrome(r.args.optBoolean("dark", true)); ok(reply, r.id, null); return;
            case "auth.start": {
                String provider = r.args.optString("provider", "yandex");
                String intent = "register".equals(r.args.optString("intent")) ? "register" : "login";
                Uri.Builder start = Uri.parse(ShellSession.ORIGIN + "/api/auth/oauth/" + provider + "/start").buildUpon().appendQueryParameter("intent", intent);
                if (r.args.optBoolean("legal_acceptance"))
                    start.appendQueryParameter("legal_acceptance", "1").appendQueryParameter("legal_version", r.args.optString("legal_version", ""));
                ShellAuth.start(activity, start.build());
                ok(reply, r.id, null); return;
            }
            case "speech.recognize": speech(r, reply); return;
            case "device.haptic": NativeDevice.haptic(activity, r.args); ok(reply, r.id, null); return;
            case "device.copyText": NativeDevice.copyText(activity, r.args); ok(reply, r.id, null); return;
            case "device.shareText": NativeDevice.shareText(activity, r.args); ok(reply, r.id, null); return;
            case "device.biometric.status": reply.postMessage(BridgeProtocol.ok(r.id, NativeDevice.biometricStatus(activity))); return;
            case "vision.image.scan": NativeVision.scan(activity, r.args, (value, code, text) -> {
                if (closed) return;
                if (value != null) reply.postMessage(BridgeProtocol.ok(r.id, value));
                else reply.postMessage(BridgeProtocol.error(r.id, code, text));
            }); return;
            case "ads.rewarded.show":
                ShellAds.show(activity, (value, code, text) -> {
                    if (value != null) reply.postMessage(BridgeProtocol.ok(r.id, value));
                    else reply.postMessage(BridgeProtocol.error(r.id, code, text));
                });
                return;
            case "push.status": reply.postMessage(BridgeProtocol.ok(r.id, pushStatus())); return;
            case "push.enable": pushEnable(r, reply); return;
            case "push.disable":
                PushManager.setEnabled(activity, false);
                PushManager.unregister(activity, PushManager.getInstallationId(activity), ShellSession.token(), () -> reply.postMessage(BridgeProtocol.ok(r.id, pushStatus())));
                return;
            case "file.save": saveFile(r, reply); return;
            case "file.share": case "file.open": shareFile(r, reply); return;
            case "ar.status": reply.postMessage(BridgeProtocol.ok(r.id, ShellSupport.arStatus(activity))); return;
            case "ar.measure": arMeasure(r, reply); return;
            case "request.cancel": ok(reply, r.id, null); return;
            default: error(reply, r.id, "unknown_operation", "Операция недоступна");
        }
    }

    private JSONObject capabilities() {
        try {
            JSONObject features = new JSONObject()
                .put("files", true)
                .put("camera", activity.getPackageManager().hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY))
                .put("speech", !activity.getPackageManager().queryIntentActivities(new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH), 0).isEmpty())
                .put("share", true)
                .put("push", PushManager.isConfigured())
                .put("ads", true)
                .put("ar", ShellSupport.arStatus(activity).optString("status"))
                .put("barcodeImage", true)
                .put("textImageLatin", true)
                .put("biometric", NativeDevice.biometricStatus(activity).optBoolean("available"))
                .put("haptics", true)
                .put("clipboardWrite", true)
                .put("shareText", true)
                .put("nativeFoundation", 2);
            return new JSONObject()
                .put("protocol", BridgeProtocol.VERSION)
                .put("platform", "android")
                .put("app_version", BuildConfig.VERSION_NAME)
                .put("version_code", BuildConfig.VERSION_CODE)
                .put("sdk", Build.VERSION.SDK_INT)
                .put("operations", new JSONArray(BridgeProtocol.OPERATIONS))
                .put("features", features);
        } catch (JSONException error) { return new JSONObject(); }
    }

    // ---------- speech ----------

    private void speech(BridgeProtocol.Request r, JavaScriptReplyProxy reply) {
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ru-RU")
            .putExtra(RecognizerIntent.EXTRA_PROMPT, "Говорите — текст появится в поле сообщения");
        if (!begin(ShellActivity.REQUEST_SPEECH, r.id, reply)) return;
        try { activity.startActivityForResult(intent, ShellActivity.REQUEST_SPEECH); }
        catch (ActivityNotFoundException error) { settle(ShellActivity.REQUEST_SPEECH, null, "unsupported", "Распознавание речи недоступно на этом устройстве"); }
    }

    // ---------- push ----------

    private JSONObject pushStatus() {
        boolean allowed = Build.VERSION.SDK_INT < 33 || activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
        JSONObject status = new JSONObject();
        try { status.put("configured", PushManager.isConfigured()).put("enabled", PushManager.isEnabled(activity)).put("permission", allowed); }
        catch (JSONException ignored) { }
        return status;
    }

    private void pushEnable(BridgeProtocol.Request r, JavaScriptReplyProxy reply) {
        Runnable register = () -> PushManager.requestTokenAndRegister(activity, ShellSession.token(), (success, text) -> {
            if (success) PushManager.setEnabled(activity, true);
            if (success) reply.postMessage(BridgeProtocol.ok(r.id, pushStatus()));
            else reply.postMessage(BridgeProtocol.error(r.id, "push_failed", text));
        });
        if (Build.VERSION.SDK_INT >= 33) activity.withPermission(Manifest.permission.POST_NOTIFICATIONS, ShellActivity.PERMISSION_NOTIFICATIONS,
            register, () -> reply.postMessage(BridgeProtocol.error(r.id, "permission_denied", "Разрешите уведомления в настройках Android")));
        else register.run();
    }

    // ---------- files ----------

    private byte[] decode(BridgeProtocol.Request r) {
        String data = r.args.optString("base64", "");
        if (data.isEmpty() || data.length() > MAX_FILE_BYTES * 4 / 3 + 8) return null;
        try {
            byte[] bytes = Base64.decode(data, Base64.DEFAULT);
            return bytes.length == 0 || bytes.length > MAX_FILE_BYTES ? null : bytes;
        } catch (IllegalArgumentException error) { return null; }
    }

    private void saveFile(BridgeProtocol.Request r, JavaScriptReplyProxy reply) {
        byte[] bytes = decode(r);
        if (bytes == null) { error(reply, r.id, "bad_request", "Файл пустой или больше 10 МБ"); return; }
        if (!begin(ShellActivity.REQUEST_SAVE, r.id, reply)) return;
        pendingSave = bytes;
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
            .setType(BridgeProtocol.safeMime(r.args.optString("mime")))
            .putExtra(Intent.EXTRA_TITLE, BridgeProtocol.safeFileName(r.args.optString("name")));
        try { activity.startActivityForResult(intent, ShellActivity.REQUEST_SAVE); }
        catch (ActivityNotFoundException error) { pendingSave = null; settle(ShellActivity.REQUEST_SAVE, null, "unsupported", "Нет приложения для сохранения файлов"); }
    }

    private void shareFile(BridgeProtocol.Request r, JavaScriptReplyProxy reply) throws Exception {
        byte[] bytes = decode(r);
        if (bytes == null) { error(reply, r.id, "bad_request", "Файл пустой или больше 10 МБ"); return; }
        File dir = new File(activity.getCacheDir(), "shared");
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IllegalStateException("cache");
        File[] old = dir.listFiles();
        if (old != null) for (File file : old) if (System.currentTimeMillis() - file.lastModified() > 3_600_000L) file.delete();
        File file = new File(dir, BridgeProtocol.safeFileName(r.args.optString("name")));
        try (OutputStream out = new FileOutputStream(file)) { out.write(bytes); }
        Uri uri = FileProvider.getUriForFile(activity, activity.getPackageName() + ".files", file);
        String mime = BridgeProtocol.safeMime(r.args.optString("mime"));
        Intent intent = "file.open".equals(r.op)
            ? new Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime)
            : new Intent(Intent.ACTION_SEND).setType(mime).putExtra(Intent.EXTRA_STREAM, uri);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            activity.startActivity("file.open".equals(r.op) ? intent : Intent.createChooser(intent, "Отправить файл"));
            ok(reply, r.id, null);
        } catch (ActivityNotFoundException error) {
            error(reply, r.id, "unsupported", "Нет приложения, чтобы открыть этот файл");
        }
    }

    // ---------- AR ----------

    private void arMeasure(BridgeProtocol.Request r, JavaScriptReplyProxy reply) {
        if (!"supported".equals(ShellSupport.arStatus(activity).optString("status"))) {
            error(reply, r.id, "ar_unavailable", "AR-замер недоступен на этом устройстве. Введите размеры вручную.");
            return;
        }
        if (!begin(ShellActivity.REQUEST_AR, r.id, reply)) return;
        activity.withPermission(Manifest.permission.CAMERA, ShellActivity.PERMISSION_AR,
            () -> activity.startActivityForResult(new Intent(activity, ArMeasureActivity.class), ShellActivity.REQUEST_AR),
            () -> settle(ShellActivity.REQUEST_AR, null, "permission_denied", "Без доступа к камере AR-замер невозможен"));
    }

    // ---------- activity results ----------

    private final Map<Integer, JavaScriptReplyProxy> replies = new HashMap<>();

    private boolean begin(int code, String id, JavaScriptReplyProxy reply) {
        if (waiting.containsKey(code)) { error(reply, id, "busy", "Предыдущее действие ещё не завершено"); return false; }
        waiting.put(code, id);
        replies.put(code, reply);
        return true;
    }

    private void settle(int code, JSONObject value, String errorCode, String text) {
        String id = waiting.remove(code);
        JavaScriptReplyProxy reply = replies.remove(code);
        if (id == null || reply == null || closed) return;
        reply.postMessage(value != null ? BridgeProtocol.ok(id, value) : BridgeProtocol.error(id, errorCode, text));
    }

    void onActivityResult(int code, int result, Intent data) {
        try {
            if (code == ShellActivity.REQUEST_SPEECH) {
                ArrayList<String> heard = data == null ? null : data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
                if (result == Activity.RESULT_OK && heard != null && !heard.isEmpty())
                    settle(code, new JSONObject().put("text", heard.get(0)), null, null);
                else settle(code, null, "cancelled", "Распознавание отменено");
            } else if (code == ShellActivity.REQUEST_SAVE) {
                byte[] bytes = pendingSave;
                pendingSave = null;
                Uri target = data == null ? null : data.getData();
                if (result != Activity.RESULT_OK || target == null || bytes == null) { settle(code, null, "cancelled", "Сохранение отменено"); return; }
                try (OutputStream out = activity.getContentResolver().openOutputStream(target)) {
                    if (out == null) throw new java.io.IOException("stream");
                    out.write(bytes);
                }
                settle(code, new JSONObject().put("saved", true), null, null);
            } else if (code == ShellActivity.REQUEST_AR) {
                String rooms = data == null ? null : data.getStringExtra(ArMeasureActivity.EXTRA_ROOMS);
                if (result == Activity.RESULT_OK && rooms != null) settle(code, new JSONObject().put("rooms", new JSONArray(rooms)), null, null);
                else settle(code, null, "cancelled", "Замер отменён");
            }
        } catch (Exception error) {
            settle(code, null, "failed", "Не удалось завершить действие");
        }
    }

    // ---------- events ----------

    /** Sends an event, or keeps it until the page says hello after loading. */
    void event(String name, JSONObject data) {
        String payload = BridgeProtocol.event(name, data);
        if (page != null && !closed) page.postMessage(payload);
        else if (queued.size() < 20) queued.add(payload);
    }

    /** Text or a single file shared into Smetra from another app. */
    void shareIn(Intent intent) {
        try {
            JSONObject data = new JSONObject();
            CharSequence text = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
            if (text != null) data.put("text", text.toString().substring(0, Math.min(text.length(), 8000)));
            Uri stream = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if (stream != null) {
                String mime = BridgeProtocol.safeMime(activity.getContentResolver().getType(stream));
                try (InputStream in = activity.getContentResolver().openInputStream(stream)) {
                    if (in != null) {
                        java.io.ByteArrayOutputStream buffer = new java.io.ByteArrayOutputStream();
                        byte[] chunk = new byte[16384];
                        int count;
                        while ((count = in.read(chunk)) != -1 && buffer.size() <= MAX_FILE_BYTES) buffer.write(chunk, 0, count);
                        byte[] bytes = buffer.toByteArray();
                        if (bytes.length <= MAX_FILE_BYTES)
                            data.put("file", new JSONObject().put("name", BridgeProtocol.safeFileName(stream.getLastPathSegment()))
                                .put("mime", mime).put("base64", Base64.encodeToString(bytes, Base64.NO_WRAP)));
                    }
                }
            }
            if (data.length() > 0) event("share.received", data);
        } catch (Exception ignored) {
            // A share we cannot read is dropped; the app still opens normally.
        }
    }

    /** Page navigation after a push tap is done by loading the URL natively. */
    void close() { closed = true; page = null; queued.clear(); }

    private static void ok(JavaScriptReplyProxy reply, String id, JSONObject value) { reply.postMessage(BridgeProtocol.ok(id, value)); }
    private static void error(JavaScriptReplyProxy reply, String id, String code, String text) { reply.postMessage(BridgeProtocol.error(id, code, text)); }
}
