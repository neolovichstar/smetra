'use strict';

function assistantInline(source){return window.SmetraMarkdown.inline(source)}
function assistantMarkdown(source){return window.SmetraMarkdown.render(source)}

// Clipboard API can be unavailable because of browser permissions or a non-secure context.
// Use a temporary selected textarea as a fallback rather than making copy silently fail.
window.SmetraCopyText=async value=>{
  const text=String(value??'');
  if(navigator.clipboard?.writeText){
    try{await navigator.clipboard.writeText(text);return true}catch{}
  }
  const field=document.createElement('textarea');
  field.value=text;field.setAttribute('readonly','');field.setAttribute('aria-hidden','true');
  Object.assign(field.style,{position:'fixed',left:'0',top:'0',width:'1px',height:'1px',padding:'0',border:'0',opacity:'0',pointerEvents:'none'});
  document.body.append(field);
  let copied=false;
  try{field.focus({preventScroll:true});field.select();field.setSelectionRange(0,field.value.length);copied=document.execCommand('copy')}
  finally{field.remove()}
  if(!copied)throw Error('Clipboard access denied');
  return true;
};

// Local CommonMark renderer. Model/user HTML stays text; remote images never load.
(() => {
  const md=window.markdownit({html:false,breaks:false,linkify:true,typographer:false});
  md.validateLink=url=>/^https?:\/\//i.test(url);
  const escape=md.utils.escapeHtml;
  const linkOpen=md.renderer.rules.link_open||((tokens,index,options,env,self)=>self.renderToken(tokens,index,options));
  md.renderer.rules.link_open=(tokens,index,options,env,self)=>{
    const token=tokens[index],label=tokens[index+1];
    token.attrSet('target','_blank');token.attrSet('rel','noopener noreferrer');
    // A bare URL becomes a compact source pill with its domain, as in ChatGPT.
    if(label?.type==='text'&&tokens[index+2]?.type==='link_close'&&label.content===token.attrGet('href')){
      try{label.content=new URL(label.content).hostname.replace(/^www\./,'');token.attrSet('class','assistant-link-pill')}catch{}
    }
    return linkOpen(tokens,index,options,env,self);
  };
  md.renderer.rules.image=(tokens,index)=>`<span class="assistant-image-alt">${escape(tokens[index].content||'Изображение')}</span>`;
  md.renderer.rules.heading_open=(tokens,index)=>`<h${Math.min(6,Number(tokens[index].tag.slice(1)))}>`;
  md.renderer.rules.heading_close=(tokens,index)=>`</h${Math.min(6,Number(tokens[index].tag.slice(1)))}>\n`;
  // Tables get a toolbar: copy as tab-separated text that pastes into Excel or Google Sheets.
  md.renderer.rules.table_open=()=>'<div class="assistant-table"><div class="assistant-table-tools"><button type="button" class="assistant-table-copy" data-copy-table aria-label="Скопировать таблицу для Excel">Копировать таблицу</button></div><div class="assistant-table-scroll" role="region" aria-label="Таблица в ответе" tabindex="0"><table>\n';
  md.renderer.rules.table_close=()=>'</table></div></div>\n';
  const NUMERIC=/^[\s+\-−]?[\d\u00a0\u202f .,]*\d(?:[\u00a0\u202f ]?(?:₽|руб\.?|р\.|%|м²|м³|м2|м3|шт\.?|м|кг|л|т|ч|дн\.?))?$/;
  for(const type of ['th_open','td_open'])md.renderer.rules[type]=(tokens,index,options,env,self)=>{
    const token=tokens[index],align=(token.attrGet('style')||'').match(/text-align:(left|center|right)/)?.[1];
    token.attrs=(token.attrs||[]).filter(([name])=>name!=='style');
    if(align)token.attrSet('class','align-'+align);
    // Money, quantities and percentages line up on the right like in a spreadsheet.
    else if(type==='td_open'&&NUMERIC.test(tokens[index+1]?.content||''))token.attrSet('class','is-numeric');
    if(type==='th_open')token.attrSet('scope','col');
    return self.renderToken(tokens,index,options);
  };
  // Small, dependency-free highlighter: every piece is escaped, only <span class> is added.
  const KEYWORDS={
    js:'const let var function return if else for while of in new class extends import export from default async await try catch finally throw typeof instanceof null undefined true false this',
    python:'def return if elif else for while in not and or import from as class with try except finally raise lambda None True False self pass yield async await',
    sql:'select from where join left right inner outer on group by order having insert into values update set delete create table alter drop and or not null as limit distinct count sum avg min max case when then else end',
    bash:'if then else fi for do done while case esac function in export echo cd ls grep cat sudo',
    json:'true false null',
  };
  const ALIASES={javascript:'js',ts:'js',typescript:'js',jsx:'js',tsx:'js',py:'python',sh:'bash',shell:'bash',zsh:'bash',console:'bash',postgresql:'sql',sqlite:'sql',mysql:'sql'};
  const highlight=(text,language)=>{
    const lang=ALIASES[language]||language,words=KEYWORDS[lang];
    if(!words)return escape(text);
    const keywords=new Set(words.split(' '));
    const comment=lang==='python'||lang==='bash'?'#[^\\n]*':lang==='sql'?'--[^\\n]*':'\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/';
    const pattern=new RegExp(`(${comment})|("(?:\\\\.|[^"\\\\\\n])*"|'(?:\\\\.|[^'\\\\\\n])*'|\`(?:\\\\.|[^\`\\\\])*\`)|(\\b\\d+(?:\\.\\d+)?\\b)|([A-Za-z_][\\w]*)`,'g');
    let html='',last=0;
    for(const match of text.matchAll(pattern)){
      html+=escape(text.slice(last,match.index));last=match.index+match[0].length;
      const [whole,isComment,isString,isNumber,word]=match;
      const kind=isComment?'comment':isString?(lang==='json'&&/^\s*:/.test(text.slice(last))?'key':'string'):isNumber?'number':
        word&&keywords.has(lang==='sql'?word.toLowerCase():word)?'keyword':word&&text[last]==='('?'function':'';
      html+=kind?`<span class="tok-${kind}">${escape(whole)}</span>`:escape(whole);
    }
    return html+escape(text.slice(last));
  };
  const codeBlock=(text,language='')=>{
    const clean=language.toLowerCase().replace(/[^a-z0-9+#.-]/g,'').slice(0,24);
    const label=clean||'Текст',body=text.replace(/\n$/,''),lines=body.split('\n').length;
    // Long listings start collapsed so the answer stays readable; one click shows everything.
    const long=lines>24;
    return `<section class="assistant-code${long?' is-collapsed':''}"><header><span>${escape(label)}</span><button type="button" class="assistant-code-copy" data-copy-code aria-label="Скопировать код">Копировать</button></header><pre tabindex="0"><code>${highlight(body,clean)}</code></pre>${long?`<button type="button" class="assistant-code-expand" data-code-expand aria-expanded="false">Показать всё · ${lines} строк</button>`:''}</section>\n`;
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
  // Callouts are parsed from Markdown blockquotes, never rendered as raw model HTML.
  md.core.ruler.after('smetra_tasks','smetra_callouts',state=>{
    const labels={NOTE:'Примечание',TIP:'Совет',WARNING:'Внимание',IMPORTANT:'Важно',CAUTION:'Осторожно'};
    for(let index=0;index<state.tokens.length-2;index++){
      const opening=state.tokens[index];
      if(opening.type!=='blockquote_open')continue;
      let inline=null;
      for(let step=index+1;step<Math.min(index+6,state.tokens.length);step++){
        if(state.tokens[step].type==='inline'){inline=state.tokens[step];break}
        if(state.tokens[step].type==='blockquote_close')break;
      }
      const first=inline?.children?.[0];
      if(!first||first.type!=='text')continue;
      const found=/^\[!(NOTE|TIP|WARNING|IMPORTANT|CAUTION)\](?:\s|$)/i.exec(first.content);
      if(!found)continue;
      const kind=found[1].toUpperCase();
      opening.attrSet('class','assistant-callout assistant-callout--'+kind.toLowerCase());
      first.content=first.content.slice(found[0].length).trimStart();
      const title=new state.Token('html_inline','',0);
      title.content='<span class="assistant-callout-title">'+labels[kind]+'</span>';
      inline.children.unshift(title);
    }
  });
  window.SmetraMarkdown={render:source=>md.render(String(source||'')),inline:source=>md.renderInline(String(source||''))};
  const tableText=table=>[...table.rows].map(row=>[...row.cells].map(cell=>cell.textContent.replace(/\s+/g,' ').trim()).join('\t')).join('\n');
  if(typeof document!=='undefined')document.addEventListener('click',async event=>{
    const expand=event.target.closest?.('[data-code-expand]');
    if(expand){const block=expand.closest('.assistant-code');const open=block.classList.toggle('is-collapsed')===false;expand.setAttribute('aria-expanded',String(open));expand.textContent=open?'Свернуть':'Показать всё';return}
    const copyTable=event.target.closest?.('[data-copy-table]');
    if(copyTable&&!copyTable.disabled){
      const table=copyTable.closest('.assistant-table')?.querySelector('table');if(!table)return;
      copyTable.disabled=true;
      try{await window.SmetraCopyText(tableText(table));copyTable.textContent='Скопировано';setTimeout(()=>{if(copyTable.isConnected)copyTable.textContent='Копировать таблицу'},1600)}
      catch{window.notify?.('Не удалось скопировать таблицу.')}
      finally{copyTable.disabled=false}
      return;
    }
    const button=event.target.closest?.('[data-copy-code]');
    if(!button||button.disabled)return;
    const code=button.closest('.assistant-code')?.querySelector('code');if(!code)return;
    const label=button.textContent;button.disabled=true;
    try{await window.SmetraCopyText(code.textContent);button.textContent='Скопировано';setTimeout(()=>{if(button.isConnected)button.textContent=label},1600)}
    catch{window.notify?.('Не удалось скопировать. Выделите код и скопируйте вручную.')}
    finally{button.disabled=false;button.focus({preventScroll:true})}
  });
})();
