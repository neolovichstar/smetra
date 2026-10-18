package ru.smetra.mobile;

import android.app.Application;
import ru.rustore.sdk.pushclient.common.logger.DefaultLogger;

public final class SmetraApp extends Application {
    @Override public void onCreate() {
        super.onCreate();
        Analytics.init(this);
        if (!BuildConfig.RUSTORE_PUSH_PROJECT_ID.isEmpty()) {
            try {
                ru.rustore.sdk.pushclient.RuStorePushClient.INSTANCE.init(
                    this, BuildConfig.RUSTORE_PUSH_PROJECT_ID, new DefaultLogger()
                );
            } catch (Exception ignored) {
                // Push remains optional until the project is configured.
            }
        }
    }
}
