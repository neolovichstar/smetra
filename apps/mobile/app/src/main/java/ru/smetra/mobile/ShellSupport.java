package ru.smetra.mobile;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.os.Build;
import android.webkit.WebView;
import androidx.webkit.WebViewFeature;
import com.google.ar.core.ArCoreApk;
import org.json.JSONObject;

/** Device checks that decide which native features the web cabinet may offer. */
final class ShellSupport {
    private ShellSupport() {}

    /** The shell needs a system WebView that supports origin-restricted messaging. */
    static boolean webViewUsable(Context context) {
        try {
            PackageInfo provider = Build.VERSION.SDK_INT >= 26 ? WebView.getCurrentWebViewPackage() : null;
            return provider != null && WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER);
        } catch (RuntimeException error) {
            return false;
        }
    }

    /**
     * ARCore is optional: many phones sold in Russia have no Google Play
     * Services for AR. "supported" means the AR screen can start (possibly
     * after installing the AR component); anything else falls back to manual input.
     */
    static JSONObject arStatus(Context context) {
        String status;
        try {
            ArCoreApk.Availability availability = ArCoreApk.getInstance().checkAvailability(context);
            if (availability.isTransient()) status = "checking";
            else if (availability == ArCoreApk.Availability.SUPPORTED_INSTALLED
                || availability == ArCoreApk.Availability.SUPPORTED_APK_TOO_OLD
                || availability == ArCoreApk.Availability.SUPPORTED_NOT_INSTALLED) status = "supported";
            else status = "unsupported";
        } catch (RuntimeException | LinkageError error) {
            status = "unsupported";
        }
        try { return new JSONObject().put("status", status); } catch (org.json.JSONException error) { return new JSONObject(); }
    }
}
