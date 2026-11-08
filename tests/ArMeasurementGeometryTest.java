package ru.smetra.mobile;

public final class ArMeasurementGeometryTest {
    private static void near(float value, float expected) {
        if (Math.abs(value - expected) > .001f || !Float.isFinite(value)) throw new AssertionError(value + " != " + expected);
    }
    private static void invalid(float value) {
        if (!Float.isNaN(value)) throw new AssertionError("Invalid dimension was accepted: " + value);
    }
    public static void main(String[] args) {
        near(ArMeasurementGeometry.distance(0,0,0,0,4,.1f,0),4);
        near(ArMeasurementGeometry.distance(1,0,0,0,0,0,3),3);
        near(ArMeasurementGeometry.distance(2,0,0,0,.1f,2.7f,.1f),2.7f);
        invalid(ArMeasurementGeometry.distance(0,0,0,0,4,2,0));
        invalid(ArMeasurementGeometry.distance(2,0,0,0,3,2.7f,0));
        invalid(ArMeasurementGeometry.distance(0,0,0,0,0,0,0));
        invalid(ArMeasurementGeometry.distance(0,0,0,0,Float.NaN,0,0));
        invalid(ArMeasurementGeometry.distance(3,0,0,0,4,0,0));
        System.out.println("PASS: horizontal lengths, vertical height, diagonal drift and invalid measurements");
    }
}
