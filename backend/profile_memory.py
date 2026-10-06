"""Optional private user context and bounded, inspectable assistant memory."""

from backend.business import DomainError, choice, identity, integer, packed, stamp, string, transaction
import re

FIELDS = {'first_name': 80, 'last_name': 80, 'profession': 120, 'company': 120, 'about': 2000}


def profile(con, user):
    row = con.execute('SELECT * FROM user_profiles WHERE user_id=?', (user['id'],)).fetchone()
    if row:
        return {key: value for key, value in dict(row).items() if key != 'user_id'}
    names = user['name'].split(' ', 1)
    return dict(first_name=names[0], last_name=names[1] if len(names) > 1 else '',
                profession='', company='', about='', response_style='concise', memory_enabled=1, updated_at=0)


def profile_route(con, user, method, data):
    if method == 'GET':
        return {'profile': profile(con, user)}
    if method != 'PATCH':
        raise DomainError(405, 'Метод не поддерживается')
    if not isinstance(data, dict) or not data or not set(data).issubset(set(FIELDS) | {'response_style', 'memory_enabled'}):
        raise DomainError(400, 'Неверные поля профиля')
    values = {key: string(value, 'Поле профиля', FIELDS[key]) for key, value in data.items() if key in FIELDS}
    if 'response_style' in data:
        values['response_style'] = choice(data['response_style'], ('concise', 'balanced', 'detailed'), 'Стиль ответа')
    if 'memory_enabled' in data:
        values['memory_enabled'] = integer(data['memory_enabled'], 'Память', 0, 1)
    with transaction(con):
        current = profile(con, user)
        current.update(values, updated_at=stamp())
        con.execute(
            'INSERT INTO user_profiles(user_id,first_name,last_name,profession,company,about,response_style,memory_enabled,updated_at) '
            'VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET '
            'first_name=excluded.first_name,last_name=excluded.last_name,profession=excluded.profession,company=excluded.company,'
            'about=excluded.about,response_style=excluded.response_style,memory_enabled=excluded.memory_enabled,updated_at=excluded.updated_at',
            (user['id'], *(current[key] for key in (*FIELDS, 'response_style', 'memory_enabled', 'updated_at'))),
        )
        name = ' '.join(filter(None, (current['first_name'], current['last_name'])))
        if name and ('first_name' in values or 'last_name' in values):
            con.execute('UPDATE users SET name=? WHERE id=?', (name[:160], user['id']))
    return {'profile': current}


def memory_items(service):
    return [dict(row) for row in service.con.execute(
        'SELECT id,title,content,source,enabled,created_at,updated_at FROM assistant_memory '
        'WHERE user_id=? AND workspace_id=? ORDER BY updated_at DESC LIMIT 50', (service.user['id'], service.wid),
    )]


def _save(service, data, source='manual'):
    title = string(data.get('title', ''), 'Название', 120, True)
    content = string(data.get('content', ''), 'Содержание', 1500, True)
    key = title.casefold()
    enabled = 1 if source == 'assistant' else integer(data.get('enabled', 1), 'Активность', 0, 1)
    with transaction(service.con):
        old = service.con.execute('SELECT id FROM assistant_memory WHERE user_id=? AND workspace_id=? AND title_key=?',
                                  (service.user['id'], service.wid, key)).fetchone()
        count = service.con.execute('SELECT count(*) FROM assistant_memory WHERE user_id=? AND workspace_id=?',
                                    (service.user['id'], service.wid)).fetchone()[0]
        if not old and count >= 50:
            raise DomainError(409, 'В памяти максимум 50 записей. Удалите ненужные')
        item_id = old['id'] if old else identity()
        service.con.execute(
            'INSERT INTO assistant_memory(id,workspace_id,user_id,title,title_key,content,source,enabled,created_at,updated_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,user_id,title_key) '
            'DO UPDATE SET content=excluded.content,source=excluded.source,enabled=excluded.enabled,updated_at=excluded.updated_at',
            (item_id, service.wid, service.user['id'], title, key, content, source, enabled, stamp(), stamp()),
        )
    return {'saved': True, 'id': item_id, 'title': title}


def memory_route(service, method, parts, data):
    if method == 'GET' and not parts:
        return 200, {'items': memory_items(service), 'enabled': bool(profile(service.con, service.user)['memory_enabled'])}
    if method == 'POST' and not parts:
        return 201, _save(service, data)
    if len(parts) != 1:
        raise DomainError(404, 'Запись памяти не найдена')
    row = service.con.execute('SELECT * FROM assistant_memory WHERE id=? AND user_id=? AND workspace_id=?',
                              (parts[0], service.user['id'], service.wid)).fetchone()
    if not row:
        raise DomainError(404, 'Запись памяти не найдена')
    if method == 'DELETE':
        service.con.execute('DELETE FROM assistant_memory WHERE id=? AND user_id=? AND workspace_id=?',
                            (parts[0], service.user['id'], service.wid))
        return 200, {'ok': True}
    if method == 'PATCH':
        if not data or not set(data).issubset({'title', 'content', 'enabled'}):
            raise DomainError(400, 'Неверные поля памяти')
        title = string(data.get('title', row['title']), 'Название', 120, True)
        content = string(data.get('content', row['content']), 'Содержание', 1500, True)
        enabled = integer(data.get('enabled', row['enabled']), 'Активность', 0, 1)
        service.con.execute('UPDATE assistant_memory SET title=?,title_key=?,content=?,enabled=?,updated_at=? '
                            'WHERE id=? AND user_id=? AND workspace_id=?',
                            (title, title.casefold(), content, enabled, stamp(), parts[0], service.user['id'], service.wid))
        return 200, {'ok': True}
    raise DomainError(405, 'Метод не поддерживается')


def remember(service, args, prompt):
    if not profile(service.con, service.user)['memory_enabled']:
        return {'saved': False, 'reason': 'Автоматическая память выключена пользователем'}
    evidence = string(args.get('evidence', ''), 'Цитата пользователя', 1500, True)
    if evidence not in prompt:
        raise DomainError(400, 'Для памяти нужна точная цитата из текущего сообщения пользователя')
    from backend.assistant_files import _SECRET

    if _SECRET.search(packed(args)) or re.search(r'\b(?:live_|test_|sk-)[A-Za-z0-9_-]{20,}|-----BEGIN .*PRIVATE KEY', packed(args)):
        raise DomainError(400, 'Секреты нельзя сохранять в память')
    return _save(service, args, 'assistant')


def assistant_context(service):
    from backend.assistant_files import _SECRET

    info = profile(service.con, service.user)
    info['about'] = info['about'][:1000]
    facts = [{'title': item['title'], 'content': item['content'][:400]} for item in memory_items(service) if item['enabled']][:5] if info['memory_enabled'] else []
    return _SECRET.sub('[секрет скрыт]', packed({'profile': info, 'memory': facts}))
