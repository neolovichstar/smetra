package ru.smetra.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.InputMethodManager;
import android.content.Context;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private LinearLayout content;
    private String token;
    private JSONObject me;
    private int green = Color.rgb(36, 93, 75);

    interface Done { void onResult(JSONObject json); }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(green);
        getWindow().setNavigationBarColor(Color.rgb(245,244,240));
        token = getPreferences(MODE_PRIVATE).getString("token", null);
        if (token == null) login(false); else refresh();
    }

    @Override public void onDestroy() { worker.shutdownNow(); super.onDestroy(); }

    private JSONObject request(String path, String method, JSONObject body) throws Exception {
        HttpURLConnection c = (HttpURLConnection)new URL(BuildConfig.API_BASE_URL + "/api" + path).openConnection();
        c.setConnectTimeout(10000); c.setReadTimeout(10000); c.setRequestMethod(method);
        c.setRequestProperty("Accept", "application/json");
        if (token != null) c.setRequestProperty("Authorization", "Bearer " + token);
        if (body != null) {
            c.setDoOutput(true); c.setRequestProperty("Content-Type", "application/json");
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            try (OutputStream output = c.getOutputStream()) { output.write(bytes); }
        }
        int code = c.getResponseCode();
        try (InputStream input = code < 400 ? c.getInputStream() : c.getErrorStream()) {
            byte[] bytes = input.readAllBytes(); JSONObject result = new JSONObject(new String(bytes, StandardCharsets.UTF_8));
            if (code >= 400) throw new Exception(result.optString("error", "Ошибка сервера: " + code));
            return result;
        } finally { c.disconnect(); }
    }

    private void call(String path, String method, JSONObject body, Done done) {
        worker.execute(() -> {
            try { JSONObject data = request(path, method, body); runOnUiThread(() -> done.onResult(data)); }
            catch (Exception err) { runOnUiThread(() -> message(err.getMessage() == null ? "Ошибка подключения" : err.getMessage())); }
        });
    }

    private void message(String text) { Toast.makeText(this, text, Toast.LENGTH_LONG).show(); }

    private void page(String title) {
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true);
        content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(22), dp(28), dp(22), dp(28));
        content.setBackgroundColor(Color.rgb(245,244,240)); scroll.addView(content); setContentView(scroll);
        TextView heading = new TextView(this); heading.setText(title); heading.setTextSize(30);
        heading.setTextColor(Color.rgb(23,33,30)); heading.setTypeface(null,1); content.addView(heading);
        View gap = new View(this); content.addView(gap,new LinearLayout.LayoutParams(1,dp(16)));
    }
    private int dp(int n) { return (int)(getResources().getDisplayMetrics().density*n); }
    private TextView text(String value) { TextView t = new TextView(this); t.setText(value); t.setTextColor(Color.rgb(70,85,75)); t.setTextSize(16); t.setPadding(0,dp(10),0,dp(10)); content.addView(t); return t; }
    private Button button(String value, View.OnClickListener click) { Button b=new Button(this); b.setText(value); b.setAllCaps(false); b.setOnClickListener(click); content.addView(b,new LinearLayout.LayoutParams(-1,dp(54))); return b; }
    private EditText field(String hint, int inputType) { EditText e=new EditText(this); e.setHint(hint); e.setInputType(inputType);e.setSingleLine(inputType != 1); content.addView(e,new LinearLayout.LayoutParams(-1,dp(inputType==1?110:58))); return e; }

    private void login(boolean create) {
        page(create ? "Регистрация" : "Вход в Сметру");
        text("Предложения для ваших клиентов");
        EditText name=create?field("Ваше имя", 33):null;
        EditText email=field("Электронная почта",33);
        EditText password=field("Пароль",129);
        button(create ? "Создать аккаунт" : "Войти",v -> {
            try {
                JSONObject body = new JSONObject().put("email",email.getText().toString().trim()).put("password",password.getText().toString());
                if(create) body.put("name",name.getText().toString().trim());
                call(create?"/auth/register":"/auth/login","POST",body,result -> {
                    token=result.optString("token");
                    getPreferences(MODE_PRIVATE).edit().putString("token",token).apply();
                    me=result.optJSONObject("user"); home();
                });
            } catch (Exception err) { message(err.getMessage()); }
        });
        button(create ? "Уже есть аккаунт" : "Создать аккаунт",v -> login(!create));
    }

    private void refresh() { call("/me","GET",null,result -> { me=result.optJSONObject("user");home(); }); }

    private void home() {
        page("Сметра"); text("Здравствуйте, " + me.optString("name") + " · " + me.optString("plan"));
        button("+ Создать предложение",v -> create());
        button("Обновить",v -> home());
        button("Настройки",v -> settings());
        call("/quotes","GET",null,result -> {
            JSONArray list=result.optJSONArray("quotes");
            if(list==null || list.length()==0) { text("Предложений пока нет. Начните с первого расчёта.");return; }
            for(int i=0;i<list.length();i++) {
                JSONObject q=list.optJSONObject(i); if(q==null)continue;
                String id=q.optString("id"), status=q.optString("status"), link=q.optString("public_url");
                text(q.optString("title") + " · " + q.optString("client") + "\n" + String.format("%,.2f ₽",q.optLong("amount_kopecks")/100.0) + " · " + status);
                if(status.equals("draft")) button("Отправить: " + q.optString("title"),v -> {
                    try { call("/quotes/"+id,"PATCH",new JSONObject().put("status","sent"),r -> { share(link);home(); }); }
                    catch(Exception e) { message(e.getMessage()); }
                });
                if(status.equals("sent")) button("Поделиться: " + q.optString("title"),v -> share(link));
                if(status.equals("accepted")) button("Завершить: " + q.optString("title"),v -> {
                    try { call("/quotes/"+id,"PATCH",new JSONObject().put("status","completed"),r -> home()); }
                    catch(Exception e) { message(e.getMessage()); }
                });
            }
        });
    }

    private void share(String url) {
        Intent intent=new Intent(Intent.ACTION_SEND); intent.setType("text/plain");
        intent.putExtra(Intent.EXTRA_TEXT,"Предложение по работе: " + url);
        startActivity(Intent.createChooser(intent,"Отправить предложение"));
    }

    private void create() {
        page("Новое предложение");
        EditText title=field("Название работы",33), client=field("Клиент",33), amount=field("Цена в рублях",8194), description=field("Описание работ",1);
        button("Сохранить",v -> {
            try {
                long cents=Math.round(Double.parseDouble(amount.getText().toString().replace(',','.'))*100);
                JSONObject body=new JSONObject().put("title",title.getText().toString()).put("client",client.getText().toString()).put("description",description.getText().toString()).put("amount",cents);
                call("/quotes","POST",body,result -> {message("Предложение создано");refresh();});
            } catch(Exception err) {message("Укажите корректную сумму");}
        });
        button("Назад",v -> home());
    }

    private void settings() {
        page("Настройки");
        text(me.optString("email"));
        text("Доступ: " + me.optString("plan") + ". Срок: " + me.optLong("entitlement_until"));
        text("Оплаченный доступ действует на сайте и в приложении. Внутри приложения продажи нет.");
        button("Обновить статус",v -> refresh());
        button("Написать в поддержку",v -> support());
        button("Выйти",v -> call("/auth/logout","POST",new JSONObject(),r -> {token=null;getPreferences(MODE_PRIVATE).edit().clear().apply();login(false);}));
        button("Удалить аккаунт",v -> new AlertDialog.Builder(this).setTitle("Удалить аккаунт?").setMessage("Все предложения будут удалены без восстановления.").setNegativeButton("Отмена",null).setPositiveButton("Удалить",(dialog,which) -> call("/me","DELETE",null,r -> {token=null;getPreferences(MODE_PRIVATE).edit().clear().apply();login(false);})).show());
        button("К предложениям",v -> home());
    }

    private void support() {
        page("Поддержка"); EditText message=field("Опишите вопрос",1);
        button("Отправить",v -> {
            try { call("/support","POST",new JSONObject().put("message",message.getText().toString()),r -> {message("Сообщение отправлено");settings();}); }
            catch(Exception e) {message(e.getMessage());}
        });
        button("Назад",v -> settings());
    }

    @Override public void onBackPressed() { if(token==null)super.onBackPressed();else home(); }
}
