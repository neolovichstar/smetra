'use strict';

/* Read-only personal memory overview. The assistant stores grounded facts via
   the existing server-side memory tools; there is no second manual editor. */
window.SmetraKnowledgePanel=async function(root){
  const personal=await api('/assistant/memory');
  if(!root.isConnected)return;
  const escape=s=>escapeHtml(String(s??''));
  const icon=(name,size=18)=>window.SmetraIcons?window.SmetraIcons.svg(name,size):'';
  const items=Array.isArray(personal.items)?personal.items.filter(item=>item.enabled):[];
  root.innerHTML=`<section class="knowledge-window memory-overview-window">
    <header class="knowledge-window-head">
      <span class="knowledge-mark" aria-hidden="true">${icon('brain',20)}</span>
      <div><h2>Память</h2><p>То, что ассистент запомнил из ваших разговоров и может учитывать в ответах.</p></div>
      <button id="knowledge-close" type="button" aria-label="Закрыть память">${icon('x')}</button>
    </header>
    <div class="knowledge-window-body memory-overview" role="region" aria-label="Запомненное ассистентом">
      ${items.length?'<div class="memory-facts">'+items.map(item=>`<article class="memory-fact">
        <h3>${escape(item.title)}</h3>
        <p>${escape(item.content)}</p>
      </article>`).join('')+'</div>':
      '<div class="knowledge-empty"><h3>Пока нечего вспомнить</h3><p>Ассистент сможет запомнить полезные сведения из вашего разговора. Например, скажите ему: «Запомни, что я работаю с ремонтом квартир».</p></div>'}
    </div>
  </section>`;
  const close=()=>{
    document.querySelector('#assistant-knowledge')?.setAttribute('aria-expanded','false');
    root.classList.add('is-closing');
    const finish=()=>{if(root.open)root.close();root.classList.remove('is-closing');root.classList.add('hidden');document.querySelector('#assistant-knowledge')?.focus()};
    if(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)finish();else setTimeout(finish,150);
  };
  root.querySelector('#knowledge-close').onclick=close;
  root.oncancel=event=>{event.preventDefault();close()};
  root.onclick=event=>{if(event.target===root)close()};
  root.onclose=()=>document.querySelector('#assistant-knowledge')?.setAttribute('aria-expanded','false');
};
