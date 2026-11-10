package ru.smetra.mobile;

/** No rating gates or incentives: only age, use and a conservative cooldown. */
final class ReviewPolicy {
    static final long DAY = 86_400_000L;
    private ReviewPolicy() { }
    static boolean eligible(long now, long firstSeen, long lastAttempt, int actions) {
        return firstSeen > 0 && now >= firstSeen && now - firstSeen >= 3 * DAY
            && actions >= 3 && (lastAttempt == 0 || (now >= lastAttempt && now - lastAttempt >= 90 * DAY));
    }
}
