'use strict';

// Local CommonMark renderer. Model/user HTML stays text; remote images never load.
(() => {
  const md=window.markdownit({html:false,breaks:false,linkify:true,typographer:false});
  md.validateLink=url=>/^https?:\/\//i.test(url);
  const escape=md.utils.escapeHtml;
  const linkOpen=md.renderer.rules.link_open||((tokens,index,options,env,self)=>self.renderToken(tokens,index,options));
  md.renderer.rules.link_open=(tokens,index,options,env,self)=>{
    tokens[index].attrSet('target','_blank');tokens[index].attrSet('rel','noopener noreferrer');
    return linkOpen(tokens,index,options,env,self);
  };
  md.renderer.rules.image=(tokens,index)=>`<span class="assistant-image-alt">${escape(tokens[index].content||'Изображение')}</span>`;
  md.renderer.rules.heading_open=(tokens,index)=>`<h${Math.min(6,Number(tokens[index].tag.slice(1))+2)}>`;
  md.renderer.rules.heading_close=(tokens,index)=>`</h${Math.min(6,Number(tokens[index].tag.slice(1))+2)}>\n`;
  md.renderer.rules.table_open=()=>'<div class="assistant-table-scroll" role="region" aria-label="Таблица в ответе" tabindex="0"><table>\n';
  md.renderer.rules.table_close=()=>'</table></div>\n';
  for(const type of ['th_open','td_open'])md.renderer.rules[type]=(tokens,index,options,env,self)=>{
    const token=tokens[index],align=(token.attrGet('style')||'').match(/text-align:(left|center|right)/)?.[1];
    token.attrs=(token.attrs||[]).filter(([name])=>name!=='style');
    if(align)token.attrSet('class','align-'+align);
    if(type==='th_open')token.attrSet('scope','col');
    return self.renderToken(tokens,index,options);
  };
  const codeBlock=(text,language='')=>{
    const label=language.replace(/[^a-z0-9+#.-]/gi,'').slice(0,24)||'Текст';
    return `<section class="assistant-code"><header><span>${escape(label)}</span><button type="button" class="assistant-code-copy" data-copy-code aria-label="Скопировать код">Копировать</button></header><pre tabindex="0"><code>${escape(text.replace(/\n$/,''))}</code></pre></section>\n`;
  };
  md.renderer.rules.fence=(tokens,index)=>codeBlock(tokens[index].content,tokens[index].info.trim().split(/\s+/)[0]);
  md.renderer.rules.code_block=(tokens,index)=>codeBlock(tokens[index].content);
  md.core.ruler.after('inline','smetra_tasks',state=>{
    for(let i=2;i<state.tokens.length;i++){
      const token=state.tokens[i];
      if(token.type!=='inline'||state.tokens[i-1].type!=='paragraph_open'||state.tokens[i-2].type!=='list_item_open')continue;
      const first=token.children?.[0],match=first?.type==='text'&&first.content.match(/^\[([ xX])\]\s+/);
      if(!match)continue;
      first.content=first.content.slice(match[0].length);
      const marker=new state.Token('html_inline','',0),done=match[1]!==' ';
      marker.content=`<span class="assistant-task ${done?'is-done':''}" role="img" aria-label="${done?'Выполнено':'Не выполнено'}"></span>`;
      token.children.unshift(marker);
    }
  });
  window.SmetraMarkdown={render:source=>md.render(String(source||'')),inline:source=>md.renderInline(String(source||''))};
  if(typeof document!=='undefined')document.addEventListener('click',async event=>{
    const button=event.target.closest?.('[data-copy-code]');
    if(!button||button.disabled)return;
    const code=button.closest('.assistant-code')?.querySelector('code');if(!code)return;
    const label=button.textContent;button.disabled=true;
    try{await navigator.clipboard.writeText(code.textContent);button.textContent='Скопировано';setTimeout(()=>{button.textContent=label},1600)}
    catch{window.notify?.('Не удалось скопировать. Выделите код и скопируйте вручную.')}
    finally{button.disabled=false}
  });
})();
