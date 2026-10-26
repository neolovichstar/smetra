package ru.smetra.mobile;

import android.content.Context;
import android.webkit.CookieManager;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.json.JSONObject;

/**
 * The web UI and native code share one server session: the HttpOnly "session"
 * cookie in the WebView cookie jar. Native calls read it from CookieManager and
 * send it as a bearer token; it is never handed to page JavaScript.
 */
final class ShellSession {
    static final String ORIGIN = BridgeProtocol.originOf(BuildConfig.API_BASE_URL);
    private static final String COOKIE = "session";
    private static final int MAX_RESPONSE = 1024 * 1024;

    private ShellSession() {}

    /** Current session token from the cookie jar, or null when signed out. */
    static String token() {
        String cookies = CookieManager.getInstance().getCookie(ORIGIN);
        if (cookies == null) return null;
        for (String part : cookies.split(";")) {
            String item = part.trim();
            if (item.startsWith(COOKIE + "=")) {
                String value = item.substring(COOKIE.length() + 1);
                return value.matches("[A-Za-z0-9_-]{20,200}") ? value : null;
            }
        }
        return null;
    }

    /**
     * Users of the previous native app keep their session: the encrypted bearer
     * token becomes the same server session cookie, then leaves the vault.
     */
    static void migrateLegacyToken(Context context) {
        TokenVault vault = new TokenVault(context);
        String legacy = vault.read();
        if (legacy == null || !legacy.matches("[A-Za-z0-9_-]{20,200}")) return;
        if (token() == null) {
            CookieManager.getInstance().setCookie(ORIGIN, cookieHeader(legacy, 30L * 86400));
            CookieManager.getInstance().flush();
        }
        try { vault.save(null); } catch (Exception ignored) { }
    }

    static String cookieHeader(String token, long maxAge) {
        return COOKIE + "=" + token + "; Path=/; HttpOnly; SameSite=Lax; Max-Age=" + maxAge
            + (ORIGIN.startsWith("https://") ? "; Secure" : "");
    }

    /** Stores Set-Cookie headers from a native response in the WebView jar. */
    static boolean adoptCookies(Map<String, List<String>> headers) {
        boolean adopted = false;
        for (Map.Entry<String, List<String>> header : headers.entrySet()) {
            if (header.getKey() == null || !header.getKey().equalsIgnoreCase("Set-Cookie")) continue;
            for (String value : header.getValue()) {
                if (value != null && value.startsWith(COOKIE + "=")) {
                    CookieManager.getInstance().setCookie(ORIGIN, value);
                    adopted = true;
                }
            }
        }
        if (adopted) CookieManager.getInstance().flush();
        return adopted;
    }

    static final class Response {
        final int status;
        final JSONObject body;
        final Map<String, List<String>> headers;
        Response(int status, JSONObject body, Map<String, List<String>> headers) { this.status = status; this.body = body; this.headers = headers; }
        boolean ok() { return status >= 200 && status < 300; }
        String message(String fallback) {
            String error = body == null ? "" : body.optString("error", "");
            return error.isEmpty() ? fallback : error;
        }
    }

    /** Blocking JSON call to the Smetra API; run off the main thread. */
    static Response call(String method, String path, JSONObject payload, boolean authenticated) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(ORIGIN + path).openConnection();
        try {
            connection.setRequestMethod(method);
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(20000);
            connection.setInstanceFollowRedirects(false);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("X-Smetra-Client", "android-shell/" + BuildConfig.VERSION_CODE);
            if (authenticated) {
                String session = token();
                if (session == null) return new Response(401, new JSONObject().put("error", "Войдите в аккаунт"), java.util.Collections.emptyMap());
                connection.setRequestProperty("Authorization", "Bearer " + session);
            }
            if (payload != null) {
                byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                connection.setFixedLengthStreamingMode(body.length);
                try (OutputStream out = connection.getOutputStream()) { out.write(body); }
            }
            int status = connection.getResponseCode();
            InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            JSONObject json = new JSONObject();
            if (stream != null) try (InputStream in = stream; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192];
                int count, total = 0;
                while ((count = in.read(buffer)) != -1) {
                    total += count;
                    if (total > MAX_RESPONSE) throw new java.io.IOException("Response too large");
                    out.write(buffer, 0, count);
                }
                String text = out.toString("UTF-8").trim();
                if (text.startsWith("{")) json = new JSONObject(text);
            }
            return new Response(status, json, connection.getHeaderFields());
        } finally {
            connection.disconnect();
        }
    }
}
