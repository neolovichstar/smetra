package ru.smetra.mobile;

import java.util.List;
import ru.rustore.sdk.pushclient.messaging.service.RuStoreMessagingService;
import ru.rustore.sdk.pushclient.messaging.exception.RuStorePushClientException;

public final class SmetraPushMessagingService extends RuStoreMessagingService {
    @Override public void onNewToken(String token) {
        PushManager.onTokenRefresh(getApplicationContext(), token);
    }
    @Override public void onDeletedMessages() {
        // The in-app notification centre is refreshed whenever the user opens it.
    }
    @Override public void onError(List<? extends RuStorePushClientException> errors) {
        // Avoid logging service tokens or user tokens in production logs.
    }
}
