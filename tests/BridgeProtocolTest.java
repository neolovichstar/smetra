package ru.smetra.mobile;

import org.json.JSONObject;

public final class BridgeProtocolTest {
    private static void check(boolean value, String message) { if (!value) throw new AssertionError(message); }
    private static String code(String raw) {
        try { BridgeProtocol.parse(raw); return "ok"; }
        catch (BridgeProtocol.BridgeException error) { return error.code; }
    }
    public static void main(String[] args) throws Exception {
        BridgeProtocol.Request request = BridgeProtocol.parse("{\"v\":1,\"id\":\"r1\",\"op\":\"app.hello\"}");
        check(request.op.equals("app.hello") && request.args.length() == 0, "Valid hello request should parse with empty args");
        check(code(null).equals("bad_request") && code("").equals("bad_request") && code("{").equals("bad_request"), "Malformed messages are rejected");
        check(code("{\"v\":2,\"id\":\"r1\",\"op\":\"app.hello\"}").equals("unsupported_version"), "Unknown protocol version is rejected");
        check(code("{\"v\":1,\"id\":\"r 1\",\"op\":\"app.hello\"}").equals("bad_request"), "Ids are restricted to a safe alphabet");
        check(code("{\"v\":1,\"id\":\"r1\",\"op\":\"sql.run\"}").equals("unknown_operation"), "Operations outside the allowlist are rejected");
        for (String operation : new String[]{"device.haptic", "device.copyText", "device.shareText",
                "device.biometric.status", "vision.image.scan"}) {
            String requestJson = new JSONObject().put("v", 1).put("id", "native")
                .put("op", operation).put("args", new JSONObject()).toString();
            check(BridgeProtocol.parse(requestJson).op.equals(operation), "Native operation must be explicitly allowlisted: " + operation);
        }

        check(code("{\"v\":1,\"id\":\"r1\",\"op\":\"file.save\",\"args\":[1]}").equals("bad_request"), "Args must be an object");
        check(BridgeProtocol.idOf("{\"id\":\"abc\"}").equals("abc") && BridgeProtocol.idOf("{\"id\":\"<x>\"}").isEmpty() && BridgeProtocol.idOf("nope").isEmpty(), "Request id recovery is safe");

        JSONObject ok = new JSONObject(BridgeProtocol.ok("r1", null));
        check(ok.getBoolean("ok") && ok.getInt("v") == 1 && ok.getJSONObject("result").length() == 0, "Ok reply shape");
        JSONObject error = new JSONObject(BridgeProtocol.error("r1", "denied", "Нет"));
        check(!error.getBoolean("ok") && error.getJSONObject("error").getString("code").equals("denied"), "Error reply shape");
        check(new JSONObject(BridgeProtocol.event("app.update", null)).getString("event").equals("app.update"), "Event shape");

        check(BridgeProtocol.trustedOrigin("https://smetra.online", "https://smetra.online"), "Production origin is trusted");
        check(!BridgeProtocol.trustedOrigin("https://evil.example", "https://smetra.online"), "Other origins are not trusted");
        check(!BridgeProtocol.trustedOrigin("http://example.invalid", "http://example.invalid"), "Plain HTTP origins are never trusted");
        check(BridgeProtocol.trustedOrigin("http://10.0.2.2:8080", "http://10.0.2.2:8080"), "Emulator loopback fixture is trusted");
        check(!BridgeProtocol.trustedOrigin(null, "https://smetra.online"), "Missing origin is not trusted");
        check(BridgeProtocol.originOf("https://smetra.online/app#x").equals("https://smetra.online"), "Origin drops the path");
        check(BridgeProtocol.sameOrigin("https://smetra.online/app", "https://smetra.online"), "Same origin navigation stays inside");
        check(!BridgeProtocol.sameOrigin("https://smetra.online.evil.example/app", "https://smetra.online"), "Lookalike hosts leave the app");
        check(!BridgeProtocol.sameOrigin("javascript:alert(1)", "https://smetra.online"), "Script URLs are not same origin");

        check(BridgeProtocol.safeAppPath("/app#assistant").equals("/app#assistant"), "In-app hash path is kept");
        check(BridgeProtocol.safeAppPath("/?quote=abc").equals("/?quote=abc"), "Quote links are kept");
        check(BridgeProtocol.safeAppPath("//evil.example/app").equals("/app"), "Protocol-relative paths are dropped");
        check(BridgeProtocol.safeAppPath("https://evil.example").equals("/app"), "Absolute URLs are dropped");
        check(BridgeProtocol.safeAppPath("/admin").equals("/app"), "Paths outside the app are dropped");
        check(BridgeProtocol.safeAppPath("/app#\n").equals("/app"), "Control characters are dropped");

        check(BridgeProtocol.safeFileName("../../etc/passwd").equals(".._.._etc_passwd"), "Separators are replaced");
        check(BridgeProtocol.safeFileName("..").equals("smetra-file") && BridgeProtocol.safeFileName(null).equals("smetra-file"), "Empty and dot names get a default");
        check(BridgeProtocol.safeFileName("a".repeat(200) + ".pdf").endsWith(".pdf"), "Long names keep their extension");
        check(BridgeProtocol.safeMime("application/pdf; charset=binary").equals("application/pdf"), "Known MIME types are normalized");
        check(BridgeProtocol.safeMime("text/html").equals("application/octet-stream"), "Active content is not shared as HTML");
        System.out.println("PASS: bridge protocol parsing, replies, origins, deep links, file names and MIME types");
    }
}
