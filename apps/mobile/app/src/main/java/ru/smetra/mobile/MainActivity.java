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
    private String token,uploadProject,uploadConstruction,uploadDefect,uploadLog,uploadPurchase,pendingPdfDocument,pendingCaptureText;
    private android.net.Uri pendingCaptureFile;
    private JSONObject me;
    private String assistantConversation="";
    private JSONObject assistantContext=null;
    private boolean assistantFileBlocked=false,assistantAvailable=false,assistantStreaming=false;
    private int assistantRemaining=0;
    private int assistantMaxUpload=3_000_000;
    private android.net.Uri assistantAttachmentUri;
    private String assistantAttachmentThread="",assistantAttachmentAccount="";
    private JSONObject assistantUploadedAttachment;
    private String assistantAttachmentRequestKey="";
    private int assistantAttachmentGeneration=0;
    private boolean assistantAttachmentBusy=false,assistantAttachmentPicking=false;
    private MobilePresentation presentation;
    private long lastPresentationCheck;
    private int pageVersion=0;
    private String currentPage="login",parentPage="home",constructionParentId=null;
    private String catalogSearch="",catalogParentId=null,catalogCategory="",catalogCurrency="RUB";
    private boolean catalogFavorites=false,catalogRecent=false;
    private int catalogLoadSeq=0;
    private boolean catalogHasMore=false;
    private JSONArray catalogItems=new JSONArray();
    private boolean publicView=false;
    private Button clickedButton;
    private TextView feedback;
    interface Done {void onResult(JSONObject json);}
    static class ApiException extends Exception {
        final int status;
        ApiException(int status,String message){super(message);this.status=status;}
    }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);presentation=MobilePresentation.cached(this);presentation.apply(this);ui=new SmetraUi(this);
        getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);
        vault=new TokenVault(this);token=vault.read();
        if(state!=null){assistantAttachmentRequestKey=state.getString("assistant_attachment_request_key","");assistantAttachmentPicking=state.getBoolean("assistant_attachment_picking",false);assistantAttachmentThread=state.getString("assistant_attachment_thread","");assistantAttachmentAccount=state.getString("assistant_attachment_account","");String uri=state.getString("assistant_attachment_uri");if(uri!=null)assistantAttachmentUri=android.net.Uri.parse(uri);try{String file=state.getString("assistant_attachment_uploaded");if(file!=null)assistantUploadedAttachment=new JSONObject(file);}catch(Exception ignored){}}
        String legacy=getPreferences(MODE_PRIVATE).getString("token",null);
        if(token==null&&legacy!=null){try{vault.save(legacy);token=legacy;}catch(Exception ignored){token=null;}}
        getPreferences(MODE_PRIVATE).edit().remove("token").apply();
        if(!openLink(getIntent())){if(token==null)login(false);else{page("С возвращением","home",false);loading(content);refresh();}}
        refreshPresentation();
    }
    @Override protected void onResume(){super.onResume();if(presentation!=null)refreshPresentation();}
    private void refreshPresentation(){
        long moment=System.currentTimeMillis();if(moment-lastPresentationCheck<300000)return;lastPresentationCheck=moment;
        worker.execute(()->{try{MobilePresentation next=MobilePresentation.fetch(BuildConfig.API_BASE_URL);runOnUiThread(()->{
            if(isFinishing()||next.version<presentation.version||next.raw.equals(presentation.raw))return;
            presentation=next;next.apply(this);
            if(currentPage.equals("login"))login(false);else if(currentPage.equals("home"))home();
        });}catch(Exception ignored){/* Keep the last native presentation while offline. */}});
    }
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);openLink(intent);}
    private boolean openLink(Intent intent){if(intent==null)return false;if(Intent.ACTION_SEND.equals(intent.getAction())){Analytics.event("capture_shared_in",Analytics.params("source","android_share"),false);CharSequence shared=intent.getCharSequenceExtra(Intent.EXTRA_TEXT);pendingCaptureText=shared==null?"":shared.toString().substring(0,Math.min(shared.length(),8000));pendingCaptureFile=intent.getParcelableExtra(Intent.EXTRA_STREAM);if(pendingCaptureText.isBlank()&&pendingCaptureFile==null){message("Не удалось прочитать переданный запрос");return false;}if(token==null)login(false);else capture();return true;}android.net.Uri link=intent.getData();if(link!=null&&"smetra".equals(link.getScheme())&&"auth".equals(link.getHost())){String ticket=link.getQueryParameter("ticket"),verifier=getPreferences(MODE_PRIVATE).getString("oauth_verifier",null);if(ticket!=null&&verifier!=null){page("Вход","login",false);loading(content);try{call("/auth/native/exchange","POST",new JSONObject().put("ticket",ticket).put("verifier",verifier),result->{token=result.optString("token");try{vault.save(token);getPreferences(MODE_PRIVATE).edit().remove("oauth_verifier").apply();me=result.optJSONObject("user");Analytics.login(me);afterLogin();}catch(Exception error){token=null;login(false);message("Не удалось сохранить сессию");}});}catch(Exception error){login(false);message("Повторите вход");}return true;}}if(link!=null&&"smetra".equals(link.getScheme())&&"quote".equals(link.getHost())&&link.getQueryParameter("token")!=null){publicQuote(link.getQueryParameter("token"));return true;}return false;}
    private void afterLogin(){if((pendingCaptureText!=null&&!pendingCaptureText.isBlank())||pendingCaptureFile!=null)capture();else home();}
    @Override public void onDestroy(){worker.shutdownNow();super.onDestroy();}
    @Override protected void onSaveInstanceState(Bundle state){
        state.putString("assistant_attachment_request_key",assistantAttachmentRequestKey);
        super.onSaveInstanceState(state);state.putString("assistant_attachment_thread",assistantAttachmentThread);state.putString("assistant_attachment_account",assistantAttachmentAccount);
        state.putBoolean("assistant_attachment_picking",assistantAttachmentPicking);
        if(assistantAttachmentUri!=null)state.putString("assistant_attachment_uri",assistantAttachmentUri.toString());
        if(assistantUploadedAttachment!=null)state.putString("assistant_attachment_uploaded",assistantUploadedAttachment.toString());
    }
    private JSONObject request(String path,String method,JSONObject body)throws Exception{
        return request(path,method,body,token);
    }
    private JSONObject request(String path,String method,JSONObject body,String sessionToken)throws Exception{
        final byte[] payload=body==null?null:body.toString().getBytes(StandardCharsets.UTF_8);
        HttpURLConnection c=(HttpURLConnection)new URL(BuildConfig.API_BASE_URL+"/api"+path).openConnection();
        c.setConnectTimeout(10000);c.setReadTimeout(path.startsWith("/assistant")?110000:(path.equals("/ai/draft")||path.equals("/files")&&method.equals("POST"))?65000:20000);c.setRequestMethod(method);c.setRequestProperty("Accept","application/json");
        if(sessionToken!=null)c.setRequestProperty("Authorization","Bearer "+sessionToken);
        try{
            if(body!=null){if(body.has("_request_key"))c.setRequestProperty("Idempotency-Key",body.optString("_request_key"));c.setDoOutput(true);c.setFixedLengthStreamingMode(payload.length);c.setRequestProperty("Content-Type","application/json");try(OutputStream output=c.getOutputStream()){output.write(payload);}}
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
                if(method.equals("GET")&&(path.equals("/dashboard")||path.equals("/quotes")||path.equals("/clients")||path.equals("/projects")))getPreferences(MODE_PRIVATE).edit().putString("cache:"+path,data.toString()).apply();
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
    private void clearSession(){token=null;me=null;assistantConversation="";assistantContext=null;clearAssistantAttachment();catalogSearch="";catalogCategory="";catalogCurrency="RUB";catalogFavorites=false;catalogRecent=false;catalogItems=new JSONArray();Analytics.clearUser();try{vault.save(null);}catch(Exception ignored){}getPreferences(MODE_PRIVATE).edit().clear().apply();}
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
        content=ui.column();content.setPadding(dp(20),dp(8),dp(20),dp(24));content.setFocusableInTouchMode(true);scroll.addView(content);shell.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        if(token!=null&&!publicView)navigation(shell);
        setContentView(root);root.requestApplyInsets();
        LinearLayout header=ui.row();
        if(back){header.addView(ui.iconButton("back","Назад",this::goBack),new LinearLayout.LayoutParams(dp(48),dp(48)));ui.gap(header,12);}
        TextView brand=ui.label(back?title:"сметра.",back?18:25,INK,true);brand.setLetterSpacing(-.04f);
        if(!back){android.text.SpannableString wordmark=new android.text.SpannableString("сметра.");wordmark.setSpan(new android.text.style.ForegroundColorSpan(0xff2186ff),6,7,0);brand.setText(wordmark);}
        header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        if(!back&&token!=null&&!publicView)header.addView(ui.iconButton("grid","Открыть профиль",this::settings),new LinearLayout.LayoutParams(dp(48),dp(48)));
        content.addView(header);ui.space(content,back?16:20);ui.enter(content);
    }
    private void navigation(LinearLayout shell){
        LinearLayout nav=ui.row();nav.setPadding(dp(10),dp(10),dp(10),dp(10));nav.setBackgroundColor(BG);
        String[] labels={"Сегодня","Клиенты","Создать","Проекты","Ещё"},pages={"home","clients","create","projects","more"},icons={"clock","clients","plus","projects","grid"};
        String selected=currentPage.equals("create")||currentPage.equals("quote")||currentPage.equals("capture")||currentPage.equals("draft-preview")?"home":currentPage.equals("client")?"clients":currentPage.equals("project")?"projects":currentPage.startsWith("assistant")||currentPage.equals("settings")||currentPage.equals("tasks")||currentPage.equals("support")||currentPage.equals("billing")||currentPage.equals("payments")||currentPage.equals("receipt")||currentPage.equals("approvals")||currentPage.startsWith("catalog")?"more":currentPage;
        for(int i=0;i<5;i++){final int index=i;boolean active=pages[i].equals(selected);LinearLayout item=ui.column();item.setGravity(Gravity.CENTER);item.setPadding(0,dp(8),0,dp(8));ui.ripple(item,BG,18,0);item.setSelected(active);item.setContentDescription(labels[i]+(active?", выбрано":""));
            item.addView(ui.new Icon(icons[i],active?BLUE:MUTED),new LinearLayout.LayoutParams(dp(21),dp(21)));ui.space(item,5);TextView caption=ui.label(labels[i],10,active?BLUE:MUTED,active);caption.setGravity(Gravity.CENTER);item.addView(caption);
            ui.tap(item,()->{publicView=false;if(index==0)home();else if(index==1)records("clients");else if(index==2)quickCreate();else if(index==3)records("projects");else more();});LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,-2,1);params.setMargins(dp(1),0,dp(1),0);nav.addView(item,params);
        }shell.addView(nav);
    }
    private void quickCreate(){ui.choiceSheet("Создать в Сметре",new String[]{"Новая смета","Из сообщения клиента","Новый клиент"},new Runnable[]{this::create,this::capture,this::newClient});}
    private TextView text(String value){TextView view=ui.label(value,14,MUTED,false);ui.space(content,10);content.addView(view);return view;}
    private Button addButton(LinearLayout parent,String title,boolean primary,View.OnClickListener action){final Button[] holder=new Button[1];Button button=ui.button(title,primary,()->{clickedButton=holder[0];action.onClick(holder[0]);clickedButton=null;});holder[0]=button;parent.addView(button);return button;}
    private Button button(String title,boolean primary,View.OnClickListener action){return addButton(content,title,primary,action);}
    private EditText field(String label,int type){return ui.field(content,label,type);}
    private void updateFieldLabel(EditText field,String label){
        if(!(field.getParent() instanceof ViewGroup))return;
        ViewGroup parent=(ViewGroup)field.getParent();
        for(int i=0;i<parent.getChildCount();i++){View child=parent.getChildAt(i);if(child instanceof TextView&&child.getLabelFor()==field.getId()){((TextView)child).setText(label);return;}}
    }
    private void loading(LinearLayout parent){LinearLayout box=ui.card(parent);box.setTag("loading");box.addView(ui.label("Загружаем данные…",14,MUTED,false));for(int i=0;i<3;i++){ui.space(box,12);View bar=new View(this);bar.setBackground(ui.shape(RAISED,6,0));box.addView(bar,new LinearLayout.LayoutParams(dp(i==1?150:230),dp(10)));}}
    private void clearLoading(LinearLayout parent){for(int i=parent.getChildCount()-1;i>=0;i--){View child=parent.getChildAt(i);if("loading".equals(child.getTag()))parent.removeViewAt(i);else if(child instanceof LinearLayout)clearLoading((LinearLayout)child);}}
    private String exactMoney(long cents,String currency){return String.format(new Locale("ru","RU"),"%,.2f",cents/100.0)+" "+currencySymbol(currency);}
    private String currencySymbol(String currency){switch(currency){case "RUB":return "₽";case "USD":return "$";case "EUR":return "€";case "KZT":return "₸";case "GBP":return "£";default:return currency;}}
    private String status(String value){switch(value){case "draft":return "Черновик";case "sent":return "На согласовании";case "viewed":return "Просмотрена клиентом";case "changes_requested":return "Нужны изменения";case "approved":case "accepted":return "Согласована";case "expired":return "Срок истёк";case "declined":return "Отклонена";case "completed":case "done":return "Завершён";case "in_progress":case "active":return "В работе";case "new":return "Новый";case "planned":return "Запланирован";case "waiting":return "Ожидает";case "todo":return "К выполнению";case "paused":return "На паузе";case "cancelled":return "Отменён";default:return value.isEmpty()?"Без статуса":value;}}
    private int statusColor(String value){if(value.equals("accepted")||value.equals("approved")||value.equals("completed")||value.equals("done"))return GREEN;if(value.equals("sent")||value.equals("viewed")||value.equals("changes_requested")||value.equals("paused")||value.equals("waiting"))return AMBER;if(value.equals("declined")||value.equals("cancelled")||value.equals("expired"))return RED;return BLUE;}

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
                call(create?"/auth/register":"/auth/login","POST",body,result->{token=result.optString("token");try{vault.save(token);getPreferences(MODE_PRIVATE).edit().clear().apply();}catch(Exception error){token=null;message("Не удалось защитить сессию на устройстве");return;}me=result.optJSONObject("user");if(create)Analytics.registration(me);else Analytics.login(me);afterLogin();});
            }catch(Exception error){message("Не удалось войти");}
        });
        button(create?"Уже есть аккаунт · Войти":"Первый раз? Создать аккаунт",false,v->emailLogin(!create));
        ui.space(content,18);TextView note=ui.label("От первого расчёта до завершённого проекта",11,MUTED,false);note.setGravity(Gravity.CENTER);content.addView(note);
    }
    private void login(boolean ignored){
        publicView=false;page("Вход","login",false);content.addView(ui.art("unfold",190));ui.space(content,16);content.addView(ui.label(presentation.loginTitle,34,INK,true));text(presentation.loginSubtitle);ui.space(content,22);
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
            if(enabled==0){ui.space(methods,14);methods.addView(ui.label("Яндекс ID, VK ID, Mail и Одноклассники появятся после подключения.",11,MUTED,false));}
        });
        ui.space(content,18);TextView legal=ui.label("Продолжая, вы принимаете условия использования и политику конфиденциальности.",11,MUTED,false);content.addView(legal);button("Условия и конфиденциальность",false,v->openUrl(BuildConfig.API_BASE_URL+"/privacy"));
    }
    private void openUrl(String url){try{startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(url)));}catch(Exception error){message("Не удалось открыть браузер");}}
    private void startIdentity(String provider){try{byte[] bytes=new byte[48];new java.security.SecureRandom().nextBytes(bytes);String verifier=android.util.Base64.encodeToString(bytes,android.util.Base64.URL_SAFE|android.util.Base64.NO_WRAP|android.util.Base64.NO_PADDING);String challenge=android.util.Base64.encodeToString(java.security.MessageDigest.getInstance("SHA-256").digest(verifier.getBytes(StandardCharsets.UTF_8)),android.util.Base64.URL_SAFE|android.util.Base64.NO_WRAP|android.util.Base64.NO_PADDING);getPreferences(MODE_PRIVATE).edit().putString("oauth_verifier",verifier).apply();openUrl(BuildConfig.API_BASE_URL+"/api/auth/oauth/"+provider+"/start?app_challenge="+challenge);}catch(Exception error){message("Не удалось начать вход. Попробуйте ещё раз.");}}
    private boolean proActive(JSONObject account){return account!=null&&"pro".equals(account.optString("plan"))&&account.optLong("entitlement_until")>System.currentTimeMillis()/1000;}
    private String subscriptionDate(JSONObject account){
        return java.text.DateFormat.getDateInstance(java.text.DateFormat.LONG,new Locale("ru","RU"))
            .format(new java.util.Date(account.optLong("entitlement_until")*1000));
    }
    private void billing(){
        parentPage="settings";page("Ваш тариф","billing",true);
        boolean active=proActive(me);
        content.addView(ui.art("flight",160));ui.space(content,8);
        content.addView(ui.label(active?"Ваш тариф · Про":"Ваш тариф · Старт",29,INK,true));
        text(active?"Про действует до "+subscriptionDate(me)+". Доступ общий для сайта и приложения.":"Первые 10 смет бесплатно. Оплата не требуется.");
        ui.space(content,26);ui.divider(content);ui.space(content,22);
        content.addView(ui.label("ПРО · 490 ₽",18,BLUE,true));
        text("31 день доступа · без автоматических списаний");
        ui.space(content,16);
        for(String benefit:new String[]{"До 10 000 смет","Клиенты, заказы и согласования","Учёт поступлений и расходов","Синхронизация на всех устройствах"}){
            LinearLayout row=ui.row();row.setPadding(0,dp(10),0,dp(10));
            row.addView(ui.new Icon("check",BLUE),new LinearLayout.LayoutParams(dp(18),dp(18)));
            ui.gap(row,12);row.addView(ui.label(benefit,14,INK,false));content.addView(row);
        }
        ui.space(content,16);
        text("Оплата оформляется на сайте в браузере. После оплаты доступ появится и в приложении.");
        button(active?"Продлить Про на сайте":"Оформить Про на сайте",true,v->openUrl(BuildConfig.API_BASE_URL+"/app#billing"));
        button("Проверить статус оплаты",false,v->call("/billing/sync","POST",new JSONObject(),result->{
            JSONObject updated=result.optJSONObject("user");
            if(updated==null){message("Не удалось проверить статус оплаты");return;}
            if(!active&&proActive(updated))Analytics.event("pro_entitlement_activated",Analytics.params("source","billing_sync"),true);
            me=updated;Analytics.identify(me);billing();
            message(proActive(updated)?"На сервере активен Про до "+subscriptionDate(updated):"Тариф Старт. Подтверждённой оплаты Про нет.");
        }));
    }
    private String assistantPreference(){return "assistant.conversation:"+(me==null?"":me.optString("id"));}
    private void selectAssistantThread(JSONObject thread){
        assistantConversation=thread==null?"":thread.optString("id");
        getPreferences(MODE_PRIVATE).edit().putString(assistantPreference(),assistantConversation).apply();
        assistant();
    }
    private void askAssistant(String entity,String id,String label){
        call("/assistant/conversations","GET",null,r->{JSONArray list=r.optJSONArray("items");
            if(list!=null)for(int i=0;i<list.length();i++){JSONObject item=list.optJSONObject(i);if(item!=null&&entity.equals(item.optString("context_entity"))&&id.equals(item.optString("context_id"))){selectAssistantThread(item);return;}}
            try{call("/assistant/conversations","POST",new JSONObject().put("title",label.substring(0,Math.min(120,label.length()))).put("context_entity",entity).put("context_id",id),created->selectAssistantThread(created.optJSONObject("conversation")));}catch(Exception error){message(error.getMessage());}
        });
    }
    private void assistantThreads(){
        parentPage="assistant";page("Диалоги","assistant-threads",true);content.addView(ui.label("Диалоги",26,INK,true));
        button("Новый диалог",true,v->assistantThreadEdit(null));button("Общий диалог",false,v->selectAssistantThread(null));
        LinearLayout listHost=ui.column();content.addView(listHost);loading(listHost);
        call("/assistant/conversations","GET",null,r->{listHost.removeAllViews();JSONArray list=r.optJSONArray("items");
            if(list==null||list.length()==0){ui.empty(listHost,"spark","Пока нет диалогов","Создайте отдельный диалог для проекта или задачи.");return;}
            for(int i=0;i<list.length();i++){JSONObject item=list.optJSONObject(i);if(item==null)continue;LinearLayout row=ui.card(listHost);row.addView(ui.label(item.optString("title"),15,INK,true));ui.space(row,5);row.addView(ui.label((item.optInt("pinned")==1?"Закреплён · ":"")+(item.optString("context_entity").isEmpty()?"Без контекста":"Контекст: "+assistantEntity(item.optString("context_entity"))),11,MUTED,false));ui.tap(row,()->selectAssistantThread(item));}
        });
    }
    private String assistantEntity(String entity){switch(entity){case "clients":return "Клиент";case "quotes":return "Смета";case "projects":return "Заказ";case "files":return "Файл";default:return "Запись";}}
    private void assistantThreadEdit(JSONObject thread){
        parentPage="assistant";page("Диалог","assistant-settings",true);content.addView(ui.label(thread==null?"Новый диалог":"Настройки диалога",26,INK,true));
        EditText title=field("Название диалога",1);title.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(120)});title.setText(thread==null?"Новый диалог":thread.optString("title"));
        button(thread==null?"Создать диалог":"Сохранить название",true,v->{String name=title.getText().toString().trim();if(name.isEmpty()){title.setError("Введите название");return;}try{JSONObject body=new JSONObject().put("title",name);call(thread==null?"/assistant/conversations":"/assistant/conversations/"+thread.optString("id"),thread==null?"POST":"PATCH",body,r->selectAssistantThread(r.optJSONObject("conversation")));}catch(Exception error){message(error.getMessage());}});
        if(thread!=null){button(thread.optInt("pinned")==1?"Открепить диалог":"Закрепить диалог",false,v->{try{call("/assistant/conversations/"+thread.optString("id"),"PATCH",new JSONObject().put("pinned",thread.optInt("pinned")==1?0:1),r->selectAssistantThread(r.optJSONObject("conversation")));}catch(Exception error){message(error.getMessage());}});
            button("Удалить диалог",false,v->ui.sheet("Удалить диалог?","Сообщения этого диалога будут удалены. Сметы и рабочие записи сохранятся.","Удалить",true,()->call("/assistant/conversations/"+thread.optString("id"),"DELETE",null,r->selectAssistantThread(null))));}
    }
    private void assistant(){
        parentPage="home";page("Ассистент","assistant",false);loading(content);
        assistantConversation=getPreferences(MODE_PRIVATE).getString(assistantPreference(),"");
        if(assistantConversation.isEmpty()){renderAssistant(null);return;}
        call("/assistant/conversations","GET",null,r->{JSONArray items=r.optJSONArray("items");JSONObject selected=null;
            if(items!=null)for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);if(item!=null&&item.optString("id").equals(assistantConversation)){selected=item;break;}}
            if(selected==null){assistantConversation="";getPreferences(MODE_PRIVATE).edit().remove(assistantPreference()).apply();}
            renderAssistant(selected);
        });
    }
    private void renderAssistant(JSONObject thread){
        content.removeAllViews();assistantContext=null;assistantFileBlocked=false;assistantAvailable=false;assistantRemaining=0;assistantStreaming=false;
        if(thread!=null&&!thread.optString("context_entity").isEmpty()){try{assistantContext=new JSONObject().put("entity",thread.optString("context_entity")).put("id",thread.optString("context_id"));}catch(Exception ignored){}}
        assistantFileBlocked=assistantContext!=null&&assistantContext.optString("entity").equals("files");
        content.addView(ui.label("Ассистент",26,INK,true));ui.space(content,7);
        TextView allowance=ui.label("Загружаю лимит…",11,MUTED,false);content.addView(allowance);
        ui.space(content,12);LinearLayout toolbar=ui.row();content.addView(toolbar,ui.match());
        Button dialogs=addButton(toolbar,"Диалоги",false,v->assistantThreads());dialogs.setLayoutParams(new LinearLayout.LayoutParams(0,dp(48),1));
        ui.gap(toolbar,8);Button jobs=addButton(toolbar,"Фоновые задачи",false,v->assistantJobs());jobs.setCompoundDrawablesRelative(null,null,null,null);jobs.setTextSize(12);jobs.setSingleLine(true);jobs.setLayoutParams(new LinearLayout.LayoutParams(0,dp(48),1));
        if(thread!=null){ui.gap(toolbar,4);toolbar.addView(ui.iconButton("grid","Настройки диалога",()->assistantThreadEdit(thread)),new LinearLayout.LayoutParams(dp(48),dp(48)));}
        ui.space(content,8);content.addView(ui.label(thread==null?"Общий диалог":thread.optString("title"),13,INK,true));
        if(assistantContext!=null){LinearLayout contextBar=ui.card(content);TextView contextLabel=ui.label("Контекст · "+assistantEntity(assistantContext.optString("entity")),12,BLUE,false);contextBar.addView(contextLabel);
            String entity=assistantContext.optString("entity"),id=assistantContext.optString("id");
            call("/"+entity+"/"+id+(entity.equals("files")?"/metadata":""),"GET",null,r->{JSONObject record=r.optJSONObject(entity.equals("quotes")?"quote":entity.equals("files")?"file":"item");if(record!=null)contextLabel.setText(assistantEntity(entity)+" · "+record.optString("title",record.optString("name",id)));});
            addButton(contextBar,"Убрать контекст",false,v->{try{call("/assistant/conversations/"+assistantConversation,"PATCH",new JSONObject().put("context_entity","").put("context_id",""),r->assistant());}catch(Exception error){message(error.getMessage());}});
        }
        LinearLayout preparation=ui.column();content.addView(preparation);
        ui.space(content,12);ui.divider(content);LinearLayout messages=ui.column();content.addView(messages);loading(messages);
        EditText prompt=field("Ваше сообщение",1);prompt.setHint("Спросите или поручите задачу…");prompt.setMaxLines(5);prompt.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(3000)});
        final String draftKey=assistantDraftKey(assistantConversation,me==null?"":me.optString("id"));
        prompt.setText(getPreferences(MODE_PRIVATE).getString(draftKey,""));
        prompt.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){getPreferences(MODE_PRIVATE).edit().putString(draftKey,s.toString()).apply();}public void afterTextChanged(Editable value){}});
        addButton(content,"Прикрепить файл · PDF, TXT, MD",false,v->pickAssistantAttachment());
        ui.space(content,8);Button send=button("Отправить ↗",true,v->{String value=prompt.getText().toString().trim();if(value.isEmpty()){prompt.setError("Напишите задачу");return;}streamAssistant(value,messages,prompt,allowance,(Button)v);});send.setEnabled(false);
        Button background=button("Выполнить в фоне",false,v->{
            if(!send.isEnabled()){message("Дождитесь ответа или проверьте лимит сообщений.");return;}
            String value=prompt.getText().toString().trim();if(value.isEmpty()){prompt.setError("Напишите задачу");return;}
            try{JSONObject body=new JSONObject().put("text",value).put("context",assistantContext==null?JSONObject.NULL:assistantContext);
                if(!assistantConversation.isEmpty())body.put("conversation_id",assistantConversation);
                String submitted=body.toString(),key=getPreferences(MODE_PRIVATE).getString("assistant_job_key","");
                if(key.isEmpty()||!submitted.equals(getPreferences(MODE_PRIVATE).getString("assistant_job_body","")))key=java.util.UUID.randomUUID().toString();
                getPreferences(MODE_PRIVATE).edit().putString("assistant_job_key",key).putString("assistant_job_body",submitted).apply();
                body.put("_request_key",key);
                call("/assistant/jobs","POST",body,result->{getPreferences(MODE_PRIVATE).edit().remove("assistant_job_key").remove("assistant_job_body").apply();prompt.setText("");assistantJobs();message("Задача сохранена. Можно закрыть приложение.");});
            }catch(Exception error){message(error.getMessage());}
        });background.setVisibility(View.GONE);
        call("/assistant/jobs","GET",null,result->{if(result.optBoolean("enabled"))background.setVisibility(View.VISIBLE);});
        ui.space(content,8);TextView status=ui.label("Изменения применяются после вашего подтверждения.",10,MUTED,false);content.addView(status);
        String historyPath=assistantConversation.isEmpty()?"/assistant":"/assistant/conversations/"+assistantConversation;
        call(historyPath,"GET",null,r->{messages.removeAllViews();JSONArray history=r.optJSONArray("messages");
            if(history!=null&&history.length()>0){for(int i=0;i<history.length();i++){JSONObject item=history.optJSONObject(i);if(item!=null)assistantMessage(messages,item.optString("role"),item.optString("content"));}
                JSONObject last=history.optJSONObject(history.length()-1);if(thread!=null&&last!=null){String lastId=last.optString("id");addButton(messages,"Продолжить в новой ветке",false,v->{try{call("/assistant/conversations/"+thread.optString("id")+"/fork","POST",new JSONObject().put("message_id",lastId),created->selectAssistantThread(created.optJSONObject("conversation")));}catch(Exception error){message(error.getMessage());}});}
            }else{ui.space(messages,26);messages.addView(ui.label("Что сделаем сегодня?",24,INK,true));ui.space(messages,10);messages.addView(ui.label("Спросите о работе или поручите подготовить изменение.",14,MUTED,false));ui.space(messages,24);}
            if(thread==null)assistantState(messages,allowance,send,status,r);
        });
        if(thread!=null)call("/assistant","GET",null,result->assistantState(messages,allowance,send,status,result));
        if(assistantContext!=null&&assistantContext.optString("entity").equals("files"))loadFilePreparation(preparation,send,assistantContext.optString("id"),pageVersion);
    }
    private void assistantState(LinearLayout messages,TextView allowance,Button send,TextView status,JSONObject result){assistantAvailable=result.optBoolean("available");assistantMaxUpload=Math.max(1,Math.min(5_000_000,result.optInt("file_upload_max_bytes",3_000_000)));JSONArray actions=result.optJSONArray("actions");if(actions!=null)for(int i=0;i<actions.length();i++)assistantAction(messages,actions.optJSONObject(i));JSONArray recent=result.optJSONArray("recent_actions");if(recent!=null)for(int i=0;i<recent.length();i++)assistantUndo(ui.card(messages),recent.optJSONObject(i));applyAssistantQuota(result.optJSONObject("quota"),allowance,send);if(!assistantAvailable){send.setEnabled(false);status.setText("Ассистент пока не подключён.");}}
    private void loadFilePreparation(LinearLayout host,Button send,String id,int version){
        if(version!=pageVersion||isFinishing())return;
        call("/files/"+id+"/metadata","GET",null,result->{
            if(version!=pageVersion)return;
            JSONObject info=result.optJSONObject("processing"),file=result.optJSONObject("file");if(info==null||file==null)return;
            String state=info.optString("state");boolean active=state.equals("queued")||state.equals("running")||state.equals("retry");
            assistantFileBlocked=active||state.equals("failed")||state.equals("deferred")||state.equals("cancelled")||state.equals("needs_ocr")||file.optLong("size")>2000000&&!state.equals("ready");
            send.setEnabled(assistantAvailable&&assistantRemaining>0&&!assistantFileBlocked&&!assistantStreaming);host.removeAllViews();
            String label=state.equals("ready")?"Текст готов · "+info.optInt("pages")+" стр."+(info.optBoolean("truncated")?" · подготовлена часть текста":""):state.equals("needs_ocr")?"В PDF есть страницы без текста. Для них нужен OCR.":state.equals("failed")?info.optString("error","Не удалось подготовить документ"):state.equals("cancelled")?"Подготовка отменена":active?"Подготавливаю текст документа…":"Подготовьте документ перед вопросом";
            ui.space(host,8);host.addView(ui.label(label,11,MUTED,false));
            JSONArray missingPages=info.optJSONArray("missing_text_pages");
            if((state.equals("ready")||state.equals("needs_ocr"))&&missingPages!=null&&missingPages.length()>0){StringBuilder gaps=new StringBuilder("Без текста: стр. ");for(int i=0;i<Math.min(6,missingPages.length());i++){if(i>0)gaps.append(", ");gaps.append(missingPages.optInt(i));}if(missingPages.length()>6)gaps.append("…");host.addView(ui.label(gaps.toString(),11,MUTED,false));}
            boolean ocr=info.optBoolean("ocr_supported");JSONObject ocrQuota=info.optJSONObject("ocr_quota");
            if(ocrQuota!=null)host.addView(ui.label("OCR: "+ocrQuota.optInt("used")+" из "+ocrQuota.optInt("limit")+" в месяц · первые 2 страницы",11,MUTED,false));
            if(state.equals("ready")&&info.optString("method").equals("ocr"))host.addView(ui.label("Текст получен OCR. Проверьте суммы по оригиналу.",11,MUTED,false));
            if(info.optBoolean("supported")&&(active&&info.optBoolean("can_cancel")||state.equals("failed")||state.equals("cancelled")||state.equals("deferred")||state.equals("legacy")||state.equals("needs_ocr"))){
                Button action=addButton(host,active?"Отменить подготовку":ocr?"Распознать скан":state.equals("failed")?"Повторить":"Подготовить документ",false,v->{
                    try{JSONObject body=active?null:new JSONObject().put("_request_key",java.util.UUID.randomUUID().toString());call("/files/"+id+(ocr?"/ocr":"/processing"),active?"DELETE":"POST",body,r->loadFilePreparation(host,send,id,version));}catch(Exception error){message(error.getMessage());}
                });action.setEnabled(!info.optBoolean("cancel_requested")&&(active||ocrQuota==null||ocrQuota.optInt("used")<ocrQuota.optInt("limit")));
            }
            if(active)host.postDelayed(()->loadFilePreparation(host,send,id,version),hasWindowFocus()?4000:15000);
        });
    }
    private String assistantDraftKey(String thread,String account){return "assistant_draft:"+account+":"+thread;}
    private void clearAssistantAttachment(){
        assistantAttachmentGeneration++;
        assistantAttachmentRequestKey="";
        if(assistantAttachmentUri!=null)try{getContentResolver().releasePersistableUriPermission(assistantAttachmentUri,Intent.FLAG_GRANT_READ_URI_PERMISSION);}catch(SecurityException ignored){}
        assistantAttachmentUri=null;assistantUploadedAttachment=null;assistantAttachmentThread="";assistantAttachmentAccount="";assistantAttachmentBusy=false;assistantAttachmentPicking=false;
    }
    private void pickAssistantAttachment(){
        if(assistantAttachmentBusy){message("Дождитесь загрузки файла.");return;}
        if(me==null||token==null){message("Войдите в пространство.");return;}
        clearAssistantAttachment();assistantAttachmentThread=assistantConversation;assistantAttachmentAccount=me.optString("id");assistantAttachmentPicking=true;
        assistantAttachmentRequestKey=java.util.UUID.randomUUID().toString();
        Intent picker=new Intent(Intent.ACTION_OPEN_DOCUMENT);picker.setType("*/*");picker.addCategory(Intent.CATEGORY_OPENABLE);
        picker.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"application/pdf","text/plain","text/markdown","text/x-markdown","application/octet-stream"});
        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        try{startActivityForResult(picker,305);}catch(android.content.ActivityNotFoundException error){clearAssistantAttachment();message("На устройстве нет приложения для выбора документов.");}
    }
    private void receiveAssistantAttachment(int resultCode,Intent data){
        assistantAttachmentPicking=false;
        if(resultCode!=RESULT_OK||data==null||data.getData()==null){clearAssistantAttachment();return;}
        android.net.Uri uri=data.getData();
        if(!"content".equals(uri.getScheme())){clearAssistantAttachment();message("Выберите документ через приложение «Файлы».");return;}
        assistantAttachmentUri=uri;
        if((data.getFlags()&Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)!=0)try{getContentResolver().takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION);}catch(SecurityException ignored){}
        if(me!=null)previewAssistantAttachment();
    }
    private static class AssistantAttachmentSource {
        final String name;final byte[] bytes;final boolean pdf;
        AssistantAttachmentSource(String name,byte[] bytes,boolean pdf){this.name=name;this.bytes=bytes;this.pdf=pdf;}
    }
    private AssistantAttachmentSource readAssistantAttachment(android.net.Uri uri)throws Exception{
        String name=null,mime=getContentResolver().getType(uri);long declared=-1;
        try(android.database.Cursor cursor=getContentResolver().query(uri,new String[]{android.provider.OpenableColumns.DISPLAY_NAME,android.provider.OpenableColumns.SIZE},null,null,null)){
            if(cursor!=null&&cursor.moveToFirst()){int nameColumn=cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME),sizeColumn=cursor.getColumnIndex(android.provider.OpenableColumns.SIZE);if(nameColumn>=0)name=cursor.getString(nameColumn);if(sizeColumn>=0&&!cursor.isNull(sizeColumn))declared=cursor.getLong(sizeColumn);}
        }
        if(name==null||name.isBlank())name="Документ"+("application/pdf".equals(mime)?".pdf":"text/markdown".equals(mime)?".md":".txt");
        name=name.replace('\\','/');name=name.substring(name.lastIndexOf('/')+1).replaceAll("\\p{Cntrl}","").trim();
        String lower=name.toLowerCase(Locale.ROOT);boolean pdf=lower.endsWith(".pdf");
        if(!pdf&&!lower.endsWith(".txt")&&!lower.endsWith(".md"))throw new IOException("Выберите PDF, TXT или Markdown.");
        if(name.length()>180)throw new IOException("Имя файла слишком длинное. Сократите его до 180 символов.");
        if(declared>assistantMaxUpload)throw new IOException("Максимальный размер файла — "+(assistantMaxUpload/1_000_000)+" МБ.");
        byte[] bytes;try(InputStream input=getContentResolver().openInputStream(uri)){bytes=readLimited(input,assistantMaxUpload);}
        if(bytes.length==0)throw new IOException("Файл пустой. Выберите другой документ.");
        if(pdf){if(bytes.length<5||!new String(bytes,0,5,StandardCharsets.US_ASCII).equals("%PDF-"))throw new IOException("Файл не похож на PDF. Выберите другой документ.");}
        else{try{String text=StandardCharsets.UTF_8.newDecoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT).onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(bytes)).toString();if(text.indexOf('\0')>=0)throw new IOException("TXT и Markdown должны содержать текст UTF-8.");}catch(java.nio.charset.CharacterCodingException error){throw new IOException("TXT и Markdown должны содержать текст UTF-8.");}}
        return new AssistantAttachmentSource(name,bytes,pdf);
    }
    private void returnFromAssistantAttachment(){
        String thread=assistantAttachmentThread,account=assistantAttachmentAccount;clearAssistantAttachment();
        if(me!=null&&account.equals(me.optString("id"))){assistantConversation=thread;getPreferences(MODE_PRIVATE).edit().putString(assistantPreference(),thread).apply();assistant();}
    }
    private void previewAssistantAttachment(){
        if(me==null||token==null||!me.optString("id").equals(assistantAttachmentAccount)){clearAssistantAttachment();return;}
        assistantConversation=assistantAttachmentThread;
        parentPage="assistant";page("Файл для ассистента","assistant-attachment",true);content.addView(ui.label("Добавить документ",25,INK,true));loading(content);
        final int version=pageVersion;final android.net.Uri uri=assistantAttachmentUri;
        worker.execute(()->{try{AssistantAttachmentSource source=readAssistantAttachment(uri);runOnUiThread(()->{
            if(version!=pageVersion||isFinishing())return;clearLoading(content);ui.space(content,18);
            TextView name=ui.label(source.name,17,INK,true);name.setMaxLines(3);name.setEllipsize(android.text.TextUtils.TruncateAt.END);content.addView(name);ui.space(content,8);
            text((source.pdf?"PDF":source.name.toLowerCase(Locale.ROOT).endsWith(".md")?"Markdown":"TXT")+" · "+new java.text.DecimalFormat("0.#").format(source.bytes.length/1000.0)+" КБ");
            text(assistantAttachmentThread.isEmpty()?"Для документа будет создан отдельный диалог.":"Документ станет контекстом текущего диалога.");
            if(source.pdf)content.addView(ui.label("Ассистент читает текст PDF. Для сканов распознавание может быть недоступно.",11,MUTED,false));
            ui.space(content,20);button(assistantUploadedAttachment==null?"Прикрепить к диалогу":"Связать с диалогом",true,v->uploadAssistantAttachment(source,(Button)v));
            button("Выбрать другой файл",false,v->pickAssistantAttachment());button("Отмена",false,v->returnFromAssistantAttachment());
        });}catch(Exception error){runOnUiThread(()->{if(version!=pageVersion||isFinishing())return;clearLoading(content);text(error.getMessage()==null?"Не удалось прочитать файл.":error.getMessage());button("Выбрать другой файл",true,v->pickAssistantAttachment());button("Вернуться в диалог",false,v->returnFromAssistantAttachment());});}});
    }
    private void uploadAssistantAttachment(AssistantAttachmentSource source,Button submit){
        if(assistantAttachmentBusy)return;assistantAttachmentBusy=true;submit.setEnabled(false);submit.setText("Прикрепляю…");
        if(assistantAttachmentRequestKey.isEmpty())assistantAttachmentRequestKey=java.util.UUID.randomUUID().toString();
        final String requestKey=assistantAttachmentRequestKey;
        final int version=pageVersion,generation=assistantAttachmentGeneration;final String session=token,account=assistantAttachmentAccount,thread=assistantAttachmentThread;
        final String draft=getPreferences(MODE_PRIVATE).getString(assistantDraftKey(thread,account),"");final JSONObject uploaded=assistantUploadedAttachment;
        worker.execute(()->{try{
            JSONObject file=uploaded;
            if(file==null){file=request("/files","POST",new JSONObject().put("_request_key",requestKey).put("assistant_upload",true).put("name",source.name).put("content",android.util.Base64.encodeToString(source.bytes,android.util.Base64.NO_WRAP)),session).optJSONObject("file");
                if(file==null)throw new IOException("Сервер не вернул документ.");final JSONObject saved=file;runOnUiThread(()->{if(generation==assistantAttachmentGeneration&&session.equals(token)&&me!=null&&account.equals(me.optString("id")))assistantUploadedAttachment=saved;});}
            JSONObject body=new JSONObject().put("context_entity","files").put("context_id",file.optString("id"));
            if(thread.isEmpty())body.put("title",source.name.substring(0,Math.min(120,source.name.length()))).put("_request_key",requestKey);
            JSONObject result=request(thread.isEmpty()?"/assistant/conversations":"/assistant/conversations/"+thread,thread.isEmpty()?"POST":"PATCH",body,session).optJSONObject("conversation");
            if(result==null)throw new IOException("Не удалось открыть диалог с файлом.");final JSONObject selected=result;
            runOnUiThread(()->{if(generation!=assistantAttachmentGeneration)return;assistantAttachmentBusy=false;if(!session.equals(token)||me==null||!account.equals(me.optString("id")))return;
                if(thread.isEmpty()){getPreferences(MODE_PRIVATE).edit().putString(assistantDraftKey(selected.optString("id"),account),draft).apply();if(draft.equals(getPreferences(MODE_PRIVATE).getString(assistantDraftKey(thread,account),"")))getPreferences(MODE_PRIVATE).edit().remove(assistantDraftKey(thread,account)).apply();}
                clearAssistantAttachment();if(version==pageVersion){selectAssistantThread(selected);message("Документ прикреплён. Теперь можно задать вопрос.");}
            });
        }catch(Exception error){runOnUiThread(()->{if(generation!=assistantAttachmentGeneration)return;assistantAttachmentBusy=false;if(version!=pageVersion||isFinishing()||!session.equals(token))return;submit.setEnabled(true);submit.setText(assistantUploadedAttachment==null?"Повторить загрузку":"Связать с диалогом");message(error instanceof ApiException?error.getMessage():"Не удалось прикрепить документ. Сообщение сохранено, попробуйте ещё раз.");});}});
    }
    private void assistantJobs(){
        parentPage="assistant";page("Фоновые задачи","assistant-jobs",true);
        content.addView(ui.label("Задачи ассистента",25,INK,true));
        text("Работа продолжается после закрытия приложения.");
        Button refresh=button("Обновить",false,v->assistantJobs());
        LinearLayout host=ui.column();content.addView(host);final int version=pageVersion;
        loadAssistantJobs(host,refresh,version);
    }
    private void loadAssistantJobs(LinearLayout host,Button refresh,int version){
        if(isFinishing()||version!=pageVersion)return;
        call("/assistant/jobs","GET",null,result->{
            if(version!=pageVersion)return;host.removeAllViews();JSONArray jobs=result.optJSONArray("jobs");boolean active=false;
            if(jobs==null||jobs.length()==0){host.addView(ui.label("Пока нет фоновых задач",13,MUTED,false));return;}
            for(int i=0;i<jobs.length();i++){JSONObject job=jobs.optJSONObject(i);if(job==null)continue;
                String status=job.optString("status"),id=job.optString("id");boolean running=status.equals("queued")||status.equals("running")||status.equals("retry");active|=running;
                ui.space(host,16);TextView title=ui.label(job.optString("prompt"),14,INK,true);title.setMaxLines(2);title.setEllipsize(android.text.TextUtils.TruncateAt.END);host.addView(title);ui.space(host,5);
                host.addView(ui.label(job.optString("error").isEmpty()?job.optString("progress"):job.optString("error"),12,MUTED,false));
                if(running){Button cancel=addButton(host,job.optBoolean("cancel_requested")?"Отменяю…":"Отменить",false,v->call("/assistant/jobs/"+id,"DELETE",null,r->loadAssistantJobs(host,refresh,version)));cancel.setEnabled(!job.optBoolean("cancel_requested"));}
                else if(status.equals("completed"))addButton(host,(job.optString("kind").equals("file_index")||job.optString("kind").equals("file_ocr"))?"Открыть документ":"Открыть ответ",false,v->{if((job.optString("kind").equals("file_index")||job.optString("kind").equals("file_ocr"))){askAssistant("files",job.optString("file_id"),job.optString("prompt"));return;}String thread=job.optString("conversation_id");if(thread.isEmpty()){selectAssistantThread(null);}else call("/assistant/conversations/"+thread,"GET",null,r->selectAssistantThread(r.optJSONObject("conversation")));});
                ui.space(host,12);ui.divider(host);
            }
            if(active)host.postDelayed(()->{if(version==pageVersion&&!isFinishing()&&hasWindowFocus())loadAssistantJobs(host,refresh,version);},5000);
        });
    }
    private void applyAssistantQuota(JSONObject quota,TextView label,Button send){
        if(quota==null)return;
        int remaining=quota.optInt("remaining"),limit=quota.optInt("limit");
        label.setText(remaining+" из "+limit+" сообщений · "+(quota.optString("plan").equals("pro")?"Про":"Старт"));
        assistantRemaining=remaining;
        send.setEnabled(remaining>0&&assistantAvailable&&!assistantFileBlocked&&!assistantStreaming);
        if(remaining==0)send.setText("Лимит на месяц исчерпан");
        else send.setText("Отправить ↗");
    }
    private void streamAssistant(String value,LinearLayout messages,EditText prompt,TextView allowance,Button send){
        final int version=pageVersion;
        final String conversationId=assistantConversation;
        final JSONObject context=assistantContext;
        assistantStreaming=true;send.setEnabled(false);
        TextView userText=assistantMessage(messages,"user",value);
        TextView answerText=assistantMessage(messages,"assistant","");
        answerText.setText("Думаю…");
        worker.execute(()->{
            HttpURLConnection connection=null;
            StringBuilder answer=new StringBuilder();
            JSONObject[] currentQuota={null};
            boolean completed=false;
            try{
                connection=(HttpURLConnection)new URL(BuildConfig.API_BASE_URL+"/api/assistant/stream").openConnection();
                connection.setConnectTimeout(10000);
                connection.setReadTimeout(110000);
                connection.setRequestMethod("POST");
                connection.setRequestProperty("Accept","text/event-stream");
                connection.setRequestProperty("Authorization","Bearer "+token);
                connection.setRequestProperty("Content-Type","application/json");
                connection.setDoOutput(true);
                try(OutputStream output=connection.getOutputStream()){
                    JSONObject payload=new JSONObject().put("text",value).put("context",context==null?JSONObject.NULL:context);
                    if(!conversationId.isEmpty())payload.put("conversation_id",conversationId);
                    output.write(payload.toString().getBytes(StandardCharsets.UTF_8));
                }
                int code=connection.getResponseCode();
                if(code>=400){
                    try(InputStream error=connection.getErrorStream()){
                        JSONObject details=new JSONObject(new String(readLimited(error,65536),StandardCharsets.UTF_8));
                        throw new ApiException(code,details.optString("error","Ошибка сервера: "+code));
                    }
                }
                try(BufferedReader reader=new BufferedReader(new InputStreamReader(connection.getInputStream(),StandardCharsets.UTF_8))){
                    String line,kind="",payload="";
                    long lastPaint=0;
                    while((line=reader.readLine())!=null){
                        if(line.isEmpty()){
                            if(!kind.isEmpty()&&!payload.isEmpty()){
                                JSONObject event=new JSONObject(payload);
                                if(kind.equals("ready"))currentQuota[0]=event.optJSONObject("quota");
                                else if(kind.equals("delta")){
                                    answer.append(event.optString("text"));
                                    long now=android.os.SystemClock.uptimeMillis();
                                    if(now-lastPaint>55){
                                        lastPaint=now;
                                        String snapshot=answer.toString();
                                        runOnUiThread(()->{if(version==pageVersion)answerText.setText(snapshot);});
                                    }
                                }else if(kind.equals("done")){
                                    completed=true;
                                    JSONObject quota=event.optJSONObject("quota");
                                    String finalAnswer=event.optString("answer");
                                    JSONArray actions=event.optJSONArray("actions");
                                    runOnUiThread(()->{if(version!=pageVersion)return;
                                        answerText.setText(formatAssistantMarkdown(finalAnswer));
                                        assistantStreaming=false;prompt.setText("");
                                        applyAssistantQuota(quota,allowance,send);
                                        if(actions!=null)for(int i=0;i<actions.length();i++)assistantAction(messages,actions.optJSONObject(i));
                                    });
                                    break;
                                }else if(kind.equals("error")){
                                    currentQuota[0]=event.optJSONObject("quota");
                                    throw new ApiException(502,event.optString("error","Ответ прервался"));
                                }
                            }
                            kind="";payload="";
                        }else if(line.startsWith("event:"))kind=line.substring(6).trim();
                        else if(line.startsWith("data:"))payload+=line.substring(5).trim();
                    }
                }
                if(!completed)throw new IOException("Поток ответа оборвался");
            }catch(Exception error){
                runOnUiThread(()->{if(version!=pageVersion)return;assistantStreaming=false;
                    messages.removeView(userText.getParent() instanceof View?(View)userText.getParent():userText);
                    messages.removeView(answerText.getParent() instanceof View?(View)answerText.getParent():answerText);
                    applyAssistantQuota(currentQuota[0],allowance,send);
                    if(currentQuota[0]==null)send.setEnabled(assistantAvailable&&assistantRemaining>0&&!assistantFileBlocked);
                    message(error instanceof ApiException?error.getMessage():"Не удалось получить ответ. Попробуйте ещё раз.");
                });
            }finally{if(connection!=null)connection.disconnect();}
        });
    }
    private CharSequence formatAssistantMarkdown(String value){
        String safe=android.text.TextUtils.htmlEncode(value);
        safe=safe.replaceAll("(?m)^#{1,3} +(.+)$","<big><b>$1</b></big>");
        safe=safe.replaceAll("\\*\\*([^*\\n]+)\\*\\*","<b>$1</b>");
        safe=safe.replaceAll("(?m)^[-*] +","• ");
        safe=safe.replace("\n","<br>");
        return android.text.Html.fromHtml(safe,android.text.Html.FROM_HTML_MODE_COMPACT);
    }
    private TextView assistantMessage(LinearLayout host,String role,String value){
        LinearLayout row=ui.column();
        row.setPadding(0,dp(19),0,dp(20));
        host.addView(row,ui.match());
        TextView who=ui.label(role.equals("user")?"ВЫ":"СМЕТРА",10,role.equals("user")?MUTED:BLUE,true);
        row.addView(who);
        ui.space(row,9);
        TextView body=ui.label("",14,role.equals("user")?MUTED:INK,false);
        body.setText(role.equals("user")?value:formatAssistantMarkdown(value));
        body.setTextIsSelectable(true);
        row.addView(body);
        ui.divider(host);
        ui.enter(row);
        return body;
    }
    private String fieldLabel(String key){switch(key){case "optional":return "\u041e\u043f\u0446\u0438\u043e\u043d\u0430\u043b\u044c\u043d\u0430\u044f \u043f\u043e\u0437\u0438\u0446\u0438\u044f";case "included":return "\u0412\u043a\u043b\u044e\u0447\u0435\u043d\u0430 \u0432 \u0440\u0430\u0441\u0447\u0451\u0442";case "unit_price":return "Цена";case "quantity":return "Количество";case "coefficient":return "Коэффициент";case "markup":return "Наценка, %";case "discount":return "Скидка, %";case "tax":return "Налог, %";case "unit":return "Единица";case "category":return "Категория";case "notes":return "Заметки";case "title":case "name":return "Название";case "client":return "Клиент";case "description":return "Описание";case "amount":case "amount_kopecks":return "Сумма";case "items":return "Работы";case "due_date":return "Срок";case "email":return "Почта";case "phone":return "Телефон";case "terms":return "Условия";case "currency":return "Валюта";default:return key;}}
    private String assistantEditValue(String field,Object value,String currency){
        if(value==null||value==JSONObject.NULL||value.toString().isEmpty())return "—";
        if(field.equals("optional")||field.equals("included"))return Boolean.TRUE.equals(value)?"Да":"Нет";
        if(field.equals("unit_price")||field.equals("amount")||field.equals("amount_kopecks")||field.equals("price")){
            try{return exactMoney(Long.parseLong(value.toString()),currency);}catch(NumberFormatException ignored){}
        }
        if(value instanceof JSONArray){JSONArray values=(JSONArray)value;StringBuilder names=new StringBuilder();for(int i=0;i<values.length();i++){if(i>0)names.append(", ");JSONObject item=values.optJSONObject(i);names.append(item==null?"Позиция":item.optString("name","Позиция"));}return names.toString();}
        return value instanceof JSONObject?"Данные записи":value.toString();
    }
    private void assistantDiffRow(LinearLayout host,JSONObject row,String currency){
        if(row==null)return;
        if(row.has("change")){
            String change=row.optString("change"),action=change.equals("insert")?"Добавить":change.equals("remove")?"Удалить":"Переместить";
            JSONObject before=row.optJSONObject("before"),after=row.optJSONObject("after"),item=after!=null?after:before;
            ui.space(host,12);host.addView(ui.label(action+" · "+(item==null?"Позиция":item.optString("name")),12,INK,true));
            ui.space(host,5);host.addView(ui.label("Было: "+assistantStructureItem(before,row.optInt("before_row"),currency),11,MUTED,false));
            ui.space(host,4);host.addView(ui.label("Станет: "+assistantStructureItem(after,row.optInt("after_row"),currency),11,BLUE,false));return;
        }
        String field=row.optString("field");
        String heading=(row.has("row")?row.optInt("row")+". "+row.optString("name")+" · ":"")+fieldLabel(field);
        ui.space(host,12);host.addView(ui.label(heading,11,MUTED,false));ui.space(host,5);
        LinearLayout values=ui.row();host.addView(values,ui.match());
        TextView before=ui.label(assistantEditValue(field,row.opt("before"),currency),13,MUTED,false);
        before.setPaintFlags(before.getPaintFlags()|android.graphics.Paint.STRIKE_THRU_TEXT_FLAG);
        values.addView(before,new LinearLayout.LayoutParams(0,-2,1));
        values.addView(ui.label(assistantEditValue(field,row.opt("after"),currency),13,BLUE,false),new LinearLayout.LayoutParams(0,-2,1));
    }
    private String assistantStructureItem(JSONObject item,int position,String currency){
        if(item==null)return "—";
        return "Строка "+position+" · "+item.optString("quantity")+" "+item.optString("unit")+" × "+exactMoney(item.optLong("unit_price"),currency)+" · "+exactMoney(item.optLong("subtotal"),currency)+(item.optBoolean("optional")?(item.optBoolean("included")?" · опция включена":" · опция исключена"):"");
    }
    private void assistantPreview(LinearLayout host,JSONObject preview){
        String currency=preview.optString("currency","RUB");JSONArray rows=preview.optJSONArray("rows");
        if(rows!=null){for(int i=0;i<Math.min(5,rows.length());i++)assistantDiffRow(host,rows.optJSONObject(i),currency);
            if(rows.length()>5){LinearLayout extra=ui.column();extra.setVisibility(View.GONE);host.addView(extra);for(int i=5;i<rows.length();i++)assistantDiffRow(extra,rows.optJSONObject(i),currency);addButton(host,"Ещё "+(rows.length()-5)+" изменений",false,v->{boolean show=extra.getVisibility()!=View.VISIBLE;extra.setVisibility(show?View.VISIBLE:View.GONE);((Button)v).setText(show?"Свернуть":"Ещё "+(rows.length()-5)+" изменений");});}
        }
        if(preview.optString("kind").equals("quote_structure")){ui.space(host,12);host.addView(ui.label("Позиций: "+preview.optInt("before_count")+" → "+preview.optInt("after_count"),11,MUTED,false));}
        if(preview.optString("kind").equals("quote_items")||preview.optString("kind").equals("quote_structure")){ui.space(host,18);host.addView(ui.label("Итого по смете",11,MUTED,false));ui.space(host,5);host.addView(ui.label(exactMoney(preview.optLong("before_total"),currency)+" → "+exactMoney(preview.optLong("after_total"),currency),17,INK,true));}
    }
    private void assistantUndo(LinearLayout host,JSONObject action){
        host.removeAllViews();host.addView(ui.label("Сохранено · "+action.optString("summary"),14,INK,false));
        addButton(host,"Отменить изменение",false,v->{v.setEnabled(false);try{call("/assistant/undo","POST",new JSONObject().put("id",action.optString("id")),r->{host.removeAllViews();host.addView(ui.label("Изменение отменено · "+action.optString("summary"),13,BLUE,false));});}catch(Exception error){message(error.getMessage());}v.setEnabled(true);});
    }
    private void assistantAction(LinearLayout host,JSONObject action){
        if(action==null)return;
        LinearLayout proposal=ui.card(host);proposal.addView(ui.label("ПРЕДЛОЖЕНИЕ · ЕЩЁ НЕ СОХРАНЕНО",10,BLUE,true));ui.space(proposal,12);proposal.addView(ui.label(action.optString("summary"),17,INK,true));
        JSONObject preview=action.optJSONObject("preview"),fields=action.optJSONObject("arguments");
        if(preview!=null)assistantPreview(proposal,preview);
        else if(fields!=null){java.util.Iterator<String> keys=fields.keys();while(keys.hasNext()){String key=keys.next();if(key.equals("id")||key.equals("revision"))continue;ui.space(proposal,10);proposal.addView(ui.label(fieldLabel(key),11,MUTED,false));ui.space(proposal,3);proposal.addView(ui.label(assistantEditValue(key,fields.opt(key),fields.optString("currency","RUB")),14,INK,false));}}
        addButton(proposal,"Применить",true,v->{try{call("/assistant/confirm","POST",new JSONObject().put("id",action.optString("id")),r->{if(r.optBoolean("undoable"))assistantUndo(proposal,action);else{proposal.removeAllViews();proposal.addView(ui.label("Сохранено · "+action.optString("summary"),14,BLUE,false));}});}catch(Exception error){message(error.getMessage());}});
        addButton(proposal,"Не сейчас",false,v->{try{call("/assistant/dismiss","POST",new JSONObject().put("id",action.optString("id")),r->host.removeView(proposal));}catch(Exception error){message(error.getMessage());}});
    }

    private void refresh(){call("/me","GET",null,result->{me=result.optJSONObject("user");Analytics.identify(me);if(me!=null&&me.optString("id").equals(assistantAttachmentAccount)){if(assistantAttachmentUri!=null)previewAssistantAttachment();else if(assistantAttachmentPicking)assistant();else home();}else{clearAssistantAttachment();home();}});}
    private void home(){
        publicView=false;page("Сегодня","home",false);
        content.addView(ui.label(presentation.homeEyebrow,10,MUTED,true));ui.space(content,8);
        content.addView(ui.label(presentation.homeTitle,26,INK,true));ui.space(content,14);
        button(presentation.createLabel,true,v->create());button(presentation.captureLabel,false,v->capture());

        LinearLayout summary=ui.card(content),metrics=ui.row();summary.addView(metrics);
        TextView total=homeMetric(metrics,"Проекты"),waiting=homeMetric(metrics,"Ждут оплаты"),approved=homeMetric(metrics,"Согласовано за месяц");
        ui.space(summary,12);TextView received=ui.label("Получено за месяц · —",13,MUTED,false);summary.addView(received);
        ui.section(content,"Требует внимания",null);LinearLayout actionHost=ui.column();content.addView(actionHost);loading(actionHost);
        ui.section(content,"Ваши сметы",null);
        LinearLayout filters=ui.row();filters.setPadding(0,dp(12),0,dp(6));HorizontalScrollView scroller=new HorizontalScrollView(this);scroller.setHorizontalScrollBarEnabled(false);scroller.addView(filters);content.addView(scroller);
        LinearLayout host=ui.column(),more=ui.column();content.addView(host);content.addView(more);loading(host);
        final JSONArray[] data={new JSONArray()};final int[] totalCount={0};final String[] selected={""};
        call("/dashboard","GET",null,result->{
            JSONObject overview=result.optJSONObject("overview"),quoteCounts=overview==null?null:overview.optJSONObject("quotes");
            if(quoteCounts!=null)totalCount[0]=quoteCounts.optInt("total");
            JSONObject actions=result.optJSONObject("actions"),overviewSummary=actions==null?null:actions.optJSONObject("summary");
            if(overviewSummary!=null){total.setText(String.valueOf(overviewSummary.optInt("active_projects")));waiting.setText(String.valueOf(overviewSummary.optInt("waiting_payments")));approved.setText(String.valueOf(overviewSummary.optInt("approved_this_month")));JSONObject earned=overviewSummary.optJSONObject("received_this_month");received.setText("Получено за месяц · "+exactMoney(earned==null?0:earned.optLong("RUB"),"RUB"));}
            renderTodayActions(actionHost,actions==null?null:actions.optJSONArray("items"));
            JSONArray recent=result.optJSONArray("quotes");if(recent!=null&&recent.length()>0){data[0]=recent;homeFilters(filters,host,data[0],totalCount[0],selected);renderQuotes(host,data[0],selected[0]);}
        });
        call("/quotes","GET",null,result->{
            JSONArray list=result.optJSONArray("quotes");data[0]=list==null?new JSONArray():list;
            homeFilters(filters,host,data[0],Math.max(totalCount[0],data[0].length()),selected);
            renderQuotes(host,data[0],selected[0]);homeMore(host,more,filters,data[0],totalCount,selected);
        });
    }
    private void renderTodayActions(LinearLayout host,JSONArray actions){
        host.removeAllViews();
        if(actions==null||actions.length()==0){host.addView(ui.label("Срочных действий нет. Можно подготовить следующий запрос клиента.",13,MUTED,false));return;}
        for(int i=0;i<actions.length();i++){
            JSONObject action=actions.optJSONObject(i);if(action==null)continue;
            LinearLayout row=ui.column();row.setPadding(0,dp(13),0,dp(13));
            row.addView(ui.label(action.optString("title"),15,INK,true));ui.space(row,5);
            String detail=action.optString("detail");if(action.optLong("amount_kopecks")>0)detail+=" · "+exactMoney(action.optLong("amount_kopecks"),action.optString("currency","RUB"));
            row.addView(ui.label(detail,12,MUTED,false));host.addView(row);ui.divider(host);
            ui.tap(row,()->{String kind=action.optString("kind"),id=action.optString("entity_id");if(kind.equals("project"))project(id);else if(kind.equals("task"))records("tasks");else if(kind.equals("lead"))call("/leads/"+id,"GET",null,result->{JSONObject lead=result.optJSONObject("item");if(lead!=null&&!lead.optString("client_id").isEmpty())client(lead.optString("client_id"));});else if(kind.equals("quote")){try{openQuote(new JSONObject().put("id",id));}catch(Exception error){message(error.getMessage());}}});
        }
    }
    private TextView homeMetric(LinearLayout parent,String title){
        LinearLayout cell=ui.column();cell.setPadding(0,dp(5),dp(7),dp(5));parent.addView(cell,new LinearLayout.LayoutParams(0,-2,1));
        TextView number=ui.label("—",29,INK,true);cell.addView(number);ui.space(cell,8);cell.addView(ui.label(title,11,MUTED,false));return number;
    }
    private void homeFilters(LinearLayout filters,LinearLayout host,JSONArray list,int total,String[] selected){
        filters.removeAllViews();String[] names={"Все · "+total,"Черновики","На согласовании","Согласованы"},values={"","draft","sent","approved"};
        for(int i=0;i<names.length;i++){
            String value=values[i];boolean active=value.equals(selected[0]);TextView chip=ui.label(names[i],12,active?BG:MUTED,true);chip.setGravity(Gravity.CENTER);chip.setMinimumHeight(dp(48));chip.setPadding(dp(14),dp(14),dp(14),dp(14));ui.ripple(chip,active?BLUE:SURFACE,14,0);chip.setSelected(active);
            LinearLayout.LayoutParams cp=new LinearLayout.LayoutParams(-2,-2);cp.rightMargin=dp(7);filters.addView(chip,cp);
            ui.tap(chip,()->{selected[0]=value;homeFilters(filters,host,list,total,selected);renderQuotes(host,list,value);});
        }
    }
    private void homeMore(LinearLayout host,LinearLayout more,LinearLayout filters,JSONArray list,int[] total,String[] selected){
        more.removeAllViews();if(list.length()<30||total[0]>0&&list.length()>=total[0])return;
        addButton(more,"Показать ещё",false,v->call("/quotes?offset="+list.length(),"GET",null,result->{
            JSONArray next=result.optJSONArray("quotes");if(next!=null)for(int i=0;i<next.length();i++)list.put(next.opt(i));
            homeFilters(filters,host,list,Math.max(total[0],list.length()),selected);renderQuotes(host,list,selected[0]);
            if(next==null||next.length()<30)more.removeAllViews();else homeMore(host,more,filters,list,total,selected);
        }));
    }
    private void action(LinearLayout parent,String icon,String title,Runnable click){LinearLayout item=ui.column();item.setGravity(Gravity.CENTER);item.setPadding(dp(4),dp(8),dp(4),dp(8));FrameLayout tile=new FrameLayout(this);tile.setBackground(ui.shape(BG,12,LINE));tile.addView(ui.new Icon(icon,BLUE),new FrameLayout.LayoutParams(dp(23),dp(23),Gravity.CENTER));item.addView(tile,new LinearLayout.LayoutParams(dp(54),dp(54)));ui.space(item,9);TextView caption=ui.label(title,11,INK,false);caption.setGravity(Gravity.CENTER);item.addView(caption);ui.tap(item,click);item.setContentDescription(title);parent.addView(item,new LinearLayout.LayoutParams(0,-2,1));}
    private void renderQuotes(LinearLayout host,JSONArray list,String filter){host.removeAllViews();int shown=0;for(int i=0;i<list.length();i++){JSONObject q=list.optJSONObject(i);if(q==null)continue;String state=q.optString("approval_state",q.optString("status"));boolean matches=filter.isEmpty()||filter.equals(state)||filter.equals("sent")&&(state.equals("viewed")||state.equals("changes_requested"))||filter.equals("approved")&&state.equals("accepted");if(!matches)continue;shown++;LinearLayout row=ui.card(host);LinearLayout top=ui.row();TextView title=ui.label(q.optString("title"),16,INK,true);title.setMaxLines(2);top.addView(title,new LinearLayout.LayoutParams(0,-2,1));ui.gap(top,12);TextView amount=ui.label(exactMoney(q.optLong("amount_kopecks"),q.optString("currency","RUB")),15,INK,false);top.addView(amount);row.addView(top);ui.space(row,7);row.addView(ui.label(q.optString("client","Без клиента"),12,MUTED,false));ui.space(row,9);row.addView(ui.badge(status(state),statusColor(state)));ui.tap(row,()->openQuote(q));}
        if(shown==0){ui.empty(host,"document",filter.isEmpty()?"Всё начинается с первой сметы":"Пока пусто",filter.isEmpty()?"Соберите работы и стоимость.\nОтправьте клиенту одну ссылку.":"Сметы с этим статусом появятся здесь.");if(filter.isEmpty())addButton(host,"Создать первую смету",true,v->create());}ui.enter(host);
    }
    private void openQuote(JSONObject q){
        if(q.has("items")){quote(q);return;}
        String id=q.optString("id");page("Смета","quote",true);loading(content);
        call("/quotes/"+id,"GET",null,result->{JSONObject full=result.optJSONObject("quote");if(full!=null)quote(full);});
    }
    private void quote(JSONObject q){parentPage="home";page("Смета","quote",true);String state=q.optString("approval_state",q.optString("status")),currency=q.optString("currency","RUB");content.addView(ui.badge(status(state),statusColor(state)));ui.space(content,18);content.addView(ui.label(q.optString("title"),26,INK,true));text(q.optString("client"));LinearLayout price=ui.card(content);price.addView(ui.label("Стоимость работ",12,BLUE,false));ui.space(price,12);price.addView(ui.label(exactMoney(q.optLong("amount_kopecks"),currency),32,INK,true));
        if(!q.optString("description").isEmpty()){ui.section(content,"О проекте",null);text(q.optString("description"));}
        JSONArray items=q.optJSONArray("items");if(items!=null&&items.length()>0){ui.section(content,"Состав сметы",null);for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);if(item==null)continue;LinearLayout row=ui.card(content),top=ui.row();TextView name=ui.label(item.optString("name"),15,INK,true);name.setMaxLines(3);top.addView(name,new LinearLayout.LayoutParams(0,-2,1));ui.gap(top,10);top.addView(ui.label(exactMoney(item.optLong("subtotal"),currency),14,INK,false));row.addView(top);ui.space(row,7);row.addView(ui.label(item.optString("quantity","1")+" "+item.optString("unit","шт.")+(item.optBoolean("optional")&&!item.optBoolean("included",true)?" · Опционально":""),12,MUTED,false));}}
        String id=q.optString("id");ui.space(content,20);
        button("Спросить ассистента",false,v->askAssistant("quotes",id,q.optString("title")));
        if(state.equals("draft"))button("Отправить на согласование",true,v->ui.sheet("Всё готово к отправке?","Сохраним текущую версию сметы. Клиент сможет открыть её по ссылке и согласовать условия.","Опубликовать смету",false,()->{try{call("/quotes/"+id+"/status","POST",new JSONObject().put("status","sent").put("revision",q.optInt("revision")),r->{String url=r.optJSONObject("quote")!=null?r.optJSONObject("quote").optString("public_url"):"";Analytics.event("estimate_sent",Analytics.params("source","android"),true);home();share(url);});}catch(Exception error){message(error.getMessage());}}));
        if(state.equals("sent")||state.equals("viewed")||state.equals("changes_requested")||state.equals("approved")||state.equals("accepted"))button("Поделиться ссылкой",true,v->share(q.optString("public_url")));
        if(state.equals("approved")||state.equals("accepted"))button("Создать заказ из сметы",false,v->{try{call("/quotes/"+id+"/project","POST",new JSONObject(),r->{Analytics.event("project_created",Analytics.params("source","estimate"),true);records("projects");});}catch(Exception error){message(error.getMessage());}});
    }
    private void share(String url){if(url.isEmpty()){message("Ссылка ещё не готова. Обновите смету.");return;}Intent intent=new Intent(Intent.ACTION_SEND);intent.setType("text/plain");intent.putExtra(Intent.EXTRA_TEXT,"Предложение по работе: "+url);startActivity(Intent.createChooser(intent,"Отправить предложение"));}
    private void capture(){
        parentPage="home";page("Новый запрос","capture",true);
        content.addView(ui.label("Что нужно посчитать?",26,INK,true));
        text("Вставьте сообщение клиента или выберите файл. Черновик можно изменить до сохранения.");
        EditText source=field("Запрос клиента",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        source.setSingleLine(false);source.setMinLines(5);source.setGravity(Gravity.TOP);
        source.setHint("Например: лендинг для кофейни, дизайн и вёрстка, срок три недели");
        String saved=getPreferences(MODE_PRIVATE).getString("capture_text","");
        source.setText(pendingCaptureText!=null?pendingCaptureText:saved);
        source.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){pendingCaptureText=s.toString();getPreferences(MODE_PRIVATE).edit().putString("capture_text",s.toString()).apply();}public void afterTextChanged(Editable value){}});
        if(pendingCaptureFile!=null){ui.space(content,10);content.addView(ui.label("Приложен файл · до 2 МБ",12,BLUE,false));}
        ui.space(content,12);
        button("Прикрепить файл",false,v->{Intent pick=new Intent(Intent.ACTION_OPEN_DOCUMENT);pick.setType("*/*");pick.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/png","image/jpeg","application/pdf","text/plain","text/csv","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet","application/vnd.openxmlformats-officedocument.wordprocessingml.document"});pick.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(pick,303);});
        button("Надиктовать запрос",false,v->{try{Intent voice=new Intent(android.speech.RecognizerIntent.ACTION_RECOGNIZE_SPEECH);voice.putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE_MODEL,android.speech.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);voice.putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE,"ru-RU");voice.putExtra(android.speech.RecognizerIntent.EXTRA_PROMPT,"Опишите работу для сметы");startActivityForResult(voice,302);}catch(Exception error){message("Голосовой ввод недоступен на этом устройстве");}});
        ui.space(content,12);
        Button draft=button("Составить черновик",true,v->{});
        draft.setOnClickListener(v->{String input=source.getText().toString().trim();android.net.Uri file=pendingCaptureFile;if(input.isEmpty()&&file==null){source.setError("Вставьте запрос или приложите файл");return;}draft.setEnabled(false);draft.setAlpha(.5f);int version=pageVersion;message("Составляем черновик…");worker.execute(()->{try{JSONObject body=new JSONObject().put("text",input);if(file!=null)body.put("file",captureSource(file));JSONObject response=request("/ai/draft","POST",body);JSONObject result=response.optJSONObject("draft");if(result==null)throw new IOException("Черновик не получен");Analytics.event("ai_draft_generated",Analytics.params("source",file==null?"text":"file"),false);runOnUiThread(()->{if(version!=pageVersion||isFinishing())return;pendingCaptureText=input;getPreferences(MODE_PRIVATE).edit().putString("capture_draft",result.toString()).apply();draftPreview(result);});}catch(Exception error){runOnUiThread(()->{if(version!=pageVersion||isFinishing())return;draft.setEnabled(true);draft.setAlpha(1);message(error instanceof ApiException?error.getMessage():"Не удалось разобрать запрос. Текст сохранён, попробуйте ещё раз.");});}});});
        button("Продолжить вручную",false,v->{String input=source.getText().toString().trim();if(input.isEmpty()){source.setError("Вставьте запрос");return;}try{getPreferences(MODE_PRIVATE).edit().putString("draft",new JSONObject().put("title",input.split("[\\n.!?]")[0].substring(0,Math.min(input.split("[\\n.!?]")[0].length(),120))).put("description",input).toString()).apply();create();}catch(Exception error){message("Не удалось открыть редактор");}});
        String old=getPreferences(MODE_PRIVATE).getString("capture_draft",null);if(old!=null)button("Продолжить сохранённый черновик",false,v->{try{draftPreview(new JSONObject(old));}catch(Exception error){message("Черновик повреждён");}});
        text("При обработке текст или файл передаётся OpenRouter. Никакая смета не отправляется клиенту автоматически.").setTextSize(11);
    }
    private JSONObject captureSource(android.net.Uri uri)throws Exception{
        String name=uri.getLastPathSegment(),mime=getContentResolver().getType(uri);
        try(android.database.Cursor cursor=getContentResolver().query(uri,new String[]{android.provider.OpenableColumns.DISPLAY_NAME},null,null,null)){if(cursor!=null&&cursor.moveToFirst())name=cursor.getString(0);}
        if(name==null||name.isBlank())name="source.txt";
        if(mime==null||mime.equals("application/octet-stream")){String suffix=name.substring(name.lastIndexOf('.')+1).toLowerCase(Locale.ROOT);switch(suffix){case "png":mime="image/png";break;case "jpg":case "jpeg":mime="image/jpeg";break;case "pdf":mime="application/pdf";break;case "csv":mime="text/csv";break;case "xlsx":mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";break;case "docx":mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document";break;default:mime="text/plain";}}
        byte[] bytes;try(InputStream input=getContentResolver().openInputStream(uri)){bytes=readLimited(input,2_000_000);}
        return new JSONObject().put("name",name).put("mime",mime).put("content",android.util.Base64.encodeToString(bytes,android.util.Base64.NO_WRAP));
    }
    private void draftPreview(JSONObject draft){
        parentPage="home";page("Проверка черновика","draft-preview",true);
        content.addView(ui.label("Проверьте перед сохранением.",26,INK,true));text("Неизвестные цены остались пустыми. Укажите клиента и стоимость работ.");
        EditText title=field("Название",1),client=field("Клиент",1),description=field("Описание",1),terms=field("Условия и сроки",1);
        title.setText(draft.optString("title"));client.setText(draft.optString("client"));description.setText(draft.optString("description"));terms.setText(draft.optString("terms"));
        JSONArray source=draft.optJSONArray("items");if(source==null)source=new JSONArray();
        java.util.ArrayList<EditText[]> rows=new java.util.ArrayList<>();
        for(int i=0;i<source.length();i++){JSONObject item=source.optJSONObject(i);if(item==null)continue;ui.section(content,"Позиция "+(i+1),null);EditText name=field("Работа",1),quantity=field("Количество",8194),unit=field("Единица",1),price=field("Цена, ₽",8194);name.setText(item.optString("name"));quantity.setText(item.optString("quantity","1"));unit.setText(item.optString("unit","усл."));long value=item.optLong("unit_price");if(value>0)price.setText(String.format(Locale.ROOT,"%.2f",value/100.0));rows.add(new EditText[]{name,quantity,unit,price});}
        button("Сохранить черновик",true,v->{if(title.length()==0){title.setError("Укажите название");return;}if(client.length()==0){client.setError("Укажите клиента");return;}try{JSONArray items=new JSONArray();long priced=0;for(EditText[] row:rows){if(row[0].length()==0){row[0].setError("Укажите работу");return;}long value=row[3].length()==0?0:cents(row[3]);if(value<0)throw new IllegalArgumentException();priced=Math.addExact(priced,value);items.put(new JSONObject().put("name",row[0].getText().toString()).put("quantity",row[1].getText().toString()).put("unit",row[2].getText().toString()).put("unit_price",value));}if(priced==0){message("Укажите цену хотя бы одной позиции");return;}JSONObject body=new JSONObject().put("title",title.getText().toString()).put("client",client.getText().toString()).put("description",description.getText().toString()).put("terms",terms.getText().toString()).put("items",items);call("/quotes","POST",body,result->{Analytics.event("estimate_created",Analytics.params("source","ai_capture"),true);pendingCaptureText=null;pendingCaptureFile=null;getPreferences(MODE_PRIVATE).edit().remove("capture_text").remove("capture_draft").apply();home();message("Смета сохранена. Теперь можно отправить её клиенту.");});}catch(Exception error){message("Проверьте позиции и цены");}});
    }
    private void create(){
        parentPage="home";page("Новая смета","create",true);content.addView(ui.label("Новая смета",26,INK,true));text("Укажите клиента и стоимость или соберите смету из своих расценок.");
        EditText title=field("Название работы",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES),client=field("Имя клиента или компания",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_WORDS),amount=field("Стоимость, ₽",8194),description=field("Что входит в работу",1);amount.setHint("0,00");description.setHint("Объём работ, результат, сроки…");
        java.util.ArrayList<JSONObject> selected=new java.util.ArrayList<>();
        final String[] currency={catalogCurrency},submittedBody={""},requestKey={""};
        final boolean[] savedCurrency={false};
        LinearLayout selectedHost=ui.column(),pickerHost=ui.column();
        final Runnable[] saveDraft={null},renderSelected={null};
        saveDraft[0]=()->{try{
            JSONArray items=new JSONArray();for(JSONObject item:selected)items.put(item);
            JSONObject draft=new JSONObject().put("title",title.getText().toString()).put("client",client.getText().toString())
                .put("amount",amount.getText().toString()).put("description",description.getText().toString()).put("items",items)
                .put("currency",currency[0]).put("request_body",submittedBody[0]).put("request_key",requestKey[0]);
            getPreferences(MODE_PRIVATE).edit().putString("draft",draft.toString()).apply();
        }catch(Exception ignored){}};
        String saved=getPreferences(MODE_PRIVATE).getString("draft",null);
        if(saved!=null)try{JSONObject draft=new JSONObject(saved);title.setText(draft.optString("title"));client.setText(draft.optString("client"));amount.setText(draft.optString("amount"));description.setText(draft.optString("description"));savedCurrency[0]=draft.has("currency");currency[0]=draft.optString("currency",catalogCurrency);submittedBody[0]=draft.optString("request_body");requestKey[0]=draft.optString("request_key");JSONArray items=draft.optJSONArray("items");if(items!=null)for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);if(item!=null)selected.add(item);}}catch(Exception ignored){}
        updateFieldLabel(amount,"Стоимость, "+currencySymbol(currency[0]));
        TextWatcher autosave=new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){}public void afterTextChanged(Editable value){saveDraft[0].run();}};
        title.addTextChangedListener(autosave);client.addTextChangedListener(autosave);amount.addTextChangedListener(autosave);description.addTextChangedListener(autosave);
        content.addView(selectedHost);
        addButton(content,"Добавить из расценок",false,v->{
            if(!currency[0].equals(catalogCurrency)){message("Валюта расценок изменилась. Сохраните этот черновик перед созданием новой сметы.");return;}
            if(pickerHost.getChildCount()>0)pickerHost.removeAllViews();else quoteCatalogPicker(pickerHost,currency[0],item->{
            if(selected.size()>=200){message("В одной смете может быть до 200 позиций");return;}
            for(JSONObject current:selected)if(current.optString("id").equals(item.optString("id"))){message("Эта позиция уже добавлена");return;}
            try{selected.add(new JSONObject(item.toString()).put("quantity","1"));renderSelected[0].run();pickerHost.removeAllViews();}catch(Exception error){message("Не удалось добавить позицию");}
        });});
        content.addView(pickerHost);
        renderSelected[0]=()->{
            selectedHost.removeAllViews();amount.setEnabled(selected.isEmpty());amount.setAlpha(selected.isEmpty()?1:.65f);
            if(selected.isEmpty())return;
            ui.section(selectedHost,"Состав сметы",null);
            for(JSONObject item:selected){
                LinearLayout row=ui.card(selectedHost),top=ui.row();
                top.addView(ui.label(item.optString("name"),15,INK,true),new LinearLayout.LayoutParams(0,-2,1));
                TextView remove=ui.label("Убрать",11,BLUE,false);remove.setPadding(dp(12),dp(8),0,dp(8));top.addView(remove);row.addView(top);
                ui.tap(remove,()->{selected.remove(item);if(selected.isEmpty())amount.setText("");renderSelected[0].run();saveDraft[0].run();});
                row.addView(ui.label(exactMoney(item.optLong("price"),currency[0])+" / "+item.optString("unit"),12,MUTED,false));
                EditText quantity=ui.field(row,"Количество · "+item.optString("unit"),8194);quantity.setText(item.optString("quantity","1"));
                quantity.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){}public void afterTextChanged(Editable value){try{item.put("quantity",value.toString());quoteCatalogTotal(selected,amount);saveDraft[0].run();}catch(Exception ignored){}}});
            }
            quoteCatalogTotal(selected,amount);saveDraft[0].run();
        };
        renderSelected[0].run();
        call("/workspace","GET",null,result->{JSONObject workspace=result.optJSONObject("workspace");if(workspace!=null){catalogCurrency=workspace.optString("currency","RUB");if(!savedCurrency[0]){currency[0]=catalogCurrency;updateFieldLabel(amount,"Стоимость, "+currencySymbol(currency[0]));renderSelected[0].run();saveDraft[0].run();}}});
        ui.space(content,14);button("Создать смету",true,v->{
            if(title.length()==0){title.setError("Добавьте название");return;}if(client.length()==0){client.setError("Укажите клиента");return;}
            try{
                JSONObject body=new JSONObject().put("title",title.getText().toString()).put("client",client.getText().toString())
                    .put("description",description.getText().toString()).put("currency",currency[0]);
                if(selected.isEmpty()){
                    long value=cents(amount);if(value<=0)throw new IllegalArgumentException();body.put("amount",value);
                }else{
                    JSONArray items=new JSONArray(),catalogIds=new JSONArray();
                    for(JSONObject item:selected){
                        java.math.BigDecimal quantity=new java.math.BigDecimal(item.optString("quantity","1").replace(',','.'));
                        if(quantity.compareTo(new java.math.BigDecimal("0.0001"))<0||quantity.compareTo(new java.math.BigDecimal("1000000"))>0||quantity.scale()>4)throw new IllegalArgumentException();
                        catalogIds.put(item.optString("id"));items.put(new JSONObject().put("name",item.optString("name")).put("description",item.optString("description"))
                            .put("category",item.optString("category")).put("unit",item.optString("unit"))
                            .put("quantity",quantity.toPlainString()).put("unit_price",item.optLong("price"))
                            .put("cost_price",item.optLong("cost_price")));
                    }
                    body.put("items",items).put("catalog_ids",catalogIds);
                }
                String currentBody=body.toString();if(!currentBody.equals(submittedBody[0])||requestKey[0].isEmpty()){submittedBody[0]=currentBody;requestKey[0]=java.util.UUID.randomUUID().toString();}
                body.put("_request_key",requestKey[0]);saveDraft[0].run();
                call("/quotes","POST",body,result->{
                    Analytics.event("estimate_created",Analytics.params("source",selected.isEmpty()?"manual":"catalog"),true);
                    getPreferences(MODE_PRIVATE).edit().remove("draft").apply();home();message("Смета создана");
                });
            }catch(Exception error){if(selected.isEmpty())amount.setError("Укажите сумму больше нуля");else message("Проверьте количество и цену позиций");}
        });
        ui.space(content,12);content.addView(ui.label("Черновик сохраняется на устройстве автоматически.",11,MUTED,false));
    }
    private void quoteCatalogTotal(java.util.List<JSONObject> selected,EditText amount){
        try{long total=0;for(JSONObject item:selected){
            java.math.BigDecimal quantity=new java.math.BigDecimal(item.optString("quantity","1").replace(',','.'));
            long subtotal=quantity.multiply(java.math.BigDecimal.valueOf(item.optLong("price")))
                .setScale(0,java.math.RoundingMode.HALF_UP).longValueExact();total=Math.addExact(total,subtotal);
        }amount.setText(java.math.BigDecimal.valueOf(total,2).toPlainString());}
        catch(Exception error){amount.setText("");amount.setHint("Проверьте количество");}
    }
    private void quoteCatalogPicker(LinearLayout host,String currency,java.util.function.Consumer<JSONObject> choose){
        host.removeAllViews();ui.section(host,"Ваши расценки",null);
        EditText search=ui.field(host,"Найти работу или материал",android.text.InputType.TYPE_CLASS_TEXT);
        search.setSingleLine(true);search.setMinHeight(dp(56));LinearLayout results=ui.column();host.addView(results);
        final int[] sequence={0};final Runnable[] pending={null};
        java.util.function.Consumer<String> lookup=query->{
            int request=++sequence[0];results.removeAllViews();loading(results);
            call("/catalog?q="+android.net.Uri.encode(query.trim()),"GET",null,result->{
                if(request!=sequence[0]||host.getChildCount()==0)return;
                results.removeAllViews();JSONArray items=result.optJSONArray("items");
                if(items==null||items.length()==0){ui.empty(results,"document","Ничего не найдено","Добавьте расценку в разделе «Ещё».");return;}
                for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);if(item==null)continue;
                    LinearLayout row=ui.card(results);row.addView(ui.label(item.optString("name"),14,INK,true));
                    ui.space(row,5);row.addView(ui.label(exactMoney(item.optLong("price"),currency)+" / "+item.optString("unit"),12,MUTED,false));
                    ui.tap(row,()->choose.accept(item));
                }
            });
        };
        search.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){if(pending[0]!=null)search.removeCallbacks(pending[0]);pending[0]=()->lookup.accept(s.toString());search.postDelayed(pending[0],250);}public void afterTextChanged(Editable value){}});
        lookup.accept("");
    }
    private long cents(EditText field){return new java.math.BigDecimal(field.getText().toString().replace(" ","").replace(',','.')).movePointRight(2).setScale(0,java.math.RoundingMode.HALF_UP).longValueExact();}
    private void approvals(){
        publicView=false;page("Согласования","approvals",false);content.addView(ui.label("Решения клиентов",26,INK,true));text("Предложения, которые уже видит клиент, и согласованные условия.");
        LinearLayout host=ui.column();content.addView(host);loading(host);
        call("/quotes","GET",null,result->{host.removeAllViews();JSONArray list=result.optJSONArray("quotes");int count=0;if(list!=null)for(int i=0;i<list.length();i++){JSONObject q=list.optJSONObject(i);if(q==null)continue;String state=q.optString("approval_state",q.optString("status"));if(!state.equals("sent")&&!state.equals("viewed")&&!state.equals("changes_requested")&&!state.equals("approved"))continue;count++;LinearLayout row=ui.card(host);row.addView(ui.label(q.optString("title"),16,INK,true));ui.space(row,6);row.addView(ui.label(q.optString("client"),12,MUTED,false));ui.space(row,8);row.addView(ui.badge(status(state),statusColor(state)));ui.tap(row,()->quote(q));}if(count==0)ui.empty(host,"check","Согласований пока нет","Отправьте клиенту смету — её статус появится здесь.");});
    }
    private void payments(){
        publicView=false;page("Платежи","payments",false);content.addView(ui.label("Деньги под контролем.",26,INK,true));text("Записанные поступления и суммы по заказам. Списание здесь не выполняется.");
        LinearLayout balances=ui.column();content.addView(balances);loading(balances);
        call("/overview","GET",null,result->{balances.removeAllViews();JSONArray currencies=result.optJSONArray("currencies");if(currencies==null||currencies.length()==0){ui.empty(balances,"wallet","Поступлений пока нет","Создайте заказ из согласованной сметы.");return;}for(int i=0;i<currencies.length();i++){JSONObject item=currencies.optJSONObject(i);if(item==null)continue;String currency=item.optString("currency","RUB");ui.section(balances,currency,null);balances.addView(ui.label("Получено · "+exactMoney(item.optLong("paid"),currency),18,INK,true));ui.space(balances,5);balances.addView(ui.label("Осталось получить · "+exactMoney(item.optLong("unpaid"),currency),14,MUTED,false));}});
        ui.section(content,"Недавние поступления",null);LinearLayout entries=ui.column();content.addView(entries);
        call("/receipts","GET",null,result->{JSONArray list=result.optJSONArray("items");if(list==null||list.length()==0){entries.addView(ui.label("Записей пока нет.",13,MUTED,false));return;}for(int i=0;i<Math.min(20,list.length());i++){JSONObject item=list.optJSONObject(i);if(item==null)continue;LinearLayout row=ui.card(entries);row.addView(ui.label(exactMoney(item.optLong("amount_kopecks"),item.optString("currency","RUB")),17,INK,true));ui.space(row,5);row.addView(ui.label(item.optString("payment_date"),12,MUTED,false));}});
    }
    // CONSTRUCTION START
    private void constructionList(){
        publicView=false;page("Объекты","construction",true);
        content.addView(ui.label("Объекты и замеры",26,INK,true));
        text("Размеры помещений → объёмы → смета.");
        button("Новый объект",true,v->constructionNew());
        ui.section(content,"В работе",null);
        LinearLayout host=ui.column();content.addView(host);loading(host);
        call("/construction/objects","GET",null,result->{
            clearLoading(host);JSONArray items=result.optJSONArray("items");
            if(items==null||items.length()==0){ui.empty(host,"projects","Пока нет объектов","Создайте объект и запишите размеры первого помещения.");return;}
            for(int i=0;i<items.length();i++){
                JSONObject item=items.optJSONObject(i);if(item==null)continue;
                LinearLayout row=ui.row();row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(0,dp(18),0,dp(18));
                LinearLayout labels=ui.column();labels.addView(ui.label(item.optString("name"),15,INK,true));ui.space(labels,5);
                labels.addView(ui.label(item.optString("quote_id").isEmpty()?"Замеры и ведомость":"Сметра создана",11,MUTED,false));
                row.addView(labels,new LinearLayout.LayoutParams(0,-2,1));row.addView(ui.new Icon("chevron",BLUE),new LinearLayout.LayoutParams(dp(18),dp(18)));
                host.addView(row);ui.tap(row,()->constructionDetail(item.optString("id")));
                View line=new View(this);line.setBackgroundColor(LINE);host.addView(line,new LinearLayout.LayoutParams(-1,dp(1)));
            }
        });
    }
    private void constructionNew(){
        page("Новый объект","construction-new",true);
        content.addView(ui.label("Сначала объект.",27,INK,true));text("Название поможет найти замеры и смету позже.");
        EditText name=field("Название объекта",android.text.InputType.TYPE_CLASS_TEXT);
        button("Создать объект",true,v->{if(name.length()==0){name.setError("Укажите название");return;}
            try{call("/construction/objects","POST",new JSONObject().put("name",name.getText().toString()),result->constructionDetail(result.optJSONObject("object").optString("id")));}
            catch(Exception error){message(error.getMessage());}
        });
    }
    private void constructionDetail(String id){
        constructionParentId=id;
        page("Объект","construction-detail",true);loading(content);
        call("/construction/objects/"+id,"GET",null,result->{
            clearLoading(content);JSONObject object=result.optJSONObject("object"),totals=result.optJSONObject("totals");
            if(object==null)return;
            content.addView(ui.label(object.optString("name"),27,INK,true));
            ui.space(content,12);
            LinearLayout summary=ui.row();summary.addView(ui.label("План",12,MUTED,false),new LinearLayout.LayoutParams(0,-2,1));
            summary.addView(ui.label(exactMoney(totals==null?0:totals.optLong("planned_kopecks"),"RUB"),17,INK,true));content.addView(summary);
            ui.section(content,"Помещения",null);
            JSONArray zones=result.optJSONArray("zones");
            if(zones!=null)for(int i=0;i<zones.length();i++){
                JSONObject zone=zones.optJSONObject(i);if(zone==null)continue;
                LinearLayout row=ui.row();row.setPadding(0,dp(9),0,dp(9));
                row.addView(ui.label(zone.optString("name"),14,INK,false),new LinearLayout.LayoutParams(0,-2,1));
                double area=zone.optDouble("length_m")*zone.optDouble("width_m");
                row.addView(ui.label(String.format(Locale.US,"%.2f м²",area),12,BLUE,true));content.addView(row);
                ui.tap(row,()->constructionZoneEdit(id,zone));
            }
            addButton(content,"Добавить помещение",false,v->constructionZone(id));
            ui.section(content,"Ручные замеры",null);
            JSONArray measurements=result.optJSONArray("measurements");
            if(measurements!=null)for(int i=0;i<measurements.length();i++){
                JSONObject measure=measurements.optJSONObject(i);if(measure==null)continue;
                LinearLayout row=ui.row();row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(0,dp(11),0,dp(11));
                row.addView(ui.label(measure.optString("symbol"),14,INK,true),new LinearLayout.LayoutParams(0,-2,1));
                row.addView(ui.label(measure.optString("value")+" "+measure.optString("unit"),12,BLUE,true));
                content.addView(row);ui.tap(row,()->constructionMeasurementEdit(id,measure));
            }
            addButton(content,"Записать замер",false,v->constructionMeasurementNew(id,zones));
            ui.section(content,"Ведомость",null);
            JSONArray quantities=result.optJSONArray("quantities");
            if(quantities!=null)for(int i=0;i<quantities.length();i++){
                JSONObject quantity=quantities.optJSONObject(i);if(quantity==null)continue;
                LinearLayout row=ui.row();row.setPadding(0,dp(11),0,dp(11));
                LinearLayout labels=ui.column();labels.addView(ui.label(quantity.optString("title"),14,INK,true));ui.space(labels,4);
                labels.addView(ui.label(quantity.optString("quantity")+" "+quantity.optString("unit")+" · факт "+quantity.optString("actual_quantity"),11,MUTED,false));
                row.addView(labels,new LinearLayout.LayoutParams(0,-2,1));row.addView(ui.label(exactMoney(quantity.optLong("planned_total_kopecks"),"RUB"),12,INK,false));
                content.addView(row);ui.tap(row,()->constructionFact(id,quantity));
            }
            addButton(content,"Добавить работу",false,v->constructionWork(id,zones));
            if(quantities!=null&&quantities.length()>0)addButton(content,"Материал по норме расхода",false,v->constructionMaterial(id,quantities));
            ui.section(content,"Материалы и закупки",null);
            JSONArray procurement=result.optJSONArray("procurement");
            if(procurement!=null)for(int i=0;i<procurement.length();i++){
                JSONObject item=procurement.optJSONObject(i);if(item==null)continue;
                LinearLayout row=ui.column();row.setPadding(0,dp(10),0,dp(10));
                row.addView(ui.label(item.optString("title"),14,INK,true));ui.space(row,4);
                row.addView(ui.label("Нужно "+item.optString("required_quantity")+" "+item.optString("unit")+" · получено "+item.optString("received_quantity"),11,MUTED,false));
                if(item.optDouble("shortage_quantity")>0){ui.space(row,3);row.addView(ui.label("Недостача "+item.optString("shortage_quantity")+" "+item.optString("unit"),11,0xffe8a79d,false));}
                content.addView(row);
            }
            JSONArray purchases=result.optJSONArray("purchases");
            if(purchases!=null)for(int i=0;i<purchases.length();i++){
                JSONObject purchase=purchases.optJSONObject(i);if(purchase==null)continue;
                LinearLayout row=ui.row();row.setPadding(0,dp(10),0,dp(10));row.addView(ui.label(purchase.optString("purchased_on")+" · "+purchase.optString("quantity")+" · "+("received".equals(purchase.optString("status"))?"Получено":"Заказано"),12,INK,false));
                content.addView(row);ui.tap(row,()->constructionPurchaseDetail(id,purchase));
            }
            if(procurement!=null&&procurement.length()>0)addButton(content,"Записать закупку",false,v->constructionPurchaseNew(id,quantities));
            ui.section(content,"Дефектная ведомость",null);
            JSONArray defects=result.optJSONArray("defects");
            if(defects!=null)for(int i=0;i<defects.length();i++){
                JSONObject defect=defects.optJSONObject(i);if(defect==null)continue;
                LinearLayout row=ui.row();row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(0,dp(12),0,dp(12));
                LinearLayout labels=ui.column();labels.addView(ui.label(defect.optString("description"),14,INK,true));ui.space(labels,5);
                String state="resolved".equals(defect.optString("status"))?"Устранён":"in_progress".equals(defect.optString("status"))?"В работе":"Открыт";
                labels.addView(ui.label(state+(defect.optString("photo_file_id").isEmpty()?"":" · фото"),11,MUTED,false));
                row.addView(labels,new LinearLayout.LayoutParams(0,-2,1));row.addView(ui.new Icon("chevron",BLUE),new LinearLayout.LayoutParams(dp(18),dp(18)));
                content.addView(row);ui.tap(row,()->constructionDefectDetail(id,defect));
            }
            addButton(content,"Зафиксировать дефект",false,v->constructionDefectNew(id,zones));
            ui.section(content,"Журнал работ",null);
            JSONArray logs=result.optJSONArray("daily_logs");
            if(logs!=null)for(int i=0;i<logs.length();i++){
                JSONObject log=logs.optJSONObject(i);if(log==null)continue;
                LinearLayout row=ui.row();row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(0,dp(12),0,dp(12));
                LinearLayout labels=ui.column();labels.addView(ui.label(log.optString("work_description"),14,INK,true));ui.space(labels,5);
                String meta=log.optString("work_date")+(log.optInt("worker_count")>0?" · "+log.optInt("worker_count")+" чел.":"");
                labels.addView(ui.label(meta,11,MUTED,false));row.addView(labels,new LinearLayout.LayoutParams(0,-2,1));
                row.addView(ui.new Icon("chevron",BLUE),new LinearLayout.LayoutParams(dp(18),dp(18)));
                content.addView(row);ui.tap(row,()->constructionLogDetail(id,log));
            }
            addButton(content,"Записать выполненную работу",false,v->constructionLogNew(id,zones,quantities));
            ui.section(content,"Дополнительные работы",null);
            JSONArray changes=result.optJSONArray("changes");
            if(changes!=null)for(int i=0;i<changes.length();i++){
                JSONObject change=changes.optJSONObject(i);if(change==null)continue;
                LinearLayout row=ui.row();row.setPadding(0,dp(11),0,dp(11));
                LinearLayout labels=ui.column();labels.addView(ui.label(change.optString("title"),14,INK,true));ui.space(labels,4);
                String changeState="approved".equals(change.optString("status"))?"Согласовано":"sent".equals(change.optString("status"))?"На согласовании":"changes_requested".equals(change.optString("status"))?"Нужны изменения":"declined".equals(change.optString("status"))?"Отклонено":"Черновик";
                labels.addView(ui.label("Версия "+change.optInt("version")+" · "+changeState+" · "+exactMoney(change.optLong("amount_kopecks"),"RUB"),11,MUTED,false));
                row.addView(labels,new LinearLayout.LayoutParams(0,-2,1));content.addView(row);ui.tap(row,()->constructionChangeDetail(id,change));
            }
            addButton(content,"Добавить допработы",false,v->constructionChangeNew(id));
            addButton(content,"Прикрепить фото или файл",false,v->{uploadConstruction=id;uploadProject=null;uploadDefect=null;uploadLog=null;uploadPurchase=null;Intent picker=new Intent(Intent.ACTION_OPEN_DOCUMENT);picker.setType("*/*");picker.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/png","image/jpeg","application/pdf","text/plain"});picker.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(picker,301);});
            ui.space(content,16);
            if(object.optString("quote_id").isEmpty()&&quantities!=null&&quantities.length()>0){
                button("Создать смету",true,v->ui.sheet("Создать смету?","Ведомость станет черновиком сметы. Проверьте объёмы и цены.","Создать",false,()->call("/construction/objects/"+id+"/quote","POST",new JSONObject(),answer->openQuote(answer.optJSONObject("quote")))));
            }
            if(!object.optString("quote_id").isEmpty())button("Открыть смету",true,v->call("/quotes/"+object.optString("quote_id"),"GET",null,answer->openQuote(answer.optJSONObject("quote"))));
            boolean hasFact=false;if(quantities!=null)for(int i=0;i<quantities.length();i++){JSONObject row=quantities.optJSONObject(i);if(row!=null&&row.optDouble("actual_quantity")>0){hasFact=true;break;}}
            if(hasFact)addButton(content,"Сформировать акт по факту",false,v->ui.sheet("Сформировать черновик акта?","В него попадут только записанные фактические объёмы. Поздние правки не изменят документ.","Сформировать",false,()->call("/construction/objects/"+id+"/act","POST",new JSONObject(),answer->{JSONObject document=answer.optJSONObject("document");if(document==null)return;pendingPdfDocument=document.optString("id");Intent save=new Intent(Intent.ACTION_CREATE_DOCUMENT);save.setType("application/pdf");save.addCategory(Intent.CATEGORY_OPENABLE);save.putExtra(Intent.EXTRA_TITLE,"smetra-akt-"+document.optInt("number")+".pdf");startActivityForResult(save,304);})));
            addButton(content,"Скачать отчёт по объекту",false,v->{pendingPdfDocument="report:"+id;Intent save=new Intent(Intent.ACTION_CREATE_DOCUMENT);save.setType("application/pdf");save.addCategory(Intent.CATEGORY_OPENABLE);save.putExtra(Intent.EXTRA_TITLE,"smetra-report.pdf");startActivityForResult(save,304);});
        });
    }
    private void saveActPdf(int resultCode,Intent data){
        final String documentId=pendingPdfDocument;pendingPdfDocument=null;
        if(resultCode!=RESULT_OK||data==null||data.getData()==null||documentId==null)return;
        final android.net.Uri uri=data.getData();message("Сохраняем акт…");
        worker.execute(()->{HttpURLConnection connection=null;try{
            String path=documentId.startsWith("report:")?"/api/construction/objects/"+documentId.substring(7)+"/report.pdf":"/api/documents/"+documentId+"/pdf";
            connection=(HttpURLConnection)new URL(BuildConfig.API_BASE_URL+path).openConnection();
            connection.setConnectTimeout(10000);connection.setReadTimeout(30000);
            connection.setRequestProperty("Authorization","Bearer "+token);
            if(connection.getResponseCode()!=200||connection.getContentType()==null||!connection.getContentType().startsWith("application/pdf"))throw new IOException("PDF unavailable");
            try(InputStream input=connection.getInputStream();java.io.OutputStream output=getContentResolver().openOutputStream(uri)){
                if(output==null)throw new IOException("File unavailable");
                byte[] buffer=new byte[8192];int count,total=0;
                while((count=input.read(buffer))!=-1){total+=count;if(total>15_000_000)throw new IOException("PDF too large");output.write(buffer,0,count);}
            }
            runOnUiThread(()->{if(!isFinishing())message("Черновик акта сохранён");});
        }catch(Exception error){runOnUiThread(()->{if(!isFinishing())message("Не удалось сохранить акт");});}
        finally{if(connection!=null)connection.disconnect();}});
    }
    private void constructionZone(String id){
        page("Помещение","construction-zone",true);
        content.addView(ui.label("Размеры помещения",25,INK,true));text("Укажите реальные размеры в метрах. Их можно использовать в формуле объёма.");
        EditText name=field("Название",android.text.InputType.TYPE_CLASS_TEXT);
        EditText length=field("Длина, м",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        EditText width=field("Ширина, м",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        EditText height=field("Высота, м",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        button("Сохранить помещение",true,v->{if(name.length()==0||length.length()==0||width.length()==0){message("Заполните название, длину и ширину");return;}
            try{JSONObject body=new JSONObject().put("name",name.getText().toString()).put("length",measurementText(length)).put("width",measurementText(width)).put("height",height.length()==0?"0":measurementText(height));
                call("/construction/objects/"+id+"/zones","POST",body,result->constructionDetail(id));}
            catch(Exception error){message(error.getMessage());}
        });
    }
    private void constructionZoneEdit(String id,JSONObject zone){
        page("Помещение","construction-zone-edit",true);
        content.addView(ui.label(zone.optString("name"),25,INK,true));
        text("Изменение размеров пересчитает связанные объёмы. Ранее отправленная смета сохранится, а для новых размеров потребуется свежий черновик.");
        EditText name=field("Название",android.text.InputType.TYPE_CLASS_TEXT);name.setText(zone.optString("name"));
        EditText length=field("Длина, м",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);length.setText(zone.optString("length_m"));
        EditText width=field("Ширина, м",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);width.setText(zone.optString("width_m"));
        EditText height=field("Высота, м",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);height.setText(zone.optString("height_m"));
        button("Сохранить размеры",true,v->{if(name.length()==0||length.length()==0||width.length()==0){message("Заполните название, длину и ширину");return;}
            try{JSONObject body=new JSONObject().put("name",name.getText().toString()).put("length",measurementText(length)).put("width",measurementText(width)).put("height",measurementText(height));
                call("/construction/objects/"+id+"/zones/"+zone.optString("id"),"PATCH",body,result->constructionDetail(id));}
            catch(Exception error){message(error.getMessage());}
        });
    }
    private void constructionMeasurementNew(String id,JSONArray zones){
        page("Новый замер","construction-measure-new",true);
        content.addView(ui.label("Точный замер",25,INK,true));text("Укажите переменную латинскими буквами, затем используйте её в формуле объёма.");
        java.util.ArrayList<JSONObject> rooms=new java.util.ArrayList<>();rooms.add(null);
        if(zones!=null)for(int i=0;i<zones.length();i++)if(zones.optJSONObject(i)!=null)rooms.add(zones.optJSONObject(i));
        String[] names=new String[rooms.size()];names[0]="Весь объект";
        for(int i=1;i<rooms.size();i++)names[i]=rooms.get(i).optString("name");
        Spinner room=new Spinner(this);room.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,names));content.addView(room);
        EditText symbol=field("Переменная, например window_area",android.text.InputType.TYPE_CLASS_TEXT);
        EditText value=field("Размер",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        String[] units={"м","см","м²","шт."};Spinner unit=new Spinner(this);unit.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,units));content.addView(unit);
        button("Записать замер",true,v->{String code=symbol.getText().toString().trim();if(!code.matches("[a-z][a-z0-9_]{1,31}")){symbol.setError("Латинские буквы и цифры");return;}if(value.length()==0){value.setError("Укажите размер");return;}
            try{JSONObject body=new JSONObject().put("symbol",code).put("value",measurementText(value)).put("unit",units[unit.getSelectedItemPosition()]).put("source","manual");
                if(room.getSelectedItemPosition()>0)body.put("zone_id",rooms.get(room.getSelectedItemPosition()).optString("id"));
                call("/construction/objects/"+id+"/measurements","POST",body,result->constructionDetail(id));}
            catch(Exception error){message(error.getMessage());}
        });
    }
    private void constructionMeasurementEdit(String id,JSONObject measure){
        page("Замер","construction-measure-edit",true);
        content.addView(ui.label(measure.optString("symbol"),25,INK,true));text("Изменение замера пересчитает связанные позиции ведомости.");
        EditText value=field("Размер",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);value.setText(measure.optString("value"));
        String[] units={"м","см","м²","шт."};Spinner unit=new Spinner(this);unit.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,units));
        for(int i=0;i<units.length;i++)if(units[i].equals(measure.optString("unit")))unit.setSelection(i);
        content.addView(unit);
        button("Сохранить замер",true,v->{if(value.length()==0){value.setError("Укажите размер");return;}
            try{JSONObject body=new JSONObject().put("value",measurementText(value)).put("unit",units[unit.getSelectedItemPosition()]);
                call("/construction/objects/"+id+"/measurements/"+measure.optString("id"),"PATCH",body,result->constructionDetail(id));}
            catch(Exception error){message(error.getMessage());}
        });
    }
    private String measurementText(EditText input){return input.getText().toString().trim().replace(',','.');}
    private void constructionWork(String id,JSONArray zones){
        if(zones==null||zones.length()==0){message("Сначала добавьте помещение");return;}
        String[] labels=new String[zones.length()];for(int i=0;i<zones.length();i++)labels[i]=zones.optJSONObject(i).optString("name");
        page("Работа","construction-work",true);
        content.addView(ui.label("Объём из замеров",25,INK,true));text("Выберите помещение и работу. Формула area — площадь пола.");
        Spinner room=new Spinner(this);ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels);room.setAdapter(adapter);content.addView(room);
        EditText title=field("Работа",android.text.InputType.TYPE_CLASS_TEXT);
        EditText formula=field("Формула: area, perimeter * height, volume",android.text.InputType.TYPE_CLASS_TEXT);formula.setText("area");
        EditText price=field("Цена за единицу, ₽",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        button("Добавить в ведомость",true,v->{if(title.length()==0){title.setError("Укажите работу");return;}
            try{String zoneId=zones.optJSONObject(room.getSelectedItemPosition()).optString("id");
                JSONObject body=new JSONObject().put("zone_id",zoneId).put("kind","work").put("title",title.getText().toString()).put("formula",formula.getText().toString()).put("unit","м²").put("unit_price",price.length()==0?0:cents(price));
                call("/construction/objects/"+id+"/quantities","POST",body,result->constructionDetail(id));}
            catch(Exception error){message("Проверьте формулу и цену");}
        });
    }
    private void constructionFact(String id,JSONObject quantity){
        page("Факт","construction-fact",true);
        content.addView(ui.label(quantity.optString("title"),25,INK,true));
        text("План: "+quantity.optString("quantity")+" "+quantity.optString("unit")+". Фактический объём добавится к уже записанному.");
        EditText amount=field("Выполнено, "+quantity.optString("unit"),android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        button("Записать факт",true,v->{if(amount.length()==0){amount.setError("Укажите объём");return;}
            try{JSONObject body=new JSONObject().put("quantity_id",quantity.optString("id")).put("quantity",amount.getText().toString());
                call("/construction/objects/"+id+"/facts","POST",body,result->constructionDetail(id));}
            catch(Exception error){message(error.getMessage());}
        });
    }
    private void constructionMaterial(String id,JSONArray quantities){
        java.util.ArrayList<JSONObject> works=new java.util.ArrayList<>();
        for(int i=0;i<quantities.length();i++){JSONObject item=quantities.optJSONObject(i);if(item!=null&&"work".equals(item.optString("kind")))works.add(item);}
        if(works.isEmpty()){message("Сначала добавьте работу");return;}
        page("Материал","construction-material",true);
        content.addView(ui.label("Расход от объёма работы",25,INK,true));
        text("Укажите норму расхода на одну единицу работы и запас.");
        String[] names=new String[works.size()];for(int i=0;i<works.size();i++)names[i]=works.get(i).optString("title");
        Spinner parent=new Spinner(this);parent.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,names));content.addView(parent);
        EditText title=field("Материал",android.text.InputType.TYPE_CLASS_TEXT);
        EditText rate=field("Расход на единицу работы",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        EditText waste=field("Запас, %",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        EditText unit=field("Единица материала, например л",android.text.InputType.TYPE_CLASS_TEXT);unit.setText("л");
        EditText price=field("Цена за единицу, ₽",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        button("Добавить материал",true,v->{if(title.length()==0||rate.length()==0){message("Укажите материал и норму расхода");return;}
            try{JSONObject body=new JSONObject().put("parent_work_id",works.get(parent.getSelectedItemPosition()).optString("id"))
                    .put("kind","material").put("title",title.getText().toString()).put("unit",unit.getText().toString())
                    .put("consumption_rate",rate.getText().toString()).put("waste_percent",waste.length()==0?"0":waste.getText().toString())
                    .put("unit_price",price.length()==0?0:cents(price));
                call("/construction/objects/"+id+"/quantities","POST",body,result->constructionDetail(id));}
            catch(Exception error){message("Проверьте норму, единицу и цену");}
        });
    }
    private void constructionChangeNew(String id){constructionChangeForm(id,null);}
    private void constructionChangeForm(String id,JSONObject previous){
        page("Допработы",previous==null?"construction-change-new":"construction-change-edit",true);
        content.addView(ui.label(previous==null?"Новые работы":"Черновик допработ",25,INK,true));
        text("Клиент согласует их отдельно от основной сметы.");
        EditText title=field("Название",android.text.InputType.TYPE_CLASS_TEXT);
        EditText description=field("Описание для клиента",android.text.InputType.TYPE_CLASS_TEXT);
        EditText work=field("Работа или материал",android.text.InputType.TYPE_CLASS_TEXT);
        EditText quantity=field("Количество",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        String[] units={"шт.","м²","м³","м","м.п.","компл.","л","кг","ч"};Spinner unit=new Spinner(this);unit.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,units));content.addView(unit);
        EditText price=field("Цена за единицу, ₽",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        EditText days=field("Добавится к сроку, дней",android.text.InputType.TYPE_CLASS_NUMBER);
        days.setText("0");
        if(previous!=null){title.setText(previous.optString("title"));description.setText(previous.optString("description"));days.setText(previous.optString("deadline_days"));
            JSONObject item=previous.optJSONArray("items").optJSONObject(0);work.setText(item.optString("name"));quantity.setText(item.optString("quantity"));price.setText(String.format(Locale.ROOT,"%.2f",item.optLong("unit_price")/100.0));for(int i=0;i<units.length;i++)if(units[i].equals(item.optString("unit")))unit.setSelection(i);}
        button("Сохранить черновик",true,v->{if(title.length()==0||work.length()==0||quantity.length()==0||price.length()==0){message("Заполните название, работу, количество и цену");return;}
            try{java.math.BigDecimal rubles=new java.math.BigDecimal(price.getText().toString().replace(',','.'));
                long kopecks=rubles.movePointRight(2).setScale(0,java.math.RoundingMode.HALF_UP).longValueExact();
                JSONObject item=new JSONObject().put("name",work.getText().toString().trim()).put("quantity",quantity.getText().toString().trim().replace(',','.')).put("unit",units[unit.getSelectedItemPosition()]).put("unit_price",kopecks);
                JSONObject body=new JSONObject().put("title",title.getText().toString().trim()).put("description",description.getText().toString().trim())
                        .put("deadline_days",days.getText().toString().trim()).put("items",new JSONArray().put(item));
                call("/construction/objects/"+id+"/changes"+(previous==null?"":"/"+previous.optString("id")),previous==null?"POST":"PATCH",body,result->constructionDetail(id));
            }catch(Exception error){message("Проверьте количество и цену");}
        });
    }
    private void constructionChangeDetail(String id,JSONObject change){
        page("Допработы","construction-change-detail",true);
        content.addView(ui.label(change.optString("title"),25,INK,true));
        text("Версия "+change.optInt("version")+" · "+exactMoney(change.optLong("amount_kopecks"),"RUB"));
        if(!change.optString("description").isEmpty())text(change.optString("description"));
        JSONArray items=change.optJSONArray("items");if(items!=null)for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);if(item!=null)text(item.optString("name")+" · "+item.optString("quantity")+" "+item.optString("unit")+" · "+exactMoney(item.optLong("subtotal"),"RUB"));}
        if(change.optInt("deadline_days")>0)text("К сроку: +"+change.optInt("deadline_days")+" дн.");
        if(!change.optString("response_comment").isEmpty())text("Ответ клиента: "+change.optString("response_comment"));
        String state=change.optString("status");
        if("draft".equals(state)){
            if(items!=null&&items.length()==1)addButton(content,"Изменить черновик",false,v->constructionChangeForm(id,change));
            button("Отправить на согласование",true,v->ui.sheet("Зафиксировать версию?","После отправки состав и сумма допработ не меняются.","Отправить",false,()->call("/construction/objects/"+id+"/changes/"+change.optString("id")+"/send","POST",new JSONObject(),result->constructionDetail(id))));
            addButton(content,"Удалить черновик",false,v->ui.sheet("Удалить черновик?","Эту версию ещё не видит клиент.","Удалить",false,()->call("/construction/objects/"+id+"/changes/"+change.optString("id"),"DELETE",null,result->constructionDetail(id))));
        }
        if("sent".equals(state))addButton(content,"Отозвать ссылку",false,v->ui.sheet("Отозвать ссылку?","Клиент больше не сможет согласовать эту версию.","Отозвать",false,()->call("/construction/objects/"+id+"/changes/"+change.optString("id")+"/revoke","POST",new JSONObject(),result->constructionDetail(id))));
        if("changes_requested".equals(state)||"declined".equals(state))addButton(content,"Создать новую версию",false,v->call("/construction/objects/"+id+"/changes/"+change.optString("id")+"/revise","POST",new JSONObject(),result->constructionDetail(id)));
        if(!change.optString("public_token").isEmpty())addButton(content,"Поделиться ссылкой с клиентом",false,v->{String link=BuildConfig.API_BASE_URL+"/change.html?token="+android.net.Uri.encode(change.optString("public_token"));Intent share=new Intent(Intent.ACTION_SEND);share.setType("text/plain");share.putExtra(Intent.EXTRA_TEXT,link);startActivity(Intent.createChooser(share,"Ссылка на согласование"));});
    }
    private void constructionPurchaseNew(String id,JSONArray quantities){constructionPurchaseForm(id,quantities,null);}
    private void constructionPurchaseForm(String id,JSONArray quantities,JSONObject previous){
        page("Закупка",previous==null?"construction-purchase-new":"construction-purchase-edit",true);loading(content);
        call("/construction/suppliers","GET",null,result->{
            clearLoading(content);JSONArray suppliers=result.optJSONArray("items");
            content.addView(ui.label(previous==null?"Новая закупка":"Изменить закупку",25,INK,true));
            ui.section(content,"Материал",null);
            java.util.ArrayList<JSONObject> materials=new java.util.ArrayList<>();java.util.ArrayList<String> materialNames=new java.util.ArrayList<>();
            if(quantities!=null)for(int i=0;i<quantities.length();i++){JSONObject item=quantities.optJSONObject(i);if(item!=null&&"material".equals(item.optString("kind"))){materials.add(item);materialNames.add(item.optString("title")+" · "+item.optString("unit"));}}
            Spinner material=new Spinner(this);material.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,materialNames));content.addView(material);
            if(previous!=null)for(int i=0;i<materials.size();i++)if(materials.get(i).optString("id").equals(previous.optString("material_id")))material.setSelection(i);
            ui.section(content,"Поставщик",null);
            java.util.ArrayList<JSONObject> supplyRows=new java.util.ArrayList<>();java.util.ArrayList<String> supplyNames=new java.util.ArrayList<>();supplyNames.add("Не указан");
            if(suppliers!=null)for(int i=0;i<suppliers.length();i++){JSONObject item=suppliers.optJSONObject(i);if(item!=null){supplyRows.add(item);supplyNames.add(item.optString("name"));}}
            Spinner supplier=new Spinner(this);supplier.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,supplyNames));content.addView(supplier);
            if(previous!=null)for(int i=0;i<supplyRows.size();i++)if(supplyRows.get(i).optString("id").equals(previous.optString("supplier_id")))supplier.setSelection(i+1);
            addButton(content,"Новый поставщик",false,v->constructionSupplierNew(id,quantities));
            EditText date=field("Дата · ГГГГ-ММ-ДД",android.text.InputType.TYPE_CLASS_DATETIME|android.text.InputType.TYPE_DATETIME_VARIATION_DATE);
            date.setText(previous==null?new java.text.SimpleDateFormat("yyyy-MM-dd",Locale.ROOT).format(new java.util.Date()):previous.optString("purchased_on"));
            EditText amount=field("Количество",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
            if(previous!=null)amount.setText(previous.optString("quantity"));
            EditText price=field("Цена за единицу, ₽",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
            price.setText(previous==null?"0":String.format(Locale.ROOT,"%.2f",previous.optLong("unit_price_kopecks")/100.0));
            ui.section(content,"Статус",null);String[] states={"Заказано","Получено"};
            Spinner state=new Spinner(this);state.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,states));
            if(previous!=null&&"received".equals(previous.optString("status")))state.setSelection(1);content.addView(state);
            EditText notes=field("Примечание",android.text.InputType.TYPE_CLASS_TEXT);if(previous!=null)notes.setText(previous.optString("notes"));
            button("Сохранить закупку",true,v->{
                if(materials.isEmpty()||amount.length()==0){message("Укажите материал и количество");return;}
                try{java.math.BigDecimal rubles=new java.math.BigDecimal(price.getText().toString().replace(',','.'));
                    long kopecks=rubles.movePointRight(2).setScale(0,java.math.RoundingMode.HALF_UP).longValueExact();
                    JSONObject body=new JSONObject().put("material_id",materials.get(material.getSelectedItemPosition()).optString("id"))
                            .put("supplier_id",supplier.getSelectedItemPosition()==0?"":supplyRows.get(supplier.getSelectedItemPosition()-1).optString("id"))
                            .put("purchased_on",date.getText().toString().trim()).put("quantity",amount.getText().toString().trim().replace(',','.'))
                            .put("unit_price_kopecks",kopecks).put("status",state.getSelectedItemPosition()==0?"ordered":"received")
                            .put("notes",notes.getText().toString().trim());
                    call("/construction/objects/"+id+"/purchases"+(previous==null?"":"/"+previous.optString("id")),previous==null?"POST":"PATCH",body,answer->constructionDetail(id));
                }catch(Exception error){message("Проверьте количество и цену");}
            });
        });
    }
    private void constructionSupplierNew(String id,JSONArray quantities){
        page("Поставщик","construction-supplier-new",true);content.addView(ui.label("Новый поставщик",25,INK,true));
        EditText name=field("Название",android.text.InputType.TYPE_CLASS_TEXT);EditText phone=field("Телефон",android.text.InputType.TYPE_CLASS_PHONE);
        EditText email=field("Email",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        button("Сохранить поставщика",true,v->{if(name.getText().toString().trim().isEmpty()){name.setError("Укажите название");return;}
            try{call("/construction/suppliers","POST",new JSONObject().put("name",name.getText().toString().trim()).put("phone",phone.getText().toString().trim()).put("email",email.getText().toString().trim()),result->constructionPurchaseNew(id,quantities));}
            catch(Exception error){message(error.getMessage());}
        });
    }
    private void constructionPurchaseDetail(String id,JSONObject purchase){
        page("Закупка","construction-purchase-detail",true);content.addView(ui.label(purchase.optString("purchased_on"),25,INK,true));
        text(purchase.optString("quantity")+" · "+exactMoney(purchase.optLong("unit_price_kopecks"),"RUB")+" за единицу");
        text("received".equals(purchase.optString("status"))?"Получено":"Заказано");
        if(!purchase.optString("notes").isEmpty())text(purchase.optString("notes"));
        addButton(content,"Прикрепить чек или накладную",false,v->{uploadConstruction=id;uploadProject=null;uploadDefect=null;uploadLog=null;uploadPurchase=purchase.optString("id");Intent picker=new Intent(Intent.ACTION_OPEN_DOCUMENT);picker.setType("*/*");picker.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/png","image/jpeg","application/pdf"});picker.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(picker,301);});
        if(!purchase.optString("receipt_file_id").isEmpty()){
            LinearLayout ocr=new LinearLayout(this);ocr.setOrientation(LinearLayout.VERTICAL);content.addView(ocr);
            loadReceiptDraft(id,purchase,ocr,pageVersion);
        }
        addButton(content,"Изменить",false,v->call("/construction/objects/"+id,"GET",null,result->constructionPurchaseForm(id,result.optJSONArray("quantities"),purchase)));
        addButton(content,"Удалить",false,v->ui.sheet("Удалить закупку?","Список закупки пересчитается.","Удалить",false,()->call("/construction/objects/"+id+"/purchases/"+purchase.optString("id"),"DELETE",null,result->constructionDetail(id))));
    }
    private void loadReceiptDraft(String id,JSONObject purchase,LinearLayout host,int version){
        if(version!=pageVersion||isFinishing())return;
        String path="/construction/objects/"+id+"/receipt-ocr/"+purchase.optString("receipt_file_id");
        call(path,"GET",null,info->{
            if(version!=pageVersion)return;host.removeAllViews();String state=info.optString("state");
            boolean active=state.equals("queued")||state.equals("running")||state.equals("retry");
            JSONObject budget=info.optJSONObject("quota");if(budget!=null)host.addView(ui.label(budget.optInt("used")+" из "+budget.optInt("limit")+" чеков в месяц",12,MUTED,false));
            JSONObject draft=info.optJSONObject("draft");
            if(draft!=null){
                String merchant=draft.optString("merchant"),date=draft.optString("date");long total=draft.optLong("amount_kopecks");
                host.addView(ui.label((merchant.isEmpty()?"Магазин не найден":merchant)+" · Итого "+exactMoney(total,"RUB")+(date.isEmpty()?"":" · "+date),14,INK,true));
                addButton(host,"Проверить данные чека",false,v->ui.sheet("Проверка чека","Цена в форме будет рассчитана из всего итога чека. Если в чеке несколько материалов, исправьте её вручную. Закупка сохранится только после проверки формы.","Перенести в форму",false,()->{
                    try{JSONObject proposed=new JSONObject(purchase.toString());if(!date.isEmpty())proposed.put("purchased_on",date);
                        if(!merchant.isEmpty()){String notes=proposed.optString("notes");String combined=notes.isEmpty()?merchant:notes+" · "+merchant;proposed.put("notes",combined.substring(0,Math.min(2000,combined.length())));}
                        if(total>0){java.math.BigDecimal quantity=new java.math.BigDecimal(purchase.optString("quantity","1"));if(quantity.signum()>0)proposed.put("unit_price_kopecks",new java.math.BigDecimal(total).divide(quantity,0,java.math.RoundingMode.HALF_UP).longValueExact());}
                        call("/construction/objects/"+id,"GET",null,detail->constructionPurchaseForm(id,detail.optJSONArray("quantities"),proposed));
                    }catch(Exception error){message("Проверьте сумму и количество вручную");}
                }));
            }else if(active){
                host.addView(ui.label(info.optString("progress","Распознаю чек…"),13,MUTED,false));
                if(!info.optBoolean("cancel_requested"))addButton(host,"Отменить распознавание",false,v->call(path,"DELETE",null,r->loadReceiptDraft(id,purchase,host,version)));
                host.postDelayed(()->{if(version==pageVersion)loadReceiptDraft(id,purchase,host,version);},4000);
            }else{
                if(!info.optString("error").isEmpty())host.addView(ui.label(info.optString("error"),13,MUTED,false));
                final String requestKey=java.util.UUID.randomUUID().toString();
                addButton(host,state.equals("failed")||state.equals("cancelled")?"Повторить распознавание":"Распознать фото чека",false,v->{try{call(path,"POST",new JSONObject().put("_request_key",requestKey),r->loadReceiptDraft(id,purchase,host,version));}catch(Exception error){message("Не удалось открыть чек");}});
            }
        });
    }
    private void constructionLogNew(String id,JSONArray zones,JSONArray quantities){constructionLogForm(id,zones,quantities,null);}
    private void constructionLogForm(String id,JSONArray zones,JSONArray quantities,JSONObject previous){
        boolean editing=previous!=null;
        page(editing?"Запись журнала":"Журнал работ",editing?"construction-log-edit":"construction-log-new",true);
        content.addView(ui.label(editing?"Исправить запись":"Что сделано за день?",25,INK,true));
        EditText date=field("Дата · ГГГГ-ММ-ДД",android.text.InputType.TYPE_CLASS_DATETIME|android.text.InputType.TYPE_DATETIME_VARIATION_DATE);
        date.setText(editing?previous.optString("work_date"):new java.text.SimpleDateFormat("yyyy-MM-dd",Locale.ROOT).format(new java.util.Date()));
        EditText description=field("Выполненная работа",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        if(editing)description.setText(previous.optString("work_description"));
        EditText workers=field("Исполнители или бригада",android.text.InputType.TYPE_CLASS_TEXT);
        if(editing)workers.setText(previous.optString("workers"));
        EditText workerCount=field("Количество человек",android.text.InputType.TYPE_CLASS_NUMBER);
        workerCount.setText(editing?previous.optString("worker_count"):"0");
        ui.section(content,"Помещение",null);
        java.util.ArrayList<String> rooms=new java.util.ArrayList<>();rooms.add("Весь объект");
        int roomSelection=0;if(zones!=null)for(int i=0;i<zones.length();i++){JSONObject zone=zones.optJSONObject(i);if(zone==null)continue;rooms.add(zone.optString("name"));if(editing&&zone.optString("id").equals(previous.optString("zone_id")))roomSelection=rooms.size()-1;}
        Spinner room=new Spinner(this);room.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,rooms));room.setSelection(roomSelection);content.addView(room);
        ui.section(content,"Позиция ведомости",null);
        java.util.ArrayList<String> names=new java.util.ArrayList<>();java.util.ArrayList<JSONObject> works=new java.util.ArrayList<>();names.add("Без привязки");
        int workSelection=0;if(quantities!=null)for(int i=0;i<quantities.length();i++){JSONObject item=quantities.optJSONObject(i);if(item==null||!"work".equals(item.optString("kind")))continue;works.add(item);names.add(item.optString("title")+" · "+item.optString("unit"));if(editing&&item.optString("id").equals(previous.optString("quantity_id")))workSelection=works.size();}
        Spinner work=new Spinner(this);work.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,names));work.setSelection(workSelection);content.addView(work);
        EditText volume=field("Выполненный объём за день",android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL);
        volume.setText(editing?previous.optString("completed_quantity"):"0");
        String[] units={"Без объёма","м²","м³","м","м.п.","шт.","компл.","кг","т","л","ч","чел.-ч","маш.-ч"};
        Spinner unit=new Spinner(this);unit.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,units));
        if(editing)for(int i=1;i<units.length;i++)if(units[i].equals(previous.optString("unit")))unit.setSelection(i);
        content.addView(unit);
        EditText comment=field("Комментарий для следующей смены",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        if(editing)comment.setText(previous.optString("comment"));
        button(editing?"Сохранить запись":"Записать день",true,v->{
            if(description.getText().toString().trim().isEmpty()){description.setError("Опишите выполненную работу");return;}
            try{JSONObject body=new JSONObject().put("work_date",date.getText().toString().trim()).put("work_description",description.getText().toString().trim())
                    .put("workers",workers.getText().toString().trim()).put("worker_count",workerCount.getText().toString().trim())
                    .put("completed_quantity",volume.getText().toString().trim()).put("unit",unit.getSelectedItemPosition()==0?"":units[unit.getSelectedItemPosition()])
                    .put("comment",comment.getText().toString().trim()).put("zone_id",room.getSelectedItemPosition()==0?"":zones.optJSONObject(room.getSelectedItemPosition()-1).optString("id"))
                    .put("quantity_id",work.getSelectedItemPosition()==0?"":works.get(work.getSelectedItemPosition()-1).optString("id"));
                call("/construction/objects/"+id+"/logs"+(editing?"/"+previous.optString("id"):""),editing?"PATCH":"POST",body,result->constructionDetail(id));
            }catch(Exception error){message(error.getMessage());}
        });
    }
    private void constructionLogDetail(String id,JSONObject log){
        if(log==null){constructionDetail(id);return;}
        page("Журнал работ","construction-log-detail",true);
        content.addView(ui.label(log.optString("work_description"),25,INK,true));
        text(log.optString("work_date"));
        if(!log.optString("workers").isEmpty()||log.optInt("worker_count")>0)text("Исполнители · "+log.optString("workers")+(log.optInt("worker_count")>0?" · "+log.optInt("worker_count")+" чел.":""));
        if(log.optDouble("completed_quantity")>0)text("Выполнено · "+log.optString("completed_quantity")+" "+log.optString("unit"));
        if(!log.optString("comment").isEmpty())text(log.optString("comment"));
        JSONArray photos=log.optJSONArray("photo_file_ids");
        if(photos!=null&&photos.length()>0){ui.section(content,"Фотографии",null);for(int i=0;i<photos.length();i++)constructionDefectPhoto(photos.optString(i));}
        addButton(content,"Прикрепить фото",false,v->{uploadConstruction=id;uploadProject=null;uploadDefect=null;uploadLog=log.optString("id");uploadPurchase=null;Intent picker=new Intent(Intent.ACTION_OPEN_DOCUMENT);picker.setType("image/*");picker.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/png","image/jpeg"});picker.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(picker,301);});
        addButton(content,"Изменить запись",false,v->call("/construction/objects/"+id,"GET",null,result->constructionLogForm(id,result.optJSONArray("zones"),result.optJSONArray("quantities"),log)));
        addButton(content,"Удалить запись",false,v->ui.sheet("Удалить запись?","Связанный фактический объём тоже будет удалён.","Удалить",false,()->call("/construction/objects/"+id+"/logs/"+log.optString("id"),"DELETE",null,result->constructionDetail(id))));
    }
    private void constructionDefectNew(String id,JSONArray zones){
        page("Новый дефект","construction-defect-new",true);
        content.addView(ui.label("Что обнаружено?",25,INK,true));
        text("Опишите проблему и укажите помещение. Фото можно прикрепить после сохранения.");
        java.util.ArrayList<JSONObject> rooms=new java.util.ArrayList<>();rooms.add(null);
        if(zones!=null)for(int i=0;i<zones.length();i++)if(zones.optJSONObject(i)!=null)rooms.add(zones.optJSONObject(i));
        String[] names=new String[rooms.size()];names[0]="Весь объект";
        for(int i=1;i<rooms.size();i++)names[i]=rooms.get(i).optString("name");
        Spinner room=new Spinner(this);room.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,names));content.addView(room);
        EditText description=field("Описание дефекта",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        EditText measure=field("Замер, если известен",android.text.InputType.TYPE_CLASS_TEXT);
        EditText work=field("Предлагаемая работа",android.text.InputType.TYPE_CLASS_TEXT);
        button("Сохранить дефект",true,v->{if(description.getText().toString().trim().isEmpty()){description.setError("Опишите проблему");return;}
            try{JSONObject body=new JSONObject().put("description",description.getText().toString().trim()).put("measurement_note",measure.getText().toString().trim()).put("suggested_work",work.getText().toString().trim());
                if(room.getSelectedItemPosition()>0)body.put("zone_id",rooms.get(room.getSelectedItemPosition()).optString("id"));
                call("/construction/objects/"+id+"/defects","POST",body,result->constructionDefectDetail(id,result.optJSONObject("defect")));}
            catch(Exception error){message(error.getMessage());}
        });
    }
    private void constructionDefectDetail(String id,JSONObject defect){
        if(defect==null){constructionDetail(id);return;}
        page("Дефект","construction-defect-detail",true);
        content.addView(ui.label(defect.optString("description"),25,INK,true));
        if(!defect.optString("measurement_note").isEmpty())text("Замер · "+defect.optString("measurement_note"));
        if(!defect.optString("suggested_work").isEmpty())text("Работа · "+defect.optString("suggested_work"));
        String status=defect.optString("status");
        ui.space(content,18);content.addView(ui.badge("resolved".equals(status)?"Устранён":"in_progress".equals(status)?"В работе":"Открыт",BLUE));
        if(!"in_progress".equals(status))addButton(content,"Взять в работу",false,v->constructionDefectStatus(id,defect,"in_progress"));
        if(!"resolved".equals(status))addButton(content,"Отметить устранённым",false,v->constructionDefectStatus(id,defect,"resolved"));
        if("resolved".equals(status))addButton(content,"Открыть снова",false,v->constructionDefectStatus(id,defect,"open"));
        if(defect.optString("photo_file_id").isEmpty())addButton(content,"Прикрепить фото",false,v->{
            uploadConstruction=id;uploadProject=null;uploadDefect=defect.optString("id");uploadLog=null;uploadPurchase=null;
            Intent picker=new Intent(Intent.ACTION_OPEN_DOCUMENT);picker.setType("image/*");
            picker.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/png","image/jpeg"});
            picker.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(picker,301);
        });else constructionDefectPhoto(defect.optString("photo_file_id"));
    }
    private void constructionDefectPhoto(String fileId){
        ImageView image=new ImageView(this);image.setScaleType(ImageView.ScaleType.CENTER_CROP);
        image.setBackground(ui.shape(RAISED,12,LINE));image.setClipToOutline(true);
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,dp(220));params.topMargin=dp(18);content.addView(image,params);
        final int version=pageVersion;
        worker.execute(()->{HttpURLConnection connection=null;try{
            connection=(HttpURLConnection)new URL(BuildConfig.API_BASE_URL+"/api/files/"+fileId).openConnection();
            connection.setConnectTimeout(10000);connection.setReadTimeout(20000);
            connection.setRequestProperty("Authorization","Bearer "+token);
            String contentType=connection.getContentType();
            if(connection.getResponseCode()!=200||contentType==null||!contentType.startsWith("image/"))throw new IOException("Image unavailable");
            byte[] bytes;try(InputStream input=connection.getInputStream()){bytes=readLimited(input,5_500_000);}
            android.graphics.BitmapFactory.Options options=new android.graphics.BitmapFactory.Options();options.inJustDecodeBounds=true;
            android.graphics.BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);
            options.inSampleSize=1;while(options.outWidth/options.inSampleSize>1600||options.outHeight/options.inSampleSize>1600)options.inSampleSize*=2;
            options.inJustDecodeBounds=false;android.graphics.Bitmap bitmap=android.graphics.BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);
            if(bitmap==null)throw new IOException("Image unavailable");
            runOnUiThread(()->{if(!isFinishing()&&pageVersion==version)image.setImageBitmap(bitmap);else bitmap.recycle();});
        }catch(Exception error){runOnUiThread(()->{if(!isFinishing()&&pageVersion==version)message("Не удалось открыть фото");});}
        finally{if(connection!=null)connection.disconnect();}});
    }
    private void constructionDefectStatus(String id,JSONObject defect,String status){
        try{call("/construction/objects/"+id+"/defects/"+defect.optString("id"),"PATCH",new JSONObject().put("status",status),result->constructionDefectDetail(id,result.optJSONObject("defect")));}
        catch(Exception error){message(error.getMessage());}
    }
    // CONSTRUCTION END
    private void catalogList(){
        publicView=false;page("Расценки","catalog",false);
        content.addView(ui.label("Расценки",26,INK,true));
        text("Цены для новых смет. История изменений всегда под рукой.");
        button("+ Добавить расценку",true,v->catalogForm(null));
        EditText search=field("Поиск",android.text.InputType.TYPE_CLASS_TEXT);
        search.setSingleLine(true);search.setMinHeight(dp(56));search.setHint("Название, категория или артикул");search.setText(catalogSearch);
        LinearLayout filters=ui.row();ui.space(content,14);
        TextView favorite=catalogFilter("Избранное",catalogFavorites),recent=catalogFilter("Недавние",catalogRecent);
        filters.addView(favorite);ui.gap(filters,10);filters.addView(recent);content.addView(filters);
        ui.space(content,8);HorizontalScrollView categoryScroll=new HorizontalScrollView(this);
        categoryScroll.setHorizontalScrollBarEnabled(false);LinearLayout categories=ui.row();categoryScroll.addView(categories);
        content.addView(categoryScroll);ui.space(content,14);LinearLayout host=ui.column();content.addView(host);
        ui.tap(favorite,()->{catalogFavorites=!catalogFavorites;favorite.setTextColor(catalogFavorites?BLUE:MUTED);catalogLoad(host,categories,0);});
        ui.tap(recent,()->{catalogRecent=!catalogRecent;recent.setTextColor(catalogRecent?BLUE:MUTED);catalogLoad(host,categories,0);});
        final Runnable[] pending={null};
        search.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence s,int start,int count,int after){}
            public void onTextChanged(CharSequence s,int start,int before,int count){
                catalogSearch=s.toString();if(pending[0]!=null)search.removeCallbacks(pending[0]);
                pending[0]=()->{if(currentPage.equals("catalog"))catalogLoad(host,categories,0);};
                search.postDelayed(pending[0],250);
            }
            public void afterTextChanged(Editable value){}
        });
        call("/workspace","GET",null,result->{
            JSONObject workspace=result.optJSONObject("workspace");
            if(workspace!=null)catalogCurrency=workspace.optString("currency","RUB");
            if(catalogItems.length()>0)catalogRows(host,catalogItems,catalogHasMore,categories);
        });
        catalogLoad(host,categories,0);
    }
    private TextView catalogFilter(String title,boolean selected){
        TextView chip=ui.label(title,12,selected?BLUE:MUTED,selected);
        chip.setGravity(Gravity.CENTER);chip.setMinHeight(dp(40));chip.setPadding(dp(14),dp(8),dp(14),dp(8));
        ui.ripple(chip,BG,12,LINE);return chip;
    }
    private void catalogLoad(LinearLayout host,LinearLayout categories,int offset){
        final int sequence=++catalogLoadSeq;
        if(offset==0){catalogItems=new JSONArray();host.removeAllViews();loading(host);}
        String path="/catalog?q="+android.net.Uri.encode(catalogSearch.trim())
            +(catalogFavorites?"&favorite=1":"")+(catalogRecent?"&recent=1":"")
            +(catalogCategory.isEmpty()?"":"&category="+android.net.Uri.encode(catalogCategory))+"&offset="+offset;
        call(path,"GET",null,result->{
            if(sequence!=catalogLoadSeq)return;
            clearLoading(host);JSONArray next=result.optJSONArray("items");if(next==null)next=new JSONArray();
            if(categories!=null&&offset==0)catalogCategories(categories,host,result.optJSONArray("categories"));
            for(int i=0;i<next.length();i++)catalogItems.put(next.opt(i));
            catalogHasMore=next.length()==50;
            catalogRows(host,catalogItems,catalogHasMore,categories);
        });
    }
    private void catalogCategories(LinearLayout row,LinearLayout host,JSONArray options){
        row.removeAllViews();TextView all=catalogFilter("Все",catalogCategory.isEmpty());row.addView(all);
        ui.tap(all,()->{catalogCategory="";catalogLoad(host,row,0);});
        if(options==null)return;
        for(int i=0;i<options.length();i++){
            String category=options.optString(i);if(category.isBlank())continue;
            ui.gap(row,8);TextView chip=catalogFilter(category,category.equals(catalogCategory));row.addView(chip);
            ui.tap(chip,()->{catalogCategory=category;catalogLoad(host,row,0);});
        }
    }
    private void catalogRows(LinearLayout host,JSONArray items,boolean hasMore){catalogRows(host,items,hasMore,null);}
    private void catalogRows(LinearLayout host,JSONArray items,boolean hasMore,LinearLayout categories){
        host.removeAllViews();
        if(items.length()==0){ui.empty(host,"document",catalogSearch.isBlank()?"Расценок пока нет":"Ничего не найдено",catalogSearch.isBlank()?"Добавьте первую цену для будущей сметы.":"Попробуйте другой запрос или снимите фильтр.");return;}
        for(int i=0;i<items.length();i++){
            JSONObject item=items.optJSONObject(i);if(item==null)continue;
            LinearLayout line=ui.card(host),heading=ui.row();
            LinearLayout description=ui.column();TextView title=ui.label(item.optString("name"),15,INK,true);title.setMaxLines(2);description.addView(title);
            ui.space(description,5);description.addView(ui.label(item.optString("category","Без категории")+" · "+item.optString("unit","шт."),11,MUTED,false));
            heading.addView(description,new LinearLayout.LayoutParams(0,-2,1));
            TextView star=ui.label(item.optInt("favorite")==1?"★":"☆",24,item.optInt("favorite")==1?BLUE:MUTED,false);
            star.setGravity(Gravity.CENTER);star.setContentDescription(item.optInt("favorite")==1?"Убрать из избранного":"Добавить в избранное");
            heading.addView(star,new LinearLayout.LayoutParams(dp(48),dp(48)));line.addView(heading);
            ui.space(line,9);line.addView(ui.label(exactMoney(item.optLong("price"),catalogCurrency)+" / "+item.optString("unit","шт."),17,INK,false));
            ui.tap(star,()->catalogFavorite(item,host));
            ui.tap(line,()->catalogDetail(item.optString("id")));
        }
        if(hasMore)addButton(host,"Показать ещё",false,v->catalogLoad(host,categories,items.length()));
    }
    private void catalogFavorite(JSONObject item,LinearLayout listHost){
        String id=item.optString("id");
        try{JSONObject payload=new JSONObject().put("revision",item.optInt("revision"))
            .put("favorite",item.optInt("favorite")==1?0:1);
            call("/catalog/"+id,"PATCH",payload,result->{
                if(listHost!=null)catalogList();else catalogDetail(id);
            });
        }catch(Exception error){message("Не удалось обновить избранное");}
    }
    private String catalogType(String value){
        switch(value){case "work":return "Работа";case "material":return "Материал";case "equipment":return "Оборудование";case "other":return "Прочее";default:return "Услуга";}
    }
    private void catalogDetail(String id){
        parentPage="catalog";page("Расценка","catalog-detail",true);loading(content);
        call("/catalog/"+id,"GET",null,result->{
            clearLoading(content);JSONObject item=result.optJSONObject("item");if(item==null)return;
            content.addView(ui.label(item.optString("name"),29,INK,true));ui.space(content,24);ui.divider(content);ui.space(content,20);
            content.addView(ui.label("ТЕКУЩАЯ ЦЕНА",10,BLUE,true));ui.space(content,8);
            content.addView(ui.label(exactMoney(item.optLong("price"),catalogCurrency),38,INK,true));
            ui.space(content,5);content.addView(ui.label("за "+item.optString("unit","шт."),12,MUTED,false));
            ui.space(content,25);ui.divider(content);
            catalogMeta("Категория",item.optString("category").isEmpty()?"Без категории":item.optString("category"));
            catalogMeta("Тип",catalogType(item.optString("item_type")));
            if(!item.optString("article").isEmpty())catalogMeta("Артикул",item.optString("article"));
            catalogMeta("Себестоимость",exactMoney(item.optLong("cost_price"),catalogCurrency));
            if(!item.optString("description").isEmpty()){
                ui.section(content,"Описание",null);content.addView(ui.label(item.optString("description"),13,MUTED,false));
            }
            button("Редактировать",true,v->catalogForm(item));
            button(item.optInt("favorite")==1?"Убрать из избранного":"Добавить в избранное",false,v->catalogFavorite(item,null));
            ui.section(content,"История цены",null);JSONArray history=item.optJSONArray("price_history");
            if(history==null||history.length()==0){text("История начнётся со следующего изменения цены.");return;}
            for(int i=0;i<history.length();i++){
                JSONObject entry=history.optJSONObject(i);if(entry==null)continue;
                LinearLayout row=ui.card(content),top=ui.row();
                top.addView(ui.label(exactMoney(entry.optLong("price"),catalogCurrency),15,INK,true),new LinearLayout.LayoutParams(0,-2,1));
                String day=java.text.DateFormat.getDateInstance(java.text.DateFormat.MEDIUM,new Locale("ru","RU"))
                    .format(new java.util.Date(entry.optLong("created_at")*1000));
                top.addView(ui.label(day,11,MUTED,false));row.addView(top);
                if(i==history.length()-1){ui.space(row,5);row.addView(ui.label("Начальная цена",11,MUTED,false));}
            }
        });
    }
    private void catalogMeta(String title,String value){
        LinearLayout row=ui.card(content);row.addView(ui.label(title,11,MUTED,false));
        ui.space(row,6);row.addView(ui.label(value,14,INK,false));
    }
    private void catalogForm(JSONObject old){
        catalogParentId=old==null?null:old.optString("id");
        page(old==null?"Новая расценка":"Редактирование","catalog-form",true);
        text("Цена применяется к новым сметам. Уже согласованные условия сохраняются.");
        EditText name=field("Название",android.text.InputType.TYPE_CLASS_TEXT),price=field("Цена, "+currencySymbol(catalogCurrency),8194),
            cost=field("Себестоимость, "+currencySymbol(catalogCurrency),8194),unit=field("Единица",android.text.InputType.TYPE_CLASS_TEXT),
            category=field("Категория",android.text.InputType.TYPE_CLASS_TEXT),article=field("Артикул",android.text.InputType.TYPE_CLASS_TEXT),description=field("Описание",1);
        final String[] type={old==null?"service":old.optString("item_type","service")};
        TextView typeChoice=ui.label("Тип · "+catalogType(type[0]),13,BLUE,false);
        typeChoice.setPadding(0,dp(16),0,dp(16));content.addView(typeChoice);
        ui.tap(typeChoice,()->ui.choiceSheet("Тип позиции",
            new String[]{"Работа","Материал","Оборудование","Услуга","Прочее"},
            new Runnable[]{()->catalogSelectType(type,typeChoice,"work"),()->catalogSelectType(type,typeChoice,"material"),
                ()->catalogSelectType(type,typeChoice,"equipment"),()->catalogSelectType(type,typeChoice,"service"),
                ()->catalogSelectType(type,typeChoice,"other")}));
        if(old!=null){name.setText(old.optString("name"));price.setText(java.math.BigDecimal.valueOf(old.optLong("price"),2).toPlainString());
            cost.setText(java.math.BigDecimal.valueOf(old.optLong("cost_price"),2).toPlainString());
            unit.setText(old.optString("unit"));category.setText(old.optString("category"));article.setText(old.optString("article"));description.setText(old.optString("description"));}
        else{cost.setText("0");unit.setText("шт.");}
        button("Сохранить расценку",true,v->{
            if(name.getText().toString().trim().isEmpty()){name.setError("Укажите название");return;}
            if(unit.getText().toString().trim().isEmpty()){unit.setError("Укажите единицу");return;}
            long value,costValue;
            try{value=cents(price);costValue=cents(cost);if(value<0||costValue<0)throw new IllegalArgumentException();}
            catch(Exception error){price.setError("Проверьте цену и себестоимость");return;}
            try{JSONObject payload=new JSONObject().put("name",name.getText().toString().trim())
                .put("price",value).put("cost_price",costValue).put("unit",unit.getText().toString().trim())
                .put("category",category.getText().toString().trim()).put("article",article.getText().toString().trim())
                .put("description",description.getText().toString().trim())
                .put("item_type",type[0]);
                if(old!=null){payload.put("revision",old.optLong("revision"));catalogSave(old.optString("id"),payload);return;}
                String query=android.net.Uri.encode(name.getText().toString().trim());
                call("/catalog?q="+query,"GET",null,result->{
                    JSONArray items=result.optJSONArray("items");boolean duplicate=false;
                    if(items!=null)for(int i=0;i<items.length();i++){
                        JSONObject match=items.optJSONObject(i);
                        if(match!=null&&match.optString("name").trim().equalsIgnoreCase(name.getText().toString().trim())
                            &&match.optString("unit").trim().equalsIgnoreCase(unit.getText().toString().trim())){duplicate=true;break;}
                    }
                    if(duplicate)ui.sheet("Похожая расценка уже есть","Название и единица совпадают. Проверьте список, прежде чем создавать ещё одну позицию.","Создать отдельно",false,()->catalogSave(null,payload));
                    else catalogSave(null,payload);
                });
            }catch(Exception error){message("Не удалось подготовить расценку");}
        });
    }
    private void catalogSelectType(String[] current,TextView label,String value){current[0]=value;label.setText("Тип · "+catalogType(value));}
    private void catalogSave(String id,JSONObject payload){
        call(id==null?"/catalog":"/catalog/"+id,id==null?"POST":"PATCH",payload,result->{
            JSONObject item=result.optJSONObject("item");if(item==null){catalogList();return;}
            catalogDetail(item.optString("id"));message("Расценка сохранена");
        });
    }
    private void more(){publicView=false;page("Ещё","more",false);content.addView(ui.label("Всё для работы.",26,INK,true));text("Остальные разделы в одном месте.");menu("check","Согласования","Ответы клиентов по сметам",this::approvals);menu("projects","Объекты и замеры","Помещения, объёмы и контроль работ",this::constructionList);menu("wallet","Платежи","Полученные деньги и остатки",this::payments);menu("document","Расценки","Цены, история и избранное",this::catalogList);menu("spark","Ассистент","Подготовка действий с подтверждением",this::assistant);menu("clock","Задачи","Следующие шаги",()->records("tasks"));menu("wallet","Тариф и подписка","Ваш текущий доступ",this::billing);menu("grid","Профиль и настройки","Управление аккаунтом",this::settings);menu("document","Поддержка","Написать нам",this::support);}
    private void records(String kind){
        page("",kind,false);content.addView(ui.label(kind.equals("clients")?"Ваши клиенты":kind.equals("projects")?"Всё движется\nпо плану.":"Задачи",26,INK,true));text(kind.equals("clients")?"Люди, с которыми вы создаёте больше.":kind.equals("projects")?"Работа, договорённости и оплата.":"Следующий шаг для каждого проекта.");
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
    private void newClient(){parentPage="clients";page("Новый клиент","client",true);text("Все контакты — в одном месте.");EditText name=field("Имя или компания",android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_CAP_WORDS),email=field("Электронная почта",33),phone=field("Телефон",3);ui.space(content,16);button("Добавить клиента",true,v->{if(name.length()==0){name.setError("Укажите имя");return;}try{call("/clients","POST",new JSONObject().put("name",name.getText().toString()).put("email",email.getText().toString()).put("phone",phone.getText().toString()),r->{Analytics.event("client_created",Analytics.params("source","android"),true);records("clients");message("Клиент добавлен");});}catch(Exception error){message(error.getMessage());}});}
    private void client(String id){
        parentPage="clients";page("Клиент","client",true);loading(content);
        call("/clients/"+id,"GET",null,r->{
            clearLoading(content);JSONObject c=r.optJSONObject("item");if(c==null)return;
            content.addView(ui.label(c.optString("name"),26,INK,true));
            button("Спросить ассистента",false,v->askAssistant("clients",id,c.optString("name")));
            LinearLayout contacts=ui.card(content);contacts.addView(ui.label("КОНТАКТЫ",10,MUTED,true));ui.space(contacts,14);
            TextView email=ui.label(c.optString("email","Почта не указана"),16,INK,false);email.setTextIsSelectable(true);contacts.addView(email);ui.space(contacts,10);
            TextView phone=ui.label(c.optString("phone","Телефон не указан"),16,INK,false);phone.setTextIsSelectable(true);contacts.addView(phone);
            JSONArray requests=c.optJSONArray("requests");if(requests!=null&&requests.length()>0){ui.section(content,"Заявки",null);for(int i=0;i<requests.length();i++){JSONObject request=requests.optJSONObject(i);if(request==null)continue;LinearLayout row=ui.card(content);row.addView(ui.label(request.optString("details"),14,INK,false));if(!request.optString("due_date").isEmpty()){ui.space(row,7);row.addView(ui.label("Срок · "+request.optString("due_date"),12,MUTED,false));}}}
            ui.section(content,"Сметы клиента",null);JSONArray list=c.optJSONArray("quotes");LinearLayout host=ui.column();content.addView(host);renderQuotes(host,list==null?new JSONArray():list,"");
            JSONArray projects=c.optJSONArray("projects");if(projects!=null&&projects.length()>0){ui.section(content,"Проекты",null);for(int i=0;i<projects.length();i++){JSONObject item=projects.optJSONObject(i);if(item==null)continue;LinearLayout row=ui.card(content);row.addView(ui.label(item.optString("name"),15,INK,true));ui.space(row,6);row.addView(ui.label(exactMoney(item.optLong("amount_kopecks"),item.optString("currency","RUB")),13,MUTED,false));ui.tap(row,()->project(item.optString("id")));}}
            JSONArray history=c.optJSONArray("timeline");if(history!=null&&history.length()>0){ui.section(content,"История",null);for(int i=0;i<Math.min(history.length(),10);i++){JSONObject event=history.optJSONObject(i);if(event==null)continue;content.addView(ui.label(event.optString("action"),13,INK,false));ui.space(content,6);}}
        });
    }
    private void project(String id){
        parentPage="projects";page("Заказ","project",true);loading(content);call("/projects/"+id,"GET",null,r->{clearLoading(content);JSONObject p=r.optJSONObject("item");if(p==null)return;content.addView(ui.badge(status(p.optString("status")),statusColor(p.optString("status"))));ui.space(content,18);content.addView(ui.label(p.optString("name"),26,INK,true));
            String currency=p.optString("currency","RUB");long cost=p.optLong("amount_kopecks"),paid=p.optLong("paid");LinearLayout card=ui.card(content);card.setBackground(ui.gradient(24));card.addView(ui.label("Стоимость заказа",12,BLUE,false));ui.space(card,12);card.addView(ui.label(exactMoney(cost,currency),32,INK,true));ui.space(card,18);
            FrameLayout track=new FrameLayout(this);track.setBackground(ui.shape(0xff364254,4,0));View fill=new View(this);fill.setBackground(ui.shape(GREEN,4,0));track.addView(fill,new FrameLayout.LayoutParams(0,-1));card.addView(track,new LinearLayout.LayoutParams(-1,dp(5)));track.post(()->{fill.getLayoutParams().width=(int)(track.getWidth()*Math.min(1,Math.max(0,cost>0?(double)paid/cost:0)));fill.requestLayout();});ui.space(card,12);card.addView(ui.label("Получено "+exactMoney(paid,currency),13,GREEN,true));ui.space(card,5);card.addView(ui.label("Осталось "+exactMoney(Math.max(0,cost-paid),currency),12,MUTED,false));
            button("Спросить ассистента",false,v->askAssistant("projects",id,p.optString("name")));
            button("Записать оплату",true,v->receipt(id,currency));button("Прикрепить файл",false,v->{uploadProject=id;uploadConstruction=null;uploadDefect=null;uploadLog=null;uploadPurchase=null;Intent picker=new Intent(Intent.ACTION_OPEN_DOCUMENT);picker.setType("*/*");picker.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/png","image/jpeg","application/pdf","text/plain"});picker.addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(picker,301);});
            ui.section(content,"Этапы работы",null);JSONArray stages=p.optJSONArray("stages");if(stages==null||stages.length()==0)text("Этапы ещё не добавлены.");else for(int i=0;i<stages.length();i++){JSONObject stage=stages.optJSONObject(i);if(stage==null)continue;LinearLayout line=ui.card(content);line.addView(ui.label(String.format(Locale.ROOT,"%02d",i+1)+"   "+stage.optString("name"),16,INK,true));ui.space(line,8);line.addView(ui.badge(status(stage.optString("status")),statusColor(stage.optString("status"))));}
            if(!p.optString("status").equals("completed")){ui.space(content,18);button("Завершить заказ",false,v->ui.sheet("Работа завершена?","Заказ получит статус «Завершён». Его смета и история оплат сохранятся.","Завершить заказ",false,()->{try{call("/projects/"+id,"PATCH",new JSONObject().put("revision",p.optInt("revision")).put("status","completed"),res->project(id));}catch(Exception error){message(error.getMessage());}}));}
        });
    }
    private void receipt(String projectId,String currency){parentPage="projects";page("Полученная оплата","receipt",true);content.addView(ui.label("Зафиксируйте\nновое поступление.",26,INK,true));text("Укажите деньги, которые уже получили от клиента. Это запись в учёте, средства не списываются.");EditText value=field("Сумма оплаты, "+currencySymbol(currency),8194);value.setHint("0,00");final String key=java.util.UUID.randomUUID().toString();ui.space(content,20);button("Сохранить оплату",true,v->{try{long amount=cents(value);if(amount<=0)throw new IllegalArgumentException();call("/receipts","POST",new JSONObject().put("project_id",projectId).put("amount_kopecks",amount).put("method","bank_transfer").put("_request_key",key),r->{Analytics.event("payment_recorded",Analytics.params("currency",currency),true);project(projectId);message("Оплата записана");});}catch(Exception error){value.setError("Укажите сумму больше нуля");}});}
    private void settings(){
        publicView=false;page("Профиль","settings",false);content.addView(ui.label("Ваше пространство",26,INK,true));
        menu("wallet","Тариф и подписка","Старт и Про · один доступ везде",this::billing);LinearLayout profile=ui.card(content);profile.addView(ui.label(me==null?"Сметра":me.optString("name"),24,INK,true));ui.space(profile,8);profile.addView(ui.label(me==null?"":me.optString("email"),13,MUTED,false));ui.space(profile,18);profile.addView(ui.badge(me==null||me.optString("plan").equals("free")?"Базовый доступ":me.optString("plan").toUpperCase(Locale.ROOT),BLUE));text("Ваш доступ действует и на сайте, и в приложении.");
        if(me!=null&&!me.optBoolean("email_verified",false)){LinearLayout note=ui.card(content);note.addView(ui.label("Подтвердите почту",16,AMBER,true));ui.space(note,8);note.addView(ui.label("Откройте ссылку из письма, чтобы подтвердить адрес аккаунта.",13,MUTED,false));addButton(note,"Отправить письмо",false,v->call("/auth/verify/resend","POST",new JSONObject(),r->message("Письмо отправлено")));}
        ui.section(content,"Управление",null);menu("clock","Задачи","Ближайшие шаги по проектам",()->records("tasks"));menu("refresh","Обновить доступ","Синхронизировать аккаунт",this::refresh);menu("document","Поддержка","Поможем разобраться",this::support);
        ui.space(content,20);button("Выйти из аккаунта",false,v->ui.sheet("Выйти из Сметры?","Сметы и заказы останутся в аккаунте. Локальный черновик на этом устройстве будет удалён.","Выйти",false,()->call("/auth/logout","POST",new JSONObject(),r->{clearSession();login(false);})));
        Button remove=button("Удалить аккаунт",false,v->ui.sheet("Удалить аккаунт?","Все предложения и данные аккаунта будут удалены без возможности восстановления.","Удалить навсегда",true,()->call("/me","DELETE",null,r->{clearSession();login(false);})));remove.setTextColor(RED);
        ui.space(content,22);TextView version=ui.label("СМЕТРА  /  "+BuildConfig.VERSION_NAME,10,MUTED,false);version.setGravity(Gravity.CENTER);content.addView(version);
    }
    private void menu(String icon,String title,String subtitle,Runnable click){LinearLayout card=ui.card(content),row=ui.row();row.addView(ui.new Icon(icon,BLUE),new LinearLayout.LayoutParams(dp(22),dp(22)));ui.gap(row,16);LinearLayout copy=ui.column();copy.addView(ui.label(title,15,INK,true));ui.space(copy,5);copy.addView(ui.label(subtitle,11,MUTED,false));row.addView(copy,new LinearLayout.LayoutParams(0,-2,1));row.addView(ui.new Icon("chevron",MUTED),new LinearLayout.LayoutParams(dp(18),dp(18)));card.addView(row);ui.tap(card,click);}
    private void support(){parentPage="settings";page("Мы на связи","support",true);content.addView(ui.label("Чем можем\nпомочь?",32,INK,true));text("Опишите, что произошло или чего не хватает. Ваше сообщение попадёт в поддержку Сметры.");EditText input=field("Ваше сообщение",1);ui.space(content,16);button("Отправить сообщение",true,v->{if(input.getText().toString().trim().isEmpty()){input.setError("Напишите сообщение");return;}try{call("/support","POST",new JSONObject().put("message",input.getText().toString()),r->{settings();message("Сообщение отправлено");});}catch(Exception error){message(error.getMessage());}});}
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){super.onActivityResult(requestCode,resultCode,data);if(requestCode==305){receiveAssistantAttachment(resultCode,data);return;}if(requestCode==304){saveActPdf(resultCode,data);return;}if(resultCode!=RESULT_OK||data==null){if(requestCode==301){uploadProject=null;uploadConstruction=null;uploadDefect=null;uploadLog=null;uploadPurchase=null;}return;}if(requestCode==302){java.util.ArrayList<String> words=data.getStringArrayListExtra(android.speech.RecognizerIntent.EXTRA_RESULTS);if(words!=null&&!words.isEmpty()){pendingCaptureText=words.get(0);capture();}return;}if(requestCode==303){if(data.getData()!=null){pendingCaptureFile=data.getData();capture();}return;}if(requestCode!=301||data.getData()==null)return;final android.net.Uri uri=data.getData();final String projectId=uploadProject,constructionId=uploadConstruction,defectId=uploadDefect,logId=uploadLog,purchaseId=uploadPurchase;uploadProject=null;uploadConstruction=null;uploadDefect=null;uploadLog=null;uploadPurchase=null;message("Прикрепляем файл…");worker.execute(()->{try{String mime=getContentResolver().getType(uri);String suffix="image/png".equals(mime)?".png":"image/jpeg".equals(mime)?".jpg":"application/pdf".equals(mime)?".pdf":".txt";byte[] bytes;try(InputStream input=getContentResolver().openInputStream(uri)){bytes=readLimited(input,3_000_000);}JSONObject payload=new JSONObject().put(constructionId!=null?"construction_id":"project_id",constructionId!=null?constructionId:projectId).put("name","Вложение"+suffix).put("content",android.util.Base64.encodeToString(bytes,android.util.Base64.NO_WRAP));JSONObject uploaded=request("/files","POST",payload);if(defectId!=null){JSONObject file=uploaded.optJSONObject("file");if(file==null)throw new IOException("Missing upload");request("/construction/objects/"+constructionId+"/defects/"+defectId,"PATCH",new JSONObject().put("photo_file_id",file.optString("id")));runOnUiThread(()->{if(!isFinishing())constructionDetail(constructionId);});}if(logId!=null){JSONObject file=uploaded.optJSONObject("file");if(file==null)throw new IOException("Missing upload");request("/construction/objects/"+constructionId+"/logs/"+logId+"/photos","POST",new JSONObject().put("file_id",file.optString("id")));runOnUiThread(()->{if(!isFinishing())constructionDetail(constructionId);});}if(purchaseId!=null){JSONObject file=uploaded.optJSONObject("file");if(file==null)throw new IOException("Missing upload");request("/construction/objects/"+constructionId+"/purchases/"+purchaseId,"PATCH",new JSONObject().put("receipt_file_id",file.optString("id")));runOnUiThread(()->{if(!isFinishing())constructionDetail(constructionId);});}runOnUiThread(()->{if(!isFinishing())message("Файл прикреплён");});}catch(Exception error){runOnUiThread(()->{if(!isFinishing())message("Не удалось прикрепить файл. "+error.getMessage());});}});}
    private void publicQuote(String publicToken){publicView=true;page("Предложение","public",false);loading(content);call("/public/quote?token="+android.net.Uri.encode(publicToken),"GET",null,r->{clearLoading(content);JSONObject q=r.optJSONObject("quote");if(q==null)return;content.addView(ui.badge(status(q.optString("status")),statusColor(q.optString("status"))));ui.space(content,20);content.addView(ui.label(q.optString("title"),26,INK,true));text(q.optString("description"));LinearLayout price=ui.card(content);price.setBackground(ui.gradient(24));price.addView(ui.label("Стоимость предложения",13,BLUE,false));ui.space(price,14);price.addView(ui.label(exactMoney(q.optLong("amount_kopecks"),q.optString("currency","RUB")),32,INK,true));ui.space(content,16);if(q.optString("status").equals("sent"))button("Согласовать предложение",true,v->ui.sheet("Согласовать условия?","Вы принимаете состав работ и стоимость этой версии предложения.","Да, согласовать",false,()->{try{call("/public/accept","POST",new JSONObject().put("token",publicToken).put("version",q.optInt("published_version")),result->{publicQuote(publicToken);message("Предложение согласовано");});}catch(Exception error){message(error.getMessage());}}));});}
    private void goBack(){if(currentPage.startsWith("assistant-")){assistant();return;}if(currentPage.equals("catalog-form")){if(catalogParentId!=null)catalogDetail(catalogParentId);else catalogList();return;}if(currentPage.equals("catalog-detail")){catalogList();return;}if(currentPage.equals("catalog")){more();return;}if(currentPage.equals("construction-zone")||currentPage.equals("construction-work")||currentPage.equals("construction-material")||currentPage.equals("construction-fact")||currentPage.equals("construction-defect-new")||currentPage.equals("construction-defect-detail")||currentPage.equals("construction-log-new")||currentPage.equals("construction-log-edit")||currentPage.equals("construction-log-detail")||currentPage.equals("construction-purchase-new")||currentPage.equals("construction-purchase-edit")||currentPage.equals("construction-purchase-detail")||currentPage.equals("construction-change-new")||currentPage.equals("construction-change-edit")||currentPage.equals("construction-change-detail")||currentPage.equals("construction-supplier-new")||currentPage.equals("construction-zone-edit")||currentPage.equals("construction-measure-new")||currentPage.equals("construction-measure-edit")){if(constructionParentId!=null)constructionDetail(constructionParentId);else constructionList();return;}if(currentPage.equals("construction-detail")||currentPage.equals("construction-new")){constructionList();return;}if(currentPage.equals("construction")){more();return;}if(currentPage.equals("draft-preview")){capture();return;}if(currentPage.equals("clients")||currentPage.equals("projects")||currentPage.equals("settings")){home();return;}if(currentPage.equals("tasks")){settings();return;}if(currentPage.equals("public")){publicView=false;if(token==null)login(false);else refresh();return;}if(currentPage.equals("register")){login(false);return;}publicView=false;if(parentPage.equals("clients"))records("clients");else if(parentPage.equals("projects"))records("projects");else if(parentPage.equals("settings"))settings();else if(token!=null)home();else login(false);}
    @Override public void onBackPressed(){if(currentPage.equals("home")||currentPage.equals("login"))super.onBackPressed();else if(currentPage.startsWith("assistant-"))assistant();else goBack();}
}
