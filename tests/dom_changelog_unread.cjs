'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return{promise,resolve,reject}};
function setup(){
  const dom=new JSDOM('<body><aside id="sidebar"><div class="sidebar-group"><button data-tab="changelog">Что нового</button></div></aside><main id="content"></main><div id="toast"></div></body>',{url:'https://smetra.test/app#changelog',runScripts:'dangerously'}),w=dom.window,d=w.document;
  const load=source=>{const script=d.createElement('script');script.textContent=source;d.head.append(script)};
  w.matchMedia=()=>({matches:false,addEventListener(){}});w.scrollTo=()=>{};
  load(fs.readFileSync('apps/web/app.js','utf8').split("if($('#auth')){")[0]);
  w.eval("user={id:'reader',name:'Читатель',role:'user'};tab='changelog'");
  const items=['one','two'].map(id=>({id,title:'Обновление '+id,body:'Текст '+id,published:1,published_at:1,view_count:0,likes:0,dislikes:0}));
  const viewed=new Set(),posts=new Map(),unreadQueue=[];
  let feedCalls=0,failFeed=false;
  const unread=()=>items.filter(item=>item.published&&!viewed.has(item.id)).length;
  w.api=async(path,options={})=>{
    if(path==='/changelog/unread')return unreadQueue.length?unreadQueue.shift().promise:{unread_count:unread()};
    if(path==='/changelog'){
      feedCalls++;if(failFeed)throw Error('Лента недоступна');
      return{items:items.map(item=>({...item,has_viewed:viewed.has(item.id)?1:0})),can_publish:false,unread_count:unread()};
    }
    const match=path.match(/^\/changelog\/([^/]+)\/view$/);
    if(match&&options.method==='POST'){
      assert.ok(!posts.has(match[1]),'A pending read is sent once');
      const request=deferred();posts.set(match[1],request);
      await request.promise;viewed.add(match[1]);return{viewed:true};
    }
    throw Error('Unexpected '+path);
  };
  w.SmetraLoadFeature=async()=>{};w.SmetraMarkdown={render:body=>'<p>'+body+'</p>'};
  load(fs.readFileSync('apps/web/workspace-vault.js','utf8'));
  const button=d.querySelector('[data-tab=changelog]');
  return{w,d,items,viewed,posts,unreadQueue,button,count:()=>Number(button.dataset.unread||0),feedCalls:()=>feedCalls,failFeed:value=>failFeed=value,close:()=>w.close()};
}
(async()=>{
  {
    const e=setup();try{
      await e.w.SmetraVault.renderNews();assert.equal(e.count(),2,'Collapsed updates remain unread');
      const stale=deferred();e.unreadQueue.push(stale);const oldRefresh=e.w.SmetraReleaseUnread.refresh(true);
      e.d.querySelector('[data-note=one]').click();await tick();
      assert.equal(e.count(),1,'Reading clears its badge before the server responds');
      assert.equal(e.d.querySelector('[data-id=one] .changelog-new-indicator'),null);
      stale.resolve({unread_count:2});await oldRefresh;assert.equal(e.count(),1,'A stale unread response cannot restore a read update');
      e.d.querySelector('[data-note=two]').click();await tick();
      assert.equal(e.count(),0);assert.equal(e.button.querySelector('.sidebar-unread-badge'),null);assert.equal(e.button.getAttribute('aria-label'),'Что нового');
      const body=e.d.querySelector('#changelog-content-two');
      e.posts.get('one').resolve();await tick();assert.equal(e.count(),0,'Another pending read keeps the optimistic count');
      e.posts.get('two').resolve();await tick();await tick();
      assert.equal(e.d.querySelector('#changelog-content-two'),body,'Acknowledgement preserves the open content');
      assert.equal(e.feedCalls(),1,'Read acknowledgement does not repaint the feed');
      e.w.eval("tab='assistant'");await e.w.SmetraReleaseUnread.refresh(true);assert.equal(e.count(),0);
      e.w.eval("tab='changelog'");await e.w.SmetraVault.renderNews();assert.equal(e.count(),0,'Server views persist across navigation');
    }finally{e.close()}
  }
  {
    const e=setup();try{
      await e.w.SmetraVault.renderNews();e.d.querySelector('[data-note=one]').click();await tick();
      const body=e.d.querySelector('#changelog-content-one');assert.equal(e.count(),1);
      e.posts.get('one').reject(Error('Не удалось сохранить прочтение'));await tick();await tick();
      assert.equal(e.count(),2,'A failed acknowledgement restores unread count');
      assert.ok(e.d.querySelector('[data-id=one] .changelog-new-indicator'));
      assert.equal(e.d.querySelector('#changelog-content-one'),body,'Rollback preserves reading position and content');
      e.failFeed(true);await assert.rejects(e.w.SmetraVault.renderNews(),/Лента недоступна/);assert.equal(e.count(),2,'A failed feed load preserves unread count');
    }finally{e.close()}
  }
  {
    const e=setup();try{
      await e.w.SmetraVault.renderNews();e.d.querySelector('[data-note=one]').click();await tick();
      e.d.querySelector('[data-note=one]').click();await tick();e.d.querySelector('[data-note=one]').click();await tick();
      assert.equal(e.count(),1,'Reopening a pending read never decrements twice');assert.equal(e.posts.size,1);
      e.items.push({id:'new',published:1});e.posts.get('one').resolve();await tick();await tick();
      assert.equal(e.count(),2,'A newly published update remains unread after reconciliation');
      assert.ok(!e.viewed.has('new'));
    }finally{e.close()}
  }
  {
    const e=setup();try{
      await e.w.SmetraVault.renderNews();e.d.querySelector('[data-note=one]').click();await tick();
      e.w.SmetraReleaseUnread.reset();e.w.eval("user={id:'another-reader'}");e.w.SmetraReleaseUnread.set(7);
      e.posts.get('one').resolve();await tick();await tick();assert.equal(e.count(),7,'An old account read cannot change another account badge');
    }finally{e.close()}
  }
  console.log('PASS: instant per-update unread badges, stale response protection, rollback, navigation and account isolation');
})().catch(error=>{console.error(error);process.exitCode=1});
