const { chromium } = require('playwright');const fs=require('fs');
const TOKEN=fs.readFileSync(process.env.TOKEN_FILE,'utf8').trim();const O='http://localhost:8097';
(async()=>{const b=await chromium.launch();
const ctx=await b.newContext({viewport:{width:390,height:800},deviceScaleFactor:3,isMobile:true,hasTouch:true,bypassCSP:true});
await ctx.addCookies([{name:'session',value:TOKEN,url:O+'/',httpOnly:true,sameSite:'Lax'}]);
await ctx.addInitScript(()=>{try{localStorage.setItem('smetra_theme','dark')}catch(e){}
  // OLED: true black canvas, cards a touch above it.
  document.addEventListener('DOMContentLoaded',()=>{const st=document.createElement('style');st.textContent=':root,:root[data-theme=dark]{--bg:#000!important;--bg-sunken:#000!important;--surface-1:#0b0b0c!important;--surface-2:#111113!important;--surface-3:#18181a!important;--surface-4:#1f1f22!important}body,.main,#content{background:#000!important}';document.head.appendChild(st);});
});
const p=await ctx.newPage();
const go=async(h,fn,name)=>{await p.goto(O+'/app#'+h);try{await p.waitForFunction(()=>document.querySelector('#content h1, #content .assistant-message')&&!document.querySelector('#content .page-loading'),null,{timeout:8000})}catch(e){}await p.waitForTimeout(900);if(fn)await fn();await p.waitForTimeout(900);await p.screenshot({path:__dirname+'/scr/'+name+'.png'});console.log(name);};
await go('dashboard',null,'dashboard');
await go('quotes',null,'quotes');
await go('quotes',async()=>{await p.locator('[data-work=quote]').filter({hasText:'Ремонт'}).first().click();},'quote');
await go('assistant',null,'assistant');
await go('construction',async()=>{await p.locator('.construction-object').first().click();},'object');
await go('finance',null,'finance');
await go('calculators',null,'calculators');
await go('projects',null,'projects');
await b.close()})();
