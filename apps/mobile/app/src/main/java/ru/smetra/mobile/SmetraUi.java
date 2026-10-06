package ru.smetra.mobile;

import android.animation.ValueAnimator;
import android.app.Activity;
import android.app.Dialog;
import android.content.res.ColorStateList;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.*;
import android.view.animation.PathInterpolator;
import android.widget.*;

/** Small native design system. All geometry is in dp; text respects the device font scale. */
final class SmetraUi {
    static final int BG=Color.BLACK, SURFACE=Color.rgb(8,8,9), RAISED=Color.rgb(17,17,20);
    static final int LINE=Color.rgb(38,38,38), INK=Color.rgb(243,244,246), MUTED=Color.rgb(169,171,179);
    static int BLUE=Color.rgb(150,190,255);
    static final int GREEN=Color.rgb(137,224,191), AMBER=Color.rgb(241,203,140), RED=Color.rgb(255,158,167);
    static final PathInterpolator EASE=new PathInterpolator(.2f,.8f,.2f,1f);
    final Activity activity;
    final Typeface regular, medium, bold;
    SmetraUi(Activity activity) {
        this.activity=activity;
        regular=Typeface.createFromAsset(activity.getAssets(),"fonts/manrope-400.ttf");
        medium=Typeface.createFromAsset(activity.getAssets(),"fonts/manrope-600.ttf");
        bold=Typeface.createFromAsset(activity.getAssets(),"fonts/manrope-800.ttf");
    }
    int dp(float value){return Math.round(value*activity.getResources().getDisplayMetrics().density);}
    boolean motion(){return ValueAnimator.areAnimatorsEnabled();}
    LinearLayout column(){LinearLayout view=new LinearLayout(activity);view.setOrientation(LinearLayout.VERTICAL);return view;}
    LinearLayout row(){LinearLayout view=new LinearLayout(activity);view.setGravity(Gravity.CENTER_VERTICAL);return view;}
    LinearLayout.LayoutParams match(){return new LinearLayout.LayoutParams(-1,-2);}
    void space(LinearLayout parent,int size){parent.addView(new View(activity),new LinearLayout.LayoutParams(1,dp(size)));}
    void gap(LinearLayout parent,int size){parent.addView(new View(activity),new LinearLayout.LayoutParams(dp(size),1));}
    TextView label(String text,int size,int color,boolean strong){
        TextView view=new TextView(activity);view.setText(text);view.setTextSize(size);view.setTextColor(color);
        view.setTypeface(strong?medium:regular);view.setIncludeFontPadding(false);view.setLineSpacing(dp(3),1);
        return view;
    }
    GradientDrawable shape(int color,int radius,int border){
        GradientDrawable drawable=new GradientDrawable();drawable.setColor(color);drawable.setCornerRadius(dp(radius));
        if(border!=0)drawable.setStroke(dp(1),border);return drawable;
    }
    GradientDrawable gradient(int radius){return shape(BG,0,0);}
    void divider(LinearLayout parent){View line=new View(activity);line.setBackgroundColor(LINE);parent.addView(line,new LinearLayout.LayoutParams(-1,dp(1)));}
    ImageView art(String name,int height){ImageView image=new ImageView(activity);image.setScaleType(ImageView.ScaleType.FIT_CENTER);image.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);image.setLayoutParams(new LinearLayout.LayoutParams(-1,dp(height)));BrandArt.load(image,name.equals("flight")?R.drawable.brand_flight:R.drawable.brand_unfold,activity.getResources().getDisplayMetrics().widthPixels,dp(height));return image;}
    void ripple(View view,int color,int radius,int border){view.setBackground(new RippleDrawable(ColorStateList.valueOf(0x22c4dcff),shape(color,radius,border),shape(Color.WHITE,radius,0)));}
    void tap(View view,Runnable action){
        view.setFocusable(true);view.setOnClickListener(v->{v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);action.run();});
        android.animation.StateListAnimator states=new android.animation.StateListAnimator();
        android.animation.AnimatorSet press=new android.animation.AnimatorSet();
        press.playTogether(android.animation.ObjectAnimator.ofFloat(view,"scaleX",.98f),android.animation.ObjectAnimator.ofFloat(view,"scaleY",.98f));press.setDuration(motion()?100:0);
        android.animation.AnimatorSet release=new android.animation.AnimatorSet();
        release.playTogether(android.animation.ObjectAnimator.ofFloat(view,"scaleX",1f),android.animation.ObjectAnimator.ofFloat(view,"scaleY",1f));release.setDuration(motion()?220:0);release.setInterpolator(EASE);
        states.addState(new int[]{android.R.attr.state_pressed},press);states.addState(new int[]{},release);view.setStateListAnimator(states);
    }
    Button button(String title,boolean primary,Runnable action){
        Button view=new Button(activity){@Override public void setEnabled(boolean enabled){super.setEnabled(enabled);if("assistant-send".equals(getTag()))animate().alpha(enabled?1:.45f).setDuration(motion()?160:0).start();}};view.setText(title);view.setAllCaps(false);view.setTextSize(13);view.setTypeface(medium);
        view.setTextColor(primary?BG:INK);view.setMinHeight(dp(48));view.setMinimumHeight(dp(48));view.setPadding(dp(14),dp(12),dp(14),dp(12));
        view.setStateListAnimator(null);ripple(view,primary?BLUE:BG,10,primary?0xffb9d3ff:LINE);tap(view,action);
        String icon=actionIcon(title);if(icon!=null){
            int size=dp(18);Bitmap bitmap=Bitmap.createBitmap(size,size,Bitmap.Config.ARGB_8888);
            Icon glyph=new Icon(icon,primary?BG:INK);glyph.layout(0,0,size,size);glyph.draw(new Canvas(bitmap));
            BitmapDrawable drawable=new BitmapDrawable(activity.getResources(),bitmap);drawable.setBounds(0,0,size,size);
            view.setCompoundDrawablesRelative(drawable,null,null,null);view.setCompoundDrawablePadding(dp(8));
        }
        LinearLayout.LayoutParams params=match();params.topMargin=dp(8);view.setLayoutParams(params);return view;
    }
    private String actionIcon(String title){
        if(title.startsWith("Создать")||title.startsWith("Добавить")||title.startsWith("Новый")||title.startsWith("Новая"))return "plus";
        if(title.startsWith("Сохранить")||title.startsWith("Применить")||title.startsWith("Подтвердить"))return "check";
        if(title.startsWith("Обновить")||title.startsWith("Повторить"))return "refresh";
        if(title.startsWith("Отправить"))return "send";
        if(title.startsWith("Открыть"))return "arrow";
        if(title.startsWith("Найти")||title.startsWith("Поиск"))return "search";
        if(title.startsWith("Диалоги"))return "chat";
        if(title.startsWith("Фоновые"))return "clock";
        if(title.startsWith("Прикрепить"))return "attachment";
        return null;
    }
    LinearLayout card(LinearLayout parent){
        LinearLayout section=column();section.setPadding(0,dp(16),0,dp(16));LinearLayout.LayoutParams params=match();parent.addView(section,params);divider(parent);return section;
    }
    void enter(View view){enter(view,0);}
    void enter(View view,int delay){if(!motion())return;view.setAlpha(0);view.setTranslationY(dp(10));view.animate().alpha(1).translationY(0).setStartDelay(delay).setDuration(280).setInterpolator(EASE).start();}
    void transitions(ViewGroup group){
        android.animation.LayoutTransition transition=new android.animation.LayoutTransition();
        transition.setDuration(motion()?220:0);transition.setStartDelay(android.animation.LayoutTransition.APPEARING,0);
        transition.setInterpolator(android.animation.LayoutTransition.APPEARING,EASE);
        transition.setInterpolator(android.animation.LayoutTransition.CHANGE_APPEARING,EASE);
        group.setLayoutTransition(transition);
    }
    void pulse(View view){
        if(!motion())return;
        android.animation.ObjectAnimator animator=android.animation.ObjectAnimator.ofFloat(view,"alpha",.35f,.85f);
        animator.setDuration(900);animator.setRepeatCount(ValueAnimator.INFINITE);animator.setRepeatMode(ValueAnimator.REVERSE);
        view.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener(){
            public void onViewAttachedToWindow(View v){animator.start();}
            public void onViewDetachedFromWindow(View v){animator.cancel();}
        });if(view.isAttachedToWindow())animator.start();
    }
    Button glyphButton(String icon,String description,boolean primary,Runnable action){
        Button button=button("",primary,action);button.setTag("glyph-button");button.setContentDescription(description);
        ripple(button,primary?BLUE:Color.TRANSPARENT,primary?16:12,primary?0xffb9d3ff:0);
        button.setPadding(dp(12),dp(12),dp(12),dp(12));button.setGravity(Gravity.CENTER);
        button.setLayoutParams(new LinearLayout.LayoutParams(dp(48),dp(48)));glyph(button,icon,primary?BG:INK);
        button.setOnLongClickListener(v->{Toast.makeText(activity,description,Toast.LENGTH_SHORT).show();return true;});return button;
    }
    void glyph(Button button,String icon,int color){
        int size=dp(24);Bitmap bitmap=Bitmap.createBitmap(size,size,Bitmap.Config.ARGB_8888);
        Icon view=new Icon(icon,color);view.layout(0,0,size,size);view.draw(new Canvas(bitmap));
        BitmapDrawable drawable=new BitmapDrawable(activity.getResources(),bitmap);drawable.setBounds(0,0,size,size);
        button.setCompoundDrawablesRelative(drawable,null,null,null);button.setCompoundDrawablePadding(0);
    }
    TextView badge(String text,int color){TextView view=label(text,11,color,true);view.setPadding(0,dp(3),0,dp(3));view.setBackgroundColor(Color.TRANSPARENT);view.setLayoutParams(new LinearLayout.LayoutParams(-2,-2));return view;}
    EditText field(LinearLayout parent,String label,int type){
        space(parent,16);TextView title=label(label,12,MUTED,false);parent.addView(title);space(parent,8);
        EditText field=new EditText(activity);field.setTextSize(16);field.setTypeface(regular);field.setTextColor(INK);field.setHintTextColor(0xff69768a);
        field.setInputType(type);field.setSingleLine(type!=1);field.setMinHeight(dp(type==1?96:48));field.setGravity(type==1?Gravity.TOP|Gravity.START:Gravity.CENTER_VERTICAL|Gravity.START);
        field.setPadding(dp(14),dp(12),dp(14),dp(12));field.setBackground(shape(SURFACE,10,0));field.setSelectAllOnFocus(false);
        field.setOnFocusChangeListener((v,focused)->{
            android.graphics.drawable.TransitionDrawable transition=new android.graphics.drawable.TransitionDrawable(new android.graphics.drawable.Drawable[]{field.getBackground(),shape(focused?RAISED:SURFACE,10,0)});
            field.setBackground(transition);transition.startTransition(motion()?160:0);
            field.postDelayed(()->{if(field.getBackground()==transition)field.setBackground(shape(focused?RAISED:SURFACE,10,0));},170);
        });
        field.setId(View.generateViewId());title.setLabelFor(field.getId());parent.addView(field,match());return field;
    }
    View iconButton(String icon,String description,Runnable action){
        FrameLayout box=new FrameLayout(activity);box.setContentDescription(description);ripple(box,BG,12,0);
        Icon glyph=new Icon(icon,INK);FrameLayout.LayoutParams ip=new FrameLayout.LayoutParams(dp(22),dp(22),Gravity.CENTER);box.addView(glyph,ip);
        box.setMinimumWidth(dp(48));box.setMinimumHeight(dp(48));tap(box,action);return box;
    }
    void section(LinearLayout parent,String title,String detail){
        space(parent,24);LinearLayout heading=row();heading.addView(label(title,17,INK,true),new LinearLayout.LayoutParams(0,-2,1));
        if(detail!=null)heading.addView(label(detail,12,MUTED,false));parent.addView(heading);space(parent,2);
    }
    void empty(LinearLayout parent,String icon,String title,String description){
        LinearLayout card=card(parent);card.setGravity(Gravity.CENTER);card.setPadding(dp(24),dp(30),dp(24),dp(30));
        Icon glyph=new Icon(icon,BLUE);card.addView(glyph,new LinearLayout.LayoutParams(dp(36),dp(36)));space(card,18);
        TextView name=label(title,17,INK,true);name.setGravity(Gravity.CENTER);card.addView(name);space(card,8);
        TextView copy=label(description,13,MUTED,false);copy.setGravity(Gravity.CENTER);card.addView(copy);
    }
    void sheet(String title,String copy,String action,boolean destructive,Runnable confirm){
        AnimatedSheet dialog=new AnimatedSheet(title);space(dialog.body,12);dialog.body.addView(label(copy,14,MUTED,false));space(dialog.body,16);
        Button yes=button(action,true,()->dialog.close(confirm));if(destructive){ripple(yes,0xff47262d,14,0xff75404a);yes.setTextColor(RED);glyph(yes,"trash",RED);yes.setCompoundDrawablePadding(dp(8));}dialog.body.addView(yes);
        dialog.body.addView(button("Отмена",false,()->dialog.close(null)));dialog.open();
    }
    void choiceSheet(String title,String[] labels,Runnable[] actions){
        if(labels.length!=actions.length)throw new IllegalArgumentException("Choices and actions differ");
        AnimatedSheet dialog=new AnimatedSheet(title);space(dialog.body,12);
        for(int i=0;i<labels.length;i++){
            final int index=i;
            Button option=button(labels[i],i==0,()->dialog.close(actions[index]));dialog.body.addView(option);space(dialog.body,4);
        }
        dialog.open();
    }
    private final class AnimatedSheet extends Dialog {
        final LinearLayout body=column();final ScrollView scroller=new ScrollView(activity);boolean closing;ValueAnimator dimAnimator;
        AnimatedSheet(String title){
            super(activity);body.setPadding(dp(22),dp(12),dp(22),dp(24));body.setBackground(shape(RAISED,26,LINE));
            View handle=new View(activity);handle.setBackground(shape(MUTED,2,0));LinearLayout.LayoutParams hp=new LinearLayout.LayoutParams(dp(32),dp(4));hp.gravity=Gravity.CENTER;body.addView(handle,hp);space(body,16);
            LinearLayout heading=row();heading.addView(label(title,20,INK,true),new LinearLayout.LayoutParams(0,-2,1));heading.addView(iconButton("close","Закрыть",()->close(null)),new LinearLayout.LayoutParams(dp(48),dp(48)));body.addView(heading);
            scroller.setVerticalScrollBarEnabled(false);scroller.setOverScrollMode(View.OVER_SCROLL_NEVER);scroller.addView(body);setContentView(scroller);setCanceledOnTouchOutside(true);
        }
        @Override public void cancel(){close(null);}
        void close(Runnable next){
            if(closing)return;closing=true;body.animate().cancel();Runnable finish=()->{dismiss();if(next!=null&&!activity.isFinishing()&&!activity.isDestroyed())next.run();};
            if(!motion()){finish.run();return;}
            body.animate().translationY(dp(48)).alpha(0).setStartDelay(0).setDuration(190).setInterpolator(EASE).withEndAction(finish).start();
            dim(.56f,0,190);
        }
        void dim(float from,float to,int duration){
            Window window=getWindow();if(window==null)return;if(dimAnimator!=null)dimAnimator.cancel();ValueAnimator fade=ValueAnimator.ofFloat(from,to);dimAnimator=fade;fade.setDuration(duration);fade.addUpdateListener(a->{if(isShowing())window.setDimAmount((float)a.getAnimatedValue());});fade.start();
        }
        void open(){
            Window window=getWindow();if(window!=null){window.setBackgroundDrawableResource(android.R.color.transparent);window.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);window.setDimAmount(motion()?0:.56f);window.setGravity(Gravity.BOTTOM);window.setNavigationBarColor(BG);window.setWindowAnimations(0);}
            show();if(window!=null){window.getDecorView().setPadding(dp(8),dp(8),dp(8),dp(8));window.setLayout(-1,-2);}
            scroller.post(()->{if(!isShowing())return;int max=(int)(activity.getWindow().getDecorView().getHeight()*.82f);if(scroller.getHeight()>max&&window!=null)window.setLayout(-1,max);});
            if(motion()){body.setTranslationY(dp(56));body.setAlpha(0);body.animate().translationY(0).alpha(1).setDuration(300).setInterpolator(EASE).start();dim(0,.56f,240);}
        }
    }
    final class Icon extends View {
        final Paint paint=new Paint(3);final String kind;final int tint;
        Icon(String kind,int tint){super(activity);this.kind=kind;this.tint=tint;setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
        void line(Canvas c,float... points){Path p=new Path();p.moveTo(points[0],points[1]);for(int i=2;i<points.length;i+=2)p.lineTo(points[i],points[i+1]);c.drawPath(p,paint);}
        @Override protected void onDraw(Canvas c){super.onDraw(c);c.save();c.scale(getWidth()/24f,getHeight()/24f);paint.setColor(tint);paint.setStrokeWidth(1.6f);paint.setStyle(Paint.Style.STROKE);paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeJoin(Paint.Join.ROUND);
            switch(kind){
                case "spark":line(c,12,2,15,9,22,12,15,15,12,22,9,15,2,12,9,9,12,2);break;
                case "chat":c.drawRoundRect(3,3,21,18,4,4,paint);line(c,7,18,7,22,12,18);line(c,7,8,17,8);line(c,7,12,14,12);break;
                case "attachment":c.save();c.rotate(35,12,12);c.drawArc(6,2,18,18,180,180,false,paint);line(c,18,10,18,17);c.drawArc(6,11,18,23,0,180,false,paint);line(c,6,17,6,7);c.drawArc(6,3,14,11,180,180,false,paint);line(c,14,7,14,16);c.restore();break;
                case "plus":line(c,12,5,12,19);line(c,5,12,19,12);break;
                case "back":line(c,14,5,7,12,14,19);break;
                case "arrow":line(c,6,18,18,6);line(c,7,6,18,6,18,17);break;
                case "send":line(c,12,19,12,5);line(c,6,11,12,5,18,11);break;
                case "close":line(c,6,6,18,18);line(c,18,6,6,18);break;
                case "more":c.drawCircle(5,12,1,paint);c.drawCircle(12,12,1,paint);c.drawCircle(19,12,1,paint);break;
                case "home":line(c,3,10,12,3,21,10);line(c,5,9,5,21,10,21,10,15,14,15,14,21,19,21,19,9);break;
                case "profile":c.drawCircle(12,8,4,paint);c.drawArc(4,14,20,28,180,180,false,paint);break;
                case "trash":line(c,4,6,20,6);line(c,9,6,9,3,15,3,15,6);line(c,6,6,7,21,17,21,18,6);line(c,10,10,10,17);line(c,14,10,14,17);break;
                case "chevron":line(c,9,6,15,12,9,18);break;
                case "check":line(c,5,12,10,17,19,7);break;
                case "search":c.drawCircle(10,10,6,paint);line(c,15,15,21,21);break;
                case "refresh":c.drawArc(4,4,20,20,40,280,false,paint);line(c,20,3,20,9,14,9);break;
                case "clients":c.drawCircle(9,8,3.5f,paint);c.drawArc(2,14,16,26,180,180,false,paint);c.drawArc(13,4,21,12,-90,180,false,paint);c.drawArc(15,14,23,24,200,140,false,paint);break;
                case "projects":c.drawRoundRect(3,7,21,21,3,3,paint);line(c,8,7,8,3,16,3,16,7);line(c,3,12,21,12);line(c,10,12,10,15,14,15,14,12);break;
                case "grid":for(int x=3;x<20;x+=11)for(int y=3;y<20;y+=11)c.drawRoundRect(x,y,x+7,y+7,2,2,paint);break;
                case "clock":c.drawCircle(12,12,9,paint);line(c,12,7,12,12,16,14);break;
                case "link":c.save();c.rotate(-40,12,12);c.drawRoundRect(3,8,14,16,4,4,paint);c.drawRoundRect(10,8,21,16,4,4,paint);c.restore();break;
                case "wallet":c.drawRoundRect(3,5,21,20,3,3,paint);line(c,21,10,15,10,15,16,21,16);c.drawPoint(18,13,paint);break;
                default:c.drawRoundRect(5,3,19,21,3,3,paint);line(c,9,9,15,9);line(c,9,13,15,13);line(c,9,17,12,17);
            }c.restore();
        }
    }
    /** Bespoke layered document sculpture; decorative, never represents business metrics. */
    final class Sculpture extends View {
        final Paint paint=new Paint(3);
        final Shader halo=new RadialGradient(0,0,120,new int[]{0x35497fbd,0x0007090c},null,Shader.TileMode.CLAMP);
        final Shader surface=new LinearGradient(-75,-65,75,65,new int[]{0xff536c88,0xff202e40,0xff0c121b},null,Shader.TileMode.CLAMP);
        final Path check=new Path();
        Sculpture(){super(activity);setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);check.moveTo(43,27);check.lineTo(48,31);check.lineTo(55,22);}
        @Override protected void onDraw(Canvas c){super.onDraw(c);float w=getWidth(),h=getHeight();c.save();c.translate(w/2,h/2);float s=Math.min(w/290f,h/180f);c.scale(s,s);
            paint.setShader(halo);c.drawCircle(0,0,120,paint);paint.setShader(null);
            c.rotate(-17);for(int i=2;i>=0;i--){c.save();c.translate(i*14,i*12);paint.setStyle(Paint.Style.FILL);paint.setShader(surface);c.drawRoundRect(-80,-65,80,55,16,16,paint);paint.setShader(null);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(1);paint.setColor(i==0?0xffb8d6fa:0xff586c83);c.drawRoundRect(-80,-65,80,55,16,16,paint);c.restore();}
            paint.setStyle(Paint.Style.FILL);paint.setColor(0xffc6dcf7);c.drawRoundRect(-57,-39,-9,-33,3,3,paint);paint.setColor(0xff637a94);c.drawRoundRect(-57,-20,53,-17,2,2,paint);c.drawRoundRect(-57,-8,36,-5,2,2,paint);
            paint.setColor(0xffb3d2fd);c.drawRoundRect(-57,23,0,31,4,4,paint);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2);c.drawCircle(49,27,12,paint);c.drawPath(check,paint);paint.setStyle(Paint.Style.FILL);c.restore();
        }
    }
}
