package ru.smetra.mobile;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

/** JVM coverage of the envelope; Android Keystore integration is checked separately. */
public final class VaultCipherTest {
    interface Attempt { void run() throws Exception; }
    static void rejects(Attempt operation) throws Exception {
        try { operation.run(); } catch (GeneralSecurityException expected) { return; }
        throw new AssertionError("Unauthenticated or invalid envelope accepted");
    }
    public static void main(String[] args) throws Exception {
        KeyGenerator generator=KeyGenerator.getInstance("AES");generator.init(256);
        SecretKey key=generator.generateKey(),other=generator.generateKey();
        byte[] context="ru.smetra.mobile|offline_quotes|account-session".getBytes(StandardCharsets.UTF_8);
        byte[] secret="Смета клиента и секрет сессии".getBytes(StandardCharsets.UTF_8);
        byte[] envelope=VaultCipher.seal(key,context,secret);
        if(!Arrays.equals(secret,VaultCipher.open(key,context,envelope)))throw new AssertionError("Round trip");
        if(Arrays.equals(envelope,VaultCipher.seal(key,context,secret)))throw new AssertionError("Nonce reuse");
        rejects(()->VaultCipher.open(other,context,envelope));
        rejects(()->VaultCipher.open(key,"different-account".getBytes(StandardCharsets.UTF_8),envelope));
        rejects(()->VaultCipher.open(key,"different-purpose".getBytes(StandardCharsets.UTF_8),envelope));
        for(int i=0;i<envelope.length;i++){
            byte[] changed=envelope.clone();changed[i]^=1;
            rejects(()->VaultCipher.open(key,context,changed));
        }
        rejects(()->VaultCipher.open(key,context,null));
        rejects(()->VaultCipher.open(key,context,new byte[28]));
        rejects(()->VaultCipher.open(key,context,new byte[65566]));
        rejects(()->VaultCipher.seal(key,context,new byte[65537]));
        byte[] max=new byte[65536];
        if(VaultCipher.open(key,context,VaultCipher.seal(key,context,max)).length!=max.length)throw new AssertionError("Bounded record");
        if(VaultCipher.open(key,context,VaultCipher.seal(key,context,new byte[0])).length!=0)throw new AssertionError("Empty record");
        System.out.println("PASS: AES-GCM round trip, fresh nonces, tamper, purpose/account isolation and bounds");
    }
}
