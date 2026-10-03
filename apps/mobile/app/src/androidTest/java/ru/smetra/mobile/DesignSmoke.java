package ru.smetra.mobile;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.View;
import android.view.ViewGroup;
import android.widget.EditText;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.List;

/** Exercises native views against scripts/android_ui_fixture.py, captures actual device pixels. */
public class DesignSmoke extends Instrumentation {
    private Activity activity;
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){
        Bundle result=new Bundle();
        try{
            activity=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            waitText("Войти по почте");SystemClock.sleep(700);shot("01-welcome");click("Войти по почте");waitText("Войти в пространство");shot("01-login");
            fill("android-design@test.invalid","android design test only");click("Войти в пространство");
            waitText("Айдентика и упаковка");shot("02-overview");
            click("Интерьер студии");waitText("Состав сметы");waitText("Концепция и дизайн");waitText("Создать заказ из сметы");shot("02-quote");clickDescription("Назад");
            click("Ещё");click("Согласования");waitText("Решения клиентов");waitText("Согласована");shot("02-approvals");
            click("Ещё");click("Платежи");waitText("Деньги под контролем.");waitPrefix("65");shot("02-payments");click("Сегодня");waitPrefix("Все · ");
            click("Черновики");require(find("Сайт для студии Север")==null,"Draft filter must exclude sent quotes");clickPrefix("Все · ");
            click("Создать смету");waitText("Новая смета");fill("Дизайн мобильного приложения","Студия Север","98000","Аналитика, прототип и дизайн ключевых экранов.");
            top();shot("03-editor");click("Сегодня");waitPrefix("Все · ");click("Создать смету");
            require(editors().get(0).getText().toString().equals("Дизайн мобильного приложения"),"Local draft restored");click("Создать смету");waitPrefix("Все · ");
            click("Создать смету");fill("Ремонт квартиры","Студия Север","1","Покраска и отделка стен.");
            click("Добавить из расценок");waitText("Покраска стен");click("Покраска стен");
            EditText quantity=editors().get(editors().size()-1);runOnMainSync(()->quantity.setText("12.5"));
            click("Сегодня");waitPrefix("Все · ");click("Создать смету");waitText("Покраска стен");
            require(editors().get(editors().size()-1).getText().toString().equals("12.5"),"Catalog quantity must survive draft restore");
            click("Создать смету");waitText("Тестовая потеря ответа");
            click("Сегодня");waitPrefix("Все · ");click("Создать смету");waitText("Покраска стен");
            click("Создать смету");waitPrefix("Все · ");waitText("Ремонт квартиры");
            int matchingQuotes=0;for(View view:views())if(view instanceof TextView&&((TextView)view).getText().toString().equals("Ремонт квартиры"))matchingQuotes++;
            require(matchingQuotes==1,"Retry after lost response must not duplicate quote");
            click("Ремонт квартиры");waitText("Состав сметы");waitText("Покраска стен");shot("03-itemized-quote");clickDescription("Назад");
            click("Клиенты");waitText("Студия Север");shot("04-clients");
            click("Добавить клиента");fill("Михаил Орлов","mikhail@example.org","+79000000001");click("Добавить клиента");waitText("Михаил Орлов");
            click("Проекты");waitText("Интерьер студии");click("Интерьер студии");waitText("Записать оплату");shot("05-project");
            String paidBefore=textStarting("Получено ");click("Записать оплату");fill("15000");shot("06-payment");click("Сохранить оплату");waitText("Записать оплату");require(!paidBefore.equals(textStarting("Получено ")),"Payment total must update");
            click("Завершить заказ");SystemClock.sleep(600);shot("07-confirmation");getUiAutomation().performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK);SystemClock.sleep(400);
            require(find("Завершить заказ")!=null,"Dismiss confirmation without changing project");
            clickDescription("Назад");clickDescription("Открыть профиль");waitText("Ваше пространство");shot("08-profile");click("Поддержка");waitText("Отправить сообщение");shot("09-support");clickDescription("Назад");click("Тариф и подписка");require(find("Выбрать Про · 490 ₽")==null,"Android must not open external subscription checkout");shot("10-subscription");click("Ещё");click("Ассистент");waitPrefix("Отправить");shot("11-assistant");
            click("Ещё");click("Расценки");waitText("Покраска стен");waitText("Краска интерьерная");shot("12-catalog");
            click("Недавние");waitText("Покраска стен");require(find("Краска интерьерная")==null,"Recent catalog filter must exclude unused items");
            click("Недавние");click("Материалы");waitText("Краска интерьерная");require(find("Покраска стен")==null,"Catalog category filter must narrow list");
            click("Все");waitText("Покраска стен");fill("FIN-001");waitGone("Краска интерьерная");waitText("Покраска стен");
            fill("");waitText("Краска интерьерная");click("Покраска стен");waitText("История цены");waitText("FIN-001");shot("13-catalog-detail");
            click("Редактировать");fill("Покраска стен","1300","700","м²","Отделка","FIN-001","Подготовка и окраска в два слоя");
            click("Сохранить расценку");waitText("Начальная цена");shot("14-catalog-history");
            Intent shared=new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT,"Лендинг для кофейни, дизайн и вёрстка");runOnMainSync(()->((MainActivity)activity).onNewIntent(shared));waitText("Что нужно посчитать?");require(editors().get(0).getText().toString().contains("кофейни"),"Shared text must reach Capture");shot("15-capture");
            result.putString("stream","PASS: login, filters, manual and itemized draft restore, quote/client, project/payment, catalog search/filter/edit/history, share-to-Capture, custom sheet, navigation; screenshots in files/design-qa\n");
            finish(Activity.RESULT_OK,result);
        }catch(Throwable error){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error));finish(Activity.RESULT_CANCELED,result);}
    }
    private void clickDescription(String text){for(View view:views())if(text.equals(String.valueOf(view.getContentDescription()))){runOnMainSync(view::performClick);SystemClock.sleep(500);return;}throw new AssertionError("Missing control "+text);}
    private void require(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    private View decor(){return activity.getWindow().getDecorView();}
    private void walk(View view,List<View> list){list.add(view);if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)walk(group.getChildAt(i),list);}}
    private List<View> views(){List<View> list=new ArrayList<>();runOnMainSync(()->walk(decor(),list));return list;}
    private View find(String text){for(View view:views())if(view instanceof TextView&&((TextView)view).getText().toString().equals(text))return view;return null;}
    private View findPrefix(String prefix){for(View view:views())if(view instanceof TextView&&((TextView)view).getText().toString().startsWith(prefix))return view;return null;}
    private String textStarting(String prefix){View view=findPrefix(prefix);return view instanceof TextView?((TextView)view).getText().toString():"";}
    private String allText(){StringBuilder out=new StringBuilder();for(View view:views())if(view instanceof TextView)out.append(((TextView)view).getText()).append('\n');return out.toString();}
    private void waitText(String text){long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){if(find(text)!=null){SystemClock.sleep(500);return;}SystemClock.sleep(150);}throw new AssertionError("Missing text: "+text+"\n"+allText());}
    private void waitGone(String text){long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){if(find(text)==null)return;SystemClock.sleep(150);}throw new AssertionError("Text still visible: "+text+"\n"+allText());}
    private void waitPrefix(String prefix){long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){if(findPrefix(prefix)!=null){SystemClock.sleep(500);return;}SystemClock.sleep(150);}throw new AssertionError("Missing prefix: "+prefix+"\n"+allText());}
    private void click(String text){View target=find(text);require(target!=null,"Missing action "+text);runOnMainSync(()->{target.requestRectangleOnScreen(new Rect(0,0,target.getWidth(),target.getHeight()),true);View click=target;while(!click.isClickable()&&click.getParent() instanceof View)click=(View)click.getParent();require(click.isClickable(),"Not clickable: "+text);click.performClick();});SystemClock.sleep(450);}
    private void clickPrefix(String prefix){View target=findPrefix(prefix);require(target!=null,"Missing action "+prefix);click(((TextView)target).getText().toString());}
    private List<EditText> editors(){List<EditText> result=new ArrayList<>();for(View view:views())if(view instanceof EditText)result.add((EditText)view);return result;}
    private void fill(String... values){List<EditText> fields=editors();require(fields.size()==values.length,"Unexpected field count "+fields.size());runOnMainSync(()->{for(int i=0;i<values.length;i++)fields.get(i).setText(values[i]);});}
    private void top(){List<View> all=views();runOnMainSync(()->{for(View view:all)if(view instanceof ScrollView)((ScrollView)view).scrollTo(0,0);});SystemClock.sleep(400);}
    private void shot(String name)throws Exception{waitForIdleSync();SystemClock.sleep(700);Bitmap bitmap=getUiAutomation().takeScreenshot();require(bitmap!=null,"Screenshot unavailable");File dir=new File(getTargetContext().getExternalFilesDir(null),"design-qa");require(dir.isDirectory()||dir.mkdirs(),"Cannot create screenshot directory");try(FileOutputStream file=new FileOutputStream(new File(dir,name+".png"))){bitmap.compress(Bitmap.CompressFormat.PNG,100,file);}bitmap.recycle();}
}
