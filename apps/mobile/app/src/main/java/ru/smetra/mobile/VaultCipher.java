package ru.smetra.mobile;

import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Versioned authenticated envelope; keys are supplied by Android Keystore. */
final class VaultCipher {
    private static final int IV_BYTES = 12;
    private static final int MAX_BYTES = 64 * 1024;
    private VaultCipher() {}

    static byte[] seal(SecretKey key, byte[] context, byte[] plaintext) throws GeneralSecurityException {
        if (plaintext == null || plaintext.length > MAX_BYTES) throw new GeneralSecurityException("Secret too large");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key);
        cipher.updateAAD(context);
        byte[] iv = cipher.getIV(), encrypted = cipher.doFinal(plaintext);
        if (iv.length != IV_BYTES) throw new GeneralSecurityException("Unsupported nonce size");
        byte[] result = new byte[1 + IV_BYTES + encrypted.length];
        result[0] = 2;
        System.arraycopy(iv, 0, result, 1, IV_BYTES);
        System.arraycopy(encrypted, 0, result, 1 + IV_BYTES, encrypted.length);
        return result;
    }

    static byte[] open(SecretKey key, byte[] context, byte[] envelope) throws GeneralSecurityException {
        if (envelope == null || envelope.length < 1 + IV_BYTES + 16
            || envelope.length > MAX_BYTES + 1 + IV_BYTES + 16 || envelope[0] != 2)
            throw new GeneralSecurityException("Invalid secret envelope");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, Arrays.copyOfRange(envelope, 1, 1 + IV_BYTES)));
        cipher.updateAAD(context);
        return cipher.doFinal(envelope, 1 + IV_BYTES, envelope.length - 1 - IV_BYTES);
    }
}
