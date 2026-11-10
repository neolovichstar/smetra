// Own emulator + disposable fixture only. No publisher traffic or real rewards.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const {_android}=require(process.env.SMETRA_PLAYWRIGHT_MODULE||'playwright');
const adb=process.env.SMETRA_ADB||'D:/Android/Sdk/platform-tools/adb.exe',device='emulator-5556',pkg='ru.smetra.mobile';
const fixture=JSON.parse(fs.readFileSync('data/protected-estimates-fixture.json','utf8'));
assert.match(fixture.base,/^http:\/\/127\.0\.0\.1:\d+$/);
const origin=fixture.base.replace('127.0.0.1','10.0.2.2');
const run=(...args)=>execFileSync(adb,['-s',device,...args],{encoding:'utf8'}).trim();
const out='data/qa/mobile-2.2-native';fs.mkdirSync(out,{recursive:true});
const escape=value=>String(value).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function connect(){
 const device=(await _android.devices()).find(d=>d.serial()==='emulator-5556');assert(device,'Own emulator only');
 const view=await device.webView({pkg}),page=await view.page(),context=page.context();
 assert(page.url().startsWith(origin),'Own WebView uses the fixture');
 return {browser:{close:()=>device.close()},context,page};
}
(async()=>{
 let {browser,context,page}=await connect();
 await page.locator('#smetra-guest').waitFor();
 const hello=await page.evaluate(()=>SmetraShell.call('app.hello'));
 assert(hello.features.review&&hello.features.rewardRecovery);
 assert.equal(await page.evaluate(()=>SmetraShell.call('ads.rewarded.show').then(()=>null,e=>e.code)),'unauthorized');
 await page.screenshot({path:out+'/guest.png'});
 const cdp=await context.newCDPSession(page);
 await cdp.send('Network.setCookie',{name:'session',value:fixture.owner.token,url:origin,httpOnly:true,sameSite:'Lax',expires:Math.floor(Date.now()/1000)+86400});
 await page.reload();await page.locator('#shell').waitFor({state:'visible'});
 await page.evaluate(()=>SmetraShell.call('app.review.qualify',{key:'qa-save:1'}));
 // Issue a synthetic attempt through the real API, then simulate an already
 // earned, persisted SDK callback. This tests restart recovery, not an ad view.
 const response=await fetch(fixture.base+'/api/assistant/ad-reward',{method:'POST',headers:{Authorization:'Bearer '+fixture.owner.token,'Content-Type':'application/json'},body:JSON.stringify({operation:'start',provider:'vk'})});
 const attempt=await response.json();assert.equal(response.status,200,JSON.stringify(attempt));
 run('shell','am','force-stop',pkg);await browser.close();
 const xml='<?xml version="1.0" encoding="utf-8" standalone="yes" ?><map><string name="pending:'+escape(fixture.owner.id)+'">'+escape(JSON.stringify(attempt))+'</string></map>';
 execFileSync(adb,['-s',device,'shell',`run-as ${pkg} sh -c 'mkdir -p shared_prefs; cat > shared_prefs/smetra-earned-ads.xml'`],{input:xml,encoding:'utf8'});
 run('shell','am','start','-W','-n',pkg+'/.ShellActivity');
 ({browser,context,page}=await connect());await page.locator('#shell').waitFor({state:'visible'});
 await page.evaluate(()=>SmetraShell.ready);
 await page.evaluate(()=>SmetraShell.call('ads.rewarded.recover',{}, {timeout:30000}).catch(e=>({code:e.code})));
 // Bootstrap may already have started the same recovery; wait for its real
 // backend credit rather than issuing a second grant from the test.
 let wallet=0;
 for(let i=0;i<20;i++){
  const q=await fetch(fixture.base+'/api/assistant/ad-reward',{headers:{Authorization:'Bearer '+fixture.owner.token}}).then(r=>r.json());wallet=q.quota?.wallet||0;
  if(wallet===45000)break;await new Promise(resolve=>setTimeout(resolve,250));
 }
 assert.equal(wallet,45000,'The earned claim survives process restart');
 assert(!run('shell','run-as',pkg,'cat','shared_prefs/smetra-earned-ads.xml').includes('pending:'),'Successful pending claim removed');
 await page.evaluate(()=>SmetraShell.call('ads.rewarded.recover'));
 const q=await fetch(fixture.base+'/api/assistant/ad-reward',{headers:{Authorization:'Bearer '+fixture.owner.token}}).then(r=>r.json());
 assert.equal(q.quota.wallet,45000,'Repeated recovery cannot double the wallet');
 await page.screenshot({path:out+'/signed-in.png'});
 await browser.close();
 fs.writeFileSync(out+'/result.json',JSON.stringify({guest:true,nativeCapabilities:true,guestAdDenied:true,normalSession:true,reviewCall:true,restartRecovery:true,idempotentRecovery:true,advertisementPlayback:false},null,2));
 console.log('PASS: Android emulator/WebView guest, native bridge, normal session, review qualification, synthetic earned claim restored across process restart exactly once; no live ad playback tested');
})().catch(error=>{console.error(error);process.exit(1)});
