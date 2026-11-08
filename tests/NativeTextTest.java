package ru.smetra.mobile;

public final class NativeTextTest {
    public static void main(String[] args) {
        require(NativeText.isBlank(null));
        require(NativeText.isBlank(""));
        require(NativeText.isBlank(" \t\n\r"));
        require(NativeText.isBlank("\u00a0\u2003"));
        require(!NativeText.isBlank("  смета  "));
        require(!NativeText.isBlank("\u200b"));
    }

    private static void require(boolean value) {
        if (!value) throw new AssertionError("NativeText.isBlank mismatch");
    }
}
