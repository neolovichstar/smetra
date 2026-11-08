package ru.smetra.mobile;

/** Axis-aligned room dimensions, without Android or camera dependencies. */
final class ArMeasurementGeometry {
    private ArMeasurementGeometry() {}

    static float distance(int dimension, float ax, float ay, float az, float bx, float by, float bz) {
        if (dimension < 0 || dimension > 2) return Float.NaN;
        float horizontal = (float) Math.hypot(bx - ax, bz - az);
        float vertical = Math.abs(by - ay);
        if (!Float.isFinite(horizontal) || !Float.isFinite(vertical)) return Float.NaN;
        if (dimension < 2 && vertical > .2f || dimension == 2 && horizontal > .35f) return Float.NaN;
        float value = dimension == 2 ? vertical : horizontal;
        return value >= .5f && value <= 100f ? value : Float.NaN;
    }
}
