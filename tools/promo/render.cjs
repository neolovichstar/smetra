const { chromium } = require('playwright');const fs=require('fs');
const [mode, ...rest]=process.argv.slice(2);
(async()=>{// SOFTWARE_GL=1 renders on the CPU (servers without a GPU); otherwise the GPU is used.
const b=await chromium.launch(process.env.SOFTWARE_GL?{args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist']}:{headless:true,args:['--ignore-gpu-blocklist','--enable-gpu']});
const p=await b.newPage({viewport:{width:1920,height:1080}});
const errs=[];p.on('pageerror',e=>errs.push(e.message));p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});
await p.goto((process.env.ORIGIN||'http://localhost:8000')+'/tools/promo/promo.html');
await p.waitForFunction(()=>window.READY===true,null,{timeout:60000}).catch(()=>{});
if(errs.length){console.log(errs.join('\n'));}
const el=await p.$('#out');
if(mode==='frames'){fs.mkdirSync(__dirname+'/test',{recursive:true});for(const f of rest.map(Number)){await p.evaluate(f=>renderFrame(f),f);await el.screenshot({path:`${__dirname}/test/f${String(f).padStart(4,'0')}.png`});}}
else{fs.mkdirSync(__dirname+'/frames',{recursive:true});const N=await p.evaluate(()=>FRAMES);const t0=Date.now();const [a,z]=[+(rest[0]||0),+(rest[1]||N)];
 for(let f=a;f<Math.min(z,N);f++){if(fs.existsSync(`${__dirname}/frames/${String(f).padStart(4,'0')}.jpg`))continue;const data=await p.evaluate(f=>{renderFrame(f);return document.getElementById('out').toDataURL('image/jpeg',0.95)},f);
  fs.writeFileSync(`${__dirname}/frames/${String(f).padStart(4,'0')}.jpg`,Buffer.from(data.split(',')[1],'base64'));
  if(f%60===0)console.log(f,N,((Date.now()-t0)/1000).toFixed(0)+'s');}}
await b.close()})();
