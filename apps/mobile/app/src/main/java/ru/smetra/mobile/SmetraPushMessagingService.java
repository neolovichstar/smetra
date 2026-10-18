package ru.smetra.mobile;

import java.util.List;
import ru.rustore.sdk.pushclient.messaging.service.RuStoreMessagingService;
import ru.rustore.sdk.pushclient.messaging.exception.RuStorePushClientException;

public final class SmetraPushMessagingService extends RuStoreMessagingService {
    @Override public void onNewToken(String token) {
        PushManager.onTokenRefresh(getApplicationContext(), token);
    }

    @Override public void onDeletedMessages() {
        // The app refreshes its in-app notification centre when it is opened.
    }

    @Override public void onError(List<? extends RuStorePushClientException> errors) {
        // Do not write service or device tokens into production logs.
    }
}
