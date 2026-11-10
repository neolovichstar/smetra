package ru.smetra.mobile;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.provider.MediaStore;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.graphics.drawable.GradientDrawable;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.core.content.FileProvider;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;
import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.json.JSONObject;

/**
 * Native shell around the web cabinet. The interface itself is served by
 * smetra.online, so most updates need no new APK; this activity owns the
 * device: the secure WebView, sign-in, files, camera, permissions, push and
 * the bridge to native features.
 */
public final class ShellActivity extends Activity {
    static final int REQUEST_FILES = 11, REQUEST_SAVE = 12, REQUEST_AR = 13, REQUEST_SPEECH = 14;
    static final int PERMISSION_CAMERA = 21, PERMISSION_NOTIFICATIONS = 22, PERMISSION_AR = 23, PERMISSION_MICROPHONE = 24;
    private static final int DARK = 0xFF0B0B0C, LIGHT = 0xFFF7F7F5;

    private static final long READY_POLL_MS = 150, READY_LIMIT_MS = 15000;

    /** root spans the whole window (the loading cover lives here); content is inset from the system bars. */
    private FrameLayout root, content;
    private WebView web;
    private View cover;
    private StartupMark mark;
    private long coverShownAt;
    private int retries;
    private final Runnable scheduledRetry = this::retry;
    /** Never trap the user behind the mark, e.g. when a restored page fires no load events. */
    private final Runnable coverTimeout = this::coverTimedOut;
    private ShellBridge bridge;
    private ValueCallback<Uri[]> fileCallback;
    private Uri cameraOutput;
    private PermissionRequest pendingMediaRequest;
    private Runnable afterPermission;
    private ConnectivityManager.NetworkCallback network;
    private boolean pageReady, failed, dark = true;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (!ShellSupport.webViewUsable(this)) {
            // Very old or missing system WebView: keep the previous native app working.
            startActivity(new Intent(getIntent()).setClass(this, MainActivity.class));
            finish();
            return;
        }
        ShellSession.migrateLegacyToken(this);
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        content = new FrameLayout(this);
        root.addView(content, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        ShellFiles.pruneCache(this);
        applyWindowStyle();
        createWebView();
        showCover(null);
        if (state != null && web.restoreState(state) != null) {
            pageReady = true;
        } else {
            web.loadUrl(ShellSession.ORIGIN + initialPath(getIntent()));
        }
        // Android may recreate a killed activity when the OAuth Custom Tab
        // returns. onNewIntent is NOT called in that case.
        Uri launchLink = getIntent() == null ? null : getIntent().getData();
        if (launchLink != null && "smetra".equals(launchLink.getScheme())
                && "auth".equals(launchLink.getHost())) handleDeepLink(launchLink);
        ShellUpdates.check(this, bridge);
        watchNetwork();
    }

    // ---------- window ----------

