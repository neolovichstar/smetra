package ru.smetra.mobile;

import android.app.Activity;
import android.os.Handler;
import android.os.Looper;
import com.my.target.ads.Reward;
import com.my.target.ads.RewardedAd;
import com.my.target.common.models.IAdLoadingError;

/**
 * VK Ads (myTarget) rewarded video. Only invoked by an explicit user tap.
 * No bonus is granted by load/display/close: only the SDK reward callback
 * may enter the existing authenticated, daily-limited server claim flow.
 *
 * Slot format must be Rewarded in the VK publisher dashboard.
 */
final class VkRewardedAds {
    interface Listener {
        void loaded();
        void unavailable();
        void shown();
        void closed();
        void rewarded();
    }

    private final Handler main = new Handler(Looper.getMainLooper());
    private RewardedAd ad;
    private boolean loaded;
    private boolean destroyed;
    private boolean rewardReceived;

    boolean isLoaded() { return ad != null && loaded && !destroyed; }

    void load(Activity activity, int slot, Listener listener) {
        if (slot <= 0 || activity.isFinishing() || activity.isDestroyed()) {
            listener.unavailable();
            return;
        }
        destroy();
        destroyed = false;
        loaded = false;
        rewardReceived = false;
        final RewardedAd next = new RewardedAd(slot, activity);
        ad = next;
        next.setListener(new RewardedAd.RewardedAdListener() {
            private boolean current() {
                return !destroyed && ad == next && !activity.isFinishing() && !activity.isDestroyed();
            }

            @Override public void onLoad(RewardedAd rewardedAd) {
                main.post(() -> {
                    if (!current()) return;
                    loaded = true;
                    listener.loaded();
                });
            }

            @Override public void onNoAd(IAdLoadingError error, RewardedAd rewardedAd) {
                main.post(() -> {
                    if (!current()) return;
                    loaded = false;
                    listener.unavailable();
                });
            }

            @Override public void onFailedToShow(RewardedAd rewardedAd) {
                main.post(() -> {
                    if (!current()) return;
                    loaded = false;
                    listener.unavailable();
                });
            }

            @Override public void onDisplay(RewardedAd rewardedAd) {
                main.post(() -> {
                    if (current()) listener.shown();
                });
            }

            @Override public void onClick(RewardedAd rewardedAd) { }

            @Override public void onDismiss(RewardedAd rewardedAd) {
                main.post(() -> {
                    if (!current()) return;
                    loaded = false;
                    listener.closed();
                });
            }

            @Override public void onReward(Reward reward, RewardedAd rewardedAd) {
                main.post(() -> {
                    if (!current() || rewardReceived) return;
                    rewardReceived = true;
                    listener.rewarded();
                });
            }
        });
        try {
            next.load();
        } catch (RuntimeException error) {
            destroy();
            listener.unavailable();
        }
    }

    boolean show() {
        if (!isLoaded()) return false;
        loaded = false;
        try {
            ad.show();
            return true;
        } catch (RuntimeException error) {
            return false;
        }
    }

    void destroy() {
        destroyed = true;
        loaded = false;
        if (ad != null) {
            ad.setListener(null);
            ad.dismiss();
            ad = null;
        }
    }
}
