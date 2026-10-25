"use strict";
(() => {
  let token = "";
  let lastReport = null;
  const $ = id => document.getElementById(id);
  const number = n => Number(n || 0).toLocaleString("ru-RU");
  const money = n => new Intl.NumberFormat("ru-RU", {style:"currency",currency:"RUB"}).format(Number(n || 0)/100);
  const feedback = message => {
    $("feedback").textContent = String(message);
    $("feedback").classList.add("visible");
  };
  const request = async (route, options={}) => {
    const response = await fetch(route, {
      ...options,credentials:"omit",cache:"no-store",
      headers:{"Authorization":"PartnerSession "+token,...(options.body?{"Content-Type":"application/json"}:{})}
    });
    const payload = await response.json().catch(()=>({}));
    if(!response.ok) {
      if(response.status===401 && token) feedback("Сессия истекла, войдите повторно");
      throw new Error(payload.error || "Ошибка партнёрского API");
    }
    return payload;
  };
  const renderTimeline = data => {
    const host = $("timeline");
    host.replaceChildren();
    const max = Math.max(1,...data.map(day => day.visits));
    for(const day of data) {
      const column = document.createElement("div");
      column.className = "timeline-day";
      column.title = day.date+": переходы "+day.visits+", регистрации "+day.registrations+", платежи "+day.payments;
      column.setAttribute("aria-label",column.title);
      const bars = document.createElement("div"); bars.className = "timeline-bars";
      for(const [value,kind] of [[day.visits,"visits"],[day.registrations,"registrations"],[day.payments,"payments"]]){
        const bar=document.createElement("div");bar.className="timeline-bar "+kind;
        bar.style.height=(Math.max(1,value/max*100))+"%";
        bars.append(bar);
      }
      column.append(bars);
      host.append(column);
    }
  };
  const showDomain = data => {
    $("verify-state").textContent = data.status==="verified"?"Домен подтверждён":data.status==="pending"?"Ожидает проверки":"Не настроено";
    $("domain-host").textContent = data.domain || "";
    const instruction = $("domain-instructions");
    if(!data.token || data.status==="verified"){instruction.hidden=true;return;}
    instruction.hidden=false;
    instruction.textContent=data.method==="dns"
      ? ("Тип: TXT\nИмя: _smetra-verification."+data.domain+"\nЗначение: "+data.token)
      : ('Добавьте в <head> главной страницы https://'+data.domain+'/ следующий тег:\n<meta name="smetra-domain-verification" content="'+data.token+'">');
  };
  const refresh = async () => {
    const days=Number($("days").value);
    const [summary,detail,domain]=await Promise.all([
      request("/api/partners/console/summary"),
      request("/api/partners/console/analytics?days="+days),
      request("/api/partners/console/domain")
    ]);
    lastReport=detail;
    $("clicks").textContent=number(detail.visits);
    $("registrations").textContent=number(detail.registrations);
    $("conversions").textContent=number(detail.verified_subscription_payments.payments);
    $("earned").textContent=money(detail.verified_subscription_payments.commission_kopecks);
    $("cleared").textContent=money(summary.cleared_kopecks);
    $("material-clicks").textContent=number(detail.outbound_material_clicks);
    $("reported-orders").textContent=number((detail.merchant_reported.material_order_reported||{}).count);
    $("partner-name").textContent="Партнёр: "+summary.partner;
    $("referral-link").value="https://smetra.online/api/partners/r/"+encodeURIComponent(summary.partner);
    renderTimeline(detail.timeline);
    showDomain(domain);
  };
  $("connect").addEventListener("submit",async event=>{
    event.preventDefault();
    const key=$("key").value.trim();
    if(!/^smp_live_[A-Za-z0-9_-]{35,100}$/.test(key)){feedback("Неверный формат API-ключа");return;}
    const button=$("connect").querySelector("button");button.disabled=true;
    try {
      const response=await fetch("/api/partners/console/session",{
        method:"POST",credentials:"omit",cache:"no-store",
        headers:{"Content-Type":"application/json"},body:JSON.stringify({api_key:key})
      });
      const result=await response.json().catch(()=>({}));
      if(!response.ok) throw new Error(result.error||"Ошибка входа");
      token=result.session_token;
      $("key").value="";
      await refresh();
      $("signin").hidden=true;$("dashboard").hidden=false;$("signout").hidden=false;
    }catch(error){token="";feedback(error.message)}
    finally{button.disabled=false;$("key").value="";}
  });
  $("days").addEventListener("change",()=>refresh().catch(err=>feedback(err.message)));
  $("refresh").addEventListener("click",()=>refresh().catch(err=>feedback(err.message)));
  $("copy-link").addEventListener("click",async()=>{
    try{await navigator.clipboard.writeText($("referral-link").value);feedback("Ссылка скопирована")}
    catch{$("referral-link").select();feedback("Скопируйте выделенную ссылку")}
  });
  $("begin-verify").addEventListener("click",async()=>{
    try {
      const data=await request("/api/partners/console/domain",{
        method:"POST",body:JSON.stringify({method:$("verify-method").value})
      });
      showDomain(data);feedback("Проверка создана. Добавьте запись на сайт или в DNS.");
    }catch(err){feedback(err.message)}
  });
  $("check-verify").addEventListener("click",async()=>{
    const btn=$("check-verify");btn.disabled=true;
    try {
      const result=await request("/api/partners/console/domain/verify",{method:"POST",body:"{}"});
      showDomain(result);feedback(result.status==="verified"?"Домен подтверждён":"Подтверждение ещё не найдено");
    }catch(err){feedback(err.message)}
    finally{btn.disabled=false}
  });
  $("catalog").addEventListener("submit",async event=>{
    event.preventDefault();const button=$("catalog").querySelector("button");button.disabled=true;
    try {
      const data=$("products").value;
      if(data.length>55000)throw new Error("Превышен размер пакета");
      const payload=JSON.parse(data);
      const result=await request("/api/partners/console/catalog",{method:"POST",body:JSON.stringify(payload)});
      feedback("Каталог обновлён. Принято товаров: "+result.accepted);
    }catch(err){feedback(err.message)}finally{button.disabled=false}
  });
  $("csv").addEventListener("click",()=>{
    if(!lastReport)return;
    const rows=[["date","visits","registrations","payments","materials_clicks","reported_impressions","reported_orders"].join(",")];
    for(const day of lastReport.timeline)rows.push(
      [day.date,day.visits,day.registrations,day.payments,day.materials_clicks,
       day.reported_impressions,day.reported_orders].join(",")
    );
    const url=URL.createObjectURL(new Blob([rows.join("\n")],{type:"text/csv;charset=utf-8"}));
    const link=document.createElement("a");link.href=url;link.download="smetra-partner-analytics.csv";link.click();
    URL.revokeObjectURL(url);
  });
  $("signout").addEventListener("click",async()=>{
    try{await request("/api/partners/console/logout",{method:"POST",body:"{}"})}catch{}
    token="";lastReport=null;$("dashboard").hidden=true;$("signin").hidden=false;
    $("signout").hidden=true;$("key").focus();
  });
})();
