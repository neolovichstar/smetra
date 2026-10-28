/* Ctrl+V attachments in the assistant composer. Text-only paste remains native. */
(() => {
  const supportedDocuments = new Set(['pdf','txt','md','docx','xlsx','csv']);
  const supportedImages = new Map([['image/png','png'],['image/jpeg','jpg']]);
  const supportedAudio = new Set(['mp3','wav','m4a','ogg','webm','flac','aac']);
  const audioType = new Map([['audio/mpeg','mp3'],['audio/wav','wav'],['audio/x-wav','wav'],['audio/mp4','m4a'],['audio/ogg','ogg'],['audio/webm','webm'],['audio/flac','flac'],['audio/aac','aac']]);
  const extract = clipboard => {
    if(!clipboard)return [];
    let files = Array.from(clipboard.files || []);
    // Firefox/Chromium can expose file items without populating DataTransfer.files.
    if(!files.length)files = Array.from(clipboard.items || [])
      .filter(item => item.kind === 'file' && typeof item.getAsFile === 'function')
      .map(item => item.getAsFile()).filter(Boolean);
    return files.filter(file => {
      if(!file || !Number.isFinite(file.size) || file.size < 1)return false;
      const mime=String(file.type || '').toLowerCase();
      if(supportedImages.has(mime)||audioType.has(mime))return true;
      const extension = String(file.name || '').toLowerCase().split('.').pop();
      return supportedDocuments.has(extension) || supportedAudio.has(extension) || ['png','jpg','jpeg'].includes(extension);
    }).map((file, index) => {
      const type=String(file.type||'').toLowerCase();
      const format=supportedImages.get(type);
      const audio=audioType.get(type);
      if(audio && (!file.name || !/\.[a-z0-9]{2,5}$/i.test(file.name))){
        return new File([file], 'Запись-'+new Date().toISOString().replace(/[:.]/g,'-')+'-'+(index+1)+'.'+audio,
          {type,lastModified:file.lastModified||Date.now()});
      }
      if(format && (!file.name || /^image(?:\s*\(\d+\))?\.(?:png|jpe?g)$/i.test(file.name))) {
        const timestamp=new Date().toISOString().replace(/[:.]/g,'-');
        return new File([file], 'Скриншот-'+timestamp+'-'+(index+1)+'.'+format,
          {type, lastModified:file.lastModified||Date.now()});
      }
      return file;
    });
  };
  const paste = async (event, upload) => {
    const files=extract(event?.clipboardData);
    if(!files.length)return false;
    // Prevent only file payloads. Normal clipboard text is never intercepted.
    event.preventDefault();
    for(const file of files)await upload(file);
    return true;
  };
  window.SmetraClipboardAttachments = Object.freeze({extract, paste});
})();
