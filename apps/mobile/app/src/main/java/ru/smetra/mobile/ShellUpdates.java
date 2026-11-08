package ru.smetra.mobile;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import org.json.JSONObject;

/**
 * Web releases update the interface without a new APK. Native capabilities
 * still ship in the APK, so the server says which shell versions it supports:
 * below the minimum the page shows a blocking update screen, below the latest
 * it offers an update without interrupting work.
 */
final class ShellUpdates {
    static final String STORE_URL = "https://www.rustore.ru/catalog/app/ru.smetra.mobile";

    private ShellUpdates() {}

    static void check(Activity activity, ShellBridge bridge) {
        // A one-off daemon thread: an executor here was never shut down and kept a thread alive.
        Thread worker = new Thread(() -> {
            try {
                ShellSession.Response response = ShellSession.call("GET", "/api/mobile/compat", null, false);
                if (!response.ok()) return;
                JSONObject body = response.body;
                int minimum = body.optInt("min_version_code", 0), latest = body.optInt("latest_version_code", 0);
                if (BuildConfig.VERSION_CODE >= latest && BuildConfig.VERSION_CODE >= minimum) return;
                JSONObject data = new JSONObject()
                    .put("required", BuildConfig.VERSION_CODE < minimum)
                    .put("version_code", BuildConfig.VERSION_CODE)
                    .put("latest_version_code", latest)
                    .put("message", body.optString("message", ""));
                activity.runOnUiThread(() -> bridge.event("app.update", data));
            } catch (Exception ignored) {
                // Offline or an older server: keep working with what is installed.
            }
        }, "smetra-update-check");
        worker.setDaemon(true);
        worker.start();
    }

    static void openStore(Activity activity) {
        Intent store = new Intent(Intent.ACTION_VIEW, Uri.parse("rustore://apps.rustore.ru/app/" + activity.getPackageName()));
        try { activity.startActivity(store); }
        catch (ActivityNotFoundException error) {
            try { activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(STORE_URL))); } catch (ActivityNotFoundException ignored) { }
        }
    }
}
