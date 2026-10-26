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
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
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

    private FrameLayout root;
    private WebView web;
    private View cover;
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
        root.setBackgroundColor(DARK);
        setContentView(root);
        applyWindowStyle();
        createWebView();
        showCover(null);
        if (state != null && web.restoreState(state) != null) {
            pageReady = true;
        } else {
            web.loadUrl(ShellSession.ORIGIN + initialPath(getIntent()));
        }
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
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
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
        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
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
            if (!failed) { pageReady = true; hideCover(); }
            CookieManager.getInstance().flush();
        }

        @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (!request.isForMainFrame()) return;
            failed = true;
            showCover("Нет соединения с Сметрой. Проверьте интернет — мы переподключимся сами.");
        }

        @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, android.webkit.WebResourceResponse response) {
            if (request.isForMainFrame() && response.getStatusCode() >= 500) {
                failed = true;
                showCover("Сметра обновляется или временно недоступна. Повторим через несколько секунд.");
                root.postDelayed(ShellActivity.this::retry, 5000);
            }
        }

        @Override public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
            // The renderer crashed or was killed for memory: rebuild instead of crashing the app.
            String url = view.getUrl();
            root.removeView(view);
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
            // Only the app origin may use the microphone, and only after the user allows it.
            if (!BridgeProtocol.sameOrigin(request.getOrigin().toString(), ShellSession.ORIGIN)) { request.deny(); return; }
            List<String> granted = new ArrayList<>();
            for (String resource : request.getResources()) if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(resource)) granted.add(resource);
            if (granted.isEmpty()) { request.deny(); return; }
            pendingMediaRequest = request;
            withPermission(Manifest.permission.RECORD_AUDIO, PERMISSION_MICROPHONE,
                () -> { request.grant(granted.toArray(new String[0])); pendingMediaRequest = null; },
                () -> { request.deny(); pendingMediaRequest = null; });
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
                runOnUiThread(() -> {
                    if (error == null) web.loadUrl(ShellSession.ORIGIN + "/app");
                    else { hideCover(); bridge.event("auth.error", ShellBridge.message(error)); }
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

    private void showCover(String message) {
        if (cover != null) root.removeView(cover);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        box.setBackgroundColor(dark ? DARK : LIGHT);
        int pad = (int) (32 * getResources().getDisplayMetrics().density);
        box.setPadding(pad, pad, pad, pad);
        TextView mark = new TextView(this);
        mark.setText("сметра.");
        mark.setTextSize(28);
        mark.setTextColor(dark ? 0xFFF5F5F4 : 0xFF111111);
        mark.setTypeface(android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL));
        box.addView(mark);
        if (message == null) {
            ProgressBar spinner = new ProgressBar(this);
            spinner.setIndeterminate(true);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(pad, pad);
            lp.topMargin = pad / 2;
            box.addView(spinner, lp);
        } else {
            TextView text = new TextView(this);
            text.setText(message);
            text.setTextSize(15);
            text.setGravity(Gravity.CENTER);
            text.setTextColor(dark ? 0xFFA1A1A0 : 0xFF555555);
            text.setPadding(0, pad / 2, 0, pad / 2);
            box.addView(text);
            Button retry = new Button(this);
            retry.setText("Повторить");
            retry.setAllCaps(false);
            retry.setOnClickListener(v -> retry());
            box.addView(retry);
        }
        cover = box;
        root.addView(box, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        if (message == null) root.postDelayed(() -> { if (!pageReady && !failed && cover == box) hideCover(); }, 12000);
    }

    private void hideCover() {
        if (cover == null) return;
        View old = cover;
        cover = null;
        old.animate().alpha(0f).setDuration(180).withEndAction(() -> root.removeView(old)).start();
    }

    void retry() {
        if (web == null) return;
        showCover(null);
        String url = web.getUrl();
        if (url == null || !BridgeProtocol.sameOrigin(url, ShellSession.ORIGIN)) web.loadUrl(ShellSession.ORIGIN + "/app");
        else web.reload();
    }

    private void watchNetwork() {
        ConnectivityManager manager = getSystemService(ConnectivityManager.class);
        if (manager == null) return;
        network = new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network n) { runOnUiThread(() -> { if (failed) retry(); }); }
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
        if (network != null) {
            ConnectivityManager manager = getSystemService(ConnectivityManager.class);
            try { if (manager != null) manager.unregisterNetworkCallback(network); } catch (RuntimeException ignored) { }
        }
        if (pendingMediaRequest != null) pendingMediaRequest.deny();
        if (bridge != null) bridge.close();
        if (web != null) {
            root.removeView(web);
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }

    WebView webView() { return web; }
}
