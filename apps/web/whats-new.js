/* Release notes: controlled SVG icons, escaped text, explicit release vs patch status. */
(() => {
  const statusLabels={released:'Выпущено',development:'В разработке'};
  const typeLabels={major:'Обновление',patch:'Патч',preview:'В разработке'};
  // Icon paths are trusted literals. Never render SVG markup from the post JSON.
  const iconPaths={
    'newspaper':'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h7M7 12h7M7 16h7M17 8v8"/>',
    'calendar':'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18"/>',
    'bell':'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
    'shield-check':'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
    'audio-lines':'<path d="M2 10v4M6 6v12M10 3v18M14 7v10M18 5v14M22 10v4"/>',
    'ruler':'<path d="m3 17 14-14 4 4L7 21l-4-4Z"/><path d="m14 6 2 2m-5 1 2 2m-5 1 2 2"/>',
    'message-square':'<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l2-4.5A8.5 8.5 0 1 1 21 11.5Z"/>',
    'bug':'<path d="M8 3 6 1m10 2 2-2M4 10H2m20 0h-2M4 16H2m20 0h-2"/><rect x="6" y="5" width="12" height="16" rx="6"/><path d="M6 12h12"/>',
    'check':'<path d="m5 12 4 4L19 6"/>',
    'zap':'<path d="m13 2-9 12h7l-1 8 10-12h-7V2Z"/>',
    'file-text':'<path d="M6 2h9l5 5v14H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z"/><path d="M14 2v6h6M8 12h8M8 16h8"/>',
    'lock':'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 1 1 8 0v3"/>',
    'users':'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M17 5a3 3 0 0 1 0 6m4 9v-2a6 6 0 0 0-4-5.7"/>',
    'sparkles':'<path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3ZM19 17l.7 1.3L21 19l-1.3.7L19 21l-.7-1.3L17 19l1.3-.7L19 17Z"/>'
  };
  const icon=(name,cls='whats-new-icon')=>'<svg class="'+cls+'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(iconPaths[name]||iconPaths['check'])+'</svg>';
  const safe=value=>escapeHtml(value);
  const storageKey=()=> 'smetra.whats-new.seen:'+(user?.id||'guest');
  const readSeen=()=>{try{const seen=JSON.parse(localStorage.getItem(storageKey())||'[]');return Array.isArray(seen)?seen:[]}catch{return []}};
  const writeSeen=items=>{try{localStorage.setItem(storageKey(),JSON.stringify(items.slice(-100)))}catch{}};
  const refreshBadge=items=>{
    const unread=items.some(post=>post.status==='released'&&!readSeen().includes(post.id));
    const button=document.querySelector('#whats-new-nav');
    if(button){button.dataset.unread=unread?'true':'false';button.title=unread?'Что нового — есть непрочитанные публикации':'Что нового';}
  };
  const getPosts=async()=>{
    const response=await fetch('/whats-new.json',{cache:'no-store',credentials:'same-origin'});
    if(!response.ok)throw Error('Не удалось загрузить публикации');
    const data=await response.json();
    if(!data||![1,2].includes(data.schema_version)||!Array.isArray(data.posts))throw Error('Формат публикаций обновился. Перезагрузите страницу.');
    return data.posts.filter(post=>post&&/^[a-z0-9-]{1,100}$/.test(post.id)&&statusLabels[post.status]&&typeof post.title==='string'&&Array.isArray(post.changes)).slice(0,40);
  };
  const renderChanges=post=>post.changes.slice(0,12).map(entry=>{
    const detail=typeof entry==='string'?{text:entry,icon:post.type==='patch'?'check':'file-text'}:entry;
    if(!detail||typeof detail.text!=='string')return '';
    return '<li>'+icon(detail.icon,'whats-new-change-icon')+'<span>'+safe(detail.text)+'</span></li>';
  }).join('');
  const renderPost=post=>{
    const type=typeLabels[post.type]||typeLabels.major;
    const date=new Date(post.date+'T12:00:00');
    const dateLabel=Number.isNaN(date.getTime())?post.date:date.toLocaleDateString('ru-RU',{year:'numeric',month:'long',day:'numeric'});
    return `<article class="whats-new-post ${post.type==='patch'?'whats-new-patch':''}" aria-labelledby="release-${safe(post.id)}">
      <div class="whats-new-post-title">${icon(post.icon|| (post.type==='patch'?'bug':'newspaper'))}<div class="whats-new-post-heading">
        <div class="whats-new-meta"><time datetime="${safe(post.date)}">${safe(dateLabel)}</time><span class="whats-new-status">${safe(type)}</span>${post.status==='development'?'<span class="whats-new-development">Не выпущено</span>':''}</div>
        <h2 id="release-${safe(post.id)}">${safe(post.title)}</h2></div></div>
      ${post.summary?'<p>'+safe(post.summary)+'</p>':''}
      <ul class="whats-new-changes">${renderChanges(post)}</ul></article>`;
  };
  window.SmetraWhatsNewBadge=async()=>{try{refreshBadge(await getPosts())}catch{/* The main workspace remains available. */}};
  window.SmetraWhatsNew=async function(active=()=>true){
    const posts=await getPosts();if(!active())return;
    const released=posts.filter(post=>post.status==='released');
    const ordered=[...released,...posts.filter(post=>post.status==='development')];
    view(`<section class="whats-new-page"><header class="whats-new-header"><span class="eyebrow">СМЕТРА / ОБНОВЛЕНИЯ</span><h1>Что нового<span class="whats-new-dot" aria-hidden="true">.</span></h1><p>Главные обновления и патчи. В разработке — отдельно от уже доступных функций.</p></header><div class="whats-new-posts">${ordered.map(renderPost).join('')||'<p>Публикаций пока нет.</p>'}</div></section>`);
    // Mark only released posts as seen after the page is rendered.
    writeSeen([...new Set([...readSeen(),...released.map(post=>post.id)])]);
    refreshBadge(posts);
  };
})();
