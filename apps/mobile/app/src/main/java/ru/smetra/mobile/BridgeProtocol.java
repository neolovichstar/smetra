package ru.smetra.mobile;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.regex.Pattern;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Wire format of the web ↔ Android bridge. Pure Java so it is unit-testable on
 * the JVM. Requests: {"v":1,"id":"r1","op":"app.capabilities","args":{}}.
 * Replies: {"v":1,"id":"r1","ok":true,"result":{}} or
 * {"v":1,"id":"r1","ok":false,"error":{"code":"…","message":"…"}}.
 * Events: {"v":1,"event":"push.open","data":{}}.
 */
final class BridgeProtocol {
    static final int VERSION = 1;
    /** Base64 file payloads are capped well below WebView message limits. */
    static final int MAX_MESSAGE_CHARS = 14 * 1024 * 1024;
    static final Set<String> OPERATIONS = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
        "app.hello", "app.capabilities", "app.openStore", "app.openExternal",
        "auth.start",
        "request.cancel",
        "speech.recognize",
        "ads.rewarded.show",
        "push.status", "push.enable", "push.disable",
        "file.save", "file.share", "file.open",
        "ar.status", "ar.measure"
    )));
    private static final Pattern ID = Pattern.compile("[A-Za-z0-9_-]{1,64}");

    static final class Request {
        final String id, op;
        final JSONObject args;
        Request(String id, String op, JSONObject args) { this.id = id; this.op = op; this.args = args; }
    }

    static final class BridgeException extends Exception {
        final String code;
        BridgeException(String code, String message) { super(message); this.code = code; }
    }

    private BridgeProtocol() {}

    /** Parses and validates one message; never trusts types or sizes from the page. */
    static Request parse(String raw) throws BridgeException {
        if (raw == null || raw.isEmpty()) throw new BridgeException("bad_request", "Пустое сообщение");
        if (raw.length() > MAX_MESSAGE_CHARS) throw new BridgeException("too_large", "Слишком большое сообщение");
        JSONObject message;
        try { message = new JSONObject(raw); }
        catch (JSONException error) { throw new BridgeException("bad_request", "Некорректный формат"); }
        if (message.optInt("v", -1) != VERSION) throw new BridgeException("unsupported_version", "Версия протокола не поддерживается");
        String id = message.optString("id", "");
        if (!ID.matcher(id).matches()) throw new BridgeException("bad_request", "Некорректный идентификатор запроса");
        String op = message.optString("op", "");
        if (!OPERATIONS.contains(op)) throw new BridgeException("unknown_operation", "Операция недоступна");
        Object args = message.opt("args");
        if (args != null && args != JSONObject.NULL && !(args instanceof JSONObject))
            throw new BridgeException("bad_request", "Аргументы должны быть объектом");
        return new Request(id, op, args instanceof JSONObject ? (JSONObject) args : new JSONObject());
    }

    /** Request id when parsing failed, so the page can still settle its promise. */
    static String idOf(String raw) {
        try {
            String id = new JSONObject(raw).optString("id", "");
            return ID.matcher(id).matches() ? id : "";
        } catch (Exception error) { return ""; }
    }

    static String ok(String id, JSONObject result) {
        try { return new JSONObject().put("v", VERSION).put("id", id).put("ok", true).put("result", result == null ? new JSONObject() : result).toString(); }
        catch (JSONException error) { throw new IllegalStateException(error); }
    }

    static String error(String id, String code, String message) {
        try {
            return new JSONObject().put("v", VERSION).put("id", id).put("ok", false)
                .put("error", new JSONObject().put("code", code).put("message", message)).toString();
        } catch (JSONException error) { throw new IllegalStateException(error); }
    }

    static String event(String name, JSONObject data) {
        try { return new JSONObject().put("v", VERSION).put("event", name).put("data", data == null ? new JSONObject() : data).toString(); }
        catch (JSONException error) { throw new IllegalStateException(error); }
    }

    /** Only the configured HTTPS origin (or loopback for debug fixtures) may talk to the bridge. */
    static boolean trustedOrigin(String origin, String expected) {
        return origin != null && expected != null && origin.equals(expected)
            && (expected.startsWith("https://") || expected.matches("http://(127\\.0\\.0\\.1|10\\.0\\.2\\.2)(:\\d+)?"));
    }

    /** scheme://host[:port] of a base URL, without path. */
    static String originOf(String base) {
        java.net.URI uri = java.net.URI.create(base);
        String origin = uri.getScheme() + "://" + uri.getHost();
        return uri.getPort() > 0 ? origin + ":" + uri.getPort() : origin;
    }

    /** Same-origin check for navigation: everything else leaves the app container. */
    static boolean sameOrigin(String url, String origin) {
        if (url == null) return false;
        try { return originOf(url).equals(origin); } catch (Exception error) { return false; }
    }

    /** Only relative in-app paths may be opened from push or deep links. */
    static String safeAppPath(String path) {
        if (path == null || path.isEmpty()) return "/app";
        if (!path.startsWith("/") || path.startsWith("//") || path.contains("\\") || path.length() > 300) return "/app";
        if (!(path.equals("/app") || path.startsWith("/app#") || path.startsWith("/app?") || path.startsWith("/?quote="))) return "/app";
        for (char c : path.toCharArray()) if (c < 0x20 || c == 0x7f) return "/app";
        return path;
    }

    /** File names coming from the page are reduced to a safe display name. */
    static String safeFileName(String name) {
        String clean = name == null ? "" : name.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", "_").trim();
        if (clean.isEmpty() || clean.equals(".") || clean.equals("..")) clean = "smetra-file";
        return clean.length() > 120 ? clean.substring(clean.length() - 120) : clean;
    }

    static final Set<String> SHAREABLE_MIME = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
        "application/pdf", "text/csv", "text/plain", "image/png", "image/jpeg", "image/webp",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip", "application/json", "application/octet-stream"
    )));

    static String safeMime(String mime) {
        String value = mime == null ? "" : mime.split(";")[0].trim().toLowerCase(java.util.Locale.ROOT);
        return SHAREABLE_MIME.contains(value) ? value : "application/octet-stream";
    }
}
