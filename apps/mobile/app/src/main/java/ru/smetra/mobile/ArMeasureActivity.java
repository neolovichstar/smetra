package ru.smetra.mobile;

import android.app.Activity;
import android.content.Intent;
import android.graphics.drawable.GradientDrawable;
import android.opengl.GLES11Ext;
import android.opengl.GLES20;
import android.opengl.GLSurfaceView;
import android.opengl.Matrix;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import com.google.ar.core.Anchor;
import com.google.ar.core.ArCoreApk;
import com.google.ar.core.Camera;
import com.google.ar.core.Config;
import com.google.ar.core.Coordinates2d;
import com.google.ar.core.Frame;
import com.google.ar.core.HitResult;
import com.google.ar.core.Plane;
import com.google.ar.core.Point;
import com.google.ar.core.Pose;
import com.google.ar.core.Session;
import com.google.ar.core.Trackable;
import com.google.ar.core.TrackingState;
import com.google.ar.core.exceptions.CameraNotAvailableException;
import com.google.ar.core.exceptions.UnavailableException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import javax.microedition.khronos.egl.EGLConfig;
import javax.microedition.khronos.opengles.GL10;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Point-to-point room measurement with ARCore. The user aims the centre mark
 * at a corner and adds points: two for the length, two for the width and two
 * for the height (or types the height). Results are approximate and always go
 * through the server preview and an explicit import confirmation.
 */
public final class ArMeasureActivity extends Activity implements GLSurfaceView.Renderer {
    static final String EXTRA_ROOMS = "rooms";
    private static final String[] STEPS = {"length", "width", "height"};
    private static final String[] STEP_NAMES = {"Длина", "Ширина", "Высота"};

    private GLSurfaceView surface;
    private Session session;
    private boolean installRequested;
    private TextView hint, readout;
    private Button addPoint, undo, next;
    private EditText roomName, manualHeight;

    // Touched from the GL thread and the UI thread; guarded by "this".
    private final List<Anchor> anchors = new ArrayList<>();
    private boolean placeRequested, tracking;
    private int step;
    private final float[] lengths = new float[3];
    private final JSONArray rooms = new JSONArray();

