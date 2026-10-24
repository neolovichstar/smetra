"""Safe declarative quote composition. AI designs presentation, never computes price."""
from backend.business import DomainError, string

ALLOWED = frozenset(("title", "intro", "summary", "items", "breakdown",
                     "notes", "divider", "section", "metrics", "terms", "rooms"))
STYLES = frozenset(("editorial", "minimal", "technical", "compact"))
TONE = frozenset(("neutral", "warm", "graphite", "sage", "sand"))
WIDTHS = frozenset(("full", "half"))
MAX_BLOCKS = 24


def validate_layout(service, data):
    """Read-only validation scoped to authenticated user's workspace and quote.

    Never accepts executable HTML, arbitrary CSS, arbitrary money, or user
    supplied database queries. The renderer binds actual quote data by kind.
    """
    quote_id = string(data.get("id", ""), "ID сметы", 80, True)
    record = service.get("quotes", quote_id)
    blocks = data.get("blocks")
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= MAX_BLOCKS:
        raise DomainError(400, "Укажите от 1 до 24 блоков документа")
    style = data.get("style", "editorial")
    tone = data.get("tone", "neutral")
    if style not in STYLES or tone not in TONE:
        raise DomainError(400, "Неизвестная тема оформления")
    cleaned = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or block.get("kind") not in ALLOWED:
            raise DomainError(400, "Неизвестный блок сметы")
        kind = block["kind"]
        title = string(block.get("title", ""), "Заголовок блока", 100, False)
        description = string(block.get("description", ""), "Описание блока", 400, False)
        width = block.get("width", "full")
        if width not in WIDTHS:
            raise DomainError(400, "Ширина блока должна быть full или half")
        cleaned.append({"kind": kind, "title": title, "description": description,
                        "width": width, "key": str(index)})
    if not any(block["kind"] == "items" for block in cleaned):
        raise DomainError(400, "В визуальной смете необходим блок позиций")
    if not any(block["kind"] == "summary" for block in cleaned):
        raise DomainError(400, "В визуальной смете необходим блок итога")
    return {
        "id": record["id"], "layout": {"version": 1, "style": style, "tone": tone,
                                     "blocks": cleaned}, "source_revision": record["revision"]
    }
