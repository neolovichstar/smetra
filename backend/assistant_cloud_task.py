"""Deterministic, permission-scoped document lookup for explicit cloud requests.

Only server-side tool calls can claim to have found/read a cloud document.
The model gets their results in ordinary assistant/tool messages, with intact
tool call IDs; the original PDF never enters the assistant conversation DB.
"""
import re

from backend.business import DomainError

_CLOUD = re.compile(r"\b(?:гугл(?:е|а|ом)?|google|яндекс(?:е|а|ом)?|yandex|drive|диск(?:е|а|у|ом)?|облак(?:е|а))\b", re.I)
_DOC = re.compile(r"\b(?:pdf|пдф|файл(?:а|е|ов|ы)?|документ(?:а|е|ов|ы)?|черт[её]ж(?:а|ей|и)?|смет[уы])\b", re.I)
_REQUEST = re.compile(r"найд|поиск|поищ|прочит|изуч|проанализ|состав|сдела|созда|подготов", re.I)
_STOP_ACTION = r"\s+(?:и|а|затем|потом)\s+(?:прочит\w*|изуч\w*|состав\w*|сдела\w*|созда\w*|подготов\w*|проанализ\w*|посмотр\w*|найд\w*)"
_WORD = re.compile(r"[^\W_]+", re.U)
_SEARCH_STOP = frozenset({
    "гугл", "гугле", "google", "диск", "диске", "drive", "яндекс",
    "pdf", "пдф", "файл", "файла", "документ", "документа",
    "найди", "найти", "поищи", "прочитай", "прочитать", "полностью",
    "изучи", "сделай", "создай", "составь", "смету", "смета",
    "с", "из", "в", "на", "по", "и", "то", "че", "что", "про",
    "его", "её", "который", "названием", "под", "данным", "данными",
    "идеальными", "все", "всё", "указаны", "указано", "мне", "мой",
})


def request_info(prompt):
    """Extract just the document name; never send the whole command as search."""
    if not isinstance(prompt, str) or not (_CLOUD.search(prompt) and _DOC.search(prompt) and _REQUEST.search(prompt)):
        return None
    text = " ".join(prompt.split())
    provider = ("google_drive" if re.search(r"гугл|google", text, re.I) else
                "yandex_disk" if re.search(r"яндекс|yandex", text, re.I) else "")
    title = ""
    quoted = re.search(r"[«\"]([^»\"]{3,95})[»\"]", text)
    if quoted:
        title = quoted.group(1)
    if not title:
        # «файл что-то про дом на набережной и прочитай его» -> «дом на набережной».
        match = re.search(r"\bпро\s+(.{3,95}?)(?=" + _STOP_ACTION + r"|[.,!?;]|$)", text, re.I)
        if match:
            title = match.group(1)
    if not title:
        match = re.search(r"\b(?:файл|пдф|pdf|документ)\s+(?:под\s+названием\s+|с\s+названием\s+)?(.{3,95}?)(?=" + _STOP_ACTION + r"|[.,!?;]|$)", text, re.I)
        if match:
            title = re.sub(r"^(?:ч[её]\s*то\s+)?про\s+", "", match.group(1), flags=re.I)
    if not title:
        words = [term for term in _WORD.findall(text.casefold()) if len(term) >= 3 and term not in _SEARCH_STOP]
        title = " ".join(words[:4])
    title = title.strip(" «»\"'.,!?;:-")[:100]
    return {"query": title, "provider": provider}


def _file_score(item, query):
    if not isinstance(item, dict) or not isinstance(item.get("name"), str):
        return 0
    name = item["name"].casefold()
    terms = [term for term in _WORD.findall(query.casefold()) if len(term) >= 3 and term not in {"на", "для", "про", "под"}]
    if not terms or not all(term in name for term in terms):
        return 0
    return (20 if query.casefold() in name else 0) + 3 * len(terms) + (2 if name.endswith(".pdf") else 0)


def prepare(service, prompt, on_status=None):
    """Perform real cloud operations only on explicit cloud-document commands.

    Return pairs (tool_name, validated_args, result) for model protocol. When
    names are ambiguous, supply only the search output; do not pick a PDF.
    """
    info = request_info(prompt)
    if info is None:
        return []
    from backend import assistant_app_tools
    search_args = {"query": info["query"]}
    if on_status:
        on_status("Ищу документ на подключённом диске…")
    try:
        found = assistant_app_tools.read(service, "list_cloud_files", search_args)
        if not isinstance(found, dict):
            raise ValueError("invalid cloud search")
    except DomainError as error:
        return [("list_cloud_files", search_args, {"error": error.message, "status": error.status})]
    except (TypeError, ValueError, KeyError):
        return [("list_cloud_files", search_args, {"error": "Не удалось проверить список облачных файлов"})]

    # Only use the provider the user named; another connected disk is not a
    # substitute for the requested document.
    if info["provider"]:
        found = dict(found)
        found["files"] = [item for item in found.get("files", [])
                          if isinstance(item, dict) and item.get("provider") == info["provider"]]
    results = [("list_cloud_files", search_args, found)]
    files = [item for item in found.get("files", []) if isinstance(item, dict) and
             (item.get("mime") == "application/pdf" or str(item.get("name", "")).casefold().endswith(".pdf"))]
    scored = sorted((( _file_score(item, info["query"]), item) for item in files),
                    key=lambda pair: pair[0], reverse=True)
    if not scored or scored[0][0] <= 0:
        return results
    # Two competing exact matches are ambiguous. Don't read the wrong house.
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return results
    chosen = scored[0][1]
    if not isinstance(chosen.get("id"), str):
        return results
    args = {"id": chosen["id"], "page_start": 1}
    if on_status:
        on_status("Читаю страницы PDF без сохранения оригинала…")
    try:
        reading = assistant_app_tools.read(service, "read_cloud_file", args)
        if not isinstance(reading, dict):
            raise ValueError("invalid cloud extraction")
    except DomainError as error:
        reading = {"name": chosen.get("name"), "error": error.message, "status": error.status,
                   "verified": False}
    except (TypeError, ValueError, KeyError):
        reading = {"name": chosen.get("name"), "error": "Не удалось разобрать PDF",
                   "verified": False}
    results.append(("read_cloud_file", args, reading))
    return results
