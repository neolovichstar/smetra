"""Free-to-user support assistant grounded in a maintained product map."""
import json
import os
import re
import urllib.error
import urllib.request

APP_KNOWLEDGE = """
Продукт: Сметра — приложение и сайт для строительных смет и управления работами.
Профиль: в аккаунте есть публичный идентификатор вида SM-XXXXXXXXXX; им можно делиться для поиска в приложении.
Сметы: создаются в разделе «Сметы» / «Предложения». Можно редактировать строки и суммы, версии перед отправкой проверяются, отправленная версия фиксируется.
Согласование: заказчик открывает ссылку, может запросить изменения или утвердить опубликованную версию. Итоговые суммы пересчитывает сервер.
ИИ-ассистент: понимает запросы на создание и редактирование смет, клиентов, заказов, файлов и документов. Изменения показываются как отдельное предложение; пользователь подтверждает его над полем ввода. Не утверждай, что изменение сохранено до подтверждения.
Файлы и документы: загружаются в разделе файлов/документов. Доступ ограничен текущим рабочим пространством.
Финансы: доступные разделы включают авансы, расходы и этапы работ; функции зависят от тарифа.
Тарифы: Старт — 10 бесплатных смет. PRO Solo — 490 ₽/мес. или 4 900 ₽/год. PRO Плюс / Снабженец — 690 ₽/мес. TEAM / Компания — 3 990 ₽/мес. или 39 900 ₽/год и до пяти участников всего.
Оплата: автоматического списания нет, если на экране оплаты явно не указано иначе. Статус платежа определяется серверным подтверждением провайдера.
Поддержка: обращение создаёт отдельную переписку; кнопка «Позвать сотрудника» передаёт обращение оператору и отмечает его в админке.
Ограничения: не придумывай функции, кнопки, статусы платежей и точные сроки. Если ответ не следует из этого справочника или описания пользователя, честно скажи, что не уверен, и предложи позвать сотрудника.
Не проси пароль, код подтверждения, платёжные реквизиты или секреты. Не заявляй, что видишь экран пользователя, если информация не передана в контексте.
"""


def fallback_answer(text):
    value = str(text or "").casefold()
    if any(word in value for word in ("тариф", "подпис", "оплат", "деньг", "списан")):
        return (
            "Давайте проверим это по шагам. Откройте «Тариф и оплата» и нажмите «Проверить статус» — "
            "доступ меняется только после подтверждения платёжной системой. Автоматического продления нет. "
            "Если статус не изменился, нажмите «Позвать сотрудника», и обращение появится в очереди поддержки."
        )
    if any(word in value for word in ("смет", "предлож", "клиент", "соглас")):
        return (
            "Откройте «Сметы» и выберите нужный документ. ИИ может подготовить создание или изменение, "
            "но сначала покажет предложение над полем сообщения. Проверьте строки и итог, затем подтвердите действие. "
            "Если документ уже отправлен, редактирование опубликованной версии защищено проверкой ревизии."
        )
    if any(word in value for word in ("вход", "парол", "аккаунт", "идентификатор", "id")):
        return (
            "Проверьте, что вы вошли в нужный аккаунт. Ваш публичный ID начинается с SM- и виден в профиле; "
            "он нужен для поиска людей, а не для входа. Никому не отправляйте пароль или коды подтверждения."
        )
    if any(word in value for word in ("файл", "pdf", "эксел", "xlsx", "документ", "экспорт")):
        return (
            "Откройте раздел файлов или документов и проверьте рабочее пространство. Для выгрузки сметы "
            "используйте меню самого документа. Доступность формата и отсутствие отметки Сметры зависят от тарифа."
        )
    return (
        "Давайте разберёмся. Напишите, пожалуйста, в каком разделе вы находитесь и что именно происходит "
        "после последнего нажатия. Я не буду угадывать интерфейс. Если вопрос срочный или ответ не поможет, "
        "нажмите «Позвать сотрудника» — обращение попадёт в очередь специалиста."
    )


def answer(messages, context=None):
    """Return a short answer. A product-accurate fallback always exists if the provider is down."""
    latest = next((str(row.get("body", "")) for row in reversed(messages) if row.get("sender_role") == "user"), "")
    fallback = fallback_answer(latest)
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        return fallback
    model = os.getenv("SUPPORT_MODEL", os.getenv("OPENROUTER_MODEL", "qwen/qwen3.8-27b:free")).strip()
    if not re.fullmatch(r"[A-Za-z0-9._/-]+(?::[A-Za-z0-9._-]+)?", model):
        return fallback
    recent = []
    for row in messages[-12:]:
        role = row.get("sender_role")
        if role not in ("user", "ai", "admin"):
            continue
        recent.append({"role": "assistant" if role in ("ai", "admin") else "user", "content": str(row.get("body", ""))[:4000]})
    context = context if isinstance(context, dict) else {}
    safe_context = {
        "plan": str(context.get("plan", "free"))[:40],
        "quote_count": max(0, min(1000000, int(context.get("quote_count", 0) or 0))),
        "workspace_role": str(context.get("workspace_role", ""))[:40],
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты — дружелюбный помощник поддержки Сметры. Отвечай по-русски как живой специалист, "
                    "коротко, естественно и без канцелярита. Используй только достоверные сведения из справочника "
                    "ниже и сообщения пользователя. Не выдумывай названия разделов и возможности. Если данных не хватает, "
                    "задай один конкретный уточняющий вопрос или предложи пользователю нажать «Позвать сотрудника». "
                    "Не проси секреты и не утверждай, что действие уже выполнено. Справочник продукта:\n"
                    + APP_KNOWLEDGE
                    + "\nКонтекст аккаунта (не является основанием для раскрытия данных): "
                    + json.dumps(safe_context, ensure_ascii=False)
                ),
            },
            *recent,
        ],
        "max_tokens": 500,
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("PUBLIC_ORIGIN", ""),
            "X-OpenRouter-Title": "Smetra Support",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=9) as response:
            raw = response.read(64000)
        result = json.loads(raw)
        content = result["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        content = re.sub(r"<(?:script|iframe)[^>]*>.*?</(?:script|iframe)>", "", str(content), flags=re.I | re.S).strip()
        if not 2 <= len(content) <= 3000:
            return fallback
        return content
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError, urllib.error.HTTPError):
        return fallback
