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
            click("Черновики");require(find("Сайт для студии Север")==null,"Draft filter must exclude sent quotes");click("Все · 3");
            click("Создать");waitText("Новая смета");fill("Дизайн мобильного приложения","Студия Север","98000","Аналитика, прототип и дизайн ключевых экранов.");
            top();shot("03-editor");click("Сохранить на устройстве");click("Сметы");waitText("Все · 3");click("Создать");
            require(editors().get(0).getText().toString().equals("Дизайн мобильного приложения"),"Local draft restored");click("Создать смету");waitText("Все · 4");
            click("Клиенты");waitText("Студия Север");shot("04-clients");
            click("Добавить клиента");fill("Михаил Орлов","mikhail@example.org","+79000000001");click("Добавить клиента");waitText("Михаил Орлов");
            click("Заказы");waitText("Интерьер студии");click("Интерьер студии");waitText("Записать оплату");shot("05-project");
            click("Записать оплату");fill("15000");shot("06-payment");click("Сохранить оплату");waitText("Записать оплату");require(allText().replace('\u00a0',' ').contains("80 000,00"),"Payment total must update");
            click("Завершить заказ");SystemClock.sleep(600);shot("07-confirmation");getUiAutomation().performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK);SystemClock.sleep(400);
            require(find("Завершить заказ")!=null,"Dismiss confirmation without changing project");
            clickDescription("Назад");clickDescription("Открыть профиль");waitText("Ваше пространство");shot("08-profile");click("Поддержка");waitText("Отправить сообщение");shot("09-support");clickDescription("Назад");click("Тариф и подписка");shot("10-subscription");click("Ассистент");waitText("Отправить");shot("11-assistant");
            result.putString("stream","PASS: login, filters, draft restore, create quote/client, project/payment, custom sheet, navigation; screenshots in files/design-qa\n");
            finish(Activity.RESULT_OK,result);
        }catch(Throwable error){result.putString("stream","FAIL: "+android.util.Log.getStackTraceString(error));finish(Activity.RESULT_CANCELED,result);}
    }
    private void clickDescription(String text){for(View view:views())if(text.equals(String.valueOf(view.getContentDescription()))){runOnMainSync(view::performClick);SystemClock.sleep(500);return;}throw new AssertionError("Missing control "+text);}
    private void require(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    private View decor(){return activity.getWindow().getDecorView();}
    private void walk(View view,List<View> list){list.add(view);if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)walk(group.getChildAt(i),list);}}
    private List<View> views(){List<View> list=new ArrayList<>();runOnMainSync(()->walk(decor(),list));return list;}
    private View find(String text){for(View view:views())if(view instanceof TextView&&((TextView)view).getText().toString().equals(text))return view;return null;}
    private String allText(){StringBuilder out=new StringBuilder();for(View view:views())if(view instanceof TextView)out.append(((TextView)view).getText()).append('\n');return out.toString();}
    private void waitText(String text){long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){if(find(text)!=null){SystemClock.sleep(500);return;}SystemClock.sleep(150);}throw new AssertionError("Missing text: "+text+"\n"+allText());}
    private void click(String text){View target=find(text);require(target!=null,"Missing action "+text);runOnMainSync(()->{target.requestRectangleOnScreen(new Rect(0,0,target.getWidth(),target.getHeight()),true);View click=target;while(!click.isClickable()&&click.getParent() instanceof View)click=(View)click.getParent();require(click.isClickable(),"Not clickable: "+text);click.performClick();});SystemClock.sleep(450);}
    private List<EditText> editors(){List<EditText> result=new ArrayList<>();for(View view:views())if(view instanceof EditText)result.add((EditText)view);return result;}
    private void fill(String... values){List<EditText> fields=editors();require(fields.size()==values.length,"Unexpected field count "+fields.size());runOnMainSync(()->{for(int i=0;i<values.length;i++)fields.get(i).setText(values[i]);});}
    private void top(){List<View> all=views();runOnMainSync(()->{for(View view:all)if(view instanceof ScrollView)((ScrollView)view).scrollTo(0,0);});SystemClock.sleep(400);}
    private void shot(String name)throws Exception{waitForIdleSync();SystemClock.sleep(700);Bitmap bitmap=getUiAutomation().takeScreenshot();require(bitmap!=null,"Screenshot unavailable");File dir=new File(getTargetContext().getExternalFilesDir(null),"design-qa");require(dir.isDirectory()||dir.mkdirs(),"Cannot create screenshot directory");try(FileOutputStream file=new FileOutputStream(new File(dir,name+".png"))){bitmap.compress(Bitmap.CompressFormat.PNG,100,file);}bitmap.recycle();}
}
