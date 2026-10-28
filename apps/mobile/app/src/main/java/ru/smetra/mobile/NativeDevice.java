package ru.smetra.mobile;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.view.HapticFeedbackConstants;
import androidx.biometric.BiometricManager;
import org.json.JSONObject;

/**
 * Small, user-initiated device operations. No broad storage, vibration or
 * background permissions. Biometric *status* is not authentication or login.
 */
final class NativeDevice {
    private NativeDevice() {}

    static void haptic(Activity activity, JSONObject args) {
        String style = args.optString("style", "selection");
        int effect = "strong".equals(style) ? HapticFeedbackConstants.LONG_PRESS
            : HapticFeedbackConstants.KEYBOARD_TAP;
        activity.getWindow().getDecorView().performHapticFeedback(effect);
    }

    private static String checkedText(JSONObject args) {
        String text = args.optString("text", "");
        if (text.length() < 1 || text.length() > 8000) throw new IllegalArgumentException("text must be 1–8000 chars");
        return text;
    }

    static void copyText(Activity activity, JSONObject args) {
        ClipboardManager clipboard = (ClipboardManager) activity.getSystemService(Context.CLIPBOARD_SERVICE);
        if (clipboard == null) throw new IllegalStateException("clipboard unavailable");
        clipboard.setPrimaryClip(ClipData.newPlainText("Сметра", checkedText(args)));
    }

    static void shareText(Activity activity, JSONObject args) {
        Intent share = new Intent(Intent.ACTION_SEND)
            .setType("text/plain")
            .putExtra(Intent.EXTRA_TEXT, checkedText(args));
        activity.startActivity(Intent.createChooser(share, "Поделиться из Сметры"));
    }

    static JSONObject biometricStatus(Activity activity) {
        int code;
        try {
            code = BiometricManager.from(activity).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_WEAK);
        } catch (RuntimeException error) {
            code = BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE;
        }
        JSONObject result = new JSONObject();
        try {
            result.put("available", code == BiometricManager.BIOMETRIC_SUCCESS);
            result.put("status", code == BiometricManager.BIOMETRIC_SUCCESS ? "available"
                : code == BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED ? "not_enrolled" : "unavailable");
        } catch (org.json.JSONException ignored) { }
        return result;
    }
}
