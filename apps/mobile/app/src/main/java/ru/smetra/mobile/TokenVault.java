package ru.smetra.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class TokenVault {
    private static final Object KEY_LOCK = new Object();
    private final SharedPreferences prefs;
    private final String alias;
    private final byte[] associatedData;
    private final boolean legacySession;
    TokenVault(Context context) { this(context, "session", ""); }
    TokenVault(Context context, String purpose) { this(context, purpose, ""); }
    TokenVault(Context context, String purpose, String scope) {
        if (!purpose.matches("[a-z0-9_]{1,40}")) throw new IllegalArgumentException("Invalid vault purpose");
        legacySession = "session".equals(purpose);
        alias = legacySession ? "smetra.session.v1" : "smetra.secret.v1." + purpose;
        prefs=context.getSharedPreferences(legacySession ? "session_vault" : "secret_vault_" + purpose,Context.MODE_PRIVATE);
        associatedData=(context.getPackageName()+"|"+purpose+"|"+scope).getBytes(StandardCharsets.UTF_8);
    }
    private SecretKey key() throws Exception {
      synchronized (KEY_LOCK) {
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        if (!store.containsAlias(alias)) {
            KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setKeySize(256).setRandomizedEncryptionRequired(true)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return (SecretKey)store.getKey(alias,null);
      }
    }
    void save(String token) throws Exception {
        SharedPreferences.Editor edit=prefs.edit().clear();
        if(token!=null)edit.putString("sealed",Base64.encodeToString(VaultCipher.seal(key(),associatedData,token.getBytes(StandardCharsets.UTF_8)),Base64.NO_WRAP));
        if(!edit.commit())throw new java.io.IOException("Could not persist encrypted value");
    }
    String read() {
        try {
            String sealed=prefs.getString("sealed",null);
            if(sealed!=null){
                if(sealed.length()>90000)throw new java.io.IOException("Secret too large");
                return new String(VaultCipher.open(key(),associatedData,Base64.decode(sealed,Base64.NO_WRAP)),StandardCharsets.UTF_8);
            }
            if(!legacySession||!prefs.contains("value"))return null;
            // One-time migration of the previous AES-GCM session record.
            String oldValue=prefs.getString("value",""),oldIv=prefs.getString("iv","");
            if(oldValue.length()>90000||oldIv.length()>32)throw new java.io.IOException("Secret too large");
            Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(oldIv,Base64.NO_WRAP)));
            String token=new String(cipher.doFinal(Base64.decode(oldValue,Base64.NO_WRAP)),StandardCharsets.UTF_8);
            save(token);return token;
        } catch(Exception error){prefs.edit().clear().apply();return null;}
    }
}
