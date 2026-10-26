"""Short semantic chat titles from the first user message.

Generation is best-effort. Provider downtime falls back to extractive text.
Never overwrites a manually chosen title.
"""
import json
import os
import re
import urllib.request

from backend.business import packed

TITLE_LIMIT = 38
_SPACE = re.compile(r"\s+")
_PREFIX = re.compile(
    r"(?i)^(?:привет(?:ствую)?[,!\s]*|пожалуйста[,!\s]*|"
    r"(?:слушай|смотри|короче|мне нужно|можешь|помоги(?: мне)?|"
    r"я хочу|хочу|надо|давай|сделай|расскажи|объясни|подскажи|"
    r"а можно|как мне|нужно)[\s,.:!?—-]+)+"
)


def clean_title(value):
    text = re.sub(r"<[^>]*>", " ", str(value or ""))
    text = _SPACE.sub(" ", text.replace("\x00", " ")).strip(" .,:;!?–—-«»\"'*#")
    text = _PREFIX.sub("", text).strip(" .,:;!?–—-«»\"'*#")
    if not text:
        return "Новый диалог"
    if len(text) <= TITLE_LIMIT:
        return text[0].upper() + text[1:]
    candidate = text[:TITLE_LIMIT + 1]
    cut = candidate.rfind(" ")
    if cut >= max(15, TITLE_LIMIT // 2):
        candidate = candidate[:cut]
    else:
        candidate = candidate[:TITLE_LIMIT].rstrip()
    return candidate.rstrip(" .,:;!?–—-") or "Новый диалог"


def fallback_title(prompt):
    plain = _SPACE.sub(" ", str(prompt or "")).strip()
    plain = _PREFIX.sub("", plain)
    plain = re.split(r"(?<=[.!?])\s+", plain, maxsplit=1)[0]
    return clean_title(plain)


def generate_title(prompt, model, paid=False):
    text = str(prompt or "").strip()
    if not text:
        return "Новый диалог"
    if len(text) < 65 or not os.getenv("OPENROUTER_API_KEY"):
        return fallback_title(text)
    redacted = re.sub(r"(?i)(?:sk-or-v1-|ghp_|github_pat_)[A-Za-z0-9_-]{8,}",
                      "[секрет]", text[:650])
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        packed({
            "model": model,
            "messages": [
                {"role": "system", "content":
                 "Придумай лаконичное название рабочего диалога Сметры по первому сообщению. "
                 "Только название на русском языке из 2–5 слов, не более 38 символов. "
                 "Выдели конкретную тему, не начинай с «Помоги», «Вопрос», «Сделай», «Диалог». "
                 "Никаких кавычек, форматирования, номеров, JSON и пояснений."},
                {"role": "user", "content": redacted},
            ],
            "max_tokens": 45, "temperature": 0.1,
            "usage": {"include": True},
        }).encode(),
        headers={
            "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("PUBLIC_ORIGIN", ""),
            "X-OpenRouter-Title": "Smetra",
        }, method="POST",
    )
    try:
        from backend.assistant import open_completion
        with open_completion(request, timeout=7) as response:
            raw = response.read(12000)
        parsed = json.loads(raw)
        title = parsed["choices"][0]["message"]["content"]
        candidate = clean_title(str(title or "").split("\n", 1)[0])
        if candidate != "Новый диалог":
            return candidate
    except (ValueError, KeyError, TypeError, OSError, TimeoutError):
        pass
    return fallback_title(text)
