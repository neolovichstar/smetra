package ru.smetra.mobile;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import ru.rustore.sdk.review.RuStoreReviewManager;
import ru.rustore.sdk.review.RuStoreReviewManagerFactory;

/** The store owns its dialog and may decline to display it. Never infer a rating. */
final class ShellReviews {
    private static volatile boolean running;
    private ShellReviews() { }
    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences("smetra-review", Context.MODE_PRIVATE);
    }
    static void installed(Context context) {
        SharedPreferences p = prefs(context);
        if (!p.contains("first_seen")) p.edit().putLong("first_seen", System.currentTimeMillis()).apply();
    }
    static void qualify(Activity activity, String key) {
        if (key == null || !key.matches("[A-Za-z0-9_:-]{1,120}") || activity.isFinishing() || activity.isDestroyed()) return;
        SharedPreferences p = prefs(activity);
        if (key.equals(p.getString("last_event", ""))) return;
        int actions = Math.min(10000, p.getInt("actions", 0) + 1);
        p.edit().putString("last_event", key).putInt("actions", actions).apply();
        long now = System.currentTimeMillis();
        long lastFailure = p.getLong("last_failure", 0);
        if (running || ShellAds.isRunning() || (lastFailure > 0 && now - lastFailure < ReviewPolicy.DAY)
                || !ReviewPolicy.eligible(now, p.getLong("first_seen", 0), p.getLong("last_attempt", 0), actions)) return;
        running = true;
        try {
            RuStoreReviewManager manager = RuStoreReviewManagerFactory.INSTANCE.create(activity);
            manager.requestReviewFlow().addOnSuccessListener(info -> activity.runOnUiThread(() -> {
                if (activity.isFinishing() || activity.isDestroyed() || ShellAds.isRunning()) { running = false; return; }
                try {
                    p.edit().putLong("last_attempt", System.currentTimeMillis()).apply();
                    manager.launchReviewFlow(info).addOnSuccessListener(unit -> running = false)
                        .addOnFailureListener(error -> running = false);
                } catch (RuntimeException error) { running = false; }
            })).addOnFailureListener(error -> { p.edit().putLong("last_failure", System.currentTimeMillis()).apply(); running = false; });
        } catch (RuntimeException error) { p.edit().putLong("last_failure", System.currentTimeMillis()).apply(); running = false; }
    }
}
