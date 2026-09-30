"""Ephemeral coordination for serverless instances; PostgreSQL remains authoritative."""

from dataclasses import dataclass
import hashlib
import os
import secrets
import time


class RedisUnavailable(Exception):
    pass


@dataclass(frozen=True)
class LimitResult:
    allowed: bool
    retry_after: int = 0


_CLIENT = None
_CLIENT_CONFIG = None
_CIRCUIT_UNTIL = 0.0


def enabled():
    flag = os.getenv("REDIS_ENABLED", "auto").lower()
    if flag in ("0", "false", "off"):
        return False
    url = os.getenv("REDIS_KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("REDIS_KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if flag in ("1", "true", "on") and (not url or not token):
        raise RedisUnavailable("Redis credentials are not configured")
    return bool(url and token)


def environment():
    value = os.getenv("REDIS_ENV") or os.getenv("VERCEL_ENV") or "development"
    if value not in ("production", "preview", "development", "test", "integration"):
        raise ValueError("Invalid Redis environment")
    return value


def key(purpose, *parts):
    if not purpose or not purpose.replace("-", "").isalnum():
        raise ValueError("Invalid Redis key purpose")
    digest = hashlib.sha256(":|:".join(str(part) for part in parts).encode()).hexdigest()
    return f"smetra:{environment()}:{purpose}:{digest}"


class RedisProvider:
    """Narrow provider boundary around the official Upstash HTTP SDK."""

    def __init__(self, client):
        self.client = client

    def get(self, name):
        return self.client.get(name)

    def set(self, name, value, ttl):
        if ttl < 1:
            raise ValueError("TTL is required")
        return self.client.set(name, value, ex=ttl)

    def delete(self, name):
        return self.client.delete(name)

    def exists(self, name):
        return self.client.exists(name)

    def expire(self, name, ttl):
        if ttl < 1:
            raise ValueError("TTL is required")
        return self.client.expire(name, ttl)

    def ttl(self, name):
        return self.client.ttl(name)

    def incr(self, name):
        return self.client.incr(name)

    def decr(self, name):
        return self.client.decr(name)

    def mget(self, names):
        return self.client.mget(*names)

    def mset(self, values):
        return self.client.mset(values)

    def set_nx(self, name, value, ttl):
        if ttl < 1:
            raise ValueError("TTL is required")
        return self.client.set(name, value, nx=True, ex=ttl)

    def eval(self, script, names, args):
        return self.client.eval(script, keys=names, args=[str(arg) for arg in args])

    def scan(self, cursor=0, match=None, count=100):
        return self.client.scan(cursor=cursor, match=match, count=min(count, 100))


def provider():
    global _CLIENT, _CLIENT_CONFIG
    if not enabled():
        return None
    if time.monotonic() < _CIRCUIT_UNTIL:
        raise RedisUnavailable("Redis circuit is open")
    url = os.getenv("REDIS_KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("REDIS_KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
    config = (url, token)
    if _CLIENT is None or _CLIENT_CONFIG != config:
        if not url.startswith("https://"):
            raise RedisUnavailable("Redis REST URL must use HTTPS")
        try:
            import httpx
            from upstash_redis import Redis

            client = Redis(url=url, token=token, rest_retries=0, allow_telemetry=False)
            # SDK 1.8.0 has no public timeout option; pin the version and bound HTTP I/O.
            client._http._client.timeout = httpx.Timeout(2.0, connect=1.0)
            _CLIENT = RedisProvider(client)
            _CLIENT_CONFIG = config
        except (ImportError, AttributeError) as error:
            raise RedisUnavailable("Redis client is unavailable") from error
    return _CLIENT


_GCRA = """
local nowparts = redis.call('TIME')
local now = tonumber(nowparts[1]) * 1000 + math.floor(tonumber(nowparts[2]) / 1000)
local spacing = tonumber(ARGV[1]) / tonumber(ARGV[2])
local tat = tonumber(redis.call('GET', KEYS[1])) or now
local allowed_at = tat - (tonumber(ARGV[2]) - 1) * spacing
if now < allowed_at then
  return {0, math.ceil((allowed_at - now) / 1000)}
end
local next_tat = math.max(now, tat) + spacing
redis.call('SET', KEYS[1], tostring(next_tat), 'PX', tonumber(ARGV[1]) + math.ceil(spacing))
return {1, 0}
"""


def rate_limit(identifier, limit, window):
    if limit < 1 or window < 1:
        raise ValueError("Invalid rate limit")
    client = provider()
    if client is None:
        return None
    try:
        result = client.eval(_GCRA, [key("ratelimit", identifier)], [window * 1000, limit])
        return LimitResult(bool(int(result[0])), max(0, int(result[1])))
    except Exception as error:
        global _CIRCUIT_UNTIL
        _CIRCUIT_UNTIL = time.monotonic() + 10
        raise RedisUnavailable("Redis rate limit failed") from error


_UNLOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class Lease:
    def __init__(self, client, name, token):
        self.client, self.name, self.token = client, name, token

    def release(self):
        if self.client is None:
            return
        try:
            self.client.eval(_UNLOCK, [self.name], [self.token])
        except Exception:
            pass  # TTL bounds the lock; the completed DB transaction is authoritative.
        finally:
            self.client = None


def acquire_lock(purpose, *parts, ttl=120):
    if not 1 <= ttl <= 300:
        raise ValueError("Invalid lock TTL")
    client = provider()
    if client is None:
        return Lease(None, "", "")
    name = key("lock-" + purpose, *parts)
    token = secrets.token_urlsafe(24)
    try:
        if not client.set_nx(name, token, ttl):
            return None
    except Exception as error:
        global _CIRCUIT_UNTIL
        _CIRCUIT_UNTIL = time.monotonic() + 10
        raise RedisUnavailable("Redis lock failed") from error
    return Lease(client, name, token)


def probe():
    try:
        client = provider()
    except RedisUnavailable:
        return {"status": "unavailable"}
    if client is None:
        return "disabled"
    started = time.monotonic()
    try:
        client.client.ping()
        return {"status": "ok", "latency_ms": round((time.monotonic() - started) * 1000)}
    except Exception:
        return {"status": "unavailable"}
