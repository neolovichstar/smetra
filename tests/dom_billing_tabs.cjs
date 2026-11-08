/* Billing switch: selected thumb, tab semantics and number spinner regression. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {JSDOM}=require(process.env.SMETRA_JSDOM_MODULE||'jsdom');

(async()=>{
  const base=fs.readFileSync('apps/web/ui/base.css','utf8');
  const styles=fs.readFileSync('apps/web/ui/workspace.css','utf8');
  const app=fs.readFileSync('apps/web/app.html','utf8');
  const featureManifest=fs.readFileSync('apps/web/features.js','utf8');
  assert.match(base,/input\[type="number"\]::-webkit-inner-spin-button/,'WebKit steppers are hidden globally');
  assert.match(base,/input\[type="number"\]\{-moz-appearance:textfield;appearance:textfield\}/,'Firefox steppers are hidden globally');
  assert.match(styles,/\.billing-switch\.is-tokens::before\{transform:translateX\(/,'Billing thumb slides instead of jumping between backgrounds');
  assert.match(styles,/@media \(prefers-reduced-motion:reduce\)/,'System reduced-motion preference is respected');
  assert.match(styles,/#billing-plans:not\(\[hidden\]\),#billing-tokens:not\(\[hidden\]\)/,'Both panels have an entrance transition');
  assert.match(app,/ui\/base\.css\?v=20261108-spinner1/,'Spinner styles must not be served from old cache');
  assert.match(app,/ui\/workspace\.css\?v=20261108-profile1/,'Billing styles must not be served from old cache');
  assert.match(featureManifest,/ecosystem-billing\.js\?v=20261108-tabs1/,'Billing JS must not be served from old cache');

  const dom=new JSDOM('<!doctype html><html><body><main id="content"></main></body></html>',{
    url:'https://smetra.test/app',runScripts:'dangerously',pretendToBeVisual:true
  });
  const w=dom.window,doc=w.document;
  try{
    w.user={id:'user-1'};w.authRevision=1;
    w.escapeHtml=s=>String(s??'');
    w.date=()=> '01.01.2027';w.rub=n=>String(n)+' ₽';
    w.view=html=>{doc.querySelector('#content').innerHTML=html};
    w.api=async()=>({quota:{unit:'tokens',remaining:5000,monthly_used:0,monthly_limit:10000,wallet:0,resets_at:0}});
    w.render=async()=>{};
    w.eval(fs.readFileSync('apps/web/ecosystem-billing.js','utf8'));
    const pricing={catalog:{starter:{},pro_solo:{},pro_plus:{},team:{}},plans:{}};
    const billing={pricing,email_verified:false,checkout_mode:'off',payments:[],tokens:{
      bands:[{up_to_millions:100,kopecks_per_million:10000}],
      packs:[{label:'Пакет',millions:1,amount_kopecks:10000,saving_kopecks:0,featured:false}],
      min_millions:1,max_millions:20
    }};
    const owner=w.user,space={workspace:{id:'workspace-1',owner_id:owner.id},entitlements:{tier:'starter'}};
    w.sessionStorage.setItem('smetra.billing.view','tokens');
    await w.SmetraBillingCatalog(()=>true,billing,space,owner,1);

    const switcher=doc.querySelector('.billing-switch'),plans=doc.querySelector('#billing-tab-plans'),tokens=doc.querySelector('#billing-tab-tokens');
    assert.ok(switcher?.classList.contains('is-tokens'),'Deep link should paint the correct thumb immediately');
    assert.equal(tokens.getAttribute('aria-selected'),'true');
    assert.equal(plans.getAttribute('aria-selected'),'false');
    assert.equal(doc.querySelector('#billing-plans').hidden,true);
    assert.equal(doc.querySelector('#billing-tokens').hidden,false);
    assert.equal(doc.querySelector('#token-amount').getAttribute('type'),'number','Numeric field remains a validated number');

    plans.click();
    assert.equal(switcher.classList.contains('is-tokens'),false);
    assert.equal(plans.getAttribute('aria-selected'),'true');
    assert.equal(tokens.getAttribute('aria-selected'),'false');
    assert.equal(doc.querySelector('#billing-plans').hidden,false);
    assert.equal(doc.querySelector('#billing-tokens').hidden,true);

    const right=new w.KeyboardEvent('keydown',{bubbles:true,key:'ArrowRight',cancelable:true});
    plans.dispatchEvent(right);
    assert.equal(right.defaultPrevented,true,'Arrow keys remain keyboard-operable');
    assert.equal(switcher.classList.contains('is-tokens'),true);
    assert.equal(tokens.getAttribute('aria-selected'),'true');
    assert.equal(doc.querySelector('#billing-plans').hidden,true);
    assert.equal(doc.querySelector('#billing-tokens').hidden,false);
    console.log('PASS: no numeric steppers; billing slider, panel transitions, initial selection and keyboard tabs');
  }finally{dom.window.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
