package ru.smetra.mobile;

import android.content.Context;
import android.graphics.Color;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Validated, cached presentation data for the existing native screens. */
final class MobilePresentation {
    private static final String CACHE = "native_presentation_v1";
    private static final int DEFAULT_BLUE = Color.rgb(130, 177, 255);
    final int version, accent;
    final String homeEyebrow, homeTitle, createLabel, captureLabel, loginTitle, loginSubtitle;
    final String raw;

    private MobilePresentation(int version, int accent, String eyebrow, String title,
                               String create, String capture, String loginTitle, String loginSubtitle,
                               String raw) {
        this.version = version;
        this.accent = accent;
        this.homeEyebrow = eyebrow;
        this.homeTitle = title;
        this.createLabel = create;
        this.captureLabel = capture;
        this.loginTitle = loginTitle;
        this.loginSubtitle = loginSubtitle;
        this.raw = raw;
    }

    static MobilePresentation defaults() {
        return new MobilePresentation(0, DEFAULT_BLUE, "ОБЗОР", "Сметры", "Создать смету",
            "Разобрать запрос", "Ваша работа.\nВсё в порядке.",
            "Сметы, клиенты и согласования.\nОдин аккаунт на всех устройствах.", "");
    }

    static MobilePresentation cached(Context context) {
        String raw = context.getSharedPreferences(CACHE, Context.MODE_PRIVATE).getString("json", "");
        try { return parse(raw); } catch (Exception ignored) { return defaults(); }
    }

    static MobilePresentation fetch(String origin) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(origin + "/api/mobile/presentation").openConnection();
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(5000);
        connection.setRequestProperty("Accept", "application/json");
        try {
            if (connection.getResponseCode() != 200) throw new IllegalStateException("Presentation unavailable");
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) {
                byte[] buffer = new byte[2048]; int count;
                while ((count = input.read(buffer)) != -1) {
                    if (bytes.size() + count > 8192) throw new IllegalArgumentException("Presentation too large");
                    bytes.write(buffer, 0, count);
                }
            }
            return parse(bytes.toString(StandardCharsets.UTF_8.name()));
        } finally { connection.disconnect(); }
    }

    static MobilePresentation parse(String raw) throws Exception {
        if (raw == null || raw.isEmpty() || raw.length() > 8192) throw new IllegalArgumentException("Invalid presentation");
        JSONObject value = new JSONObject(raw);
        if (value.optInt("schema") != 1 || value.optInt("version") < 1) throw new IllegalArgumentException("Unsupported presentation");
        String hex = value.optString("accent", "#82B1FF");
        if (!hex.matches("#[0-9A-Fa-f]{6}")) throw new IllegalArgumentException("Invalid accent");
        JSONObject home = value.getJSONObject("home"), login = value.getJSONObject("login");
        MobilePresentation fallback = defaults();
        return new MobilePresentation(value.getInt("version"), Color.parseColor(hex),
            text(home, "eyebrow", fallback.homeEyebrow, 30),
            text(home, "title", fallback.homeTitle, 45),
            text(home, "create", fallback.createLabel, 45),
            text(home, "capture", fallback.captureLabel, 45),
            text(login, "title", fallback.loginTitle, 90),
            text(login, "subtitle", fallback.loginSubtitle, 150), raw);
    }

    private static String text(JSONObject source, String key, String fallback, int max) {
        String result = source.optString(key, fallback).trim();
        if (result.isEmpty() || result.length() > max) return fallback;
        for (int i = 0; i < result.length(); i++) if (result.charAt(i) < 32 && result.charAt(i) != '\n') return fallback;
        return result;
    }

    void apply(Context context) {
        SmetraUi.BLUE = accent;
        if (!raw.isEmpty()) context.getSharedPreferences(CACHE, Context.MODE_PRIVATE).edit().putString("json", raw).apply();
    }
}
