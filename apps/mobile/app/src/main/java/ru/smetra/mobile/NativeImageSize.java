package ru.smetra.mobile;

/** Fit-center sampling keeps enough pixels without decoding the full artwork. */
final class NativeImageSize {
    private NativeImageSize() {}
    static int sample(int width,int height,int targetWidth,int targetHeight){
        if(width<=0||height<=0||targetWidth<=0||targetHeight<=0)return 1;
        double ratio=Math.min(1d,Math.min((double)targetWidth/width,(double)targetHeight/height));
        int requiredWidth=Math.max(1,(int)Math.ceil(width*ratio));
        int requiredHeight=Math.max(1,(int)Math.ceil(height*ratio));
        int sample=1;
        while(sample<=Integer.MAX_VALUE/2&&width/(sample*2)>=requiredWidth&&height/(sample*2)>=requiredHeight)sample*=2;
        return sample;
    }
}
