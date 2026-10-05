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
    private Bundle arguments=new Bundle();
    private boolean assistantOnly;
    private boolean interfaceOnly;
    private boolean jobsOnly;
    private boolean attachmentsOnly;
    private boolean receiptsOnly;
    private boolean scansOnly;
    private boolean mixedScan;
    private boolean structureOnly;
    @Override public void onCreate(Bundle args){super.onCreate(args);arguments=args==null?new Bundle():args;assistantOnly=args!=null&&"true".equals(args.getString("assistantOnly"));jobsOnly=args!=null&&"true".equals(args.getString("jobsOnly"));attachmentsOnly=args!=null&&"true".equals(args.getString("attachmentsOnly"));receiptsOnly=args!=null&&"true".equals(args.getString("receiptsOnly"));scansOnly=args!=null&&"true".equals(args.getString("scansOnly"));mixedScan=args!=null&&"true".equals(args.getString("mixedScan"));structureOnly=args!=null&&"true".equals(args.getString("structureOnly"));start();}
    @Override public void onStart(){
        Bundle result=new Bundle();
        try{
            activity=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            waitText("Войти по почте");SystemClock.sleep(700);shot("01-welcome");click("Войти по почте");waitText("Войти в пространство");shot("01-login");
            fill("android-design@test.invalid","android design test only");click("Войти в пространство");
            waitText("Айдентика и упаковка");shot("02-overview");
            if("true".equals(arguments.getString("resourcesOnly"))){
                click("Ещё");click("Ассистент");waitText("Предпросмотр PDF");waitText("Документ");shot("31-document-preview");
                click("Применить");waitText("Скачать PDF");waitText("Отменить изменение");shot("32-document-created");
                click("Сегодня");waitText("Айдентика и упаковка");click("Ещё");click("Ассистент");waitText("Скачать PDF");
                click("Отменить изменение");waitPrefix("Изменение отменено");require(find("Скачать PDF")==null,"Removed draft has no download control");
                waitEnabledPrefix("Отправить");fill("Переименуй тестовый файл");clickPrefix("Отправить");waitText("Сроки проекта.md");shot("33-file-name-preview");
                click("Применить");waitText("Отменить изменение");click("Отменить изменение");waitPrefix("Изменение отменено");
                waitEnabledPrefix("Отправить");fill("Перенеси тестовый файл");clickPrefix("Отправить");waitText("Привязка");shot("34-file-move-preview");
                click("Применить");waitText("Отменить изменение");click("Отменить изменение");waitPrefix("Изменение отменено");
                result.putString("status","PASS: native document preview/apply/persistent download/undo and file rename/move previews with confirmation/undo");finish(Activity.RESULT_OK,result);return;
            }
            interfaceOnly="true".equals(arguments.getString("interfaceOnly"));
            if(interfaceOnly){
                click("Создать");waitSheetText("Создать в Сметре");shot("27-create-sheet");getUiAutomation().performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK);SystemClock.sleep(500);require(find("Айдентика и упаковка")!=null,"Sheet back preserves page");
                click("Ещё");click("Ассистент");waitEnabledPrefix("Отправить");waitText("Итого по смете");
                View send=findPrefix("Отправить"),dock=findTag("assistant-composer");require(send!=null&&dock!=null,"Accessible composer and send exist");
                require(send.getWidth()>=48*activity.getResources().getDisplayMetrics().density-1&&send.getHeight()>=48*activity.getResources().getDisplayMetrics().density-1,"Send touch target is at least 48dp");
                int[] before=new int[2];runOnMainSync(()->dock.getLocationOnScreen(before));
                runOnMainSync(()->{for(View view:viewsOnMain())if(view instanceof ScrollView)((ScrollView)view).scrollTo(0,10000);});SystemClock.sleep(400);int[] after=new int[2];runOnMainSync(()->dock.getLocationOnScreen(after));require(before[1]==after[1],"Composer does not scroll with history");shot("28-assistant-composer");
                EditText input=editors().get(0);touch(input);SystemClock.sleep(1200);
                if(android.os.Build.VERSION.SDK_INT>=30)require(decor().getRootWindowInsets().isVisible(android.view.WindowInsets.Type.ime()),"Software keyboard actually opened");
                Rect visible=new Rect();runOnMainSync(()->decor().getWindowVisibleDisplayFrame(visible));int[] keyboardPos=new int[2];runOnMainSync(()->dock.getLocationOnScreen(keyboardPos));require(keyboardPos[1]+dock.getHeight()<=visible.bottom+2,"Composer stays above keyboard");shot("29-assistant-keyboard");
                fill("Покажи контекст");clickPrefix("Отправить");waitText("Контекст не выбран.");require(editors().get(0).getText().length()==0,"Successful send clears draft");require(editors().get(0).isEnabled(),"Input restored after streaming");shot("30-assistant-answer");
                result.putString("stream","PASS: native animated sheet/back, 48dp send icon, pinned composer, keyboard insets, streamed answer and input restoration\n");finish(Activity.RESULT_OK,result);return;
            }
            if(structureOnly){
                click("Ещё");click("Ассистент");waitPrefix("Добавить позиции · ");waitText("Добавить · Подготовка стен");waitText("Позиций: 1 → 2");waitPrefix("Станет: Строка 2");shot("24-structure-preview");click("Применить");waitText("Отменить изменение");shot("25-structure-applied");click("Отменить изменение");waitPrefix("Изменение отменено · ");shot("26-structure-undone");
                result.putString("stream","PASS: native quote structure preview, position/quantity/money/count, explicit application and undo\n");finish(Activity.RESULT_OK,result);return;
            }
            if(scansOnly){
                click("Ещё");click("Ассистент");waitEnabledPrefix("Отправить");fill("Прочитай скан");pickFixture(mixedScan?"mixed.pdf":"scan.pdf");waitText("Прикрепить к диалогу");click("Прикрепить к диалогу");waitText("Распознать скан");
                if(mixedScan)waitText("Без текста: стр. 2");
                require(editors().get(0).getText().toString().equals("Прочитай скан"),"Scan preparation preserves draft");require(!findPrefix("Отправить").isEnabled(),"Unread scan cannot spend chat quota");click("Распознать скан");
                click("Сегодня");waitPrefix("Все · ");click("Ещё");click("Ассистент");waitText("Текст получен OCR. Проверьте суммы по оригиналу.");waitEnabledPrefix("Отправить");
                if(mixedScan)waitText("Текст готов · 3 стр.");
                require(editors().get(0).getText().toString().equals("Прочитай скан"),"OCR navigation preserves draft");waitText("OCR: 1 из 3 в месяц · первые 2 страницы");shot("23-scan-ocr-ready");clickPrefix("Отправить");waitText("Контекст файла получен.");
                result.putString("stream","PASS: native scanned PDF attachment, blocked unread input, background OCR, navigation, preserved draft, OCR quota/provenance and streamed file context\n");finish(Activity.RESULT_OK,result);return;
            }
            if(receiptsOnly){
                click("Ещё");click("Объекты и замеры");waitText("Проверка чека");click("Проверка чека");waitPrefix("2026-10-01 · ");clickPrefix("2026-10-01 · ");waitText("Распознать фото чека");click("Распознать фото чека");
                click("Ещё");click("Объекты и замеры");waitText("Проверка чека");click("Проверка чека");waitPrefix("2026-10-01 · ");clickPrefix("2026-10-01 · ");waitText("Проверить данные чека");waitText("1 из 3 чеков в месяц");shot("21-receipt-draft");
                require(find("Сохранённое примечание")!=null,"OCR does not change saved purchase");click("Проверить данные чека");clickSheetAction("Перенести в форму");waitText("Сохранить закупку");
                boolean preserved=false;for(EditText editor:editors())if(editor.getText().toString().contains("Сохранённое примечание · Тестовый магазин"))preserved=true;
                require(preserved,"Receipt proposal preserves existing purchase notes");shot("22-receipt-review");
                result.putString("stream","PASS: native receipt background job, navigation, saved draft, one monthly recognition, no automatic purchase mutation and explicit review preserving notes\n");finish(Activity.RESULT_OK,result);return;
            }
            if("true".equals(arguments.getString("officeOnly"))){
                click("Ещё");click("Файлы");waitText("brief.docx");shot("35-office-files");click("brief.docx");waitText("Техническое задание");shot("36-docx-preview");fill("Покраска");waitPrefix("Покраска");require(find("Техническое задание")==null,"DOCX search filters unrelated text");
                runOnMainSync(()->activity.onBackPressed());waitText("prices.xlsx");click("prices.xlsx");waitPrefix("3 строк");waitText("Формула (не рассчитана): =SUM(B2:B3)");click("B");waitText("B ↑");click("Работы");waitSheetText("Материалы");clickSheetAction("Материалы");waitText("Краска");click("Материалы");waitSheetText("Работы");clickSheetAction("Работы");waitPrefix("3 строк");shot("37-xlsx-preview");fill("Доставка");waitPrefix("1 строк");require(find("Покраска")==null,"XLSX search filters other rows");click("Шире");waitText("Доставка");
                runOnMainSync(()->activity.onBackPressed());waitText("prices.csv");click("prices.csv");waitText("Покраска");shot("38-csv-preview");click("Спросить ассистента");waitText("Файл · prices.csv");waitEnabledPrefix("Отправить");
                result.putString("stream","PASS: native office file center, DOCX text/table/search, XLSX formula text/search/width, CSV preview and assistant context\n");finish(Activity.RESULT_OK,result);return;
            }
            if(attachmentsOnly){
                click("Ещё");click("Ассистент");waitEnabledPrefix("Отправить");fill("Прочитай документ");
                pickFixture(null);require(editors().get(0).getText().toString().equals("Прочитай документ"),"Cancelled picker preserves draft");
                for(String name:new String[]{"empty.txt","binary.txt","large.pdf","wrong.exe"}){
                    pickFixture(name);waitText("Вернуться в диалог");click("Вернуться в диалог");waitEnabledPrefix("Отправить");
                    require(editors().get(0).getText().toString().equals("Прочитай документ"),"Rejected attachment preserves draft: "+name);
                }
                for(String name:new String[]{"brief.md","note.txt","brief.pdf","large-text.txt"}){
                    pickFixture(name);waitText("Прикрепить к диалогу");waitText(name);shot("20-attachment-"+name.replace('.','-'));
                    if("note.txt".equals(name)){
                        ActivityMonitor recreation=addMonitor(MainActivity.class.getName(),null,false);
                        runOnMainSync(()->activity.recreate());Activity restored=waitForMonitorWithTimeout(recreation,15000);removeMonitor(recreation);
                        require(restored!=null,"Attachment preview recreated");activity=restored;waitText("Прикрепить к диалогу");waitText(name);
                    }
                    click("Прикрепить к диалогу");
                    if("brief.md".equals(name)){
                        waitText("Повторить загрузку");
                        ActivityMonitor recreation=addMonitor(MainActivity.class.getName(),null,false);
                        runOnMainSync(()->activity.recreate());Activity restored=waitForMonitorWithTimeout(recreation,15000);removeMonitor(recreation);
                        require(restored!=null,"Lost upload response recreated");activity=restored;waitText("Прикрепить к диалогу");click("Прикрепить к диалогу");
                        waitText("Связать с диалогом");click("Связать с диалогом");
                    }
                    waitText("Файл · "+name,"large-text.txt".equals(name)?70000:15000);waitEnabledPrefix("Отправить");
                    if("large-text.txt".equals(name)){waitPrefix("Текст готов");waitPrefix("2 из 3");shot("20-large-document-ready");}
                    require(editors().get(0).getText().toString().equals("Прочитай документ"),"Attachment preserves draft: "+name);
                }
                click("Ещё");click("Ассистент");waitText("Файл · large-text.txt");waitEnabledPrefix("Отправить");
                require(editors().get(0).getText().toString().equals("Прочитай документ"),"Navigation preserves draft and context");
                clickPrefix("Отправить");waitText("Контекст файла получен.");shot("21-attachment-answer");
                result.putString("stream","PASS: picker cancellation, invalid rejection, PDF/TXT/MD upload, 2.1MB background preparation without consuming quota, preserved draft/navigation, streamed file response\n");finish(Activity.RESULT_OK,result);return;
            }
            if(jobsOnly){
                click("Ещё");click("Ассистент");waitEnabledPrefix("Отправить");
                click("Диалоги");click("Новый диалог");waitText("Создать диалог");fill("Фоновая проверка");click("Создать диалог");waitDescription("Настройки диалога");waitEnabledPrefix("Отправить");
                fill("Проверь рабочие данные в фоне");click("Выполнить в фоне");waitText("Задачи ассистента");
                click("Ещё");click("Ассистент");waitText("Фоновая проверка");click("Фоновые задачи");waitText("Открыть ответ");shot("18-assistant-jobs");
                click("Открыть ответ");waitText("Фоновая проверка");waitText("Фоновая задача завершена.");shot("19-assistant-job-result");
                result.putString("stream","PASS: native background enqueue, leaving screen, persisted completion and opening original conversation\n");finish(Activity.RESULT_OK,result);return;
            }
            if(assistantOnly){click("Ещё");click("Ассистент");waitPrefix("Отправить");checkAssistantThreads("Айдентика и упаковка");result.putString("stream","PASS: native conversations, rename/pin, context, streamed response, fork, clear, monthly quota and history isolation\n");finish(Activity.RESULT_OK,result);return;}
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
            clickDescription("Назад");clickDescription("Открыть профиль");waitText("Ваше пространство");shot("08-profile");click("Поддержка");waitText("Отправить сообщение");shot("09-support");clickDescription("Назад");click("Тариф и подписка");require(find("Выбрать Про · 490 ₽")==null,"Android must not open external subscription checkout");shot("10-subscription");click("Ещё");click("Ассистент");waitPrefix("Отправить");waitText("Итого по смете");shot("11-assistant-diff");click("Применить");waitText("Отменить изменение");shot("11-assistant-applied");click("Ещё");click("Ассистент");waitText("Отменить изменение");click("Отменить изменение");waitPrefix("Изменение отменено");shot("11-assistant-undone");
            checkAssistantThreads("Ремонт квартиры");
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
    private View findTag(String tag){for(View view:views())if(tag.equals(view.getTag()))return view;return null;}
    private List<View> viewsOnMain(){List<View> list=new ArrayList<>();walk(decor(),list);return list;}
    private void waitSheetText(String text){long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){android.view.accessibility.AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();if(root!=null&&!root.findAccessibilityNodeInfosByText(text).isEmpty()){SystemClock.sleep(400);return;}SystemClock.sleep(150);}throw new AssertionError("Missing sheet "+text);}
    private void pickFixture(String name){
        Intent data=name==null?null:new Intent().setData(android.net.Uri.parse("content://ru.smetra.mobile.test.documents/"+name)).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        android.content.IntentFilter filter=new android.content.IntentFilter(Intent.ACTION_OPEN_DOCUMENT);
        filter.addCategory(Intent.CATEGORY_OPENABLE);try{filter.addDataType("*/*");}catch(android.content.IntentFilter.MalformedMimeTypeException error){throw new AssertionError(error);}
        ActivityMonitor monitor=new ActivityMonitor(filter,new ActivityResult(name==null?Activity.RESULT_CANCELED:Activity.RESULT_OK,data),true);
        addMonitor(monitor);click("Прикрепить файл · PDF, TXT, MD");SystemClock.sleep(600);require(monitor.getHits()==1,"Document picker launched");removeMonitor(monitor);
    }
    private void checkAssistantThreads(String quoteTitle)throws Exception{
            click("Диалоги");waitText("Новый диалог");click("Новый диалог");waitText("Создать диалог");fill("План работ");click("Создать диалог");waitDescription("Настройки диалога");waitText("План работ");clickDescription("Настройки диалога");waitText("Сохранить название");fill("План недели");click("Сохранить название");waitDescription("Настройки диалога");waitText("План недели");clickDescription("Настройки диалога");waitText("Закрепить диалог");click("Закрепить диалог");waitDescription("Настройки диалога");waitText("План недели");shot("16-assistant-thread");
            click("Диалоги");waitText("Общий диалог");waitText("План недели");click("Общий диалог");waitText("Общий диалог");
            click("Сегодня");waitText(""+quoteTitle+"");click(""+quoteTitle+"");waitText("Спросить ассистента");click("Спросить ассистента");waitText("Смета · "+quoteTitle+"");waitEnabledPrefix("Отправить");fill("Покажи контекст");clickPrefix("Отправить");waitText("Контекст сметы получен.");
            click("Ещё");click("Ассистент");waitText("Смета · "+quoteTitle+"");waitText("Контекст сметы получен.");click("Продолжить в новой ветке");waitPrefix("Ветка · "+quoteTitle+"");waitText("Контекст сметы получен.");shot("17-assistant-context");
            click("Убрать контекст");waitGone("Убрать контекст");waitEnabledPrefix("Отправить");fill("Теперь без контекста");clickPrefix("Отправить");waitText("Контекст не выбран.");waitText("Лимит на месяц исчерпан");shot("18-assistant-limit");
            clickDescription("Настройки диалога");waitText("Удалить диалог");click("Удалить диалог");clickSheetAction("Удалить");waitText("Общий диалог");require(find("Контекст не выбран.")==null,"Thread messages must not leak into global history");
            click("Диалоги");waitText("Бриф проекта");click("Бриф проекта");waitText("Файл · brief.txt");shot("19-assistant-file-context");
    }
    private void waitDescription(String text){long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){for(View view:views())if(text.equals(String.valueOf(view.getContentDescription()))){SystemClock.sleep(500);return;}SystemClock.sleep(150);}throw new AssertionError("Missing accessible control "+text);}
    private void clickDescription(String text){for(View view:views())if(text.equals(String.valueOf(view.getContentDescription()))){runOnMainSync(view::performClick);SystemClock.sleep(500);return;}throw new AssertionError("Missing control "+text);}
    private void clickSheetAction(String text){long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){android.view.accessibility.AccessibilityNodeInfo root=getUiAutomation().getRootInActiveWindow();if(root!=null)for(android.view.accessibility.AccessibilityNodeInfo node:root.findAccessibilityNodeInfosByText(text)){if(text.equals(String.valueOf(node.getText()))&&node.isClickable()&&node.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK)){SystemClock.sleep(500);return;}}SystemClock.sleep(150);}throw new AssertionError("Missing sheet action "+text);}
    private void require(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    private View decor(){return activity.getWindow().getDecorView();}
    private void walk(View view,List<View> list){list.add(view);if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++)walk(group.getChildAt(i),list);}}
    private List<View> views(){List<View> list=new ArrayList<>();runOnMainSync(()->walk(decor(),list));return list;}
    private View find(String text){for(View view:views())if(view instanceof TextView&&((TextView)view).getText().toString().equals(text))return view;for(View view:views())if(text.equals(String.valueOf(view.getContentDescription())))return view;return null;}
    private View findPrefix(String prefix){if(prefix.equals("Отправить")){View send=findTag("assistant-send");if(send!=null)return send;}for(View view:views())if(view instanceof TextView&&((TextView)view).getText().toString().startsWith(prefix))return view;return null;}
    private String textStarting(String prefix){View view=findPrefix(prefix);return view instanceof TextView?((TextView)view).getText().toString():"";}
    private String allText(){StringBuilder out=new StringBuilder();for(View view:views())if(view instanceof TextView)out.append(((TextView)view).getText()).append('\n');return out.toString();}
    private void waitText(String text){waitText(text,15000);}
    private void waitText(String text,long timeout){long until=SystemClock.uptimeMillis()+timeout;while(SystemClock.uptimeMillis()<until){if(find(text)!=null){SystemClock.sleep(500);return;}SystemClock.sleep(150);}throw new AssertionError("Missing text: "+text+"\n"+allText());}
    private void waitGone(String text){long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){if(find(text)==null)return;SystemClock.sleep(150);}throw new AssertionError("Text still visible: "+text+"\n"+allText());}
    private void waitPrefix(String prefix){long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){if(findPrefix(prefix)!=null){SystemClock.sleep(500);return;}SystemClock.sleep(150);}throw new AssertionError("Missing prefix: "+prefix+"\n"+allText());}
    private void waitEnabledPrefix(String prefix){long until=SystemClock.uptimeMillis()+15000;while(SystemClock.uptimeMillis()<until){View view=findPrefix(prefix);if(view!=null&&view.isEnabled()){SystemClock.sleep(500);return;}SystemClock.sleep(150);}throw new AssertionError("Control not ready: "+prefix);}
    private void click(String text){View target=find(text);require(target!=null,"Missing action "+text);clickTarget(target);}
    private void clickTarget(View target){runOnMainSync(()->{target.requestRectangleOnScreen(new Rect(0,0,target.getWidth(),target.getHeight()),true);View click=target;while(!click.isClickable()&&click.getParent() instanceof View)click=(View)click.getParent();require(click.isClickable(),"Not clickable: "+target.getContentDescription());click.performClick();});SystemClock.sleep(450);}
    private void touch(View target){int[] point=new int[2];runOnMainSync(()->target.getLocationOnScreen(point));long time=SystemClock.uptimeMillis();float x=point[0]+target.getWidth()/2f,y=point[1]+target.getHeight()/2f;android.view.MotionEvent down=android.view.MotionEvent.obtain(time,time,android.view.MotionEvent.ACTION_DOWN,x,y,0),up=android.view.MotionEvent.obtain(time,time+80,android.view.MotionEvent.ACTION_UP,x,y,0);try{require(getUiAutomation().injectInputEvent(down,true)&&getUiAutomation().injectInputEvent(up,true),"Touch injected");}finally{down.recycle();up.recycle();}}
    private void clickPrefix(String prefix){View target=findPrefix(prefix);require(target!=null,"Missing action "+prefix);clickTarget(target);}
    private List<EditText> editors(){List<EditText> result=new ArrayList<>();for(View view:views())if(view instanceof EditText)result.add((EditText)view);return result;}
    private void fill(String... values){List<EditText> fields=editors();require(fields.size()==values.length,"Unexpected field count "+fields.size());runOnMainSync(()->{for(int i=0;i<values.length;i++)fields.get(i).setText(values[i]);});}
    private void top(){List<View> all=views();runOnMainSync(()->{for(View view:all)if(view instanceof ScrollView)((ScrollView)view).scrollTo(0,0);});SystemClock.sleep(400);}
    private void shot(String name)throws Exception{waitForIdleSync();SystemClock.sleep(700);Bitmap bitmap=getUiAutomation().takeScreenshot();require(bitmap!=null,"Screenshot unavailable");File dir=new File(getTargetContext().getExternalFilesDir(null),"design-qa");require(dir.isDirectory()||dir.mkdirs(),"Cannot create screenshot directory");try(FileOutputStream file=new FileOutputStream(new File(dir,name+".png"))){bitmap.compress(Bitmap.CompressFormat.PNG,100,file);}bitmap.recycle();}
}
