/* Optional screens load when opened; failed loads remain retryable. */
(() => {
  const pending=new Map();
  const features={
    markdown:{ready:()=>!!window.SmetraMarkdown,files:['/vendor/markdown-it-15.0.2.min.js','/chat-markdown.js']},
    assistant:{ready:()=>!!window.SmetraAssistant&&!!window.SmetraKnowledgePanel,deps:['markdown'],files:['/assistant-chat.js?v=20261022-glass-voice-v2','/ai-workspace.js']},
    profile:{ready:()=>!!window.SmetraProfile,files:['/profile-ui.js']},
    dataExport:{ready:()=>!!window.SmetraDataExport,files:['/data-export.js']},
    construction:{ready:()=>!!window.SmetraConstruction,files:['/construction.js']},
    admin:{ready:()=>!!window.SmetraAdmin,files:['/admin.js']},
    growth:{ready:()=>!!window.SmetraGrowth,files:['/growth.js']},
    quoteReview:{ready:()=>!!window.SmetraQuoteReview,files:['/quote-review.js']},
    quoteEditor:{ready:()=>!!window.SmetraQuoteEditorState,files:['/quote-editor-state.js']},
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
