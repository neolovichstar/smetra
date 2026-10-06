package ru.smetra.mobile;

import java.util.Objects;
import java.util.concurrent.Executor;
import java.util.function.IntSupplier;
import java.util.function.Supplier;

/** Bind deferred work to its originating account, including nested API calls. */
final class NativeSessionWork {
    static final class Snapshot {
        final String token;
        final int page;
        Snapshot(String token, int page) { this.token=token; this.page=page; }
    }
    private final Executor executor;
    private final Supplier<String> token;
    private final IntSupplier page;
    private final ThreadLocal<Snapshot> context=new ThreadLocal<>();
    NativeSessionWork(Executor executor, Supplier<String> token, IntSupplier page) {
        this.executor=executor; this.token=token; this.page=page;
    }
    void execute(Runnable action) {
        Snapshot captured=new Snapshot(token.get(),page.getAsInt());
        executor.execute(()->{
            if(!accepts(captured))return;
            context.set(captured);
            try { action.run(); } finally { context.remove(); }
        });
    }
    Snapshot snapshot() { return context.get(); }
    boolean accepts(Snapshot captured) { return captured==null||Objects.equals(captured.token,token.get()); }
    boolean samePage(Snapshot captured) { return captured==null||captured.page==page.getAsInt(); }
    String tokenForRequest(String fallback) { Snapshot captured=context.get(); return captured==null?fallback:captured.token; }
}
