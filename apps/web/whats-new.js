/* Versioned release notes. Never claim a feature is released before it ships. */
(() => {
  const labels={released:'Выпущено',development:'В разработке'};
  const storageKey=()=> 'smetra.whats-new.seen:'+(user?.id||'guest');
  const safe=(value)=>escapeHtml(value);
  const readSeen=()=>{try{return JSON.parse(localStorage.getItem(storageKey())||'[]')}catch{return []}};
  const writeSeen=items=>{try{localStorage.setItem(storageKey(),JSON.stringify(items.slice(0,100)))}catch{}};
  const refreshBadge=items=>{
    const unread=items.some(post=>post.status==='released'&&!readSeen().includes(post.id));
    const button=document.querySelector('#whats-new-nav');
    if(button){button.dataset.unread=unread?'true':'false';button.title=unread?'Что нового — есть непрочитанные публикации':'Что нового';}
  };
  const getPosts=async()=>{
    const response=await fetch('/whats-new.json',{cache:'no-store',credentials:'same-origin'});
    if(!response.ok)throw Error('Не удалось загрузить публикации');
    const data=await response.json();
    if(!data||data.schema_version!==1||!Array.isArray(data.posts))throw Error('Формат публикаций обновился. Перезагрузите страницу.');
    return data.posts.filter(post=>post&&/^[a-z0-9-]{1,100}$/.test(post.id)&&labels[post.status]&&typeof post.title==='string'&&Array.isArray(post.changes)).slice(0,40);
  };
  window.SmetraWhatsNewBadge=async()=>{
    try{refreshBadge(await getPosts())}catch{/* Do not block the workspace on a news error. */}
  };
  window.SmetraWhatsNew=async function(active=()=>true){
    const posts=await getPosts();if(!active())return;
    const seen=readSeen();
    const releasePosts=posts.filter(post=>post.status==='released');
    const draftPosts=posts.filter(post=>post.status==='development');
    const ordered=[...releasePosts,...draftPosts];
    const markSeen=()=>{writeSeen([...new Set([...seen,...releasePosts.map(post=>post.id)])]);refreshBadge(posts)};
    view(`<section class="whats-new-page">
      <header class="whats-new-header"><span class="eyebrow">СМЕТРА / ОБНОВЛЕНИЯ</span><h1>Что нового<span class="whats-new-dot" aria-hidden="true">.</span></h1><p>Изменения продукта и то, над чем мы работаем. Выпущенные функции всегда отделены от планов.</p></header>
      <div class="whats-new-posts">
        ${ordered.map((post,index)=>`<article class="whats-new-post" aria-labelledby="release-${safe(post.id)}"><div class="whats-new-meta"><time datetime="${safe(post.date)}">${safe(new Date(post.date+'T12:00:00').toLocaleDateString('ru-RU',{year:'numeric',month:'long',day:'numeric'}))}</time><span class="whats-new-status">${labels[post.status]}</span></div><h2 id="release-${safe(post.id)}">${safe(post.title)}</h2><p>${safe(post.summary||'')}</p><ul>${post.changes.slice(0,12).map(change=>`<li>${safe(change)}</li>`).join('')}</ul></article>`).join('')||'<p>Публикаций пока нет.</p>'}
      </div>
    </section>`);
    // A release is marked read only after it was actually displayed.
    markSeen();
  };
})();
