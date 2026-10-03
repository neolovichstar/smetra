"""File preparation uses the durable worker without spending model quota."""

import hashlib
import json
import os
import subprocess
import sys

from backend.business import DomainError, identity, packed, stamp, string, transaction

ACTIVE = ("queued", "running", "retry")


def state(service, row):
    status = row["index_status"] if row["index_hash"] == row["sha256"] else "legacy"
    job = (
        service.con.execute(
            "SELECT id,status,cancel_requested FROM assistant_jobs WHERE workspace_id=? AND user_id=? AND kind='file_index' AND file_id=? AND source_sha256=? ORDER BY CASE WHEN status IN ('queued','running','retry') THEN 0 WHEN status='completed' THEN 1 ELSE 2 END,created_at DESC,id DESC LIMIT 1",
            (service.wid, service.user["id"], row["id"], row["sha256"]),
        ).fetchone()
        if service.user
        else None
    )
    return {
        "state": status,
        "error": row["index_error"] if status == "failed" else "",
        "job_id": job["id"] if job else None,
        "can_cancel": bool(job and job["status"] in ACTIVE),
        "cancel_requested": bool(job and job["cancel_requested"]),
        "max_bytes": 5_000_000,
        "pages": row["index_pages"],
        "truncated": bool(row["index_truncated"]),
        "supported": row["mime"] in ("text/plain", "application/pdf"),
    }


def enqueue(service, row, key=None):
    if row["mime"] not in ("text/plain", "application/pdf") or row["size"] > 5_000_000:
        raise DomainError(422, "Для подготовки выберите PDF, TXT или Markdown до 5 МБ")
    if len(os.getenv("ASSISTANT_WORKER_SECRET", "")) < 32:
        raise DomainError(503, "Фоновая обработка пока не подключена")
    fresh = service.get("files", row["id"])
    service.con.execute(
        "UPDATE assistant_jobs SET cancel_requested=1,updated_at=? WHERE file_id=? AND workspace_id=? AND user_id=? AND kind='file_index' AND source_sha256<>? AND status IN ('queued','running','retry')",
        (stamp(), row["id"], service.wid, service.user["id"], fresh["sha256"]),
    )
    key = string(key or identity(), "Ключ операции", 100, True)
    request_hash = hashlib.sha256(
        packed([row["id"], row["sha256"]]).encode()
    ).hexdigest()
    previous = service.con.execute(
        "SELECT id,request_hash FROM assistant_jobs WHERE workspace_id=? AND user_id=? AND request_key=?",
        (service.wid, service.user["id"], key),
    ).fetchone()
    if previous:
        if previous["request_hash"] != request_hash:
            raise DomainError(409, "Этот ключ уже использован для другой обработки")
        return state(service, fresh)
    if fresh["index_hash"] == fresh["sha256"] and fresh["index_status"] in (
        *ACTIVE,
        "ready",
        "needs_ocr",
    ):
        return state(service, fresh)
    count = service.con.execute(
        "SELECT count(*) FROM assistant_jobs WHERE workspace_id=? AND user_id=? AND kind='file_index' AND status IN ('queued','running','retry')",
        (service.wid, service.user["id"]),
    ).fetchone()[0]
    if count >= 10:
        raise DomainError(429, "Дождитесь подготовки предыдущих файлов")
    now = stamp()
    service.con.execute(
        "INSERT INTO assistant_jobs(id,workspace_id,user_id,session_hash,request_key,request_hash,prompt,context,quota_key,quota_refunded,kind,file_id,source_sha256,next_attempt_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            identity(),
            service.wid,
            service.user["id"],
            service.h.session_token_hash,
            key,
            request_hash,
            "Подготовка · " + row["name"],
            "null",
            "",
            1,
            "file_index",
            row["id"],
            row["sha256"],
            now,
            now,
            now,
        ),
    )
    service.con.execute(
        "UPDATE files SET index_status='queued',index_hash=sha256,index_error='' WHERE id=? AND workspace_id=?",
        (row["id"], service.wid),
    )
    return state(service, service.get("files", row["id"]))


def ensure_ready(service, context):
    if not context or context["entity"] != "files":
        return
    row = service.get("files", context["id"])
    if row["index_hash"] == row["sha256"] and row["index_status"] in ACTIVE:
        raise DomainError(
            409, "Документ ещё готовится. Дождитесь завершения — сообщение не потрачено"
        )
    if (
        row["index_status"] == "failed"
        or row["size"] > 2_000_000
        and not (row["index_status"] == "ready" and row["index_hash"] == row["sha256"])
    ):
        raise DomainError(409, "Сначала подготовьте документ для ассистента")


