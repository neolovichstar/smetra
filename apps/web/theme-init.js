/* Apply the stored preference before styles paint; black is the brand default. */
(()=>{let theme='dark';try{if(localStorage.getItem('smetra_theme')==='light')theme='light'}catch{}document.documentElement.dataset.theme=theme})();
