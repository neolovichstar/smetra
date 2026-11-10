/* Optional screens load when opened; failed loads remain retryable. */
(() => {
  // In-flight loads only. A script whose execution did not initialize its API
  // must be reloadable; retaining an already fulfilled Promise made Retry useless.
  const pending=new Map();
  const attempts=new Map();

  const features={
    markdown:{ready:()=>!!window.SmetraMarkdown,files:['/vendor/markdown-it-15.0.2.min.js?v=20261026-r21','/chat-markdown.js?v=20261108-ai1']},
    quoteVisuals:{ready:()=>!!window.SmetraQuoteVisuals&&!!window.SmetraQuoteLayout,files:['/quote-layout-renderer.js?v=20261108-designer1','/quote-visual-core.js?v=20261110-documents1']},
    assistant:{ready:()=>!!window.SmetraAssistant,deps:['markdown'],files:['/assistant-clipboard.js?v=20261109-recovery1','/assistant-chat.js?v=20261110-timer1']},
    knowledge:{ready:()=>!!window.SmetraKnowledgePanel,files:['/ai-workspace.js?v=20261109-recovery1']},
    profile:{ready:()=>!!window.SmetraProfile,files:['/profile-ui.js?v=20261110-mobile2']},
    dataExport:{ready:()=>!!window.SmetraDataExport,files:['/data-export.js?v=20261026-r21']},
    construction:{ready:()=>!!window.SmetraConstruction&&!!window.SmetraProcurementPlan,deps:['quoteVisuals'],files:['/procurement-plan.js?v=20261108-suppliers1','/construction.js?v=20261110-workflow1']},
    calculators:{ready:()=>!!window.SmetraCalculators,files:['/calculators.js?v=20261110-mobile2']},
    arScan:{ready:()=>!!window.SmetraARScan,files:['/ar-scan.js?v=20261108-ar5']},
    admin:{ready:()=>!!window.SmetraAdmin,files:['/admin.js?v=20261109-traffic-compact1']},
    growth:{ready:()=>!!window.SmetraGrowth&&!!window.SmetraPaymentUI,files:['/payment-ui.js?v=20261108-paywall1','/ecosystem-billing.js?v=20261109-checkout1','/growth.js?v=20261108-paywall1']},
    quoteReview:{ready:()=>!!window.SmetraQuoteReview,files:['/quote-review.js?v=20261110-workflow1']},
    estimateAudit:{ready:()=>!!window.SmetraEstimateAudit,files:['/estimate-audit.js?v=20261026-r21']},
    quoteEditor:{ready:()=>!!window.SmetraQuoteEditorState&&!!window.SmetraEstimateAudit,deps:['estimateAudit'],files:['/quote-editor-state.js?v=20261026-r21']},
    objectChats:{ready:()=>!!window.SmetraObjectChats,files:['/object-chats.js?v=20261026-r21']},
    premiumTools:{ready:()=>!!window.SmetraPremiumTools,files:['/premium-tools.js?v=20261028-autosync1']},
  };
  const load=source=>{
    if(pending.has(source))return pending.get(source);
    const attempt=(attempts.get(source)||0)+1;
    attempts.set(source,attempt);
    const request=new Promise((resolve,reject)=>{
      const script=document.createElement('script');
      // A cached but partially evaluated script must not strand the page
      // indefinitely. On retries ask for a fresh response.
      script.src=attempt===1?source:source+(source.includes('?')?'&':'?')+'recovery='+attempt;
      script.async=false;
      let settled=false;
      const finish=error=>{
        if(settled)return;
        settled=true;clearTimeout(timer);
        if(error){script.remove();reject(error)}
        else resolve();
      };
      const timer=setTimeout(()=>finish(Error('Раздел загружается слишком долго. Повторите попытку.')),10000);
      script.onload=()=>finish();
      script.onerror=()=>finish(Error('Не удалось загрузить раздел. Проверьте интернет и повторите попытку.'));
      document.head.append(script);
    });
    pending.set(source,request);
    // Do not retain either resolved or rejected loads. Otherwise onload can
    // fire without the JS evaluating, and Retry will forever reuse that result.
    void request.then(
      ()=>{if(pending.get(source)===request)pending.delete(source)},
      ()=>{if(pending.get(source)===request)pending.delete(source)}
    );
    return request;
  };
  window.SmetraLoadFeature=async name=>{
    const feature=features[name];if(!feature)throw Error('Раздел не найден');
    if(feature.ready())return;
    for(const dependency of feature.deps||[])await window.SmetraLoadFeature(dependency);
    await Promise.all(feature.files.map(load));
    if(feature.ready())return;
    // One fresh retry for an asset that fetched successfully but failed to
    // initialize (including a stale HTTP/browser cache entry).
    await Promise.all(feature.files.map(load));
    if(!feature.ready())throw Error('Не удалось запустить раздел. Повторите попытку.');
  };
  let warmed=false;
  window.SmetraWarmFeatures=()=>{
    if(warmed||navigator.connection?.saveData||/2g/.test(navigator.connection?.effectiveType||''))return;
    warmed=true;
    const run=()=>{
      const files=new Set(Object.values(features).flatMap(feature=>[...(feature.deps||[]).flatMap(dep=>features[dep]?.files||[]),...feature.files]));
      for(const source of files){if(pending.has(source))continue;const href=new URL(source,location.href).href;if(document.querySelector(`link[rel="prefetch"][href="${href}"]`))continue;const link=document.createElement('link');link.rel='prefetch';link.as='script';link.href=source;document.head.append(link);}
    };
    if(window.requestIdleCallback)window.requestIdleCallback(run,{timeout:3500});else setTimeout(run,900);
  };
})();
