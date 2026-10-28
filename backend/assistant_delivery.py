"""Drive a durable, owned chat job over SSE without tying its lifetime to the socket."""
import json
import logging

from backend.business import DomainError
from backend import assistant_jobs

log = logging.getLogger(__name__)


class DurableChatStream:
    def __init__(self, service, job_id, completed_result=None):
        self.service, self.job_id = service, job_id
        self.completed_result = completed_result

    def write(self, handler):
        service = self.service
        # Persist the queue record / release the request-scoped read transaction
        # before opening the worker's separately scoped connection.
        if service.runtime_connection:
            runtime, service.runtime_connection = service.runtime_connection, None
            runtime.finish(True)
            service.con = service.global_con
        con = service.global_con
        connected = True

        def send(kind, value):
            nonlocal connected
            if not connected:
                return
            try:
                handler.wfile.write(("event: " + kind + "\ndata: " + json.dumps(value, ensure_ascii=False) + "\n\n").encode())
                handler.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                # The queue and SQL completion fence own the job, not the browser.
                connected = False

        try:
            handler.send_response(200)
            for name, value in (
                ("Content-Type", "text/event-stream; charset=utf-8"),
                ("Cache-Control", "no-store, no-transform"),
                ("X-Accel-Buffering", "no"),
                ("X-Content-Type-Options", "nosniff"),
                ("Referrer-Policy", "no-referrer"),
            ):
                handler.send_header(name, value)
            handler.end_headers()
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            connected = False
        send("ready", {"job_id": self.job_id})
        if self.completed_result is not None:
            # Replaying an owned saved answer is read-only. Do not acquire the
            # queue write lock or race a second worker just to return its result.
            send("done", {**self.completed_result, "job_id": self.job_id})
            return
        try:
            job = assistant_jobs.claim(con, self.job_id)
            if job:
                assistant_jobs.process_job(handler, con, service.origin, job, on_event=send)
            row = con.execute(
                "SELECT * FROM assistant_jobs WHERE id=? AND workspace_id=? AND user_id=?",
                (self.job_id, service.wid, service.user["id"]),
            ).fetchone()
            if not row:
                raise DomainError(404, "Задача не найдена")
            if row["status"] == "completed":
                send("done", {**json.loads(row["result"]), "job_id": self.job_id})
            elif row["status"] in assistant_jobs.ACTIVE:
                send("background", {"job": assistant_jobs.public(row)})
            else:
                send("error", {
                    "error": row["error"] or "Ответ остановлен.",
                    "job_id": self.job_id,
                    "cancelled": row["status"] == "cancelled",
                })
        except DomainError as error:
            send("error", {"error": error.message, "job_id": self.job_id})
        except Exception as error:
            log.error("Assistant delivery failed request_id=%s type=%s",
                      getattr(handler, "request_id", ""), type(error).__name__)
            # The durable record remains available to the scheduler and history.
            send("background", {"job": {"id": self.job_id, "status": "queued"}})
