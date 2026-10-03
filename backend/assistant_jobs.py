"""Durable assistant queue. Provider calls never hold a database write lock.

The scheduler only wakes a worker; job claims, budgets and results live in SQL.
Each attempt rechecks the original session and workspace membership. Mutations
remain proposals, and proposals/messages/result commit together behind a lease.
"""

import hashlib
import hmac
import json
import os
from backend.business import DomainError, Service, identity, packed, stamp, string, transaction
from backend import assistant

ACTIVE = ('queued', 'running', 'retry')
PUBLIC_COLUMNS = 'id,conversation_id,prompt,status,progress,error,attempts,cancel_requested,created_at,updated_at'


def authenticate(handler):
    secret = os.getenv('ASSISTANT_WORKER_SECRET', '')
    if len(secret) < 32 or not hmac.compare_digest(
        handler.headers.get('Authorization', ''), 'Bearer ' + secret,
    ):
        raise DomainError(401, 'Нет доступа')


def public(row):
    return {key: row[key] for key in PUBLIC_COLUMNS.split(',')}


def refund(con, row):
    changed = con.execute(
        'UPDATE assistant_jobs SET quota_refunded=1 WHERE id=? AND quota_refunded=0 RETURNING id',
        (row['id'],),
    ).fetchone()
    if changed:
        con.execute('UPDATE rate_limits SET count=count-1 WHERE key=? AND count>0', (row['quota_key'],))


def route(service, method, parts, data):
    args = (service.wid, service.user['id'])
    if method == 'GET' and not parts:
        rows = service.con.execute(
            f'SELECT {PUBLIC_COLUMNS} FROM assistant_jobs WHERE workspace_id=? AND user_id=? ORDER BY created_at DESC,id DESC LIMIT 20', args,
        )
        return 200, {'jobs': [public(row) for row in rows], 'enabled': len(os.getenv('ASSISTANT_WORKER_SECRET', '')) >= 32}
    if parts:
        if len(parts) != 1 or method not in ('GET', 'DELETE'):
            raise DomainError(404, 'Задача не найдена')
        if method == 'GET':
            row = service.con.execute(f'SELECT {PUBLIC_COLUMNS},result FROM assistant_jobs WHERE id=? AND workspace_id=? AND user_id=?', (parts[0], *args)).fetchone()
            if not row:
                raise DomainError(404, 'Задача не найдена')
            result = public(row)
            if row['status'] == 'completed':
                result['result'] = json.loads(row['result'])
            return 200, {'job': result, 'quota': assistant.public_quota(service)}
        with transaction(service.con):
            row = service.con.execute('SELECT * FROM assistant_jobs WHERE id=? AND workspace_id=? AND user_id=?', (parts[0], *args)).fetchone()
            if not row:
                raise DomainError(404, 'Задача не найдена')
            if method == 'DELETE' and row['status'] in ACTIVE:
                if row['status'] == 'running':
                    service.con.execute("UPDATE assistant_jobs SET cancel_requested=1,progress='Отменяю…',updated_at=? WHERE id=?", (stamp(), row['id']))
                else:
                    service.con.execute("UPDATE assistant_jobs SET status='cancelled',progress='Отменено',updated_at=? WHERE id=?", (stamp(), row['id']))
                    refund(service.con, row)
            row = service.con.execute('SELECT * FROM assistant_jobs WHERE id=?', (row['id'],)).fetchone()
        result = public(row)
        if row['status'] == 'completed':
            result['result'] = json.loads(row['result'])
        return 200, {'job': result, 'quota': assistant.public_quota(service)}
    if method != 'POST':
        raise DomainError(405, 'Метод не поддерживается')
    if len(os.getenv('ASSISTANT_WORKER_SECRET', '')) < 32 or not assistant.available():
        raise DomainError(503, 'Фоновый ассистент пока не подключён')
    prompt = string(data.get('text', ''), 'Сообщение', 3000, True)
    key = string(service.h.headers.get('Idempotency-Key', ''), 'Ключ запроса', 100, True)
    context = assistant.verified_context(service, data.get('context'))
    thread_id = data.get('conversation_id')
    if thread_id is not None:
        from backend.ai_workspace import conversation

        selected = conversation(service, string(thread_id, 'Диалог', 80, True))
        thread_id = selected['id']
        if 'context' not in data and selected['context_entity']:
            context = assistant.verified_context(service, {'entity': selected['context_entity'], 'id': selected['context_id']})
    request_hash = hashlib.sha256(packed([prompt, context, thread_id]).encode()).hexdigest()
    service.h.throttle('assistant:' + service.user['id'], 12, 60)
    with transaction(service.con):
        existing = service.con.execute('SELECT * FROM assistant_jobs WHERE workspace_id=? AND user_id=? AND request_key=?', (*args, key)).fetchone()
        if existing:
            if existing['request_hash'] != request_hash:
                raise DomainError(409, 'Этот ключ уже используется для другой задачи')
            return 200, {'job': public(existing), 'quota': assistant.public_quota(service)}
        count = service.con.execute("SELECT count(*) AS n FROM assistant_jobs WHERE workspace_id=? AND user_id=? AND status IN ('queued','running','retry')", args).fetchone()['n']
        if count >= 2:
            raise DomainError(429, 'Дождитесь завершения текущих фоновых задач')
        quota_key = assistant.reserve_in_transaction(service)
        job_id, now = identity(), stamp()
        service.con.execute(
            'INSERT INTO assistant_jobs(id,workspace_id,user_id,conversation_id,session_hash,request_key,request_hash,prompt,context,quota_key,next_attempt_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (job_id, *args, thread_id, service.h.session_token_hash, key, request_hash, prompt, packed(context), quota_key, now, now, now),
        )
        row = service.con.execute('SELECT * FROM assistant_jobs WHERE id=?', (job_id,)).fetchone()
    return 202, {'job': public(row), 'quota': assistant.public_quota(service)}


