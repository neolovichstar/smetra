package ru.smetra.mobile;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import android.view.Gravity;
import android.view.View;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Thin, origin-bound shell. Product screens are published at /app. */
public final class WebActivity extends Activity {
    private static final int PICK_FILE = 41, SAVE_FILE = 42;
    private static final String ORIGIN = BuildConfig.API_BASE_URL;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private WebView web;
    private LinearLayout message;
    private android.webkit.ValueCallback<Uri[]> fileCallback;
    private byte[] pendingFile;
    private boolean loadFailed;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.BLACK);
        getWindow().setNavigationBarColor(Color.BLACK);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        web = new WebView(this);
        web.setBackgroundColor(Color.BLACK);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        // The user-selected content:// URI from the Android picker is needed for uploads.
        web.getSettings().setAllowContentAccess(true);
        web.getSettings().setAllowFileAccessFromFileURLs(false);
        web.getSettings().setAllowUniversalAccessFromFileURLs(false);
        web.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.getSettings().setJavaScriptCanOpenWindowsAutomatically(false);
        web.getSettings().setUserAgentString(web.getSettings().getUserAgentString() + " SmetraAndroid/1");
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.setVerticalScrollBarEnabled(false);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.addJavascriptInterface(new NativeActions(), "SmetraNative");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (!request.isForMainFrame()) return false;
                return navigate(request.getUrl());
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!loadFailed && trusted(Uri.parse(url))) message.setVisibility(View.GONE);
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) { loadFailed = true; showMessage("Нет соединения с Сметрой", "Повторить"); }
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, android.webkit.WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 500) { loadFailed = true; showMessage("Сервис временно недоступен", "Повторить"); }
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, android.webkit.ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                try { startActivityForResult(intent, PICK_FILE); }
                catch (Exception error) { fileCallback = null; callback.onReceiveValue(null); toast("Не удалось открыть файлы"); }
                return true;
            }
        });
        web.setDownloadListener((url, agent, disposition, type, length) -> {
            Uri uri = Uri.parse(url);
            if (trusted(uri) && uri.getPath() != null && uri.getPath().startsWith("/api/public/")) {
                String name = android.webkit.URLUtil.guessFileName(url, disposition, type);
                fetchDownload(uri.getEncodedPath() + (uri.getEncodedQuery() == null ? "" : "?" + uri.getEncodedQuery()), name, "");
            } else toast("Скачивание доступно только со Сметры");
        });
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        message = new LinearLayout(this);
        message.setOrientation(LinearLayout.VERTICAL);
        message.setGravity(Gravity.CENTER);
        message.setPadding(40, 40, 40, 40);
        message.setBackgroundColor(Color.BLACK);
        TextView title = new TextView(this);
        title.setTextColor(Color.WHITE);
        title.setTextSize(22);
        title.setGravity(Gravity.CENTER);
        title.setText("Открываем Сметру…");
        message.addView(title);
        Button retry = new Button(this);
        retry.setText("Повторить");
        retry.setOnClickListener(v -> { loadFailed = false; message.setVisibility(View.VISIBLE); migrateAndLoad(); });
        retry.setVisibility(View.GONE);
        message.addView(retry);
        message.setTag(new View[]{title, retry});
        root.addView(message, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        migrateAndLoad();
    }

    private boolean trusted(Uri uri) {
        Uri base = Uri.parse(ORIGIN);
        return "https".equals(uri.getScheme()) && base.getHost().equalsIgnoreCase(uri.getHost())
            && (uri.getPort() == -1 || uri.getPort() == 443);
    }

    private boolean navigate(Uri uri) {
        if (trusted(uri)) {
            String path = uri.getPath();
            if (path != null && path.matches("/api/auth/oauth/(yandex|vk|mail|ok)/start")) {
                if ("1".equals(uri.getQueryParameter("link"))) {
                    toast("Привяжите способ входа на сайте в браузере");
                    openExternal(Uri.parse(ORIGIN + "/app#settings"));
                } else startIdentity(path.split("/")[4]);
                return true;
            }
            if ("1".equals(uri.getQueryParameter("external")) && "/app".equals(path)) {
                openExternal(Uri.parse(ORIGIN + "/app" + (uri.getFragment() == null ? "" : "#" + uri.getFragment())));
                return true;
            }
            return false;
        }
        if ("about".equals(uri.getScheme())) return false;
        if ("https".equals(uri.getScheme())) openExternal(uri);
        return true;
    }

    private void openExternal(Uri uri) {
        try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
        catch (Exception error) { toast("Не удалось открыть браузер"); }
    }

    private void startIdentity(String provider) {
        try {
            byte[] bytes = new byte[48]; new SecureRandom().nextBytes(bytes);
            String verifier = android.util.Base64.encodeToString(bytes, android.util.Base64.URL_SAFE | android.util.Base64.NO_WRAP | android.util.Base64.NO_PADDING);
            String challenge = android.util.Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(verifier.getBytes(StandardCharsets.UTF_8)), android.util.Base64.URL_SAFE | android.util.Base64.NO_WRAP | android.util.Base64.NO_PADDING);
            getSharedPreferences("MainActivity", MODE_PRIVATE).edit().putString("oauth_verifier", verifier).apply();
            openExternal(Uri.parse(ORIGIN + "/api/auth/oauth/" + provider + "/start?app_challenge=" + challenge));
        } catch (Exception error) { toast("Не удалось начать вход"); }
    }

    private void migrateAndLoad() {
        loadFailed = false;
        String token = new TokenVault(this).read();
        if (token == null) { web.loadUrl(ORIGIN + "/app"); return; }
        worker.execute(() -> {
            String cookie = null;
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(ORIGIN + "/api/auth/native/web-session").openConnection();
                connection.setRequestMethod("POST");
                connection.setConnectTimeout(10000);
                connection.setReadTimeout(10000);
                connection.setRequestProperty("Authorization", "Bearer " + token);
                connection.setRequestProperty("Content-Length", "0");
                if (connection.getResponseCode() == 200) cookie = connection.getHeaderField("Set-Cookie");
            } catch (Exception ignored) {
            } finally { if (connection != null) connection.disconnect(); }
            final String result = cookie;
            runOnUiThread(() -> {
                if (isFinishing()) return;
                if (result != null && result.startsWith("session=")) {
                    CookieManager.getInstance().setCookie(ORIGIN, result, done -> {
                        CookieManager.getInstance().flush();
                        web.loadUrl(ORIGIN + "/app");
                    });
                } else web.loadUrl(ORIGIN + "/app");
            });
        });
    }

    private void showMessage(String text, String action) {
        View[] views = (View[]) message.getTag();
        ((TextView) views[0]).setText(text);
        ((Button) views[1]).setText(action);
        views[1].setVisibility(View.VISIBLE);
        message.setVisibility(View.VISIBLE);
    }

    private void toast(String text) { runOnUiThread(() -> Toast.makeText(this, text, Toast.LENGTH_LONG).show()); }

    public final class NativeActions {
        @JavascriptInterface public void signedOut() {
            try { new TokenVault(WebActivity.this).save(null); } catch (Exception ignored) {}
        }
        @JavascriptInterface public void download(String path, String filename, String workspace) {
            if (path == null || !path.matches("/(documents/[A-Za-z0-9_-]+/pdf|files/[A-Za-z0-9_-]+|transfer/[A-Za-z0-9_-]+\\?format=csv)")) return;
            if (workspace == null || !workspace.matches("[A-Za-z0-9_-]{0,80}")) return;
            fetchDownload("/api" + path, filename, workspace);
        }
    }

    private void fetchDownload(String path, String filename, String workspace) {
        if (pendingFile != null) { toast("Сначала сохраните предыдущий файл"); return; }
        worker.execute(() -> {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(ORIGIN + path).openConnection();
                connection.setConnectTimeout(10000);
                connection.setReadTimeout(20000);
                String cookies = CookieManager.getInstance().getCookie(ORIGIN);
                if (cookies != null) connection.setRequestProperty("Cookie", cookies);
                if (!workspace.isEmpty()) connection.setRequestProperty("X-Workspace-Id", workspace);
                if (connection.getResponseCode() != 200) throw new IllegalStateException("Файл недоступен");
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                try (InputStream input = connection.getInputStream()) {
                    byte[] buffer = new byte[8192]; int count;
                    while ((count = input.read(buffer)) != -1) {
                        if (out.size() + count > 8_000_000) throw new IllegalStateException("Файл слишком большой");
                        out.write(buffer, 0, count);
                    }
                }
                byte[] bytes = out.toByteArray();
                runOnUiThread(() -> {
                    pendingFile = bytes;
                    String safe = filename == null ? "smetra-file" : filename.replaceAll("[^\\p{L}\\p{N}._-]", "_");
                    Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE);
                    intent.setType(safe.endsWith(".pdf") ? "application/pdf" : safe.endsWith(".csv") ? "text/csv" : "application/octet-stream");
                    intent.putExtra(Intent.EXTRA_TITLE, safe);
                    try { startActivityForResult(intent, SAVE_FILE); }
                    catch (Exception error) { pendingFile = null; toast("Не удалось сохранить файл"); }
                });
            } catch (Exception error) { toast(error.getMessage() == null ? "Не удалось скачать файл" : error.getMessage()); }
            finally { if (connection != null) connection.disconnect(); }
        });
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == PICK_FILE && fileCallback != null) {
            fileCallback.onReceiveValue(result == RESULT_OK && data != null && data.getData() != null ? new Uri[]{data.getData()} : null);
            fileCallback = null;
        } else if (request == SAVE_FILE) {
            byte[] bytes = pendingFile; pendingFile = null;
            if (result == RESULT_OK && data != null && data.getData() != null && bytes != null) {
                try (OutputStream output = getContentResolver().openOutputStream(data.getData())) {
                    if (output == null) throw new IllegalStateException();
                    output.write(bytes);
                    toast("Файл сохранён");
                } catch (Exception error) { toast("Не удалось записать файл"); }
            }
        }
    }

    @Override public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        loadFailed = false;
        message.setVisibility(View.VISIBLE);
        migrateAndLoad();
    }

    @Override protected void onDestroy() {
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        worker.shutdownNow();
        web.destroy();
        super.onDestroy();
    }
}
