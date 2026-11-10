package ru.smetra.mobile;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import com.my.target.ads.Reward;
import com.my.target.ads.RewardedAd;
import com.my.target.common.MyTargetPrivacy;
import com.my.target.common.models.IAdLoadingError;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Supplier;
import org.json.JSONObject;

/** Nonces never leave native code. Pending earned claims survive Activity/process loss. */
final class ShellAds {
    interface Result { void done(JSONObject result, String errorCode, String message); }
    private static final ExecutorService IO = Executors.newSingleThreadExecutor();
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static volatile Flow current;
    private ShellAds() { }
    static boolean isRunning() { return current != null; }
    private static SharedPreferences prefs(Context c) { return c.getSharedPreferences("smetra-earned-ads", Context.MODE_PRIVATE); }
    private static final class Flow {
        final Activity activity;
        final Result result;
        final String token;
        final Supplier<String> session;
        String owner;
        JSONObject attempt;
        RewardedAd ad;
        boolean earned, dismissed, claiming;
        Runnable watchdog;
        Flow(Activity a, Result r, Supplier<String> source) { activity = a; result = r; session = source; token = source.get(); }
    }
    static void show(Activity activity, Result result) { show(activity, ShellSession::token, result); }
    static void show(Activity activity, Supplier<String> session, Result result) { begin(activity, session, result, false); }
    static void recover(Activity activity, Result result) {
        if (prefs(activity).getAll().isEmpty()) { result.done(new JSONObject(), null, null); return; }
        begin(activity, ShellSession::token, result, true);
    }
    private static boolean live(Flow flow) { return current == flow && !flow.activity.isFinishing() && !flow.activity.isDestroyed(); }
    private static void begin(Activity activity, Supplier<String> session, Result result, boolean recovery) {
        if (current != null) { result.done(null, "busy", "Видео уже запускается"); return; }
        Flow flow = new Flow(activity, result, session);
        if (flow.token == null) { result.done(null, "unauthorized", "Войдите, чтобы получить награду"); return; }
        current = flow;
        IO.execute(() -> {
            try {
                ShellSession.Response me = ShellSession.callWithSession("GET", "/api/me", null, flow.token);
                if (!me.ok()) { finish(flow, null, "unauthorized", "Войдите, чтобы получить награду"); return; }
                flow.owner = me.body.getJSONObject("user").getString("id");
                String saved = prefs(activity).getString("pending:" + flow.owner, "");
                if (!saved.isEmpty()) {
                    try { flow.attempt = new JSONObject(saved); }
                    catch (Exception error) { prefs(activity).edit().remove("pending:" + flow.owner).commit(); }
                    if (flow.attempt != null) { flow.earned = true; claim(flow); return; }
                }
                if (recovery) { finish(flow, new JSONObject(), null, null); return; }
                ShellSession.Response response = ShellSession.callWithSession("POST", "/api/assistant/ad-reward", new JSONObject().put("operation", "start").put("provider", "vk"), flow.token);
                if (!response.ok()) { finish(flow, null, "not_available", response.message("Видео сейчас недоступно")); return; }
                String unit = response.body.optString("ad_unit_id");
                if (!"vk".equals(response.body.optString("provider")) || !unit.matches("[1-9][0-9]{0,9}") || Long.parseLong(unit) > Integer.MAX_VALUE) { finish(flow, null, "not_available", "Рекламный блок ещё не подключён"); return; }
                flow.attempt = response.body;
                MAIN.post(() -> load(flow, unit));
            } catch (Exception error) { finish(flow, null, "network", "Нет соединения. Попробуйте позже."); }
        });
    }
    private static void load(Flow flow, String unit) {
        if (!live(flow)) { finish(flow, null, "cancelled", "Экран закрыт"); return; }
        flow.watchdog = () -> finish(flow, null, "load_failed", "Видео не загрузилось. Попробуйте позже.");
        MAIN.postDelayed(flow.watchdog, 60_000);
        try {
            // No profile, estimate, location, VK ID or custom user ID is sent to ads.
            // Consent for personalized advertising has not been requested.
            MyTargetPrivacy.setUserConsent(false);
            RewardedAd ad = new RewardedAd(Integer.parseInt(unit), flow.activity);
            flow.ad = ad;
            ad.setListener(new RewardedAd.RewardedAdListener() {
                @Override public void onLoad(RewardedAd loaded) {
                    if (!live(flow)) { loaded.setListener(null); loaded.dismiss(); return; }
                    MAIN.removeCallbacks(flow.watchdog);
                    try { loaded.show(); }
                    catch (RuntimeException error) { finish(flow, null, "show_failed", "Не удалось показать видео"); }
                }
                @Override public void onNoAd(IAdLoadingError error, RewardedAd loaded) { finish(flow, null, "load_failed", "Реклама сейчас недоступна. Попробуйте позже."); }
                @Override public void onDisplay(RewardedAd shown) { }
                @Override public void onClick(RewardedAd clicked) { }
                @Override public void onFailedToShow(RewardedAd failed) { finish(flow, null, "show_failed", "Не удалось показать видео"); }
                @Override public void onDismiss(RewardedAd dismissed) {
                    if (!live(flow)) return;
                    flow.dismissed = true;
                    if (flow.earned) {
                        claim(flow);
                    } else {
                        // Some SDK versions deliver onReward just after the
                        // close callback. Keep the flow valid briefly rather
                        // than denying an earned reward due to event order.
                        MAIN.postDelayed(() -> {
                            if (!live(flow)) return;
                            if (flow.earned) claim(flow);
                            else finish(flow, null, "not_completed", "Чтобы получить токены, досмотрите видео до конца");
                        }, 900);
                    }
                }
                @Override public void onReward(Reward reward, RewardedAd rewarded) {
                    if (!live(flow) || flow.earned) return;
                    flow.earned = true;
                    // App-private storage; no bearer token, account password or ad content.
                    prefs(flow.activity).edit().putString("pending:" + flow.owner, flow.attempt.toString()).commit();
                    if (flow.dismissed) claim(flow);
                }
            });
            ad.load();
        } catch (RuntimeException error) { finish(flow, null, "load_failed", "Не удалось загрузить видео"); }
    }
    private static void claim(Flow flow) {
        synchronized (flow) { if (flow.claiming) return; flow.claiming = true; }
        IO.execute(() -> {
            for (int retry = 0; retry < 3; retry++) {
                try {
                    JSONObject body = new JSONObject().put("attempt_id", flow.attempt.getString("attempt_id")).put("nonce", flow.attempt.getString("nonce"));
                    ShellSession.Response response = ShellSession.callWithSession("POST", "/api/assistant/ad-reward", body, flow.token);
                    if (response.ok()) {
                        prefs(flow.activity).edit().remove("pending:" + flow.owner).commit();
                        JSONObject safe = new JSONObject().put("granted", response.body.optLong("granted")).put("unit", "tokens");
                        if (response.body.has("quota")) safe.put("quota", response.body.getJSONObject("quota"));
                        finish(flow, safe, null, null); return;
                    }
                    if (response.status < 500 && response.status != 429) {
                        if (response.status != 401 && response.status != 403) prefs(flow.activity).edit().remove("pending:" + flow.owner).commit();
                        finish(flow, null, "claim_failed", response.message("Не удалось начислить награду")); return;
                    }
                } catch (Exception ignored) { }
                if (retry < 2) try { Thread.sleep(1000L * (retry + 1)); } catch (InterruptedException error) { Thread.currentThread().interrupt(); break; }
            }
            finish(flow, null, "claim_pending", "Просмотр сохранён на устройстве. Повторим начисление при следующем входе; не очищайте данные приложения.");
        });
    }
    static void release(Activity activity) {
        Flow flow = current;
        if (flow != null && flow.activity == activity) finish(flow, null, "cancelled", "Экран закрыт");
    }
    private static void finish(Flow flow, JSONObject value, String code, String text) {
        MAIN.post(() -> {
            if (current != flow) return;
            current = null;
            if (flow.watchdog != null) MAIN.removeCallbacks(flow.watchdog);
            if (flow.ad != null) { flow.ad.setListener(null); flow.ad.dismiss(); }
            flow.ad = null;
            if (!flow.token.equals(flow.session.get())) { flow.result.done(null, "account_changed", "Аккаунт изменился. Откройте баланс после входа."); return; }
            flow.result.done(value, code, text);
        });
    }
}
