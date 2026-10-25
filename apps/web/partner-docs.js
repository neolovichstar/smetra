"use strict";
(async()=>{
const host=document.getElementById("documentation");
try{
  const response=await fetch("/partner-docs.md",{cache:"no-store",credentials:"omit"});
  if(!response.ok)throw new Error("Документация недоступна");
  const text=await response.text();
  if(!window.markdownit)throw new Error("Не удалось открыть Markdown");
  // HTML disabled: documentation text cannot inject executable markup.
  const md=window.markdownit({html:false,linkify:true,typographer:true});
  host.innerHTML=md.render(text);
}catch(error){host.textContent=error.message;}
})();