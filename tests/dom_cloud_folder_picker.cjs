const fs=require('node:fs');
const assert=require('node:assert/strict');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
(async()=>{
  const dom=new JSDOM('<!doctype html><main id="mount"></main>',{url:'https://smetra.online/app#premium',runScripts:'outside-only'});
  const w=dom.window,doc=w.document;
  w.escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  w.view=html=>{doc.querySelector('#mount').innerHTML=html};
  w.header=()=>'<h1>Материалы и облака</h1>';
  w.notify=message=>{w.lastNotice=message};
  w.tab='premium';w.render=async()=>w.SmetraPremiumTools.render();
  w.SmetraDialog={confirm:async()=>true};
  const calls=[];
  const connections=[{id:'y-1',provider:'yandex_disk',status:'active',account_label:'Мой Яндекс'}];
  const folders=[];
  w.api=async(path,options)=>{
    calls.push({path,options});
    if(path==='/premium/features')return {cloud_drives:true,product_monitor:true,visual_estimates:true};
    if(path==='/quotes')return {quotes:[]};
    if(path==='/premium/product-sources')return {sources:[]};
    if(path==='/premium/cloud/connections'&&options?.method==='DELETE'){
      const request=JSON.parse(options.body);
      const index=connections.findIndex(c=>c.id===request.connection_id);
      if(index<0)throw Error('Unknown connection');
      connections.splice(index,1);
      return {ok:true};
    }
    if(path==='/premium/cloud/connections')return {connections};
    if(path==='/premium/cloud/folders'&&options?.method==='POST'){
      const request=JSON.parse(options.body);
      const connection=connections.find(c=>c.id===request.connection_id);
      folders.push({id:'bound-'+folders.length,provider:connection.provider,connection_id:connection.id,
        folder_id:request.folder_id,folder_name:'Мой диск',account_label:connection.account_label,
        status:'active',sync_requested:true});
      return {folder_id:folders[folders.length-1].id,sync_requested:true};
    }
    if(path==='/premium/cloud/folders')return {folders};
    if(path==='/premium/cloud/jobs')return {jobs:[]};
    if(path.startsWith('/premium/cloud/browse-folders?')){
      const url=new URL(path,'https://smetra.online');
      if(url.searchParams.get('parent')==='/')return {parent:'/',folders:[{id:'/Проекты',name:'Проекты'}],files:[{name:'Смета.xlsx',mime_type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}],next_cursor:''};
      if(url.searchParams.get('parent')==='/Проекты')return {parent:'/Проекты',folders:[{id:'/Проекты/Сметы',name:'Сметы'}],files:[{name:'Счёт.pdf',mime_type:'application/pdf'}],next_cursor:''};
      return {parent:url.searchParams.get('parent'),folders:[],next_cursor:''};
    }
    throw Error('Unexpected request: '+path);
  };
  w.eval(fs.readFileSync('apps/web/premium-tools.js','utf8'));
  await w.SmetraPremiumTools.render();
  await new Promise(r=>setTimeout(r,25));
  const cards=[...doc.querySelectorAll('.premium-connect')];
  assert.equal(cards.length,2,'Only two provider cards, no duplicate list');
  assert.match(cards[0].textContent,/Отключить/);
  assert.equal(cards[0].querySelector('.premium-connect-action').dataset.premiumDisconnect,'y-1');
  assert.match(cards[1].textContent,/Подключить/);
  assert.equal(doc.querySelector('.premium-connection-list'),null);
  assert.equal(doc.querySelector('.premium-folder-setup'),null,'Redundant add-folder accordion is gone');
  assert.equal(doc.querySelectorAll('.premium-connect-action').length,2);
  assert.equal(doc.querySelectorAll('[data-premium-disconnect]').length,1);
  assert.equal(cards[0].querySelector('.premium-connect-select').getAttribute('aria-pressed'),'true');
  assert.ok(cards[0].classList.contains('is-selected'));
  assert.equal(doc.querySelector('.premium-cloud-folders-heading h3').textContent,'Папки и файлы');
  assert.match(doc.querySelector('#premium-folder-entries').textContent,/Проекты/);
  assert.match(doc.querySelector('#premium-folder-entries').textContent,/Смета.xlsx/);
  assert.equal(doc.querySelector('#premium-folder-submit').disabled,true,'Selection is required before synchronization');
  // Root selection works even when there are no subfolders to click.
  doc.querySelector('#premium-folder-select-current').click();
  assert.equal(doc.querySelector('#premium-folder-id').value,'/');
  assert.match(doc.querySelector('#premium-folder-choice').textContent,/Мой диск/);
  assert.equal(doc.querySelector('#premium-folder-submit').disabled,false,'Explicit root selection enables synchronization');
  doc.querySelector('#premium-folder-back').disabled; // no navigation on root selection
  assert.equal(doc.querySelector('#premium-folder-submit').textContent,'Добавить папку');
  assert.equal(doc.querySelectorAll('[data-premium-resync]').length,0,'No manual sync buttons');
  assert.equal(doc.querySelector('#premium-sync-all'),null,'No global manual sync button');
  const pageBefore=doc.querySelector('.premium-tools-page');
  const pickerBefore=doc.querySelector('#premium-folder-entries');
  pageBefore.scrollTop=115;
  doc.querySelector('#premium-folder-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
  await new Promise(r=>setTimeout(r,35));
  assert.equal(folders.length,1,'Folder added for automatic background syncing');
  assert.equal(folders[0].sync_requested,true);
  assert.equal(doc.querySelector('.premium-tools-page'),pageBefore,'Adding folder does not rebuild page');
  assert.equal(doc.querySelector('#premium-folder-entries'),pickerBefore,'Folder browser is not recreated');
  assert.equal(pageBefore.scrollTop,115,'Adding a folder keeps page scroll position');
  assert.match(doc.querySelector('.premium-folder-list').textContent,/Мой диск/);
  assert.equal(doc.querySelector('#premium-cloud-folder-count').textContent,'1 папок');
  assert.equal(doc.querySelector('#premium-folder-submit').disabled,true,'Prevent repeated submit');
  assert.equal(calls.filter(x=>x.path==='/premium/cloud/sync').length,0,'No manual sync endpoint');
  const styles=fs.readFileSync('apps/web/ui/modules.css','utf8');
  assert.match(styles,/\.premium-cloud-sync-list \.premium-folder-list\{max-height:\d+px;overflow-y:auto/);
  assert.match(styles,/\.premium-folder-entries\{height:\d+px;max-height:\d+px/);
  // Switch providers clears the previous selected folder.
  const beforeSelect=calls.length;
  cards[1].querySelector('.premium-connect-select').click();
  await new Promise(r=>setTimeout(r,25));
  assert.equal(cards[0].querySelector('.premium-connect-select').getAttribute('aria-pressed'),'false');
  assert.equal(cards[1].querySelector('.premium-connect-select').getAttribute('aria-pressed'),'true');
  assert.ok(cards[1].classList.contains('is-selected'),'Google is visually selected');
  assert.equal(doc.querySelector('#premium-cloud-name').textContent,'Google Drive');
  assert.equal(doc.querySelector('#premium-folder-submit').disabled,true,'Cannot sync a disconnected cloud');
  assert.match(doc.querySelector('#premium-folder-entries').textContent,/не подключён/);
  assert.equal(calls.length,beforeSelect,'Selecting a card never initiates OAuth or disconnect');
  cards[0].click(); // Whole card outside small action selects.
  await new Promise(r=>setTimeout(r,25));
  assert.ok(cards[0].classList.contains('is-selected'));
  assert.equal(doc.querySelector('#premium-folder-submit').disabled,true,'Switching providers must clear earlier selection');
  assert.match(doc.querySelector('#premium-folder-entries').textContent,/Проекты/);
  doc.querySelector('.premium-folder-enter').click();
  await new Promise(r=>setTimeout(r,25));
  assert.match(doc.querySelector('#premium-folder-entries').textContent,/Сметы/);
  assert.equal(doc.querySelector('#premium-folder-id').value,'');
  doc.querySelector('.premium-folder-select').click();
  assert.equal(doc.querySelector('.premium-folder-select').getAttribute('aria-pressed'),'true');
  assert.equal(doc.querySelector('.premium-folder-enter').tagName,'BUTTON','Open works with keyboard');
  assert.equal(doc.querySelector('#premium-folder-id').value,'/Проекты/Сметы');
  assert.match(doc.querySelector('#premium-folder-choice').textContent,/Сметы/);
  assert.equal(doc.querySelector('#premium-folder-submit').disabled,false);
  doc.querySelector('#premium-folder-back').click();
  await new Promise(r=>setTimeout(r,25));
  assert.equal(doc.querySelector('#premium-folder-id').value,'','Navigating invalidates previous selection');
  assert.equal(doc.querySelector('#premium-folder-submit').disabled,true);
  assert.ok(calls.some(x=>x.path.includes('browse-folders?connection_id=y-1')));
  assert.equal(doc.documentElement.querySelectorAll('input[name="folder_id"]').length,1);
  const deleteBefore=calls.filter(x=>x.options?.method==='DELETE').length;
  // Only the small OAuth button can initiate a disconnection.
  doc.querySelector('[data-premium-disconnect="y-1"]').click();
  await new Promise(r=>setTimeout(r,35));
  assert.equal(calls.filter(x=>x.options?.method==='DELETE').length,deleteBefore+1);
  assert.equal(doc.querySelectorAll('[data-premium-disconnect]').length,0);
  assert.match(doc.querySelector('[data-premium-connect="yandex_disk"]').textContent,/Подключить/);
  assert.equal(doc.querySelector('[data-premium-select="yandex_disk"]').getAttribute('aria-pressed'),'true');
  // Connected Google Drive with an empty root must still be understandable.
  connections.push({id:'g-1',provider:'google_drive',status:'active',account_label:'Google User'});
  await w.SmetraPremiumTools.render();
  doc.querySelector('[data-premium-select="google_drive"]').click();
  await new Promise(r=>setTimeout(r,25));
  assert.match(doc.querySelector('#premium-folder-entries').textContent,/нет папок или файлов/);
  assert.equal(doc.querySelector('#premium-folder-submit').disabled,true);
  doc.querySelector('#premium-folder-select-current').click();
  assert.equal(doc.querySelector('#premium-folder-id').value,'root');
  assert.match(doc.querySelector('#premium-folder-choice').textContent,/Google Drive \/ Мой диск/);
  assert.equal(doc.querySelector('#premium-folder-submit').disabled,false);
  dom.window.close();
  console.log('PASS: independent select/actions, visible folders, active highlight, nested picker and back');
})().catch(error=>{console.error(error);process.exit(1)});
