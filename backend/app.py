import base64
import hashlib
import hmac
import http.server
import json
import os
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv('DB_PATH', str(ROOT / 'data' / 'smetra.sqlite3')))
WEB = ROOT / 'apps' / 'web'
PORT = int(os.getenv('PORT', '8080'))
ORIGIN = os.getenv('PUBLIC_ORIGIN', f'http://localhost:{PORT}').rstrip('/')
COOKIE_SECURE = ORIGIN.startswith('https://')
_LOCK = threading.RLock()
RATE = {}
PLANS = {'pro_month': (49000, 31), 'pro_year': (490000, 366)}


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA busy_timeout=10000')
    return con


def migrate():
    with db() as con:
        con.executescript((ROOT / 'backend' / 'schema.sql').read_text())


def now():
    return int(time.time())


def uid():
    return str(uuid.uuid4())


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + digest).decode()


def verify_password(password, encoded):
    try:
        value = base64.b64decode(encoded)
        return hmac.compare_digest(base64.b64decode(hash_password(password, value[:16]))[16:], value[16:])
    except (ValueError, TypeError):
        return False


def audit(con, actor, action, target, detail=''):
    con.execute('INSERT INTO audit(id,actor_id,action,target,detail,created_at) VALUES(?,?,?,?,?,?)', (uid(), actor, action, target, detail[:500], now()))


def event(con, user_id, name):
    con.execute('INSERT INTO events(id,user_id,name,created_at) VALUES(?,?,?,?)', (uid(), user_id, name, now()))


