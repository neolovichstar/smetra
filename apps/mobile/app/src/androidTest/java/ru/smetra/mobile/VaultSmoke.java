package ru.smetra.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Base64;
import org.json.JSONObject;

/** Runs against Android Keystore, not a JVM substitute. Uses isolated test purposes. */
final class VaultSmoke {
    static void require(boolean value,String message){if(!value)throw new AssertionError(message);}
    static void run(Context context)throws Exception{
        TokenVault first=new TokenVault(context,"qa_record","session-a");
        TokenVault other=new TokenVault(context,"qa_record","session-b");
        SharedPreferences prefs=context.getSharedPreferences("secret_vault_qa_record",Context.MODE_PRIVATE);
        try{
            first.save("private-value");String sealed=prefs.getString("sealed","");
            require(!sealed.contains("private-value")&&!prefs.contains("value"),"Plaintext secret persisted");
            require("private-value".equals(first.read()),"Keystore round trip");
            first.save("private-value");require(!sealed.equals(prefs.getString("sealed","")),"Nonce reused");
            require(other.read()==null,"Cross-session record accepted");
            first.save("private-value");byte[] changed=Base64.decode(prefs.getString("sealed",""),Base64.NO_WRAP);
            changed[changed.length-1]^=1;prefs.edit().putString("sealed",Base64.encodeToString(changed,Base64.NO_WRAP)).commit();
            require(first.read()==null,"Tampered record accepted");
            require(!prefs.contains("sealed"),"Invalid ciphertext retained");
            first.save("another-secret");first.save(null);require(first.read()==null,"Clear failed");
            TokenVault pkce=new TokenVault(context,"oauth_pkce");
            String verifier="a".repeat(64);
            pkce.save(new JSONObject().put("verifier",verifier).put("started_at",System.currentTimeMillis()).toString());
            require(ShellAuth.pending(context),"Valid challenge missing");
            require(verifier.equals(ShellAuth.takeVerifier(context)),"Challenge was not recovered");
            require(ShellAuth.takeVerifier(context)==null,"Challenge replay accepted");
            pkce.save(new JSONObject().put("verifier",verifier).put("started_at",System.currentTimeMillis()-610000).toString());
            require(!ShellAuth.pending(context),"Expired challenge accepted");
            pkce.save(new JSONObject().put("verifier",verifier).put("started_at",System.currentTimeMillis()+60000).toString());
            require(ShellAuth.takeVerifier(context)==null,"Future challenge accepted");
            pkce.save(null);
        }finally{first.save(null);}
    }
}
