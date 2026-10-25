"use strict";
(() => {
  let token = "";
  const $ = id => document.getElementById(id);
  const money = amount => new Intl.NumberFormat("ru-RU", {style:"currency", currency:"RUB", maximumFractionDigits:2}).format(Number(amount || 0) / 100);
  const feedback = (message) => {
    $("feedback").textContent = message;
    $("feedback").classList.add("visible");
  };
  const request = async (route, options={}) => {
    const response = await fetch(route, {
      ...options,
      credentials: "omit",
      cache: "no-store",
      headers: {"Authorization":"Partner "+token, ...(options.body ? {"Content-Type":"application/json"} : {})}
    });
    const content = await response.json().catch(()=>({}));
    if(!response.ok) throw new Error(content.error || "Ошибка запроса к партнёрскому API");
    return content;
  };
  const refresh = async () => {
    const response = await request("/api/partners/console/summary");
    $("clicks").textContent = Number(response.clicks_30d || 0).toLocaleString("ru-RU");
    $("conversions").textContent = Number(response.conversions || 0).toLocaleString("ru-RU");
    $("earned").textContent = money(response.earned_kopecks);
    $("cleared").textContent = money(response.cleared_kopecks);
    $("partner-name").textContent = "Партнёр: "+String(response.partner || "");
  };
  $("connect").addEventListener("submit", async event => {
    event.preventDefault();
    const key = $("key").value.trim();
    if(!/^smp_live_[A-Za-z0-9_-]{35,100}$/.test(key)) {
      feedback("Некорректный формат ключа");
      return;
    }
    token = key;
    const btn = $("connect").querySelector("button");
    btn.disabled = true;
    try {
      await refresh();
      $("signin").hidden = true;
      $("dashboard").hidden = false;
      $("signout").hidden = false;
      $("key").value = "";
    } catch (error) {
      token = "";
      feedback(error.message);
    } finally { btn.disabled = false; }
  });
  $("refresh").addEventListener("click", () => refresh().catch(error => feedback(error.message)));
  $("catalog").addEventListener("submit", async event => {
    event.preventDefault();
    const btn = $("catalog").querySelector("button");
    btn.disabled = true;
    try {
      const text = $("products").value;
      if(text.length > 55000) throw new Error("Слишком большой пакет");
      const products = JSON.parse(text);
      const result = await request("/api/partners/console/catalog", {method:"POST",body:JSON.stringify(products)});
      feedback("Обновлено товаров: "+result.accepted);
    } catch (error) { feedback(error.message); }
    finally { btn.disabled = false; }
  });
  $("signout").addEventListener("click", () => {
    token = "";
    $("dashboard").hidden = true;
    $("signin").hidden = false;
    $("signout").hidden = true;
    $("key").value = "";
    $("key").focus();
  });
})();