package ru.smetra.mobile;

import android.app.Application;

public final class SmetraApp extends Application {
    @Override public void onCreate() {
        super.onCreate();
        Analytics.init(this);
    }
}
