package ru.smetra.mobile;

import android.content.Context;
import java.io.File;

/**
 * Prune only stale temporary files created by the native shell itself.
 * Never touch the user's downloads, documents or any arbitrary cache folder.
 */
final class ShellFiles {
    private static final long MAX_AGE_MS = 72L * 60L * 60L * 1000L;
    private static final int MAX_ENTRIES_PER_FOLDER = 512;

    private ShellFiles() { }

    static void pruneCache(Context context) {
        File cache = context.getCacheDir();
        if (cache == null) return;
        long cutoff = System.currentTimeMillis() - MAX_AGE_MS;
        pruneFolder(new File(cache, "camera"), cutoff);
        pruneFolder(new File(cache, "shared"), cutoff);
    }

    private static void pruneFolder(File folder, long cutoff) {
        File[] entries = folder.listFiles();
        if (entries == null) return;
        int inspected = 0;
        for (File entry : entries) {
            if (++inspected > MAX_ENTRIES_PER_FOLDER) break;
            // Do not recurse into directories or follow them elsewhere.
            if (!entry.isFile()) continue;
            long modified = entry.lastModified();
            if (modified > 0L && modified < cutoff) {
                // Cleanup is best-effort; stale temp files must never crash startup.
                entry.delete();
            }
        }
    }
}