    private void applyWindowStyle() {
        getWindow().setStatusBarColor(Color.TRANSPARENT);
        getWindow().setNavigationBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                content.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return WindowInsets.CONSUMED;
            });
        }
        setDarkChrome(true);
    }

    /** The page reports its theme so system bar icons stay readable. */
    void setDarkChrome(boolean value) {
        dark = value;
        root.setBackgroundColor(value ? DARK : LIGHT);
        if (web != null) web.setBackgroundColor(value ? DARK : LIGHT);
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController controller = getWindow().getInsetsController();
            if (controller != null) {
                int light = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                controller.setSystemBarsAppearance(value ? 0 : light, light);
            }
        } else {
            getWindow().setStatusBarColor(value ? DARK : LIGHT);
            getWindow().setNavigationBarColor(value ? DARK : LIGHT);
            // Android 8–10: dark icons on the light theme, otherwise they vanish on white.
            int flags = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            View decor = getWindow().getDecorView();
            decor.setSystemUiVisibility(value ? decor.getSystemUiVisibility() & ~flags : decor.getSystemUiVisibility() | flags);
        }
    }

    // ---------- web view ----------

    @SuppressLint("SetJavaScriptEnabled")
    private void createWebView() {
        web = new WebView(this);
        web.setBackgroundColor(DARK);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(false);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setGeolocationEnabled(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setSafeBrowsingEnabled(true);
        settings.setTextZoom(100);
        settings.setUserAgentString(settings.getUserAgentString() + " SmetraAndroid/" + BuildConfig.VERSION_NAME
            + " (" + BuildConfig.VERSION_CODE + ") SmetraBridge/" + BridgeProtocol.VERSION);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        bridge = new ShellBridge(this, web);
        // Only the exact app origin can see the bridge; iframes and other sites cannot.
        WebViewCompat.addWebMessageListener(web, "SmetraNative", Collections.singleton(ShellSession.ORIGIN), bridge);
        web.setWebViewClient(new ShellClient());
        web.setWebChromeClient(new ShellChrome());
        web.setDownloadListener((url, agent, disposition, mime, length) -> openExternal(Uri.parse(url)));
        content.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    }

    private final class ShellClient extends WebViewClient {
        @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri url = request.getUrl();
            String scheme = url.getScheme() == null ? "" : url.getScheme();
            if ("smetra".equals(scheme)) { handleDeepLink(url); return true; }
            if (BridgeProtocol.sameOrigin(url.toString(), ShellSession.ORIGIN)) {
                if (ShellAuth.interceptable(url)) {
                    try { ShellAuth.start(ShellActivity.this, url); }
                    catch (Exception error) { bridge.event("auth.error", ShellBridge.message("Не удалось открыть вход. Попробуйте ещё раз.")); }
                    return true;
                }
                return false;
            }
            if (!request.isForMainFrame()) return true;
            openExternal(url);
            return true;
        }

        @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) { failed = false; }

        @Override public void onPageFinished(WebView view, String url) {
            if (!failed) {
                pageReady = true;
                retries = 0;
                root.removeCallbacks(scheduledRetry);
                awaitAppReady();
            }
            CookieManager.getInstance().flush();
        }

        @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (!request.isForMainFrame()) return;
            failed = true;
            showCover("Нет соединения со Сметрой.\nПроверьте интернет — мы переподключимся сами.");
            scheduleRetry();
        }

        @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, android.webkit.WebResourceResponse response) {
            if (request.isForMainFrame() && response.getStatusCode() >= 500) {
                failed = true;
                showCover("Сметра обновляется или временно недоступна.\nПовторим через несколько секунд.");
                scheduleRetry();
            }
        }

        @Override public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
            // The renderer crashed or was killed for memory: rebuild instead of crashing the app.
            String url = view.getUrl();
            content.removeView(view);
            if (bridge != null) bridge.close();
            view.destroy();
            createWebView();
            web.loadUrl(url != null && BridgeProtocol.sameOrigin(url, ShellSession.ORIGIN) ? url : ShellSession.ORIGIN + "/app");
            return true;
        }
    }

    private final class ShellChrome extends WebChromeClient {
        @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
            if (fileCallback != null) fileCallback.onReceiveValue(null);
            fileCallback = callback;
            boolean imagesOnly = acceptsOnlyImages(params.getAcceptTypes());
            boolean multiple = params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE;
            if (params.isCaptureEnabled() && imagesOnly) {
                withPermission(Manifest.permission.CAMERA, PERMISSION_CAMERA, () -> openCamera(), () -> openPicker(params, imagesOnly, multiple));
            } else {
                openPicker(params, imagesOnly, multiple);
            }
            return true;
        }

        @Override public void onPermissionRequest(PermissionRequest request) {
            // Camera/microphone belong only to the app origin and need Android permission.
            if (!BridgeProtocol.sameOrigin(request.getOrigin().toString(), ShellSession.ORIGIN)) { request.deny(); return; }
            List<String> granted = new ArrayList<>();
            for (String resource : request.getResources()) if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource) || PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resource)) granted.add(resource);
            if (granted.isEmpty()) { request.deny(); return; }
            pendingMediaRequest = request;
            Runnable allow = () -> { if (pendingMediaRequest != request) return; request.grant(granted.toArray(new String[0])); pendingMediaRequest = null; };
            Runnable deny = () -> { if (pendingMediaRequest != request) return; request.deny(); pendingMediaRequest = null; };
            Runnable audio = () -> {
                if (pendingMediaRequest != request) return;
                if (granted.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) withPermission(Manifest.permission.RECORD_AUDIO, PERMISSION_MICROPHONE, allow, deny);
                else allow.run();
            };
            if (granted.contains(PermissionRequest.RESOURCE_VIDEO_CAPTURE)) withPermission(Manifest.permission.CAMERA, PERMISSION_CAMERA, audio, deny);
            else audio.run();
        }

        @Override public void onPermissionRequestCanceled(PermissionRequest request) { pendingMediaRequest = null; }
    }

    // ---------- files and camera ----------

    private static boolean acceptsOnlyImages(String[] types) {
        if (types == null || types.length == 0) return false;
        for (String type : types) if (type == null || !(type.startsWith("image/") || type.matches("\\.(jpe?g|png|webp|heic)"))) return false;
        return true;
    }

    private void openPicker(WebChromeClient.FileChooserParams params, boolean imagesOnly, boolean multiple) {
        Intent intent;
        if (imagesOnly && Build.VERSION.SDK_INT >= 33) {
            intent = new Intent(MediaStore.ACTION_PICK_IMAGES);
            if (multiple) intent.putExtra(MediaStore.EXTRA_PICK_IMAGES_MAX, 10);
        } else {
            intent = params.createIntent();
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            if (multiple) intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        }
        try { startActivityForResult(intent, REQUEST_FILES); }
        catch (ActivityNotFoundException error) { deliverFiles(null); }
    }

    private void openCamera() {
        try {
            File dir = new File(getCacheDir(), "captures");
            if (!dir.isDirectory() && !dir.mkdirs()) throw new IllegalStateException("cache");
            File photo = File.createTempFile("photo-", ".jpg", dir);
            cameraOutput = FileProvider.getUriForFile(this, getPackageName() + ".files", photo);
            Intent intent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE).putExtra(MediaStore.EXTRA_OUTPUT, cameraOutput)
                .addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            startActivityForResult(intent, REQUEST_FILES);
        } catch (Exception error) {
            cameraOutput = null;
            deliverFiles(null);
        }
    }

    private void deliverFiles(Uri[] files) {
        if (fileCallback != null) fileCallback.onReceiveValue(files);
        fileCallback = null;
        cameraOutput = null;
    }

    private static Uri[] collect(Intent data) {
        if (data == null) return null;
        ClipData clip = data.getClipData();
        if (clip != null && clip.getItemCount() > 0) {
            Uri[] uris = new Uri[Math.min(clip.getItemCount(), 20)];
            for (int i = 0; i < uris.length; i++) uris[i] = clip.getItemAt(i).getUri();
            return uris;
        }
        return data.getData() != null ? new Uri[]{data.getData()} : null;
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == REQUEST_FILES) {
            if (result != RESULT_OK) { deliverFiles(null); return; }
            if (cameraOutput != null && (data == null || data.getData() == null)) deliverFiles(new Uri[]{cameraOutput});
            else deliverFiles(collect(data));
            return;
        }
        bridge.onActivityResult(request, result, data);
    }

    // ---------- permissions ----------

    void withPermission(String permission, int code, Runnable granted, Runnable denied) {
        if (checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED) { granted.run(); return; }
        afterPermission = () -> {
            if (checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED) granted.run(); else denied.run();
        };
        requestPermissions(new String[]{permission}, code);
    }

    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        Runnable next = afterPermission;
        afterPermission = null;
        if (next != null) next.run();
    }

    // ---------- navigation and links ----------

    private String initialPath(Intent intent) {
        if (intent == null) return "/app";
        if ("ru.smetra.mobile.OPEN_NOTIFICATIONS".equals(intent.getAction())) return "/app#notifications";
        String path = intent.getStringExtra("smetra_path");
        if (path != null) return BridgeProtocol.safeAppPath(path);
        Uri data = intent.getData();
        if (data != null && "smetra".equals(data.getScheme()) && "quote".equals(data.getHost())) {
            String token = data.getQueryParameter("token");
            if (token != null && token.matches("[A-Za-z0-9_-]{8,200}")) return "/?quote=" + token;
        }
        return "/app";
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        Uri data = intent.getData();
        if (data != null && "smetra".equals(data.getScheme())) { handleDeepLink(data); return; }
        if (Intent.ACTION_SEND.equals(intent.getAction())) { bridge.shareIn(intent); return; }
        String path = initialPath(intent);
        if (!"/app".equals(path) || "ru.smetra.mobile.OPEN_NOTIFICATIONS".equals(intent.getAction())) web.loadUrl(ShellSession.ORIGIN + path);
    }

    private void handleDeepLink(Uri link) {
        if ("auth".equals(link.getHost())) {
            String ticket = link.getQueryParameter("ticket");
            String verifier = ShellAuth.takeVerifier(this);
            showCover(null);
            new Thread(() -> {
                String error = ShellAuth.exchange(ticket, verifier);
                if (error == null) {
                    // A successful ticket exchange is not enough: verify the
                    // WebView session before leaving the registration screen.
                    try {
                        if (!ShellSession.call("GET", "/api/me", null, true).ok())
                            error = "Сессия не сохранилась. Повторите вход.";
                    } catch (Exception ignored) {
                        error = "Не удалось проверить сессию. Проверьте соединение.";
                    }
                }
                final String resultError = error;
                runOnUiThread(() -> {
                    if (resultError == null) {
                        web.loadUrl(ShellSession.ORIGIN + "/app#dashboard");
                    } else {
                        hideCover();
                        bridge.event("auth.error", ShellBridge.message(resultError));
                    }
                });
            }, "smetra-auth").start();
            return;
        }
        if ("quote".equals(link.getHost())) web.loadUrl(ShellSession.ORIGIN + initialPath(new Intent(Intent.ACTION_VIEW, link)));
    }

    void openExternal(Uri url) {
        String scheme = url.getScheme() == null ? "" : url.getScheme();
        if (!scheme.equals("https") && !scheme.equals("http") && !scheme.equals("mailto") && !scheme.equals("tel")) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW, url).addCategory(Intent.CATEGORY_BROWSABLE)); }
        catch (ActivityNotFoundException ignored) { }
    }

    @Override public void onBackPressed() {
        if (web == null) { super.onBackPressed(); return; }
        // The page closes its own dialogs, panels and sub-pages first.
        web.evaluateJavascript("(window.SmetraShell&&window.SmetraShell.handleBack&&window.SmetraShell.handleBack())?'1':'0'", value -> {
            if ("\"1\"".equals(value)) return;
            if (web.canGoBack()) web.goBack();
            else moveTaskToBack(true);
        });
    }

    // ---------- loading and offline ----------

    /**
     * Full-window cover: the animated mark sits exactly where the system
     * splash icon was. With a message it stops moving and shows the reason
     * and a retry button underneath, keeping the mark in place.
     */
    private void showCover(String message) {
        int ink = dark ? 0xFFFFFFFF : 0xFF111111;
        float density = getResources().getDisplayMetrics().density;
        if (cover == null) {
            FrameLayout box = new FrameLayout(this);
            box.setBackgroundColor(dark ? Color.BLACK : LIGHT);
            box.setClickable(true);
            mark = new StartupMark(this, ink);
            box.addView(mark, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
            cover = box;
            root.addView(box, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        }
        FrameLayout box = (FrameLayout) cover;
        box.animate().cancel();
        box.setAlpha(1f);
        if (box.getChildCount() > 1) box.removeViewAt(1);
        mark.setAnimating(message == null);
        mark.setAlpha(message == null ? 1f : 0.35f);
        root.removeCallbacks(coverTimeout);
        if (message == null) {
            box.setContentDescription("Загрузка");
            coverShownAt = SystemClock.uptimeMillis();
            root.postDelayed(coverTimeout, READY_LIMIT_MS);
            return;
        }
        int pad = Math.round(32 * density);
        LinearLayout notice = new LinearLayout(this);
        notice.setOrientation(LinearLayout.VERTICAL);
        notice.setGravity(Gravity.CENTER_HORIZONTAL);
        notice.setPadding(pad, 0, pad, 0);
        TextView text = new TextView(this);
        text.setText(message);
        text.setTextSize(15);
        text.setLineSpacing(0, 1.25f);
        text.setGravity(Gravity.CENTER);
        text.setTextColor(dark ? 0x99FFFFFF : 0x99111111);
        notice.addView(text);
        TextView again = new TextView(this);
        again.setText("Повторить");
        again.setTextSize(15);
        again.setTextColor(ink);
        again.setGravity(Gravity.CENTER);
        again.setMinHeight(Math.round(44 * density));
        again.setPadding(Math.round(24 * density), 0, Math.round(24 * density), 0);
        GradientDrawable pill = new GradientDrawable();
        pill.setCornerRadius(999 * density);
        pill.setStroke(Math.max(1, Math.round(density)), dark ? 0x40FFFFFF : 0x33111111);
        again.setBackground(pill);
        again.setFocusable(true);
        again.setClickable(true);
        again.setOnClickListener(v -> { retries = 0; retry(); });
        LinearLayout.LayoutParams button = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        button.topMargin = Math.round(20 * density);
        notice.addView(again, button);
        // Below the mark, whose centre stays at the centre of the window.
        box.addView(notice, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER));
        notice.setVisibility(View.INVISIBLE);
        StartupMark current = mark;
        notice.post(() -> {
            notice.setTranslationY(current.halfHeight() + 40 * density + notice.getHeight() / 2f);
            notice.setVisibility(View.VISIBLE);
        });
        box.setContentDescription(message);
        box.announceForAccessibility(message);
    }

    /**
     * The page has loaded, but /app still runs its own boot (session, data).
     * Keep the native mark until the cabinet leaves the boot state, so the
     * user sees one loading screen instead of two.
     */
    private void awaitAppReady() {
        if (cover == null || web == null) return;
        if (SystemClock.uptimeMillis() - coverShownAt > READY_LIMIT_MS) { hideCover(); return; }
        web.evaluateJavascript("(function(){var b=document.body;if(!b)return'wait';"
            + "if(!b.classList.contains('smetra-app-booting'))return'ready';"
            + "var r=document.getElementById('app-startup-retry');return r&&!r.hidden?'ready':'wait'})()", value -> {
            if (cover == null || failed) return;
            if ("\"ready\"".equals(value)) hideCover();
            else root.postDelayed(this::awaitAppReady, READY_POLL_MS);
        });
    }

    private void coverTimedOut() { if (!failed) hideCover(); }

    private void hideCover() {
        if (cover == null) return;
        View old = cover;
        cover = null;
        mark = null;
        root.removeCallbacks(coverTimeout);
        old.animate().alpha(0f).setDuration(200).withEndAction(() -> root.removeView(old)).start();
    }

    /** Server or network trouble: retry on our own with backoff (3, 6, 12, 24, 30 s). */
    private void scheduleRetry() {
        root.removeCallbacks(scheduledRetry);
        long delay = Math.min(30000L, 3000L << Math.min(retries, 4));
        retries++;
        root.postDelayed(scheduledRetry, delay);
    }

    void retry() {
        if (web == null) return;
        root.removeCallbacks(scheduledRetry);
        showCover(null);
        String url = web.getUrl();
        if (url == null || !BridgeProtocol.sameOrigin(url, ShellSession.ORIGIN)) web.loadUrl(ShellSession.ORIGIN + "/app");
        else web.reload();
    }

    private void watchNetwork() {
        ConnectivityManager manager = getSystemService(ConnectivityManager.class);
        if (manager == null) return;
        network = new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network n) { runOnUiThread(() -> { if (failed) { retries = 0; retry(); } }); }
        };
        try { manager.registerDefaultNetworkCallback(network); } catch (RuntimeException ignored) { network = null; }
    }

    // ---------- lifecycle ----------

    @Override protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
        if (web != null && ShellAuth.pending(this)) bridge.event("auth.returned", new JSONObject());
    }

    @Override protected void onPause() {
        if (web != null) web.onPause();
        CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        if (web != null) web.saveState(out);
    }

    @Override protected void onDestroy() {
        ShellAds.release(this);
        if (network != null) {
            ConnectivityManager manager = getSystemService(ConnectivityManager.class);
            try { if (manager != null) manager.unregisterNetworkCallback(network); } catch (RuntimeException ignored) { }
        }
        if (root != null) { root.removeCallbacks(scheduledRetry); root.removeCallbacks(coverTimeout); }
        if (pendingMediaRequest != null) pendingMediaRequest.deny();
        if (bridge != null) bridge.close();
        if (web != null) {
            content.removeView(web);
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }

    WebView webView() { return web; }
}
