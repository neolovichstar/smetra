package ru.smetra.mobile;

import android.app.Activity;
import android.os.Handler;
import android.os.Looper;
import com.yandex.mobile.ads.common.AdError;
import com.yandex.mobile.ads.common.AdRequest;
import com.yandex.mobile.ads.common.AdRequestError;
import com.yandex.mobile.ads.common.ImpressionData;
import com.yandex.mobile.ads.common.YandexAds;
import com.yandex.mobile.ads.rewarded.Reward;
import com.yandex.mobile.ads.rewarded.RewardedAd;
import com.yandex.mobile.ads.rewarded.RewardedAdEventListener;
import com.yandex.mobile.ads.rewarded.RewardedAdLoadListener;
import com.yandex.mobile.ads.rewarded.RewardedAdLoader;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

/**
 * Rewarded video for the free plan. The page only asks to show an ad; native
 * code starts a server attempt, shows the video and claims with the attempt's
 * nonce. The nonce and session never reach JavaScript, and the server decides
 * eligibility and the amount.
 */
final class ShellAds {
    interface Result { void done(JSONObject result, String errorCode, String message); }

    private static final ExecutorService IO = Executors.newSingleThreadExecutor();
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static boolean initialized;
    private static boolean running;

    private ShellAds() {}

    static void show(Activity activity, Result result) {
        if (running) { result.done(null, "busy", "Видео уже запускается"); return; }
        running = true;
        IO.execute(() -> {
            try {
                ShellSession.Response attempt = ShellSession.call("POST", "/api/assistant/ad-reward",
                    new JSONObject().put("operation", "start"), true);
                if (!attempt.ok()) { finish(result, null, "not_available", attempt.message("Видео сейчас недоступно")); return; }
                String unit = attempt.body.optString("ad_unit_id", "");
                if (unit.isEmpty()) { finish(result, null, "not_available", "Видео сейчас недоступно"); return; }
                MAIN.post(() -> load(activity, unit, attempt.body, result));
            } catch (Exception error) {
                finish(result, null, "network", "Нет соединения. Попробуйте позже.");
            }
        });
    }

    private static void load(Activity activity, String unit, JSONObject attempt, Result result) {
        if (activity.isFinishing()) { finish(result, null, "cancelled", "Экран закрыт"); return; }
        Runnable request = () -> {
            RewardedAdLoader loader = new RewardedAdLoader(activity);
            loader.loadAd(new AdRequest.Builder(unit).build(), new RewardedAdLoadListener() {
                @Override public void onAdLoaded(RewardedAd ad) { play(activity, ad, attempt, result); }
                @Override public void onAdFailedToLoad(AdRequestError error) {
                    finish(result, null, "load_failed", "Реклама сейчас недоступна. Попробуйте позже.");
                }
            });
        };
        if (initialized) { request.run(); return; }
        try {
            // The SDK starts only after the user explicitly asks for a rewarded video.
            YandexAds.initialize(activity, () -> MAIN.post(() -> { initialized = true; request.run(); }));
        } catch (RuntimeException error) {
            finish(result, null, "load_failed", "Не удалось запустить рекламу");
        }
    }

    private static void play(Activity activity, RewardedAd ad, JSONObject attempt, Result result) {
        final boolean[] rewarded = {false};
        ad.setAdEventListener(new RewardedAdEventListener() {
            @Override public void onAdShown() { }
            @Override public void onAdFailedToShow(AdError error) {
                ad.setAdEventListener(null);
                finish(result, null, "show_failed", "Не удалось показать видео");
            }
            @Override public void onAdDismissed() {
                ad.setAdEventListener(null);
                if (!rewarded[0]) finish(result, null, "not_completed", "Чтобы получить токены, досмотрите видео до конца");
            }
            @Override public void onAdClicked() { }
            @Override public void onAdImpression(ImpressionData data) { }
            @Override public void onRewarded(Reward reward) {
                if (rewarded[0]) return;
                rewarded[0] = true;
                claim(attempt, result);
            }
        });
        ad.show(activity);
    }

    private static void claim(JSONObject attempt, Result result) {
        IO.execute(() -> {
            try {
                JSONObject body = new JSONObject()
                    .put("attempt_id", attempt.optString("attempt_id"))
                    .put("nonce", attempt.optString("nonce"));
                ShellSession.Response claimed = ShellSession.call("POST", "/api/assistant/ad-reward", body, true);
                if (!claimed.ok()) { finish(result, null, "claim_failed", claimed.message("Не удалось начислить награду")); return; }
                JSONObject safe = new JSONObject()
                    .put("granted", claimed.body.optLong("granted"))
                    .put("unit", claimed.body.optString("unit", "tokens"));
                if (claimed.body.has("quota")) safe.put("quota", claimed.body.getJSONObject("quota"));
                finish(result, safe, null, null);
            } catch (Exception error) {
                finish(result, null, "network", "Нет соединения. Награда сохранится, попробуйте ещё раз.");
            }
        });
    }

    private static void finish(Result result, JSONObject value, String code, String message) {
        MAIN.post(() -> { running = false; result.done(value, code, message); });
    }
}
