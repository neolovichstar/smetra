package ru.smetra.mobile;

import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Actual delayed executor work, switching account while a request is running. */
public final class NativeSessionWorkTest {
    public static void main(String[] args) throws Exception {
        ExecutorService executor=Executors.newSingleThreadExecutor();
        AtomicReference<String> token=new AtomicReference<>("account-a");
        AtomicInteger page=new AtomicInteger(1);
        NativeSessionWork work=new NativeSessionWork(executor,token::get,page::get);
        CountDownLatch started=new CountDownLatch(1),release=new CountDownLatch(1);
        AtomicReference<String> requestToken=new AtomicReference<>();
        AtomicBoolean queuedOldRan=new AtomicBoolean(),oldResultAccepted=new AtomicBoolean(true),newRan=new AtomicBoolean(),oldPageAccepted=new AtomicBoolean(true);
        work.execute(()->{started.countDown();try { if(!release.await(5,TimeUnit.SECONDS))throw new AssertionError("Timed out"); } catch(InterruptedException error) { throw new AssertionError(error); }
            requestToken.set(work.tokenForRequest(token.get()));oldResultAccepted.set(work.accepts(work.snapshot()));});
        if(!started.await(5,TimeUnit.SECONDS))throw new AssertionError("Worker did not start");
        work.execute(()->queuedOldRan.set(true));
        token.set("account-b");page.incrementAndGet();
        work.execute(()->{newRan.set("account-b".equals(work.tokenForRequest("wrong")));NativeSessionWork.Snapshot snapshot=work.snapshot();page.incrementAndGet();oldPageAccepted.set(work.samePage(snapshot));});
        release.countDown();executor.shutdown();if(!executor.awaitTermination(5,TimeUnit.SECONDS))throw new AssertionError("Worker did not stop");
        if(!"account-a".equals(requestToken.get())||oldResultAccepted.get()||queuedOldRan.get()||!newRan.get()||oldPageAccepted.get())throw new AssertionError("Session or page crossed the delayed-work boundary");
        if(!"fallback".equals(work.tokenForRequest("fallback")))throw new AssertionError("Thread context leaked");
        AtomicReference<String> anonymous=new AtomicReference<>();NativeSessionWork anonymousWork=new NativeSessionWork(Runnable::run,anonymous::get,()->1);
        anonymousWork.execute(()->{anonymous.set("signed-in");if(anonymousWork.tokenForRequest("signed-in")!=null)throw new AssertionError("Anonymous work acquired a new session");});
        System.out.println("PASS: queued old work skipped; running work keeps its account; old replies rejected; new account/page and anonymous context isolated");
    }
}