def user_view(user, con):
    expiry = user['entitlement_until'] or 0
    return {'id': user['id'], 'email': user['email'], 'name': user['name'], 'role': user['role'],
            'plan': user['plan'] if expiry > now() else 'free', 'entitlement_until': expiry,
            'quote_count': con.execute('SELECT count(*) FROM quotes WHERE user_id=?', (user['id'],)).fetchone()[0]}


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'Smetra/1.0'

    def log_message(self, fmt, *args):
        print(json.dumps({'time': now(), 'remote': self.client_address[0], 'message': fmt % args}, ensure_ascii=False), flush=True)

    def send_json(self, status, payload, cookie=None):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        size = int(self.headers.get('Content-Length', '0'))
        if size > 65536 or size < 0:
            raise ApiError(413, 'Слишком большой запрос')
        try:
            data = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(data, dict): raise ValueError('Expected object')
            return data
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, 'Некорректный JSON')

    def route(self):
        parsed = urllib.parse.urlsplit(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    def auth(self, con, admin=False):
        raw = self.headers.get('Authorization', '')
        token = raw[7:] if raw.startswith('Bearer ') else ''
        if not token:
            cookie = self.headers.get('Cookie', '')
            for part in cookie.split(';'):
                if part.strip().startswith('session='):
                    token = part.strip()[8:]
        if not token:
            raise ApiError(401, 'Войдите в аккаунт')
        row = con.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?', (hashlib.sha256(token.encode()).hexdigest(), now())).fetchone()
        if not row:
            raise ApiError(401, 'Сессия истекла')
        if row['blocked']:
            raise ApiError(403, 'Аккаунт заблокирован')
        if admin and row['role'] != 'admin':
            raise ApiError(403, 'Недостаточно прав')
        return row

    def throttle(self, key, limit=15, window=60):
        with _LOCK:
            moment = now()
            count, start = RATE.get(key, (0, moment))
            if moment - start >= window:
                count, start = 0, moment
            if count >= limit:
                raise ApiError(429, 'Слишком много запросов. Попробуйте позже')
            RATE[key] = (count + 1, start)

    def require_origin(self):
        origin = self.headers.get('Origin')
        if origin and origin != ORIGIN:
            raise ApiError(403, 'Неверный источник запроса')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise ApiError(403, 'Запрос отклонён')

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def do_PATCH(self):
        self.dispatch('PATCH')

    def do_DELETE(self):
        self.dispatch('DELETE')

    def dispatch(self, method):
        try:
            path, query = self.route()
            if method != 'GET' and path != '/api/webhooks/yookassa':
                self.require_origin()
            if path.startswith('/api/'):
                with db() as con:
                    self.api(method, path, query, con)
            elif method == 'GET':
                self.static(path)
            else:
                raise ApiError(404, 'Не найдено')
        except ApiError as err:
            self.send_json(err.status, {'error': err.message})
        except Exception as err:
            print(json.dumps({'time': now(), 'error': repr(err), 'path': self.path}), flush=True)
            self.send_json(500, {'error': 'Внутренняя ошибка. Попробуйте позже'})

    def static(self, path):
        if path == '/health':
            with db() as con:
                con.execute('SELECT 1')
            return self.send_json(200, {'ok': True})
        public = {'/': ('index.html', 'text/html'), '/app': ('app.html', 'text/html'), '/admin': ('admin.html', 'text/html'), '/privacy': ('privacy.html', 'text/html'), '/terms': ('terms.html', 'text/html'), '/style.css': ('style.css', 'text/css'), '/app.js': ('app.js', 'text/javascript'), '/robots.txt': ('robots.txt', 'text/plain'), '/sitemap.xml': ('sitemap.xml', 'application/xml')}
        if path not in public:
            raise ApiError(404, 'Страница не найдена')
        file, typ = public[path]
        data = (WEB / file).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', typ + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def api(self, method, path, query, con):
        if path == '/api/auth/register' and method == 'POST':
            self.throttle('register:' + self.client_address[0], 5, 3600)
            data = self.body()
            email = str(data.get('email', '')).strip().lower()
            password = str(data.get('password', ''))
            name = str(data.get('name', '')).strip()
            if '@' not in email or len(email) > 254 or len(password) < 12 or len(password) > 128 or not 1 <= len(name) <= 80:
                raise ApiError(400, 'Укажите имя, почту и пароль от 12 символов')
            try:
                user_id = uid()
                con.execute('INSERT INTO users(id,email,password_hash,name,created_at) VALUES(?,?,?,?,?)', (user_id,email,hash_password(password),name,now()))
                event(con,user_id,'signup_completed')
            except sqlite3.IntegrityError:
                raise ApiError(409, 'Такая почта уже зарегистрирована')
            return self.login_response(con, user_id)
        if path == '/api/auth/login' and method == 'POST':
            self.throttle('login:' + self.client_address[0], 10, 300)
            data = self.body()
            user = con.execute('SELECT * FROM users WHERE email=?', (str(data.get('email','')).lower().strip(),)).fetchone()
            if not user or not verify_password(str(data.get('password','')), user['password_hash']):
                raise ApiError(401, 'Неверная почта или пароль')
            if user['blocked']:
                raise ApiError(403, 'Аккаунт заблокирован')
            return self.login_response(con, user['id'])
        if path == '/api/public/quote' and method == 'GET':
            token = query.get('token', [''])[0]
            row = con.execute('SELECT q.*,u.name AS author FROM quotes q JOIN users u ON u.id=q.user_id WHERE q.public_token=?', (token,)).fetchone()
            if not row:
                raise ApiError(404, 'Предложение не найдено')
            return self.send_json(200, {'quote': self.quote_view(row), 'author': row['author']})
        if path == '/api/public/accept' and method == 'POST':
            data = self.body()
            token = str(data.get('token',''))
            self.throttle('accept:' + self.client_address[0], 20, 3600)
            row = con.execute('SELECT * FROM quotes WHERE public_token=?', (token,)).fetchone()
            if not row:
                raise ApiError(404, 'Предложение не найдено')
            if row['status'] != 'sent':
                raise ApiError(409, 'Предложение уже обработано')
            changed = con.execute("UPDATE quotes SET status='accepted',updated_at=? WHERE id=? AND status='sent'", (now(),row['id']))
            if not changed.rowcount: raise ApiError(409,'Предложение уже обработано')
            event(con,row['user_id'],'quote_accepted')
            return self.send_json(200, {'ok': True})
        if path == '/api/webhooks/yookassa' and method == 'POST':
            self.throttle('webhook:' + self.client_address[0], 120, 60)
            data = self.body()
            payment_id = str(data.get('object',{}).get('id',''))
            if not payment_id or len(payment_id)>100:
                raise ApiError(400, 'Некорректный платеж')
            payment = con.execute('SELECT * FROM payments WHERE provider_id=?',(payment_id,)).fetchone()
            if not payment:
                raise ApiError(404, 'Платеж не найден')
            verified = self.provider_payment(payment_id)
            self.apply_payment(con,payment,verified)
            return self.send_json(200, {'ok': True})
        user = self.auth(con, path.startswith('/api/admin/'))
        if path == '/api/me' and method == 'GET':
            return self.send_json(200, {'user': user_view(user,con)})
        if path == '/api/auth/logout' and method == 'POST':
            token = self.headers.get('Authorization','')[7:] if self.headers.get('Authorization','').startswith('Bearer ') else ''
            if not token:
                for part in self.headers.get('Cookie','').split(';'):
                    if part.strip().startswith('session='): token=part.strip()[8:]
            con.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
            return self.send_json(200,{'ok':True},self.cookie('',0))
        if path == '/api/me' and method == 'DELETE':
            con.execute('DELETE FROM users WHERE id=?',(user['id'],))
            audit(con,None,'account.deleted',user['id'])
            return self.send_json(200,{'ok':True},self.cookie('',0))
        if path == '/api/quotes' and method == 'GET':
            try: offset = max(0,min(int(query.get('offset',['0'])[0]),100000))
            except ValueError: raise ApiError(400,'Неверная страница')
            search = '%' + str(query.get('q',[''])[0])[:80].replace('%','\\%').replace('_','\\_') + '%'
            rows = con.execute("SELECT * FROM quotes WHERE user_id=? AND (title LIKE ? ESCAPE '\\' OR client LIKE ? ESCAPE '\\') ORDER BY created_at DESC LIMIT 30 OFFSET ?",(user['id'],search,search,offset)).fetchall()
            return self.send_json(200, {'quotes':[self.quote_view(r) for r in rows]})
        if path == '/api/quotes' and method == 'POST':
            data = self.body()
            count = con.execute("SELECT count(*) FROM events WHERE user_id=? AND name='quote_created'",(user['id'],)).fetchone()[0]
            if count >= (10 if (user['entitlement_until'] or 0) <= now() else 10000):
                raise ApiError(402,'Лимит бесплатного тарифа: 10 предложений')
            title, client = str(data.get('title','')).strip(), str(data.get('client','')).strip()
            try:
                amount = int(data.get('amount',0))
            except (TypeError, ValueError):
                raise ApiError(400,'Укажите сумму в копейках')
            description = str(data.get('description','')).strip()
            if not 1<=len(title)<=120 or not 1<=len(client)<=120 or not 1<=amount<=10000000000 or len(description)>3000:
                raise ApiError(400,'Проверьте название, клиента, описание и сумму')
            qid=uid()
            con.execute('INSERT INTO quotes(id,user_id,title,client,description,amount_kopecks,public_token,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(qid,user['id'],title,client,description,amount,secrets.token_urlsafe(24),now(),now()))
            event(con,user['id'],'quote_created')
            return self.send_json(201,{'quote':self.quote_view(con.execute('SELECT * FROM quotes WHERE id=?',(qid,)).fetchone())})
        if path.startswith('/api/quotes/'):
            qid=path.removeprefix('/api/quotes/')
            row=con.execute('SELECT * FROM quotes WHERE id=? AND user_id=?',(qid,user['id'])).fetchone()
            if not row: raise ApiError(404,'Предложение не найдено')
            if method == 'PATCH':
                data=self.body()
                status=data.get('status')
                if status not in ('sent','declined','completed') or (row['status'],status) not in [('draft','sent'),('sent','declined'),('accepted','completed')]:
                    raise ApiError(409,'Этот переход статуса недоступен')
                con.execute('UPDATE quotes SET status=?,updated_at=? WHERE id=?',(status,now(),qid))
                event(con,user['id'],'quote_'+status)
                return self.send_json(200,{'quote':self.quote_view(con.execute('SELECT * FROM quotes WHERE id=?',(qid,)).fetchone())})
            if method == 'DELETE':
                con.execute('DELETE FROM quotes WHERE id=?',(qid,))
                audit(con,user['id'],'quote.deleted',qid)
                return self.send_json(200,{'ok':True})
        if path == '/api/support' and method == 'POST':
            self.throttle('support:'+user['id'],5,3600)
            message=str(self.body().get('message','')).strip()
            if not 5<=len(message)<=2000: raise ApiError(400,'Опишите вопрос (5–2000 символов)')
            con.execute('INSERT INTO support(id,user_id,message,status,created_at) VALUES(?,?,?,?,?)',(uid(),user['id'],message,'open',now()))
            return self.send_json(201,{'ok':True})
        if path == '/api/billing' and method == 'GET':
            payments=con.execute('SELECT id,plan,amount_kopecks,status,created_at FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 30',(user['id'],)).fetchall()
            return self.send_json(200,{'payments':[dict(r) for r in payments], 'plans':{k:v[0] for k,v in PLANS.items()}})
        if path == '/api/billing/checkout' and method == 'POST':
            data=self.body(); plan=data.get('plan'); key=self.headers.get('Idempotency-Key','')
            if plan not in PLANS or not 16<=len(key)<=100: raise ApiError(400,'Неверный тариф или ключ запроса')
            previous=con.execute('SELECT * FROM payments WHERE user_id=? AND idempotency_key=?',(user['id'],key)).fetchone()
            if previous:
                if previous['plan']!=plan: raise ApiError(409,'Ключ уже использован для другого тарифа')
                return self.send_json(200,{'url':previous['confirmation_url'],'status':previous['status']})
            if not os.getenv('YOOKASSA_SHOP_ID') or not os.getenv('YOOKASSA_SECRET_KEY'):
                raise ApiError(503,'Оплата пока недоступна')
            amount=PLANS[plan][0]
            request={'amount':{'value':f'{amount/100:.2f}','currency':'RUB'},'capture':True,'confirmation':{'type':'redirect','return_url':ORIGIN+'/app?payment=return'},'description':'Сметра: '+plan,'metadata':{'user_id':user['id'],'plan':plan},'receipt':{'customer':{'email':user['email']},'items':[{'description':'Доступ к сервису Сметра: '+plan,'quantity':'1.00','amount':{'value':f'{amount/100:.2f}','currency':'RUB'},'vat_code':1,'payment_mode':'full_payment','payment_subject':'service'}]}}
            result=self.provider_call('/payments','POST',request,key)
            if not result.get('id') or not result.get('confirmation',{}).get('confirmation_url','').startswith('https://'): raise ApiError(502,'Платежный сервис вернул неполный ответ')
            con.execute('INSERT INTO payments(id,user_id,provider_id,plan,amount_kopecks,status,idempotency_key,confirmation_url,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(uid(),user['id'],result['id'],plan,amount,'pending',key,result['confirmation']['confirmation_url'],now()))
            event(con,user['id'],'checkout_started')
            return self.send_json(201,{'url':result['confirmation']['confirmation_url'],'status':'pending'})
        if path == '/api/billing/sync' and method == 'POST':
            self.throttle('sync:'+user['id'],5,60)
            rows=con.execute("SELECT * FROM payments WHERE user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 3",(user['id'],)).fetchall()
            for row in rows: self.apply_payment(con,row,self.provider_payment(row['provider_id']))
            current=con.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
            return self.send_json(200,{'user':user_view(current,con)})
        if path == '/api/admin/overview' and method == 'GET':
            stats={key:con.execute(sql).fetchone()[0] for key,sql in {'users':'SELECT count(*) FROM users','quotes':'SELECT count(*) FROM quotes','subscriptions':'SELECT count(*) FROM users WHERE entitlement_until > unixepoch()','revenue_kopecks':"SELECT coalesce(sum(amount_kopecks),0) FROM payments WHERE status='succeeded'"}.items()}
            users=[dict(r) for r in con.execute('SELECT id,email,name,role,blocked,plan,entitlement_until,created_at FROM users ORDER BY created_at DESC LIMIT 100')]
            tickets=[dict(r) for r in con.execute('SELECT id,user_id,message,status,created_at FROM support ORDER BY created_at DESC LIMIT 100')]
            logs=[dict(r) for r in con.execute('SELECT actor_id,action,target,created_at FROM audit ORDER BY created_at DESC LIMIT 100')]
            return self.send_json(200,{'stats':stats,'users':users,'tickets':tickets,'audit':logs})
        if path.startswith('/api/admin/users/') and method == 'PATCH':
            target=path.removeprefix('/api/admin/users/')
            data=self.body(); action=data.get('action')
            if target==user['id'] and action=='block': raise ApiError(409,'Нельзя заблокировать себя')
            if not con.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone(): raise ApiError(404,'Пользователь не найден')
            if action in ('block','unblock'):
                con.execute('UPDATE users SET blocked=? WHERE id=?',(int(action=='block'),target))
                if action=='block': con.execute('DELETE FROM sessions WHERE user_id=?',(target,))
            elif action=='grant':
                con.execute("UPDATE users SET plan='pro',entitlement_until=max(coalesce(entitlement_until,0),?)+? WHERE id=?",(now(),31*86400,target))
            elif action=='revoke':
                con.execute("UPDATE users SET plan='free',entitlement_until=0 WHERE id=?",(target,))
            else: raise ApiError(400,'Неизвестное действие')
            audit(con,user['id'],'admin.'+action,target)
            return self.send_json(200,{'ok':True})
        raise ApiError(404,'Маршрут не найден')

    def quote_view(self,r):
        return {k:r[k] for k in ('id','title','client','description','amount_kopecks','status','created_at','updated_at')} | {'public_url':ORIGIN+'/?quote='+r['public_token']}

    def cookie(self,token,age):
        return 'session='+token+'; Path=/; HttpOnly; SameSite=Lax; Max-Age='+str(age)+('; Secure' if COOKIE_SECURE else '')

    def login_response(self,con,user_id):
        token=secrets.token_urlsafe(32)
        con.execute('INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,?)',(uid(),user_id,hashlib.sha256(token.encode()).hexdigest(),now()+30*86400))
        row=con.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
        return self.send_json(200,{'user':user_view(row,con),'token':token},self.cookie(token,30*86400))

    def provider_call(self,path,method='GET',payload=None,key=None):
        credentials=base64.b64encode((os.environ['YOOKASSA_SHOP_ID']+':'+os.environ['YOOKASSA_SECRET_KEY']).encode()).decode()
        headers={'Authorization':'Basic '+credentials,'Content-Type':'application/json'}
        if key: headers['Idempotence-Key']=key
        request=urllib.request.Request('https://api.yookassa.ru/v3'+path,data=json.dumps(payload).encode() if payload else None,headers=headers,method=method)
        try:
            with urllib.request.urlopen(request,timeout=12) as response: return json.load(response)
        except (urllib.error.URLError,TimeoutError) as err:
            print(json.dumps({'payment_api_error':str(err)}),flush=True)
            raise ApiError(502,'Платёжный сервис временно недоступен')

    def provider_payment(self,payment_id):
        return self.provider_call('/payments/'+urllib.parse.quote(payment_id,safe=''))

    def apply_payment(self,con,local,remote):
        if remote.get('id')!=local['provider_id'] or remote.get('amount',{}).get('currency')!='RUB' or remote.get('amount',{}).get('value')!=f"{local['amount_kopecks']/100:.2f}" or remote.get('metadata',{}).get('user_id')!=local['user_id'] or remote.get('metadata',{}).get('plan')!=local['plan']:
            raise ApiError(409,'Данные платежа не совпали')
        status=remote.get('status')
        if status not in ('pending','succeeded','canceled'): return
        with _LOCK:
            con.execute('BEGIN IMMEDIATE')
            try:
                current=con.execute('SELECT status FROM payments WHERE id=?',(local['id'],)).fetchone()
                if current['status']!=status and current['status']=='pending':
                    con.execute('UPDATE payments SET status=? WHERE id=?',(status,local['id']))
                    if status=='succeeded':
                        con.execute("UPDATE users SET entitlement_until=max(coalesce(entitlement_until,0),?)+?,plan=? WHERE id=?",(now(),PLANS[local['plan']][1]*86400,'pro',local['user_id']))
                    event(con,local['user_id'],'payment_'+status)
                    audit(con,None,'payment.'+status,local['id'])
                con.execute('COMMIT')
            except Exception:
                con.execute('ROLLBACK')
                raise


def main():
    migrate()
    server=http.server.ThreadingHTTPServer(('0.0.0.0',PORT),Handler)
    print(f'Smetra listening on {PORT}',flush=True)
    server.serve_forever()


if __name__=='__main__': main()
