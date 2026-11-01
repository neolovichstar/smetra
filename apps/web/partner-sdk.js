/* Smetra Partner Widget SDK v1 — public, zero-dependency, no API keys. */
(function(root){
  "use strict";
  const PATTERN=/^[a-z0-9][a-z0-9_-]{2,39}$/;
  function referralUrl(code) {
    if(typeof code!=="string"||!PATTERN.test(code))throw new TypeError("Invalid partner code");
    return "https://smetra.online/api/partners/r/"+encodeURIComponent(code);
  }
  function mount(options){
    if(!options||typeof options!=="object")throw new TypeError("Options required");
    const target=typeof options.container==="string"
      ?document.querySelector(options.container):options.container;
    if(!target||typeof target.appendChild!=="function")throw new TypeError("Invalid container");
    const anchor=document.createElement("a");
    anchor.href=referralUrl(options.code);
    anchor.textContent=String(options.label||"Создать смету с ИИ");
    anchor.rel="noopener noreferrer";
    anchor.setAttribute("data-smetra-partner",options.code);
    target.appendChild(anchor);
    return anchor;
  }
  function attach(options){
    if(!options||typeof options.selector!=="string")throw new TypeError("Selector required");
    const url=referralUrl(options.code);
    const matches=document.querySelectorAll(options.selector);
    for(const link of matches){
      if(link.tagName!=="A")continue;
      link.href=url;
      link.rel="noopener noreferrer";
    }
    return matches.length;
  }
  root.SmetraPartner=Object.freeze({version:"1.0.0",referralUrl,mount,attach});
})(window);
