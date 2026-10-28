package ru.smetra.mobile;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.Base64;
import com.google.mlkit.vision.barcode.BarcodeScanning;
import com.google.mlkit.vision.barcode.BarcodeScanner;
import com.google.mlkit.vision.barcode.BarcodeScannerOptions;
import com.google.mlkit.vision.barcode.common.Barcode;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import com.google.mlkit.vision.text.TextRecognizer;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Offline, opt-in analysis of a single user-supplied JPEG/PNG. Nothing is
 * uploaded by the native scanner. Text model is Latin only: for Russian
 * documents the server's OCR/design workflow is the supported path.
 */
final class NativeVision {
    interface Result { void deliver(JSONObject data, String code, String message); }
    private static final int MAX_IMAGE_BYTES = 3_000_000;
    private NativeVision() {}

    private static void fail(Result callback, String code, String text) { callback.deliver(null, code, text); }

    static void scan(Activity activity, JSONObject args, Result callback) {
        final String mode = args.optString("mode", "barcode");
        if (!"barcode".equals(mode) && !"text".equals(mode)) {
            fail(callback, "bad_request", "Режим сканирования не поддерживается");
            return;
        }
        String encoded = args.optString("base64", "");
        if (encoded.isEmpty() || encoded.length() > MAX_IMAGE_BYTES * 4 / 3 + 8) {
            fail(callback, "too_large", "Изображение должно быть не больше 3 МБ");
            return;
        }
        byte[] data;
        try { data = Base64.decode(encoded, Base64.DEFAULT); }
        catch (IllegalArgumentException error) { fail(callback, "bad_request", "Некорректное изображение"); return; }
        if (data.length < 16 || data.length > MAX_IMAGE_BYTES) {
            fail(callback, "bad_request", "Пустое или слишком большое изображение");
            return;
        }
        boolean png = data[0] == (byte) 0x89 && data[1] == 0x50 && data[2] == 0x4e && data[3] == 0x47;
        boolean jpg = data[0] == (byte) 0xff && data[1] == (byte) 0xd8 && data[2] == (byte) 0xff;
        if (!png && !jpg) { fail(callback, "bad_request", "Разрешены только PNG и JPEG"); return; }
        BitmapFactory.Options size = new BitmapFactory.Options();
        size.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(data, 0, data.length, size);
        long pixels = (long) size.outWidth * size.outHeight;
        if (size.outWidth < 1 || size.outHeight < 1 || pixels > 24_000_000L) {
            fail(callback, "bad_request", "Некорректные размеры изображения");
            return;
        }
        BitmapFactory.Options options = new BitmapFactory.Options();
        int max = Math.max(size.outWidth, size.outHeight);
        options.inSampleSize = 1;
        while (max / options.inSampleSize > 2400) options.inSampleSize *= 2;
        final Bitmap bitmap;
        try { bitmap = BitmapFactory.decodeByteArray(data, 0, data.length, options); }
        catch (OutOfMemoryError error) { fail(callback, "too_large", "Не хватает памяти для обработки"); return; }
        if (bitmap == null) { fail(callback, "bad_request", "Не удалось открыть изображение"); return; }
        InputImage image = InputImage.fromBitmap(bitmap, 0);
        try {
            if ("barcode".equals(mode)) {
                BarcodeScannerOptions settings = new BarcodeScannerOptions.Builder()
                    .setBarcodeFormats(Barcode.FORMAT_QR_CODE, Barcode.FORMAT_CODE_128,
                        Barcode.FORMAT_EAN_13, Barcode.FORMAT_DATA_MATRIX, Barcode.FORMAT_PDF417)
                    .build();
                BarcodeScanner scanner = BarcodeScanning.getClient(settings);
                scanner.process(image)
                    .addOnSuccessListener(barcodes -> {
                        JSONArray values = new JSONArray();
                        for (Barcode barcode : barcodes) {
                            if (values.length() >= 20) break;
                            String raw = barcode.getRawValue();
                            if (raw == null) continue;
                            try {
                                values.put(new JSONObject().put("format", barcode.getFormat())
                                    .put("text", raw.substring(0, Math.min(raw.length(), 2048))));
                            } catch (org.json.JSONException ignored) { }
                        }
                        try { callback.deliver(new JSONObject().put("items", values), null, null); }
                        catch (org.json.JSONException ignored) { fail(callback, "failed", "Не удалось прочитать код"); }
                    })
                    .addOnFailureListener(error -> fail(callback, "failed", "Не удалось прочитать QR или штрихкод"))
                    .addOnCompleteListener(task -> { scanner.close(); bitmap.recycle(); });
            } else {
                TextRecognizer recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
                recognizer.process(image)
                    .addOnSuccessListener(value -> {
                        try {
                            String raw = value.getText();
                            callback.deliver(new JSONObject().put("text", raw.substring(0, Math.min(raw.length(), 12000)))
                                .put("language", "latin"), null, null);
                        } catch (org.json.JSONException ignored) { fail(callback, "failed", "Не удалось прочитать текст"); }
                    })
                    .addOnFailureListener(error -> fail(callback, "failed", "Не удалось распознать текст"))
                    .addOnCompleteListener(task -> { recognizer.close(); bitmap.recycle(); });
            }
        } catch (RuntimeException error) {
            bitmap.recycle();
            fail(callback, "failed", "Сканирование недоступно на этом устройстве");
        }
    }
}
