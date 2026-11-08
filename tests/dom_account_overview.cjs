'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
function setup(){
 const dom=new JSDOM('<body><main id="content"></main><button id="theme"></button><div id="toast"></div></body>',{url:'https://smetra.test/app#profile',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window,d=w.document;
 const load=source=>{const el=d.createElement('script');el.textContent=source;d.head.append(el);};
 w.matchMedia=()=>({matches:false,addEventListener(){}});w.scrollTo=()=>{};
 load(fs.readFileSync('apps/web/app.js','utf8').split("if($('#auth')){")[0]);
 w.eval("user={id:'owner',name:'Анна Иванова',email:'anna@example.test',email_verified:true};tab='profile'");
 w.Workspace={render:async()=>false};
 const usage={plan:{name:'Старт'},tokens:{used:10000,limit:60000,remaining:50000,remaining_pct:83,wallet:3000,resets_at:1900000000},quotes:{used:1,limit:3,remaining:2,remaining_pct:66},storage:{used:1000,limit:1000000,remaining:999000,remaining_pct:99},seats:{used:1,limit:1,remaining:0,remaining_pct:0},records:{quotes:2,clients:1,projects:1,files:1},history:{spent:10000,added:3000,entries:[{id:'debit',bucket:'monthly',delta:-10000,reason:'assistant',created_at:1}]}};
 const currencies=['RUB','EUR'].map((currency,index)=>({currency,received:10000+index*10000,spent:3000,balance:7000+index*10000,received_month:5000,spent_month:1000,balance_month:4000,months:[{month:'2026-11',received:5000,spent:1000}]}));
 const summary={workspace:{name:'Моя студия',currency:'RUB'},counts:{quotes:2,objects:1,active_projects:1,completed_projects:0,clients:1,conversations:3},quote_states:{draft:1,approved:1},recent_quotes:[],money:{as_of:'2026-11-08',currencies}};
 let failUsage=false;
 w.api=async path=>{if(path==='/profile-summary')return summary;if(path==='/profile')return{profile:{first_name:'Анна',last_name:'Иванова',company:'Студия',profession:'Отделка',about:'',response_style:'concise',memory_enabled:1}};if(path==='/usage'){if(failUsage)throw Error('Временная ошибка API');return usage}if(path==='/profile/id')return{public_id:'SM-ANNA'};throw Error('Unexpected '+path)};
 for(const file of ['ui/icons.js','profile-ui.js'])load(fs.readFileSync('apps/web/'+file,'utf8'));
 return{w,d,summary,usage,failUsage:value=>failUsage=value,close:()=>dom.window.close()};
}
(async()=>{
 const e=setup();try{
  await e.w.render();const {w,d}=e;
  assert.deepEqual([...d.querySelectorAll('[data-account-section]')].map(b=>b.textContent),['Профиль','Использование','Настройки']);
  assert.ok(d.querySelector('.profile-overview'));assert.equal(d.querySelector('#profile-form'),null);assert.equal(d.querySelector('[data-hub-tab=public]'),null);
  assert.match(d.querySelector('[data-profile-money]').textContent,/100/);
  d.querySelector('[data-profile-currency=EUR]').click();assert.match(d.querySelector('.profile-money-metric strong').textContent,/200/);
  d.querySelector('[data-profile-period=month]').click();assert.match(d.querySelector('.profile-money-metric strong').textContent,/50/);
  w.eval("tab='settings'");await w.render();assert.ok(d.querySelector('.settings-top-tabs'));assert.ok(d.querySelector('[data-hub-tab=privacy]'));assert.equal(d.querySelector('[data-hub-tab=public]'),null);assert.ok(d.querySelector('#profile-form'));
  d.querySelector('[data-hub-tab=privacy]').click();assert.equal(d.querySelector('#hub-panel-privacy').hidden,false);assert.equal(d.querySelector('#hub-panel-details').hidden,true);
  w.eval("tab='usage'");e.failUsage(true);await w.render();assert.match(d.querySelector('#hub-usage-host').textContent,/Временная ошибка API/);assert.equal(d.querySelector('.usage-summary-grid'),null,'A failure does not turn into fake zero usage');
  e.failUsage(false);d.querySelector('#hub-usage-host button').click();await tick();await tick();assert.ok(d.querySelector('.usage-history'));assert.match(d.querySelector('.usage-summary-grid').textContent,/53[\s\u00a0]000/);assert.match(d.querySelector('.usage-history').textContent,/10[\s\u00a0]000/);
  e.summary.money=null;w.eval("tab='profile'");await w.render();assert.match(d.querySelector('[data-profile-money]').textContent,/правом просмотра финансов/);assert.equal(d.querySelector('.profile-money-grid'),null);
  console.log('PASS: account rail, horizontal privacy settings, scoped financial stats and detailed usage recovery');
 }finally{e.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
