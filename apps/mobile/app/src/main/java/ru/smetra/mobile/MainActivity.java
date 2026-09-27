package ru.smetra.mobile;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.*;
import android.view.inputmethod.InputMethodManager;
import android.widget.*;
import android.text.Editable;
import android.text.TextWatcher;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import static ru.smetra.mobile.SmetraUi.*;

public class MainActivity extends Activity {
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private LinearLayout content;
    private FrameLayout root;
    private SmetraUi ui;
    private TokenVault vault;
    private String token,uploadProject;
    private JSONObject me;
    private int pageVersion=0;
    private String currentPage="login",parentPage="home";
    private boolean publicView=false;
    private Button clickedButton;
    private TextView feedback;
    interface Done {void onResult(JSONObject json);}
    static class ApiException extends Exception {
        final int status;
        ApiException(int status,String message){super(message);this.status=status;}
    }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);ui=new SmetraUi(this);
        getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);
        vault=new TokenVault(this);token=vault.read();
        String legacy=getPreferences(MODE_PRIVATE).getString("token",null);
        if(token==null&&legacy!=null){try{vault.save(legacy);token=legacy;}catch(Exception ignored){token=null;}}
        getPreferences(MODE_PRIVATE).edit().remove("token").apply();
        if(!openLink(getIntent())){if(token==null)login(false);else{page("С возвращением","home",false);loading(content);refresh();}}
    }
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);openLink(intent);}
    private boolean openLink(Intent intent){android.net.Uri link=intent.getData();if(link!=null&&"smetra".equals(link.getScheme())&&"auth".equals(link.getHost())){String ticket=link.getQueryParameter("ticket"),verifier=getPreferences(MODE_PRIVATE).getString("oauth_verifier",null);if(ticket!=null&&verifier!=null){page("Вход","login",false);loading(content);try{call("/auth/native/exchange","POST",new JSONObject().put("ticket",ticket).put("verifier",verifier),result->{token=result.optString("token");try{vault.save(token);getPreferences(MODE_PRIVATE).edit().remove("oauth_verifier").apply();me=result.optJSONObject("user");home();}catch(Exception error){token=null;login(false);message("Не удалось сохранить сессию");}});}catch(Exception error){login(false);message("Повторите вход");}return true;}}if(link!=null&&"smetra".equals(link.getScheme())&&"quote".equals(link.getHost())&&link.getQueryParameter("token")!=null){publicQuote(link.getQueryParameter("token"));return true;}return false;}
    @Override public void onDestroy(){worker.shutdownNow();super.onDestroy();}
    private JSONObject request(String path,String method,JSONObject body)throws Exception{
        HttpURLConnection c=(HttpURLConnection)new URL(BuildConfig.API_BASE_URL+"/api"+path).openConnection();
        c.setConnectTimeout(10000);c.setReadTimeout(path.startsWith("/assistant")?110000:20000);c.setRequestMethod(method);c.setRequestProperty("Accept","application/json");
        if(token!=null)c.setRequestProperty("Authorization","Bearer "+token);
        try{
            if(body!=null){if(body.has("_request_key"))c.setRequestProperty("Idempotency-Key",body.optString("_request_key"));c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json");try(OutputStream output=c.getOutputStream()){output.write(body.toString().getBytes(StandardCharsets.UTF_8));}}
            int code=c.getResponseCode();try(InputStream input=code<400?c.getInputStream():c.getErrorStream()){
                JSONObject result=new JSONObject(new String(readLimited(input,8_000_000),StandardCharsets.UTF_8));
                if(code>=400)throw new ApiException(code,result.optString("error","Ошибка сервера: "+code));return result;
            }
        }finally{c.disconnect();}
    }
    private void call(String path,String method,JSONObject body,Done done){
        final int version=pageVersion;final Button submit=clickedButton;clickedButton=null;
        if(submit!=null){submit.setEnabled(false);submit.setAlpha(.5f);}
        worker.execute(()->{
            try{
                JSONObject data=request(path,method,body);
                if(method.equals("GET")&&(path.equals("/quotes")||path.equals("/clients")||path.equals("/projects")))getPreferences(MODE_PRIVATE).edit().putString("cache:"+path,data.toString()).apply();
                runOnUiThread(()->{if(version==pageVersion&&!isFinishing()){restore(submit);done.onResult(data);}});
            }catch(Exception error){runOnUiThread(()->{
                if(version!=pageVersion||isFinishing())return;restore(submit);clearLoading(content);
                if(error instanceof ApiException&&((ApiException)error).status==401&&token!=null){clearSession();login(false);message("Сессия завершена. Войдите снова.");return;}
                if(!(error instanceof ApiException)&&method.equals("GET")){
                    String cached=getPreferences(MODE_PRIVATE).getString("cache:"+path,null);
                    if(cached!=null){try{done.onResult(new JSONObject(cached));message("Нет сети · показаны сохранённые данные");return;}catch(Exception ignored){}}
                }
                String description=error instanceof ApiException?error.getMessage():"Не удалось подключиться. Проверьте интернет и попробуйте ещё раз.";
                message(description);
                if(method.equals("GET")){
                    LinearLayout failure=ui.card(content);failure.addView(ui.label("Данные пока недоступны",17,INK,true));ui.space(failure,8);failure.addView(ui.label(description,13,MUTED,false));
                    addButton(failure,"Повторить",false,v->{content.removeView(failure);call(path,method,body,done);});
                }
            });}
        });
    }
    private void restore(Button button){if(button!=null){button.setEnabled(true);button.setAlpha(1);}}
    private void clearSession(){token=null;me=null;try{vault.save(null);}catch(Exception ignored){}getPreferences(MODE_PRIVATE).edit().clear().apply();}
    private static byte[] readLimited(InputStream input,int maximum)throws IOException{if(input==null)throw new IOException("Пустой ответ сервера");ByteArrayOutputStream output=new ByteArrayOutputStream();byte[] buffer=new byte[8192];int count;while((count=input.read(buffer))!=-1){if(output.size()+count>maximum)throw new IOException("Файл слишком большой");output.write(buffer,0,count);}return output.toByteArray();}
    private int dp(float value){return ui.dp(value);}
    private void message(String message){
        if(root==null)return;if(feedback!=null)root.removeView(feedback);
        final FrameLayout parent=root;TextView toast=ui.label(message==null?"Не удалось выполнить действие":message,13,INK,false);feedback=toast;
        toast.setPadding(dp(18),dp(15),dp(18),dp(15));toast.setBackground(ui.shape(RAISED,18,LINE));toast.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        FrameLayout.LayoutParams params=new FrameLayout.LayoutParams(-1,-2,Gravity.TOP);params.setMargins(dp(20),dp(12),dp(20),0);parent.addView(toast,params);ui.enter(toast);
        toast.postDelayed(()->{if(toast.getParent()==parent)toast.animate().alpha(0).setDuration(ui.motion()?180:0).withEndAction(()->parent.removeView(toast)).start();},5500);
    }
    private void page(String title,String page,boolean back){
        View focused=getCurrentFocus();if(focused!=null)((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(focused.getWindowToken(),0);
        currentPage=page;pageVersion++;clickedButton=null;feedback=null;
        root=new FrameLayout(this);root.setBackgroundColor(BG);LinearLayout shell=ui.column();root.addView(shell,new FrameLayout.LayoutParams(-1,-1));
        root.setOnApplyWindowInsetsListener((view,insets)->{view.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;});
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setVerticalScrollBarEnabled(false);scroll.setOverScrollMode(View.OVER_SCROLL_NEVER);
        content=ui.column();content.setPadding(dp(22),dp(12),dp(22),dp(28));content.setFocusableInTouchMode(true);scroll.addView(content);shell.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        if(token!=null&&!publicView)navigation(shell);
        setContentView(root);root.requestApplyInsets();
        LinearLayout header=ui.row();
        if(back){header.addView(ui.iconButton("back","Назад",this::goBack),new LinearLayout.LayoutParams(dp(48),dp(48)));ui.gap(header,12);}
        TextView brand=ui.label(back?title:"сметра.",back?21:26,INK,true);brand.setLetterSpacing(-.04f);
        if(!back){android.text.SpannableString wordmark=new android.text.SpannableString("сметра.");wordmark.setSpan(new android.text.style.ForegroundColorSpan(0xff2186ff),6,7,0);brand.setText(wordmark);}
        header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        if(!back&&token!=null&&!publicView)header.addView(ui.iconButton("grid","Открыть профиль",this::settings),new LinearLayout.LayoutParams(dp(48),dp(48)));
        content.addView(header);ui.space(content,back?18:26);ui.enter(content);
    }
    private void navigation(LinearLayout shell){
        LinearLayout nav=ui.row();nav.setPadding(dp(10),dp(10),dp(10),dp(10));nav.setBackgroundColor(BG);
        String[] labels={"Сметы","Клиенты","Заказы","Ассистент"},pages={"home","clients","projects","assistant"},icons={"document","clients","projects","spark"};
        String selected=currentPage.equals("create")||currentPage.equals("quote")?"home":currentPage.equals("project")||currentPage.equals("receipt")?"projects":currentPage.equals("client")?"clients":currentPage.equals("tasks")||currentPage.equals("support")?"settings":currentPage;
        for(int i=0;i<4;i++){final int index=i;boolean active=pages[i].equals(selected);LinearLayout item=ui.column();item.setGravity(Gravity.CENTER);item.setPadding(0,dp(8),0,dp(8));ui.ripple(item,BG,18,0);item.setSelected(active);item.setContentDescription(labels[i]+(active?", выбрано":""));
            item.addView(ui.new Icon(icons[i],active?BLUE:MUTED),new LinearLayout.LayoutParams(dp(22),dp(22)));ui.space(item,5);TextView caption=ui.label(labels[i],11,active?BLUE:MUTED,active);caption.setGravity(Gravity.CENTER);item.addView(caption);
            ui.tap(item,()->{publicView=false;if(index==0)home();else if(index==1)records("clients");else if(index==2)records("projects");else assistant();});LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,-2,1);params.setMargins(dp(3),0,dp(3),0);nav.addView(item,params);
        }shell.addView(nav);
    }
    private TextView text(String value){TextView view=ui.label(value,14,MUTED,false);ui.space(content,10);content.addView(view);return view;}
    private Button addButton(LinearLayout parent,String title,boolean primary,View.OnClickListener action){final Button[] holder=new Button[1];Button button=ui.button(title,primary,()->{clickedButton=holder[0];action.onClick(holder[0]);clickedButton=null;});holder[0]=button;parent.addView(button);return button;}
    private Button button(String title,boolean primary,View.OnClickListener action){return addButton(content,title,primary,action);}
    private EditText field(String label,int type){return ui.field(content,label,type);}
    private void loading(LinearLayout parent){LinearLayout box=ui.card(parent);box.setTag("loading");box.addView(ui.label("Загружаем данные…",14,MUTED,false));for(int i=0;i<3;i++){ui.space(box,12);View bar=new View(this);bar.setBackground(ui.shape(RAISED,6,0));box.addView(bar,new LinearLayout.LayoutParams(dp(i==1?150:230),dp(10)));}}
    private void clearLoading(LinearLayout parent){for(int i=parent.getChildCount()-1;i>=0;i--){View child=parent.getChildAt(i);if("loading".equals(child.getTag()))parent.removeViewAt(i);else if(child instanceof LinearLayout)clearLoading((LinearLayout)child);}}
    private String exactMoney(long cents,String currency){return String.format(new Locale("ru","RU"),"%,.2f",cents/100.0)+" "+currencySymbol(currency);}
    private String currencySymbol(String currency){switch(currency){case "RUB":return "₽";case "USD":return "$";case "EUR":return "€";case "KZT":return "₸";case "GBP":return "£";default:return currency;}}
    private String status(String value){switch(value){case "draft":return "Черновик";case "sent":return "На согласовании";case "accepted":return "Согласована";case "declined":return "Отклонена";case "completed":case "done":return "Завершён";case "in_progress":case "active":return "В работе";case "new":return "Новый";case "planned":return "Запланирован";case "waiting":return "Ожидает";case "todo":return "К выполнению";case "paused":return "На паузе";case "cancelled":return "Отменён";default:return value.isEmpty()?"Без статуса":value;}}
    private int statusColor(String value){if(value.equals("accepted")||value.equals("completed")||value.equals("done"))return GREEN;if(value.equals("sent")||value.equals("paused")||value.equals("waiting"))return AMBER;if(value.equals("declined")||value.equals("cancelled"))return RED;return BLUE;}

    private void emailLogin(boolean create){
        publicView=false;page("",create?"register":"login",false);
        content.addView(ui.art("unfold",create?100:125));ui.space(content,12);
        TextView heading=ui.label(create?"Начните с идеи.":"Всё начинается\nс ясности.",34,INK,true);heading.setLetterSpacing(-.045f);content.addView(heading);
        text(create?"Создайте пространство для ваших клиентов и проектов.":"Сметы, клиенты и работа.\nВ одном пространстве, под вашим контролем.");ui.space(content,4);
        EditText name=create?field("Как вас зовут",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_WORDS):null;
        EditText email=field("Электронная почта",33);email.setHint("you@company.ru");email.setAutofillHints(View.AUTOFILL_HINT_EMAIL_ADDRESS);
        EditText password=field("Пароль",129);password.setHint("Введите пароль");password.setAutofillHints(create?"newPassword":View.AUTOFILL_HINT_PASSWORD);
        ui.space(content,16);button(create?"Создать аккаунт":"Войти в пространство",true,v->{
            if(email.getText().toString().trim().isEmpty()){email.setError("Введите почту");return;}if(password.length()==0){password.setError("Введите пароль");return;}
            try{JSONObject body=new JSONObject().put("email",email.getText().toString().trim()).put("password",password.getText().toString());if(create)body.put("name",name.getText().toString().trim());
                call(create?"/auth/register":"/auth/login","POST",body,result->{token=result.optString("token");try{vault.save(token);getPreferences(MODE_PRIVATE).edit().clear().apply();}catch(Exception error){token=null;message("Не удалось защитить сессию на устройстве");return;}me=result.optJSONObject("user");home();});
            }catch(Exception error){message("Не удалось войти");}
        });
        button(create?"Уже есть аккаунт · Войти":"Первый раз? Создать аккаунт",false,v->emailLogin(!create));
        ui.space(content,18);TextView note=ui.label("От первого расчёта до завершённого проекта",11,MUTED,false);note.setGravity(Gravity.CENTER);content.addView(note);
    }
    private void login(boolean ignored){
        publicView=false;page("Вход","login",false);content.addView(ui.art("unfold",190));ui.space(content,16);content.addView(ui.label("Ваша работа.\nВсё в порядке.",34,INK,true));text("Сметы, клиенты и согласования.\nОдин аккаунт на всех устройствах.");ui.space(content,22);
        LinearLayout methods=ui.column();content.addView(methods);
        addButton(methods,"Войти по почте",true,v->emailLogin(false));
        call("/auth/providers","GET",null,result->{
            JSONArray list=result.optJSONArray("providers");methods.removeAllViews();int enabled=0;
            if(list!=null)for(int i=0;i<list.length();i++){
                JSONObject provider=list.optJSONObject(i);
                if(provider==null||!provider.optBoolean("enabled"))continue;
                addButton(methods,"Продолжить с "+provider.optString("name"),provider.optString("id").equals("yandex"),v->startIdentity(provider.optString("id")));
                enabled++;
            }
            addButton(methods,"Войти по почте",enabled==0,v->emailLogin(false));
            if(enabled==0){ui.space(methods,14);methods.addView(ui.label("Яндекс ID, VK ID и Mail ID появятся после подключения.",11,MUTED,false));}
        });
        ui.space(content,18);TextView legal=ui.label("Продолжая, вы принимаете условия использования и политику конфиденциальности.",11,MUTED,false);content.addView(legal);button("Условия и конфиденциальность",false,v->openUrl(BuildConfig.API_BASE_URL+"/privacy"));
    }
    private void openUrl(String url){try{startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(url)));}catch(Exception error){message("Не удалось открыть браузер");}}
    private void startIdentity(String provider){try{byte[] bytes=new byte[48];new java.security.SecureRandom().nextBytes(bytes);String verifier=android.util.Base64.encodeToString(bytes,android.util.Base64.URL_SAFE|android.util.Base64.NO_WRAP|android.util.Base64.NO_PADDING);String challenge=android.util.Base64.encodeToString(java.security.MessageDigest.getInstance("SHA-256").digest(verifier.getBytes(StandardCharsets.UTF_8)),android.util.Base64.URL_SAFE|android.util.Base64.NO_WRAP|android.util.Base64.NO_PADDING);getPreferences(MODE_PRIVATE).edit().putString("oauth_verifier",verifier).apply();openUrl(BuildConfig.API_BASE_URL+"/api/auth/oauth/"+provider+"/start?app_challenge="+challenge);}catch(Exception error){message("Не удалось начать вход. Попробуйте ещё раз.");}}
    private void billing(){parentPage="settings";page("Ваш тариф","billing",true);content.addView(ui.art("flight",160));ui.space(content,8);content.addView(ui.label("Больше возможностей.\nТа же ясность.",29,INK,true));text("Один доступ на сайте и в приложении.\nБез автоматических списаний.");ui.space(content,26);content.addView(ui.label("ПРО",11,BLUE,true));ui.space(content,10);content.addView(ui.label("490 ₽",44,INK,true));text("31 день доступа");ui.space(content,20);for(String benefit:new String[]{"До 10 000 смет","Клиенты, заказы и согласования","Учёт поступлений и расходов","Синхронизация на всех устройствах"}){LinearLayout row=ui.row();row.setPadding(0,dp(10),0,dp(10));row.addView(ui.new Icon("check",BLUE),new LinearLayout.LayoutParams(dp(18),dp(18)));ui.gap(row,12);row.addView(ui.label(benefit,14,INK,false));content.addView(row);}ui.space(content,20);button("Выбрать Про · 490 ₽",true,v->checkout("pro_month"));button("На год · 4 900 ₽",false,v->checkout("pro_year"));ui.space(content,18);text("Старт — бесплатно. Первые 10 смет для знакомства с Сметрой.");button("Обновить статус подписки",false,v->call("/billing/sync","POST",new JSONObject(),r->{me=r.optJSONObject("user");message("Статус обновлён");}));}
    private void checkout(String plan){try{call("/billing/checkout","POST",new JSONObject().put("plan",plan).put("_request_key",java.util.UUID.randomUUID().toString()),r->{String url=r.optString("url");if(url.startsWith("https://"))openUrl(url);else message("Оплата пока недоступна");});}catch(Exception error){message("Не удалось открыть оплату");}}
    private void assistant(){parentPage="home";page("Ассистент","assistant",false);content.addView(ui.label("Ассистент",34,INK,true));text("Освободим время для самой работы.");LinearLayout messages=ui.column();content.addView(messages);loading(messages);call("/assistant","GET",null,result->{messages.removeAllViews();JSONArray history=result.optJSONArray("messages");if(history!=null&&history.length()>0){for(int i=0;i<history.length();i++){JSONObject item=history.optJSONObject(i);assistantMessage(messages,item.optString("role"),item.optString("content"));}}else{ui.space(messages,30);messages.addView(ui.label("Что нужно\nсделать сегодня?",28,INK,true));ui.space(messages,12);messages.addView(ui.label("Найду клиента, подготовлю смету, добавлю задачу или помогу разобраться в оплатах.",14,MUTED,false));}JSONArray actions=result.optJSONArray("actions");if(actions!=null)for(int i=0;i<actions.length();i++)assistantAction(messages,actions.optJSONObject(i));if(!result.optBoolean("available"))message("Ассистент пока подключается.");});
        EditText prompt=field("Ваше сообщение",1);prompt.setHint("Например: помоги составить смету на сайт");ui.space(content,8);button("Отправить",true,v->{String value=prompt.getText().toString().trim();if(value.isEmpty()){prompt.setError("Напишите задачу");return;}try{message("Разбираюсь в задаче…");call("/assistant/chat","POST",new JSONObject().put("text",value),result->{assistantMessage(messages,"user",value);assistantMessage(messages,"assistant",result.optString("answer"));JSONArray actions=result.optJSONArray("actions");if(actions!=null)for(int i=0;i<actions.length();i++)assistantAction(messages,actions.optJSONObject(i));prompt.setText("");});}catch(Exception error){message(error.getMessage());}});text("Сообщение и нужные данные пространства обрабатывает OpenRouter. Изменения применяются после вашего подтверждения.").setTextSize(10);
    }
    private void assistantMessage(LinearLayout host,String role,String value){LinearLayout row=ui.card(host);row.addView(ui.label(role.equals("user")?"ВЫ":"АССИСТЕНТ",10,role.equals("user")?MUTED:BLUE,true));ui.space(row,10);TextView copy=ui.label(value,15,role.equals("user")?MUTED:INK,false);copy.setTextIsSelectable(true);row.addView(copy);}
    private String fieldLabel(String key){switch(key){case "title":case "name":return "Название";case "client":return "Клиент";case "description":return "Описание";case "amount":case "amount_kopecks":return "Сумма";case "items":return "Работы";case "due_date":return "Срок";case "email":return "Почта";case "phone":return "Телефон";case "terms":return "Условия";case "currency":return "Валюта";default:return key;}}
    private void assistantAction(LinearLayout host,JSONObject action){if(action==null)return;LinearLayout proposal=ui.card(host);proposal.addView(ui.label("ПРЕДЛОЖЕНИЕ · ЕЩЁ НЕ СОХРАНЕНО",10,BLUE,true));ui.space(proposal,12);proposal.addView(ui.label(action.optString("summary"),18,INK,true));JSONObject fields=action.optJSONObject("arguments");if(fields!=null){java.util.Iterator<String> keys=fields.keys();while(keys.hasNext()){String key=keys.next();if(key.equals("id")||key.equals("revision"))continue;String value=fields.optString(key);if(key.equals("amount")||key.equals("amount_kopecks")||key.equals("price"))value=exactMoney(fields.optLong(key),fields.optString("currency","RUB"));if(key.equals("items")){JSONArray items=fields.optJSONArray(key);StringBuilder list=new StringBuilder();if(items!=null)for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);list.append(item.optString("name")).append(" · ").append(item.optString("quantity")).append(" × ").append(exactMoney(item.optLong("unit_price"),fields.optString("currency","RUB"))).append('\n');}value=list.toString();}ui.space(proposal,10);proposal.addView(ui.label(fieldLabel(key),11,MUTED,false));ui.space(proposal,3);proposal.addView(ui.label(value,14,INK,false));}}
        addButton(proposal,"Применить",true,v->{try{call("/assistant/confirm","POST",new JSONObject().put("id",action.optString("id")),r->{proposal.removeAllViews();proposal.addView(ui.label("Сохранено · "+action.optString("summary"),14,BLUE,false));});}catch(Exception error){message(error.getMessage());}});addButton(proposal,"Не сейчас",false,v->{try{call("/assistant/dismiss","POST",new JSONObject().put("id",action.optString("id")),r->host.removeView(proposal));}catch(Exception error){message(error.getMessage());}});
    }

    private void refresh(){call("/me","GET",null,result->{me=result.optJSONObject("user");home();});}
    private void home(){
        publicView=false;page("Сметы","home",false);
        String name=me==null?"":me.optString("name").trim().split(" ")[0];content.addView(ui.label(name.isEmpty()?"ВАШЕ ПРОСТРАНСТВО":"ВАШЕ ПРОСТРАНСТВО, "+name.toUpperCase(new Locale("ru")),10,MUTED,true));ui.space(content,8);
        content.addView(ui.label("Сметы",36,INK,true));
        LinearLayout summary=ui.card(content);summary.setBackground(ui.gradient(26));TextView totalCaption=ui.label("В последних сметах",13,BLUE,false);summary.addView(totalCaption);ui.space(summary,12);
        TextView total=ui.label("—",38,INK,true);total.setLetterSpacing(-.05f);total.setAutoSizeTextTypeUniformWithConfiguration(22,38,1,android.util.TypedValue.COMPLEX_UNIT_SP);summary.addView(total,new LinearLayout.LayoutParams(-1,dp(55)));ui.space(summary,16);
        TextView waiting=ui.label("Загружаем статусы…",12,MUTED,false);summary.addView(waiting);
        ui.space(content,16);LinearLayout actions=ui.row();action(actions,"plus","Создать",this::create);action(actions,"clients","Клиенты",()->records("clients"));action(actions,"projects","Заказы",()->records("projects"));action(actions,"spark","Ассистент",this::assistant);content.addView(actions);
        ui.section(content,"Сметы",null);LinearLayout filters=ui.row();filters.setPadding(0,dp(12),0,dp(6));HorizontalScrollView scroller=new HorizontalScrollView(this);scroller.setHorizontalScrollBarEnabled(false);scroller.addView(filters);content.addView(scroller);
        LinearLayout host=ui.column();content.addView(host);loading(host);
        call("/quotes","GET",null,result->{JSONArray list=result.optJSONArray("quotes");if(list==null)list=new JSONArray();long amount=0;int sent=0,accepted=0;String sumCurrency=list.length()>0?list.optJSONObject(0).optString("currency","RUB"):"RUB";boolean mixed=false;for(int i=0;i<list.length();i++){JSONObject q=list.optJSONObject(i);if(q!=null){if(sumCurrency.equals(q.optString("currency","RUB")))amount+=q.optLong("amount_kopecks");else mixed=true;if(q.optString("status").equals("sent"))sent++;if(q.optString("status").equals("accepted"))accepted++;}}
            totalCaption.setText("В последних сметах");total.setText(exactMoney(amount,sumCurrency));waiting.setText(String.format(new Locale("ru"),"%d на согласовании   ·   %d согласовано",sent,accepted));if(mixed){ui.space(summary,8);summary.addView(ui.label("В итог не включены сметы в других валютах",11,MUTED,false));}
            final JSONArray data=list;filters.removeAllViews();String[] names={"Все · "+list.length(),"Черновики","Отправлены","Согласованы"},values={"","draft","sent","accepted"};
            for(int i=0;i<names.length;i++){final int index=i;TextView chip=ui.label(names[i],12,i==0?BG:MUTED,true);chip.setGravity(Gravity.CENTER);chip.setMinimumHeight(dp(48));chip.setPadding(dp(14),dp(14),dp(14),dp(14));ui.ripple(chip,i==0?BLUE:SURFACE,14,0);LinearLayout.LayoutParams cp=new LinearLayout.LayoutParams(-2,-2);cp.rightMargin=dp(7);filters.addView(chip,cp);ui.tap(chip,()->{for(int j=0;j<filters.getChildCount();j++){TextView item=(TextView)filters.getChildAt(j);item.setTextColor(j==index?BG:MUTED);ui.ripple(item,j==index?BLUE:SURFACE,14,0);item.setSelected(j==index);}renderQuotes(host,data,values[index]);});}
            renderQuotes(host,data,"");
        });
    }
    private void action(LinearLayout parent,String icon,String title,Runnable click){LinearLayout item=ui.column();item.setGravity(Gravity.CENTER);item.setPadding(dp(4),dp(8),dp(4),dp(8));FrameLayout tile=new FrameLayout(this);tile.setBackground(ui.shape(BG,12,LINE));tile.addView(ui.new Icon(icon,BLUE),new FrameLayout.LayoutParams(dp(23),dp(23),Gravity.CENTER));item.addView(tile,new LinearLayout.LayoutParams(dp(54),dp(54)));ui.space(item,9);TextView caption=ui.label(title,11,INK,false);caption.setGravity(Gravity.CENTER);item.addView(caption);ui.tap(item,click);item.setContentDescription(title);parent.addView(item,new LinearLayout.LayoutParams(0,-2,1));}
    private void renderQuotes(LinearLayout host,JSONArray list,String filter){host.removeAllViews();int shown=0;for(int i=0;i<list.length();i++){JSONObject q=list.optJSONObject(i);if(q==null||!filter.isEmpty()&&!filter.equals(q.optString("status")))continue;shown++;LinearLayout row=ui.card(host);LinearLayout top=ui.row();TextView title=ui.label(q.optString("title"),16,INK,true);title.setMaxLines(2);top.addView(title,new LinearLayout.LayoutParams(0,-2,1));ui.gap(top,12);TextView amount=ui.label(exactMoney(q.optLong("amount_kopecks"),q.optString("currency","RUB")),15,INK,false);top.addView(amount);row.addView(top);ui.space(row,7);row.addView(ui.label(q.optString("client","Без клиента"),12,MUTED,false));ui.space(row,9);row.addView(ui.badge(status(q.optString("status")),statusColor(q.optString("status"))));ui.tap(row,()->quote(q));}
        if(shown==0){ui.empty(host,"document",filter.isEmpty()?"Всё начинается с первой сметы":"Пока пусто",filter.isEmpty()?"Соберите работы и стоимость.\nОтправьте клиенту одну ссылку.":"Сметы с этим статусом появятся здесь.");if(filter.isEmpty())addButton(host,"Создать первую смету",true,v->create());}ui.enter(host);
    }
    private void quote(JSONObject q){parentPage="home";page("Смета","quote",true);content.addView(ui.badge(status(q.optString("status")),statusColor(q.optString("status"))));ui.space(content,18);content.addView(ui.label(q.optString("title"),28,INK,true));text(q.optString("client"));LinearLayout price=ui.card(content);price.setBackground(ui.gradient(24));price.addView(ui.label("Стоимость работ",12,BLUE,false));ui.space(price,12);price.addView(ui.label(exactMoney(q.optLong("amount_kopecks"),q.optString("currency","RUB")),32,INK,true));
        if(!q.optString("description").isEmpty()){ui.section(content,"Состав работ",null);text(q.optString("description"));}
        String state=q.optString("status"),id=q.optString("id");ui.space(content,20);
        if(state.equals("draft"))button("Отправить на согласование",true,v->ui.sheet("Всё готово к отправке?","Сохраним текущую версию сметы. Клиент сможет открыть её по ссылке и согласовать условия.","Опубликовать смету",false,()->{try{call("/quotes/"+id+"/status","POST",new JSONObject().put("status","sent").put("revision",q.optInt("revision")),r->{home();share(q.optString("public_url"));});}catch(Exception error){message(error.getMessage());}}));
        if(state.equals("sent")||state.equals("accepted"))button("Поделиться ссылкой",true,v->share(q.optString("public_url")));
        if(state.equals("accepted"))button("Создать заказ из сметы",false,v->{try{call("/quotes/"+id+"/project","POST",new JSONObject(),r->records("projects"));}catch(Exception error){message(error.getMessage());}});
    }
    private void share(String url){if(url.isEmpty()){message("Ссылка ещё не готова. Обновите смету.");return;}Intent intent=new Intent(Intent.ACTION_SEND);intent.setType("text/plain");intent.putExtra(Intent.EXTRA_TEXT,"Предложение по работе: "+url);startActivity(Intent.createChooser(intent,"Отправить предложение"));}
    private void create(){
        parentPage="home";page("Новая смета","create",true);content.addView(ui.label("Придайте идее\nточную стоимость.",28,INK,true));text("Сначала основное. Отправить смету клиенту можно после сохранения.");
        EditText title=field("Название работы",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES),client=field("Имя клиента или компания",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_WORDS),amount=field("Стоимость, ₽",8194),description=field("Что входит в работу",1);amount.setHint("0,00");description.setHint("Объём работ, результат, сроки…");
        String saved=getPreferences(MODE_PRIVATE).getString("draft",null);if(saved!=null)try{JSONObject d=new JSONObject(saved);title.setText(d.optString("title"));client.setText(d.optString("client"));amount.setText(d.optString("amount"));description.setText(d.optString("description"));}catch(Exception ignored){}
        ui.space(content,14);button("Создать смету",true,v->{if(title.length()==0){title.setError("Добавьте название");return;}try{long value=cents(amount);if(value<=0)throw new IllegalArgumentException();JSONObject body=new JSONObject().put("title",title.getText().toString()).put("client",client.getText().toString()).put("description",description.getText().toString()).put("amount",value);call("/quotes","POST",body,result->{getPreferences(MODE_PRIVATE).edit().remove("draft").apply();home();message("Смета создана");});}catch(Exception error){amount.setError("Укажите сумму больше нуля");}});
        button("Сохранить на устройстве",false,v->{try{JSONObject d=new JSONObject().put("title",title.getText().toString()).put("client",client.getText().toString()).put("amount",amount.getText().toString()).put("description",description.getText().toString());getPreferences(MODE_PRIVATE).edit().putString("draft",d.toString()).apply();message("Черновик сохранён на этом устройстве");}catch(Exception error){message("Не удалось сохранить черновик");}});
    }
    private long cents(EditText field){return new java.math.BigDecimal(field.getText().toString().replace(" ","").replace(',','.')).movePointRight(2).setScale(0,java.math.RoundingMode.HALF_UP).longValueExact();}
    private void records(String kind){
        page("",kind,false);content.addView(ui.label(kind.equals("clients")?"Ваши клиенты":kind.equals("projects")?"Всё движется\nпо плану.":"Задачи",30,INK,true));text(kind.equals("clients")?"Люди, с которыми вы создаёте больше.":kind.equals("projects")?"Работа, договорённости и оплата.":"Следующий шаг для каждого проекта.");
        if(kind.equals("clients"))button("Добавить клиента",true,v->newClient());
        EditText search=ui.field(content,"Поиск",android.text.InputType.TYPE_CLASS_TEXT);search.setSingleLine(true);search.setHint(kind.equals("clients")?"Имя, компания или почта":"Название или статус");
        LinearLayout host=ui.column();content.addView(host);loading(host);
        call("/"+kind,"GET",null,r->{JSONArray data=r.optJSONArray("items");final JSONArray list=data==null?new JSONArray():data;renderRecords(host,kind,list,search.getText().toString());search.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){renderRecords(host,kind,list,s.toString());}public void afterTextChanged(Editable e){}});});
    }
    private void renderRecords(LinearLayout host,String kind,JSONArray list,String query){host.removeAllViews();int shown=0;for(int i=0;i<list.length();i++){JSONObject item=list.optJSONObject(i);if(item==null)continue;String name=item.optString("name",item.optString("title"));String subtitle=kind.equals("clients")?item.optString("email",item.optString("phone")):status(item.optString("status"));if(!(name+" "+subtitle).toLowerCase(new Locale("ru")).contains(query.toLowerCase(new Locale("ru"))))continue;shown++;
        LinearLayout card=ui.card(host),row=ui.row();TextView initial=ui.label(name.isEmpty()?"С":name.substring(0,1).toUpperCase(new Locale("ru")),20,BLUE,true);initial.setGravity(Gravity.CENTER);initial.setBackground(ui.shape(0xff263347,16,0));row.addView(initial,new LinearLayout.LayoutParams(dp(48),dp(48)));ui.gap(row,14);LinearLayout labels=ui.column();labels.addView(ui.label(name,15,INK,true));ui.space(labels,6);labels.addView(ui.label(subtitle.isEmpty()?"Контакты не добавлены":subtitle,12,MUTED,false));row.addView(labels,new LinearLayout.LayoutParams(0,-2,1));ui.gap(row,8);row.addView(ui.new Icon("chevron",MUTED),new LinearLayout.LayoutParams(dp(17),dp(17)));card.addView(row);
        if(kind.equals("projects")){ui.space(card,18);card.addView(ui.label(exactMoney(item.optLong("amount_kopecks"),item.optString("currency","RUB")),22,INK,true));ui.tap(card,()->project(item.optString("id")));}else if(kind.equals("clients"))ui.tap(card,()->client(item.optString("id")));else ui.tap(card,()->ui.sheet(name,item.optString("description","Описание не добавлено"),"Понятно",false,()->{}));
        }if(shown==0)ui.empty(host,kind.equals("clients")?"clients":"projects",query.isEmpty()?"Здесь начинается работа":"Ничего не найдено",query.isEmpty()?(kind.equals("clients")?"Добавьте первого клиента,\nчтобы держать контакты под рукой.":"Новые записи появятся здесь.\nЗаказ можно создать из согласованной сметы."):"Попробуйте другое имя или название.");
    }
    private void newClient(){parentPage="clients";page("Новый клиент","client",true);text("Все контакты — в одном месте.");EditText name=field("Имя или компания",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_WORDS),email=field("Электронная почта",33),phone=field("Телефон",3);ui.space(content,16);button("Добавить клиента",true,v->{if(name.length()==0){name.setError("Укажите имя");return;}try{call("/clients","POST",new JSONObject().put("name",name.getText().toString()).put("email",email.getText().toString()).put("phone",phone.getText().toString()),r->{records("clients");message("Клиент добавлен");});}catch(Exception error){message(error.getMessage());}});}
    private void client(String id){parentPage="clients";page("Клиент","client",true);loading(content);call("/clients/"+id,"GET",null,r->{clearLoading(content);JSONObject c=r.optJSONObject("item");if(c==null)return;content.addView(ui.label(c.optString("name"),30,INK,true));LinearLayout contacts=ui.card(content);contacts.addView(ui.label("КОНТАКТЫ",10,MUTED,true));ui.space(contacts,14);TextView email=ui.label(c.optString("email","Почта не указана"),16,INK,false);email.setTextIsSelectable(true);contacts.addView(email);ui.space(contacts,10);TextView phone=ui.label(c.optString("phone","Телефон не указан"),16,INK,false);phone.setTextIsSelectable(true);contacts.addView(phone);ui.section(content,"Сметы клиента",null);JSONArray list=c.optJSONArray("quotes");LinearLayout host=ui.column();content.addView(host);renderQuotes(host,list==null?new JSONArray():list,"");});}
    private void project(String id){
        parentPage="projects";page("Заказ","project",true);loading(content);call("/projects/"+id,"GET",null,r->{clearLoading(content);JSONObject p=r.optJSONObject("item");if(p==null)return;content.addView(ui.badge(status(p.optString("status")),statusColor(p.optString("status"))));ui.space(content,18);content.addView(ui.label(p.optString("name"),28,INK,true));
            String currency=p.optString("currency","RUB");long cost=p.optLong("amount_kopecks"),paid=p.optLong("paid");LinearLayout card=ui.card(content);card.setBackground(ui.gradient(24));card.addView(ui.label("Стоимость заказа",12,BLUE,false));ui.space(card,12);card.addView(ui.label(exactMoney(cost,currency),32,INK,true));ui.space(card,18);
            FrameLayout track=new FrameLayout(this);track.setBackground(ui.shape(0xff364254,4,0));View fill=new View(this);fill.setBackground(ui.shape(GREEN,4,0));track.addView(fill,new FrameLayout.LayoutParams(0,-1));card.addView(track,new LinearLayout.LayoutParams(-1,dp(5)));track.post(()->{fill.getLayoutParams().width=(int)(track.getWidth()*Math.min(1,Math.max(0,cost>0?(double)paid/cost:0)));fill.requestLayout();});ui.space(card,12);card.addView(ui.label("Получено "+exactMoney(paid,currency),13,GREEN,true));ui.space(card,5);card.addView(ui.label("Осталось "+exactMoney(Math.max(0,cost-paid),currency),12,MUTED,false));
            button("Записать оплату",true,v->receipt(id,currency));button("Прикрепить файл",false,v->{uploadProject=id;Intent picker=new Intent(Intent.ACTION_OPEN_DOCUMENT);picker.setType("*/*");picker.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/png","image/jpeg","application/pdf","text/plain"});picker.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(picker,301);});
            ui.section(content,"Этапы работы",null);JSONArray stages=p.optJSONArray("stages");if(stages==null||stages.length()==0)text("Этапы ещё не добавлены.");else for(int i=0;i<stages.length();i++){JSONObject stage=stages.optJSONObject(i);if(stage==null)continue;LinearLayout line=ui.card(content);line.addView(ui.label(String.format(Locale.ROOT,"%02d",i+1)+"   "+stage.optString("name"),16,INK,true));ui.space(line,8);line.addView(ui.badge(status(stage.optString("status")),statusColor(stage.optString("status"))));}
            if(!p.optString("status").equals("completed")){ui.space(content,18);button("Завершить заказ",false,v->ui.sheet("Работа завершена?","Заказ получит статус «Завершён». Его смета и история оплат сохранятся.","Завершить заказ",false,()->{try{call("/projects/"+id,"PATCH",new JSONObject().put("revision",p.optInt("revision")).put("status","completed"),res->project(id));}catch(Exception error){message(error.getMessage());}}));}
        });
    }
    private void receipt(String projectId,String currency){parentPage="projects";page("Полученная оплата","receipt",true);content.addView(ui.label("Зафиксируйте\nновое поступление.",28,INK,true));text("Укажите деньги, которые уже получили от клиента. Это запись в учёте, средства не списываются.");EditText value=field("Сумма оплаты, "+currencySymbol(currency),8194);value.setHint("0,00");final String key=java.util.UUID.randomUUID().toString();ui.space(content,20);button("Сохранить оплату",true,v->{try{long amount=cents(value);if(amount<=0)throw new IllegalArgumentException();call("/receipts","POST",new JSONObject().put("project_id",projectId).put("amount_kopecks",amount).put("method","bank_transfer").put("_request_key",key),r->{project(projectId);message("Оплата записана");});}catch(Exception error){value.setError("Укажите сумму больше нуля");}});}
    private void settings(){
        publicView=false;page("Профиль","settings",false);content.addView(ui.label("Ваше пространство",28,INK,true));
        menu("wallet","Тариф и подписка","Старт и Про · один доступ везде",this::billing);LinearLayout profile=ui.card(content);profile.addView(ui.label(me==null?"Сметра":me.optString("name"),24,INK,true));ui.space(profile,8);profile.addView(ui.label(me==null?"":me.optString("email"),13,MUTED,false));ui.space(profile,18);profile.addView(ui.badge(me==null||me.optString("plan").equals("free")?"Базовый доступ":me.optString("plan").toUpperCase(Locale.ROOT),BLUE));text("Ваш доступ действует и на сайте, и в приложении.");
        if(me!=null&&!me.optBoolean("email_verified",false)){LinearLayout note=ui.card(content);note.addView(ui.label("Подтвердите почту",16,AMBER,true));ui.space(note,8);note.addView(ui.label("Откройте ссылку из письма, чтобы подтвердить адрес аккаунта.",13,MUTED,false));addButton(note,"Отправить письмо",false,v->call("/auth/verify/resend","POST",new JSONObject(),r->message("Письмо отправлено")));}
        ui.section(content,"Управление",null);menu("clock","Задачи","Ближайшие шаги по проектам",()->records("tasks"));menu("refresh","Обновить доступ","Синхронизировать аккаунт",this::refresh);menu("document","Поддержка","Поможем разобраться",this::support);
        ui.space(content,20);button("Выйти из аккаунта",false,v->ui.sheet("Выйти из Сметры?","Сметы и заказы останутся в аккаунте. Локальный черновик на этом устройстве будет удалён.","Выйти",false,()->call("/auth/logout","POST",new JSONObject(),r->{clearSession();login(false);})));
        Button remove=button("Удалить аккаунт",false,v->ui.sheet("Удалить аккаунт?","Все предложения и данные аккаунта будут удалены без возможности восстановления.","Удалить навсегда",true,()->call("/me","DELETE",null,r->{clearSession();login(false);})));remove.setTextColor(RED);
        ui.space(content,22);TextView version=ui.label("СМЕТРА  /  "+BuildConfig.VERSION_NAME,10,MUTED,false);version.setGravity(Gravity.CENTER);content.addView(version);
    }
    private void menu(String icon,String title,String subtitle,Runnable click){LinearLayout card=ui.card(content),row=ui.row();row.addView(ui.new Icon(icon,BLUE),new LinearLayout.LayoutParams(dp(22),dp(22)));ui.gap(row,16);LinearLayout copy=ui.column();copy.addView(ui.label(title,15,INK,true));ui.space(copy,5);copy.addView(ui.label(subtitle,11,MUTED,false));row.addView(copy,new LinearLayout.LayoutParams(0,-2,1));row.addView(ui.new Icon("chevron",MUTED),new LinearLayout.LayoutParams(dp(18),dp(18)));card.addView(row);ui.tap(card,click);}
    private void support(){parentPage="settings";page("Мы на связи","support",true);content.addView(ui.label("Чем можем\nпомочь?",32,INK,true));text("Опишите, что произошло или чего не хватает. Ваше сообщение попадёт в поддержку Сметры.");EditText input=field("Ваше сообщение",1);ui.space(content,16);button("Отправить сообщение",true,v->{if(input.getText().toString().trim().isEmpty()){input.setError("Напишите сообщение");return;}try{call("/support","POST",new JSONObject().put("message",input.getText().toString()),r->{settings();message("Сообщение отправлено");});}catch(Exception error){message(error.getMessage());}});}
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){super.onActivityResult(requestCode,resultCode,data);if(requestCode!=301||resultCode!=RESULT_OK||data==null||data.getData()==null)return;final android.net.Uri uri=data.getData();final String projectId=uploadProject;message("Прикрепляем файл…");worker.execute(()->{try{String mime=getContentResolver().getType(uri);String suffix="image/png".equals(mime)?".png":"image/jpeg".equals(mime)?".jpg":"application/pdf".equals(mime)?".pdf":".txt";byte[] bytes;try(InputStream input=getContentResolver().openInputStream(uri)){bytes=readLimited(input,3_000_000);}JSONObject payload=new JSONObject().put("project_id",projectId).put("name","Вложение"+suffix).put("content",android.util.Base64.encodeToString(bytes,android.util.Base64.NO_WRAP));request("/files","POST",payload);runOnUiThread(()->{if(!isFinishing())message("Файл прикреплён");});}catch(Exception error){runOnUiThread(()->{if(!isFinishing())message("Не удалось прикрепить файл. "+error.getMessage());});}});}
    private void publicQuote(String publicToken){publicView=true;page("Предложение","public",false);loading(content);call("/public/quote?token="+android.net.Uri.encode(publicToken),"GET",null,r->{clearLoading(content);JSONObject q=r.optJSONObject("quote");if(q==null)return;content.addView(ui.badge(status(q.optString("status")),statusColor(q.optString("status"))));ui.space(content,20);content.addView(ui.label(q.optString("title"),30,INK,true));text(q.optString("description"));LinearLayout price=ui.card(content);price.setBackground(ui.gradient(24));price.addView(ui.label("Стоимость предложения",13,BLUE,false));ui.space(price,14);price.addView(ui.label(exactMoney(q.optLong("amount_kopecks"),q.optString("currency","RUB")),32,INK,true));ui.space(content,16);if(q.optString("status").equals("sent"))button("Согласовать предложение",true,v->ui.sheet("Согласовать условия?","Вы принимаете состав работ и стоимость этой версии предложения.","Да, согласовать",false,()->{try{call("/public/accept","POST",new JSONObject().put("token",publicToken).put("version",q.optInt("published_version")),result->{publicQuote(publicToken);message("Предложение согласовано");});}catch(Exception error){message(error.getMessage());}}));});}
    private void goBack(){if(currentPage.equals("clients")||currentPage.equals("projects")||currentPage.equals("settings")){home();return;}if(currentPage.equals("tasks")){settings();return;}if(currentPage.equals("public")){publicView=false;if(token==null)login(false);else refresh();return;}if(currentPage.equals("register")){login(false);return;}publicView=false;if(parentPage.equals("clients"))records("clients");else if(parentPage.equals("projects"))records("projects");else if(parentPage.equals("settings"))settings();else if(token!=null)home();else login(false);}
    @Override public void onBackPressed(){if(currentPage.equals("home")||currentPage.equals("login"))super.onBackPressed();else goBack();}
}