def claim(con):
    now = stamp()
    with transaction(con):
        row = con.execute(
            "SELECT * FROM assistant_jobs WHERE (status IN ('queued','retry') AND next_attempt_at<=?) OR (status='running' AND lease_until<=?) ORDER BY created_at,id LIMIT 1",
            (now, now),
        ).fetchone()
        if not row:
            return None
        if row['cancel_requested'] or row['attempts'] >= 3 or row['created_at'] < now - 3600:
            status = 'cancelled' if row['cancel_requested'] else 'failed'
            con.execute('UPDATE assistant_jobs SET status=?,progress=?,error=?,updated_at=? WHERE id=?',
                        (status, 'Отменено' if status == 'cancelled' else 'Не удалось завершить', '' if status == 'cancelled' else 'Задача не завершилась вовремя. Создайте новую.', now, row['id']))
            refund(con, row)
            return None
        lease = identity()
        con.execute("UPDATE assistant_jobs SET status='running',progress='Проверяю доступ…',attempts=attempts+1,lease_token=?,lease_until=?,updated_at=? WHERE id=?", (lease, now + 180, now, row['id']))
        return dict(con.execute('SELECT * FROM assistant_jobs WHERE id=?', (row['id'],)).fetchone())


def fail(con, job, error):
    with transaction(con):
        row = con.execute('SELECT * FROM assistant_jobs WHERE id=? AND status=\'running\' AND lease_token=?', (job['id'], job['lease_token'])).fetchone()
        if not row:
            return
        cancelled = bool(row['cancel_requested'])
        retry = not cancelled and error.status in (429, 502, 503, 504) and row['attempts'] < 3 and row['created_at'] > stamp() - 3600
        status = 'cancelled' if cancelled else 'retry' if retry else 'failed'
        con.execute('UPDATE assistant_jobs SET status=?,progress=?,error=?,next_attempt_at=?,lease_token=\'\',lease_until=0,updated_at=? WHERE id=?',
                    (status, 'Отменено' if cancelled else 'Повторю позже' if retry else 'Не удалось завершить', '' if cancelled else error.message, stamp() + 60 * (3 ** (row['attempts'] - 1)), stamp(), row['id']))
        if not retry:
            refund(con, row)


def run_one(handler, con, origin):
    authenticate(handler)
    job = claim(con)
    if not job:
        return {'ok': True, 'processed': 0}
    service, lease = Service(handler, con, origin), None
    try:
        user = con.execute(
            'SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.user_id=? AND s.expires_at>? AND u.blocked=0 AND u.deleted_at IS NULL',
            (job['session_hash'], job['user_id'], stamp()),
        ).fetchone()
        member = con.execute('SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?', (job['workspace_id'], job['user_id'])).fetchone()
        if not user or not member:
            raise DomainError(403, 'Доступ изменился. Войдите и создайте задачу заново.')
        service.user, service.wid, service.role = user, job['workspace_id'], member['role']
        service.write_access()
        if getattr(con, 'is_postgres', False):
            from backend.postgres import Connection

            runtime = Connection(runtime=True)
            service.con = service.runtime_connection = runtime
            runtime.scope(job['session_hash'], job['workspace_id'])
        if job['conversation_id']:
            from backend.ai_workspace import conversation

            conversation(service, job['conversation_id'])
        context = assistant.verified_context(service, json.loads(job['context']))
        from backend.redis_infra import RedisUnavailable, acquire_lock

        try:
            lease = acquire_lock('assistant', user['id'], ttl=120)
        except RedisUnavailable:
            raise DomainError(503, 'Ассистент временно недоступен') from None
        if lease is None:
            raise DomainError(429, 'Ожидаю завершения другого ответа')
        service.assistant_deferred_actions = []

        def progress(message):
            row = con.execute("UPDATE assistant_jobs SET progress=?,updated_at=? WHERE id=? AND lease_token=? AND status='running' AND cancel_requested=0 RETURNING id", (message[:120], stamp(), job['id'], job['lease_token'])).fetchone()
            if not row:
                raise DomainError(409, 'Задача отменена')

        def complete(result):
            # This fence is in the same transaction as messages and proposals.
            row = service.con.execute(
                "UPDATE assistant_jobs SET status='completed',progress='Готово',result=?,error='',lease_token='',lease_until=0,updated_at=? WHERE id=? AND status='running' AND lease_token=? AND lease_until>? AND cancel_requested=0 RETURNING id",
                (packed(result), stamp(), job['id'], job['lease_token'], stamp()),
            ).fetchone()
            if not row:
                raise DomainError(409, 'Задача отменена или передана другой попытке')

        assistant.answer_chat(service, job['prompt'], context=context, conversation_id=job['conversation_id'], on_status=progress, on_commit=complete)
        if service.runtime_connection:
            service.runtime_connection.finish(True)
            service.runtime_connection = None
    except Exception as error:
        if service.runtime_connection:
            service.runtime_connection.finish(False)
            service.runtime_connection = None
        fail(con, job, error if isinstance(error, DomainError) else DomainError(502, 'Сервис временно недоступен. Попробую позже.'))
    finally:
        if lease:
            lease.release()
    return {'ok': True, 'processed': 1}
