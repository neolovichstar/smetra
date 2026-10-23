'use strict';
// Landing only: no synthetic estimate or demo preview.
fetch('/api/auth/providers').then(r=>r.json()).then(data=>{if(data.rustore_url&&/^https:\/\/(www\.)?rustore\.ru\//.test(data.rustore_url)){const button=document.querySelector('#rustore');button.href=data.rustore_url;button.textContent='Открыть в RuStore';button.removeAttribute('aria-disabled');document.querySelector('#mobile-note').textContent='Карточка приложения в RuStore. Доступность установки проверьте на странице магазина.'}}).catch(()=>{});
 const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
 if(!reducedMotion&&'IntersectionObserver' in window){
  const targets=document.querySelectorAll('.landing-section,.feature-list article,.mobile-cta');
  targets.forEach((element,index)=>{element.classList.add('scroll-reveal');element.style.setProperty('--reveal-delay',`${Math.min(index%3,2)*75}ms`)});
  document.body.classList.add('motion-ready');
  const observer=new IntersectionObserver(entries=>{for(const entry of entries){if(entry.isIntersecting){entry.target.classList.add('in-view');observer.unobserve(entry.target)}}},{threshold:.08,rootMargin:'0px 0px -24px 0px'});
  targets.forEach(element=>observer.observe(element));
 }

// A single scroll frame drives the document stack; reduced motion stays static.
const heroSheet=document.querySelector('.hero-sheet');
if(heroSheet&&!reducedMotion){
 let scheduled=false;
 const updateHero=()=>{scheduled=false;const progress=Math.min(1,Math.max(0,scrollY/650));heroSheet.style.transform='rotateY('+(-7+7*progress)+'deg) rotateX('+(3-3*progress)+'deg) translateY('+(progress*-16)+'px)';};
 addEventListener('scroll',()=>{if(!scheduled){scheduled=true;requestAnimationFrame(updateHero)}},{passive:true});
 updateHero();
}