    private int cameraTexture, backgroundProgram, lineProgram;
    private final float[] quad = {-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f};
    private final float[] quadUv = new float[8];
    private FloatBuffer quadBuffer, uvBuffer;
    private final float[] view = new float[16], projection = new float[16], mvp = new float[16];
    private int width, height;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        FrameLayout root = new FrameLayout(this);
        surface = new GLSurfaceView(this);
        surface.setPreserveEGLContextOnPause(true);
        surface.setEGLContextClientVersion(2);
        surface.setEGLConfigChooser(8, 8, 8, 8, 16, 0);
        surface.setRenderer(this);
        surface.setRenderMode(GLSurfaceView.RENDERMODE_CONTINUOUSLY);
        root.addView(surface);
        root.addView(crosshair(), new FrameLayout.LayoutParams(dp(28), dp(28), Gravity.CENTER));
        root.addView(panel(), new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM));
        hint = text(15, 0xFFFFFFFF);
        hint.setGravity(Gravity.CENTER);
        hint.setPadding(dp(16), dp(48), dp(16), dp(12));
        hint.setBackground(new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[]{0xCC000000, 0x00000000}));
        root.addView(hint, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP));
        setContentView(root);
        refresh();
    }

    // ---------- UI ----------

    private int dp(int value) { return (int) (value * getResources().getDisplayMetrics().density); }

    private TextView text(int size, int color) {
        TextView view = new TextView(this);
        view.setTextSize(size);
        view.setTextColor(color);
        return view;
    }

    private View crosshair() {
        View mark = new View(this);
        GradientDrawable ring = new GradientDrawable();
        ring.setShape(GradientDrawable.OVAL);
        ring.setStroke(dp(2), 0xFFFFFFFF);
        ring.setColor(0x334C8DFF);
        mark.setBackground(ring);
        return mark;
    }

    private Button button(String label, boolean primary) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextColor(primary ? 0xFF0B0B0C : 0xFFF5F5F4);
        GradientDrawable shape = new GradientDrawable();
        shape.setCornerRadius(dp(12));
        shape.setColor(primary ? 0xFFF5F5F4 : 0xFF26262A);
        button.setBackground(shape);
        return button;
    }

    private View panel() {
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(16), dp(14), dp(16), dp(20));
        GradientDrawable sheet = new GradientDrawable();
        sheet.setColor(0xF20B0B0C);
        sheet.setCornerRadii(new float[]{dp(18), dp(18), dp(18), dp(18), 0, 0, 0, 0});
        panel.setBackground(sheet);
        readout = text(14, 0xFFD4D4D2);
        readout.setLineSpacing(0, 1.2f);
        panel.addView(readout);
        roomName = new EditText(this);
        roomName.setHint("Название помещения");
        roomName.setText("Комната 1");
        roomName.setTextColor(0xFFF5F5F4);
        roomName.setHintTextColor(0xFF8A8A88);
        roomName.setSingleLine(true);
        panel.addView(roomName);
        manualHeight = new EditText(this);
        manualHeight.setHint("Высота вручную, м (например 2,7)");
        manualHeight.setTextColor(0xFFF5F5F4);
        manualHeight.setHintTextColor(0xFF8A8A88);
        manualHeight.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        manualHeight.setVisibility(View.GONE);
        panel.addView(manualHeight);
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, dp(10), 0, 0);
        undo = button("Отменить", false);
        addPoint = button("Поставить точку", true);
        next = button("Готово", false);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(48), 1f);
        lp.setMargins(dp(4), 0, dp(4), 0);
        row.addView(undo, lp);
        row.addView(addPoint, new LinearLayout.LayoutParams(0, dp(48), 1.4f) {{ setMargins(dp(4), 0, dp(4), 0); }});
        row.addView(next, lp);
        panel.addView(row);
        addPoint.setOnClickListener(v -> { synchronized (this) { placeRequested = true; } });
        undo.setOnClickListener(v -> undo());
        next.setOnClickListener(v -> nextAction());
        return panel;
    }

    private void refresh() {
        runOnUiThread(() -> {
            synchronized (this) {
                StringBuilder lines = new StringBuilder();
                for (int i = 0; i < 3; i++) {
                    lines.append(STEP_NAMES[i]).append(": ")
                        .append(lengths[i] > 0 ? String.format(Locale.forLanguageTag("ru"), "%.2f м", lengths[i]) : (i == step ? "измеряем…" : "—"));
                    if (i < 2) lines.append("   ");
                }
                lines.append("\nПомещений добавлено: ").append(rooms.length())
                    .append(". Замер приблизительный — проверьте размеры перед импортом.");
                readout.setText(lines.toString());
                if (!tracking) hint.setText("Медленно поводите телефоном, чтобы камера нашла пол и стены");
                else if (step < 3) hint.setText("Наведите круг на " + (anchors.size() % 2 == 0 ? "начало" : "конец") + " — " + STEP_NAMES[step].toLowerCase(Locale.ROOT)
                    + (step == 2 ? " (можно ввести вручную)" : ""));
                else hint.setText("Помещение измерено. Добавьте его или измерьте следующее");
                addPoint.setEnabled(tracking && step < 3);
                addPoint.setAlpha(addPoint.isEnabled() ? 1f : .5f);
                manualHeight.setVisibility(step == 2 ? View.VISIBLE : View.GONE);
                next.setText(step >= 3 ? "Добавить" : step == 2 ? "Без высоты" : rooms.length() > 0 ? "Готово" : "Отмена");
            }
        });
    }

    private void undo() {
        synchronized (this) {
            if (!anchors.isEmpty()) {
                if (anchors.size() % 2 == 0 && step > 0) { step--; lengths[step] = 0; }
                anchors.remove(anchors.size() - 1).detach();
            } else if (step > 0) {
                step--; lengths[step] = 0;
            }
        }
        refresh();
    }

    private void nextAction() {
        synchronized (this) {
            if (step == 2) {
                String typed = manualHeight.getText().toString().replace(',', '.').trim();
                try {
                    float value = Float.parseFloat(typed);
                    if (value >= 1.5f && value <= 6f) { lengths[2] = value; step = 3; }
                    else { hint.setText("Высота — от 1,5 до 6 м"); return; }
                } catch (NumberFormatException error) { hint.setText("Введите высоту или измерьте её двумя точками"); return; }
            } else if (step >= 3) {
                addRoom();
            } else {
                finishWithRooms();
                return;
            }
        }
        refresh();
    }

    private void addRoom() {
        try {
            String name = roomName.getText().toString().trim();
            rooms.put(new JSONObject()
                .put("name", name.isEmpty() ? "Комната " + (rooms.length() + 1) : name.substring(0, Math.min(name.length(), 120)))
                .put("unit", "м")
                .put("length", String.format(Locale.ROOT, "%.2f", lengths[0]))
                .put("width", String.format(Locale.ROOT, "%.2f", lengths[1]))
                .put("height", String.format(Locale.ROOT, "%.2f", lengths[2]))
                .put("source", "arcore"));
        } catch (Exception ignored) { return; }
        for (Anchor anchor : anchors) anchor.detach();
        anchors.clear();
        lengths[0] = lengths[1] = lengths[2] = 0;
        step = 0;
        roomName.setText("Комната " + (rooms.length() + 1));
        manualHeight.setText("");
        if (rooms.length() >= 12) finishWithRooms();
    }

    private void finishWithRooms() {
        if (rooms.length() == 0) { setResult(RESULT_CANCELED); finish(); return; }
        setResult(RESULT_OK, new Intent().putExtra(EXTRA_ROOMS, rooms.toString()));
        finish();
    }

    // ---------- ARCore session ----------

    @Override protected void onResume() {
        super.onResume();
        if (session == null) {
            try {
                if (ArCoreApk.getInstance().requestInstall(this, !installRequested) == ArCoreApk.InstallStatus.INSTALL_REQUESTED) {
                    installRequested = true;
                    return;
                }
                session = new Session(this);
                Config config = new Config(session);
                config.setPlaneFindingMode(Config.PlaneFindingMode.HORIZONTAL_AND_VERTICAL);
                config.setFocusMode(Config.FocusMode.AUTO);
                config.setUpdateMode(Config.UpdateMode.LATEST_CAMERA_IMAGE);
                if (session.isDepthModeSupported(Config.DepthMode.AUTOMATIC)) config.setDepthMode(Config.DepthMode.AUTOMATIC);
                session.configure(config);
            } catch (UnavailableException | RuntimeException error) {
                fail("AR недоступен на этом устройстве. Введите размеры вручную в Сметре.");
                return;
            }
        }
        try { session.resume(); }
        catch (CameraNotAvailableException error) { fail("Камера занята другим приложением. Закройте его и попробуйте снова."); session = null; return; }
        surface.onResume();
    }

    @Override protected void onPause() {
        super.onPause();
        if (session != null) { surface.onPause(); session.pause(); }
    }

    @Override protected void onDestroy() {
        if (session != null) { session.close(); session = null; }
        super.onDestroy();
    }

    private void fail(String message) {
        setResult(RESULT_CANCELED, new Intent().putExtra("error", message));
        android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_LONG).show();
        finish();
    }

    // ---------- rendering (GL thread) ----------

    @Override public void onSurfaceCreated(GL10 gl, EGLConfig config) {
        GLES20.glClearColor(0f, 0f, 0f, 1f);
        int[] textures = new int[1];
        GLES20.glGenTextures(1, textures, 0);
        cameraTexture = textures[0];
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, cameraTexture);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR);
        backgroundProgram = program(
            "attribute vec4 a_Position;attribute vec2 a_Uv;varying vec2 v_Uv;void main(){gl_Position=a_Position;v_Uv=a_Uv;}",
            "#extension GL_OES_EGL_image_external : require\nprecision mediump float;varying vec2 v_Uv;uniform samplerExternalOES u_Texture;void main(){gl_FragColor=texture2D(u_Texture,v_Uv);}");
        lineProgram = program(
            "uniform mat4 u_Mvp;uniform float u_Size;attribute vec4 a_Position;void main(){gl_Position=u_Mvp*a_Position;gl_PointSize=u_Size;}",
            "precision mediump float;uniform vec4 u_Color;void main(){gl_FragColor=u_Color;}");
        quadBuffer = buffer(quad);
        uvBuffer = buffer(quadUv);
    }

    @Override public void onSurfaceChanged(GL10 gl, int w, int h) {
        width = w; height = h;
        GLES20.glViewport(0, 0, w, h);
        if (session != null) session.setDisplayGeometry(getWindowManager().getDefaultDisplay().getRotation(), w, h);
    }

    @Override public void onDrawFrame(GL10 gl) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT | GLES20.GL_DEPTH_BUFFER_BIT);
        Session current = session;
        if (current == null) return;
        try {
            current.setCameraTextureName(cameraTexture);
            Frame frame = current.update();
            if (frame.hasDisplayGeometryChanged()) {
                frame.transformCoordinates2d(Coordinates2d.OPENGL_NORMALIZED_DEVICE_COORDINATES, quad, Coordinates2d.TEXTURE_NORMALIZED, quadUv);
                uvBuffer = buffer(quadUv);
            }
            drawBackground();
            Camera camera = frame.getCamera();
            boolean nowTracking = camera.getTrackingState() == TrackingState.TRACKING;
            if (nowTracking != tracking) { tracking = nowTracking; refresh(); }
            if (!nowTracking) return;
            camera.getViewMatrix(view, 0);
            camera.getProjectionMatrix(projection, 0, 0.05f, 50f);
            Matrix.multiplyMM(mvp, 0, projection, 0, view, 0);
            boolean place;
            synchronized (this) { place = placeRequested; placeRequested = false; }
            if (place) place(frame);
            drawMarks();
        } catch (Exception ignored) {
            // A dropped frame is harmless; the next one retries.
        }
    }

    private void place(Frame frame) {
        Anchor anchor = null;
        for (HitResult hit : frame.hitTest(width / 2f, height / 2f)) {
            Trackable trackable = hit.getTrackable();
            boolean surfaceHit = (trackable instanceof Plane && ((Plane) trackable).isPoseInPolygon(hit.getHitPose()))
                || (trackable instanceof Point && ((Point) trackable).getOrientationMode() == Point.OrientationMode.ESTIMATED_SURFACE_NORMAL)
                || trackable.getClass().getSimpleName().equals("DepthPoint");
            if (surfaceHit && hit.getDistance() < 15f) { anchor = hit.createAnchor(); break; }
        }
        if (anchor == null) {
            runOnUiThread(() -> hint.setText("Здесь нет поверхности. Наведите круг на угол или край пола/стены"));
            return;
        }
        synchronized (this) {
            if (step >= 3) { anchor.detach(); return; }
            anchors.add(anchor);
            if (anchors.size() % 2 == 0) {
                Pose a = anchors.get(anchors.size() - 2).getPose(), b = anchor.getPose();
                float dx = a.tx() - b.tx(), dy = a.ty() - b.ty(), dz = a.tz() - b.tz();
                lengths[step] = (float) Math.sqrt(dx * dx + dy * dy + dz * dz);
                step++;
            }
        }
        refresh();
    }

    private void drawBackground() {
        GLES20.glDisable(GLES20.GL_DEPTH_TEST);
        GLES20.glDepthMask(false);
        GLES20.glUseProgram(backgroundProgram);
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0);
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, cameraTexture);
        GLES20.glUniform1i(GLES20.glGetUniformLocation(backgroundProgram, "u_Texture"), 0);
        int position = GLES20.glGetAttribLocation(backgroundProgram, "a_Position");
        int uv = GLES20.glGetAttribLocation(backgroundProgram, "a_Uv");
        GLES20.glVertexAttribPointer(position, 2, GLES20.GL_FLOAT, false, 0, quadBuffer);
        GLES20.glVertexAttribPointer(uv, 2, GLES20.GL_FLOAT, false, 0, uvBuffer);
        GLES20.glEnableVertexAttribArray(position);
        GLES20.glEnableVertexAttribArray(uv);
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4);
        GLES20.glDisableVertexAttribArray(position);
        GLES20.glDisableVertexAttribArray(uv);
        GLES20.glDepthMask(true);
    }

    private void drawMarks() {
        float[] points;
        synchronized (this) {
            List<float[]> tracked = new ArrayList<>();
            for (Anchor anchor : anchors) {
                if (anchor.getTrackingState() != TrackingState.TRACKING) continue;
                Pose pose = anchor.getPose();
                tracked.add(new float[]{pose.tx(), pose.ty(), pose.tz()});
            }
            points = new float[tracked.size() * 3];
            for (int i = 0; i < tracked.size(); i++) System.arraycopy(tracked.get(i), 0, points, i * 3, 3);
        }
        if (points.length == 0) return;
        GLES20.glUseProgram(lineProgram);
        GLES20.glUniformMatrix4fv(GLES20.glGetUniformLocation(lineProgram, "u_Mvp"), 1, false, mvp, 0);
        int position = GLES20.glGetAttribLocation(lineProgram, "a_Position");
        FloatBuffer vertices = buffer(points);
        GLES20.glVertexAttribPointer(position, 3, GLES20.GL_FLOAT, false, 0, vertices);
        GLES20.glEnableVertexAttribArray(position);
        GLES20.glLineWidth(6f);
        GLES20.glUniform4f(GLES20.glGetUniformLocation(lineProgram, "u_Color"), 0.30f, 0.55f, 1f, 1f);
        GLES20.glDrawArrays(GLES20.GL_LINES, 0, points.length / 3 - (points.length / 3) % 2);
        GLES20.glUniform1f(GLES20.glGetUniformLocation(lineProgram, "u_Size"), 28f);
        GLES20.glUniform4f(GLES20.glGetUniformLocation(lineProgram, "u_Color"), 1f, 1f, 1f, 1f);
        GLES20.glDrawArrays(GLES20.GL_POINTS, 0, points.length / 3);
        GLES20.glDisableVertexAttribArray(position);
    }

    private static FloatBuffer buffer(float[] values) {
        FloatBuffer result = ByteBuffer.allocateDirect(values.length * 4).order(ByteOrder.nativeOrder()).asFloatBuffer();
        result.put(values).position(0);
        return result;
    }

    private static int program(String vertex, String fragment) {
        int program = GLES20.glCreateProgram();
        GLES20.glAttachShader(program, shader(GLES20.GL_VERTEX_SHADER, vertex));
        GLES20.glAttachShader(program, shader(GLES20.GL_FRAGMENT_SHADER, fragment));
        GLES20.glLinkProgram(program);
        return program;
    }

    private static int shader(int type, String source) {
        int shader = GLES20.glCreateShader(type);
        GLES20.glShaderSource(shader, source);
        GLES20.glCompileShader(shader);
        return shader;
    }
}
