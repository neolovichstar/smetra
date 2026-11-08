package ru.smetra.mobile;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.util.Base64;
import androidx.browser.customtabs.CustomTabColorSchemeParams;
import androidx.browser.customtabs.CustomTabsIntent;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import org.json.JSONObject;

/**
 * Sign-in with an identity provider in the system browser (Custom Tabs), never
 * in the WebView. PKCE: the verifier is sealed with Android Keystore, the browser
 * only sees its SHA-256 challenge. The server returns a one-time ticket to
 * smetra://auth; native code exchanges ticket + verifier for the HttpOnly
 * session cookie and puts it into the WebView jar. No token reaches JS.
 */
final class ShellAuth {
    private static final String PREFS = "smetra_shell_auth";
    private static final String VERIFIER = "verifier";
    private static final String STARTED = "started_at";
    private static final long TTL_MS = 10 * 60 * 1000L;

    private ShellAuth() {}

    /**
     * Starts sign-in from an intercepted web navigation to
     * /api/auth/oauth/{provider}/start, keeping only the parameters the server
     * understands (intent and the registration consent pair).
     */
    static void start(Activity activity, Uri webStart) throws Exception {
        java.util.List<String> segments = webStart.getPathSegments();
        String provider = segments.size() == 5 ? segments.get(3) : "";
        if (!"google".equals(provider) && !"yandex".equals(provider)) throw new IllegalArgumentException("provider");
        String intent = "register".equals(webStart.getQueryParameter("intent")) ? "register" : "login";
        byte[] bytes = new byte[48];
        new SecureRandom().nextBytes(bytes);
        int flags = Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING;
        String verifier = Base64.encodeToString(bytes, flags);
        String challenge = Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(verifier.getBytes(StandardCharsets.US_ASCII)), flags);
        clearLegacy(activity);
        new TokenVault(activity,"oauth_pkce").save(new JSONObject().put(VERIFIER,verifier)
            .put(STARTED,System.currentTimeMillis()).toString());
        Uri.Builder url = Uri.parse(ShellSession.ORIGIN + "/api/auth/oauth/" + provider + "/start").buildUpon()
            .appendQueryParameter("app_challenge", challenge)
            .appendQueryParameter("intent", intent);
        String legal = webStart.getQueryParameter("legal_version");
        if ("1".equals(webStart.getQueryParameter("legal_acceptance")) && legal != null && legal.matches("[A-Za-z0-9._-]{1,60}"))
            url.appendQueryParameter("legal_acceptance", "1").appendQueryParameter("legal_version", legal);
        CustomTabsIntent tab = new CustomTabsIntent.Builder()
            .setDefaultColorSchemeParams(new CustomTabColorSchemeParams.Builder().setToolbarColor(0xFF0B0B0C).build())
            .setShowTitle(true)
            .build();
        tab.launchUrl(activity, url.build());
    }

    /** True while a browser sign-in started by this app is still pending. */
    static boolean pending(Context context) {
        return challenge(context)!=null;
    }

    /** Account linking needs the WebView session, so it stays in the WebView flow. */
    static boolean interceptable(Uri url) {
        java.util.List<String> segments = url.getPathSegments();
        return segments.size() == 5 && "api".equals(segments.get(0)) && "auth".equals(segments.get(1))
            && "oauth".equals(segments.get(2)) && "start".equals(segments.get(4))
            && !"1".equals(url.getQueryParameter("link")) && url.getQueryParameter("app_challenge") == null;
    }

    /** Verifier for a pending sign-in, consumed once. */
    static String takeVerifier(Context context) {
        JSONObject value=challenge(context);
        try{new TokenVault(context,"oauth_pkce").save(null);}catch(Exception error){return null;}
        return value==null?null:value.optString(VERIFIER,null);
    }

    /** Blocking exchange; returns null on success or a user-facing error. */
    static String exchange(String ticket, String verifier) {
        if (ticket == null || !ticket.matches("[A-Za-z0-9_-]{16,200}") || verifier == null) return "Ссылка входа недействительна. Повторите вход.";
        try {
            ShellSession.Response response = ShellSession.call("POST", "/api/auth/native/exchange",
                new JSONObject().put("ticket", ticket).put("verifier", verifier), false);
            if (!response.ok()) return response.message("Не удалось войти. Повторите попытку.");
            if (!ShellSession.adoptCookies(response.headers)) {
                // Older servers only return the bearer token for native clients.
                String token = response.body.optString("token", "");
                if (!token.matches("[A-Za-z0-9_-]{20,200}")) return "Сервер не вернул сессию. Повторите вход.";
                android.webkit.CookieManager.getInstance().setCookie(ShellSession.ORIGIN, ShellSession.cookieHeader(token, 30L * 86400));
                android.webkit.CookieManager.getInstance().flush();
            }
            return null;
        } catch (Exception error) {
            return "Нет соединения с сервером. Проверьте интернет и повторите вход.";
        }
    }

    private static void clearLegacy(Context context) {
        SharedPreferences legacy=context.getApplicationContext().getSharedPreferences(PREFS,Context.MODE_PRIVATE);
        if(legacy.contains(VERIFIER)||legacy.contains(STARTED))legacy.edit().clear().apply();
    }

    private static JSONObject challenge(Context context) {
        clearLegacy(context);
        try{
            String sealed=new TokenVault(context,"oauth_pkce").read();
            if(sealed==null)return null;
            JSONObject value=new JSONObject(sealed);
            long age=System.currentTimeMillis()-value.optLong(STARTED,0);
            return age>=0&&age<TTL_MS&&value.optString(VERIFIER,"").matches("[A-Za-z0-9_-]{43,128}")?value:null;
        }catch(Exception error){return null;}
    }
}