def terminal(con, job, status, error=""):
    if job["kind"] == "file_index":
        con.execute(
            "UPDATE files SET index_status=?,index_error=? WHERE id=? AND workspace_id=? AND sha256=? AND index_status IN ('queued','running','retry') AND NOT EXISTS (SELECT 1 FROM assistant_jobs j WHERE j.file_id=files.id AND j.source_sha256=files.sha256 AND j.id<>? AND j.status IN ('queued','running','retry'))",
            (
                status,
                error[:200],
                job["file_id"],
                job["workspace_id"],
                job["source_sha256"],
                job["id"],
            ),
        )


def isolated_extract(raw, mime):
    # The parser does not need database/model credentials. Preserve only Python
    # import paths and OS essentials (including Windows QA compatibility).
    environment = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL")
        if key in os.environ
    }
    environment["PYTHONPATH"] = os.pathsep.join(sys.path)
    environment["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "backend.file_extractor", mime],
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=25,
        env=environment,
    )
    if result.returncode or len(result.stdout) > 800_000:
        raise ValueError("extractor")
    return json.loads(result.stdout)


def process(service, job, complete, progress, validate):
    from backend.attachments import download

    row = service.get("files", job["file_id"])
    if row["sha256"] != job["source_sha256"]:
        raise DomainError(409, "Документ изменился; старую подготовку остановили")
    progress("Извлекаю текст документа…")
    raw = download(row, service.con).data
    try:
        extracted = isolated_extract(raw, row["mime"])
        if not isinstance(extracted, dict) or not isinstance(
            extracted.get("truncated"), bool
        ):
            raise ValueError("result")
        pages = extracted["pages"]
        if (
            not isinstance(pages, list)
            or len(pages) > 12
            or any(
                not isinstance(page, list)
                or len(page) != 2
                or not isinstance(page[0], int)
                or not 1 <= page[0] <= 12
                or not isinstance(page[1], str)
                or len(page[1]) > 120_000
                for page in pages
            )
        ):
            raise ValueError("pages")
        if len({page[0] for page in pages}) != len(pages):
            raise ValueError("duplicate pages")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        raise DomainError(
            422,
            "Не удалось безопасно прочитать документ. Попробуйте текстовый PDF или TXT",
        ) from None
    progress("Сохраняю текст для поиска…")
    with transaction(service.con):
        # Repeat session/role checks after parsing, and fence both source and lease.
        validate()
        fresh = service.get("files", row["id"])
        if fresh["sha256"] != job["source_sha256"]:
            raise DomainError(409, "Документ изменился; старый текст не сохранён")
        complete(
            {
                "file_id": row["id"],
                "name": row["name"],
                "pages": len(pages),
                "truncated": bool(extracted["truncated"]),
                "needs_ocr": not any(text.strip() for _, text in pages),
            }
        )
        service.con.execute(
            "DELETE FROM file_text_chunks WHERE file_id=? AND workspace_id=?",
            (row["id"], service.wid),
        )
        for number, text in pages:
            if text.strip():
                service.con.execute(
                    "INSERT INTO file_text_chunks(file_id,workspace_id,page,text,source_sha256) VALUES(?,?,?,?,?)",
                    (
                        row["id"],
                        service.wid,
                        number,
                        text[:120_000],
                        job["source_sha256"],
                    ),
                )
        service.con.execute(
            "UPDATE files SET index_status=?,index_hash=sha256,index_error='',index_truncated=?,index_pages=? WHERE id=? AND workspace_id=?",
            (
                "ready" if any(text.strip() for _, text in pages) else "needs_ocr",
                int(bool(extracted["truncated"])),
                len(pages),
                row["id"],
                service.wid,
            ),
        )


def cancel(service, row):
    job = service.con.execute(
        "SELECT * FROM assistant_jobs WHERE workspace_id=? AND user_id=? AND kind='file_index' AND file_id=? AND source_sha256=? AND status IN ('queued','running','retry') ORDER BY created_at DESC,id DESC LIMIT 1",
        (service.wid, service.user["id"], row["id"], row["sha256"]),
    ).fetchone()
    if job:
        if job["status"] == "running":
            service.con.execute(
                "UPDATE assistant_jobs SET cancel_requested=1,updated_at=? WHERE id=?",
                (stamp(), job["id"]),
            )
        else:
            service.con.execute(
                "UPDATE assistant_jobs SET status='cancelled',updated_at=? WHERE id=?",
                (stamp(), job["id"]),
            )
            terminal(service.con, job, "cancelled")
    return state(service, service.get("files", row["id"]))
