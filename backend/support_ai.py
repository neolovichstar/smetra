"""Free-to-user support assistant grounded in a maintained product map."""
import json
import os
import re
import urllib.error
import urllib.request

APP_KNOWLEDGE = """
Продукт: Сметра — приложение и сайт для строительных смет и управления работами.
Профиль: в аккаунте есть публичный идентификатор вида SM-XXXXXXXXXXXXXXXX; им можно делиться для поиска в приложении. Он не заменяет пароль и не даёт право входа.
Общение: раздел «Почта и чаты» содержит личные переписки по публичному ID, обсуждения конкретных смет и профессиональные сообщества по темам. Чаты объектов и команды доступны участникам активного TEAM и привязаны к рабочему пространству.
Сметы: создаются в разделе «Сметы» / «Предложения». Можно редактировать строки и суммы; сервер проверяет ревизии, отправленная версия фиксируется. После публикации для обсуждения создаётся отдельная переписка с привязкой к ID сметы.
Согласование: заказчик открывает ссылку, может запросить изменения или утвердить опубликованную версию. Итоговые суммы пересчитывает сервер; галочки необязательных позиций не подменяют серверный расчёт.
ИИ-ассистент: понимает запросы на создание и редактирование смет, клиентов, заказов, файлов и документов. Может подготовить письмо со ссылкой на смету по email, но показывает адрес и действие в карточке, а реальная отправка выполняется только после явного подтверждения пользователя и при настроенной почте сервиса. Не утверждай, что документ изменён или письмо отправлено до подтверждённого результата.
Файлы и документы: загружаются в разделе файлов/документов. Доступ ограничен текущим рабочим пространством.
Финансы: доступные разделы включают авансы, расходы и этапы работ; функции зависят от тарифа. TEAM включает владельца и до четырёх сотрудников.
Поддержка: каждый запрос создаёт отдельную закрытую от других пользователей переписку; бесплатный AI отвечает на типовые вопросы. Кнопка «Позвать сотрудника» или неразрешённая техническая/платёжная проблема передаёт тикет в админку с приоритетом.
Тарифы: Старт — 10 бесплатных смет. PRO Solo — 490 ₽/мес. или 4 900 ₽/год. PRO Плюс / Снабженец — 690 ₽/мес. TEAM / Компания — 3 990 ₽/мес. или 39 900 ₽/год и до пяти участников всего.
Оплата: автоматического списания нет, если на экране оплаты явно не указано иначе. Статус платежа определяется серверным подтверждением провайдера.
Поддержка: обращение создаёт отдельную переписку; кнопка «Позвать сотрудника» передаёт обращение оператору и отмечает его в админке.
Ограничения: не обещай AR-сканер, серверно подтверждённые награды за рекламу, прямой API-заказ у ритейлеров или CPA-кэшбэк как доступные функции, если интерфейс/сервер явно их не предоставляют. Рекламные награды временно отключены, пока нет доверенной серверной проверки просмотра. Не утверждай, что подтверждены масштабы нагрузки 300 000 MAU без проведённого нагрузочного теста. Не придумывай функции, кнопки, статусы платежей и точные сроки. Если ответ не следует из этого справочника или описания пользователя, честно скажи, что не уверен, и предложи позвать сотрудника.
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


def _last_user_message(messages):
    return next((str(row.get("body", "")) for row in reversed(messages) if row.get("sender_role") == "user"), "")


def _escalation_for(latest, reply, provider_ok):
    value = str(latest or "").casefold()
    answer_text = str(reply or "").casefold()
    human_request = any(token in value for token in (
        "позови сотруд", "позвать сотруд", "нужен человек", "оператор", "с живым человеком",
        "свяжи с поддержк", "подключи человека", "поговорить с человеком", "позови менедж",
    ))
    if human_request:
        return True, "high"
    critical = any(token in value for token in (
        "списал деньги", "списали деньги", "двойное списание", "платёж прошёл дважды",
        "пропали данные", "удалилась смета", "взлом", "чужой аккаунт", "утечка",
        "не могу войти", "потерял доступ", "смета исчезла",
    ))
    if critical:
        return True, "urgent"
    broken = any(token in value for token in (
        "пустая страница", "пустую страницу", "белый экран", "не открыва", "не работает",
        "не получается", "ошибка", "не сохраня", "не загружа", "не отправля", "сломал",
        "зависает", "пропал", "не запуска", "не вижу", "не отвечает",
    ))
    if broken and (not provider_ok or any(token in answer_text for token in (
        "не уверен", "не могу определить", "недостаточно информации", "позовите сотрудника",
        "позвать сотрудника", "не могу помочь",
    ))):
        return True, "high"
    known_topic = any(token in value for token in (
        "тариф", "подпис", "оплат", "смет", "предлож", "клиент", "соглас",
        "вход", "парол", "аккаунт", "идентификатор", "публичный id", "профил",
        "файл", "pdf", "эксел", "xlsx", "документ", "экспорт",
    ))
    uncertain = any(token in answer_text for token in (
        "не уверен", "не могу определить", "недостаточно информации",
        "не могу помочь", "позовите сотрудника", "позвать сотрудника",
    ))
    if uncertain:
        return True, "high"
    if not provider_ok and not known_topic:
        return True, "high"
    return False, "normal"


def answer_result(messages, context=None):
    """Return a customer-safe answer and whether a human agent should take over."""
    latest = _last_user_message(messages)
    fallback = fallback_answer(latest)
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        escalate, priority = _escalation_for(latest, fallback, False)
        return {"text": fallback, "needs_human": escalate, "priority": priority, "source": "fallback"}
    model = os.getenv("SUPPORT_MODEL", "qwen/qwen3.8-27b:free").strip()
    if not re.fullmatch(r"[A-Za-z0-9._/-]+(?::[A-Za-z0-9._-]+)?", model):
        escalate, priority = _escalation_for(latest, fallback, False)
        return {"text": fallback, "needs_human": escalate, "priority": priority, "source": "fallback"}
    recent = []
    for row in messages[-12:]:
        role = row.get("sender_role")
        if role not in ("user", "ai", "admin"):
            continue
        recent.append({
            "role": "assistant" if role in ("ai", "admin") else "user",
            "content": str(row.get("body", ""))[:4000],
        })
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
                    "ниже и сообщений пользователя. Не выдумывай названия разделов и возможности. "
                    "Верни только JSON-объект с полями reply (строка) и needs_human (boolean), без Markdown и "
                    "дополнительных полей. needs_human=true, если пользователь просит сотрудника, есть спор о деньгах, "
                    "риск потери данных/доступа/безопасности, конкретная техническая ошибка, либо ты не можешь надёжно "
                    "решить вопрос по имеющимся сведениям. Если можно дать конкретную проверяемую инструкцию, "
                    "needs_human=false. Не проси секреты и не утверждай, что действие уже выполнено. Справочник продукта:\n"
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
            content = "\n".join(
                str(item.get("text", "")) for item in content if isinstance(item, dict)
            )
        content = str(content).strip()
        needs_human = False
        try:
            structured = json.loads(content)
            if isinstance(structured, dict) and isinstance(structured.get("reply"), str):
                content = structured["reply"].strip()
                needs_human = structured.get("needs_human") is True
        except (ValueError, TypeError):
            # Compatibility with providers that ignore JSON-only output instructions.
            pass
        content = re.sub(r"<(?:script|iframe)[^>]*>.*?</(?:script|iframe)>", "", content, flags=re.I | re.S).strip()
        if not 2 <= len(content) <= 3000:
            escalate, priority = _escalation_for(latest, fallback, False)
            return {"text": fallback, "needs_human": escalate, "priority": priority, "source": "fallback"}
        inferred, priority = _escalation_for(latest, content, True)
        needs_human = needs_human or inferred
        return {
            "text": content,
            "needs_human": needs_human,
            "priority": "urgent" if priority == "urgent" else ("high" if needs_human else "normal"),
            "source": "model",
        }
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError, urllib.error.HTTPError):
        escalate, priority = _escalation_for(latest, fallback, False)
        return {"text": fallback, "needs_human": escalate, "priority": priority, "source": "fallback"}


def answer(messages, context=None):
    """Backward-compatible plain text helper."""
    return answer_result(messages, context)["text"]
