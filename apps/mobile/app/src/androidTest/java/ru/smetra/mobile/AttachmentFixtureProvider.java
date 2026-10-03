package ru.smetra.mobile;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/** Static test documents only. This provider is never packaged in the release app. */
public class AttachmentFixtureProvider extends ContentProvider {
    @Override public boolean onCreate(){return true;}
    private byte[] bytes(Uri uri)throws IOException{
        String name=uri.getLastPathSegment();
        if("empty.txt".equals(name))return new byte[0];
        if("binary.txt".equals(name))return new byte[]{(byte)0xff,0};
        if("large-text.txt".equals(name)){byte[] content=new byte[2_100_000];java.util.Arrays.fill(content,(byte)'a');return content;}
        if("brief.pdf".equals(name)||"scan.pdf".equals(name))try(java.io.InputStream input=getContext().getAssets().open(name)){return input.readAllBytes();}
        return "# Project brief\nPaint walls, 12 square metres.\n".getBytes(StandardCharsets.UTF_8);
    }
    @Override public String getType(Uri uri){return uri.toString().endsWith(".pdf")?"application/pdf":uri.toString().endsWith(".md")?"application/octet-stream":"text/plain";}
    @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String order){
        try{MatrixCursor cursor=new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE});cursor.addRow(new Object[]{uri.getLastPathSegment(),"large.pdf".equals(uri.getLastPathSegment())?5_000_001:bytes(uri).length});return cursor;}catch(IOException error){throw new IllegalStateException(error);}
    }
    @Override public ParcelFileDescriptor openFile(Uri uri,String mode)throws java.io.FileNotFoundException{
        if(!"r".equals(mode))throw new java.io.FileNotFoundException("Read only");
        try{File file=new File(getContext().getCacheDir(),"attachment-fixture");try(FileOutputStream out=new FileOutputStream(file)){out.write(bytes(uri));}return ParcelFileDescriptor.open(file,ParcelFileDescriptor.MODE_READ_ONLY);}catch(IOException error){throw new java.io.FileNotFoundException(error.getMessage());}
    }
    @Override public Uri insert(Uri uri,ContentValues values){throw new UnsupportedOperationException();}
    @Override public int update(Uri uri,ContentValues values,String selection,String[] args){throw new UnsupportedOperationException();}
    @Override public int delete(Uri uri,String selection,String[] args){throw new UnsupportedOperationException();}
}
