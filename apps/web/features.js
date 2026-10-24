/* Optional screens load when opened; failed loads remain retryable. */
(() => {
  const pending=new Map();

  const features={
    markdown:{ready:()=>!!window.SmetraMarkdown,files:['/vendor/markdown-it-15.0.2.min.js?v=20261025-r2','/chat-markdown.js?v=20261025-r2']},
    quoteVisuals:{ready:()=>!!window.SmetraQuoteVisuals&&!!window.SmetraQuoteLayout,files:['/quote-layout-renderer.js?v=20261025-r2','/quote-visual-core.js?v=20261025-r2']},
    assistant:{ready:()=>!!window.SmetraAssistant&&!!window.SmetraKnowledgePanel,deps:['markdown','quoteVisuals'],files:['/assistant-chat.js?v=20261025-r2','/ai-workspace.js?v=20261025-r2']},
    profile:{ready:()=>!!window.SmetraProfile,files:['/profile-ui.js?v=20261025-r2']},
    dataExport:{ready:()=>!!window.SmetraDataExport,files:['/data-export.js?v=20261025-r2']},
    construction:{ready:()=>!!window.SmetraConstruction,deps:['quoteVisuals'],files:['/construction.js?v=20261025-r2']},
    calculators:{ready:()=>!!window.SmetraCalculators,files:['/calculators.js?v=20261025-r2']},
    admin:{ready:()=>!!window.SmetraAdmin,files:['/admin.js?v=20261025-r2']},
    growth:{ready:()=>!!window.SmetraGrowth,files:['/ecosystem-billing.js?v=20261025-r2','/growth.js?v=20261025-r2']},
    quoteReview:{ready:()=>!!window.SmetraQuoteReview,files:['/quote-review.js?v=20261025-r2']},
    estimateAudit:{ready:()=>!!window.SmetraEstimateAudit,files:['/estimate-audit.js?v=20261025-r2']},
    quoteEditor:{ready:()=>!!window.SmetraQuoteEditorState&&!!window.SmetraEstimateAudit,deps:['estimateAudit'],files:['/quote-editor-state.js?v=20261025-r2']},
    objectChats:{ready:()=>!!window.SmetraObjectChats,files:['/object-chats.js?v=20261025-r2']},
    premiumTools:{ready:()=>!!window.SmetraPremiumTools,files:['/premium-tools.js?v=20261025-r2']},
  };
  const load=source=>{
    if(pending.has(source))return pending.get(source);
    const request=new Promise((resolve,reject)=>{
      const script=document.createElement('script');script.src=source;script.async=false;
      const timer=setTimeout(()=>fail(),15000);
      const fail=()=>{clearTimeout(timer);script.remove();pending.delete(source);reject(Error('Не удалось загрузить раздел. Проверьте интернет и повторите попытку.'))};
      script.onload=()=>{clearTimeout(timer);resolve()};script.onerror=fail;document.head.append(script);
    });
    pending.set(source,request);return request;
  };
  window.SmetraLoadFeature=async name=>{
    const feature=features[name];if(!feature)throw Error('Раздел не найден');
    if(feature.ready())return;
    for(const dependency of feature.deps||[])await window.SmetraLoadFeature(dependency);
    // Ordered classic scripts retain execution order while fetching concurrently.
    await Promise.all(feature.files.map(load));
    if(!feature.ready())throw Error('Не удалось открыть раздел. Повторите попытку.');
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
