/* Price impact frontend may display supplier observations but cannot write quotes. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');
const code=fs.readFileSync('apps/web/price-impact.js','utf8');
(async()=>{
  const dom=new JSDOM('<!doctype html><main class="premium-tools-page"><section class="premium-section"></section><section class="premium-section"></section></main>',{url:'https://smetra.test/app#premium',runScripts:'dangerously'});
  const w=dom.window,requests=[],submitted=[];
  w.api=async(path,options)=>{
    requests.push(path);submitted.push(options);
    if(path==='/premium/price-impact?quote_id=quote-1')return {
      quote_id:'quote-1',revision:7,currency:'RUB',
      original_total_kopecks:100000,indicative_total_kopecks:105000,
      comparable_delta_kopecks:5000,comparable_lines:1,
      lines:[
        {line_id:'line-1',name:'Кабель <img src=x onerror=alert(1)>',quantity:'5',unit:'м',status:'comparable',delta_kopecks:5000,quote_unit_price_kopecks:10000,supplier_unit_price_kopecks:11000,delta_percent:'10.00'},
        {line_id:'line-2',name:'Краска',quantity:'2',unit:'л',status:'unit_mismatch'}
      ]};
    throw Error('Unexpected call: '+path);
  };
  w.eval(code);
  w.SmetraPriceImpact.mount([{id:'quote-1',title:'Ремонт <script>alert(1)</script>'}]);
  const $=s=>w.document.querySelector(s);
  assert.ok($('#spi-section'));
  assert.equal(w.document.querySelectorAll('script').length,0,'Untrusted quote name escaped');
  assert.equal(requests.length,0,'No price queries without explicit user action');
  assert.equal($('#spi-check').disabled,true);
  $('#spi-quote').value='quote-1';$('#spi-quote').dispatchEvent(new w.Event('change',{bubbles:true}));
  assert.equal($('#spi-check').disabled,false);
  $('#spi-check').click();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.length,1);
  assert.ok($('#spi-report').textContent.includes('+50'));
  assert.ok($('#spi-report').textContent.includes('Единицы не совпадают'));
  assert.equal($('#spi-report').querySelectorAll('img').length,0);
  assert.ok($('#spi-report').textContent.includes('не изменяются автоматически'));
  assert.equal(submitted[0],undefined,'Price impact API must only perform GET');
  dom.window.close();
  console.log('PASS: read-only price impact, opt-in GET, safe labels and unit mismatch display');
})().catch(error=>{console.error(error);process.exitCode=1});
