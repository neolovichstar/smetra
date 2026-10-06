package ru.smetra.mobile;

public final class NativeImageSizeTest {
    private static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    public static void main(String[] args){
        check(NativeImageSize.sample(1254,1254,1080,570)==2,"Phone artwork should decode one quarter of its pixels");
        check(NativeImageSize.sample(1254,1254,360,125)==8,"Small artwork needs no full-size texture");
        check(NativeImageSize.sample(1254,1254,1800,1800)==1,"Do not sample when the artwork is smaller than the viewport");
        check(NativeImageSize.sample(0,1254,360,125)==1,"Invalid bounds should not loop");
        check(NativeImageSize.sample(8000,1000,400,400)==16,"Landscape artwork uses fit-center dimensions");
        check(NativeImageSize.sample(1000,8000,400,400)==16,"Portrait artwork uses fit-center dimensions");
        System.out.println("PASS: native artwork sampling, aspect ratios, upscaling and invalid bounds");
    }
}
