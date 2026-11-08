package ru.smetra.mobile;

public final class NativeQuoteNumbersTest {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private static void invalid(Runnable action, String message) {
        try { action.run(); } catch (RuntimeException expected) { return; }
        throw new AssertionError(message);
    }

    public static void main(String[] args) {
        check(QuoteNumbers.toMinorUnits("1 234,56") == 123456, "Russian decimal comma and grouping spaces");
        check(QuoteNumbers.toMinorUnits("12.50") == 1250, "Dot decimal support");
        check(QuoteNumbers.lineTotal(10000, "1,5", "1", "0", "0", "0") == 15000,
                "Quantity with a decimal comma");
        check(QuoteNumbers.lineTotal(10000, "2", "1,5", "10", "5", "20") == 37620,
                "Coefficient, markup, discount and tax calculation");
        invalid(() -> QuoteNumbers.toMinorUnits("1,234"), "Sub-kopeck prices must not be rounded silently");
        invalid(() -> QuoteNumbers.lineTotal(10000, "0", "1", "0", "0", "0"), "Quantity must be positive");
        invalid(() -> QuoteNumbers.lineTotal(10000, "1", "1", "0", "101", "0"), "Discount cannot exceed 100 percent");
        invalid(() -> QuoteNumbers.lineTotal(-1, "1", "1", "0", "0", "0"), "Price cannot be negative");
        System.out.println("PASS: locale decimal parsing, exact money conversion, quote calculation and invalid-input rejection");
    }
}
