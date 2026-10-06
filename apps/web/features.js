/* Optional screens load when opened; failed loads remain retryable. */
(() => {
  const pending=new Map();
  const features={
    markdown:{ready:()=>!!window.SmetraMarkdown,files:['/vendor/markdown-it-15.0.2.min.js','/chat-markdown.js']},
    assistant:{ready:()=>!!window.SmetraAssistant&&!!window.SmetraKnowledgePanel,deps:['markdown'],files:['/assistant-chat.js','/ai-workspace.js']},
    profile:{ready:()=>!!window.SmetraProfile,files:['/profile-ui.js']},
    construction:{ready:()=>!!window.SmetraConstruction,files:['/construction.js']},
    admin:{ready:()=>!!window.SmetraAdmin,files:['/admin.js']},
    growth:{ready:()=>!!window.SmetraGrowth,files:['/growth.js']},
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
    for(const file of feature.files)await load(file);
    if(!feature.ready())throw Error('Не удалось открыть раздел. Повторите попытку.');
  };
})();
