package ru.smetra.mobile;

import org.junit.Test;
import static org.junit.Assert.*;

public class ReviewPolicyTest {
    private static final long FIRST = 1000L;
    @Test public void waitsForActualUseAndAge() {
        assertFalse(ReviewPolicy.eligible(FIRST, FIRST, 0, 3));
        assertFalse(ReviewPolicy.eligible(FIRST + 2 * ReviewPolicy.DAY, FIRST, 0, 10));
        assertFalse(ReviewPolicy.eligible(FIRST + 3 * ReviewPolicy.DAY, FIRST, 0, 2));
        assertTrue(ReviewPolicy.eligible(FIRST + 3 * ReviewPolicy.DAY, FIRST, 0, 3));
    }
    @Test public void respectsCooldownAndClockRollback() {
        long last = FIRST + 4 * ReviewPolicy.DAY;
        assertFalse(ReviewPolicy.eligible(last + 89 * ReviewPolicy.DAY, FIRST, last, 100));
        assertTrue(ReviewPolicy.eligible(last + 90 * ReviewPolicy.DAY, FIRST, last, 100));
        assertFalse(ReviewPolicy.eligible(last - 1, FIRST, last, 100));
        assertFalse(ReviewPolicy.eligible(FIRST - 1, FIRST, 0, 100));
        assertFalse(ReviewPolicy.eligible(last, 0, 0, 100));
    }
}
