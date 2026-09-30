package ru.smetra.mobile;

import android.app.Application;
import com.my.tracker.MyTracker;
import com.my.tracker.MyTrackerConfig;
import com.my.tracker.MyTrackerParams;
import org.json.JSONObject;
import java.util.HashMap;
import java.util.Map;

/** Centralized, privacy-minimized product analytics for attribution and funnel events. */
final class Analytics {
    private static volatile boolean enabled;

    private Analytics() {}

    static void init(Application app) {
        String key = BuildConfig.MYTRACKER_SDK_KEY == null ? "" : BuildConfig.MYTRACKER_SDK_KEY.trim();
        if (key.isEmpty()) return;
        try {
            MyTrackerConfig config = MyTracker.getTrackerConfig();
            config.setAutotrackingPurchaseEnabled(false);
            config.setBufferingPeriod(60);
            config.setForcingPeriod(86400);
            MyTracker.setDebugMode(BuildConfig.DEBUG);
            MyTracker.initTracker(key, app);
            enabled = true;
        } catch (Throwable ignored) {
            enabled = false;
        }
    }

    static void identify(JSONObject user) {
        if (!enabled || user == null) return;
        String id = user.optString("id", "").trim();
        if (id.isEmpty()) return;
        try { MyTracker.getTrackerParams().setCustomUserId(id); } catch (Throwable ignored) {}
    }

    static void clearUser() {
        if (!enabled) return;
        try { MyTracker.getTrackerParams().setCustomUserId(""); } catch (Throwable ignored) {}
    }

    static void registration(JSONObject user) {
        if (!enabled || user == null) return;
        String id = user.optString("id", "").trim();
        if (id.isEmpty()) return;
        identify(user);
        try { MyTracker.trackRegistrationEvent(id, null); MyTracker.flush(); } catch (Throwable ignored) {}
    }

    static void login(JSONObject user) {
        if (!enabled || user == null) return;
        String id = user.optString("id", "").trim();
        if (id.isEmpty()) return;
        identify(user);
        try { MyTracker.trackLoginEvent(id, null); MyTracker.flush(); } catch (Throwable ignored) {}
    }

    static void event(String name) { event(name, null, false); }
    static void critical(String name) { event(name, null, true); }

    static void event(String name, Map<String, String> params, boolean flush) {
        if (!enabled || name == null || name.isBlank()) return;
        try {
            if (params == null || params.isEmpty()) MyTracker.trackEvent(name);
            else MyTracker.trackEvent(name, params);
            if (flush) MyTracker.flush();
        } catch (Throwable ignored) {}
    }

    static Map<String, String> params(String... pairs) {
        HashMap<String, String> result = new HashMap<>();
        if (pairs == null) return result;
        for (int i = 0; i + 1 < pairs.length; i += 2) {
            String key = pairs[i], value = pairs[i + 1];
            if (key == null || value == null) continue;
            key = key.length() > 255 ? key.substring(0, 255) : key;
            value = value.length() > 255 ? value.substring(0, 255) : value;
            result.put(key, value);
        }
        return result;
    }
}
