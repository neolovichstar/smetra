package ru.smetra.mobile;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.os.SystemClock;
import android.view.View;

/**
 * Loading mark matching the four horizontal bars of the launcher icon.
 * This is a decorative view: the parent cover owns loading announcements.
 */
final class StartupMark extends View {
    private static final float DESIGN_WIDTH = 273f;
    private static final float DESIGN_HEIGHT = 297f;
    private static final float[] BAR_WIDTHS = {273f, 213f, 273f, 133f};
    private static final float[] BAR_TOPS = {0f, 90f, 180f, 270f};
    private static final float BAR_HEIGHT = 39f;
    private static final float CORNER = 12f;

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final float scale;
    private boolean animating = true;
    private long animationStart = SystemClock.uptimeMillis();

    StartupMark(Context context, int color) {
        super(context);
        scale = context.getResources().getDisplayMetrics().density * 0.16f;
        paint.setColor(color);
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
    }

    float halfHeight() {
        return DESIGN_HEIGHT * scale / 2f;
    }

    void setAnimating(boolean enabled) {
        if (animating == enabled) return;
        animating = enabled;
        if (enabled) animationStart = SystemClock.uptimeMillis();
        invalidate();
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float opacity = 1f;
        boolean motion = animating && ValueAnimator.areAnimatorsEnabled();
        if (motion) {
            float phase = ((SystemClock.uptimeMillis() - animationStart) % 1700L) / 1700f;
            opacity = 0.74f + 0.26f * (float) Math.sin(Math.PI * 2 * phase);
        }
        paint.setAlpha(Math.max(0, Math.min(255, Math.round(opacity * 255f))));
        float left = (getWidth() - DESIGN_WIDTH * scale) / 2f;
        float top = (getHeight() - DESIGN_HEIGHT * scale) / 2f;
        for (int i = 0; i < BAR_WIDTHS.length; i++) {
            float x = left;
            float y = top + BAR_TOPS[i] * scale;
            canvas.drawRoundRect(x, y, x + BAR_WIDTHS[i] * scale,
                    y + BAR_HEIGHT * scale, CORNER * scale, CORNER * scale, paint);
        }
        if (motion && isAttachedToWindow()) postInvalidateDelayed(40L);
    }
}
