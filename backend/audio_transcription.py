"""Workspace-scoped audio transcription through OpenRouter with signature validation.

Never execute uploaded media or expose it as public content. Audio is supplied to
the STT provider only after an explicit user action.
"""
import base64
import json
import os
import urllib.error
import urllib.request

from backend.business import DomainError
from backend.attachments import download

AUDIO = {
    ".mp3": ("audio/mpeg", "mp3"),
    ".wav": ("audio/wav", "wav"),
    ".m4a": ("audio/mp4", "m4a"),
    ".ogg": ("audio/ogg", "ogg"),
    ".webm": ("audio/webm", "webm"),
    ".flac": ("audio/flac", "flac"),
    ".aac": ("audio/aac", "aac"),
}
MIMES = frozenset(mime for mime, _ in AUDIO.values())
MAX_AUDIO_BYTES = 3_000_000


def validate_audio(name, raw):
    from pathlib import Path
    extension = Path(name).suffix.lower()
    if extension not in AUDIO or not 0 < len(raw) <= MAX_AUDIO_BYTES:
        raise DomainError(400, "Аудио: MP3, WAV, M4A, OGG, WEBM, FLAC или AAC до 3 МБ")
    signatures = {
        ".mp3": raw[:3] == b"ID3" or len(raw) >= 2 and raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0,
        ".wav": raw[:4] == b"RIFF" and raw[8:12] == b"WAVE",
        ".m4a": raw[4:8] == b"ftyp" and len(raw) >= 16,
        ".ogg": raw[:4] == b"OggS",
        ".webm": raw[:4] == b"\x1a\x45\xdf\xa3",
        ".flac": raw[:4] == b"fLaC",
        ".aac": len(raw) >= 7 and raw[0] == 0xFF and raw[1] & 0xF6 == 0xF0,
    }
    if not signatures[extension]:
        raise DomainError(400, "Аудиофайл повреждён или расширение не совпадает с форматом")
    if extension == ".wav":
        import io
        import wave
        try:
            with wave.open(io.BytesIO(raw), "rb") as source:
                if source.getframerate() <= 0 or source.getnframes() / source.getframerate() > 180:
                    raise ValueError("duration")
        except (ValueError, EOFError, wave.Error):
            raise DomainError(400, "WAV повреждён или длиннее 3 минут") from None
    return AUDIO[extension]


def transcribe(service, file_id):
    row = service.get("files", file_id)
    service.write_access()
    if row["mime"] not in MIMES:
        raise DomainError(422, "Выбранный файл не является аудио")
    existing = service.con.execute(
        "SELECT text FROM file_text_chunks WHERE file_id=? AND workspace_id=? AND source_sha256=? ORDER BY page LIMIT 1",
        (row["id"], service.wid, row["sha256"]),
    ).fetchone()
    if row["index_status"] == "ready" and row["index_hash"] == row["sha256"] and existing:
        return 200, {"text": existing["text"], "cached": True}
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise DomainError(503, "Распознавание аудио ещё не настроено")
    service.h.throttle("transcribe:" + service.user["id"], 4, 600)
    from backend.redis_infra import acquire_lock, RedisUnavailable
    try:
        lease = acquire_lock("transcription", row["id"], ttl=90)
    except RedisUnavailable:
        raise DomainError(503, "Распознавание временно недоступно") from None
    if lease is None:
        raise DomainError(409, "Аудио уже распознаётся")
    try:
        raw = download(row, service.con).data
        mime, fmt = validate_audio(row["name"], raw)
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/audio/transcriptions",
            json.dumps({
                "model": os.getenv("OPENROUTER_TRANSCRIPTION_MODEL", "openai/whisper-large-v3-turbo"),
                "input_audio": {"data": base64.b64encode(raw).decode("ascii"), "format": fmt},
                "provider": {"data_collection": "deny"},
            }).encode("utf-8"),
            {
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("PUBLIC_ORIGIN", ""),
                "X-OpenRouter-Title": "Smetra",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=58) as response:
                payload = response.read(150_001)
            if len(payload) > 150_000:
                raise ValueError("oversize transcript")
            transcript = json.loads(payload)["text"]
            if not isinstance(transcript, str) or not transcript.strip():
                raise ValueError("empty transcript")
        except urllib.error.HTTPError as error:
            if error.code == 429:
                raise DomainError(429, "Сервис распознавания занят. Попробуйте позже") from None
            raise DomainError(502, "Не удалось распознать аудио. Исходный файл сохранён") from None
        except (OSError, ValueError, KeyError, TypeError):
            raise DomainError(502, "Не удалось распознать аудио. Исходный файл сохранён") from None

        transcript = " ".join(transcript.split())[:120_000]
        if not transcript:
            raise DomainError(422, "В аудио не удалось распознать речь")
        fresh = service.get("files", row["id"])
        if fresh["sha256"] != row["sha256"]:
            raise DomainError(409, "Аудиофайл изменился. Повторите распознавание")
        service.con.execute(
            "INSERT INTO file_text_chunks(file_id,workspace_id,page,text,source_sha256) VALUES(?,?,?,?,?) "
            "ON CONFLICT(file_id,page) DO UPDATE SET text=excluded.text,source_sha256=excluded.source_sha256",
            (row["id"], service.wid, 1, transcript, row["sha256"]),
        )
        service.con.execute(
            "UPDATE files SET index_status='ready',index_hash=sha256,index_method='transcription',"
            "index_pages=1,index_truncated=0,index_error='' WHERE id=? AND workspace_id=? AND sha256=?",
            (row["id"], service.wid, row["sha256"]),
        )
        return 200, {"text": transcript, "cached": False}
    finally:
        lease.release()
