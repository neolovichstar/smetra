"""Short voice-to-estimate drafts. Never persists audio or trusts model arithmetic."""
import base64
import binascii
import json
import os
import urllib.error
import urllib.request

from backend.business import DomainError

SUPPORTED = ("wav", "mp3", "flac")
MAX_AUDIO_BYTES = 1_400_000
MAX_TRANSCRIPT = 7_000

def decode_audio(data):
    if not isinstance(data, dict):
        raise DomainError(400, "Добавьте аудиозапись")
    audio_format = data.get("format")
    if audio_format not in SUPPORTED:
        raise DomainError(400, "Формат аудио: WAV, MP3 или FLAC")
    encoded = data.get("audio")
    if not isinstance(encoded, str) or not 16 <= len(encoded) <= 1_900_000:
        raise DomainError(413, "Аудиозапись должна быть короче и меньше 1,4 МБ")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise DomainError(400, "Аудиофайл повреждён") from None
    if not 64 <= len(raw) <= MAX_AUDIO_BYTES:
        raise DomainError(413, "Аудиозапись должна быть меньше 1,4 МБ")
    valid = {
        "wav": raw[:4] == b"RIFF" and raw[8:12] == b"WAVE",
        "mp3": raw[:3] == b"ID3" or raw[:2] in (bytes((255,251)),bytes((255,243)),bytes((255,242))),
        "flac": raw[:4] == b"fLaC",
    }
    if not valid[audio_format]:
        raise DomainError(400, "Формат и содержимое аудиофайла не совпадают")
    return audio_format, encoded

def transcribe(data):
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise DomainError(503, "Распознавание голоса пока недоступно")
    audio_format, encoded = decode_audio(data)
    model = os.getenv("OPENROUTER_STT_MODEL","openai/whisper-large-v3")
    if model not in ("openai/whisper-large-v3","openai/gpt-4o-mini-transcribe","openai/gpt-4o-transcribe"):
        raise DomainError(503, "Модель распознавания не настроена")
    body = json.dumps({
        "model":model,
        "input_audio":{"data":encoded,"format":audio_format},
        "language":"ru",
        "response_format":"json",
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/audio/transcriptions",body,
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json",
                 "HTTP-Referer":os.getenv("PUBLIC_ORIGIN","https://smetra.online"),
                 "X-OpenRouter-Title":"Smetra"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request,timeout=40) as response:
            raw=response.read(180_001)
        if len(raw)>180_000:
            raise ValueError("STT response too large")
        reply=json.loads(raw)
        text=reply.get("text") if isinstance(reply,dict) else None
        if not isinstance(text,str) or not 1 <= len(text.strip()) <= MAX_TRANSCRIPT:
            raise ValueError("Invalid STT response")
        return text.strip()
    except (urllib.error.URLError,TimeoutError,OSError,ValueError,KeyError,TypeError):
        raise DomainError(502,"Не удалось распознать голос. Попробуйте ещё раз") from None

def draft(service, data):
    # Two-stage bounded pipeline: speech -> reviewed structured draft. Neither
    # OpenRouter call is inside a write transaction. The existing AI drafting
    # layer handles quotas, schema validation and trusted server-side money.
    service.h.throttle("voice:"+service.user["id"],3,300)
    transcript=transcribe(data)
    from backend.ai import draft as estimate_draft
    status,result=estimate_draft(service,{
        "text":"Голосовая заметка прораба. Распознанный текст может содержать "
               "строительный сленг и ошибки распознавания. Не добавляй "
               "неуслышанные работы/цены, помечай сомнительные количества "
               "как требующие проверки.\n\n"+transcript
    })
    return status,{**result,"transcript":transcript,"requires_review":True,
                   "audio_retained":False}
