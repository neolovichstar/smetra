package ru.smetra.mobile;

import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.function.BooleanSupplier;
import java.util.function.Consumer;

/** Native quote editing, bounded history and a single recoverable server writer. */
final class QuoteDraftEditor {
    interface Failure { void accept(int status,String message); }
    interface Request { void send(String path,String method,JSONObject body,Consumer<JSONObject> done,Failure fail); }
    private final SmetraUi ui;
    private final SharedPreferences preferences;
    private final Request request;
    private final BooleanSupplier active;
    private final Consumer<JSONObject> finish;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final LinearLayout host,rowsHost,conflict;
    private final TextView status,total;
    private final Button undo,redo,save;
    private final ArrayList<String> history=new ArrayList<>();
    private JSONObject data,quote,pending;
    private final String key;
    private String saved,group="",copyBody="",copyKey=java.util.UUID.randomUUID().toString();
    private long groupAt;
    private int index=0,attempt=0,recoveryRevision=-1;
    private boolean painting=false,busy=false,blocked=false,closed=false,finishing=false;
    private final Runnable scheduled=()->send(false);

    QuoteDraftEditor(SmetraUi ui,LinearLayout host,SharedPreferences preferences,String userId,JSONObject original,
                     Request request,BooleanSupplier active,Consumer<JSONObject> finish)throws Exception {
        this.ui=ui;this.host=host;this.preferences=preferences;this.request=request;this.active=active;this.finish=finish;
        quote=copy(original);data=copy(original);key="quote-edit:"+userId+":"+quote.getString("id");
        JSONArray items=data.optJSONArray("items");if(items==null||items.length()==0){items=new JSONArray().put(new JSONObject().put("line_id",java.util.UUID.randomUUID().toString()).put("name",data.optString("title")).put("quantity","1").put("unit","шт.").put("unit_price",data.optLong("amount_kopecks")));data.put("items",items);}
        saved=payload().toString();history.add(data.toString());
        status=ui.label("Автосохранение включено",12,SmetraUi.BLUE,false);host.addView(status);
        total=ui.label("",22,SmetraUi.INK,true);ui.space(host,12);host.addView(total);
        LinearLayout tools=ui.row();undo=ui.button("Отменить",false,()->travel(-1));redo=ui.button("Повторить",false,()->travel(1));
        tools.addView(undo,new LinearLayout.LayoutParams(0,-2,1));ui.gap(tools,8);tools.addView(redo,new LinearLayout.LayoutParams(0,-2,1));host.addView(tools);
        String local=preferences.getString(key,null);
        if(local!=null){Button recover=ui.button("Восстановить правки с устройства",false,()->restoreLocal());host.addView(recover);}
        conflict=ui.column();conflict.setVisibility(android.view.View.GONE);host.addView(conflict);
        conflict.addView(ui.label("Серверная редакция изменилась. Правки остались на устройстве.",13,SmetraUi.MUTED,false));
        conflict.addView(ui.button("Открыть серверную версию",false,()->request.send("/quotes/"+quote.optString("id"),"GET",null,r->{if(alive())finish.accept(r.optJSONObject("quote"));},(code,error)->state(error))));
        conflict.addView(ui.button("Сохранить правки копией",true,()->saveCopy()));
        rowsHost=ui.column();host.addView(rowsHost);
        save=ui.button("Сохранить и закрыть",true,()->send(true));host.addView(save);
        host.addView(ui.button("Повторить сохранение",false,()->{attempt=0;send(false);}));
        paint();
    }
    private static JSONObject copy(JSONObject value)throws Exception{return new JSONObject(value.toString());}
    private boolean alive(){return !closed&&active.getAsBoolean();}
    private void state(String value){if(alive())status.setText(value);}
    private JSONObject payload()throws Exception{
        JSONObject result=copy(data);JSONArray rows=result.getJSONArray("items");
        for(int n=0;n<rows.length();n++){JSONObject row=rows.getJSONObject(n);
            for(String field:new String[]{"unit_price","cost_price"}){String raw=field+"_text";if(row.has(raw)){row.put(field,new BigDecimal(row.optString(raw).replace(',','.')).movePointRight(2).setScale(0,RoundingMode.UNNECESSARY).longValueExact());row.remove(raw);}}
        }
        result.remove("revision");return result;
    }
    private void persist(){if(!alive())return;try{JSONObject local=new JSONObject().put("quote_revision",blocked&&recoveryRevision>=0?recoveryRevision:quote.optInt("revision")).put("data",data).put("pending",pending==null?JSONObject.NULL:pending);preferences.edit().putString(key,local.toString()).apply();}catch(Exception error){state("Локальное сохранение недоступно");}}
    private void complete(JSONObject value){closed=true;handler.removeCallbacksAndMessages(null);preferences.edit().remove(key).apply();finish.accept(value);}
    private void changed(String field){if(painting||!alive())return;
        String value=data.toString();if(!value.equals(history.get(index))){long now=android.os.SystemClock.elapsedRealtime();
            if(!field.isEmpty()&&field.equals(group)&&now-groupAt<700&&index>0)history.set(index,value);
            else{while(history.size()>index+1)history.remove(history.size()-1);history.add(value);if(history.size()>60)history.remove(0);index=history.size()-1;}
            group=field;groupAt=now;
        }
        undo.setEnabled(index>0);redo.setEnabled(index<history.size()-1);refreshTotal();persist();
        if(!blocked){state("Правки сохранены на устройстве");handler.removeCallbacks(scheduled);handler.postDelayed(scheduled,1800);}
    }
    private void travel(int delta){int next=index+delta;if(next<0||next>=history.size())return;try{index=next;group="";data=new JSONObject(history.get(index));paint();changed("");}catch(Exception error){state("Не удалось восстановить правку");}}
    private EditText field(LinearLayout parent,String label,String value,int type,Consumer<String> update,String group){
        EditText input=ui.field(parent,label,type);input.setText(value);input.setTextSize(14);
        if(type==android.text.InputType.TYPE_CLASS_TEXT){input.setSingleLine(false);input.setMinHeight(ui.dp(48));}
        input.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){}public void afterTextChanged(Editable value){update.accept(value.toString());changed(group);}});return input;
    }
    private void set(JSONObject value,String key,Object field){try{value.put(key,field);}catch(Exception error){state("Проверьте поле");}}
    private void paint(){painting=true;rowsHost.removeAllViews();
        field(rowsHost,"Название",data.optString("title"),1,value->set(data,"title",value),"title");
        field(rowsHost,"Клиент",data.optString("client"),1,value->set(data,"client",value),"client");
        field(rowsHost,"Описание",data.optString("description"),1,value->set(data,"description",value),"description");
        JSONArray items=data.optJSONArray("items");
        for(int n=0;n<items.length();n++){final int position=n;JSONObject item=items.optJSONObject(n);if(item==null)continue;
            ui.section(rowsHost,"Позиция "+(n+1),null);String id=item.optString("line_id",String.valueOf(n));
            LinearLayout actions=ui.row();
            Button up=ui.button("↑",false,()->move(position,-1)),down=ui.button("↓",false,()->move(position,1));
            up.setContentDescription("Переместить позицию вверх");down.setContentDescription("Переместить позицию вниз");up.setEnabled(n>0);down.setEnabled(n<items.length()-1);
            actions.addView(up,new LinearLayout.LayoutParams(0,-2,1));ui.gap(actions,6);actions.addView(down,new LinearLayout.LayoutParams(0,-2,1));ui.gap(actions,6);
            actions.addView(ui.button("Копия",false,()->duplicate(position)),new LinearLayout.LayoutParams(0,-2,2));rowsHost.addView(actions);
            field(rowsHost,"Работа или материал",item.optString("name"),1,value->set(item,"name",value),id+":name");
            field(rowsHost,"Количество",item.optString("quantity","1"),8194,value->set(item,"quantity",value.replace(',','.')),id+":quantity");
            field(rowsHost,"Единица",item.optString("unit","шт."),1,value->set(item,"unit",value),id+":unit");
            String currency=data.optString("currency","RUB");
            field(rowsHost,"Цена, "+currency,item.optString("unit_price_text",BigDecimal.valueOf(item.optLong("unit_price"),2).toPlainString()),8194,value->set(item,"unit_price_text",value),id+":price");
            field(rowsHost,"Себестоимость, "+currency,item.optString("cost_price_text",BigDecimal.valueOf(item.optLong("cost_price"),2).toPlainString()),8194,value->set(item,"cost_price_text",value),id+":cost");
            CheckBox optional=new CheckBox(ui.activity);optional.setText("Дополнительная позиция");optional.setTextColor(SmetraUi.INK);optional.setButtonTintList(android.content.res.ColorStateList.valueOf(SmetraUi.BLUE));optional.setChecked(item.optBoolean("optional"));optional.setOnCheckedChangeListener((v,checked)->{set(item,"optional",checked);if(!checked)set(item,"included",true);changed("");paint();});rowsHost.addView(optional);
            if(item.optBoolean("optional")){CheckBox included=new CheckBox(ui.activity);included.setText("Включена в итог");included.setTextColor(SmetraUi.INK);included.setButtonTintList(android.content.res.ColorStateList.valueOf(SmetraUi.BLUE));included.setChecked(item.optBoolean("included",true));included.setOnCheckedChangeListener((v,checked)->{set(item,"included",checked);changed("");});rowsHost.addView(included);}
            Button remove=ui.button("Удалить позицию",false,()->{if(items.length()<=1){state("Оставьте хотя бы одну позицию");return;}items.remove(position);changed("");paint();});rowsHost.addView(remove);
        }
        rowsHost.addView(ui.button("Добавить позицию",false,()->{if(items.length()>=200){state("До 200 позиций в смете");return;}try{items.put(new JSONObject().put("line_id",java.util.UUID.randomUUID().toString()).put("name","").put("quantity","1").put("unit","шт.").put("unit_price",0));changed("");paint();}catch(Exception error){state("Не удалось добавить позицию");}}));
        field(rowsHost,"Условия",data.optString("terms"),1,value->set(data,"terms",value),"terms");
        field(rowsHost,"Срок · ГГГГ-ММ-ДД",data.optString("due_date"),1,value->set(data,"due_date",value),"due_date");
        undo.setEnabled(index>0);redo.setEnabled(index<history.size()-1);painting=false;refreshTotal();
    }
    private void refreshTotal(){try{JSONArray items=payload().getJSONArray("items");long sum=0;BigDecimal hundred=new BigDecimal("100");
        for(int n=0;n<items.length();n++){JSONObject row=items.getJSONObject(n);if(row.optBoolean("optional")&&!row.optBoolean("included",true))continue;
            BigDecimal quantity=new BigDecimal(row.optString("quantity","1")),coefficient=new BigDecimal(row.optString("coefficient","1")),markup=new BigDecimal(row.optString("markup","0")),discount=new BigDecimal(row.optString("discount","0")),tax=new BigDecimal(row.optString("tax","0"));
            if(quantity.signum()<=0||coefficient.signum()<=0||discount.signum()<0||discount.compareTo(hundred)>0||tax.signum()<0||tax.compareTo(hundred)>0)throw new IllegalArgumentException();
            BigDecimal base=quantity.multiply(BigDecimal.valueOf(row.optLong("unit_price"))).multiply(coefficient).multiply(BigDecimal.ONE.add(markup.divide(hundred))).multiply(BigDecimal.ONE.subtract(discount.divide(hundred))).setScale(0,RoundingMode.HALF_UP);
            sum=Math.addExact(sum,base.add(base.multiply(tax).divide(hundred).setScale(0,RoundingMode.HALF_UP)).longValueExact());
        }
        java.text.NumberFormat format=java.text.NumberFormat.getCurrencyInstance(new java.util.Locale("ru","RU"));format.setCurrency(java.util.Currency.getInstance(data.optString("currency","RUB")));total.setText(format.format(BigDecimal.valueOf(sum,2)));
    }catch(Exception error){total.setText("Проверьте числовые поля");}}
    private void move(int position,int delta){JSONArray rows=data.optJSONArray("items");int next=position+delta;if(next<0||next>=rows.length())return;try{JSONObject first=rows.getJSONObject(position);rows.put(position,rows.getJSONObject(next));rows.put(next,first);changed("");paint();}catch(Exception error){state("Не удалось переместить позицию");}}
    private void duplicate(int position){JSONArray rows=data.optJSONArray("items");if(rows.length()>=200)return;try{JSONObject added=copy(rows.getJSONObject(position));added.put("line_id",java.util.UUID.randomUUID().toString());JSONArray next=new JSONArray();for(int i=0;i<rows.length();i++){next.put(rows.getJSONObject(i));if(i==position)next.put(added);}data.put("items",next);changed("");paint();}catch(Exception error){state("Не удалось скопировать позицию");}}
    private void restoreLocal(){if(busy){state("Дождитесь текущего сохранения");return;}try{JSONObject local=new JSONObject(preferences.getString(key,"{}"));data=local.getJSONObject("data");pending=local.optJSONObject("pending");int revision=local.optInt("quote_revision");recoveryRevision=revision;blocked=revision!=quote.optInt("revision")&&!(pending!=null&&revision==quote.optInt("revision")-1);history.clear();history.add(data.toString());index=0;paint();if(blocked){conflict.setVisibility(android.view.View.VISIBLE);state("Конфликт редакций. Можно сохранить копию.");}else changed("");}catch(Exception error){state("Не удалось прочитать локальный черновик");}}
    private void send(boolean close){handler.removeCallbacks(scheduled);if(!alive()||blocked)return;if(busy){finishing|=close;return;}finishing|=close;
        try{
            if(pending==null){JSONObject body=payload();if(data.optString("title").trim().isEmpty()||data.optString("client").trim().isEmpty())throw new IllegalArgumentException();for(int i=0;i<body.getJSONArray("items").length();i++){JSONObject row=body.getJSONArray("items").getJSONObject(i);if(row.optString("name").trim().isEmpty()||new BigDecimal(row.optString("quantity")).signum()<=0)throw new IllegalArgumentException();}
                if(body.toString().equals(saved)){state("Сохранено");if(finishing)complete(quote);return;}
                pending=new JSONObject().put("body",body).put("fingerprint",body.toString());body.put("revision",quote.optInt("revision"));persist();
            }
            JSONObject captured=copy(pending);busy=true;save.setEnabled(false);state("Сохраняем…");
            request.send("/quotes/"+quote.optString("id")+"/autosave","PATCH",captured.getJSONObject("body"),result->{if(!alive())return;busy=false;save.setEnabled(true);JSONObject value=result.optJSONObject("quote");if(value==null){state("Не удалось прочитать сохранённую смету");return;}quote=value;saved=captured.optString("fingerprint");pending=null;attempt=0;persist();try{if(!payload().toString().equals(saved)){state("Есть новые правки");handler.postDelayed(scheduled,finishing?0:1800);}else{state("Сохранено");if(finishing)complete(quote);}}catch(Exception error){state("Заполните поля. Правки на устройстве");}},(code,error)->{if(!alive())return;busy=false;save.setEnabled(true);if(code==409){blocked=true;conflict.setVisibility(android.view.View.VISIBLE);state("Конфликт редакций. Ваши правки сохранены.");}else if(code==400){pending=null;state(error);}else if(code==401||code==403||code==402){blocked=true;state(error);}else{state("Нет связи. Правки на устройстве.");if(attempt<3)handler.postDelayed(scheduled,new long[]{4000,10000,30000}[attempt++]);}finishing=false;persist();});
        }catch(Exception error){finishing=false;state("Заполните обязательные поля. Правки на устройстве.");persist();}
    }
    private void saveCopy(){try{JSONObject body;if(copyBody.isEmpty()){body=payload();body.remove("id");body.put("title",data.optString("title").substring(0,Math.min(110,data.optString("title").length()))+" — копия");copyBody=body.toString();}else body=new JSONObject(copyBody);body.put("_request_key",copyKey);request.send("/quotes","POST",body,result->{if(alive())complete(result.optJSONObject("quote"));},(code,error)->state(error));}catch(Exception error){state("Проверьте поля перед сохранением копии");}}
    void resume(){if(alive()){attempt=0;handler.removeCallbacks(scheduled);handler.postDelayed(scheduled,1800);}}
    void close(){persist();closed=true;handler.removeCallbacksAndMessages(null);}
}
