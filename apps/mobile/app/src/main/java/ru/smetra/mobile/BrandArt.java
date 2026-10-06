package ru.smetra.mobile;

import android.content.res.Resources;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.LruCache;
import android.widget.ImageView;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/** Bounded background resource decoding; the cache never retains an Activity. */
final class BrandArt {
    private static final LruCache<String,Bitmap> CACHE=new LruCache<String,Bitmap>(6*1024*1024){
        @Override protected int sizeOf(String key,Bitmap bitmap){return bitmap.getAllocationByteCount();}
    };
    private static final ThreadPoolExecutor WORKER=new ThreadPoolExecutor(1,1,30,TimeUnit.SECONDS,
        new ArrayBlockingQueue<Runnable>(8),task->{Thread thread=new Thread(task,"smetra-brand-art");thread.setDaemon(true);thread.setPriority(Thread.MIN_PRIORITY);return thread;},new ThreadPoolExecutor.DiscardOldestPolicy());
    static { WORKER.allowCoreThreadTimeOut(true); }
    private BrandArt() {}
    static void load(ImageView image,int resource,int width,int height){
        final String key=resource+":"+width+":"+height;
        Bitmap cached=CACHE.get(key);
        if(cached!=null){image.setImageBitmap(cached);return;}
        final Resources resources=image.getResources();
        final java.lang.ref.WeakReference<ImageView> target=new java.lang.ref.WeakReference<>(image);
        WORKER.execute(()->{
            try{
                if(target.get()==null)return;
                Bitmap bitmap=CACHE.get(key);
                if(bitmap==null){
                    BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;options.inScaled=false;
                    BitmapFactory.decodeResource(resources,resource,options);
                    options.inSampleSize=NativeImageSize.sample(options.outWidth,options.outHeight,width,height);
                    options.inJustDecodeBounds=false;options.inPreferredConfig=Bitmap.Config.ARGB_8888;
                    bitmap=BitmapFactory.decodeResource(resources,resource,options);
                    if(bitmap==null)return;
                    CACHE.put(key,bitmap);
                }
                final Bitmap loaded=bitmap;ImageView view=target.get();
                if(view!=null)view.post(()->{ImageView current=target.get();if(current!=null&&current.isAttachedToWindow())current.setImageBitmap(loaded);});
            }catch(RuntimeException ignored){/* Artwork must not prevent login or work. */}
        });
    }
}
