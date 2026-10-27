/* The vault shows separate quotas and permission-safe, compact actions. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const items=[
 {id:'photo-1',name:'Визуализация кухни.png',mime:'image/png',size:120000,created_at:1690000000,vault_scope:'personal',archived:0},
 {id:'doc-1',name:'Командный акт.pdf',mime:'application/pdf',size:450000,created_at:1690000000,vault_scope:'workspace',archived:0}
];
(async()=>{
 const dom=new JSDOM('<main id="content"></main>',{url:'https://example.test/app#files',runScripts:'dangerously',pretendToBeVisual:true});
 const w=dom.window,doc=w.document,requests=[],notices=[];
 const init=doc.createElement('script');init.textContent="let user={id:'qa'},tab='files';const escapeHtml=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));const view=html=>document.querySelector('#content').innerHTML=html;";doc.head.append(init);
 w.notify=value=>notices.push(value);
 w.URL.createObjectURL=()=> 'blob:thumbnail';
 w.URL.revokeObjectURL=()=>{};
 w.fetch=async()=>({ok:true,blob:async()=>new w.Blob(['photo'],{type:'image/png'})});
 w.Workspace={manageFile:async()=>{},currentWorkspaceId:()=> 'workspace-1'};
 w.SmetraLoadFeature=async()=>{};
 w.SmetraAssistantContext=()=>{};
 w.api=async(path,opts={})=>{
   requests.push({path,method:opts.method||'GET'});
   if(path==='/workspace')return {workspace:{id:'workspace-1',role:'viewer'}};
   if(path.startsWith('/files?')){
     const query=new URLSearchParams(path.split('?')[1]);
     const candidates=items.filter(item=>item.archived===Number(query.get('archived')||0)).filter(item=>query.get('type')==='images'?item.mime.startsWith('image/'):query.get('type')==='documents'?!item.mime.startsWith('image/'):true);
     return {items:candidates,total:candidates.length,used_bytes:1450000,quota_bytes:15000000000,
      personal_used_bytes:2000000,personal_quota_bytes:5000000000,
      workspace_used_bytes:1000000,workspace_quota_bytes:10000000000,max_upload_bytes:3000000};
   }
   throw Error('Unexpected API '+path);
 };
 const script=doc.createElement('script');script.textContent=fs.readFileSync('apps/web/workspace-vault.js','utf8');doc.head.append(script);
 await w.SmetraVault.render();await tick();
 assert.equal(doc.querySelector('#vault-usage').textContent,'2.0 МБ из 5.00 ГБ','account meter must not sum workspace capacity');
 assert.equal(doc.querySelector('#vault-team-usage').textContent,'1.0 МБ из 10.00 ГБ','workspace meter displays independent capacity');
 assert.ok(doc.querySelector('#vault-upload'),'personal uploads are available even if team membership is viewer');
 assert.equal(doc.querySelectorAll('.vault-image-tile').length,1);
 assert.equal(doc.querySelectorAll('.vault-image-tile [data-action=open]').length,1,'the photo preview doubles as the open action');
 assert.ok(doc.querySelector('.vault-action-more summary svg'),'the editable personal file has an icon menu');
 assert.equal(doc.querySelectorAll('.vault-action-dropdown button').length,3);
 assert.ok(!doc.querySelector('.vault-image-tile .vault-item-actions [data-action=open]'),'no redundant open button on pictures');
 doc.querySelector('[data-filter=files]').click();await tick();await tick();
 assert.equal(doc.querySelectorAll('.vault-file-tile').length,1);
 assert.equal(doc.querySelectorAll('.vault-file-tile .vault-action-dropdown button').length,0,'viewer cannot edit shared files');
 assert.equal(doc.querySelector('#vault-search').getAttribute('aria-label'),'Поиск файлов');
 assert.equal(doc.querySelectorAll('.vault-file-tile .vault-action-primary').length,2);
 assert.equal(notices.length,0);
 dom.window.close();console.log('PASS: personal/team quota, responsive action structure, gallery, viewer permissions and file tabs');
})().catch(error=>{console.error(error);process.exit(1)});
