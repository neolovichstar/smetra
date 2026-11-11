const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function setup(){
 const dom=new JSDOM('<div id="content"></div>',{url:'https://example.test/app#billing',runScripts:'outside-only',pretendToBeVisual:true}),w=dom.window;
 w.user={id:'owner',plan:'free',entitlement_until:0};w.authRevision=1;w.tab='billing';w.escapeHtml=value=>String(value??'');w.rub=value=>String(value);w.date=()=>'';
 const notices=[];w.notify=value=>notices.push(value);w.view=html=>w.document.querySelector('#content').innerHTML=html;
 const offer={email_verified:true,checkout_mode:'live',payments:[],pricing:{
  plans:{
   pro_month:{name:'PRO Solo',amount_kopecks:49000,duration_days:31},pro_year:{name:'PRO Solo',amount_kopecks:490000,duration_days:366},
   pro_plus_month:{name:'PRO Плюс',amount_kopecks:69000,duration_days:31},pro_plus_year:{name:'PRO Плюс',amount_kopecks:690000,duration_days:366},
   team_month:{name:'TEAM',amount_kopecks:399000,duration_days:31},team_year:{name:'TEAM',amount_kopecks:3990000,duration_days:366},
   business_month:{name:'BUSINESS',amount_kopecks:999000,duration_days:31},business_year:{name:'BUSINESS',amount_kopecks:9990000,duration_days:366}
  },
  catalog:[
   {id:'pro_solo',name:'PRO Solo',price_kopecks:49000,plan:'pro_month',annual_plan:'pro_year',seat_limit:1,features:['До 10 000 смет']},
   {id:'pro_plus',name:'PRO Плюс',price_kopecks:69000,plan:'pro_plus_month',annual_plan:'pro_plus_year',seat_limit:1,features:['Облако до 5 ГБ']},
   {id:'team_company',name:'TEAM',price_kopecks:399000,plan:'team_month',annual_plan:'team_year',seat_limit:5,features:['Объектные чаты']},
   {id:'business_partner',name:'BUSINESS',price_kopecks:999000,plan:'business_month',annual_plan:'business_year',seat_limit:15,features:['До 15 участников']}
  ],
  purchase_bonus:{pro_month:50,pro_year:300,pro_plus_month:0,pro_plus_year:0,team_month:0,team_year:0,business_month:0,business_year:0},
  annual_saving_kopecks:98000,limits:{free_quotes:10,pro_quotes:10000,pro_ai:100}
 }};
 let resolve,calls=0,version=0;
 w.api=async path=>path==='/billing'?offer:path==='/billing/sync'?(calls++,new Promise(r=>resolve=r)):{};
 w.eval(fs.readFileSync('apps/web/growth.js','utf8'));
 const render=async()=>{const mine=++version;await w.SmetraGrowth.billing(()=>mine===version&&w.tab==='billing')};w.render=render;
 return {dom,w,offer,notices,render,finish:value=>resolve(value),calls:()=>calls};
}
(async()=>{
 {
  const x=setup();await x.render();
  assert.equal(x.w.document.querySelectorAll('[data-tier]').length,4,'Four paid tiers render from the API catalog');
  x.w.document.querySelector('[data-tier="team_company"]').click();
  assert.equal(x.w.document.querySelector('#upgrade-checkout').dataset.plan,'team_month');
  x.w.document.querySelector('[data-period="pro_year"]').click();
  assert.equal(x.w.document.querySelector('#upgrade-checkout').dataset.plan,'team_year');
  x.w.document.querySelector('[data-tier="pro_solo"]').click();
  assert.equal(x.w.document.querySelector('#upgrade-checkout').dataset.plan,'pro_month');
  x.w.document.querySelector('#sync').click();await tick();x.w.tab='quotes';x.w.view('<p>Quotes</p>');
  x.finish({user:{id:'owner',plan:'pro'},payments:[]});await tick();assert.equal(x.w.user.plan,'free');assert.equal(x.w.document.querySelector('#content').textContent,'Quotes');assert.deepEqual(x.notices,[]);x.dom.window.close();
 }
 {
  const x=setup();await x.render();x.w.document.querySelector('#sync').click();await tick();x.w.authRevision++;
  x.finish({user:{id:'owner',plan:'pro'},payments:[]});await tick();assert.equal(x.w.user.plan,'free','Changed session ignores previous payment response');x.dom.window.close();
 }
 {
  const x=setup();await x.render();x.w.document.querySelector('#sync').click();await tick();await x.render();x.w.document.querySelector('#sync').click();await tick();assert.equal(x.calls(),1,'Rerender cannot create a second concurrent sync');
  x.finish({user:{id:'owner',plan:'free'},payments:[]});await tick();await tick();assert.equal(x.w.user.plan,'free');x.dom.window.close();
 }
 {
  const x=setup();x.w.user.plan='pro';x.w.user.entitlement_until=Date.now()/1000+1000;x.w.sessionStorage.setItem('smetra.checkout.owner.pro_month','pending-key');await x.render();x.w.document.querySelector('#sync').click();await tick();
  x.finish({user:{id:'owner',plan:'pro',entitlement_until:Date.now()/1000+1000},payments:[{status:'pending'}]});await tick();await tick();assert.equal(x.w.sessionStorage.getItem('smetra.checkout.owner.pro_month'),'pending-key','Existing Pro cannot erase a pending renewal key');x.dom.window.close();
 }
 console.log('PASS: payment sync ignores departed pages and sessions; concurrent checks share one request; pending renewal keeps its key');
})().catch(error=>{console.error(error);process.exit(1)});
